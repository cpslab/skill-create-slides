# 詳しい導入手順


以下は初めて使うメンバー向けの手順です。**スキルの取得 → ツールの導入 → 動作確認 → 自分の研究で制作**の順に進めます。PPTX生成には公開パッケージを使い、Codex専用の制作ライブラリを必要としません。利用するAIサービスの契約・ログインは別途必要です。

### 1. Git・Node.js・uvを用意する

既に使えるものは再インストールしません。所属先でNix等を使っている場合は、その管理方法でも構いません。

| ツール | 用途 | 導入方法 |
|---|---|---|
| GitHub CLI（gh） | `gh skill install` による取得 | この方法を使う場合は [GitHub CLI](https://cli.github.com/) を導入し、`gh skill install --help` で対応を確認する |
| Git | Gitでの取得・更新 | [公式導入ページ](https://git-scm.com/install/)でOSを選ぶ |
| Node.js | 編集可能なPPTXの生成・npxでの取得 | PPTX生成には20以上、`npx skills` も使う場合は22.20.0以上のサポート中LTSを用意する。[公式ダウンロード](https://nodejs.org/en/download) |
| uv | Pythonと検査・描画用ライブラリの管理 | [公式導入手順](https://docs.astral.sh/uv/getting-started/installation/)を使う。Pythonは後の `uv sync` で用意できる |

uvの公式インストーラーを使う例です。

macOS・Linux：

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Windows PowerShell：

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

インストール後はターミナルを開き直し、次を確認します。

```sh
git --version
node --version
npm --version
uv --version
```

### 2. スキルをGitHubから取得する

#### GitHub CLIで導入する

研究プロジェクトのGitリポジトリで次を実行し、画面で `research-presentation-slides` と使うエージェントを選びます。

```sh
gh skill install cpslab/skill-create-slides
```

ホームディレクトリなどから個人用に導入する場合は、`--scope user` を指定できます。次はCodexの例です。[GitHub CLIの導入オプション](https://cli.github.com/manual/gh_skill_install)

```sh
gh skill install cpslab/skill-create-slides research-presentation-slides --agent codex --scope user
```

手順4は、CLIが表示した導入先のスキルフォルダで実行します。

#### npx skills で導入する

macOS・Linux・Windowsとも、使いたい研究プロジェクトのフォルダで実行します。

```sh
npx skills add cpslab/skill-create-slides
```

表示されたエージェントから使うものを選びます。たとえばCodexだけに導入する場合は `--agent codex`、3つとも使う場合は `--agent codex claude-code opencode` を付けて指定できます。全プロジェクトで共通に使う個人用の導入には `-g` を付けます。[Skills CLIのオプション](https://github.com/vercel-labs/skills/blob/main/docs/commands.md#skills-add)

導入先はCLIの完了画面に表示されます。標準のプロジェクト配置では、次を実行すると手順4で使うスキルのフォルダへ移動できます。個人用に導入した場合は、完了画面のパスを使ってください。

```sh
cd .agents/skills/research-presentation-slides
```

#### Git・ZIPで手動導入する

リポジトリを普段コードを保管する場所にクローンし、その中の `skills/research-presentation-slides/` をエージェントのスキルフォルダへリンクします。以下は個人用の配置例です。すでに同名のスキルがある場合は[更新について](#更新について)を先に確認してください。

macOS・Linux：

```sh
mkdir -p "$HOME/src" "$HOME/.agents/skills"
git clone https://github.com/cpslab/skill-create-slides.git "$HOME/src/skill-create-slides"
ln -s "$HOME/src/skill-create-slides/skills/research-presentation-slides" "$HOME/.agents/skills/"
cd "$HOME/.agents/skills/research-presentation-slides"
```

Windows PowerShellでは次を使います。

```powershell
New-Item -ItemType Directory -Force "$HOME/src", "$HOME/.agents/skills" | Out-Null
git clone https://github.com/cpslab/skill-create-slides.git "$HOME/src/skill-create-slides"
New-Item -ItemType Junction -Path "$HOME/.agents/skills/research-presentation-slides" -Target "$HOME/src/skill-create-slides/skills/research-presentation-slides"
Set-Location "$HOME/.agents/skills/research-presentation-slides"
```

ZIPで取得する場合はGitHubの **Code → Download ZIP** から展開し、中の `skills/research-presentation-slides/` をフォルダごと `.agents/skills/` へコピーします。コピー先の `research-presentation-slides/` 直下に `SKILL.md`、`assets/`、依存定義、lockファイルが並びます。

版1.8.0には [yomiyasu の推敲手順](vendor/yomiyasu/revision.md) と [unslop を使った研究図の作り方](figure-design-unslop.md) が同梱されています。新しく設定するPCでも、この2つのガイドはスキル本体と一緒に使えます。yomiyasu 公式版のPython検査ツールも使いたい場合は、別途[公式版の導入手順](https://github.com/nanaism/yomiyasu#readme)に従ってください。

### 3. 利用するエージェントへ登録する

`gh skill install` または `npx skills` で導入すると、選んだエージェントへの登録も完了します。下表で呼び出し方を確認し、手順4へ進んでください。手動導入の場合は、下表とリンク作成の手順に従います。

| 利用環境 | 導入・ログイン | スキルの呼び出し |
|---|---|---|
| Codex | [公式案内](https://learn.chatgpt.com/docs/build-skills)に従ってCodexを用意する。上記 `.agents/skills` を認識する | `$research-presentation-slides` |
| OpenCode | [公式導入手順](https://opencode.ai/docs/)で使用する版を導入し、プロバイダーへ接続する。上記 `.agents/skills` を認識する | `research-presentation-slides スキルを読み込んでください` |
| Claude Code | [公式導入手順](https://code.claude.com/docs/en/setup)で導入し、`claude` を起動してログインする。手動導入の場合は下記のリンクを追加する | `/research-presentation-slides` |

<details>
<summary>OpenCode・Claude Codeをまだ導入していない場合</summary>

OpenCodeの公式手順にあるnpm版を使う例（OpenCode 1）：

```sh
npm install -g opencode-ai
opencode
```

起動後に `/connect` で利用するプロバイダーへ接続します。OpenCode 2を使う場合は [V2の導入案内](https://opencode.ai/v2/docs/) を使ってください。両版は既定で同じ `opencode` コマンドを使用するので、既に導入してある版を確認してから選びます。

Claude Codeの公式インストーラーを使う例（macOS・Linux）：

```sh
curl -fsSL https://claude.ai/install.sh | bash
claude
```

Windows PowerShell：

```powershell
irm https://claude.ai/install.ps1 | iex
claude
```

初回起動時の案内に従ってログインします。`Not logged in` と表示された場合は、Claude Code内の `/login` を実行します。インストーラーや対応OSの最新条件は表の公式ページを参照してください。

</details>

OpenCodeは `.agents/skills` と `.claude/skills` の両方を探索します。Claude Codeは個人用スキルを `.claude/skills` から読み、スキルフォルダへのシンボリックリンクも扱えます。[OpenCodeのスキル仕様](https://opencode.ai/docs/skills/)・[Claude Codeのスキル仕様](https://code.claude.com/docs/en/skills)

手動導入でClaude Codeを使う人は、同じスキル本体を参照するリンクを1回だけ作ります。**既存の同名スキルへ上書きしません。**

macOS・Linux：

```sh
mkdir -p "$HOME/.claude/skills"
ln -s "$HOME/.agents/skills/research-presentation-slides" \
  "$HOME/.claude/skills/research-presentation-slides"
```

Windows PowerShell（同じPC内のフォルダへジャンクションを作成）：

```powershell
New-Item -ItemType Directory -Force "$HOME/.claude/skills" | Out-Null
New-Item -ItemType Junction -Path "$HOME/.claude/skills/research-presentation-slides" -Target "$HOME/.agents/skills/research-presentation-slides"
```

Claude Codeだけを使う場合は、手順2でリンクまたはZIPのコピーを作る親フォルダを `.claude/skills/` に変更できます。登録後に新しいセッションを開き、スキルの読込み元と版を確認してください。

### 4. 生成・描画用ツールを入れる

スキルのフォルダで実行します。以下はmacOS・Linux・Windowsで共通です。

```sh
npm ci
uv sync --frozen --python 3.12
```

`package-lock.json` に従いPptxGenJS・sharpを、`uv.lock` に従いPyMuPDF・Pillowを導入します。利用者が使っているni等から同等のlock付き導入を行っても構いません。`node_modules/` と `.venv/` は各PCで作る実行環境で、他のPCへコピーする配布物には含めません。

続いて、PPTXをPDFへ書き出す **LibreOffice** と、日本語表示用の **Noto Sans JP** を入れます。

| OS | LibreOffice | Noto Sans JP |
|---|---|---|
| macOS | [公式ダウンロード](https://www.libreoffice.org/download/download-libreoffice/)でIntel／Apple Siliconを確認して選ぶ。DMGを開き、Applicationsへ移動する | [Google Fonts](https://fonts.google.com/noto/specimen/Noto+Sans+JP)から取得し、展開したフォントをFont Bookでインストールする |
| Windows | 同じ公式ページでOS・CPUに合うインストーラーを選び、画面の案内に従う | ダウンロードしたフォントを右クリックしてインストールする |
| Linux | ディストリビューションのパッケージ管理でLibreOfficeのImpressを含めて導入する | ダウンロードしたフォントをユーザーのフォントフォルダ等へ入れ、利用環境のフォントキャッシュを更新する |

LibreOfficeのOS別手順は[公式インストール案内](https://www.libreoffice.org/installation-instructions/)も参照してください。WindowsのWSLを使う場合は、Node・Python・LibreOffice・フォントもWSL内へ揃えます。Windows側だけへ入れたアプリがLinuxのコマンドとして使えるとは仮定しません。

macOSのPowerPointを既に利用している場合は、LibreOfficeの代わりに `--renderer powerpoint` を指定する経路もあります。後続の `doctor.py` と `render_portable.py` の両方へ指定してください。doctorで省略するとLibreOfficeを検査します。発表先がPowerPointなら、LibreOfficeでの静止表示確認に加えて発表先アプリで開き、動画・編集・スライドショーの動作を確認します。

### 5. 環境と画像制作機能を確認する

次はスキルのフォルダから実行します。記録は研究用フォルダへ保存し、パスは自分の保存先へ変更してください。

```sh
uv run --frozen python scripts/doctor.py --backend portable --strict \
  --report /path/to/my-research/presentation/environment.json
```

Windowsでも同じオプションを使えます。コマンドを1行で入力し、保存先を `"C:/Users/自分の名前/Documents/my-research/presentation/environment.json"` 等へ変更します。LibreOfficeを通常と異なる場所へ入れた場合は、環境変数 `SOFFICE` に実行ファイルの場所を設定できます。[詳細な生成・描画コマンド](generation.md#公開ツールで生成検証する標準)

**doctorは生成・描画の依存確認です。画像生成と画像閲覧は、選んだモデルと接続済みツールで実際に利用できるか別に確認します。** モデル名や契約名だけで利用可能と判断しません。画像生成サービスは固定せず、エージェントが利用できる機能を選びます。生成が必要な画像の用途・参照素材・寸法・品質・実物との違いを渡し、出力画像を確認します。追加サービスの契約・料金や外部送信が必要な場合は、その機能の利用条件を確認します。

画像生成や画像閲覧が利用できない場合は不足を明示し、対応モデル・ツールを用意して再開します。必要な画像を作れない状態を、完成イメージのレビュー済みや全ページ確認済みとして扱いません。

### 6. 架空作例で生成から描画まで試す

スキルのフォルダで実行します。以下はMac/Linuxの例です。`SLIDE_TRIAL_DIR` はスキルとは別の、新しい作業フォルダにしてください。WindowsではPowerShellの `$SlideTrialDir` に同じ用途のパスを設定して各コマンドを1行で実行できます。

```sh
SLIDE_TRIAL_DIR="$HOME/Documents/slide-skill-trial"

uv run --frozen node scripts/build_deck.mjs --backend portable \
  --input assets/plan-reference/input.json --work-dir "$SLIDE_TRIAL_DIR" \
  --output "$SLIDE_TRIAL_DIR/output/plan-v1.pptx"

uv run --frozen python scripts/render_portable.py \
  --input "$SLIDE_TRIAL_DIR/output/plan-v1.pptx" \
  --output-dir "$SLIDE_TRIAL_DIR/render-v1" --renderer libreoffice

uv run --frozen python scripts/check_pptx.py "$SLIDE_TRIAL_DIR/output/plan-v1.pptx" \
  --expect-slides 7 --report "$SLIDE_TRIAL_DIR/structure-v1.json"

uv run --frozen python scripts/check_layout.py "$SLIDE_TRIAL_DIR/output/plan-v1.pptx" \
  --profile assets/profiles/cps-workshop.json --deck-spec assets/plan-reference/input.json \
  --report "$SLIDE_TRIAL_DIR/layout-v1.json"
```

これは固定入力の内部試験で、利用者レビューや新規画像生成は行いません。既存の出力は上書きしないため、再試行では `plan-v2.pptx`・`render-v2` など新しい名前を使います。PPTX・発表メモ・配置対応表、全ページPNG・一覧・hash付き描画記録が作成されます。PNGを1枚ずつ開いて表示を確認してください。配置検査の終了値2は要確認事項が残る状態です。個別確認と[最終品質判定](generation.md#個別目視と最終判定)まで行って、初めて検証済みと記録します。

## 更新について

手元でスキルを編集した場合は差分を保存してから、導入に使った方法で更新してください。

- **GitHub CLI** で導入した場合は `gh skill update research-presentation-slides` を実行します。プロジェクト用ならそのプロジェクト内で実行してください。[GitHub CLIの更新手順](https://cli.github.com/manual/gh_skill_update)
- **npx skills** で導入した場合は、プロジェクト内で `npx skills update research-presentation-slides -p` を実行します。個人用は `-p` を `-g` に替えます。[Skills CLIの更新手順](https://github.com/vercel-labs/skills/blob/main/docs/commands.md#skills-update)
- **Git** でクローンし、スキルのサブフォルダへリンクした場合は、クローン先で `git pull --ff-only` を実行します。以前の手順で `.agents/skills/research-presentation-slides/` 等にリポジトリを直接クローンした場合は、初回のみクローン全体をスキルの探索外（例：`~/src/skill-create-slides/`）に移してから更新します。手順2のリンク作成を行い、元の導入先から新しい `skills/research-presentation-slides/` を参照できるようにしてください。
- **ZIP** で取得した場合は、旧版をスキルの探索外に移し、新しいZIPから手順2と同じフォルダをコピーします。

更新後はスキルフォルダで `npm ci` と `uv sync --frozen --python 3.12` を実行し、新しいセッションで読込み元と版を確認してください。

