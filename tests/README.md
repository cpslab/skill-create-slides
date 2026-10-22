# 合成fixtureによる回帰試験

```bash
uv run --frozen python -m unittest discover -s tests -v
uv run --frozen node --test tests/test_*.mjs
```

構造・配置のfixtureはPython標準ライブラリを使う。公開経路の描画試験にはPyMuPDFとPillow、生成試験にはnpm依存も使う。fixtureは実研究に由来しない最小OOXMLで、表示品質の見本ではない。ページ番号の重複・欠落、画面外配置、本文1 pt、出典サイズの役割差、表の非ネイティブ置換、チャートキャッシュの系列名と改変値、許可済み重なり、未解決継承・グループ、ページ挿入後の番号、重要条件、最終ファイルと全ページ画像の対応、旧構造検査のCLI互換性を確認する。

生成側の対応表とPPTXが同時に誤っていても、独立入力の数値・表セル・必須文・図の接続が異なれば不合格にする。明示した設定・入力・対応表のファイルが存在しない場合も、既定値へ黙って戻らず失敗する。

`test_init_presentation.py` はMarkdownの制作記録を初期化し、既存の `workflow.md`・`workflow.org` とリンクを保護して二重作成しないことを確認する。

構造検査では、XML要素名が正常でも `xsi:type="prefix:Type"` の値に未宣言の接頭辞が残る不具合も検出する。名前空間の有効範囲を要素ごとに扱い、子や兄弟の宣言で誤って合格にしない。接続線は `forward`・`backward`・`both`・`none` の両端を調べ、意図しない逆向きの矢印も検出する。

ページ挿入試験は検査器が古い番号を検出する試験であり、生成器による目次・メモ更新の実行証拠とは区別する。表示レビューやアプリ操作をこのfixtureの合格で置き換えない。

## 実装したCLI

- `scripts/extract_reference.py INPUT.pptx --output-dir DIR` は `reference-inventory.json`、`reference-style.md`、`slide-catalog.md` を作る。画像のレンダーは行わず未検証として記録する。抽出には本文・表セル・ノート・チャートキャッシュ・画像寸法と切り抜き・関係・明示書式が含まれる。グループ変換、マスター等からの未解決書式を推測値で埋めない。
- `scripts/check_layout.py INPUT.pptx --profile PROFILE.json --deck-spec INPUT.json --layout INPUT.layout.json --report REPORT.json` は役割・位置・番号・文字・入力一致・ネイティブ要素を調べる。`--layout` 省略時は同名の `.layout.json` を探す。終了値は確実な不具合が1、判断待ち・未検証だけなら2、機械検査の範囲内に問題がなければ0。これは最終完成判定ではない。
- `scripts/check_memo.py INPUT.pptx --deck-spec INPUT.json --report MEMO.json` は同じディレクトリの発表メモと、PPTX内ノート・独立入力を照合する。明示した既存メモは `--memo` で指定できる。形式・番号・ID・題名・主張・補足・根拠とhashを記録し、意味は判断待ちとして残す。
- `scripts/quality_gate.py INPUT.pptx --layout-report REPORT.json --deck-spec INPUT.json --memo-report MEMO.json --visual-review VISUAL.json --report GATE.json` は構造検査・配置結果・メモ・全ページ確認を最終ファイルに照合する。メモレポートは現物から再検査し、省略や古い記録の流用を検出する。必須の不具合・未解決・未検証があれば終了値1、記録の照合が全て通れば0。アプリ操作の未検証は別欄にも残る。

図形の識別は `role:<role>|id:<id>` 形式の名前を使う。任意の図形名から本文などを推測しない。`bounds_in` は `[x,y,width,height]`、インチ単位。

## 生成側の対応表

```json
{
  "schema_version": 1,
  "pptx_sha256": "最終PPTXのSHA-256",
  "slides": [{
    "number": 1,
    "id": "question",
    "required_text": ["入力からの必須文"],
    "notes_required": ["入力からの補足"],
    "expected_elements": [{
      "id": "title", "role": "title", "kind": "shape",
      "text": "入力からの必須文", "bounds_in": [0.5, 0.68, 7.55, 0.43]
    }],
    "allowed_overlaps": []
  }]
}
```

