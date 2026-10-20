# 合成fixtureによる回帰試験

```bash
uv run --no-project python -m unittest discover -s tests -v
```

Python標準ライブラリのみを使う。fixtureは実研究に由来しない最小OOXMLで、表示品質の見本ではない。ページ番号の重複・欠落、画面外配置、本文1 pt、出典サイズの役割差、表の非ネイティブ置換、チャートキャッシュの系列名と改変値、許可済み重なり、未解決継承・グループ、ページ挿入後の番号、重要条件、最終ファイルと全ページ画像の対応、旧構造検査のCLI互換性を確認する。

生成側の対応表とPPTXが同時に誤っていても、独立入力の数値・表セル・必須文・図の接続が異なれば不合格にする。明示した設定・入力・対応表のファイルが存在しない場合も、既定値へ黙って戻らず失敗する。

構造検査では、XML要素名が正常でも `xsi:type="prefix:Type"` の値に未宣言の接頭辞が残る不具合も検出する。名前空間の有効範囲を要素ごとに扱い、子や兄弟の宣言で誤って合格にしない。接続線は `forward`・`backward`・`both`・`none` の両端を調べ、意図しない逆向きの矢印も検出する。

ページ挿入試験は検査器が古い番号を検出する試験であり、生成器による目次・メモ更新の実行証拠とは区別する。表示レビューやアプリ操作をこのfixtureの合格で置き換えない。

## 実装したCLI

- `scripts/extract_reference.py INPUT.pptx --output-dir DIR` は `reference-inventory.json`、`reference-style.md`、`slide-catalog.md` を作る。画像のレンダーは行わず未検証として記録する。抽出には本文・表セル・ノート・チャートキャッシュ・画像寸法と切り抜き・関係・明示書式が含まれる。グループ変換、マスター等からの未解決書式を推測値で埋めない。
- `scripts/check_layout.py INPUT.pptx --profile PROFILE.json --deck-spec INPUT.json --layout INPUT.layout.json --report REPORT.json` は役割・位置・番号・文字・入力一致・ネイティブ要素を調べる。`--layout` 省略時は同名の `.layout.json` を探す。終了値は確実な不具合が1、判断待ち・未検証だけなら2、機械検査の範囲内に問題がなければ0。これは最終完成判定ではない。
- `scripts/quality_gate.py INPUT.pptx --layout-report REPORT.json --visual-review VISUAL.json --report GATE.json` は構造検査・配置結果・全ページ確認を最終PPTXのSHA-256で照合する。必須の不具合・未解決・未検証があれば終了値1、記録の照合が全て通れば0。アプリ操作の未検証は別欄にも残る。

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

独立した入力の `slides[].required_text`・`sources`・`notes`・`semantic_claims` も照合する。意味項目の例は `{text, source, status, unit, subject, aggregation, visible_condition}`。`status` は `measured`、`illustrative`、`hypothesis`、`plan`、`reported`、`interpretation`。後ろ4つの属性は必要なときだけ指定する。重要な条件をノートだけへ移すと、画面の文字照合は不合格になる。機械による文字一致は研究判断を代替しない。

配布作例の `question`・`premise`・`message`・`blocks`・`steps`・`conditions`・`takeaways`、表の `table.rows`、チャートの `chart.categories` と `chart.series`、図の `diagram.nodes` と `diagram.edges` は独立入力から直接照合する。生成側の対応表だけを正解とは扱わない。未対応の入力形式では明示的な `required_text`・`semantic_claims` と個別の資料照合を加える。

## 目視記録

```json
{
  "pptx_sha256": "最終PPTXのSHA-256",
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

空のchart/axis `c:title`は、対象アプリが既定の軸名を表示するため検出する。タイトル要素がない無題軸は許可し、明示的な空タイトルと区別する合成fixtureを含む。
