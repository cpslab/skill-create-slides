# 研究発表スライド制作スキル

現在のスキル版は **1.8.0** です。研究資料があるフォルダでエージェントを起動して、「research-presentation-slides スキルを使って、学会の10分発表を作ってください」のように依頼できます。[制作手順](SKILL.md) · [初回の依頼例](references/sharing.md#最初の依頼例)

## 導入

このフォルダにスキル本体、素材、スクリプト、依存定義が入っています。PPTXを生成するには、ここで `npm ci` と `uv sync --frozen --python 3.12` を実行します。レンダー用のアプリ・フォントの準備と動作確認は[詳しい導入手順](references/installation.md)を参照してください。

## 更新について

取得に使った方法に合わせて[更新手順](references/installation.md#更新について)を選んでください。配布ファイルのサイズとSHA-256は[配布マニフェスト](package-manifest.json)に記録しています。
