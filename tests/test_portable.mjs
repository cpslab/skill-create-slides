import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';

const root=fileURLToPath(new URL('../',import.meta.url));
const python=process.env.RUNTIME_PYTHON||(process.platform==='win32'?'python':'python3');
const cleanEnv={...process.env};
for(const key of ['RUNTIME_NODE_MODULES','CODEX_PRIMARY_RUNTIME_NODE_MODULES','PRESENTATIONS_SKILL_DIR'])delete cleanEnv[key];
function run(command,args){return spawnSync(command,args,{cwd:root,env:cleanEnv,encoding:'utf8',timeout:60000});}

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
  const sidecar=JSON.parse(await fs.readFile(output.replace('.pptx','.layout.json'),'utf8'));
  assert.equal(sidecar.backend,'portable');
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

test('sidecar and memo links are rejected before publishing; regular memo additions survive',async()=>{
 const work=await fs.mkdtemp(path.join(os.tmpdir(),'cps-portable-files-'));
 try{
  const input=path.join(root,'assets/plan-reference/input.json'),output=path.join(work,'output/deck.pptx');
  await fs.mkdir(path.dirname(output));
  const sentinel=path.join(work,'outside.txt');await fs.writeFile(sentinel,'Preserve this content');
  const build=()=>run(process.execPath,['scripts/build_deck.mjs','--input',input,'--output',output,'--work-dir',work,'--python',python]);
  for(const destination of [output.replace('.pptx','.layout.json'),output.replace('.pptx','-発表メモ.txt')]){
   await fs.symlink(sentinel,destination);
   const result=build();assert.notEqual(result.status,0);
   assert.equal(await fs.readFile(sentinel,'utf8'),'Preserve this content');await assert.rejects(fs.access(output));
   await fs.unlink(destination);
  }
  const memo=output.replace('.pptx','-発表メモ.txt');
  await fs.writeFile(memo,'My rehearsal note: pause here.');
  const result=build();assert.equal(result.status,0,result.stderr);
  assert.match(await fs.readFile(memo,'utf8'),/My rehearsal note: pause here\./);
 }finally{await fs.rm(work,{recursive:true,force:true});}
});
