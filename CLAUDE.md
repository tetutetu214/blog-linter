# blog-linter

Qiita 記事と Obsidian Vault ノートの公開前チェックを行う自作 linter（Python 3.12）。

## 構成

- `blog_linter/secret_checker.py` — 機密情報検出（正規表現、SECRET_PATTERNS）
- `blog_linter/notation_checker.py` — 表記ブレ検出（NOTATION_RULES）
- `blog_linter/qiita_client.py` — Qiita API v2 投稿・更新（機密検出時は投稿ブロック、デフォルト限定共有）
- `blog_linter/linter.py` — 統合層（lint_markdown）
- `blog_linter/__main__.py` — CLI（`python -m blog_linter check|post <file>`）
- `app.py` — Streamlit UI

## 規約

- 新規依存は原則追加しない（標準ライブラリ優先。既存実装の方針に従う）
- コードコメント・メッセージは日本語
- テストは pytest。test name は「振る舞い」で書く / 1 テスト = 1 目的 / トートロジー・空 assertion 禁止

## 関連する外部ファイル

- タグ語彙の正本: `/mnt/c/Users/lemon/Vault/.claude/tag-vocabulary.txt`（1行1タグ、`#` コメント可）
- Vault の書き手ルール: `/mnt/c/Users/lemon/Vault/CLAUDE.md`
- Qiita トークン: `~/.secrets/qiita.env`（中身を画面に出さない）
