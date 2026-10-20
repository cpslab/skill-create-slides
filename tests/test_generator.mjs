import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {CPS,loadProfile,resolveStructure,wrapTitle} from '../assets/layouts/cps.mjs';

test('automatic English heading wrap avoids a stranded final word and preserves explicit breaks',()=>{
 const title='Separate permission to discuss and to publish';
 const wrapped=wrapTitle(title,7.55,24);
 assert.equal(wrapped.replaceAll('\n',' '),title);
 assert.ok(wrapped.split('\n').at(-1).split(' ').length>1);
 assert.equal(wrapTitle('First line\nSecond line',7.55,24),'First line\nSecond line');
});

const metadata={title:'Understanding decisions in community research',short_title:'Community research',authors:'Example Researcher · Example Group',contact:'researcher@example.org'};
function harness(profile) {
 const charts=[],edges=[];
 const makeShape=options=>{
  const text={},shape={...options};
  Object.defineProperty(shape,'text',{get:()=>text,set:value=>{text.value=value;}});
  return shape;
 };
 const presentation={slides:{add:()=>({
  background:{},
  shapes:{add:makeShape,connect:(from,to,options)=>{edges.push({from,to,...options});return {};}},
  charts:{add:(type,options)=>{const chart={type,...options};charts.push(chart);return chart;}},
  speakerNotes:{textFrame:{setText(){}}}
 })}};
 const cps=new CPS(presentation,profile,{metadata},'.',null);
 cps.logo=async()=>{};
 return {cps,charts,edges};
}
function overlap(a,b) {
 const [x,y,w,h]=a,[xx,yy,ww,hh]=b;
 return x<xx+ww-.001&&xx<x+w-.001&&y<yy+hh-.001&&yy<y+h-.001;
}
const chartData=values=>({unit:'change',subject:'participants',aggregation:'mean',status:'measured',categories:['A','B'],series:[{name:'Difference',values}]});
const nodes=[{id:'a',text:'A',bounds_in:[1,2,2,.5]},{id:'b',text:'B',bounds_in:[5,2,2,.5]}];

test('undeclared and duplicate chapter IDs cannot silently corrupt contents ranges',async()=>{
 const profile=await loadProfile('cps-workshop');
 const input={structure:{sections:[{id:'study',title:'Study'}]},slides:[
  {id:'cover',type:'cover'},{id:'contents',type:'toc'},
  {id:'question',type:'question',section:'study'},{id:'summary',type:'summary'}]};
 assert.deepEqual(resolveStructure(input,profile).ranges.map(s=>[s.start,s.end]),[[3,3]]);
 const misspelt=structuredClone(input);misspelt.slides[2].section='stduy';
 assert.throws(()=>resolveStructure(misspelt,profile),/Unknown section/);
 const duplicate=structuredClone(input);duplicate.structure.sections.push({id:'study',title:'Duplicate'});
 assert.throws(()=>resolveStructure(duplicate,profile),/duplicate section ID/);
 const missing=structuredClone(input);delete missing.structure.sections[0].id;
 assert.throws(()=>resolveStructure(missing,profile),/Missing\/duplicate section ID/);
});

test('signed results remain inside the default chart axis',async()=>{
 const {cps,charts}=harness(await loadProfile('cps-workshop'));cps.start({id:'results',number:1});
 cps.chart('mixed',chartData([-4,3]),[.5,1.5,9,3]);
 cps.chart('negative',chartData([-4,-2]),[.5,1.5,9,3]);
 cps.chart('positive',chartData([4,3]),[.5,1.5,9,3]);
 assert.ok(charts[0].yAxis.min<=-4);assert.ok(charts[1].yAxis.min<=-4);assert.equal(charts[2].yAxis.min,0);
 assert.deepEqual(charts[0].series[0].values,[-4,3]);
 cps.chart('specified',{...chartData([-4,3]),min:-10},[.5,1.5,9,3]);assert.equal(charts[3].yAxis.min,-10);
});

test('axis titles receive their own explicit font and do not materialize an empty x title',async()=>{
 const profile=await loadProfile('cps-workshop'),{cps,charts}=harness(profile);
 cps.start({id:'axes',number:1});
 cps.chart('without-x-title',chartData([1,2]),[.5,1.5,9,3]);
 assert.equal(charts[0].xAxis.title,'');
 assert.equal(charts[0].yAxis.title.text,'change');
 assert.deepEqual(charts[0].yAxis.title.textStyle,{fontSize:16,fill:profile.colour_roles.muted,typeface:profile.font});
 cps.chart('with-x-title',{...chartData([1,2]),x_title:'Elapsed time'},[.5,1.5,9,3]);
 assert.equal(charts[1].xAxis.title.text,'Elapsed time');
 assert.deepEqual(charts[1].xAxis.title.textStyle,charts[1].yAxis.title.textStyle);
});

