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
const accent = '#38761D';
const footerLine = process.env.FOOTER_LINE ?? 'on';
if (!['on','off'].includes(footerLine)) throw new Error('FOOTER_LINE must be on or off.');
const black = '#17202A';
const gray = '#59636E';
const pale = '#EFF5E4';
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
  if (divider) logoAt(slide, 808.128, 52.8, 116.256);
  else {
    if (footerLine === 'on') rect(slide,'footer-line',0,484.32,960,5.664,key);
    logoAt(slide,30.816,504.288,85.92);
  }
  const pageNumber=txt(slide,'page',String(page),714.048,500.544,223.968,28.8,18.667,false,black,'right');
  pageNumber.text.style={typeface:'Arial',fontSize:18.667,color:black,alignment:'right',verticalAlignment:'middle',insets:{left:0,right:0,top:0,bottom:0}};
  slide.speakerNotes.textFrame.setText('架空研究の教材。全数値は assets/example-source.org の合成データであり、実測値ではない。CPS LABの視覚スタイルと編集可能性を示す9種類のレイアウト見本。表紙と目次の素材枠は配置見本であり、実証写真や実動画ではない。研究発表の推奨枚数・章配分ではない。');
  if(page>=3) {
    const chapter={3:'目次',4:'03 ここまでの結果',5:'02 しくみと評価方法',6:'03 ここまでの結果',7:'03 ここまでの結果',8:'まとめ',9:'サマリ'}[page];
    txt(slide,`running-chapter-${page}`,chapter,48,11.52,268.8,32,16,false,accent);
    txt(slide,`running-title-${page}`,'室内環境ログの記録間隔',336,11.52,576,32,16,false,accent,'right');
  }
  return slide;
}
function references(slide) {
  txt(slide,'page-reference','[1] 室内環境ログ研究の入力資料（同梱教材・合成データ）, 2026.',48,443.52,864,34.56,12,false,gray);
  slide.speakerNotes.textFrame.setText('架空研究・合成データの教材。実測ではない。表紙・目次の素材枠は配置見本。\n[1] assets/example-source.org。番号は全ページ共通。この教材入力は実在論文ではない。');
}
function heading(slide, title, message) {
  txt(slide,'title',title,48,49.92,864,42,36,true);
  if (message) txt(slide,'message',message,48,96,864,57.6,30.667,true);
}

