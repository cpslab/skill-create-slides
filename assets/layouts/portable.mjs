// Public-library backend. Page composition and the input schema remain in CPS.
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {CPS} from './cps.mjs';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const colour=value=>value?.replace(/^#/,'');
const position=([x,y,w,h])=>({x,y,w,h});
const name=(role,id)=>`role:${role}|id:${id}`;

export class PortableCPS extends CPS {
 start(spec){
  this.spec=spec;this.slide=this.pres.addSlide();
  this.slide.background={color:colour(this.p.colour_roles.background)};
  this.slide.speakerNotes={textFrame:{setText:text=>this.slide.addNotes(text)}};
  this.objects=new Map();
  this.rec={number:spec.number,id:spec.id,required_text:[],expected_elements:[],allowed_overlaps:[],semantic_claims:spec.semantic_claims||[]};
  this.records.push(this.rec);return this.slide;
 }
 box(id,role,b,fill='none',line='none',lw=0,geometry='rect'){
  this.slide.addShape(geometry,{...position(b),objectName:name(role,id),
   fill:{color:colour(fill==='none'?'#FFFFFF':fill),transparency:fill==='none'?100:0},
   line:{color:colour(line==='none'?'#FFFFFF':line),width:lw,transparency:line==='none'?100:0}});
  const obj={bounds:b,name:name(role,id)};this.record(id,role,'shape',b);this.objects.set(id,obj);return obj;
 }
 text(id,text,b,role='body',opts={}){
  if(text===undefined||text===null||text==='')throw new Error(`Empty required text: ${id}`);
  const size=opts.size||this.p.typography_pt[role]||this.p.typography_pt.body;
  if(this.p.minimum_font_pt[role]&&size<this.p.minimum_font_pt[role])throw new Error(`${id}: font below profile minimum`);
  this.slide.addText(String(text),{...position(b),objectName:name(role,id),fontFace:opts.font||this.p.font,
   fontSize:size,bold:opts.bold??['title','question'].includes(role),color:colour(opts.color||this.p.colour_roles.body),
   align:opts.align||'left',valign:opts.valign==='mid'?'middle':opts.valign||'top',
   margin:0,breakLine:false,paraSpaceAfter:0,fit:'none',wrap:true,
   ...(opts.fill&&opts.fill!=='none'?{fill:{color:colour(opts.fill)}}:{}),
   lang:this.input.metadata.language||'en-GB'});
  const obj={bounds:b,name:name(role,id)};this.record(id,role,'shape',b,{text:String(text),font_pt:size});this.objects.set(id,obj);return obj;
 }
 async image(id,asset,b,role='image',fit='contain'){
  const file=path.resolve(this.dir,asset.path),bytes=await fs.readFile(file),meta=await this.sharp(bytes).metadata();
  if(!meta.width||!meta.height)throw new Error(`Image dimensions unavailable: ${asset.path}`);
  if(!['png','jpeg'].includes(meta.format))throw new Error(`Portable image format ${meta.format} is not supported. Supply a reviewed PNG/JPEG derivative and retain the original asset.`);
  if(!['contain','cover'].includes(fit))throw new Error(`Unsupported image fit: ${fit}`);
  const [x,y,w,h]=b,ratio=meta.width/meta.height;
  const actual=fit==='contain'?(w/h>ratio?[x+(w-h*ratio)/2,y,h*ratio,h]:[x,y+(h-w/ratio)/2,w,w/ratio]):b;
  // Preserve the original evidence asset; Office's crop settings implement cover.
  const data=`data:image/${meta.format};base64,${bytes.toString('base64')}`;
  // PptxGenJS 4 uses sizing; w/h describe the original aspect ratio before cropping.
  const sizing=fit==='cover'?{x,y,w:meta.width/96,h:meta.height/96,sizing:{type:'cover',w,h}}:position(actual);
  this.slide.addImage({data,...sizing,objectName:name(role,id),altText:asset.alt||id});
  const assetRef=asset.shared?'skill:'+path.relative(root,file).split(path.sep).join('/'):path.relative(this.dir,file).split(path.sep).join('/');
  this.record(id,role,'image',actual,{frame_bounds_in:b,asset:{path:assetRef,sha256:crypto.createHash('sha256').update(bytes).digest('hex'),width_px:meta.width,height_px:meta.height,effective_ppi:Math.min(meta.width/actual[2],meta.height/actual[3]),fit}});
  const obj={bounds:actual,name:name(role,id)};this.objects.set(id,obj);return obj;
 }
 table(id,data,b){
  const rows=data.rows,cols=rows[0]?.length;
  if(!rows.length||!cols||rows.some(r=>r.length!==cols))throw new Error('Table must be a rectangular, non-empty matrix');
  const [,,w,h]=b,widths=data.widths||Array(cols).fill(w/cols),size=data.font_pt||this.p.typography_pt.table;
  if(size<this.p.minimum_font_pt.table)throw new Error('Table font below profile minimum');
  if(Math.abs(widths.reduce((a,b)=>a+b,0)-w)>.02)throw new Error('Table column widths must sum to table width');
  const heights=data.heights||Array(rows.length).fill(h/rows.length);
  if(heights.length!==rows.length||heights.some(v=>!Number.isFinite(v)||v<=0)||Math.abs(heights.reduce((a,b)=>a+b,0)-h)>.02)throw new Error('Positive row heights must match table height');
  const padding={left:.1,right:.1,top:.08,bottom:.08,...data.padding_in};
  if(Object.values(padding).some(v=>!Number.isFinite(v)||v<0))throw new Error('Table padding must be finite and non-negative');
  const cells=rows.map((row,r)=>row.map(value=>({text:String(value),options:{bold:r===0,
   fill:colour(r===0?this.p.colour_roles.table_header:r===data.highlight_row?this.p.colour_roles.highlight:'#FFFFFF')}})));
  this.slide.addTable(cells,{...position(b),objectName:name('table',id),colW:widths,rowH:heights,
   fontFace:this.p.font,fontSize:size,color:colour(this.p.colour_roles.body),align:'left',valign:'middle',
   margin:[padding.top,padding.right,padding.bottom,padding.left].map(v=>v*72),
   border:{type:'solid',color:'CCD3C8',pt:.45},autoPage:false,verbose:false});
  this.record(id,'table','table',b,{table:{rows},font_pt:size});return this.slide;
 }
 chart(id,data,b){
  if(!data.unit||!data.subject||!data.aggregation||!data.status)throw new Error('Chart requires unit, subject, aggregation and status');
  const type=data.type||'bar';
  if(!['bar','line'].includes(type))throw new Error(`Portable chart type ${type} is not implemented; implement and validate its native semantics before use.`);
  if(!data.categories?.length||!data.series?.length||data.series.some(s=>s.values?.length!==data.categories.length||s.values.some(v=>!Number.isFinite(v))))throw new Error('Chart series require finite values matching categories');
  // Reject unimplemented decorations instead of silently changing their meaning.
  if(data.series.some(s=>s.marker||s.line))throw new Error('Portable per-series marker/line styling needs an explicit implementation; do not silently drop it.');
  const values=data.series.flatMap(s=>s.values),minimum=data.min??Math.min(0,...values),c=this.p.colour_roles;
  this.slide.addChart(type,data.series.map(s=>({name:s.name,labels:data.categories,values:s.values})),{
   ...position(b),objectName:name('chart',id),showLegend:true,legendPos:'b',legendFontFace:this.p.font,legendFontSize:12,
   chartColors:data.series.map((s,i)=>colour(s.fill||c.series[i%c.series.length])),showTitle:false,
   showValue:false,showCatName:false,showSerName:false,showBorder:false,barDir:'col',catAxisLabelFontFace:this.p.font,
   catAxisLabelFontSize:12,valAxisLabelFontFace:this.p.font,valAxisLabelFontSize:12,
   showCatAxisTitle:!!data.x_title,catAxisTitle:data.x_title||'',
   catAxisTitleFontFace:this.p.font,catAxisTitleFontSize:12,showValAxisTitle:true,
   valAxisTitle:data.unit,valAxisTitleFontFace:this.p.font,valAxisTitleFontSize:12,
   valAxisMinVal:minimum,...(data.max!==undefined?{valAxisMaxVal:data.max}:{}),valAxisLabelFormatCode:data.number_format||'0',
   catGridLine:{style:'none'},valGridLine:{color:'DDDDDD',width:.5},chartArea:{fill:{color:'FFFFFF'},roundedCorners:false},
   plotArea:{fill:{color:'FFFFFF'}},showMarker:type==='line',lineSize:2,lang:this.input.metadata.language||'en-GB'});
  this.record(id,'chart','chart',b,{chart:{categories:data.categories,series:data.series.map(({name,values})=>({name,values})),unit:data.unit,subject:data.subject,aggregation:data.aggregation,status:data.status}});
 }
 diagram(id,data){
  const nodes=new Map();
  for(const n of data.nodes){this.text(n.id,n.text,n.bounds_in,'diagram-node',{size:this.p.typography_pt.label,align:'center',valign:'middle',fill:this.p.colour_roles.highlight});nodes.set(n.id,n);}
  const anchor=(b,side)=>{const [x,y,w,h]=b;const a={left:[x,y+h/2],right:[x+w,y+h/2],top:[x+w/2,y],bottom:[x+w/2,y+h]};if(!a[side])throw new Error(`Unknown connector side ${side}`);return a[side];};
  for(const e of data.edges){
   if(!nodes.has(e.from)||!nodes.has(e.to)||!e.meaning)throw new Error('Every edge requires valid endpoints and meaning');
   if(!e.id||this.objects.has(e.id))throw new Error(`Missing/duplicate diagram edge ID ${e.id}`);
   const direction=e.direction??'forward';
   if(!['forward','backward','both','none'].includes(direction))throw new Error(`Unsupported diagram direction: ${direction}`);
   if(e.kind&&e.kind!=='straight')throw new Error('Portable diagram currently supports straight connectors only.');
   const fromSide=e.from_side||'right',toSide=e.to_side||'left',[x,y]=anchor(nodes.get(e.from).bounds_in,fromSide),[xx,yy]=anchor(nodes.get(e.to).bounds_in,toSide);
   this.slide.addShape('line',{x:Math.min(x,xx),y:Math.min(y,yy),w:Math.abs(xx-x),h:Math.abs(yy-y),flipH:xx<x,flipV:yy<y,objectName:name('diagram-edge',e.id),line:{color:colour(this.p.colour_roles.accent),width:1.2,
    beginArrowType:['backward','both'].includes(direction)?'triangle':'none',endArrowType:['forward','both'].includes(direction)?'triangle':'none'}});
   this.rec.expected_elements.push({id:e.id,role:'diagram-edge',kind:'connector',edge:{from:e.from,to:e.to,direction,meaning:e.meaning,from_side:fromSide,to_side:toSide}});
   this.rec.allowed_overlaps.push([e.id,e.from],[e.id,e.to]);this.objects.set(e.id,{});
  }
 }
}
