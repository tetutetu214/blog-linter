from unittest.mock import patch

from blog_linter.ai_writing_checker import (
    BLOG_TEXTLINT_CONFIG,
    TEXTLINT_CONFIG,
)
from blog_linter.linter import lint_markdown
from blog_linter.notation_checker import check_notation
from blog_linter.profiles import get_profile_checks


def _blog_rule_issues(text, rule_name):
    with patch("blog_linter.linter.check_ai_writing", return_value=[]):
        issues = lint_markdown(text, profile="blog")
    return [issue for issue in issues if issue.rule_name == rule_name]


def test_blogプロファイルは機密情報と表記ブレとAI文体をチェックする():
    assert get_profile_checks("blog") == (
        "secrets",
        "notation",
        "ai_writing",
        "blog_style",
        "blog_structure",
    )


def test_blogプロファイルはblog用textlint設定を渡す(tmp_path):
    article = tmp_path / "article.md"

    with patch("blog_linter.linter.check_ai_writing", return_value=[]) as checker:
        lint_markdown("本文", profile="blog", file_path=article)

    checker.assert_called_once_with(
        article,
        config_path=BLOG_TEXTLINT_CONFIG,
    )


def test_blogプロファイルは80字を超える一文を指摘する(tmp_path):
    article = tmp_path / "article.md"
    text = (
        "読者が迷わず内容を理解できるように、前提と手順と結果を一つずつ"
        "順序立てて説明し、必要な補足情報も省略せず具体的に記載することで、"
        "技術記事全体の読みやすさと正確さを高めます。"
    )
    assert 80 < len(text) < 100
    article.write_text(text, encoding="utf-8")

    issues = lint_markdown(text, profile="blog", file_path=article)

    assert any(issue.rule_name == "sentence-length" for issue in issues)


def test_拡張子がmdxでも80字を超える一文を指摘する(tmp_path):
    """textlint は .md 以外を無言でスキップするため、ブログ記事の .mdx で偽クリーンになっていた"""
    article = tmp_path / "article.mdx"
    text = (
        "読者が迷わず内容を理解できるように、前提と手順と結果を一つずつ"
        "順序立てて説明し、必要な補足情報も省略せず具体的に記載することで、"
        "技術記事全体の読みやすさと正確さを高めます。"
    )
    article.write_text(text, encoding="utf-8")

    issues = lint_markdown(text, profile="blog", file_path=article)

    assert any(issue.rule_name == "sentence-length" for issue in issues)


def test_同じ本文なら拡張子がmdでもmdxでも同じ件数を指摘する(tmp_path):
    text = (
        "読者が迷わず内容を理解できるように、前提と手順と結果を一つずつ"
        "順序立てて説明し、必要な補足情報も省略せず具体的に記載することで、"
        "技術記事全体の読みやすさと正確さを高めます。"
    )
    counts = []
    for name in ("article.md", "article.mdx"):
        article = tmp_path / name
        article.write_text(text, encoding="utf-8")
        issues = lint_markdown(text, profile="blog", file_path=article)
        counts.append(len([i for i in issues if i.category == "ai_writing"]))

    assert counts[0] == counts[1]
    assert counts[0] > 0


def test_qiitaプロファイルは従来のtextlint設定を渡す(tmp_path):
    article = tmp_path / "article.md"

    with patch("blog_linter.linter.check_ai_writing", return_value=[]) as checker:
        lint_markdown("本文", profile="qiita", file_path=article)

    checker.assert_called_once_with(
        article,
        config_path=TEXTLINT_CONFIG,
    )


def test_qiitaプロファイルは長音符号のある表記を引き続き推奨する():
    with patch("blog_linter.linter.check_ai_writing", return_value=[]):
        issues = lint_markdown("サーバを使います。", profile="qiita")

    assert any(
        issue.matched_text == "サーバ" and issue.suggestion == "サーバー"
        for issue in issues
    )


