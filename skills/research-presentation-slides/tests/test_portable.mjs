import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {managedMemo,memoHash} from '../assets/layouts/memo.mjs';

const root=fileURLToPath(new URL('../',import.meta.url));
const python=process.env.RUNTIME_PYTHON||(process.platform==='win32'?'python':'python3');
const cleanEnv={...process.env};
for(const key of ['RUNTIME_NODE_MODULES','CODEX_PRIMARY_RUNTIME_NODE_MODULES','PRESENTATIONS_SKILL_DIR'])delete cleanEnv[key];
function run(command,args){return spawnSync(command,args,{cwd:root,env:cleanEnv,encoding:'utf8',timeout:60000});}

test('native table and text alignment are valid before package finalisation',async()=>{
 const work=await fs.mkdtemp(path.join(os.tmpdir(),'cps-portable-native-alignment-'));
 try{
  const [{default:PptxGenJS},{PortableCPS},{loadProfile}]=await Promise.all([import('pptxgenjs'),import('../assets/layouts/portable.mjs'),import('../assets/layouts/cps.mjs')]);
  const presentation=new PptxGenJS(),profile=await loadProfile('cps-workshop');
  const cps=new PortableCPS(presentation,profile,{metadata:{language:'en-GB'}},work);
  cps.start({number:1,id:'synthetic-table'});
  cps.table('table',{rows:[['Method','Value'],['Fictional example','3']]},[.5,1,8,1]);
  cps.text('middle','Middle alignment',[.5,2.5,4,.5],'body',{valign:'middle'});
  cps.text('legacy-mid','Accepted legacy option',[.5,3.5,4,.5],'body',{valign:'mid'});
  const output=path.join(work,'raw.pptx');await presentation.writeFile({fileName:output});
  const check=run(python,['-c',`import sys,zipfile,xml.etree.ElementTree as E
with zipfile.ZipFile(sys.argv[1]) as z:
 root=E.fromstring(z.read('ppt/slides/slide1.xml'))
 ns={'a':'http://schemas.openxmlformats.org/drawingml/2006/main','p':'http://schemas.openxmlformats.org/presentationml/2006/main'}
 cells=root.findall('.//a:tcPr',ns)
 assert len(cells)==4 and all(cell.get('anchor')=='ctr' for cell in cells),[cell.attrib for cell in cells]
 bodies=root.findall('.//p:sp/p:txBody/a:bodyPr',ns)
 assert len(bodies)==2 and all(body.get('anchor')=='ctr' for body in bodies),[body.attrib for body in bodies]
`,output]);
  assert.equal(check.status,0,check.stderr);
 }finally{await fs.rm(work,{recursive:true,force:true});}
});