test('two-line titles reserve descender clearance and move the rule and body together',async()=>{
 for(const profileId of ['cps-workshop','cps-midterm']){
  const profile=await loadProfile(profileId),{cps}=harness(profile);
  await cps.page({id:'two-line',number:1,type:'comparison',title:'Separate permission to discuss\nand to publish',conditions:[{title:'Research conversation',text:'A participant chooses.'},{title:'Publication decision',text:'A separate permission.'}]},{});
  const elements=cps.records[0].expected_elements,title=elements.find(e=>e.id==='title'),body=elements.find(e=>e.id==='condition-title-0'),rule=elements.find(e=>e.id==='title-rule');
  assert.equal(title.font_pt,profile.typography_pt.title);
  assert.ok(title.bounds_in[3]>=2*title.font_pt/72*1.3-.001);
  assert.ok(body.bounds_in[1]>=title.bounds_in[1]+title.bounds_in[3]+.3);
  if(rule){
   assert.ok(rule.bounds_in[1]>=title.bounds_in[1]+title.bounds_in[3]+.099);
   assert.ok(body.bounds_in[1]>=rule.bounds_in[1]+.25);
  }
 }
});

test('diagram arrows and the sidecar preserve all supported directions',async()=>{
 for(const direction of ['forward','backward','both','none']){
  const {cps,edges}=harness(await loadProfile('cps-workshop'));cps.start({id:'diagram',number:1});
  cps.diagram('relationship',{nodes,edges:[{id:'link',from:'a',to:'b',direction,meaning:'Specified relation'}]});
  assert.equal(edges[0].head.type!=='none',['backward','both'].includes(direction));
  assert.equal(edges[0].tail.type!=='none',['forward','both'].includes(direction));
  assert.equal(cps.records[0].expected_elements.find(e=>e.id==='link').edge.direction,direction);
 }
});

test('invalid diagram directions and duplicate IDs stop generation',async()=>{
 const {cps}=harness(await loadProfile('cps-workshop'));cps.start({id:'diagram',number:1});
 assert.throws(()=>cps.diagram('relationship',{nodes,edges:[{id:'link',from:'a',to:'b',direction:'mistyped',meaning:'Relation'}]}),/Unsupported diagram direction/);
 cps.start({id:'duplicate',number:2});
 assert.throws(()=>cps.diagram('relationship',{nodes,edges:[{id:'a',from:'a',to:'b',meaning:'Relation'}]}),/duplicate diagram edge ID/);
});

test('four summary takeaways retain the formal title, author and contact without overlap',async()=>{
 for(const id of ['cps-midterm','cps-workshop']){
  const {cps}=harness(await loadProfile(id));
  await cps.page({id:'closing',number:1,type:'summary',title:'研究から得た要点',takeaways:['第一の要点','第二の要点','第三の要点','第四の要点']},{});
  const elements=cps.records[0].expected_elements;
  assert.equal(elements.find(e=>e.id==='summary-title').text,metadata.title);
  assert.equal(elements.find(e=>e.id==='summary-author').text,metadata.authors);
  assert.equal(elements.find(e=>e.id==='contact').text,metadata.contact);
  assert.equal(elements.filter(e=>e.id.startsWith('takeaway')).length,4);
  const body=elements.filter(e=>/^(summary-|takeaway-|contact)/.test(e.id));
  for(const [i,a] of body.entries())for(const b of body.slice(i+1))assert.equal(overlap(a.bounds_in,b.bounds_in),false,`${id}: ${a.id} overlaps ${b.id}`);
 }
});

test('a two-line heading and absent contact remain valid; excessive summary text fails explicitly',async()=>{
 const {cps}=harness(await loadProfile('cps-midterm'));cps.input.metadata={...metadata,contact:undefined};
 await cps.page({id:'closing',number:1,type:'summary',title:'研究で得た知見と\n今後の方向',takeaways:['第一の要点','第二の要点','第三の要点','第四の要点']},{});
 assert.equal(cps.records[0].expected_elements.some(e=>e.id==='contact'),false);
 await assert.rejects(()=>cps.page({id:'overfull',number:2,type:'summary',title:'Summary',takeaways:Array(4).fill('A long research explanation '.repeat(30))},{}),/does not fit/);
});

