# 共通部品による再生成と検査

通常の制作では、研究資料を読み、企画書・アウトライン・完成イメージの必要なレビューを済ませる。以下は承認済み構成をPPTXへ実装する手順。固定入力による開発内部試験では、固定した内容とレビュー対象外の理由を記録し、利用者の了承を捏造しない。

## 正本と入出力

研究の正本は利用者の資料、編集する構成正本は `slide-structure.org`。そこから照合して作ったJSONを生成入力とし、元Orgの版を制作記録へ残す。JSONをOrgとは別の内容正本として編集し続けない。修正を生成入力へ加えるときは構成正本にも戻し、主張や順序が変わる場合は必要なレビューを受け直す。機械入力の自動変換がないことを、自動同期済みと説明しない。

| 分担 | ファイル・処理 |
|---|---|
| 研究入力と構成 | 当該作業先の資料、Org、生成用JSON。題目・著者・出典・素材は毎回ここから取得 |
| 共通の視覚仕様 | [cps-midterm.json](../assets/profiles/cps-midterm.json)、[cps-workshop.json](../assets/profiles/cps-workshop.json)、[配色正本](cps-lab-style.md) |
| レイアウト部品 | [cps.mjs](../assets/layouts/cps.mjs)。研究固有の既定値を持たない |
| 生成 | [build_deck.mjs](../scripts/build_deck.mjs)。入力JSONからPPTX・配置対応表・発表メモを出力 |
| 描画 | [render_deck.mjs](../scripts/render_deck.mjs)。保存済みPPTXを再読み込みして全ページPNGと一覧を作る |
| 検査 | 構造・配置・目視記録を別に持ち、[quality_gate.py](../scripts/quality_gate.py) で最終ファイルへ結び付ける |

JSONは `schema_version: 1`、`profile`、`metadata`、`structure`、`slides` を持つ。`metadata` の `title`、`short_title`、`authors` は必須。`contact`、`venue` 等は今回の入力にある場合だけ記入する。架空教材なら `fictional_label` で明示する。

任意の `style.palette` には `botanica`、`iris`、`kimera`、`orange`、`sicilia`、`bordeaux`、または配色正本の色名（ボタニカ等）を指定できる。省略時はプロファイルの既定配色。`style.FOOTER_LINE` は選択済みの `on`／`off` を渡し、`style.font` は今回採用したフォントを指定する。配色値を各ページへ手入力せず、正本の色対応から生成する。

`structure.sections` は `id`、`title`、任意の `description` を持つ章の配列。`slides` は表示順に並べ、各ページに一意の `id`、`type`、`title`、必要な `section` と型別の内容を記す。`sources`、`notes`、主張と根拠を結ぶ `semantic_claims` も各ページに置く。番号と章のページ範囲は生成器が派生させる。目次・採用する章扉・サマリ・補足も独立したページ項目とする。

2×2目次では各章へ任意の `image: {"path": "concept.png", "alt": "概念図の説明"}` と `image_label: "計画"` を指定できる。画像がない章は章名・ページ範囲・説明で示し、空の画像枠を生成しない。画像ラベルと説明は画像外へ置く。`cps-midterm` の章扉は `section` から目次と同じ番号・章名を取り、案内文は `guide`、未指定なら `message`、さらに未指定なら章の `description` を使う。通常本文と表紙の配置はこの指定で変わらない。

型別の入力は [レイアウト選択](layout-patterns.md) と共通部品の実装に従う。既存の表やチャートを画像へ置き換えず、正確な図はノードと接続を入力する。素材の相対パスは入力JSONの場所から解決される。

表の `widths` は列幅（inch）で合計を表全幅へ合わせる。任意の `heights` は各行の正の高さで、行数と要素数を揃え、合計を表全高へ合わせる（許容差0.02 inch）。`padding_in` の `left`・`right`・`top`・`bottom` は非負のセル内余白。指定がない辺は既定値を使う。文字を縮小する前に列幅・行高・余白と改行を調整する。

`cover_type: "type-b"` は提供済みの `poster: {"path": "poster.png"}` を必須とし、`video: {"path": "background.mp4", "autoplay": true, "loop": true, "muted": true}` があれば、そのMP4をポスターへ結び付けて埋め込む。パスは入力JSONからの相対パス。3つの再生設定を省略した場合は `true` とする。静止ポスターだけの見本と、動画を埋め込んだ成果物を区別する。

