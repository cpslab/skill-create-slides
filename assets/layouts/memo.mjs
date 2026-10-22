// Presentation notes share one interpretation across both PPTX backends and the external memo.
import crypto from 'node:crypto';

export const memoHash=body=>crypto.createHash('sha256').update(body,'utf8').digest('hex');
export function markdownText(value){
 return String(value).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/[\\`*_[\]{}()#+\-.!|>~]/g,'\\$&').replace(/\r\n?/g,'\n').replace(/\n/g,'  \n');
}
function strings(value,field,id){
 if(value===undefined)return [];
 if(!Array.isArray(value)||value.some(item=>typeof item!=='string'))throw new Error(`Slide ${id}: ${field} must be an array of strings.`);
 return [...value];
}
export function normalizeNotes(slide){
 const id=slide.id||'(unknown)',notes=slide.notes;
 let text='',evidence=[],preparation=[];
 if(typeof notes==='string')text=notes;
 else if(notes!==undefined){
  if(!notes||typeof notes!=='object'||Array.isArray(notes))throw new Error(`Slide ${id}: notes must be a string or an object.`);
  const unknown=Object.keys(notes).filter(key=>!['text','evidence','preparation'].includes(key));
  if(unknown.length)throw new Error(`Slide ${id}: unsupported notes field ${unknown.join(', ')}.`);
  if(notes.text!==undefined&&typeof notes.text!=='string')throw new Error(`Slide ${id}: notes.text must be a string.`);
  text=notes.text||'';
  evidence=strings(notes.evidence,'notes.evidence',id);
  preparation=strings(notes.preparation,'notes.preparation',id);
 }
 const claims=typeof slide.message==='string'&&slide.message.trim()?[slide.message]:
  (Array.isArray(slide.semantic_claims)?slide.semantic_claims.flatMap(claim=>typeof claim?.text==='string'&&claim.text.trim()?[claim.text]:[]):[]);
 return {text,evidence,preparation,claims,sources:strings(slide.sources,'sources',id)};
}
export function speakerNotes(slide){
 const n=normalizeNotes(slide),parts=[];
 if(n.claims.length)parts.push('画面の主張\n'+n.claims.join('\n'));
 if(n.text)parts.push('口頭補足\n'+n.text);
 if(n.sources.length)parts.push('根拠\n'+n.sources.join('\n'));
 if(n.evidence.length)parts.push('根拠・確認情報\n'+n.evidence.join('\n'));
 return parts.join('\n\n');
}
export function renderMemoBody(slides,metadata,format='markdown'){
 const md=format==='markdown';
 return (md?'# 発表メモ\n\n':'')+slides.map(slide=>{
  const n=normalizeNotes(slide),title=slide.title||metadata.title;
  if(md)return `## 表示ページ ${slide.number}\n\n- スライドID：${markdownText(slide.id)}\n- 題名：${markdownText(title)}\n\n`+
   (n.claims.length?`### 画面の主張\n\n${markdownText(n.claims.join('\n'))}\n\n`:'')+
   `### 口頭補足\n\n${markdownText(n.text||'追加の口頭補足なし')}\n\n### 根拠\n\n${markdownText(n.sources.join(' / ')||'今回の入力資料')}\n`+
   (n.evidence.length?`\n### 根拠・確認情報\n\n${markdownText(n.evidence.join('\n'))}\n`:'');
  return `表示ページ番号：${slide.number}\nスライドID：${slide.id}\n題名：${title}\n`+
   (n.claims.length?`画面の主張：${n.claims.join('\n')}\n`:'')+
   `口頭補足：${n.text||'追加の口頭補足なし'}\n根拠：${n.sources.join(' / ')||'今回の入力資料'}\n`+
   (n.evidence.length?`根拠・確認情報：${n.evidence.join('\n')}\n`:'');
 }).join('\n');
}
export function renderPreparationMemo(slides){
 const sections=slides.flatMap(slide=>{
  const n=normalizeNotes(slide);
  return n.preparation.length?[`## 表示ページ ${slide.number}｜${markdownText(slide.id)}\n\n${n.preparation.map(item=>'- '+markdownText(item)).join('\n')}\n`]:[];
 });
 return sections.length?'# 制作確認\n\n発表用の読み上げ補足とは別に、制作者が確認する項目。\n\n'+sections.join('\n'):'';
}
export function memoMarkers(format){
 return format==='markdown'?{start:'<!-- GENERATED CONTENT START -->',end:'<!-- GENERATED CONTENT END -->',hashPrefix:'<!-- GENERATED CONTENT SHA256: ',hashSuffix:' -->'}:
  {start:'=== GENERATED CONTENT START ===',end:'=== GENERATED CONTENT END ===',hashPrefix:'=== GENERATED CONTENT SHA256: ',hashSuffix:' ==='};
}
export function managedMemo(body,format='markdown'){
 const m=memoMarkers(format),generated_sha256=memoHash(body);
 return {generated_sha256,text:m.start+'\n'+m.hashPrefix+generated_sha256+m.hashSuffix+'\n'+body+m.end};
}
export function mergeMemo(existing,generated,format='markdown'){
 const m=memoMarkers(format),before=existing||'';
 if(!before.includes(m.start)&&!before.includes(m.end)&&!before.includes(m.hashPrefix)){
  return generated+(format==='markdown'?'\n\n## 利用者の追記（再生成時も保持）\n\n':'\n\n利用者の追記（再生成時も保持）：\n')+before;
 }
 if(before.split(m.start).length!==2||before.split(m.end).length!==2)throw new Error('Presentation memo has ambiguous generated content markers; retain the current file and reconcile it.');
 const start=before.indexOf(m.start),end=before.indexOf(m.end),inner=before.slice(start+m.start.length,end);
 if(end<start||!inner.startsWith('\n'+m.hashPrefix))throw new Error('Presentation memo has no verified generated content hash; retain the current file and reconcile it.');
 const hashEnd=inner.indexOf('\n',1),hashLine=inner.slice(1,hashEnd);
 const hash=hashLine.slice(m.hashPrefix.length,-m.hashSuffix.length);
 if(hashEnd<0||!hashLine.endsWith(m.hashSuffix)||!/^[a-f0-9]{64}$/.test(hash)||memoHash(inner.slice(hashEnd+1))!==hash){
  throw new Error('Presentation memo generated content was edited or its hash is invalid; retain the current file and reconcile it.');
 }
 return before.slice(0,start)+generated+before.slice(end+m.end.length);
}
