# todo — blog-linter

## 次の一手 <!-- next-move: 2026-09-21 -->
- Jev 文体判定の**記事単位の評価データを実装済み**（`experiments/jev_voice/build_article_dataset.py`、公開 5 記事 × 初稿/公開版、article 10 件 + section 53 件、テスト 15 件 pass）。生成物は .gitignore 済み
- **実測の結論: Jev はこの文体判定に使えない**（section 53 件で最良 accuracy 0.660、表層特徴 0.755 に負け、AUC 0.333 と逆向き）。評価データ側は物差しとして機能したので採用
- ⏳てつてつ: 残る未検証はペア比較（2 つ並べてどちらが LLM かを choice question で聞く形）。試すか、ここで打ち切るか
- 打ち切る場合: 旧 `build_dataset.py`（文単位・レビュー不採用）を残すか消すかを決めてから PR を作る。review-gate があるため reviewer を通す必要あり

タスク一覧の正本はリポジトリ直下の `TODO.md`（このファイルは briefing 用の次の一手のみ）。