表は要素に `table: {rows: [["見出し", "値"]]}`、チャートは `chart: {categories: [...], series: [{name: "...", values: [...]}]}`、接続線は `edge: {from: "node-a", to: "node-b", direction: "forward"}` を持つ。接続先はPPTX内部の実IDへ照合する。素材の `asset.sha256` があれば埋め込みデータと照合する。

独立した入力の `slides[].required_text`・`sources`・`notes`・`semantic_claims` も照合する。意味項目の例は `{text, source, status, unit, subject, aggregation, denominator, period, visible_condition}`。`status` は `measured`、`illustrative`、`hypothesis`、`plan`、`reported`、`interpretation`。`unit` 以降は必要なときだけ画面に残す文字列として指定する。重要な条件をノートだけへ移すと、画面の文字照合は不合格になる。機械による文字一致は研究判断を代替しない。`test_quality_conditions.py` は部分集団の分母・期間・対象の欠落と不正な型を検出し、数値のない計画へ数値項目を要求しないことを確認する。

配布作例の `question`・`premise`・`message`・`blocks`・`steps`・`conditions`・`takeaways`、表の `table.rows`、チャートの `chart.categories` と `chart.series`、図の `diagram.nodes` と `diagram.edges` は独立入力から直接照合する。生成側の対応表だけを正解とは扱わない。未対応の入力形式では明示的な `required_text`・`semantic_claims` と個別の資料照合を加える。

## 目視記録

```json
{
  "pptx_sha256": "最終PPTXのSHA-256",
  "deck_spec_sha256": "独立入力ファイルのSHA-256",
  "pages": [{
    "number": 1,
    "image": "rendered/slide-01.png",
    "image_sha256": "実際に確認した画像のSHA-256",
    "status": "pass",
    "reviewer": "実際の確認者または方法",
    "notes": "実際に確認した文字・図表・切れ・条件と結果"
  }],
  "resolved_findings": [{
    "id": "配置レポートのfinding ID",
    "status": "pass",
    "reason": "解決と判断できた理由",
    "method": "実施した確認方法",
    "evidence": "元入力・画像・実アプリ結果の所在"
  }],
  "application_checks": {"required": false, "status": "unverified", "reason": "実操作は未実施"}
}
```

`pages` は全ページを1回ずつ含める。`image` の相対パスは目視記録ファイルの場所を基準にする。自動検出された `error` は目視の解消記録で無効化できず、生成元を修正して再検査する。未対応のグループや継承、画像文字、チャートの意味等は別の実確認があれば、その対象・方法・証拠を記録して判断する。実際に未確認のものを一括で解消済みにしない。品質ゲートはレビュー記録とファイルの整合を検査するもので、記録内容が真実であることまでは自動証明しない。

メモのfindingを解消する記録には、その記録ごとに現行の `memo_sha256` と `deck_spec_sha256` も付ける。`test_memo.py` は欠落・ページ対応・外部メモとPPTX内ノートの不一致・旧レポート・手修正後の再レビュー・検査出力による原本上書きの拒否を確認する。新しい利用者承認工程を設ける試験ではない。

空のchart/axis `c:title`は、対象アプリが既定の軸名を表示するため検出する。タイトル要素がない無題軸は許可し、明示的な空タイトルと区別する合成fixtureを含む。

## 公開バックエンドの確認

`test_portable.mjs` はCodex用のランタイム環境変数を外し、公開npm依存だけで架空入力からPPTXを書き出す。表セル・チャート系列・編集可能要素・接続先と矢印・負方向の線・元入力との一致・既存成果物の上書き拒否を確認する。未実装チャートを黙って置き換えず失敗することも確認する。

表紙タイプBの画像トリミング・元バイト保持、未対応画像の明示拒否、副生成物のリンク拒否と発表メモの追記保持も試験する。[1.6.0の実機検証結果](../references/portable-validation.md)には、mock試験から独立したレンダー・個別目視・クライアント実行の範囲を記載している。