// 1. Type A cover: title band, two author bands, a clearly labelled photo slot.
{
  const s=base(1);
  txt(s,'venue','研究発表の視覚作例',48,32,850,40,24);
  txt(s,'topic','室内環境ログの記録間隔\n合成データを用いた予備検討',72,148.512,816,115.776,38.667,true,black,'center',key);
  txt(s,'affiliation','CPS LAB スタイル見本',72,314,510,48,24,false,black,'center','#999999');
  txt(s,'author','架空の発表者',72,384,510,48,24,false,black,'center','#999999');
  rect(s,'research-photo-slot',630,294,258,160,'#F3F5F1','#9AA09A',1);
  txt(s,'photo-slot-label','研究対象の写真枠\n写真は未同梱',640,337,238,74,24,false,gray,'center');
}
// 2. Type B cover: a static layout sample; no fabricated video is embedded.
{
  const s=pres.slides.add();s.background.fill='#37424A';
  txt(s,'venue','研究発表の視覚作例',48,29,864,38,24,false,'#FFFFFF','center');
  txt(s,'topic','室内環境ログの記録間隔\n合成データを用いた予備検討',60,142,840,120,40,true,'#FFFFFF','center');
  txt(s,'affiliation','CPS LAB スタイル見本',90,300,780,44,24,false,'#FFFFFF','center');
  txt(s,'author','架空の発表者',90,361,780,42,24,false,'#FFFFFF','center');
  txt(s,'media-placeholder','全面を動画・静止ポスターに置換する配置見本',48,450,864,34,24,false,'#FFFFFF','center');
  const pn=txt(s,'page','2',714.048,500.544,223.968,28.8,18.667,false,'#FFFFFF','right');
  pn.text.style={typeface:'Arial',fontSize:18.667,color:'#FFFFFF',alignment:'right',verticalAlignment:'middle',insets:{left:0,right:0,top:0,bottom:0}};
  s.speakerNotes.textFrame.setText('表紙タイプBの静止レイアウト見本。背景は素材枠で、動画も静止ポスターも未提供・未同梱。利用者の動画を指定された加工・無音・自動再生・ループ・次ページでの停止条件で埋め込む。対象アプリでの再生検証は別工程。本文のデザインは表紙タイプAを選んでも同じ。');
}
// 3. Four-chapter 2x2 contents. Slots show image placement, not fictional evidence.
{
  const s=base(3);heading(s,'目次','研究のねらい、しくみ、ここまでの結果、今後の展望');
  const items=[['01 研究のねらい','利用場面の画像枠'],['02 しくみと評価方法','手法・実機の画像枠'],['03 ここまでの結果','評価・結果図の画像枠'],['04 今後の展望','構想図の画像枠（計画）']];
  for(let i=0;i<items.length;i++){
    const x=48+(i%2)*456,y=169+Math.floor(i/2)*132;
    txt(s,`toc-label-${i}`,items[i][0],x,y,408,32,24,true);
    rect(s,`toc-image-slot-${i}`,x,y+38,408,74,'#F3F5F1','#B5BDB2',1);
    txt(s,`toc-image-label-${i}`,items[i][1],x+10,y+43,388,64,24,false,gray,'center');
  }
  rect(s,'toc-rule-vertical',480,164,1,265,'#D7DCD5');
  rect(s,'toc-rule-horizontal',48,295,864,1,'#D7DCD5');
}
// 4. Midterm divider: chapter and guide at the top, upper-right logo, white space.
{
  const s=base(4,true);
  rect(s,'upper-chapter-band',48,102,816,86.25,key);
  txt(s,'chapter','03  ここまでの結果',70.5,108.75,772.5,68.25,50.25,true);
  txt(s,'chapter-guide','合成データで確認したことと、残る課題',72,222,810,82.5,29.333);
}
// 5. Native editable diagram, showing an operation rather than a causal claim.
{
  const s=base(5);
  heading(s,'同じ入力の間引き','合成13点から、0・5・10分の3点を保持する [1]');
  txt(s,'all-label','1分間隔の入力',48,180,280,36,24,true);
  txt(s,'kept-label','5分間隔で保持',48,325,280,36,24,true);
  const start=340, step=42;
  for (let i=0;i<13;i++) {
    const x=start+i*step;
    const inputPoint=rect(s,`input-${i}`,x,198,18,18,'#666666','none',0,'ellipse');
    txt(s,`minute-${i}`,String(i),x-10,165,38,26,18.667,false,gray,'center');
    if(data[i].kept) {
      const retainedPoint=rect(s,`retained-${i}`,x-2,342,22,22,accent,black,1.2);
      s.shapes.connect(inputPoint,retainedPoint,
        {kind:'straight',fromSide:'bottom',toSide:'top',line:{fill:gray,width:1.2},tail:{type:'triangle',width:'sm',length:'sm'}});
    }
  }
  txt(s,'axis-unit','時刻 [分]',794,266,95,28,18.667,false,gray,'right');
  txt(s,'arrow-meaning','矢印は「保持する点」の対応',340,377,510,26,18.667,false,gray);
  references(s);
}
// 6. Native scatter chart with complete literal data and an embedded workbook.
{
  const s=base(6);
  heading(s,'この合成例では高い値が記録に残らない','5分間隔の保持点には、1000 ppmを超える値がない [1]');
  const chart=s.charts.add('scatter',{
    position:{left:46,top:165,width:652,height:242},
    series:[
      {name:'1分間隔 (小点)',xValues:data.map(d=>d.t),values:data.map(d=>d.v),fill:'#666666',line:{fill:'none',width:0},marker:{symbol:'circle',size:7}},
      {name:'5分間隔 (大点)',xValues:retained.map(d=>d.t),values:retained.map(d=>d.v),fill:accent,line:{fill:'none',width:0},marker:{symbol:'square',size:12}},
      {name:'1000 ppm',xValues:[0,12],values:[1000,1000],line:{fill:'#777777',width:1.4,style:'dashed'},marker:{symbol:'none'}},
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
  txt(s,'kept-max',`保持3点\n${maxKept} ppm`,724,335,190,74,25.333,true,accent);
  references(s);
}
// 7. Native table preserves units and scope without implying battery savings.
{
  const s=base(7);
  heading(s,'記録量と保持された値','保持点は13点から3点に減る [1]');
  const table=s.tables.add({rows:4,columns:3,left:48,top:174,width:864,height:228,
    columnWidths:[412,226,226],values:[['比較項目','1分間隔','5分間隔'],['保持点数',String(data.length),String(retained.length)],['保持最大値 [ppm]',String(maxAll),String(maxKept)],['1000 ppm超の記録点数',String(aboveAll),String(aboveKept)]]});
  table.borders.assign({fill:'#CCCCCC',width:1,style:'solid'});
  table.cells.block({row:0,column:0,rowCount:4,columnCount:3}).assign({textStyle:{typeface:font,fontSize:24,color:black},margins:{left:16,right:16,top:8,bottom:8},anchor:'center'});
  for(let r=0;r<4;r++)for(let c=0;c<3;c++){
    const cell=table.getCell(r,c);cell.fill=r===0?pale:'#FFFFFF';
    cell.text.style={typeface:font,fontSize:24,bold:r===0 || c===2,color:c===2?accent:black,alignment:c===0?'left':'center',verticalAlignment:'middle'};
  }
  references(s);
}
// 8. Summary: four flat rows in the same chapter order as the contents.
{
  const s=base(8);heading(s,'まとめ','記録点数と、残る変化を併せて確かめる [1]');
  const rows=[
    ['01 研究のねらい','記録点を減らすとき、短い変化が残るかを問う'],
    ['02 しくみと評価方法','同じ合成系列を、全13点と保持3点で比較した'],
    ['03 ここまでの結果','この例では、5分間隔の保持点に\n1000 ppmを超える値が残らなかった'],
    ['04 今後の展望','波形・開始時刻を変え、実機条件で確かめる計画'],
  ];
  rows.forEach(([label,body],i)=>{
    const y=170+i*64;
    txt(s,`summary-label-${i}`,label,48,y,279.75,58,24,true,accent);
    txt(s,`summary-body-${i}`,body,345.75,y,566.25,58,24,false);
    if(i<3)rect(s,`summary-rule-${i}`,48,y+60.5,864,1,'#D7DCD5');
  });
  references(s);
}


// 9. Physical final page: overview, authors and explicitly fictional contact.
{
  const s=base(9);
  txt(s,'final-title','室内環境ログの記録間隔\n合成データを用いた予備検討',48,64,864,94,34.667,true);
  txt(s,'final-author','架空の発表者 ／ CPS LAB スタイル見本',48,170,864,34,24);
  const takeaways=['問い：記録点を減らすとき、短い変化が残るか', '確認：この合成例では、保持3点に1000 ppm超の値が残らない [1]', '次の計画：波形・開始時刻と実機条件を変えて確かめる'];
  takeaways.forEach((t,i)=>txt(s,`takeaway-${i}`,t,48,225+i*55,864,48,24));
  txt(s,'contact','連絡先（架空教材の例）：presenter@example.org',48,407,864,30,24,true,accent);
  references(s);
}

const candidatePath=path.join(stage,'candidate.pptx');
const finalPath=path.join(out,'cps-layout-reference.pptx');
await (await PresentationFile.exportPptx(pres)).save(candidatePath);
await finalizePresentation({workspaceDir,candidatePath,finalPath,pythonExecutable:RUNTIME_PYTHON,
  integrityValidatorPath:path.join(PRESENTATIONS_SKILL_DIR,'container_tools/inspect_presentation_package_integrity.py'),
  layoutValidatorPath:path.join(PRESENTATIONS_SKILL_DIR,'container_tools/inspect_presentation_layout_geometry.py'),
  layoutArgs:['--expected-slide-size-emu','9144000,5143500','--validate-bullet-geometry','--validate-heading-fit','--require-native-table-slide','7'],
  explicitTotalSlideCount:9,requiredNativeTableOwnerSlides:[7],requiredNativeChartOwnerSlides:[6],materializeLiteralChartWorkbooks:true,
  fontPolicy:{basis:'design',families:[font,'Arial']},verifyArtifactToolImport:true,
  receiptPath:path.join(stage,'validation.json')});

// Keep oral qualifications beside the exported PPTX, mapped to its display pages.
const memoRows = [
  [1, '表紙タイプA', '室内環境ログの記録間隔／合成データを用いた予備検討', '架空研究・架空発表者のレイアウト教材です。写真枠は配置例で実証写真ではありません。'],
  [2, '表紙タイプB', '室内環境ログの記録間隔／合成データを用いた予備検討', '静止レイアウト教材です。動画は同梱していません。実案件では素材と再生条件を確認します。'],
  [3, '目次', '研究のねらい、しくみ、ここまでの結果、今後の展望', '画像枠は配置例です。実際の発表では各章の正本素材を使います。'],
  [5, '同じ入力の間引き', '合成13点から、0・5・10分の3点を保持する [1]', '開始時刻0分の合成系列1例で、間引き処理だけを確認しています。'],
  [6, 'この合成例では高い値が記録に残らない', '5分間隔の保持点には、1000 ppmを超える値がない [1]', '1000 ppmは教材用の任意閾値で、安全基準を表しません。波形や開始時刻を変えた場合、実環境の異常検出は未確認です。'],
  [7, '記録量と保持された値', '保持点は13点から3点に減る [1]', '合成データからの計算です。消費電力を測っていないため、省電力効果は確認していません。健康リスクも未評価です。'],
  [8, 'まとめ', '記録点数と、残る変化を併せて確かめる [1]', '今回の結果は合成系列1例に限られます。最適な記録間隔を実証したものではありません。実機条件の確認は次の計画です。'],
  [9, '最終サマリ', 'この合成例では、保持3点に1000 ppm超の値が残らない [1]', '連絡先は架空教材の例です。実案件では発表者の連絡先を確認します。結果の範囲と次の計画を区別して説明します。'],
];
const memo = '発表用メモ：CPSレイアウト見本\n対応PPTX：cps-layout-reference.pptx\nこの教材は架空研究・合成データによる9種類のレイアウト例です。\n\n' + memoRows.map(([page,title,claim,oral]) =>
  `表示ページ番号：${page}\nスライドID：SAMPLE-${String(page).padStart(2,'0')}\n題名：${title}\n画面の主張：${claim}\n口頭の補足・限定：${oral}\n範囲・条件・未確認：${page >= 5 ? '合成系列1例。実環境・消費電力・健康リスクは未評価。' : 'レイアウト教材。写真・動画は未同梱。'}\n根拠・出典：[1] assets/example-source.org（同梱教材）\n`
).join('\n');
await fs.writeFile(path.join(out,'cps-layout-reference-発表メモ.txt'), memo, 'utf8');

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
await sharp({create:{width:1480,height:880,channels:3,background:'#E5E5E5'}})
  .composite(thumbs.map((input,i)=>({input,left:10+(i%3)*490,top:10+Math.floor(i/3)*290})))
  .png().toFile(path.join(out,'contact-sheet.png'));
console.log(JSON.stringify({outputDirectory:out,slides:slides.length,validationReceipt:path.join(stage,'validation.json')},null,2));