動画は既に利用者が準備したMP4を使い、生成器は変換・切り抜き・速度変更を行わない。バイト列とSHA-256を保持し、ネイティブのメディア関係、自動開始または動画クリック開始、ループ、消音の設定を保存する。対応は新規候補の役割ID付きポスターに限定し、既存の再生タイミングがあるページへの合成は受け付けない。MP4のヘッダー確認だけではコーデック互換性を証明しない。H.264等の形式、白文字の読みやすさ、再生・ページ遷移時の停止・操作バーの動作は対象アプリで検証するまで `unverified` とする。候補ごとの `media.json` に埋込結果とこの未検証状態を記録する。

## 環境を確認する

Pythonの構造・配置検査は標準ライブラリを基本とする。生成・描画はNode.js、利用可能な `@oai/artifact-tool` と `sharp`、生成の最終処理には現行PresentationsのhelperとPythonを使う。パッケージが一般公開のnpmから必ず取得できるとは仮定しない。

利用環境の依存解決手段を使い、次の実パスを確認して設定する。個人のパスや特定キャッシュ版を配布物へ記入しない。

| 環境変数 | 設定するもの |
|---|---|
| `RUNTIME_NODE` | 使用するNode.js実行ファイル |
| `RUNTIME_NODE_MODULES` | `@oai/artifact-tool` と `sharp` を含む `node_modules` |
| `RUNTIME_PYTHON` | 最終処理で使用するPython実行ファイル |
| `PRESENTATIONS_SKILL_DIR` | 現行Presentationsスキルのディレクトリ |

`runtime.mjs` は `RUNTIME_NODE_MODULES` の代わりに `CODEX_PRIMARY_RUNTIME_NODE_MODULES` も読める。検証のため明示的な値へ揃えてよい。uv、ni、Nix等は各利用者の環境管理方針に従う。これらを全メンバーの必須設定にはしない。

```sh
python3 scripts/doctor.py --report /path/to/work/environment.json
```

uv運用の環境なら `python3` の代わりに `uv run --no-project` を使える。doctorの依存importとフォントファイルの存在は、実際に使用されたフォントや対象アプリでの表示・再生を証明しない。生成に必要な能力がなければ依存しない入力整理・検査を進め、不足を記録する。

## 生成、描画、検査

リポジトリのルートで実行する例。`/path/to/work` は利用者の作業先へ置き換える。実研究の出力・素材・分析は配布元へ置かない。

```sh
"$RUNTIME_NODE" scripts/build_deck.mjs \
  --input /path/to/work/deck.json \
  --work-dir /path/to/work \
  --output /path/to/work/output/deck-v1.pptx

"$RUNTIME_NODE" scripts/render_deck.mjs \
  --input /path/to/work/output/deck-v1.pptx \
  --output-dir /path/to/work/render-v1

python3 scripts/check_pptx.py /path/to/work/output/deck-v1.pptx \
  --report /path/to/work/structure-v1.json

python3 scripts/check_layout.py /path/to/work/output/deck-v1.pptx \
  --profile assets/profiles/cps-workshop.json \
  --deck-spec /path/to/work/deck.json \
  --report /path/to/work/layout-v1.json
```

`--work-dir` で私的な作業先を明示し、最終PPTXはその配下の独立した出力ディレクトリへ保存する。作業先直下へのPPTX保存や、作業先外へ向く出力先・シンボリックリンクは受け付けない。候補と検証receiptは作業先の `.build/` に実行ごとの一意なディレクトリを作り、最終成果物と分離する。

既存PPTXは上書きしない。新しい版名で生成し、最終処理が失敗した場合は `.build/` 内の候補を調べる。成功時はPPTXと同じディレクトリに `.layout.json`、`-発表メモ.txt` ができる。発表メモの自動生成範囲外の利用者追記は保つ。既存メモを別版へ引き継ぐ場合も内容を照合して保持する。

レンダーは全ページ画像、`contact-sheet.png`、PPTXと画像のhashを持つ `render-record.json` を出力する。各ページの初期状態は `unverified`。一覧生成だけで目視合格へ書き換えない。ImageGenの完成イメージと、この検証用レンダーは別の成果物。

`--renderer` を省略すると `artifact-tool` を使う。macOSでPowerPointとPopplerの `pdftocairo` を利用できる場合は、次の経路で保存済みPPTXをPDFへ書き出して描画できる。新しい出力ディレクトリを使い、`pdftocairo` がPATHにない場合は `PDFTOCAIRO` に実行ファイルを指定する。

```sh
"$RUNTIME_NODE" scripts/render_deck.mjs \
  --input /path/to/work/output/deck-v1.pptx \
  --output-dir /path/to/work/render-powerpoint-v1 \
  --renderer powerpoint
```

この経路は [render_powerpoint.applescript](../scripts/render_powerpoint.applescript) によるPowerPointのPDF書出しとPoppler CairoのPNG変換を使い、今回の共通ランタイム依存も引き続き必要。macOS以外では利用できず、利用可能な描画手段で検証する。`render-record.json` には実際に使った描画エンジンとPowerPointの版を残す。PDF書出しは静止表示の検証であり、個々の図表の編集操作や動画再生の検証とは分ける。