def test_blogプロファイルはブランド名eufyの小文字表記を指摘する():
    issues = _blog_rule_issues("eufy を使います。", "brand-capitalization")

    assert [issue.suggestion for issue in issues] == ["Eufy"]


def test_blogプロファイルはEufyとURLとライブラリ名を指摘しない():
    text = (
        "Eufy を使います。\n"
        "https://example.com/eufy/device を参照します。\n"
        "eufy-security-client を導入します。"
    )

    assert _blog_rule_issues(text, "brand-capitalization") == []


def test_URLとMarkdownリンク先の表記ブレはどのプロファイルでも指摘しない():
    text = (
        "https://docs.aws.amazon.com/lambda/latest/dg/lambda-nodejs.html\n"
        "[クライアント](https://github.com/bropat/eufy-security-client)"
    )

    for profile in ("qiita", "blog"):
        issues = check_notation(text, profile=profile)

        assert not any(
            issue.rule_name in {"表記ブレ: Node.js", "表記ブレ: GitHub"}
            for issue in issues
        )


def test_blogプロファイルはにわとりと鶏を指摘する():
    issues = _blog_rule_issues("にわとりと鶏を飼います。", "chicken-notation")

    assert [issue.matched_text for issue in issues] == ["にわとり", "鶏"]


def test_blogプロファイルはニワトリを指摘しない():
    assert _blog_rule_issues("ニワトリを飼います。", "chicken-notation") == []


def test_blogプロファイルは非公式訳語を指摘する():
    issues = _blog_rule_issues("状態機械を実装します。", "unofficial-translation")

    assert [issue.suggestion for issue in issues] == ["ステートマシン"]


def test_blogプロファイルは公式の用語を指摘しない():
    assert _blog_rule_issues(
        "ステートマシンを実装します。",
        "unofficial-translation",
    ) == []


def test_blogプロファイルは用語を並べるスラッシュ表記を指摘する():
    issues = _blog_rule_issues(
        "OS/ランタイムを選択します。",
        "slash-coordination",
    )

    assert [issue.matched_text for issue in issues] == ["OS/ランタイム"]


def test_blogプロファイルはURLとパスと日付のスラッシュを指摘しない():
    text = (
        "https://example.com/OS/runtime を参照します。\n"
        "src/components/Button.tsx を開きます。\n"
        "/usr/local/bin に置きます。\n"
        "2026/09/22 に実施します。"
    )

    assert _blog_rule_issues(text, "slash-coordination") == []


def test_blogプロファイルは英数字と日本語の直接隣接を指摘する():
    text = "EC2における SSH不可の 15分間で 1つの例を示します。"

    issues = _blog_rule_issues(text, "alnum-japanese-spacing")

    assert {issue.matched_text for issue in issues} == {
        "2に",
        "H不",
        "5分",
        "1つ",
    }


def test_blogプロファイルはMarkdown記号とURLの境界を指摘しない():
    text = "# 見出し\n- 項目\n1. 手順\nhttps://example.com/日本語"

    assert _blog_rule_issues(text, "alnum-japanese-spacing") == []


def test_blogプロファイルは開くべき漢字を指摘する():
    text = "実行出来ます。その事が出来るのは確認の為です。"

    issues = _blog_rule_issues(text, "open-kanji")

    assert {issue.suggestion for issue in issues} == {
        "できます",
        "ことができる",
        "のため",
    }


def test_blogプロファイルは開いた表記を指摘しない():
    text = "実行できます。そのことができるのは確認のためです。"

    assert _blog_rule_issues(text, "open-kanji") == []


def test_blogプロファイルは多数派と異なる文体だけを指摘する():
    text = "設定します。\n確認します。\nこの方法である。"

    issues = _blog_rule_issues(text, "style-mixing")

    assert [issue.matched_text for issue in issues] == ["である。"]


