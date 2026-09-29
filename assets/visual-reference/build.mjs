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

// Parse the actual synthetic source, avoiding a second copy of the numbers.
const source = await fs.readFile(path.join(here, '../example-source.org'), 'utf8');
const matches = [...source.matchAll(/^\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(保持)?\s*\|\s*$/gm)];
const data = matches.map(m => ({ t: Number(m[1]), v: Number(m[2]), kept: !!m[3] }));
if (data.length !== 13) throw new Error('Expected 13 explicitly synthetic input rows.');
const retained = data.filter(d => d.kept);
const maxAll = Math.max(...data.map(d => d.v));
const maxKept = Math.max(...retained.map(d => d.v));
const aboveAll = data.filter(d => d.v > 1000).length;
const aboveKept = retained.filter(d => d.v > 1000).length;
if (retained.length !== 3 || maxAll !== 1120 || maxKept !== 970 || aboveAll !== 2 || aboveKept !== 0) {
  throw new Error('Source changed. Review the prose and chart before rebuilding.');
}
const font = 'Noto Sans JP';
const key = '#9BBB59';
const black = '#000000';
const gray = '#666666';
const pale = '#F0F5E7';
const logo = await fs.readFile(path.join(here, '../NewmajimeModeLogoSmall.png'));
const pres = Presentation.create({ slideSize: { width: 960, height: 540 } });

function rect(slide, name, x, y, w, h, fill, lineFill = 'none', lineWidth = 0, geometry = 'rect') {
  return slide.shapes.add({ geometry, name, position: { left:x, top:y, width:w, height:h }, fill,
    line: { fill:lineFill, width:lineWidth, style:'solid' } });
}
function txt(slide, name, text, x, y, w, h, size=24, bold=false, color=black, alignment='left', fill='none') {
  const s = rect(slide, name, x, y, w, h, fill, 'none');
  s.text = text;
  s.text.style = { typeface:font, fontSize:size, bold, color, alignment, verticalAlignment:'middle',
    autoFit:'none', wrap:true, insets:{ left:0, right:0, top:0, bottom:0 } };
  return s;
}
function logoAt(slide, x, y, width) {
  slide.images.add({ blob:logo, contentType:'image/png', alt:'CPS LAB ロゴ', fit:'contain',
    position:{ left:x, top:y, width, height:width*123/438 } });
}
function base(page, divider=false) {
  const slide = pres.slides.add();
  slide.background.fill = '#FFFFFF';
  if (divider) logoAt(slide, 808.128, 23.136, 116.256);
  else {
    rect(slide,'footer-line',0,484.32,960,5.664,key);
    logoAt(slide,30.816,504.288,85.92);
  }
  const pageNumber=txt(slide,'page',String(page),714.048,500.544,223.968,28.8,18.667,false,black,'right');
  pageNumber.text.style={typeface:'Arial',fontSize:18.667,color:black,alignment:'right',verticalAlignment:'middle',insets:{left:0,right:0,top:0,bottom:0}};
  txt(slide,'fictional-disclosure','架空作例・合成データ',150,501,500,28,14,false,gray);
  slide.speakerNotes.textFrame.setText('架空研究の教材。全数値は assets/example-source.org の合成データであり、実測値ではない。CPS LABの視覚スタイルと編集可能性を示す6種類のレイアウト見本。研究発表の推奨枚数・章配分ではない。');
  return slide;
}
function heading(slide, title, message) {
  txt(slide,'title',title,27,10,900,54,36,true);
  if (message) txt(slide,'message',message,48,86,864,66,25.33,true);
}

