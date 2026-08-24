# knowledge.md — blog-linter

## 学習済み概念

- 2026-07-10 プロファイル抽象: チェッカー群は共通部品のまま、対象（Qiita記事 / Vaultノート）ごとに「どのチェックをどう掛けるか」の組み合わせだけを切り替える仕組み — 理解度テスト合格
- 2026-07-10 textlint 不採用の代償: preset-ja-technical-writing の成熟した日本語校正ルール群（文長・ら抜き・二重否定）を捨てた。必要になれば後から併用可能 — 理解度テスト合格
- 2026-07-10 タグ語彙固定の理由: 自由付与だと表記ゆれでタグ検索・集約の信頼性が壊れる。「先に語彙へ1行追加」の手間と引き換えに信頼性を守る — 理解度テスト合格

- 2026-07-11 後方互換の設計（--profile 省略時は qiita デフォルトで既存挙動を壊さない）— 理解度テスト合格（PR直前）
- 2026-07-11 vault から表記ブレを外した観測駆動の判断（実測185件ノイズ、表記統一は記事化時に qiita で）— 理解度テスト合格（PR直前）
- 2026-07-11 遅延 import の目的（check を dotenv 非依存にして週次 kb-lint を素の python3 で回す）— 理解度テスト合格（PR直前）
- 2026-07-12 textlint のルール/プリセット機構（本体は検査ロジックを持たず npm ルールを .textlintrc で有効化、プリセットは詰め合わせで個別 on/off 可）/ 形態素解析ルールは Python 移植不可のため subprocess 統合を選定 / 未インストール環境は検出スキップ＋明示報告 — 理解度テスト合格

## 決定事項

- 2026-07-12 **textlint を採用（方針転換）**。2026-07-10 の不採用判断は preset-ja-technical-writing が対象。今回は @textlint-ja/textlint-rule-preset-ai-writing（AI文体検出、kuromoji 形態素解析依存で Python 移植不可）のための採用で、当時想定した「必要になれば後から併用」に該当。Node.js 依存が増えるが未導入環境では graceful degradation でスキップする

- 2026-07-11 **vault プロファイルから notation（表記ブレ）を除外**。実 Vault 検収で表記ブレ185件がノイズ化（過去の内部ノートに「Amazon DynamoDB」フル表記を強制する形になる）。vault の関心は機密混入防止と構造の健全性に絞り、表記統一は記事化時に qiita プロファイルで掛ける分業とした（観測駆動の判断）
- 2026-07-11 frontmatter パーサのブロックリスト対応は tags 限定だと sources で誤検知する（premise-check.md で実測）。値が空のキーはすべてブロックリスト開始とみなす実装に修正

- 2026-07-10 vault プロファイルを追加。タグ語彙の正本は Vault 側 `/mnt/c/Users/lemon/Vault/.claude/tag-vocabulary.txt`（プレーンテキスト採用。PyYAML 依存を増やさないため）
- 2026-07-10 `raw/` は人間専用領域のため lint 対象外。`.obsidian/` `.claude/` も走査除外
- 2026-07-10 ブログ執筆フロー（Vault drafts/ → 記事生成 → qiita 投稿）と obsidian-qiita-s3 再開は今回スコープ外（TODO.md に記載）

- 2026-08-25 **blog プロファイル新設（blog-site 用）で preset-ja-technical-writing を導入**。checks は ("secrets", "ai_writing")。notation は Qiita 表記規約用、frontmatter は blog-site 側の Astro zod スキーマが fail-closed で担うため含めない。textlint 設定は既存 .textlintrc.json（qiita）と新設 .textlintrc.blog.json（ai-writing + ja-technical-writing）で分離し、qiita/vault の挙動は不変（検証: blog 設定で sentence-length / max-ten 検出、qiita 設定で同ファイル指摘ゼロ）。実装は Codex（gpt-5.6-sol）、依存は textlint-rule-preset-ja-technical-writing@12.0.2
