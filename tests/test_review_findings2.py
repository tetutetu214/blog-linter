import re
from pathlib import Path
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest

from blog_linter.linter import lint_markdown
from blog_linter.models import LintIssue
from blog_linter.notation_checker import check_notation


def _blog_rule_issues(text: str, rule_name: str):
    with patch("blog_linter.linter.check_ai_writing", return_value=[]):
        issues = lint_markdown(text, profile="blog")
    return [issue for issue in issues if issue.rule_name == rule_name]


def test_指摘1_JSX属性のバッククォートは後続本文を隠さない():
    text = '<img alt="`" />\neufy を確認出来ます。\n<img alt="`" />'

    assert len(_blog_rule_issues(text, "brand-capitalization")) == 1
    assert len(_blog_rule_issues(text, "open-kanji")) == 1


def test_指摘2_コードを含むリンクと画像の非本文を検査しない():
    link = "[`説明`](./出来る.md)"
    image = '![`x` eufy](./image.png "状態機械を確認出来ます。")'

    assert _blog_rule_issues(link, "open-kanji") == []
    assert _blog_rule_issues(image, "brand-capitalization") == []
    assert _blog_rule_issues(image, "unofficial-translation") == []
    assert _blog_rule_issues(image, "open-kanji") == []


def test_指摘3_引用とリストの未閉鎖フェンスは外側の本文を隠さない():
    texts = (
        "> ```text\n> code\n\neufy を確認出来ます。",
        "- ```\n  example\n- eufy を確認出来ます。",
    )

    for text in texts:
        assert len(_blog_rule_issues(text, "brand-capitalization")) == 1
        assert len(_blog_rule_issues(text, "open-kanji")) == 1


def test_指摘4_字下げコードだけを本文から除外する():
    indented_code = "\teufy を確認出来ます。"
    indented_fence_text = "    ```\n\neufy を確認出来ます。"

    assert _blog_rule_issues(indented_code, "brand-capitalization") == []
    assert _blog_rule_issues(indented_code, "open-kanji") == []
    assert len(
        _blog_rule_issues(indented_fence_text, "brand-capitalization")
    ) == 1
    assert len(_blog_rule_issues(indented_fence_text, "open-kanji")) == 1


def test_指摘5_エスケープと段落境界をコードスパンにしない():
    escaped = "\\`eufy\\`"
    separate_paragraphs = "`\n\neufy\n\n`"

    assert len(_blog_rule_issues(escaped, "brand-capitalization")) == 1
    assert len(
        _blog_rule_issues(separate_paragraphs, "brand-capitalization")
    ) == 1


def test_指摘6_参照形式リンクと画像の非本文を検査しない():
    link = '[説明][ref]\n\n[ref]: ./出来る.md "title"'
    image = (
        "![eufy][pic]\n\n"
        '[pic]: ./image.png "状態機械を確認出来ます。"'
    )

    assert _blog_rule_issues(link, "open-kanji") == []
    assert _blog_rule_issues(image, "brand-capitalization") == []
    assert _blog_rule_issues(image, "unofficial-translation") == []
    assert _blog_rule_issues(image, "open-kanji") == []


def test_指摘7_JSXは属性の種類を問わず検査しない():
    assert _blog_rule_issues(
        '<img src="./出来る.png" />',
        "open-kanji",
    ) == []
    assert _blog_rule_issues(
        "<Widget value={eufy} />",
        "brand-capitalization",
    ) == []


def test_指摘8_対応する括弧を含む素のURLを末尾まで検査しない():
    assert _blog_rule_issues(
        "https://example.com/a(b)/eufy",
        "brand-capitalization",
    ) == []
    assert _blog_rule_issues(
        "https://example.com/a(b)/出来る",
        "open-kanji",
    ) == []


def test_指摘9_体言止めを常体として数えない():
    list_text = "設定します。\n確認します。\n- 追加のおやつ。"
    table_text = "設定します。\n確認します。\n| 項目 | いぬ。 |"

    assert _blog_rule_issues(list_text, "style-mixing") == []
    assert _blog_rule_issues(table_text, "style-mixing") == []


def test_指摘10_形容詞の常体は意図的に検出しない():
    text = "設定します。\n確認します。\n処理が速い。"

    assert _blog_rule_issues(text, "style-mixing") == []


def test_指摘11_強調された語尾も文体として数える():
    polite_majority = "設定します。\n確認します。\n処理を**実行する**。"
    plain_majority = "保存する。\n確認する。\n設定し**ます**。"

    assert [
        issue.line_number
        for issue in _blog_rule_issues(polite_majority, "style-mixing")
    ] == [3]
    assert [
        issue.line_number
        for issue in _blog_rule_issues(plain_majority, "style-mixing")
    ] == [3]


def test_指摘12_為替の語中を開かない():
    text = "日本の為替制度を確認します。"

    assert _blog_rule_issues(text, "open-kanji") == []


