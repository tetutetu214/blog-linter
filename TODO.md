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
- [ ] ブログ執筆フロー: Vault に drafts/ 新設 → worklog/wiki から記事ドラフト生成 → lint → qiita-articles へ出力 → qiita-cli 投稿
- [ ] obsidian-qiita-s3 の再開（画像の S3+CloudFront 配信。ステージ0で停止中）
- [ ] textlint 併用の検討（日本語文章品質: preset-ja-technical-writing。今回は構造チェック優先で見送り）
