# TODO: ブログ記事リンター

## セットアップ
- [x] PLAN.md 作成
- [x] SPEC.md 作成
- [x] TODO.md 作成
- [ ] プロジェクト構成・依存関係セットアップ

## 実装
- [x] 機密情報チェッカー（secret_checker.py）※2026-07-11 test_article.md で10件検出を確認
- [x] 表記ブレチェッカー（notation_checker.py）※同上12件検出を確認
- [x] CLI（__main__.py）
- [x] AI 文体チェッカー（ai_writing_checker.py、textlint preset-ai-writing 統合）※2026-07-12 qiita プロファイルのみ
- [ ] Streamlit UI（app.py）※ファイルは存在、動作未検証

## Qiita API 連携
- [x] Qiita API クライアント（qiita_client.py）
- [x] post サブコマンド（機密情報検出時は投稿ブロック）
- [x] Streamlit 投稿UI（機密情報時は投稿無効化・デフォルト限定共有）
- [x] Qiita API クライアントのテスト（HTTP層モック）

## テスト・動作確認
- [x] テスト用Markdownで動作確認（2026-07-11、22件検出・exit 1）

## vault プロファイル（Obsidian Vault 対応、2026-07-11 着手）
- [x] タグ語彙ファイル新設（Vault 側 `.claude/tag-vocabulary.txt`、現行11語彙+bedrock/agentcore/cdk）
- [x] Vault CLAUDE.md のタグ節を正本ファイル参照に書き換え
- [x] kb-lint skill にステップ0（機械 lint）を追加
- [x] LintIssue を models.py へ分離（Codex 委譲）
- [x] frontmatter_checker.py — frontmatter・タグ語彙・命名・wikilink 検証（Codex 委譲＋Claude が sources ブロックリスト誤検知を修正）
- [x] profiles.py — qiita / vault のチェック組み合わせ定義（検収時に vault から notation を除外）
- [x] CLI 拡張 — check --profile vault --vault-root、ディレクトリ走査（Codex 委譲）
- [x] 実 Vault 全ファイルでの検収（pytest 30件 pass、実 Vault 指摘11件=全件本物、qiita regression なし）
- [ ] 実 Vault の残指摘11件の解消（wikilink 未記載の古い worklog 10件 + wiki/concepts 1件。次回 kb-lint セッションで対応）

## スコープ外（次回以降の候補）
<!-- 2026-08-25 blog プロファイル追加時の reviewer 指摘から TODO 送りした5件 -->
- [ ] linter.py の textlint 設定選択が `profile == "blog"` の文字列比較。ai_writing を含む第3プロファイル追加時に黙って qiita 設定へフォールバックする。config path を PROFILE_CHECKS 側に持たせる構造が素直
- [ ] notation_checker の粗さが blog フローに波及: YAML frontmatter の title 行と URL 内文字列（例: docs.aws.amazon.com/lambda/... の lambda）を誤検知し、同一箇所を2回重複出力する（コードブロック内は正しく除外。notation は警告扱いのため実害は限定的）
- [ ] `--profile blog` でディレクトリ一括 lint 不可（__main__.py のディレクトリ対応が vault 限定。content/posts/ 一括チェックに必要になったら対応）
- [ ] app.py（Streamlit UI）が profile 固定で blog を選べない
- [ ] ai_writing_checker が textlint の stderr を破棄し設定破損時の原因追跡が難しい（優先度低: 実 textlint を通す統合テスト導入で config 破損は CI 検出可能になった）
- [ ] ブログ執筆フロー: Vault に drafts/ 新設 → worklog/wiki から記事ドラフト生成 → lint → qiita-articles へ出力 → qiita-cli 投稿
- [ ] obsidian-qiita-s3 の再開（画像の S3+CloudFront 配信。ステージ0で停止中）
- [x] textlint 併用の検討（日本語文章品質: preset-ja-technical-writing）→ 2026-08-25 blog プロファイル新設で導入（blog-site 用。qiita/vault は従来設定のまま）

## マージ後に残った課題（2026-09-19、PR #5 マージ時点）
- [ ] 表記ブレ「Lambda → AWS Lambda」が実記事で 140 件出る。うち 46% が同一座標の完全重複（notation_checker.py:21 の 2 変種が両方 IGNORECASE で二重ヒット）。1 記事 1 回の集約か、blog プロファイルでの緩和を検討する
- [ ] blog-voice から回ってきた未実装ルール 4 件（~/.claude/skills/blog-voice/linter-candidates.md）: ニワトリの表記ゆれ / 非公式訳語の禁止（状態機械→ステートマシン）/ 節の冒頭が「まず、」/ 同一小節に「（出典:」3 回以上
- [ ] tests/test_blog_profile.py の一部がトートロジー（辞書リテラルの写し）または実装署名に密結合
- [ ] .mdx の連続 import 行が 1 段落に融合して sentence-length に当たる誤検知 1 件（JSX タグ行は誤検知 0 件）
- [ ] textlint の column は行内桁でなく文書内オフセット。表示が誤解を招く
