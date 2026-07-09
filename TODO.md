# TODO: ブログ記事リンター

## セットアップ
- [x] PLAN.md 作成
- [x] SPEC.md 作成
- [x] TODO.md 作成
- [ ] プロジェクト構成・依存関係セットアップ

## 実装
- [ ] 機密情報チェッカー（secret_checker.py）
- [ ] 表記ブレチェッカー（notation_checker.py）
- [ ] CLI（__main__.py）
- [ ] Streamlit UI（app.py）

## Qiita API 連携
- [x] Qiita API クライアント（qiita_client.py）
- [x] post サブコマンド（機密情報検出時は投稿ブロック）
- [x] Streamlit 投稿UI（機密情報時は投稿無効化・デフォルト限定共有）
- [x] Qiita API クライアントのテスト（HTTP層モック）

## テスト・動作確認
- [ ] テスト用Markdownで動作確認