def test_blogプロファイルは旧textlint文体ルールに頼らない(tmp_path):
    article = tmp_path / "article.md"
    text = "設定します。\n確認します。\nこの方法である。"
    article.write_text(text, encoding="utf-8")

    issues = lint_markdown(text, profile="blog", file_path=article)

    assert any(issue.rule_name == "style-mixing" for issue in issues)
    assert not any(
        issue.rule_name == "no-mix-dearu-desumasu"
        for issue in issues
    )


def test_blogプロファイルは見出しと表と箇条書きの体言止めを指摘しない():
    text = (
        "# 概要\n\n"
        "| 項目 | 設定 |\n"
        "| --- | --- |\n"
        "- **注意事項**\n\n"
        "設定します。\n確認します。"
    )

    assert _blog_rule_issues(text, "style-mixing") == []


def test_blogプロファイルは閉じ括弧後の読点で文をつなぐ表現を指摘する():
    text = "毎秒一回実行します（通常のペース）、これを超えると停止します。"

    issues = _blog_rule_issues(text, "comma-sentence-join")

    assert [issue.matched_text for issue in issues] == ["）、これ"]


def test_blogプロファイルは括弧付きの列挙を指摘しない():
    text = "構成要素（推奨）、環境変数（任意）を確認します。"

    assert _blog_rule_issues(text, "comma-sentence-join") == []


def test_blogプロファイルは見出し直後のまずで始まる段落を指摘する():
    text = "## 手順\n\nまず、設定ファイルを開きます。"

    issues = _blog_rule_issues(text, "section-opening-mazu")

    assert [issue.line_number for issue in issues] == [3]


def test_blogプロファイルは見出し直後でないまずを指摘しない():
    text = "## 手順\n前提を確認します。\n\nまず、ファイルを開きます。"

    assert _blog_rule_issues(text, "section-opening-mazu") == []


def test_blogプロファイルは同一小節の出典表記3回以上を指摘する():
    text = (
        "## 根拠\n"
        "一つ目（出典: A）\n"
        "二つ目（出典: B）\n"
        "三つ目（出典: C）"
    )

    issues = _blog_rule_issues(text, "citation-density")

    assert [issue.line_number for issue in issues] == [1]


def test_blogプロファイルは出典表記が小節ごと2回以下なら指摘しない():
    text = (
        "## 根拠A\n"
        "一つ目（出典: A）\n"
        "二つ目（出典: B）\n"
        "## 根拠B\n"
        "三つ目（出典: C）\n"
        "四つ目（出典: D）"
    )

    assert _blog_rule_issues(text, "citation-density") == []


def test_blogプロファイルはAWSサービスの未宣言の初出略称だけを指摘する():
    text = (
        "Lambda を使います。Lambda で処理します。\n"
        "S3 に保存します。S3 から読みます。\n"
        "EC2 を起動します。EC2 を停止します。"
    )

    issues = _blog_rule_issues(text, "aws-first-mention")

    assert [issue.matched_text for issue in issues] == ["Lambda", "S3", "EC2"]


def test_blogプロファイルは正式名と略称宣言のあるAWSサービスを指摘しない():
    text = (
        "AWS Lambda（これ以降は Lambda と表記する）を使います。\n"
        "Amazon S3（以降は S3 と表記する）に保存します。\n"
        "Amazon EC2（以降は EC2 と表記する）を起動します。\n"
        "Lambda と S3 と EC2 を連携します。"
    )

    assert _blog_rule_issues(text, "aws-first-mention") == []


def test_blogプロファイルは同じ文の正式名と略称を宣言として扱い指摘しない():
    text = (
        "本文では AWS のサービス名を、初出だけ正式名称で書きます。"
        "以降は AWS Lambda を「Lambda」、Amazon S3 を「S3」のように略記します。\n"
        "Lambda で処理し、S3 に保存します。"
    )

    assert _blog_rule_issues(text, "aws-first-mention") == []


def test_blogプロファイルは鉤括弧内の略称宣言以降を指摘しない():
    text = "これ以降は「Lambda」と表記します。\nLambda で処理します。"

    assert _blog_rule_issues(text, "aws-first-mention") == []