// 1. Title: canonical colour band, two neutral author bands, common footer.
{
  const s=base(1);
  txt(s,'venue','研究発表の視覚作例',48,32,850,40,24);
  txt(s,'topic','室内環境ログの記録間隔\n合成データを用いた予備検討',72,148.512,816,115.776,38.667,true,black,'center',key);
  txt(s,'affiliation','CPS LAB スタイル見本',170,309,620,40,24,false,black,'center','#999999');
  txt(s,'author','架空の発表者',170,362,620,40,24,false,black,'center','#999999');
}
// 2. Divider: upper-right logo, no lower line or second logo.
{
  const s=base(2,true);
  txt(s,'chapter','記録間隔の比較',75.84,347.04,816,107.232,53.333,true,black,'center',key);
}
// 3. Native editable diagram, showing an operation rather than a causal claim.
{
  const s=base(3);
  heading(s,'同じ入力の間引き','全13点から、0・5・10分の3点だけを保持する');
  txt(s,'all-label','1分間隔の入力',48,180,280,36,24,true);
  txt(s,'kept-label','5分間隔で保持',48,325,280,36,24,true);
  const start=340, step=42;
  for (let i=0;i<13;i++) {
    const x=start+i*step;
    const inputPoint=rect(s,`input-${i}`,x,198,18,18,'#666666','none',0,'ellipse');
    txt(s,`minute-${i}`,String(i),x-10,165,38,26,18.667,false,gray,'center');
    if(data[i].kept) {
      const retainedPoint=rect(s,`retained-${i}`,x-2,342,22,22,key,black,1.2);
      s.shapes.connect(inputPoint,retainedPoint,
        {kind:'straight',fromSide:'bottom',toSide:'top',line:{fill:gray,width:1.2},tail:{type:'triangle',width:'sm',length:'sm'}});
    }
  }
  txt(s,'axis-unit','時刻 [分]',794,266,95,28,18.667,false,gray,'right');
  txt(s,'arrow-meaning','矢印は「保持する点」の対応',340,403,510,30,21.333,false,gray);
  txt(s,'source-note','合成系列1例／開始時刻0分／間引き処理だけを確認',48,443,864,25,18.667,false,gray);
}
// 4. Native scatter chart with complete literal data and an embedded workbook.
{
  const s=base(4);
  heading(s,'この例では高い値が記録に残らない','5分間隔の保持点には、1000 ppmを超える値がない');
  const chart=s.charts.add('scatter',{
    position:{left:46,top:170,width:652,height:292},
    series:[
      {name:'1分間隔 (小点)',xValues:data.map(d=>d.t),values:data.map(d=>d.v),fill:'#666666',line:{fill:'none',width:0},marker:{symbol:'circle',size:7}},
      {name:'5分間隔 (大点)',xValues:retained.map(d=>d.t),values:retained.map(d=>d.v),fill:key,line:{fill:'none',width:0},marker:{symbol:'square',size:12}},
      {name:'説明用の任意閾値',xValues:[0,12],values:[1000,1000],line:{fill:'#777777',width:1.4,style:'dashed'},marker:{symbol:'none'}},
    ],
    scatterOptions:{style:'lineWithMarkers'},
    hasLegend:true,legend:{position:'bottom',overlay:false,textStyle:{typeface:font,fontSize:18.667,fill:black}},
    xAxis:{title:'時刻 [分]',min:0,max:12,majorUnit:2,numberFormatCode:'0',position:'bottom',textStyle:{typeface:font,fontSize:18.667},majorGridlines:null},
    yAxis:{title:'模擬濃度 [ppm]',min:600,max:1200,majorUnit:200,numberFormatCode:'0',textStyle:{typeface:font,fontSize:18.667},majorGridlines:{fill:'#DDDDDD',width:1}},
    chartFill:'#FFFFFF',plotAreaFill:'#FFFFFF',chartLine:{fill:'none',width:0},plotAreaLine:{fill:'none',width:0},
  });
  applyPresentationChartFont(chart,{fontFamily:font});
  txt(s,'maximum-label','保持最大値',724,187,190,30,24,true);
  txt(s,'all-max',`全13点\n${maxAll} ppm`,724,234,190,74,25.333,false);
  txt(s,'kept-max',`保持3点\n${maxKept} ppm`,724,335,190,74,25.333,true);
  txt(s,'condition','合成系列1例／開始時刻0分／閾値は安全基準を表さない',48,455,860,24,16,false,gray);
}
// 5. Native table preserves units and scope without implying battery savings.
{
  const s=base(5);
  heading(s,'保持点数と最大値が変わった','点数の減少と、残った値を分けて見る');
  const table=s.tables.add({rows:4,columns:3,left:48,top:184,width:864,height:238,
    columnWidths:[412,226,226],values:[['比較項目','1分間隔','5分間隔'],['保持点数',String(data.length),String(retained.length)],['保持最大値 [ppm]',String(maxAll),String(maxKept)],['1000 ppm超の記録点数',String(aboveAll),String(aboveKept)]]});
  table.borders.assign({fill:'#CCCCCC',width:1,style:'solid'});
  table.cells.block({row:0,column:0,rowCount:4,columnCount:3}).assign({textStyle:{typeface:font,fontSize:24,color:black},margins:{left:16,right:16,top:8,bottom:8},anchor:'center'});
  for(let r=0;r<4;r++)for(let c=0;c<3;c++){
    const cell=table.getCell(r,c);cell.fill=r===0?pale:'#FFFFFF';
    cell.text.style={typeface:font,fontSize:24,bold:r===0 || c===2,color:black,alignment:c===0?'left':'center',verticalAlignment:'middle'};
  }
  txt(s,'scope','合成データからの計算。消費電力・継続時間・健康リスクは未評価',48,438,864,31,18.667,false,gray);
}
// 6. Summary: one key finding with measured scope and next step separated.
{
  const s=base(6);
  txt(s,'summary-title','記録間隔の検討方法',48,35,864,57,32,true,black,'center',key);
  txt(s,'finding-label','今回分かったこと',48,132,320,37,26.667,true);
  txt(s,'finding','一つの合成系列では、5分間隔の保持点に\n短時間の高い値が残らなかった。',48,181,864,84,26.667);
  txt(s,'next-label','次に確かめること',48,294,320,37,26.667,true);
  txt(s,'next','波形・開始時刻を変え、実機条件で確認する。',48,342,864,40,25.333);
  txt(s,'conclusion','記録点数と、残る変化を併せて確かめる',48,411,864,58,26.667,true,black,'center',key).borderRadius=8;
}