新規の発表メモはMarkdownで出力し、旧TXTメモがある場合はその形式と追記を保持する。両形式の併存時は正本を決めずに生成を進めない。Markdownの特殊文字を含む入力でも、題名・補足・出典を本文として保持することを検査する。

従来の `notes` 文字列と任意の `{text, evidence, preparation}` を共通に正規化する。発話補足・詳細根拠をPPTX内ノートと外部メモへ出力し、制作TODOは作業先の `production-checks.md` だけへ出す。自動生成範囲の手修正や前回hash不明を検出した場合は原本と正式PPTXを更新せず、作業先へ比較用候補を残す。自動範囲外の追記は再生成後も保持する。

再生成対象には [英語の計画研究](../assets/plan-reference/input.json)、[図表を含む架空研究](../assets/workshop-reference/input.json)、[日本語中間発表](../assets/portable-reference/midterm-input.json) がある。[再生成と検査](../references/generation.md) の公開経路で実行する。固定入力の内部試験なので本人レビューを実施したとは記録しない。レンダーのmock試験、実際のLibreOffice出力、全ページの個別確認、クライアントを使った制作は別の証拠である。

## 1.7.3の文体確認

2026-10-22に、独立したエージェントへスキルと [架空の文体入力3件](writing-style-cases.md) を渡し、既存文面の直接改稿を確認した。現在の指定と古いメモリの優先順位、メモリ参照不可、AI草案と本人の表現の区別、条件・人数・計画の保持、引用内の命令の非実行を確認した。出力例と確認範囲は同ファイルに記録している。実研究の制作レビューではなく、本人の了承は記録していない。

配布検査と制作記録初期化の既存試験11件、skill-creatorの構文検査が成功した。スクリプトと作例PPTXは変更していない。各クライアントからの実メモリ取得、本人による自然さの評価、PPTX生成後の改行・表示は今回の試験では未検証。

## 1.7.1の確認記録

Python120件・Node.js28件が成功。DrawingML anchor、presentationの順序・重複、Content Typeの不在・重複、2Dグラフの過剰軸参照、マスターのテーマ共有を独立に検出する。修復側では正常な3D・複合グラフや独立テーマを保持し、原本・未変更部品の保全、追加テーマのZIP格納、名前衝突回避、再適用時の無変更を確認する。

PowerPoint出力の試験では、正常open・変更なし・全スライド読取の応答を必須とし、枚数だけの旧応答や不完全な読取を拒否する。mockとは別に、実際のPowerPoint 16.111で再生成3件・全28ページの修復なしopenと表示を確認した。[環境・hash・実施範囲](../references/compatibility-validation.md)

## 1.7.0の確認記録

後続の互換性調査で、このときの生成物にも不正な表anchorが残っていたことが判明した。以下は当時の検査範囲での結果であり、PowerPointで修復なしに開けることを証明していない。1.7.1で生成器と検出範囲を修正した。

2026-10-22にPython回帰試験83件、Node.js回帰試験27件を実行し、全件成功した。skill-creatorの構文検査、配布ファイル・相対リンク・manifestの照合も成功した。

英語の計画研究のコピーへ、計画ページの構造化メモ（発話補足・詳細根拠・制作TODO）と計画の主張を加え、公開バックエンドで7ページを生成した。LibreOfficeDev 26.8.0.0.alpha0による最終PPTXのPDF書出しとPyMuPDF 1.28.2によるPNGを全ページ個別に確認した。番号・目次・改行・表セル・計画の限定・メモとの意味対応を照合し、構造・配置・メモ・目視記録を束ねた品質ゲートは合格した。PPTXのSHA-256は `23eafedab8faa0e901680a87077d8b72020ce75b60885d55fbd34e611ff6fb79`。配布作例のPPTXや画像は差し替えていない。

これは架空の固定入力による内部試験であり、使用者の制作レビューではない。今回の版ではCodex専用バックエンドの実生成、PowerPoint本体での編集・再生、Claude Code・OpenCodeクライアントでの完走を追加検証していない。