def test_blogプロファイルは正式名だけのAWSサービスを略称と誤判定しない():
    text = "AWS Lambda と Amazon S3 と Amazon EC2 を使います。"

    assert _blog_rule_issues(text, "aws-first-mention") == []


def test_blog固有ルールはfrontmatter内を指摘しない():
    text = (
        "---\n"
        "title: eufy と OS/ランタイム\n"
        "description: にわとりの状態機械は実行出来ます\n"
        "note: EC2における方法）、これを使う。\n"
        "# 手順\n"
        "まず、確認します。\n"
        "sources: （出典: A）（出典: B）（出典: C）\n"
        "service: Lambda\n"
        "---\n"
        "設定します。\n確認します。"
    )
    rule_names = {
        "brand-capitalization",
        "chicken-notation",
        "unofficial-translation",
        "slash-coordination",
        "alnum-japanese-spacing",
        "open-kanji",
        "style-mixing",
        "comma-sentence-join",
        "section-opening-mazu",
        "citation-density",
        "aws-first-mention",
    }

    with patch("blog_linter.linter.check_ai_writing", return_value=[]):
        issues = lint_markdown(text, profile="blog")

    assert not rule_names.intersection(issue.rule_name for issue in issues)


def test_blog固有ルールはコードブロック内を指摘しない():
    text = (
        "設定します。\n確認します。\n"
        "```md\n"
        "# 手順\n"
        "まず、eufy と OS/ランタイムを確認出来ます。\n"
        "にわとりの状態機械である。\n"
        "EC2における方法）、これを使う。\n"
        "（出典: A）（出典: B）（出典: C）\n"
        "Lambda\n"
        "```"
    )
    rule_names = {
        "brand-capitalization",
        "chicken-notation",
        "unofficial-translation",
        "slash-coordination",
        "alnum-japanese-spacing",
        "open-kanji",
        "style-mixing",
        "comma-sentence-join",
        "section-opening-mazu",
        "citation-density",
        "aws-first-mention",
    }

    with patch("blog_linter.linter.check_ai_writing", return_value=[]):
        issues = lint_markdown(text, profile="blog")

    assert not rule_names.intersection(issue.rule_name for issue in issues)


def test_blog固有の語句ルールはインラインコード内を指摘しない():
    text = (
        "`eufy にわとり 状態機械 OS/ランタイム "
        "EC2に 実行出来ます ）、これ Lambda` を例にします。"
    )
    rule_names = {
        "brand-capitalization",
        "chicken-notation",
        "unofficial-translation",
        "slash-coordination",
        "alnum-japanese-spacing",
        "open-kanji",
        "comma-sentence-join",
        "aws-first-mention",
    }

    with patch("blog_linter.linter.check_ai_writing", return_value=[]):
        issues = lint_markdown(text, profile="blog")

    assert not rule_names.intersection(issue.rule_name for issue in issues)


def test_blog固有ルールは複数行のalt属性とtitle属性内を指摘しない():
    text = (
        "## 構成\n\n"
        "設定します。\n"
        "確認します。\n"
        "<img\n"
        '  alt="eufy にわとり 状態機械 OS/ランタイム EC2に NodeJS Github\n'
        "  実行出来ます。この方法である。）、これ Lambda\n"
        '  （出典: A）（出典: B）（出典: C）"\n'
        '  title="eufy と S3における説明である。"\n'
        "/>"
    )
    rule_names = {
        "brand-capitalization",
        "chicken-notation",
        "unofficial-translation",
        "slash-coordination",
        "alnum-japanese-spacing",
        "open-kanji",
        "style-mixing",
        "comma-sentence-join",
        "citation-density",
        "aws-first-mention",
        "表記ブレ: Node.js",
        "表記ブレ: GitHub",
    }

    with patch("blog_linter.linter.check_ai_writing", return_value=[]):
        issues = lint_markdown(text, profile="blog")

    assert not rule_names.intersection(issue.rule_name for issue in issues)