対象アプリが既に書き出したPDFを使う場合は、次の経路を使える。`PPTX_SHA256` には書出し元PPTXの実際のSHA-256を設定する。

```sh
"$RUNTIME_NODE" scripts/render_deck.mjs \
  --input /path/to/work/output/deck-v1.pptx \
  --output-dir /path/to/work/render-pdf-v1 \
  --renderer pdf \
  --pdf /path/to/work/application-export.pdf \
  --pdf-source-sha256 "$PPTX_SHA256"
```

この引数照合だけではPDFの由来を証明できない。実際の書出し操作のログ、対象アプリの版、書出し元PPTX・PDFのhashを保存し、目視記録から参照する。ログのないPDFを「最終PPTXの対象アプリ表示」として合格証拠にしない。

1.5.0の最終表示検証には、実際に成功したPowerPoint 16.111のPDF書出しと `pdftocairo` の経路を使った。画像全体の読み取りで文字やロゴ等が欠けたように見えた箇所は、同一PNGの該当領域を拡大・切り出して再確認し、画素や文字抽出も照合する。今回の疑義は元画像内の保持を確認して訂正した。画像の見落としから描画エンジンの不具合を断定しない。PPTX・PDF・PNGの対応を記録し、別環境や他のPPTXに同じ結果を保証しない。

初期候補ではコアプロパティXMLのQName不正を修正した。初期のアプリ応答待ちには、その候補の修復モードと短いタイムアウトが混在していた。別の書出し待機ではアクセス許可ダイアログが表示され、利用者による承認後にPDFが作成された。タイムアウトだけからファイル破損や反復書出しの不具合と断定しない。今回の最終候補では従来教材9枚・再構成21枚・架空作例10枚・計画作例7枚の4件で、同じhelperによる開封・PDF書出し・閉じる処理の正常終了を確認した。この実行範囲を記録し、任意の環境での安定性へ一般化しない。

生成時の [normalise_generated.py](../scripts/normalise_generated.py) は、既定段落書式と属性・子要素が完全一致する冗長なレベルを整理し、異なるフォント・段落書式は保持する。表示不具合を修正する効果は、この処理の実行だけでは証明しない。最終ファイルを実際に描画して確かめ、利用者が手修正したデッキへの一律適用はしない。

配置検査の終了値は0＝所定の機械検査で指摘なし、1＝error、2＝review_required／unverifiedが残る状態。構造検査の終了値0も完成品質の証明ではない。継承、回転・入れ子グループ、図中文字等の未対応解析をpassとして扱わない。

## 個別目視と最終判定

最終PPTXからの全ページPNGを1枚ずつ開き、文字欠け、語中改行、語尾だけの行、意図しない重なり、表・グラフ・図ラベル、出典、条件、ページ番号を確認する。必要なら入力や部品を修正し、別版を生成して描画・検査をやり直す。

目視記録JSONには最終PPTXの `pptx_sha256` と、全ページの `number`、`image`、`image_sha256`、`status`、`reviewer`、具体的な `notes` を記す。レンダー記録の `image_sha256` と対応させる。確認したページだけ `status: "pass"` とし、氏名を推測せず確認主体と方法を記す。

配置検査の要確認項目を解消する場合は `resolved_findings` にその `id`、`status`、`reason`、`method`、`evidence` を記す。機械検査のerrorを理由文だけで免除しない。動画・対象アプリの実操作を要求する場合は `application_checks` に実施環境と結果を記録し、未操作をpassにしない。

```sh
python3 scripts/quality_gate.py /path/to/work/output/deck-v1.pptx \
  --layout-report /path/to/work/layout-v1.json \
  --visual-review /path/to/work/visual-review-v1.json \
  --report /path/to/work/quality-v1.json

python3 -m unittest discover -s tests
"$RUNTIME_NODE" --test tests/test_generator.mjs
```

