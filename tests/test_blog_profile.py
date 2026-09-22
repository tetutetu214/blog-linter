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


def test_blogプロファイルはURLとMarkdownリンク先の表記ブレを指摘しない():
    text = (
        "https://docs.aws.amazon.com/lambda/latest/dg/lambda-nodejs.html\n"
        "[クライアント](https://github.com/bropat/eufy-security-client)"
    )

    issues = check_notation(text, profile="blog")

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


def test_Markdownリンク先の閉じ括弧より後ろは本文として検査する():
    text = "[資料](https://example.com)のeufyと状態機械を確認します。"

    assert _blog_rule_issues(text, "brand-capitalization")
    assert _blog_rule_issues(text, "unofficial-translation")


def test_インラインコード内のタグ断片は後続本文の除外状態を変えない():
    text = (
        '`<img alt="` は記法の例です。\n'
        "eufy を確認出来ます。\n"
        "Lambda を使います。"
    )

    assert _blog_rule_issues(text, "brand-capitalization")
    assert _blog_rule_issues(text, "open-kanji")
    assert _blog_rule_issues(text, "aws-first-mention")


def test_一般動詞で終わる常体を文体混在として指摘する():
    text = "設定します。\n確認します。\nログを読む。"

    issues = _blog_rule_issues(text, "style-mixing")

    assert [issue.line_number for issue in issues] == [3]


def test_常体が多数なら敬体を全件指摘する():
    text = "保存する。\nログを読む。\n完了です。"

    issues = _blog_rule_issues(text, "style-mixing")

    assert [issue.line_number for issue in issues] == [3]


def test_敬体と常体が同数でも両方を指摘する():
    text = "設定します。\nログを読む。"

    issues = _blog_rule_issues(text, "style-mixing")

    assert [issue.line_number for issue in issues] == [1, 2]


def test_qiitaのURLとバッククォート判定は変更前の挙動を保つ():
    url_issues = check_notation(
        "https://example.com/NodeJS",
        profile="qiita",
    )
    closed_issues = check_notation("``サーバ``", profile="qiita")
    unclosed_issues = check_notation("`サーバ", profile="qiita")

    assert len(url_issues) == 3
    assert len(closed_issues) == 1
    assert unclosed_issues == []
    # 既定プロファイルは blog（Qiita からブログへ移行済み、2026-09-23）。
    assert check_notation("``サーバ``") == check_notation("``サーバ``", profile="blog")


def test_短い内側フェンスは長いコードブロックを閉じない():
    text = (
        "````md\n"
        "```\n"
        "````\n"
        "eufy と 状態機械を確認出来ます。"
    )

    assert _blog_rule_issues(text, "brand-capitalization")
    assert _blog_rule_issues(text, "unofficial-translation")


def test_frontmatter内のフェンスは本文のコード状態を変えない():
    text = (
        "---\n"
        "description: |\n"
        "  ```\n"
        "---\n"
        "eufy と 状態機械を確認します。"
    )

    assert _blog_rule_issues(text, "brand-capitalization")
    assert _blog_rule_issues(text, "unofficial-translation")


def test_情報文字列付きフェンス行は終了フェンスとして扱わない():
    text = (
        "```text\n"
        "```not-a-closer\n"
        "eufy を確認出来ます。\n"
        "```"
    )

    assert _blog_rule_issues(text, "brand-capitalization") == []
    assert _blog_rule_issues(text, "open-kanji") == []


def test_引用とリスト内のフェンスコードを本文として検査しない():
    quote = "> ```text\n> eufy を確認出来ます。\n> ```"
    list_item = "- ```text\n  eufy を確認出来ます。\n  ```"

    for text in (quote, list_item):
        assert _blog_rule_issues(text, "brand-capitalization") == []
        assert _blog_rule_issues(text, "open-kanji") == []


