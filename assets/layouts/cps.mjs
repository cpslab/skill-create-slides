// Shared layout primitives. Research text/data/assets enter only through the deck input.
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import crypto from 'node:crypto';
export const INCH_TO_EMU=914400, POINT_TO_EMU=12700, PX_PER_INCH=96;
export const inch=v=>v*PX_PER_INCH, pt=v=>v*PX_PER_INCH/72;
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
export async function loadProfile(id,overrides={}) {
 if(!['cps-workshop','cps-midterm'].includes(id))throw new Error(`Unknown profile: ${id}`);
 const p=JSON.parse(await fs.readFile(path.join(root,'assets/profiles',id+'.json'),'utf8'));
 // The canonical palette stays in the style specification, shared with the palette example.
 const style=await fs.readFile(path.join(root,'references/cps-lab-style.md'),'utf8');
 const paletteNames={botanica:'ボタニカ',iris:'アイリス',kimera:'kiMera',orange:'オレンジ',sicilia:'シチリア',bordeaux:'ボルドー'};
 const selected=overrides.palette||p.palette, paletteName=paletteNames[selected]||selected;
 const line=style.split('\n').find(l=>l.startsWith('| '+paletteName+' |'));
 const colours=[...(line||'').matchAll(/#[0-9A-Fa-f]{6}/g)].map(m=>m[0]);
 if(colours.length!==4)throw new Error('Unknown palette or incomplete canonical colour table.');
 p.palette=selected;
 p.colour_roles={...p.colour_roles,base:colours[3],main:colours[0],on_main:colours[1],accent:colours[2],on_accent:colours[3]};
 if(paletteName!=='ボタニカ'){
  const tint=(hex,white)=>'#'+hex.slice(1).match(/../g).map(v=>Math.round(parseInt(v,16)*(1-white)+255*white).toString(16).padStart(2,'0')).join('').toUpperCase();
  p.colour_roles.highlight=tint(colours[0],.88);p.colour_roles.table_header=tint(colours[0],.93);p.colour_roles.series=['#A6B1B6',colours[2]];
 }
 if(overrides.font)p.font=overrides.font;
 if(overrides.FOOTER_LINE) {if(!['on','off'].includes(overrides.FOOTER_LINE))throw new Error('FOOTER_LINE must be on/off');p.frame.FOOTER_LINE=overrides.FOOTER_LINE;}
 return p;
}
export function resolveStructure(input,profile) {
 const slides=structuredClone(input.slides), ids=new Set();
 for(const s of slides){if(!s.id||ids.has(s.id))throw new Error(`Missing/duplicate slide ID ${s.id}`);ids.add(s.id);}
 const sections=input.structure?.sections||[];
 const sectionIds=new Set();
 for(const section of sections){
  if(typeof section.id!=='string'||!section.id.trim()||sectionIds.has(section.id))throw new Error(`Missing/duplicate section ID ${section.id}`);
  sectionIds.add(section.id);
 }
 for(const slide of slides){
  if(Object.hasOwn(slide,'section')&&!sectionIds.has(slide.section))throw new Error(`Unknown section ${slide.section} on slide ${slide.id}`);
 }
 if(!slides.some(s=>s.type==='toc'))throw new Error('A contents slide is required.');
 if(profile.id==='cps-midterm' && sections.length!==4)throw new Error('cps-midterm needs four explicitly authored sections. Use cps-workshop for other structures.');
 const structure={...profile.structure,...input.structure};
 const ranges=sections.map(sec=>{const pages=slides.flatMap((s,i)=>s.section===sec.id?[i+1]:[]);return {...sec,start:Math.min(...pages),end:Math.max(...pages)};});
 if(ranges.some(r=>!Number.isFinite(r.start)))throw new Error('Every section must have a slide.');
 if(structure.section_dividers==='all' && sections.some(sec=>!slides.some(s=>s.type==='divider'&&s.section===sec.id)))throw new Error('Add independent section divider items for section_dividers=all.');
 slides.forEach((s,i)=>s.number=i+1);
 const summary=structure.summary_placement==='end_of_deck'?slides.findLastIndex(s=>s.type==='summary'):slides.findIndex(s=>s.type==='summary');
 if(summary<0)throw new Error('An authored summary is required.');
 if(structure.summary_placement==='end_of_deck'&&summary!==slides.length-1)throw new Error('Place the summary at the end of this deck.');
 if(structure.summary_placement==='end_of_main' && slides.slice(summary+1).some(s=>!s.appendix&&s.id!==structure.final_summary_id))throw new Error('Only appendix slides may follow the main summary.');
 return {slides,ranges,structure};
}
// Conservative word-boundary wrapping; final render remains authoritative.
export function wrapTitle(text,widthIn,sizePt){
 const width=widthIn*72/sizePt*.94;
 const measure=s=>Array.from(s).reduce((n,c)=>n+(/[^\u0000-\u007F]/u.test(c)?1:/[ilI.,:;! ']/.test(c)?.28:/[MW@]/.test(c)?.9:.54),0);
 return String(text).split('\n').flatMap(line=>{
  if(measure(line)<=width)return [line];
  const words=line.includes(' ')?line.split(' '):Array.from(line),sep=line.includes(' ')?' ':'';let rows=[],row='';
  for(const word of words){const next=row?row+sep+word:word;if(measure(next)>width&&row){rows.push(row);row=word;}else row=next;}if(row)rows.push(row);
  // Avoid a single stranded word in automatically wrapped English headings.
  // Explicit source line breaks remain untouched.
  if(sep&&rows.length>1){
   const tail=rows.length-1,previous=rows[tail-1].split(' '),last=rows[tail].split(' ');
   if(last.length===1&&previous.length>3){
    while(previous.length>2&&measure(last.join(' '))<measure(previous.join(' '))*.6){
     if(measure(previous.at(-1)+' '+last.join(' '))>width)break;
     last.unshift(previous.pop());
    }
    rows[tail-1]=previous.join(' ');rows[tail]=last.join(' ');
   }
  }
  return rows;
 }).join('\n');
}
export class CPS {
 constructor(presentation,profile,input,inputDir,sharp){this.pres=presentation;this.p=profile;this.input=input;this.dir=inputDir;this.sharp=sharp;this.records=[];}
 start(spec){this.spec=spec;this.slide=this.pres.slides.add();this.slide.background.fill=this.p.colour_roles.background;this.objects=new Map();this.rec={number:spec.number,id:spec.id,required_text:[],expected_elements:[],allowed_overlaps:[],semantic_claims:spec.semantic_claims||[]};this.records.push(this.rec);return this.slide;}
 record(id,role,kind,b,extra={}){if(this.objects.has(id))throw new Error(`Duplicate element ${id}`);const e={id,role,kind,bounds_in:b,...extra};this.rec.expected_elements.push(e);if(extra.text)this.rec.required_text.push(extra.text);return e;}
 box(id,role,b,fill='none',line='none',lw=0,geometry='rect') {
  const [x,y,w,h]=b;const s=this.slide.shapes.add({name:`role:${role}|id:${id}`,geometry,position:{left:inch(x),top:inch(y),width:inch(w),height:inch(h)},fill,line:{fill:line,width:pt(lw),style:'solid'}});
  this.record(id,role,'shape',b);this.objects.set(id,s);return s;
 }
 text(id,text,b,role='body',opts={}) {
  if(text===undefined||text===null||text==='')throw new Error(`Empty required text: ${id}`);
  const size=opts.size||this.p.typography_pt[role]||this.p.typography_pt.body;
  const min=this.p.minimum_font_pt[role];if(min&&size<min)throw new Error(`${id}: ${size}pt below adopted ${role} minimum ${min}pt`);
  const s=this.box(id,role,b,opts.fill||'none');s.text=String(text);
  s.text.style={typeface:opts.font||this.p.font,fontSize:pt(size),bold:opts.bold??['title','question'].includes(role),color:opts.color||this.p.colour_roles.body,alignment:opts.align||'left',verticalAlignment:opts.valign||'top',wrap:true,autoFit:'none',insets:{left:0,right:0,top:0,bottom:0}};
  const e=this.rec.expected_elements.at(-1);Object.assign(e,{text:String(text),font_pt:size});this.rec.required_text.push(String(text));return s;
 }
 async image(id,asset,b,role='image',fit='contain') {
  const file=path.resolve(this.dir,asset.path), bytes=await fs.readFile(file),meta=await this.sharp(bytes).metadata();
  const [x,y,w,h]=b;
  const im=this.slide.images.add({name:`role:${role}|id:${id}`,blob:bytes,contentType:asset.content_type||({'jpg':'image/jpeg','jpeg':'image/jpeg','png':'image/png','webp':'image/webp'}[meta.format]),alt:asset.alt||id,fit,position:{left:inch(x),top:inch(y),width:inch(w),height:inch(h)}});
  const ratio=meta.width/meta.height, actual=fit==='contain'?(w/h>ratio?[x+(w-h*ratio)/2,y,h*ratio,h]:[x,y+(h-w/ratio)/2,w,w/ratio]):b;
  const assetRef=asset.shared?'skill:'+path.relative(root,file).split(path.sep).join('/'):path.relative(this.dir,file).split(path.sep).join('/');
  this.record(id,role,'image',actual,{frame_bounds_in:b,asset:{path:assetRef,sha256:crypto.createHash('sha256').update(bytes).digest('hex'),width_px:meta.width,height_px:meta.height,effective_ppi:Math.min(meta.width/actual[2],meta.height/actual[3]),fit}});this.objects.set(id,im);return im;
 }
 async logo(b){await this.image('logo',{path:path.join(root,'assets/NewmajimeModeLogoSmall.png'),shared:true,alt:'CPS LAB'},b,'logo');}
 frameGeometry(spec) {
  const p=this.p,width=p.frame.logo_position==='title_right'?7.55:9,size=spec.title_size||p.typography_pt.title;
  const title=wrapTitle(spec.title||'',width,size),lines=title.split('\n').length;
  // Reserve actual line leading and descenders; the title, rule and body share this geometry.
  const height=lines>1?lines*size/72*1.3:.43;
  return {title,width,size,lines,height,ruleY:lines>1?.68+height+.10:1.209,bodyTop:p.frame.body_top_in+(lines>1?height-.43:0)};
 }
 async frame(spec,geometry=this.frameGeometry(spec)) {
  const p=this.p,c=p.colour_roles,f=p.frame,m=f.margin_in;
  const sec=(this.input.structure?.sections||[]).find(s=>s.id===spec.section)?.title||spec.section_label||spec.type;
  this.text('chapter',sec,[m,.25,4.1,.35],'header',{color:c.accent});
  this.text('short-title',this.input.metadata.short_title,[4.8,.25,4.7,.35],'header',{align:'right',color:c.accent});
  const {title,width,lines,height,ruleY}=geometry;
  if(lines>2)throw new Error('Title exceeds two readable lines; revise the input title or choose a title-led page.');
  this.text('title',title,[m,.68,width,height],'title',{color:c.accent,size:spec.title_size});
  if(f.logo_position==='title_right')await this.logo([8.337,.719,1.18,1.18*123/438]);
  else await this.logo([.321,5.253,.895,.895*123/438]);
  if(f.title_rule)this.box('title-rule','rule',[m,ruleY,9,.008],c.main);
  if(f.FOOTER_LINE==='on')this.box('footer-rule','rule',p.id==='cps-midterm'?[0,f.footer_y_in,10,.059]:[m,f.footer_y_in,9,.008],c.main);
  this.text('page',String(spec.number),[9.17,5.32,.33,.19],'page',{align:'right',size:p.typography_pt.page});
  if(spec.sources?.length)this.text('sources',spec.sources.join('\n'),[m,Math.min(f.source_y_in,5.17-spec.sources.length*.17),9,spec.sources.length*.17],'source',{color:c.muted});
 }
 table(id,data,b) {
  const rows=data.rows,cols=rows[0]?.length;if(!rows.length||rows.some(r=>r.length!==cols))throw new Error('Table must be a rectangular, non-empty matrix');
  const [x,y,w,h]=b, widths=data.widths||Array(cols).fill(w/cols),size=data.font_pt||this.p.typography_pt.table;
  if(size<this.p.minimum_font_pt.table)throw new Error('Table font below profile minimum');
  if(Math.abs(widths.reduce((a,b)=>a+b,0)-w)>.02)throw new Error('Table column widths must sum to table width');
  const t=this.slide.tables.add({rows:rows.length,columns:cols,left:inch(x),top:inch(y),width:inch(w),height:inch(h),columnWidths:widths.map(inch),values:rows});
  t.name=`role:table|id:${id}`;
  t.borders.assign({fill:'#CCD3C8',width:.6,style:'solid'});
  const padding={left:.1,right:.1,top:.08,bottom:.08,...data.padding_in};
  if(Object.values(padding).some(v=>!Number.isFinite(v)||v<0))throw new Error('Table padding must be finite and non-negative');
  t.cells.block({row:0,column:0,rowCount:rows.length,columnCount:cols}).assign({textStyle:{typeface:this.p.font,fontSize:pt(size),color:this.p.colour_roles.body},margins:Object.fromEntries(Object.entries(padding).map(([k,v])=>[k,inch(v)])),anchor:'center'});
  for(let r=0;r<rows.length;r++)for(let col=0;col<cols;col++){
   const cell=t.getCell(r,col);cell.fill=r===0?this.p.colour_roles.table_header:r===data.highlight_row?this.p.colour_roles.highlight:'#FFFFFF';
   cell.text.style={typeface:this.p.font,fontSize:pt(size),bold:r===0,color:this.p.colour_roles.body,alignment:'left',verticalAlignment:'middle',autoFit:'none'};
  }
  if(data.heights){if(data.heights.length!==rows.length||data.heights.some(v=>!Number.isFinite(v)||v<=0)||Math.abs(data.heights.reduce((a,b)=>a+b,0)-h)>.02)throw new Error('Positive row heights must match row count and sum to table height');data.heights.forEach((height,i)=>t.rows[i].height=inch(height));}
  this.record(id,'table','table',b,{table:{rows},font_pt:size});this.objects.set(id,t);return t;
 }
 chart(id,data,b) {
  if(!data.unit||!data.subject||!data.aggregation||!data.status)throw new Error('Chart requires unit, subject, aggregation and status');
  const [x,y,w,h]=b;
  const values=data.series.flatMap(s=>s.values||[]).filter(Number.isFinite);
  const minimum=data.min??values.reduce((min,value)=>Math.min(min,value),0);
  // Axis tick textStyle does not style the title; use the documented title object.
  const axisTitle=text=>text?{text,textStyle:{fontSize:pt(12),fill:this.p.colour_roles.muted}}:'';
  const chart=this.slide.charts.add(data.type||'bar',{name:`role:chart|id:${id}`,position:{left:inch(x),top:inch(y),width:inch(w),height:inch(h)},categories:data.categories,series:data.series.map((s,i)=>{const fill=s.fill||this.p.colour_roles.series[i%this.p.colour_roles.series.length];return {...s,fill,...(s.marker?{marker:{...s.marker,fill:s.marker.fill||fill}}:{})};}),hasLegend:true,legend:{position:'bottom',overlay:false,textStyle:{typeface:this.p.font,fontSize:pt(12),fill:this.p.colour_roles.body}},barOptions:{direction:'column',grouping:'clustered'},xAxis:{title:axisTitle(data.x_title),textStyle:{typeface:this.p.font,fontSize:pt(12)},majorGridlines:null},yAxis:{title:axisTitle(data.unit),min:minimum,max:data.max,numberFormatCode:data.number_format||'0',textStyle:{typeface:this.p.font,fontSize:pt(12)},majorGridlines:{fill:'#DDDDDD',width:.5}},chartFill:'#FFFFFF',plotAreaFill:'#FFFFFF',chartLine:{fill:'none',width:0},plotAreaLine:{fill:'none',width:0}});
  for(const axis of [chart.xAxis,chart.yAxis])if(axis?.title?.text?.trim())axis.title.textStyle.typeface=this.p.font;
  this.record(id,'chart','chart',b,{chart:{categories:data.categories,series:data.series.map(({name,values})=>({name,values})),unit:data.unit,subject:data.subject,aggregation:data.aggregation,status:data.status}});this.objects.set(id,chart);return chart;
 }
 diagram(id,data) {
  const nodes=new Map();
  for(const n of data.nodes){const obj=this.text(n.id,n.text,n.bounds_in,'label',{align:'center',valign:'middle',fill:this.p.colour_roles.highlight});nodes.set(n.id,obj);this.rec.expected_elements.at(-1).role='diagram-node';obj.name=`role:diagram-node|id:${n.id}`;}
  for(const e of data.edges){if(!nodes.has(e.from)||!nodes.has(e.to)||!e.meaning)throw new Error('Every edge requires valid endpoints and meaning');
   if(!e.id||this.objects.has(e.id))throw new Error(`Missing/duplicate diagram edge ID ${e.id}`);
   const direction=e.direction??'forward';
   if(!['forward','backward','both','none'].includes(direction))throw new Error(`Unsupported diagram direction: ${direction}`);
   const arrow={type:'triangle',width:'sm',length:'sm'},plain={type:'none'};
   const obj=this.slide.shapes.connect(nodes.get(e.from),nodes.get(e.to),{kind:e.kind||'straight',fromSide:e.from_side||'right',toSide:e.to_side||'left',line:{fill:this.p.colour_roles.accent,width:pt(1.2)},head:['backward','both'].includes(direction)?arrow:plain,tail:['forward','both'].includes(direction)?arrow:plain});obj.name=`role:diagram-edge|id:${e.id}`;
   this.rec.expected_elements.push({id:e.id,role:'diagram-edge',kind:'connector',edge:{from:e.from,to:e.to,direction,meaning:e.meaning}});this.objects.set(e.id,obj);
   this.rec.allowed_overlaps.push([e.id,e.from],[e.id,e.to]);
  }
 }
 async page(s,resolved){
  this.start(s);const p=this.p,c=p.colour_roles,frame=this.frameGeometry(s);let top=frame.bodyTop, bottom=Math.min(p.frame.body_bottom_in,5.05-(s.sources?.length||0)*.17);
  if(s.type==='cover'){
   if(s.video&&s.cover_type!=='type-b')throw new Error('Video input requires a type-b cover.');
   if(s.cover_type==='type-b'&&!s.poster?.path)throw new Error('A type-b cover requires a supplied poster image.');
   if(s.cover_type==='type-b'&&s.poster){await this.image('cover-media',s.poster,[0,0,10,5.625],'background','cover');}
   else this.box('cover-band','background',[.5,1.45,9,1.45],c.main);
   if(s.video){
    if(typeof s.video.path!=='string'||!s.video.path)throw new Error('Video input requires an MP4 path.');
    const settings=Object.fromEntries(['autoplay','loop','muted'].map(key=>[key,s.video[key]??true]));
    if(Object.values(settings).some(value=>typeof value!=='boolean'))throw new Error('Video autoplay, loop and muted must be booleans.');
    const source=path.resolve(this.dir,s.video.path),bytes=await fs.readFile(source);
    this.rec.media=[{poster_id:'cover-media',path:path.relative(this.dir,source).split(path.sep).join('/'),sha256:crypto.createHash('sha256').update(bytes).digest('hex'),...settings}];
   }
   const colour=s.cover_type==='type-b'?'#FFFFFF':c.body;
   this.text('cover-title',this.input.metadata.title,[.75,1.6,8.5,1.1],'title',{size:28,align:'center',color:s.cover_type==='type-b'?colour:c.on_main});
   this.text('cover-author',this.input.metadata.authors,[.7,3.35,8.6,.65],'body',{align:'center',color:colour});
   if(this.input.metadata.venue)this.text('venue',this.input.metadata.venue,[.7,.6,8.6,.65],'body',{align:'center',color:colour});
   if(this.input.metadata.fictional_label)this.text('fictional',this.input.metadata.fictional_label,[.7,4.5,8.6,.4],'label',{align:'center',color:colour});
   if(s.cover_type!=='type-b'){await this.logo([.321,5.253,.895,.895*123/438]);if(p.frame.FOOTER_LINE==='on')this.box('cover-rule','rule',[.5,5.188,9,.008],c.main);}
   this.text('page',String(s.number),[9.17,5.32,.33,.19],'page',{align:'right',color:colour});
   for(const e of this.rec.expected_elements.filter(e=>e.kind==='shape'&&e.role!=='background'))this.rec.allowed_overlaps.push(['cover-media',e.id],['cover-band',e.id]);
  } else if(p.id==='cps-midterm'&&s.type==='divider'){
   const sections=this.input.structure?.sections||[],index=sections.findIndex(section=>section.id===s.section);
   if(s.section&&index<0)throw new Error(`Unknown divider section: ${s.section}`);
   const section=sections[index],label=section?`${String(index+1).padStart(2,'0')}  ${section.title}`:s.label||s.title;
   const title=wrapTitle(label,8.05,p.typography_pt.question);
   if(title.includes('\n'))throw new Error('Midterm divider chapter title must fit one line; use a shorter chapter name.');
   this.text('chapter',label,[.5,.12,2.8,.33],'header',{color:c.accent});
   this.text('short-title',this.input.metadata.short_title,[3.5,.12,6,.33],'header',{align:'right',color:c.accent});
   await this.logo([8.418,.55,1.211,1.211*123/438]);
   this.box('divider-band','background',[.5,1.06,8.5,.9],c.main);
   this.text('divider-title',title,[.73,1.12,8.05,.72],'question',{color:c.on_main,valign:'middle'});
   this.rec.allowed_overlaps.push(['divider-band','divider-title']);
   const guide=s.guide||s.message||section?.description;
   if(guide){
    const text=wrapTitle(guide,8.5,p.typography_pt.body);
    if(text.split('\n').length>3)throw new Error('Midterm divider guide exceeds three lines.');
    this.text('divider-guide',text,[.75,2.31,8.5,1.1],'body');
   }
   this.text('page',String(s.number),[9.17,5.28,.33,.25],'page',{align:'right'});
   if(s.sources?.length)this.text('sources',s.sources.join('\n'),[.5,Math.min(p.frame.source_y_in,5.17-s.sources.length*.17),9,s.sources.length*.17],'source',{color:c.muted});
  } else {
   await this.frame(s,frame);
   if(s.message&&!(p.id==='cps-midterm'&&s.type==='toc')){this.text('message',s.message,[.5,top,9,.6],'body');top+=.7;}
   const h=bottom-top;
   switch(s.type){
    case 'toc': {
     const grid=resolved.structure.toc_style==='grid';
     if(p.id==='cps-midterm'&&s.message){
      if(wrapTitle(s.message,9,p.typography_pt.body).includes('\n'))throw new Error('Midterm contents guide must fit one line.');
      this.text('message',s.message,[.5,top-.55,9,.45],'body');
     }
     if(grid){
      if(resolved.ranges.length>4)throw new Error('The two-by-two contents grid supports at most four sections.');
      const rowGap=.18,cellHeight=(h-rowGap)/2,cellWidth=4.35;
      for(const [i,sec] of resolved.ranges.entries()){
       const x=.5+(i%2)*4.65,y=top+Math.floor(i/2)*(cellHeight+rowGap);
       const label=wrapTitle(`${String(i+1).padStart(2,'0')}  ${sec.title}`,3.5,p.typography_pt.body);
       const labelHeight=label.split('\n').length*p.typography_pt.body/72*1.2+.02;
       if(labelHeight>cellHeight-.2)throw new Error('Contents chapter title is too long for its grid cell.');
       this.text(`section-${i}`,label,[x,y,3.5,labelHeight],'body',{bold:true,color:c.accent});
       this.text(`range-${i}`,sec.start===sec.end?`${sec.start}`:`${sec.start}–${sec.end}`,[x+3.65,y,.7,.32],'label',{align:'right'});
       const contentTop=y+labelHeight+.06,contentHeight=cellHeight-labelHeight-.06;
       if(sec.image){
        const caption=[sec.image_label,sec.description].filter(Boolean).join('\n');
        const captionText=caption?wrapTitle(caption,2.5,p.typography_pt.caption):'';
        const captionHeight=captionText?captionText.split('\n').length*p.typography_pt.caption/72*1.2+.02:0;
        if(contentHeight<.3||captionHeight>contentHeight)throw new Error('Contents image and caption do not fit; shorten its label/description or omit the image.');
        await this.image(`section-image-${i}`,sec.image,[x,contentTop,captionText?1.65:cellWidth,contentHeight]);
        if(captionText)this.text(`section-desc-${i}`,captionText,[x+1.85,contentTop+(contentHeight-captionHeight)/2,2.5,captionHeight],'caption');
       }else if(sec.description){
        const description=wrapTitle(sec.description,cellWidth,p.typography_pt.label);
        const descriptionHeight=description.split('\n').length*p.typography_pt.label/72*1.2+.02;
        if(descriptionHeight>contentHeight)throw new Error('Contents description is too long for its grid cell.');
        this.text(`section-desc-${i}`,description,[x,contentTop,cellWidth,descriptionHeight],'label');
       }
      }
      this.box('toc-rule-vertical','rule',[4.995,top,.01,h],'#D7DCD5');
      this.box('toc-rule-horizontal','rule',[.5,top+cellHeight+rowGap/2,9,.01],'#D7DCD5');
      break;
     }
     for(const [i,sec] of resolved.ranges.entries()){
      const x=.5,y=top+i*Math.min(1.05,h/resolved.ranges.length),w=7.7;
      this.text(`section-${i}`,`${String(i+1).padStart(2,'0')}  ${sec.title}`,[x,y,w,.4],'body',{bold:true,color:c.accent});
      if(sec.description)this.text(`section-desc-${i}`,sec.description,[x+.45,y+.43,w-.45,.45],'label');
      this.text(`range-${i}`,sec.start===sec.end?`${sec.start}`:`${sec.start}–${sec.end}`,[8.5,y,1,.35],'label',{align:'right'});
     }break;}
    case 'question':
     if(s.premise)this.text('premise',s.premise,[.7,top+.1,8.6,.65],'body');
     this.text('question',s.question,[.7,top+.95,8.5,Math.max(1.5,h-1)],'question',{color:c.accent});break;
    case 'concept': {
     const texts=s.blocks||[];const w=s.image?4.35:9;
     for(const [i,t] of texts.entries())this.text(`block-${i}`,t,[.5,top+i*h/texts.length,w,h/texts.length-.15],'body');
     if(s.image)await this.image('concept-image',s.image,[5.2,top,4.3,h]);break;}
    case 'photos': {
     const n=s.items.length,g=.3,w=(9-g*(n-1))/n;
     for(const [i,item] of s.items.entries()){
      const x=.5+i*(w+g);await this.image(`photo-${i}`,item.asset,[x,top,w,h*.58]);
      this.text(`photo-title-${i}`,item.title,[x,top+h*.62,w,.36],'label',{bold:true,color:c.accent});
      this.text(`photo-description-${i}`,item.description,[x,top+h*.78,w,h*.22],'label');
     }break;}
    case 'table':this.table('main-table',s.table,[.5,top,s.image?5.6:9,h]);if(s.image)await this.image('table-image',s.image,[6.4,top,3.1,h]);break;
    case 'ui':
     await this.image('ui',s.image,[.6,top,3.4,h]);
     for(const [i,t] of s.steps.entries())this.text(`step-${i}`,t,[4.5,top+i*h/s.steps.length,5,h/s.steps.length-.2],'body');break;
    case 'chart':
     this.text('chart-scope',s.chart.scope_label,[.5,top,9,.38],'label');
     // Native vertical axis titles can extend above the plot; keep a clear band below the scope.
     this.chart('main-chart',s.chart,[.5,top+.7,9,h-1.4]);
     this.text('interpretation',s.interpretation,[.5,bottom-.65,9,.6],'body');break;
    case 'comparison':
     for(const [i,condition] of s.conditions.entries()){
      const x=.5+i*4.65;this.text(`condition-title-${i}`,condition.title,[x,top,4.35,.5],'body',{bold:true,color:c.accent});
      this.text(`condition-body-${i}`,condition.text,[x,top+.65,4.35,h-.65],'body');
     }break;
    case 'diagram':this.diagram('diagram',s.diagram);if(s.caption)this.text('caption',s.caption,[.5,bottom-.65,9,.6],'body');break;
    case 'summary': {
     if(!Array.isArray(s.takeaways)||!s.takeaways.length)throw new Error('Summary requires authored takeaways');
     const measure=(value,role)=>{
      if(typeof value!=='string'||!value.trim())throw new Error(`Summary requires non-empty ${role} text`);
      const text=wrapTitle(value,9,p.typography_pt[role]);
      return {text,height:text.split('\n').length*p.typography_pt[role]/72*1.2+.02};
     };
     const formal=measure(this.input.metadata.title,'label'),author=measure(this.input.metadata.authors,'label');
     const contact=this.input.metadata.contact?measure(this.input.metadata.contact,'label'):null;
     const sameTitle=String(s.title).replace(/\s+/g,' ').trim()===this.input.metadata.title.replace(/\s+/g,' ').trim();
     const points=s.takeaways.map(t=>measure(t,'body'));
     let cursor=top;
     const prefix=(sameTitle?0:formal.height+.04)+author.height+.08;
     const contentBottom=bottom-(contact?contact.height+.08:0);
     const available=contentBottom-cursor-prefix,total=points.reduce((sum,t)=>sum+t.height,0);
     if(total+.05*(points.length-1)>available+.001)throw new Error('Summary text does not fit at the profile font sizes; shorten or reflow the title/takeaways, or use an explicit composition.');
     if(!sameTitle){this.text('summary-title',formal.text,[.5,cursor,9,formal.height],'label',{bold:true,color:c.accent});cursor+=formal.height+.04;}
     this.text('summary-author',author.text,[.5,cursor,9,author.height],'label');cursor+=author.height+.08;
     const gap=points.length>1?Math.min(.18,(available-total)/(points.length-1)):0;
     for(const [i,t] of points.entries()){this.text(`takeaway-${i}`,t.text,[.5,cursor,9,t.height],'body');cursor+=t.height+gap;}
     if(contact)this.text('contact',contact.text,[.5,bottom-contact.height,9,contact.height],'label',{color:c.accent});break;}
    case 'divider':this.text('divider-title',s.label||s.title,[.65,2.1,8.7,1.1],'question',{color:c.accent});break;
    case 'explicit':for(const e of s.elements){if(e.kind==='text')this.text(e.id,e.text,e.bounds_in,e.role,e.options);else if(e.kind==='image')await this.image(e.id,e.asset,e.bounds_in,e.role);else if(e.kind==='table')this.table(e.id,e.data,e.bounds_in);else if(e.kind==='chart')this.chart(e.id,e.data,e.bounds_in);else if(e.kind==='diagram')this.diagram(e.id,e.data);else throw new Error(`Unsupported explicit element kind: ${e.kind}`);}break;
    default:throw new Error(`Unknown layout type ${s.type}`);
   }
  }
  this.slide.speakerNotes.textFrame.setText([s.notes||'',...(s.sources||[])].filter(Boolean).join('\n'));
 }
}
