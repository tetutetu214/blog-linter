# todo — blog-linter

## 次の一手 <!-- next-move: 2026-09-21 -->
- Jev 文体判定の**記事単位の評価データを実装済み**（`experiments/jev_voice/build_article_dataset.py`、公開 5 記事 × 初稿/公開版、article 10 件 + section 53 件、テスト 15 件 pass）。生成物は .gitignore 済み
- ⏳てつてつ: `experiments/jev_voice/article_dataset_report.md` を見て、この評価セットで測ることに納得できるか判断する。特に section 粒度の最良表層特徴 0.755（多数派ベースライン 0.604）を許容するか
- 判断後: 旧 `build_dataset.py`（文単位・レビュー不採用）を残すか消すかを決めてから PR を作る。review-gate があるため reviewer を通す必要あり

タスク一覧の正本はリポジトリ直下の `TODO.md`（このファイルは briefing 用の次の一手のみ）。