def test_複数行インラインコードを本文として検査しない():
    text = "`eufy\n状態機械を確認出来ます。`"

    assert _blog_rule_issues(text, "brand-capitalization") == []
    assert _blog_rule_issues(text, "unofficial-translation") == []
    assert _blog_rule_issues(text, "open-kanji") == []


def test_本数の異なるバッククォートはコードスパンにしない():
    text = "``eufy```"

    assert _blog_rule_issues(text, "brand-capitalization")


def test_Markdown画像のaltとtitleを本文として検査しない():
    text = '![eufy](./image.png "状態機械を確認出来ます。")'

    assert _blog_rule_issues(text, "brand-capitalization") == []
    assert _blog_rule_issues(text, "unofficial-translation") == []
    assert _blog_rule_issues(text, "open-kanji") == []


def test_JSX式のalt属性を本文として検査しない():
    text = '<img alt={"eufy にわとり 実行出来ます EC2に"} />'
    excluded_rules = {
        "brand-capitalization",
        "chicken-notation",
        "open-kanji",
        "alnum-japanese-spacing",
        "aws-first-mention",
    }

    with patch("blog_linter.linter.check_ai_writing", return_value=[]):
        issues = lint_markdown(text, profile="blog")

    assert not excluded_rules.intersection(
        issue.rule_name for issue in issues
    )


def test_JSX式内の不等号はタグを閉じず後続alt属性を除外する():
    text = (
        '<img src={width > 100 ? large : small} alt="eufy" />\n'
        "状態機械を確認します。"
    )

    assert _blog_rule_issues(text, "brand-capitalization") == []
    assert _blog_rule_issues(text, "unofficial-translation")


def test_URLとMarkdownリンク先の開く漢字を指摘しない():
    text = "https://example.com/出来る\n[説明](./出来る.md)"

    assert _blog_rule_issues(text, "open-kanji") == []


def test_frontmatterのブロックスカラー内区切りで終了しない():
    text = (
        "---\n"
        "description: |\n"
        "  ---\n"
        "  eufy を確認出来ます。\n"
        "---\n"
        "本文です。"
    )

    assert _blog_rule_issues(text, "brand-capitalization") == []
    assert _blog_rule_issues(text, "open-kanji") == []


def test_AWS略称の否定宣言を肯定宣言として扱わない():
    text = "これ以降は Lambda と表記しません。\nLambda を使います。"

    assert len(_blog_rule_issues(text, "aws-first-mention")) == 1


def test_AWS略称を探す説明文を宣言として扱わない():
    text = "以下の例では Lambda という表記を探します。\nLambda を使います。"

    assert len(_blog_rule_issues(text, "aws-first-mention")) == 1


def test_AWS正式名との比較を略称宣言として扱わない():
    text = "Lambda と AWS Lambda の違いを調べます。"

    assert len(_blog_rule_issues(text, "aws-first-mention")) == 1


def test_AWS略称の肯定宣言は改行をまたいでも成立する():
    text = (
        "AWS Lambda（これ以降は\n"
        "Lambda と表記する）を使います。\n"
        "Lambda を使います。"
    )

    assert _blog_rule_issues(text, "aws-first-mention") == []


def test_AWS以外を明示したlambdaとIAMをAWS略称として扱わない():
    text = (
        "Python の lambda 式を使います。\n"
        "Google Cloud の IAM を使います。\n"
        "Azure の IAM を確認します。"
    )

    assert _blog_rule_issues(text, "aws-first-mention") == []


def test_AWS文脈のIAMは初出略称として指摘する():
    text = "AWS 環境で IAM を使います。"

    issues = _blog_rule_issues(text, "aws-first-mention")

    assert [issue.matched_text for issue in issues] == ["IAM"]


def test_open_kanjiは漢字語に含まれる事を部分一致で置換しない():
    text = "仕事が出来る。手仕事が出来る。出来高と出来事と為替を確認する。"

    assert _blog_rule_issues(text, "open-kanji") == []


