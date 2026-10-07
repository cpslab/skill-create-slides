# 6配色の見本

標準6色を各1ページにした比較教材。白いベース、メイン色の帯と横線、独立アクセントの文字・面を同じ配置で示す。配色の正本は [cps-lab-style.md](cps-lab-style.md) の対応表で、生成コードはこの表からHEX値を読む。

- [編集可能な配色見本PPTX](../assets/palette-reference/cps-color-reference.pptx)
- [生成コード](../assets/palette-reference/build.mjs)

画像はネイティブな文字・図形で制作したPPTXを再読み込みして生成した表示確認用レンダー。ImageGenの完成イメージではなく、実案件の完成イメージレビューを代替しない。画像生成・編集は引き続きImageGen限定とする。

再生成は [視覚作例](visual-reference.md) と同じランタイム変数を設定し、空の `VISUAL_BUILD_DIR` を指定して実行する。

```sh
"$RUNTIME_NODE" "$RESEARCH_SLIDE_SKILL_DIR/assets/palette-reference/build.mjs"
```

出力先は `VISUAL_BUILD_DIR/output/`。候補と構造・配置検査の記録は `.build/`。配色変更時は正本の表を更新して再生成し、READMEの色コードと画像、manifestを揃える。PowerPoint本体での編集・再保存の検証とは区別する。