test('public backend exports native elements, workbooks, notes and connector endpoints without Codex',async()=>{
 const work=await fs.mkdtemp(path.join(os.tmpdir(),'cps-portable-'));
 try{
  const input=path.join(root,'assets/workshop-reference/input.json'),output=path.join(work,'output/deck.pptx');
  const build=run(process.execPath,['scripts/build_deck.mjs','--backend','portable','--input',input,'--output',output,'--work-dir',work,'--python',python]);
  assert.equal(build.status,0,build.stderr);
  const check=run(python,['scripts/check_layout.py',output,'--profile','assets/profiles/cps-workshop.json','--deck-spec',input]);
  const report=JSON.parse(check.stdout);
  assert.deepEqual(report.errors,[]);
  assert.deepEqual(report.unverified,[]);
  assert.ok(report.checks.some(s=>s.native_tables>0));
  assert.ok(report.checks.some(s=>s.native_charts>0));
  assert.ok(report.checks.some(s=>s.native_connectors>0));
  assert.ok(report.review_items.length>0,'semantic and visual review must remain required');
  const structure=JSON.parse(run(python,['scripts/check_pptx.py',output]).stdout);
  assert.deepEqual(structure.errors,[]);
  const compatibility=run(python,['-c',`
import sys,zipfile,xml.etree.ElementTree as E
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from repair_pptx_compat import normalise_parts,PRESENTATION_CHILDREN
with zipfile.ZipFile(sys.argv[1]) as z:
 parts={n:z.read(n) for n in z.namelist()}
 ns={'a':'http://schemas.openxmlformats.org/drawingml/2006/main'}
 cells=[n for name,data in parts.items() if name.endswith('.xml') for n in E.fromstring(data).findall('.//a:tcPr',ns)]
 assert cells and all(n.get('anchor')=='ctr' for n in cells),[n.attrib for n in cells]
 root=E.fromstring(parts['ppt/presentation.xml'])
 order=[PRESENTATION_CHILDREN.index(n.tag.split('}')[-1]) for n in root]
 assert order==sorted(order),order
 assert any(n.tag.endswith('}notesMasterIdLst') for n in root)
 repaired,changes=normalise_parts(parts)
 assert changes==[],changes
 assert repaired==parts
`,output]);
  assert.equal(compatibility.status,0,compatibility.stderr);
  const sidecar=JSON.parse(await fs.readFile(output.replace('.pptx','.layout.json'),'utf8'));
  assert.equal(sidecar.backend,'portable');
  const memo=await fs.readFile(output.replace('.pptx','-発表メモ.md'),'utf8');
  assert.match(memo,/# 発表メモ/);
  assert.equal((memo.match(/^## 表示ページ \d+$/gm)||[]).length,sidecar.slides.length);
  assert.equal(sidecar.memo.file,path.basename(output.replace('.pptx','-発表メモ.md')));
  assert.equal(sidecar.memo.format,'markdown');assert.equal(sidecar.memo.sha256,memoHash(memo));
  assert.equal(sidecar.memo.generated_sha256,memo.match(/GENERATED CONTENT SHA256: ([a-f0-9]{64})/)[1]);
  await assert.rejects(fs.access(output.replace('.pptx','-発表メモ.txt')));
  const overwrite=run(process.execPath,['scripts/build_deck.mjs','--backend','portable','--input',input,'--output',output,'--work-dir',work,'--python',python]);
  assert.notEqual(overwrite.status,0);assert.match(overwrite.stderr,/already exists/);
 }finally{await fs.rm(work,{recursive:true,force:true});}
});

test('unsupported chart styling stops instead of silently changing data presentation',async()=>{
 const work=await fs.mkdtemp(path.join(os.tmpdir(),'cps-portable-unsupported-'));
 try{
  const input=JSON.parse(await fs.readFile(path.join(root,'assets/plan-reference/input.json'),'utf8'));
  input.slides.splice(-1,0,{id:'unsupported',type:'chart',title:'Synthetic data',interpretation:'Illustrative only',
   chart:{type:'scatter',unit:'units',subject:'synthetic items',aggregation:'example',status:'illustrative',
    scope_label:'Synthetic values',categories:['A','B'],series:[{name:'Example',values:[-2,3]}]}});
  const filename=path.join(work,'input.json');await fs.writeFile(filename,JSON.stringify(input));
  const output=path.join(work,'output/deck.pptx');
  const result=run(process.execPath,['scripts/build_deck.mjs','--backend','portable','--input',filename,'--output',output,'--work-dir',work,'--python',python]);
  assert.notEqual(result.status,0);assert.match(result.stderr,/not implemented/);
  await assert.rejects(fs.access(output));
 }finally{await fs.rm(work,{recursive:true,force:true});}
});

test('a type-b cover crops a PNG with native settings and retains its source bytes',async()=>{
 const work=await fs.mkdtemp(path.join(os.tmpdir(),'cps-portable-cover-'));
 try{
  const input=JSON.parse(await fs.readFile(path.join(root,'assets/plan-reference/input.json'),'utf8'));
  const poster=path.join(root,'assets/NewmajimeModeLogoSmall.png');
  input.slides[0].cover_type='type-b';input.slides[0].poster={path:poster,alt:'Test fixture'};
  const filename=path.join(work,'input.json');await fs.writeFile(filename,JSON.stringify(input));
  const output=path.join(work,'output/deck.pptx');
  const result=run(process.execPath,['scripts/build_deck.mjs','--input',filename,'--output',output,'--work-dir',work,'--python',python]);
  assert.equal(result.status,0,result.stderr);
  const inspection=run(python,['-c',`
import sys,zipfile,xml.etree.ElementTree as E
with zipfile.ZipFile(sys.argv[1]) as z:
 r=E.fromstring(z.read('ppt/slides/slide1.xml'))
 ns={'p':'http://schemas.openxmlformats.org/presentationml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main'}
 pic=next(p for p in r.findall('.//p:pic',ns) if 'cover-media' in p.find('p:nvPicPr/p:cNvPr',ns).get('name',''))
 crop=pic.find('p:blipFill/a:srcRect',ns)
 assert 24000<int(crop.get('l'))<26000 and crop.get('l')==crop.get('r'),E.tostring(crop)
 assert crop.get('t')=='0' and crop.get('b')=='0'
 ext=pic.find('p:spPr/a:xfrm/a:ext',ns)
 assert ext.get('cx')=='9144000' and ext.get('cy')=='5143500'
 assert open(sys.argv[2],'rb').read() in [z.read(n) for n in z.namelist() if n.startswith('ppt/media/')]
`,output,poster]);
  assert.equal(inspection.status,0,inspection.stderr);
 }finally{await fs.rm(work,{recursive:true,force:true});}
});

test('unsupported SVG never produces an invalid PNG fallback',async()=>{
 const work=await fs.mkdtemp(path.join(os.tmpdir(),'cps-portable-svg-'));
 try{
  const input=JSON.parse(await fs.readFile(path.join(root,'assets/plan-reference/input.json'),'utf8'));
  await fs.writeFile(path.join(work,'poster.svg'),'<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100"><rect width="200" height="100" fill="green"/></svg>');
  input.slides[0].cover_type='type-b';input.slides[0].poster={path:'poster.svg'};
  const filename=path.join(work,'input.json');await fs.writeFile(filename,JSON.stringify(input));
  const output=path.join(work,'output/deck.pptx');
  const result=run(process.execPath,['scripts/build_deck.mjs','--input',filename,'--output',output,'--work-dir',work,'--python',python]);
  assert.notEqual(result.status,0);assert.match(result.stderr,/format svg is not supported/);
  await assert.rejects(fs.access(output));
 }finally{await fs.rm(work,{recursive:true,force:true});}
});

test('sidecar and either memo format reject links; a legacy text memo is preserved in place',async()=>{
 const work=await fs.mkdtemp(path.join(os.tmpdir(),'cps-portable-files-'));
 try{
  const input=path.join(root,'assets/plan-reference/input.json'),output=path.join(work,'output/deck.pptx');
  await fs.mkdir(path.dirname(output));
  const sentinel=path.join(work,'outside.txt');await fs.writeFile(sentinel,'Preserve this content');
  const build=()=>run(process.execPath,['scripts/build_deck.mjs','--input',input,'--output',output,'--work-dir',work,'--python',python]);
  for(const destination of [output.replace('.pptx','.layout.json'),output.replace('.pptx','-発表メモ.md'),output.replace('.pptx','-発表メモ.txt')]){
   await fs.symlink(sentinel,destination);
   const result=build();assert.notEqual(result.status,0);
   assert.equal(await fs.readFile(sentinel,'utf8'),'Preserve this content');await assert.rejects(fs.access(output));
   await fs.unlink(destination);
  }
  const memo=output.replace('.pptx','-発表メモ.txt');
  await fs.writeFile(memo,'My rehearsal note: pause here.');
  const result=build();assert.equal(result.status,0,result.stderr);
  assert.match(await fs.readFile(memo,'utf8'),/My rehearsal note: pause here\./);
  assert.match(await fs.readFile(memo,'utf8'),/^=== GENERATED CONTENT START ===/);
  await assert.rejects(fs.access(output.replace('.pptx','-発表メモ.md')));
 }finally{await fs.rm(work,{recursive:true,force:true});}
});

test('Markdown memo regeneration replaces generated text and retains user additions around it',async()=>{
 const work=await fs.mkdtemp(path.join(os.tmpdir(),'cps-portable-markdown-memo-'));
 try{
  const data=JSON.parse(await fs.readFile(path.join(root,'assets/plan-reference/input.json'),'utf8'));
  data.slides[0].notes='Compare <sample> & [controls] *literally*\n# Keep this next line';
  const input=path.join(work,'input.json'),output=path.join(work,'output/deck.pptx');
  await fs.writeFile(input,JSON.stringify(data));
  await fs.mkdir(path.dirname(output));
  const memo=output.replace('.pptx','-発表メモ.md');
  await fs.writeFile(memo,'Personal introduction\n\n'+managedMemo('# Previous generated version\n').text+'\n\n## My additions\nPause before the final page.\n');
  const result=run(process.execPath,['scripts/build_deck.mjs','--input',input,'--output',output,'--work-dir',work,'--python',python]);
  assert.equal(result.status,0,result.stderr);
  const updated=await fs.readFile(memo,'utf8');
  assert.ok(updated.startsWith('Personal introduction\n\n'));
  assert.ok(updated.endsWith('\n\n## My additions\nPause before the final page.\n'));
  assert.doesNotMatch(updated,/Previous generated version/);
  assert.match(updated,/^# 発表メモ$/m);
  assert.equal((updated.match(/<!-- GENERATED CONTENT START -->/g)||[]).length,1);
  assert.ok(updated.includes('Compare &lt;sample\\> &amp; \\[controls\\] \\*literally\\*  \n\\# Keep this next line'));
 }finally{await fs.rm(work,{recursive:true,force:true});}
});

test('structured memo fields reach both outputs while preparation stays in the private build',async()=>{
 const work=await fs.mkdtemp(path.join(os.tmpdir(),'cps-portable-structured-memo-'));
 try{
  const data=JSON.parse(await fs.readFile(path.join(root,'assets/plan-reference/input.json'),'utf8'));
  data.slides[0].notes={text:'Spoken supplementary explanation.',evidence:['Detailed citation and the checked scope.'],preparation:['AUTHOR TASK: verify the caption.']};
  const input=path.join(work,'input.json'),output=path.join(work,'output/deck.pptx');await fs.writeFile(input,JSON.stringify(data));
  const result=run(process.execPath,['scripts/build_deck.mjs','--input',input,'--output',output,'--work-dir',work,'--python',python]);
  assert.equal(result.status,0,result.stderr);
  const memo=await fs.readFile(output.replace('.pptx','-発表メモ.md'),'utf8');
  assert.match(memo,/### 根拠・確認情報/);assert.match(memo,/Detailed citation/);assert.doesNotMatch(memo,/AUTHOR TASK/);
  const inspection=run(python,['-c',`import sys,zipfile,xml.etree.ElementTree as E
with zipfile.ZipFile(sys.argv[1]) as z:
 text='\\n'.join(''.join(E.fromstring(z.read(n)).itertext()) for n in z.namelist() if n.startswith('ppt/notesSlides/notesSlide') and n.endswith('.xml'))
 assert 'Spoken supplementary explanation.' in text
 assert 'Detailed citation and the checked scope.' in text
 assert 'AUTHOR TASK' not in text
`,output]);
  assert.equal(inspection.status,0,inspection.stderr);
  const stages=await fs.readdir(path.join(work,'.build'));
  assert.equal(stages.length,1);
  const preparationPath=path.join(work,'.build',stages[0],'production-checks.md');
  assert.equal(JSON.parse(result.stdout.trim().split('\n').at(-1)).preparation,preparationPath);
  assert.match(await fs.readFile(preparationPath,'utf8'),/AUTHOR TASK/);
 }finally{await fs.rm(work,{recursive:true,force:true});}
});

test('unverified or edited generated memo blocks stop publication and retain a candidate',async()=>{
 const work=await fs.mkdtemp(path.join(os.tmpdir(),'cps-portable-memo-conflict-'));
 try{
  const input=path.join(root,'assets/plan-reference/input.json');
  for(const [index,existing] of [
   '<!-- GENERATED CONTENT START -->\nOld unverified text\n<!-- GENERATED CONTENT END -->',
   managedMemo('Original text\n').text.replace('Original text','Hand-edited text'),
  ].entries()){
   const output=path.join(work,`output/deck-${index}.pptx`),memo=output.replace('.pptx','-発表メモ.md');
   await fs.mkdir(path.dirname(output),{recursive:true});await fs.writeFile(memo,existing);
   const result=run(process.execPath,['scripts/build_deck.mjs','--input',input,'--output',output,'--work-dir',work,'--python',python]);
   assert.notEqual(result.status,0);assert.match(result.stderr,/retain the current file/);assert.match(result.stderr,/Candidate memo:/);
   assert.equal(await fs.readFile(memo,'utf8'),existing);await assert.rejects(fs.access(output));await assert.rejects(fs.access(output.replace('.pptx','.layout.json')));
  }
  const stages=await fs.readdir(path.join(work,'.build'));
  assert.equal(stages.length,2);
  for(const stage of stages)assert.match(await fs.readFile(path.join(work,'.build',stage,'memo-candidate.md'),'utf8'),/GENERATED CONTENT SHA256/);
 }finally{await fs.rm(work,{recursive:true,force:true});}
});

test('invalid note input never publishes a deck or replaces a personal memo',async()=>{
 const work=await fs.mkdtemp(path.join(os.tmpdir(),'cps-portable-invalid-memo-'));
 try{
  const data=JSON.parse(await fs.readFile(path.join(root,'assets/plan-reference/input.json'),'utf8'));
  data.slides[0].notes={text:'Spoken',evidence:[false]};
  const input=path.join(work,'input.json'),output=path.join(work,'output/deck.pptx'),memo=output.replace('.pptx','-発表メモ.md');
  await fs.writeFile(input,JSON.stringify(data));await fs.mkdir(path.dirname(output));await fs.writeFile(memo,'My personal memo');
  const result=run(process.execPath,['scripts/build_deck.mjs','--input',input,'--output',output,'--work-dir',work,'--python',python]);
  assert.notEqual(result.status,0);assert.match(result.stderr,/notes.evidence must be an array of strings/);
  await assert.rejects(fs.access(output));assert.equal(await fs.readFile(memo,'utf8'),'My personal memo');
 }finally{await fs.rm(work,{recursive:true,force:true});}
});

test('competing Markdown and legacy memos stop generation before publishing or editing',async()=>{
 const work=await fs.mkdtemp(path.join(os.tmpdir(),'cps-portable-competing-memos-'));
 try{
  const input=path.join(root,'assets/plan-reference/input.json'),output=path.join(work,'output/deck.pptx');
  await fs.mkdir(path.dirname(output));
  for(const suffix of ['md','txt'])await fs.writeFile(output.replace('.pptx',`-発表メモ.${suffix}`),`Original ${suffix}`);
  const result=run(process.execPath,['scripts/build_deck.mjs','--input',input,'--output',output,'--work-dir',work,'--python',python]);
  assert.notEqual(result.status,0);assert.match(result.stderr,/Both Markdown and legacy text presentation memos exist/);
  await assert.rejects(fs.access(output));
  for(const suffix of ['md','txt'])assert.equal(await fs.readFile(output.replace('.pptx',`-発表メモ.${suffix}`),'utf8'),`Original ${suffix}`);
 }finally{await fs.rm(work,{recursive:true,force:true});}
});
