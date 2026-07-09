# SPEC: ブログ記事リンター

## 概要
Markdown形式のブログ記事に対して、機密情報の漏洩チェックと表記ブレチェックを行うツール。
Streamlit Web UIとPython CLIの両方で利用可能。

## 対象ユーザー
- ブログ記事（特にQiita）を公開前にチェックしたい技術者

## 技術スタック
- Python 3.x
- Streamlit（Web UI）
- CLI（argparse）

## 機能

### 1. 機密情報チェック
正規表現ベースで以下を検出する：
- AWSアクセスキーID（AKIA...）
- AWSシークレットアクセスキー（40文字の英数字+記号）
- AWSセッションキー
- AWSアカウントID（12桁数字）
- 汎用APIキー・トークン（api_key=xxx, token=xxx 等）
- GitHubトークン（ghp_, gho_, ghs_, ghr_）
- Slackトークン（xoxb-, xoxp-, xoxs-）
- 秘密鍵（-----BEGIN ... PRIVATE KEY-----）
- パスワードっぽい記述（password=xxx, passwd=xxx）
- IPアドレス（プライベートIP含む）
- データベース接続文字列

### 2. 表記ブレチェック
プリセットルールで以下を検出する：
- 長音記号の有無（サーバー/サーバ、ユーザー/ユーザ）
- 英語表記のブレ（例: GitHub/Github/github）
- AWS用語の表記統一（Lambda/lambda, EC2/ec2）
- 一般的なIT用語の表記統一

### 3. Web UI（Streamlit）
- テキストエリアにMarkdownを貼り付け or ファイルアップロード
- 「チェック」ボタンで実行
- 結果をカテゴリ別（機密情報/表記ブレ）に表示
- 問題箇所の行番号、該当テキスト、修正案を表示

### 4. CLI
- python -m blog_linter check ファイルパス で実行
- 結果をターミナルに表示
- 終了コード: 問題なし=0, 問題あり=1

### 5. Qiita連携
- qiita-articles リポジトリ（/home/tetutetu/qiita-articles/）のファイルを直接指定可能
- Streamlit UIからqiita-articlesのMarkdownファイルを一覧・選択可能

### 6. Qiita API 連携（新規投稿・更新、機密情報検出時は投稿ブロック、デフォルト限定共有）
- Qiita API v2 で記事を直接投稿・更新する（CLI の post サブコマンド / Streamlit UI）
- 投稿前に必ずリントし、機密情報が1件でも検出されたら投稿をブロックする
- デフォルトは限定共有（private=True）。一般公開は明示指定した場合のみ
- トークンは環境変数 QIITA_TOKEN または ~/.secrets/qiita.env から読み込む（値はログ出力しない）

## やらないこと
- 文法チェック（日本語の文法）
- 自動修正（提案のみ）
