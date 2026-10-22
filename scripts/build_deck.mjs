#!/usr/bin/env node
// Input is the approved production specification; changes belong here, not in the PPTX.
import fs from 'node:fs/promises';
import {constants} from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {pathToFileURL} from 'node:url';
import {runtime,args,readJSON} from './runtime.mjs';
import {CPS,loadProfile,resolveStructure,inch} from '../assets/layouts/cps.mjs';
import {managedMemo,memoHash,mergeMemo,renderMemoBody,renderPreparationMemo} from '../assets/layouts/memo.mjs';
const a=args(['input','output','work-dir','backend','python']);if(!a.input||!a.output||!a['work-dir'])throw new Error('Required: --input <json> --work-dir <private workspace> --output <workspace/output/new.pptx>');
const backend=a.backend||'portable';
if(!['portable','codex'].includes(backend))throw new Error('Choose --backend portable or codex.');
const inputPath=path.resolve(a.input),output=path.resolve(a.output),workspace=path.resolve(a['work-dir']),data=await readJSON(inputPath);
const relativeOutput=path.relative(workspace,path.dirname(output));
if(!relativeOutput||relativeOutput==='..'||relativeOutput.startsWith('..'+path.sep)||path.isAbsolute(relativeOutput)||!output.toLowerCase().endsWith('.pptx'))throw new Error('Output must be a new .pptx in a subdirectory of --work-dir, separate from private build receipts.');
if(data.schema_version!==1||['title','authors','short_title'].some(key=>typeof data.metadata?.[key]!=='string'||!data.metadata[key].trim()))throw new Error('schema_version 1 and non-empty metadata title, short_title, authors strings are required.');
const profile=await loadProfile(data.profile||'cps-midterm',data.style||{}),resolved=resolveStructure(data,profile);
async function requireAbsent(file){
 try{await fs.lstat(file);throw new Error(`Output already exists; choose a new revision filename: ${path.basename(file)}`);}catch(e){if(e.code!=='ENOENT')throw e;}
}
await requireAbsent(output);
await fs.mkdir(workspace,{recursive:true});
if((await fs.lstat(workspace)).isSymbolicLink())throw new Error('Work directory must not be a symbolic link.');
// Create only directories below the explicitly selected workspace; refuse symlink escapes.
let outputDirectory=workspace;
for(const component of relativeOutput.split(path.sep)){
 outputDirectory=path.join(outputDirectory,component);
 try{await fs.mkdir(outputDirectory);}catch(e){if(e.code!=='EEXIST')throw e;}
 const stat=await fs.lstat(outputDirectory);
 if(!stat.isDirectory()||stat.isSymbolicLink())throw new Error('Output subdirectories must be real directories inside --work-dir.');
}
const layoutPath=output.replace(/\.pptx$/i,'.layout.json');
const markdownMemoPath=output.replace(/\.pptx$/i,'-発表メモ.md'),legacyMemoPath=output.replace(/\.pptx$/i,'-発表メモ.txt');
await requireAbsent(layoutPath);
// A memo may contain user additions. Refuse links and inspect it before generation.
async function readMemo(file){
 try{
  const st=await fs.lstat(file);
  if(!st.isFile()||st.isSymbolicLink()||st.nlink!==1)throw new Error('Presentation memo must be a regular file without links.');
  const handle=await fs.open(file,constants.O_RDONLY|(constants.O_NOFOLLOW||0));
  try{return await handle.readFile('utf8');}finally{await handle.close();}
 }catch(e){if(e.code==='ENOENT')return null;throw e;}
}
const markdownMemo=await readMemo(markdownMemoPath),legacyMemo=await readMemo(legacyMemoPath);
if(markdownMemo!==null&&legacyMemo!==null)throw new Error('Both Markdown and legacy text presentation memos exist; choose the authoritative record before generation.');
// Preserve an existing text memo in place; new presentation memos use Markdown.
const isMarkdown=legacyMemo===null,memoPath=isMarkdown?markdownMemoPath:legacyMemoPath;
const existingMemo=isMarkdown?markdownMemo:legacyMemo;
const memoFormat=isMarkdown?'markdown':'text';
const stageRoot=path.join(workspace,'.build');
await fs.mkdir(stageRoot,{recursive:true});
if((await fs.lstat(stageRoot)).isSymbolicLink())throw new Error('Private build directory must not be a symbolic link.');
const stage=await fs.mkdtemp(path.join(stageRoot,path.basename(output,'.pptx')+'-'));
const generatedMemo=managedMemo(renderMemoBody(resolved.slides,data.metadata,memoFormat),memoFormat);
const memoCandidate=path.join(stage,isMarkdown?'memo-candidate.md':'memo-candidate.txt');
await fs.writeFile(memoCandidate,generatedMemo.text,{flag:'wx'});
const preparation=renderPreparationMemo(resolved.slides);
const preparationPath=path.join(stage,'production-checks.md');
if(preparation)await fs.writeFile(preparationPath,preparation,{flag:'wx'});
let mergedMemo;
try{mergedMemo=mergeMemo(existingMemo,generatedMemo.text,memoFormat);}
catch(error){throw new Error(`${error.message} Candidate memo: ${memoCandidate}`);}
await fs.writeFile(memoCandidate,mergedMemo);
async function verifyMemoUnchanged(){
 if(await readMemo(memoPath)!==existingMemo)throw new Error(`Presentation memo changed during generation; retain the current file and reconcile it before delivery. Candidate memo: ${memoCandidate}`);
 // An authoritative memo in the other format may have appeared after preflight.
 if(await readMemo(isMarkdown?legacyMemoPath:markdownMemoPath)!==null)throw new Error(`Both Markdown and legacy text presentation memos exist; retain them and choose the authoritative record. Candidate memo: ${memoCandidate}`);
}
let pres,cps,PresentationFile;
if(backend==='portable'){
 const [{default:PptxGenJS},{default:sharp},{PortableCPS}]=await Promise.all([import('pptxgenjs'),import('sharp'),import('../assets/layouts/portable.mjs')]);
 pres=new PptxGenJS();
 pres.defineLayout({name:'CPS',width:profile.slide_size_in[0],height:profile.slide_size_in[1]});pres.layout='CPS';
 pres.author=data.metadata.authors;pres.title=data.metadata.title;pres.subject=data.metadata.short_title;
 pres.lang=data.metadata.language||'en-GB';pres.theme={headFontFace:profile.font,bodyFontFace:profile.font,lang:pres.lang};
 cps=new PortableCPS(pres,profile,data,path.dirname(inputPath),sharp);
}else{
 const api=await runtime();PresentationFile=api.PresentationFile;
 pres=api.Presentation.create({slideSize:{width:inch(profile.slide_size_in[0]),height:inch(profile.slide_size_in[1])}});
 cps=new CPS(pres,profile,data,path.dirname(inputPath),api.sharp);
}
for(const s of resolved.slides)await cps.page(s,resolved);
const candidate=path.join(stage,'candidate.pptx');
const scriptDir=path.dirname(fileURLToPath(import.meta.url));
const skill=process.env.PRESENTATIONS_SKILL_DIR;
const python=a.python||process.env.RUNTIME_PYTHON||(process.platform==='win32'?'python':'python3');
const rolePath=path.join(stage,'roles.json');await fs.writeFile(rolePath,JSON.stringify({metadata:{title:data.metadata.title,authors:data.metadata.authors},slides:cps.records}));
if(backend==='portable'){
 await pres.writeFile({fileName:candidate});
 execFileSync(python,[path.join(scriptDir,'finalize_portable.py'),candidate,rolePath]);
 if(cps.records.some(record=>record.media?.length))execFileSync(python,[path.join(scriptDir,'embed_media.py'),candidate,rolePath,'--input-dir',path.dirname(inputPath),'--report',path.join(stage,'media.json')]);
 await verifyMemoUnchanged();
 // Exclusive creation protects an existing user revision, including a concurrent writer.
 await fs.copyFile(candidate,output,1);
}else{
if(!skill)throw new Error('Codex backend requires PRESENTATIONS_SKILL_DIR.');
const {finalizePresentation,applyPresentationChartFont}=await import(pathToFileURL(path.join(skill,'container_tools/artifact_tool_utils.mjs')).href);
for(const slide of pres.slides.items) for(const chart of slide.charts.items) applyPresentationChartFont(chart,{fontFamily:profile.font});
await(await PresentationFile.exportPptx(pres)).save(candidate);
execFileSync(python,[path.join(scriptDir,'tag_generated.py'),candidate,rolePath]);
if(cps.records.some(record=>record.media?.length))execFileSync(python,[path.join(scriptDir,'embed_media.py'),candidate,rolePath,'--input-dir',path.dirname(inputPath),'--report',path.join(stage,'media.json')]);
const tableOwners=cps.records.filter(r=>r.expected_elements.some(e=>e.kind==='table')).map(r=>r.number);
const chartOwners=cps.records.filter(r=>r.expected_elements.some(e=>e.kind==='chart')).map(r=>r.number);
await verifyMemoUnchanged();
await finalizePresentation({workspaceDir:workspace,candidatePath:candidate,finalPath:output,pythonExecutable:python,integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),layoutArgs:['--expected-slide-size-emu','9144000,5143500','--validate-heading-fit',...tableOwners.flatMap(n=>['--require-native-table-slide',String(n)])],explicitTotalSlideCount:resolved.slides.length,requiredNativeTableOwnerSlides:tableOwners,requiredNativeChartOwnerSlides:chartOwners,materializeLiteralChartWorkbooks:true,fontPolicy:{basis:'design',families:[profile.font]},verifyArtifactToolImport:true,receiptPath:path.join(stage,'finalizer.json')});
}
const sha=crypto.createHash('sha256').update(await fs.readFile(output)).digest('hex');
const layout={schema_version:1,backend,pptx_sha256:sha,source_sha256:crypto.createHash('sha256').update(await fs.readFile(inputPath)).digest('hex'),profile_id:profile.id,slides:cps.records,structure:resolved.structure,ranges:resolved.ranges,
 memo:{file:path.basename(memoPath),format:memoFormat,sha256:memoHash(mergedMemo),generated_sha256:generatedMemo.generated_sha256}};
await fs.writeFile(layoutPath,JSON.stringify(layout,null,2)+'\n',{flag:'wx'});
await verifyMemoUnchanged();
if(existingMemo===null)await fs.writeFile(memoPath,mergedMemo,{flag:'wx'});
else{
 // Rename replaces the directory entry, never following a late symlink or hard link.
 const memoTemp=path.join(stage,isMarkdown?'memo.md':'memo.txt');await fs.writeFile(memoTemp,mergedMemo,{flag:'wx'});
 await fs.rename(memoTemp,memoPath);
}
console.log(JSON.stringify({pptx:output,sha256:sha,slides:resolved.slides.length,layout:layoutPath,memo:memoPath,...(preparation?{preparation:preparationPath}:{})}));
