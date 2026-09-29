# CPS LABの視覚作例を使う

この6枚は、**架空研究・合成データによるレイアウトの見本**。推奨する発表枚数・章構成ではない。[通し作例](worked-example.md) は表紙＋本編4枚の短時間発表例であり、この6種類のレイアウト集とは用途が異なる。

- [編集可能なPPTX](../assets/visual-reference/cps-layout-reference.pptx)
- [全体一覧PNG](../assets/visual-reference/contact-sheet.png)
- [根拠となる合成入力表](../assets/example-source.org)
- [再生成コード](../assets/visual-reference/build.mjs)

## 比較するポイント

| ページ | 種類 | 合わせる見た目・編集性 |
|---|---|---|
| [1](../assets/visual-reference/slide-1.png) | 表紙 | 題目帯、所属と発表者の帯、余白、共通フッター。題目が主役になる文字階層 |
| [2](../assets/visual-reference/slide-2.png) | 章扉 | 下寄りの章名帯、右上ロゴ。通常ページの下端線と左下ロゴを重複させない |
| [3](../assets/visual-reference/slide-3.png) | 模式図 | 上部の話題・メッセージ、下部の主図、点と矢印の対応、個別編集できる図形と文字 |
| [4](../assets/visual-reference/slide-4.png) | 定量図 | 共通軸、単位、系列の区別、結果の短い表示、条件注記。データを持つネイティブ散布図 |
| [5](../assets/visual-reference/slide-5.png) | 比較表 | 読めるセル文字、単位、控えめな罫線、同じ項目での比較。ネイティブ表 |
| [6](../assets/visual-reference/slide-6.png) | まとめ | 今回の知見と次の計画を分け、最後に主要メッセージを短く置く |

ページの画像だけで比較せず、PPTXのテキスト・図形・表・チャートを選択して編集可能性も確かめる。図表の形式や本文量が今回の研究に合わない場合は、同じ読み順と文字階層を保って調整する。合成数値・架空発表者・教材注記は自分の研究内容へ置き換える。

CPSの作例では960×540 px（10×5.625 inch）のキャンバスを使う。これは16:9の幾何を実装するための値。文字サイズのpxとptは区別する（96 px = 72 pt）。別サイズへ移す場合は位置・寸法・文字階層を整合させる。色を変更する場合は6色の対応表と文字色を使い、図表の意味まで変えない。

## 作例で検証する範囲

PPTX構造、ネイティブチャートと表、合成入力との数値対応、書き出し後の再読み込み、全6枚の画像表示を確認する。初回利用時には、自分の発表用アプリでも開いて確認する。画像レンダーで表示できることと、そのアプリでの編集・印刷・再生確認は別に記録する。

2026-09-29の同梱作例では、最終PPTXを再読み込みした全6枚を目視し、パッケージ検査とチャートの埋込数値を照合した。PowerPoint本体での編集・再保存は未検証。

今回使用したPNG描画エンジンでは、散布図の四角点が丸、破線が実線として表示される。PPTX内部には指定した形状と線種が残っている。作例は点の大きさと凡例も併用して条件を区別する。各メンバーの発表用アプリでの表示を別に確認する。配布版とファイルの対応は [パッケージ記録](../package-manifest.json) を参照する。

## 作例を再生成するとき

通常の利用に再生成は不要。スタイル実装の確認・改訂時に使う。現行 `Presentations` スキルと `load_workspace_dependencies` で必要な環境を確認し、実際の絶対パスを次に設定する。

| 変数 | 内容 |
|---|---|
| `RUNTIME_NODE` | 同梱Node.jsの実行ファイル |
| `RUNTIME_NODE_MODULES` | `@oai/artifact-tool` と `sharp` がある同梱パッケージディレクトリ |
| `RUNTIME_PYTHON` | 同梱Pythonの実行ファイル |
| `PRESENTATIONS_SKILL_DIR` | 現在利用するPresentationsスキルのディレクトリ |
| `VISUAL_BUILD_DIR` | 新しい作業用ディレクトリ。既存納品物を含めない |
| `RESEARCH_SLIDE_SKILL_DIR` | この研究発表スキルのディレクトリ |

現行Presentationsの制作開始・実装手順に従ったうえで実行する。

```bash
"$RUNTIME_NODE" "$RESEARCH_SLIDE_SKILL_DIR/assets/visual-reference/build.mjs"
```

出力は `VISUAL_BUILD_DIR/output/`、候補と検証記録は同ディレクトリ内の `.build/`。同じ納品名が既にある作業先へ上書きしない。コードはスキル内の合成入力表を読むため、フォルダ構成を維持する。実案件の制作コードとして使う場合は、固定されている6枚の構成や合成値の検査も含めて意図的に変更する。