test('unknown explicit elements cannot silently disappear',async()=>{
 const {cps}=harness(await loadProfile('cps-workshop'));
 await assert.rejects(()=>cps.page({id:'explicit',number:1,type:'explicit',title:'Evidence',elements:[{id:'lost',kind:'unknown',text:'Required evidence'}]},{}),/Unsupported explicit element kind/);
});

test('build output cannot escape the selected workspace or share its receipt directory',async()=>{
 const work=await fs.mkdtemp(path.join(os.tmpdir(),'cps-generator-test-'));
 const build=fileURLToPath(new URL('../scripts/build_deck.mjs',import.meta.url));
 const input=fileURLToPath(new URL('../assets/plan-reference/input.json',import.meta.url));
 const invoke=output=>spawnSync(process.execPath,[build,'--input',input,'--work-dir',work,'--output',output],{encoding:'utf8'});
 try{
  for(const output of [path.join(work,'deck.pptx'),path.join(work,'..','escape.pptx')]){
   const result=invoke(output);assert.notEqual(result.status,0);assert.match(result.stderr,/subdirectory of --work-dir/);
  }
  const outside=await fs.mkdtemp(path.join(os.tmpdir(),'cps-generator-outside-'));
  try{
   await fs.symlink(outside,path.join(work,'linked'),'dir');
   const result=invoke(path.join(work,'linked','deck.pptx'));assert.notEqual(result.status,0);assert.match(result.stderr,/real directories inside --work-dir/);
   assert.deepEqual(await fs.readdir(outside),[]);
  }finally{await fs.rm(outside,{recursive:true,force:true});}
 }finally{await fs.rm(work,{recursive:true,force:true});}
});

const sections=['研究のねらい','しくみと評価方法','現時点での整理','今後の展望'].map((title,i)=>({id:`section-${i}`,title,description:'実施前の研究計画を示す',start:3+i*2,end:4+i*2}));
test('midterm contents reserve page ranges and do not invent images',async()=>{
 const {cps}=harness(await loadProfile('cps-midterm'));
 await cps.page({id:'contents',number:2,type:'toc',title:'目次',message:'問い、方法、現在地、今後の計画を示す'},{structure:{toc_style:'grid'},ranges:sections});
 const records=cps.records[0].expected_elements;
 assert.equal(records.filter(e=>e.kind==='image').length,0);
 for(let i=0;i<4;i++)assert.equal(overlap(records.find(e=>e.id===`section-${i}`).bounds_in,records.find(e=>e.id===`range-${i}`).bounds_in),false);
 assert.equal(records.filter(e=>e.id.startsWith('section-desc-')).length,4);
});

test('midterm contents accept supplied images and keep their plan captions outside the image',async()=>{
 const {cps}=harness(await loadProfile('cps-midterm'));
 cps.image=async(id,asset,b)=>{cps.record(id,'image','image',b,{asset});cps.objects.set(id,{});};
 const ranges=structuredClone(sections);ranges[0].image={path:'supplied-concept.png'};ranges[0].image_label='計画';
 await cps.page({id:'contents',number:2,type:'toc',title:'目次'},{structure:{toc_style:'grid'},ranges});
 const records=cps.records[0].expected_elements,image=records.find(e=>e.id==='section-image-0'),caption=records.find(e=>e.id==='section-desc-0');
 assert.equal(records.filter(e=>e.kind==='image').length,1);
 assert.equal(image.asset.path,'supplied-concept.png');assert.match(caption.text,/計画/);
 assert.equal(overlap(image.bounds_in,caption.bounds_in),false);
});

test('midterm dividers use the upper band, canonical section title and upper-right logo',async()=>{
 const {cps}=harness(await loadProfile('cps-midterm')),logos=[];
 cps.input.structure={sections};cps.logo=async bounds=>{logos.push(bounds);};
 await cps.page({id:'chapter',number:3,type:'divider',section:'section-0',title:'研究のねらい',guide:'未実施の問いと計画を整理する'},{});
 const records=cps.records[0].expected_elements;
 assert.equal(records.find(e=>e.id==='divider-title').text,'01  研究のねらい');
 assert.deepEqual(records.find(e=>e.id==='divider-band').bounds_in,[.5,1.06,8.5,.9]);
 assert.ok(logos[0][0]>8&&logos[0][1]<1);
 assert.equal(records.some(e=>e.id==='footer-rule'),false);
 assert.equal(records.some(e=>e.id==='title'),false);
 assert.equal(records.find(e=>e.id==='page').text,'3');
});
