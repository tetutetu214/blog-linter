"""CLI エントリーポイント: python -m blog_linter check|post <file>"""
import argparse
import sys
from pathlib import Path
from blog_linter.linter import lint_markdown, has_secret_issues
from blog_linter import qiita_client


def main():
    parser = argparse.ArgumentParser(
        description="ブログ記事リンター - 機密情報・表記ブレチェック"
    )
    subparsers = parser.add_subparsers(dest="command")

    check_parser = subparsers.add_parser("check", help="Markdownファイルをチェック")
    check_parser.add_argument("file", type=str, help="チェック対象のMarkdownファイルパス")

    post_parser = subparsers.add_parser("post", help="Markdownファイルを Qiita に投稿")
    post_parser.add_argument("file", type=str, help="投稿対象のMarkdownファイルパス")
    post_parser.add_argument("--title", type=str, default=None, help="記事タイトル（省略時は先頭H1）")
    post_parser.add_argument("--tags", type=str, default=None, help="タグ（カンマ区切り、必須）")
    post_parser.add_argument("--public", action="store_true", help="限定共有ではなく一般公開する")
    post_parser.add_argument("--tweet", action="store_true", help="投稿時にツイートする")
    post_parser.add_argument("--update", type=str, default=None, metavar="ITEM_ID",
                             help="指定した記事IDを更新する（省略時は新規投稿）")

    args = parser.parse_args()

    if args.command == "check":
        _run_check(args)
    elif args.command == "post":
        _run_post(args)
    else:
        parser.print_help()
        sys.exit(1)


def _run_check(args):
    filepath = Path(args.file)
    if not filepath.exists():
        print(f"エラー: ファイルが見つかりません: {filepath}")
        sys.exit(1)

    text = filepath.read_text(encoding="utf-8")
    issues = lint_markdown(text)

    if not issues:
        print("問題は見つかりませんでした。")
        sys.exit(0)

    secret_issues = [i for i in issues if i.category == "secret"]
    notation_issues = [i for i in issues if i.category == "notation"]

    if secret_issues:
        print(f"\n{'='*60}")
        print(f"  機密情報の検出: {len(secret_issues)} 件")
        print(f"{'='*60}")
        for issue in secret_issues:
            print(f"  L{issue.line_number}:{issue.column}  [{issue.rule_name}]")
            print(f"    {issue.message}")
            print(f"    → {issue.suggestion}")
            print()

    if notation_issues:
        print(f"\n{'='*60}")
        print(f"  表記ブレの検出: {len(notation_issues)} 件")
        print(f"{'='*60}")
        for issue in notation_issues:
            print(f"  L{issue.line_number}:{issue.column}  [{issue.rule_name}]")
            print(f"    {issue.message}")
            print()

    print(f"合計: {len(issues)} 件の問題が見つかりました。")
    sys.exit(1)


def _run_post(args):
    filepath = Path(args.file)
    if not filepath.exists():
        print(f"エラー: ファイルが見つかりません: {filepath}")
        sys.exit(1)

    text = filepath.read_text(encoding="utf-8")

    # 投稿前に必ずリントし、機密情報があれば投稿を中止する
    issues = lint_markdown(text)
    if has_secret_issues(issues):
        secret_issues = [i for i in issues if i.category == "secret"]
        print(f"\n{'='*60}")
        print(f"  機密情報の検出: {len(secret_issues)} 件")
        print(f"{'='*60}")
        for issue in secret_issues:
            print(f"  L{issue.line_number}:{issue.column}  [{issue.rule_name}]")
            print(f"    {issue.message}")
            print(f"    → {issue.suggestion}")
            print()
        print("機密情報が検出されたため投稿を中止しました")
        sys.exit(1)

    # 表記ブレのみの場合は警告表示のうえ投稿は続行する
    notation_issues = [i for i in issues if i.category == "notation"]
    if notation_issues:
        print(f"警告: 表記ブレが {len(notation_issues)} 件あります（投稿は続行します）")

    # タイトルの決定（--title 優先、無ければ先頭H1）
    title = args.title if args.title else qiita_client.extract_title(text)
    if not title:
        print("エラー: タイトルが必要です（--title で指定するか先頭に # 見出しを置いてください）")
        sys.exit(1)

    # タグの決定（カンマ区切り、必須）
    tags = []
    if args.tags:
        tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    if not tags:
        print("エラー: タグを最低1つ指定してください（--tags で指定）")
        sys.exit(1)

    private = not args.public
    token = qiita_client.load_token()

    if args.update:
        result = qiita_client.update_item(
            item_id=args.update,
            title=title,
            body=text,
            tags=tags,
            private=private,
            token=token,
        )
    else:
        result = qiita_client.post_item(
            title=title,
            body=text,
            tags=tags,
            private=private,
            tweet=args.tweet,
            token=token,
        )

    if result.ok:
        action = "更新" if args.update else "投稿"
        print(f"{action}に成功しました: {result.url}")
        sys.exit(0)

    print(f"エラー: 投稿に失敗しました: {result.error_message}")
    sys.exit(1)


if __name__ == "__main__":
    main()