品質ゲートは記録とファイルの対応を検査する。レビュー文の真偽や研究内容の妥当性を自動証明しない。[Q1〜Q11](quality-standard.md#最終受入の11項目)は別に全項目を判定する。再生成の成功、全ページ目視、研究・使用者からの独立性、対象アプリの実動作を相互の代替にしない。

## 同梱の短い研究発表を再生成する

以下は固定した架空教材の内部試験。新しい実研究の承認記録には使わない。既存の配布PPTXを上書きせず、作業先の新しい版名へ生成する。

```sh
"$RUNTIME_NODE" scripts/build_deck.mjs \
  --input assets/workshop-reference/input.json \
  --work-dir /path/to/work \
  --output /path/to/work/output/workshop-reference-v1.pptx

"$RUNTIME_NODE" scripts/build_deck.mjs \
  --input assets/plan-reference/input.json \
  --work-dir /path/to/work \
  --output /path/to/work/output/plan-reference-v1.pptx
```

生成後は前節と同じ描画・構造・配置・個別目視・品質ゲートを実行する。既存の `validation.json` は配布済みファイルに対する記録で、新しく生成したPPTXの合格記録には流用しない。

| 研究資料 | 構成・レイアウト入力 | 狙いと説明の範囲 | 配布成果物と証拠 |
|---|---|---|---|
| [workshop-reference/research-source.org](../assets/workshop-reference/research-source.org) | [workshop-reference/input.json](../assets/workshop-reference/input.json) | 10枚、3章。短い問い、比較表、生成した概念素材・UI、分岐、1合成系列の比較、次の計画。実機や実測の成果を主張しない | [PPTX](../assets/workshop-reference/workshop-reference.pptx)、[一覧](../assets/workshop-reference/contact-sheet.png)、[検証記録](../assets/workshop-reference/validation.json) |
| [plan-reference/research-source.org](../assets/plan-reference/research-source.org) | [plan-reference/input.json](../assets/plan-reference/input.json) | 7枚、2章。未記録の意味を区別する概念と質的研究計画。装置・UI・定量結果を入力にも出力にも要求しない | [PPTX](../assets/plan-reference/plan-reference.pptx)、[一覧](../assets/plan-reference/contact-sheet.png)、[検証記録](../assets/plan-reference/validation.json) |

この2作例の `research-source.org` は、今回の既存固定JSONにある研究上の事実・計画・全合成値・集約単位・架空発表者・素材区分を相互照合して整理した教材資料。JSONより前に存在した元論文や実験記録ではない。研究内容はOrgで、ページ順・章・部品型・座標はJSONで確認できるよう分離している。今回JSONは変更せず、生成は従来どおりJSONを読む。Orgからの自動変換・自動同期や、研究資料だけから独立して構成した検証を実施済みとは扱わない。

枚数と章数は各作例の入力による値であり、短い研究発表の必須値ではない。著者名と `example.org` の連絡先は架空入力。画像は同梱概念素材であり、実物・実装・実測の証拠ではない。従来型の9枚教材は [visual-reference.md](visual-reference.md) の専用再生成手順を保持する。

生成素材の用途・寸法・hashと再生成時の扱いは [来歴](../assets/workshop-reference/media/provenance.md) を参照する。

## 配布物を確認・更新する

```sh
python3 scripts/check_package.py --report /path/to/work/package-check.json
```

[check_package.py](../scripts/check_package.py) は、配布対象の欠落・追加、manifestのbytes/SHA-256、SKILL・README・manifestの版、Markdown／Orgの相対リンク、Markdownの見出しアンカー、ローカルES module importを確認する。UTF-8ファイルとPPTX内XML／relsの個人ホームへの絶対パスも検出する。特定の研究名や著者名を禁止語にせず、研究の独立性は別に入力と照合する。

配布対象はルートの `AGENTS.md`・`README.md`・`SKILL.md` と、`agents`・`assets`・`references`・`scripts`・`tests` の対応拡張子。隠しファイル／ディレクトリ、`__pycache__`、`node_modules`、manifest自身はhash一覧から除く。シンボリックリンクを配布ファイルとして追跡しない。検査レポートは配布ディレクトリの外へ保存する。

全成果物が揃った後、明示的に一覧を更新する。

```sh
python3 scripts/check_package.py --refresh --report /path/to/work/package-check-final.json
```

`--refresh` はSKILLとREADMEの版一致、リンクと可搬性の検査が通った場合だけ、manifestの `version` と `files` を実ファイルから更新する。`packaged_on`、過去の作例検証、その他のメタデータは保持し、検証日や合格結果を作らない。新しい実施記録は実際の検証後に別途追記する。終了値0はこの配布整合検査の合格、1は問題ありで、スライドの意味・目視・動作・独立性の合格を含まない。

## 参照PPTXの調査

```sh
python3 scripts/extract_reference.py /path/to/reference.pptx \
  --output-dir /path/to/private-audit/reference
```

抽出は `reference-inventory.json`、`reference-style.md`、`slide-catalog.md` を作る。画像は別途 `render_deck.mjs` で最終PPTXから描画する。レイアウト名だけでページ役割を決めず、観測値・採用規則・参照固有の内容を分ける。未解決の継承や変換は推測値で埋めない。実研究の抽出物を配布物や通常生成の依存先へ加えない。