const candidatePath=path.join(stage,'candidate.pptx');
const finalPath=path.join(out,'cps-layout-reference.pptx');
await (await PresentationFile.exportPptx(pres)).save(candidatePath);
await finalizePresentation({workspaceDir,candidatePath,finalPath,pythonExecutable:RUNTIME_PYTHON,
  integrityValidatorPath:path.join(PRESENTATIONS_SKILL_DIR,'container_tools/inspect_presentation_package_integrity.py'),
  layoutValidatorPath:path.join(PRESENTATIONS_SKILL_DIR,'container_tools/inspect_presentation_layout_geometry.py'),
  layoutArgs:['--expected-slide-size-emu','9144000,5143500','--validate-bullet-geometry','--validate-heading-fit','--require-native-table-slide','5'],
  explicitTotalSlideCount:6,requiredNativeTableOwnerSlides:[5],requiredNativeChartOwnerSlides:[4],materializeLiteralChartWorkbooks:true,
  fontPolicy:{basis:'design',families:[font,'Arial']},verifyArtifactToolImport:true,
  receiptPath:path.join(stage,'validation.json')});

// Render the final exported package, not only the in-memory builder.
const final=await PresentationFile.importPptx(await FileBlob.load(finalPath));
const slides=final.slides.items;
const thumbs=[];
for(let i=0;i<slides.length;i++) {
  const blob=await final.export({slide:slides[i],format:'png',scale:1.5});
  const bytes=Buffer.from(await blob.arrayBuffer());
  await fs.writeFile(path.join(out,`slide-${i+1}.png`),bytes);
  thumbs.push(await sharp(bytes).resize(480,270).png().toBuffer());
}
await sharp({create:{width:1480,height:590,channels:3,background:'#E5E5E5'}})
  .composite(thumbs.map((input,i)=>({input,left:10+(i%3)*490,top:10+Math.floor(i/3)*290})))
  .png().toFile(path.join(out,'contact-sheet.png'));
console.log(JSON.stringify({outputDirectory:out,slides:slides.length,validationReceipt:path.join(stage,'validation.json')},null,2));