def test_chicken_notationは複合語の鶏を部分一致で置換しない():
    text = "養鶏場と鶏肉加工場を見学します。"

    assert _blog_rule_issues(text, "chicken-notation") == []


def test_comma_sentence_joinはまたはの列挙を指摘しない():
    text = "入力（必須）、または出力（任意）を指定します。"

    assert _blog_rule_issues(text, "comma-sentence-join") == []


def test_style_mixingは外側パイプの有無によらず表内の完全文を数える():
    tables = (
        "設定します。\n確認します。\n\n"
        "項目 | 説明\n--- | ---\n手順 | 操作する。",
        "設定します。\n確認します。\n\n"
        "| 項目 | 説明 |\n| --- | --- |\n| 手順 | 操作する。 |",
    )

    for text in tables:
        issues = _blog_rule_issues(text, "style-mixing")
        assert len(issues) == 1
        assert issues[0].line_number == 6


def test_style_mixingは補足が続く箇条書き内の完全文を数える():
    text = "設定します。\n確認します。\n- 操作する。（補足）"

    issues = _blog_rule_issues(text, "style-mixing")

    assert len(issues) == 1
    assert issues[0].line_number == 3


def test_slash_coordinationルールは用語らしいスラッシュにも存在しない():
    text = (
        "TCP/IP と A/B テストを確認します。\n"
        "CPU/GPU/TPU を比較します。\n"
        "読み込み/書き込みを制限します。"
    )

    assert _blog_rule_issues(text, "slash-coordination") == []


def test_alt属性内の見出し文字列で出典の小節を分割しない():
    text = (
        "## 根拠\n"
        "一（出典: A）\n"
        "二（出典: B）\n"
        '<img alt="\n'
        "## ダミー\n"
        '" />\n'
        "三（出典: C）"
    )

    issues = _blog_rule_issues(text, "citation-density")

    assert [issue.line_number for issue in issues] == [1]


def test_コード除外は目印を外すと同じ語を指摘する():
    protected = "~~~text\neufy\n~~~"
    exposed = "eufy"

    assert _blog_rule_issues(protected, "brand-capitalization") == []
    assert _blog_rule_issues(exposed, "brand-capitalization")


def test_インラインコード除外は目印を外すと同じ語を指摘する():
    protected = "`eufy`"
    exposed = "eufy"

    assert _blog_rule_issues(protected, "brand-capitalization") == []
    assert _blog_rule_issues(exposed, "brand-capitalization")


def test_frontmatter除外は目印を外すと同じ語を指摘する():
    protected = "---\ntitle: eufy\n---\n本文です。"
    exposed = "title: eufy\n本文です。"

    assert _blog_rule_issues(protected, "brand-capitalization") == []
    assert _blog_rule_issues(exposed, "brand-capitalization")


def test_URL除外は目印を外すと同じ語を指摘する():
    protected = "https://example.com/eufy"
    exposed = "example.com/eufy"

    assert _blog_rule_issues(protected, "brand-capitalization") == []
    assert _blog_rule_issues(exposed, "brand-capitalization")


def test_Markdown画像除外は目印を外すと同じ語を指摘する():
    protected = "![eufy](./image.png)"
    exposed = "eufy"

    assert _blog_rule_issues(protected, "brand-capitalization") == []
    assert _blog_rule_issues(exposed, "brand-capitalization")


def test_JSX属性除外は目印を外すと同じ語を指摘する():
    protected = '<img alt={"eufy"} />'
    exposed = "eufy"

    assert _blog_rule_issues(protected, "brand-capitalization") == []
    assert _blog_rule_issues(exposed, "brand-capitalization")


def test_ラベル除外は目印を外すと同じ文体を指摘する():
    protected = "設定します。\n# 操作する。"
    exposed = "設定します。\n操作する。"

    assert _blog_rule_issues(protected, "style-mixing") == []
    assert _blog_rule_issues(exposed, "style-mixing")
