#!/usr/bin/env node
// Input is the approved production specification; changes belong here, not in the PPTX.
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {pathToFileURL} from 'node:url';
import {runtime,args,readJSON} from './runtime.mjs';
import {CPS,loadProfile,resolveStructure,inch} from '../assets/layouts/cps.mjs';
const a=args(['input','output','work-dir']);if(!a.input||!a.output||!a['work-dir'])throw new Error('Required: --input <json> --work-dir <private workspace> --output <workspace/output/new.pptx>');
const inputPath=path.resolve(a.input),output=path.resolve(a.output),workspace=path.resolve(a['work-dir']),data=await readJSON(inputPath);
const relativeOutput=path.relative(workspace,path.dirname(output));
if(!relativeOutput||relativeOutput==='..'||relativeOutput.startsWith('..'+path.sep)||path.isAbsolute(relativeOutput)||!output.toLowerCase().endsWith('.pptx'))throw new Error('Output must be a new .pptx in a subdirectory of --work-dir, separate from private build receipts.');
if(data.schema_version!==1||['title','authors','short_title'].some(key=>typeof data.metadata?.[key]!=='string'||!data.metadata[key].trim()))throw new Error('schema_version 1 and non-empty metadata title, short_title, authors strings are required.');
const profile=await loadProfile(data.profile||'cps-midterm',data.style||{}),resolved=resolveStructure(data,profile);
try {await fs.access(output);throw new Error('Output already exists; choose a new revision filename.');}catch(e){if(e.code!=='ENOENT')throw e;}
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
const {Presentation,PresentationFile,sharp}=await runtime();
const pres=Presentation.create({slideSize:{width:inch(profile.slide_size_in[0]),height:inch(profile.slide_size_in[1])}});
const cps=new CPS(pres,profile,data,path.dirname(inputPath),sharp);
for(const s of resolved.slides)await cps.page(s,resolved);
const stageRoot=path.join(workspace,'.build');
await fs.mkdir(stageRoot,{recursive:true});
if((await fs.lstat(stageRoot)).isSymbolicLink())throw new Error('Private build directory must not be a symbolic link.');
const stage=await fs.mkdtemp(path.join(stageRoot,path.basename(output,'.pptx')+'-'));
const candidate=path.join(stage,'candidate.pptx');
const skill=process.env.PRESENTATIONS_SKILL_DIR,python=process.env.RUNTIME_PYTHON;
if(!skill||!python)throw new Error('Set PRESENTATIONS_SKILL_DIR and RUNTIME_PYTHON to available finalisation tools; no candidate was exported.');
const {finalizePresentation,applyPresentationChartFont}=await import(pathToFileURL(path.join(skill,'container_tools/artifact_tool_utils.mjs')).href);
for(const slide of pres.slides.items) for(const chart of slide.charts.items) applyPresentationChartFont(chart,{fontFamily:profile.font});
await(await PresentationFile.exportPptx(pres)).save(candidate);
const rolePath=path.join(stage,'roles.json');await fs.writeFile(rolePath,JSON.stringify({metadata:{title:data.metadata.title,authors:data.metadata.authors},slides:cps.records}));
execFileSync(python,[path.join(path.dirname(fileURLToPath(import.meta.url)),'tag_generated.py'),candidate,rolePath]);
if(cps.records.some(record=>record.media?.length))execFileSync(python,[path.join(path.dirname(fileURLToPath(import.meta.url)),'embed_media.py'),candidate,rolePath,'--input-dir',path.dirname(inputPath),'--report',path.join(stage,'media.json')]);
const tableOwners=cps.records.filter(r=>r.expected_elements.some(e=>e.kind==='table')).map(r=>r.number);
const chartOwners=cps.records.filter(r=>r.expected_elements.some(e=>e.kind==='chart')).map(r=>r.number);
await finalizePresentation({workspaceDir:workspace,candidatePath:candidate,finalPath:output,pythonExecutable:python,integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),layoutArgs:['--expected-slide-size-emu','9144000,5143500','--validate-heading-fit',...tableOwners.flatMap(n=>['--require-native-table-slide',String(n)])],explicitTotalSlideCount:resolved.slides.length,requiredNativeTableOwnerSlides:tableOwners,requiredNativeChartOwnerSlides:chartOwners,materializeLiteralChartWorkbooks:true,fontPolicy:{basis:'design',families:[profile.font]},verifyArtifactToolImport:true,receiptPath:path.join(stage,'finalizer.json')});
const sha=crypto.createHash('sha256').update(await fs.readFile(output)).digest('hex');
const layout={schema_version:1,pptx_sha256:sha,source_sha256:crypto.createHash('sha256').update(await fs.readFile(inputPath)).digest('hex'),profile_id:profile.id,slides:cps.records,structure:resolved.structure,ranges:resolved.ranges};
await fs.writeFile(output.replace(/\.pptx$/i,'.layout.json'),JSON.stringify(layout,null,2)+'\n');
const memoPath=output.replace(/\.pptx$/i,'-発表メモ.txt');
const start='=== GENERATED CONTENT START ===',end='=== GENERATED CONTENT END ===';
const generated=start+'\n'+resolved.slides.map(s=>`表示ページ番号：${s.number}\nスライドID：${s.id}\n題名：${s.title||data.metadata.title}\n口頭補足：${s.notes||'追加の口頭補足なし'}\n根拠：${(s.sources||[]).join(' / ')||'今回の入力資料'}\n`).join('\n')+end;
let existing='';try{existing=await fs.readFile(memoPath,'utf8');}catch(e){if(e.code!=='ENOENT')throw e;}
const merged=existing.includes(start)&&existing.includes(end)?existing.slice(0,existing.indexOf(start))+generated+existing.slice(existing.indexOf(end)+end.length):generated+'\n\n利用者の追記（再生成時も保持）：\n'+existing;
await fs.writeFile(memoPath,merged);
console.log(JSON.stringify({pptx:output,sha256:sha,slides:resolved.slides.length,layout:output.replace(/\.pptx$/i,'.layout.json'),memo:memoPath}));
