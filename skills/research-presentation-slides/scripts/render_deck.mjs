#!/usr/bin/env node
// Render the saved final file; this is verification, never a substitute for the user’s completed-image review.
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {runtime,args} from './runtime.mjs';
const a=args(['input','output-dir','scale','renderer','pdf','pdf-source-sha256']);if(!a.input||!a['output-dir'])throw new Error('Required --input <pptx> --output-dir <directory>');
const {PresentationFile,FileBlob,sharp}=await runtime(),source=path.resolve(a.input),out=path.resolve(a['output-dir']);
await fs.mkdir(out,{recursive:true});const pages=[],thumbs=[];
let renderer=a.renderer||'artifact-tool',images=[],pdfRecord;
if(renderer==='powerpoint'||renderer==='pdf'){
 let pdf,count,engine;
 if(renderer==='powerpoint'){
  if(process.platform!=='darwin')throw new Error('PowerPoint AppleScript renderer requires macOS; select an available renderer on this computer.');
  pdf=path.join(out,'powerpoint-export.pdf');
  try{await fs.access(pdf);throw new Error('Use a new output directory: PDF already exists.');}catch(e){if(e.code!=='ENOENT')throw e;}
  const script=path.join(path.dirname(fileURLToPath(import.meta.url)),'render_powerpoint.applescript');
  const result=execFileSync('/usr/bin/osascript',[script,source,pdf],{encoding:'utf8',timeout:240000}).trim().split('|');
  count=Number(result[1]);engine=`Microsoft PowerPoint ${result[0]} → PDF → Poppler Cairo`;
 }else{
  const sha=crypto.createHash('sha256').update(await fs.readFile(source)).digest('hex');
  if(!a.pdf||a['pdf-source-sha256']!==sha)throw new Error('PDF fallback requires --pdf and --pdf-source-sha256 matching the source PPTX; separately retain the actual export log.');
  pdf=path.resolve(a.pdf);engine='Provided PDF → Poppler Cairo (export provenance must be verified in the review record)';
 }
 execFileSync(process.env.PDFTOCAIRO||'pdftocairo',['-r',String(96*Number(a.scale||1.5)),'-png',pdf,path.join(out,'ppt-page')]);
 pdfRecord={sha256:crypto.createHash('sha256').update(await fs.readFile(pdf)).digest('hex'),source_binding:a['pdf-source-sha256']||'exported directly from requested PPTX'};
 const names=(await fs.readdir(out)).filter(n=>/^ppt-page-\d+\.png$/.test(n)).sort((x,y)=>Number(x.match(/\d+/)[0])-Number(y.match(/\d+/)[0]));
 if(count&&names.length!==count)throw new Error('PowerPoint PDF page count differs from presentation slide count.');
 images=await Promise.all(names.map(n=>fs.readFile(path.join(out,n))));
 for(const n of names)await fs.unlink(path.join(out,n));
 renderer=engine;
}else if(renderer==='artifact-tool'){
 const p=await PresentationFile.importPptx(await FileBlob.load(source));
 for(const s of p.slides.items)images.push(Buffer.from(await(await p.export({slide:s,format:'png',scale:Number(a.scale||1.5)})).arrayBuffer()));
 renderer='@oai/artifact-tool final PPTX reimport (check for renderer-specific text clipping)';
}else throw new Error('Unknown renderer; choose artifact-tool, powerpoint or pdf.');
for(const [i,img] of images.entries()){
 const filename=`slide-${String(i+1).padStart(2,'0')}.png`;await fs.writeFile(path.join(out,filename),img);
 const m=await sharp(img).metadata();pages.push({number:i+1,image:filename,image_sha256:crypto.createHash('sha256').update(img).digest('hex'),width:m.width,height:m.height,status:'unverified'});
 thumbs.push(await sharp(img).resize(480,270,{fit:'contain',background:'#FFFFFF'}).png().toBuffer());
}
const columns=3,rows=Math.ceil(pages.length/columns);
await sharp({create:{width:columns*490+10,height:rows*280+10,channels:3,background:'#E6E6E6'}}).composite(thumbs.map((input,i)=>({input,left:10+(i%columns)*490,top:10+Math.floor(i/columns)*280}))).png().toFile(path.join(out,'contact-sheet.png'));
const record={pptx_sha256:crypto.createHash('sha256').update(await fs.readFile(source)).digest('hex'),renderer,pdf:pdfRecord,pages};await fs.writeFile(path.join(out,'render-record.json'),JSON.stringify(record,null,2)+'\n');console.log(JSON.stringify({pages:pages.length,output_directory:out}));