def test_指摘13_その他を接続語として扱わない():
    text = "入力（必須）、その他の項目（任意）を指定します。"

    assert _blog_rule_issues(text, "comma-sentence-join") == []


def test_指摘14_AWS略称の宣言解析をせず確認だけを出す():
    texts = (
        "これ以降は Lambda と表記するわけではありません。\n"
        "Lambda を使います。",
        "これ以降は Lambda を実行し、結果を S3 と表記する。\n"
        "Lambda を使います。",
    )

    for text in texts:
        issues = _blog_rule_issues(text, "aws-first-mention")
        assert any(issue.matched_text == "Lambda" for issue in issues)
        assert all(issue.needs_review for issue in issues)
        assert all(issue.suggestion is None for issue in issues)


def test_指摘15_AWS以外のサービス帰属を判定せず確認だけを出す():
    texts = (
        ("Google Cloud の IAM と AWS の権限を比較します。", "IAM"),
        ("## Google Cloud の設定\nVPC を作成します。", "VPC"),
    )

    for text, matched_text in texts:
        issues = _blog_rule_issues(text, "aws-first-mention")
        assert [issue.matched_text for issue in issues] == [matched_text]
        assert issues[0].needs_review is True
        assert issues[0].suggestion is None


def test_指摘16_UIはstyleとstructureの場所と理由を表示する():
    with patch("blog_linter.linter.check_ai_writing", return_value=[]):
        app_path = Path(__file__).parents[1] / "app.py"
        app = AppTest.from_file(app_path).run()
        app.text_area[0].input("実行出来ます。\nLambda を使います。")
        app.button[0].click().run()

    metrics = {metric.label: metric.value for metric in app.metric}
    expanders = "\n".join(expander.label for expander in app.expander)
    markdown = "\n".join(element.value for element in app.markdown)
    assert metrics["文体"] == "1 件"
    assert metrics["構成"] == "1 件"
    assert "[提案] [open-kanji]" in expanders
    assert "[確認] [aws-first-mention]" in expanders
    assert "**行番号:**" in markdown
    assert "**メッセージ:**" in markdown


def test_指摘18_CLIヘルプはblogを既定として表示する(capsys):
    from blog_linter.__main__ import main

    with patch("sys.argv", ["prog", "check", "--help"]):
        with pytest.raises(SystemExit) as exit_info:
            main()

    assert exit_info.value.code == 0
    assert "デフォルト: blog" in capsys.readouterr().out


def test_CLIは確認と提案を区別して表示する(capsys):
    from blog_linter.__main__ import _print_issues

    issues = [
        LintIssue(
            1,
            1,
            "eufy",
            "notation",
            "brand-capitalization",
            "確認してください。",
            needs_review=True,
        ),
        LintIssue(
            2,
            1,
            "出来ます",
            "style",
            "open-kanji",
            "開くことを推奨します。",
            suggestion="できます",
        ),
    ]

    _print_issues(issues)

    output = capsys.readouterr().out
    assert "[確認] [brand-capitalization]" in output
    assert "[提案] [open-kanji]" in output


def test_確認専用5ルールは提案を持たない():
    cases = (
        ("eufy", "brand-capitalization"),
        ("にわとり", "chicken-notation"),
        ("OS/ランタイム", "slash-coordination"),
        ("Lambda", "aws-first-mention"),
    )

    for text, rule_name in cases:
        issues = _blog_rule_issues(text, rule_name)
        assert issues
        assert all(issue.needs_review for issue in issues)
        assert all(issue.suggestion is None for issue in issues)

    # 非公式訳語は辞書が空で出荷するため、語を足した状態で確かめる。
    with patch.dict(
        "blog_linter.notation_checker.BLOG_UNOFFICIAL_TRANSLATIONS",
        {"状態機械": "ステートマシン"},
        clear=True,
    ):
        issues = _blog_rule_issues("状態機械を実装します。", "unofficial-translation")

    assert issues
    assert all(issue.needs_review for issue in issues)
    assert all(issue.suggestion is None for issue in issues)


def test_フェンス除外を外すと指摘が増える():
    text = "~~~text\neufy\n~~~"

    assert _blog_rule_issues(text, "brand-capitalization") == []
    with patch(
        "blog_linter.markdown_utils._block_non_prose_ranges",
        return_value=[],
    ):
        assert _blog_rule_issues(text, "brand-capitalization") != []


def test_インラインコード除外を外すと指摘が増える():
    text = "`eufy`"

    assert _blog_rule_issues(text, "brand-capitalization") == []
    with patch(
        "blog_linter.markdown_utils._inline_non_prose_ranges",
        return_value=[],
    ):
        assert _blog_rule_issues(text, "brand-capitalization") != []


