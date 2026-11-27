// Rebuild the fictional CPS reference. See ../../references/visual-reference.md for environment inputs.
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';

const here = path.dirname(fileURLToPath(import.meta.url));
const { RUNTIME_NODE_MODULES, RUNTIME_PYTHON, PRESENTATIONS_SKILL_DIR, VISUAL_BUILD_DIR } = process.env;
for (const [name, value] of Object.entries({ RUNTIME_NODE_MODULES, RUNTIME_PYTHON, PRESENTATIONS_SKILL_DIR, VISUAL_BUILD_DIR })) {
  if (!value || !path.isAbsolute(value)) throw new Error(`Set ${name} to an absolute path resolved for this computer.`);
}
const requireRuntime = createRequire(path.join(RUNTIME_NODE_MODULES, 'package.json'));
const { Presentation, PresentationFile, FileBlob } = await import(pathToFileURL(requireRuntime.resolve('@oai/artifact-tool')).href);
const sharp = requireRuntime('sharp');
const { finalizePresentation, applyPresentationChartFont } = await import(pathToFileURL(path.join(PRESENTATIONS_SKILL_DIR, 'container_tools/artifact_tool_utils.mjs')).href);
const workspaceDir = VISUAL_BUILD_DIR;
const stage = path.join(workspaceDir, '.build');
const out = path.join(workspaceDir, 'output');
await fs.mkdir(stage, { recursive: true });
await fs.mkdir(out, { recursive: true });


const font='Noto Sans JP', black='#17202A', gray='#59636E';
const source=await fs.readFile(path.join(here,'../../references/cps-lab-style.md'),'utf8');
const rows=[...source.matchAll(/^\| ([^|]+) \| `(#(?:[0-9A-F]{6}))` \| `(#(?:[0-9A-F]{6}))` \| `(#(?:[0-9A-F]{6}))` \| `(#(?:[0-9A-F]{6}))` \|$/gm)];
const names=['iris','kimera','orange','sicilia','botanica','bordeaux'];
if(rows.length!==6) throw new Error('Expected exactly six CPS palettes in the canonical style table.');
const logo=await fs.readFile(path.join(here,'../NewmajimeModeLogoSmall.png'));
const pres=Presentation.create({slideSize:{width:960,height:540}});
function rect(slide,name,x,y,w,h,fill,lineFill='none',lineWidth=0){
 return slide.shapes.add({geometry:'rect',name,position:{left:x,top:y,width:w,height:h},fill,line:{fill:lineFill,width:lineWidth,style:'solid'}});
}
function txt(slide,name,text,x,y,w,h,size=24,bold=false,color=black,align='left'){
 const shape=rect(slide,name,x,y,w,h,'none');shape.text=text;
 shape.text.style={typeface:font,fontSize:size,bold,color,alignment:align,verticalAlignment:'middle',autoFit:'none',wrap:true,insets:{left:0,right:0,top:0,bottom:0}};
 return shape;
}
for(let i=0;i<rows.length;i++){
 const [,name,key,onKey,accent]=rows[i]; const s=pres.slides.add();s.background.fill='#FFFFFF';
 txt(s,'chapter','スタイル',48,11.52,268.8,32,16,false,accent);
 txt(s,'running-title','研究発表スライド',336,11.52,576,32,16,false,accent,'right');
 txt(s,'title',`配色サンプル：${name}`,48,49.92,864,42,36,true);
 txt(s,'message','白を基調に、メイン色とアクセント色を使い分ける',48,96,864,57.6,30.667,true);
 const swatches=[['ベース','#FFFFFF',black,'白背景を本文の基調にする'],['メイン',key,onKey,'帯・面・下端の横線に使う'],['アクセント',accent,'#FFFFFF','重要語・数値・図の注目点に使う']];
 swatches.forEach(([role,color,onColor,usage],j)=>{
  const y=178+j*94;
  rect(s,`swatch-${j}`,48,y,256,72,color,j===0?'#BEC4C9':'none',j===0?1:0);
  txt(s,`role-${j}`,role,64,y+10,224,52,26,true,onColor);
  txt(s,`hex-${j}`,color,340,y,572,36,28,true,j===2?accent:black);
  txt(s,`usage-${j}`,usage,340,y+40,572,32,22,false,gray);
 });
 txt(s,'sample-disclosure','配色比較の教材／共通レイアウト／下端横線あり',48,447,864,28,18.667,false,gray);
 rect(s,'footer-line',0,484.32,960,5.664,key);
 s.images.add({blob:logo,contentType:'image/png',alt:'CPS LAB ロゴ',fit:'contain',position:{left:30.816,top:504.288,width:85.92,height:85.92*123/438}});
 const page=txt(s,'page',String(i+1),714.048,500.544,223.968,28.8,18.667,false,black,'right');
 page.text.style={typeface:'Arial',fontSize:18.667,color:black,alignment:'right',verticalAlignment:'middle',insets:{left:0,right:0,top:0,bottom:0}};
 s.speakerNotes.textFrame.setText(`配色比較の教材。仕様の正本は references/cps-lab-style.md。${name}: base=#FFFFFF, main=${key}, accent=${accent}。画像はこの編集可能PPTXの検証用レンダーで、ImageGenによる完成イメージではない。実研究の結果を示すものではない。`);
}
const candidatePath=path.join(stage,'candidate.pptx'), finalPath=path.join(out,'cps-color-reference.pptx');
await (await PresentationFile.exportPptx(pres)).save(candidatePath);
await finalizePresentation({workspaceDir,candidatePath,finalPath,pythonExecutable:RUNTIME_PYTHON,
 integrityValidatorPath:path.join(PRESENTATIONS_SKILL_DIR,'container_tools/inspect_presentation_package_integrity.py'),
 layoutValidatorPath:path.join(PRESENTATIONS_SKILL_DIR,'container_tools/inspect_presentation_layout_geometry.py'),
 layoutArgs:['--expected-slide-size-emu','9144000,5143500','--validate-heading-fit'],explicitTotalSlideCount:6,
 fontPolicy:{basis:'design',families:[font,'Arial']},verifyArtifactToolImport:true,receiptPath:path.join(stage,'validation.json')});
const final=await PresentationFile.importPptx(await FileBlob.load(finalPath));
for(let i=0;i<6;i++){
 const blob=await final.export({slide:final.slides.items[i],format:'png',scale:1.5});
 await fs.writeFile(path.join(out,`${names[i]}.png`),Buffer.from(await blob.arrayBuffer()));
}
console.log(JSON.stringify({outputDirectory:out,palettes:6}));