def test_front_matter除外を外すと指摘が増える():
    text = "---\ntitle: eufy\n---\n本文です。"

    assert _blog_rule_issues(text, "brand-capitalization") == []
    with patch(
        "blog_linter.markdown_utils._block_non_prose_ranges",
        return_value=[],
    ):
        assert _blog_rule_issues(text, "brand-capitalization") != []


def test_URL除外を外すと指摘が増える():
    text = "https://example.com/eufy"

    assert _blog_rule_issues(text, "brand-capitalization") == []
    with patch(
        "blog_linter.markdown_utils._raw_url_ranges",
        return_value=[],
    ):
        assert _blog_rule_issues(text, "brand-capitalization") != []


def test_リンク先除外を外すと指摘が増える():
    text = "[説明](./eufy)"

    assert _blog_rule_issues(text, "brand-capitalization") == []
    with patch(
        "blog_linter.markdown_utils._inline_non_prose_ranges",
        return_value=[],
    ):
        assert _blog_rule_issues(text, "brand-capitalization") != []


def test_画像のaltとtitle除外を外すと指摘が増える():
    text = '![eufy](./image.png "状態機械")'

    assert _blog_rule_issues(text, "brand-capitalization") == []
    with patch(
        "blog_linter.markdown_utils._inline_non_prose_ranges",
        return_value=[],
    ):
        assert _blog_rule_issues(text, "brand-capitalization") != []


def test_HTMLとJSX除外を外すと指摘が増える():
    texts = (
        "<Widget value={eufy} />",
        "本文 <span data-value=eufy>表示</span>",
    )

    for text in texts:
        assert _blog_rule_issues(text, "brand-capitalization") == []
        with patch(
            "blog_linter.markdown_utils._html_tag_ranges",
            return_value=[],
        ):
            assert _blog_rule_issues(text, "brand-capitalization") != []


def test_参照形式リンク除外を外すと指摘が増える():
    text = "[説明][ref]\n\n[ref]: ./eufy"

    assert _blog_rule_issues(text, "brand-capitalization") == []
    with patch(
        "blog_linter.markdown_utils._reference_definition_ranges",
        return_value=[],
    ):
        assert _blog_rule_issues(text, "brand-capitalization") != []


def test_体言止めの防御を外すと指摘が増える():
    text = "設定します。\n確認します。\n追加のおやつ。"
    broad_plain_ending = re.compile(r"つ[。！？!?]+$")

    assert _blog_rule_issues(text, "style-mixing") == []
    with patch(
        "blog_linter.blog_style_checker._PLAIN_ENDING_PATTERN",
        broad_plain_ending,
    ):
        assert _blog_rule_issues(text, "style-mixing") != []


def test_表の行の除外を外すと指摘が増える():
    text = (
        "設定します。\n確認します。\n\n"
        "| 項目 | 説明 |\n| --- | --- |\n| 手順 | 操作する。 |"
    )

    assert _blog_rule_issues(text, "style-mixing") == []
    with patch(
        "blog_linter.blog_style_checker._is_nominal_or_label_line",
        return_value=False,
    ):
        assert _blog_rule_issues(text, "style-mixing") != []


def test_箇条書きの完全な文は文体検査から除外しない():
    text = "設定します。\n確認します。\n- 操作する。"

    assert _blog_rule_issues(text, "style-mixing")


def test_漢字隣接の除外を外すと指摘が増える():
    text = "日本の為替制度を確認します。"

    assert _blog_rule_issues(text, "open-kanji") == []
    with patch(
        "blog_linter.blog_style_checker._has_adjacent_kanji",
        return_value=False,
    ):
        assert _blog_rule_issues(text, "open-kanji") != []


def test_接続語の除外を外すと指摘が増える():
    text = "入力（必須）、または出力（任意）を指定します。"

    assert _blog_rule_issues(text, "comma-sentence-join") == []
    with patch(
        "blog_linter.blog_style_checker._is_excluded_connector",
        return_value=False,
    ):
        assert _blog_rule_issues(text, "comma-sentence-join") != []


def test_従来どおり提案する6ルールは確認専用ではない():
    cases = (
        ("EC2に接続します。", "alnum-japanese-spacing"),
        ("実行出来ます。", "open-kanji"),
        ("設定します。\n確認します。\n実行する。", "style-mixing"),
        ("入力（必須）、これを使います。", "comma-sentence-join"),
        ("## 手順\nまず、確認します。", "section-opening-mazu"),
        (
            "## 根拠\n一（出典: A）\n二（出典: B）\n三（出典: C）",
            "citation-density",
        ),
    )

    for text, rule_name in cases:
        issues = _blog_rule_issues(text, rule_name)
        assert issues
        assert all(issue.needs_review is False for issue in issues)
        assert all(issue.suggestion for issue in issues)


def test_qiitaプロファイルの従来表記ルールは提案を維持する():
    issues = check_notation("サーバを使います。", profile="qiita")

    assert len(issues) == 1
    assert issues[0].needs_review is False
    assert issues[0].suggestion == "サーバー"
