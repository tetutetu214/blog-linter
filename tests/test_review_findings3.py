from unittest.mock import patch

from blog_linter.linter import lint_markdown


def _blog_rule_issues(text: str, rule_name: str):
    with patch("blog_linter.linter.check_ai_writing", return_value=[]):
        issues = lint_markdown(text, profile="blog")
    return [issue for issue in issues if issue.rule_name == rule_name]


def test_指摘1_HTMLタグだけを除外して周囲と内側の本文を検査する():
    line_break = "<br>\neufy を確認出来ます。"
    container = (
        "<div>\neufy を確認出来ます。\n</div>\n"
        "eufy を確認出来ます。"
    )

    assert len(_blog_rule_issues(line_break, "brand-capitalization")) == 1
    assert len(_blog_rule_issues(line_break, "open-kanji")) == 1
    assert len(_blog_rule_issues(container, "brand-capitalization")) == 2
    assert len(_blog_rule_issues(container, "open-kanji")) == 2


def test_指摘2_画像ラベル内のコードは画像後の本文を隠さない():
    text = "![`[`](./x.png) eufy を確認出来ます。 ]"

    assert len(_blog_rule_issues(text, "brand-capitalization")) == 1
    assert len(_blog_rule_issues(text, "open-kanji")) == 1


def test_指摘3_リンク先の構文だけを除外して後続本文を検査する():
    apostrophe = "[説明](./it's.md) eufy を確認出来ます (it's OK)"
    angle_destination = (
        "[説明](<./a(b/出来る>) eufy を確認出来ます。"
    )

    assert len(_blog_rule_issues(apostrophe, "brand-capitalization")) == 1
    assert len(_blog_rule_issues(apostrophe, "open-kanji")) == 1
    assert len(
        _blog_rule_issues(angle_destination, "brand-capitalization")
    ) == 1
    assert [
        issue.matched_text
        for issue in _blog_rule_issues(angle_destination, "open-kanji")
    ] == ["出来ます"]


def test_指摘4_引用内の水平線をfront_matterとして除外しない():
    text = "> ---\n> eufy を確認出来ます。"

    assert len(_blog_rule_issues(text, "brand-capitalization")) == 1
    assert len(_blog_rule_issues(text, "open-kanji")) == 1


def test_指摘4_未閉鎖の開始区切りをfront_matterとして除外しない():
    text = "---\neufy を確認出来ます。"

    assert len(_blog_rule_issues(text, "brand-capitalization")) == 1
    assert len(_blog_rule_issues(text, "open-kanji")) == 1


def test_指摘5_長いバッククォート列の一部でコードスパンを閉じない():
    text = "``x ``` eufy 出来る``"

    assert _blog_rule_issues(text, "brand-capitalization") == []
    assert _blog_rule_issues(text, "open-kanji") == []


def test_指摘6_文中のJSXタグ属性を検査しない():
    text = '説明 <Widget value={eufy} title={"出来る"} /> を表示します。'

    assert _blog_rule_issues(text, "brand-capitalization") == []
    assert _blog_rule_issues(text, "open-kanji") == []


def test_指摘7_CRLFと引用記号を含む複数行タグの属性を検査しない():
    crlf = '本文 <span\r\n title="出来る">表示</span>'
    blockquote = '> 本文 <span\n> title="出来る">表示</span>'

    assert _blog_rule_issues(crlf, "open-kanji") == []
    assert _blog_rule_issues(blockquote, "open-kanji") == []


def test_指摘7_独立した閉じ行を持つ複数行タグの属性だけを除外する():
    text = (
        '<video\n  controls\n  title="出来る"\n>\n'
        "eufy を確認出来ます。"
    )

    assert len(_blog_rule_issues(text, "brand-capitalization")) == 1
    assert [
        issue.matched_text
        for issue in _blog_rule_issues(text, "open-kanji")
    ] == ["出来ます"]


def test_指摘7_未閉鎖の複数行タグ候補は後続本文を隠さない():
    text = "<Widget\neufy を確認出来ます。\n次の > 記号"

    assert len(_blog_rule_issues(text, "brand-capitalization")) == 1
    assert len(_blog_rule_issues(text, "open-kanji")) == 1


def test_指摘8_採用されなかった重複参照定義も検査しない():
    text = "[説明][x]\n\n[x]: ./ok\n[x]: ./出来る.md"

    assert _blog_rule_issues(text, "open-kanji") == []


def test_指摘9_素のURLは日本語の句読点で終了して後続本文を残す():
    sentence = "詳しくは https://example.com。実行出来ます。"
    parenthesized = "（https://example.com）eufy を確認出来ます。"

    assert len(_blog_rule_issues(sentence, "open-kanji")) == 1
    assert len(_blog_rule_issues(parenthesized, "brand-capitalization")) == 1
    assert len(_blog_rule_issues(parenthesized, "open-kanji")) == 1


def test_指摘10_パーサが認識したftp_autolink全体を検査しない():
    text = "<ftp://example.com/出来る>"

    assert _blog_rule_issues(text, "open-kanji") == []
    assert _blog_rule_issues(text, "slash-coordination") == []


def test_指摘11_スラッシュ並列は3項と文字種混在を語全体で報告する():
    text = (
        "CPU/GPU/TPU を比較します。\n"
        "読み込み/書き込みを制限します。\n"
        "CPU/読み込みを比較します。"
    )

    issues = _blog_rule_issues(text, "slash-coordination")

    assert [issue.matched_text for issue in issues] == [
        "CPU/GPU/TPU",
        "読み込み/書き込み",
        "CPU/読み込み",
    ]


def test_指摘12_形容詞と名詞内の文字列を常体の語尾に数えない():
    adjective = "設定します。\n確認します。\nデータが少ない。"
    noun = "設定します。\n確認します。\n追加のくつした。"

    assert _blog_rule_issues(adjective, "style-mixing") == []
    assert _blog_rule_issues(noun, "style-mixing") == []


def test_指摘12_活用した動詞の語尾は常体として数える():
    past = "設定します。\n確認します。\n条件を満たした。"
    negative = "設定します。\n確認します。\n装置が動かない。"

    assert _blog_rule_issues(past, "style-mixing")
    assert _blog_rule_issues(negative, "style-mixing")


def test_指摘13_構文上の表だけを除外して本文を含む箇条書きを検査する():
    code_pipe = "設定します。\n確認します。\n`x | y` を使う。"
    list_sentence = "設定します。\n確認します。\n- 操作する。（補足）"

    assert [
        issue.line_number
        for issue in _blog_rule_issues(code_pipe, "style-mixing")
    ] == [3]
    assert [
        issue.line_number
        for issue in _blog_rule_issues(list_sentence, "style-mixing")
    ] == [3]


def test_指摘14_リンクとHTML装飾を除いた表示文の語尾を検査する():
    link = "設定します。\n確認します。\n[実行する](./doc)。"
    html = (
        "設定します。\n確認します。\n"
        "実行<strong>する</strong>。"
    )

    assert [
        issue.line_number
        for issue in _blog_rule_issues(link, "style-mixing")
    ] == [3]
    assert [
        issue.line_number
        for issue in _blog_rule_issues(html, "style-mixing")
    ] == [3]


def test_指摘15_長い候補を除外しても内側の短い候補を検査する():
    text = "仕事が出来る。操作が出来る。"

    issues = _blog_rule_issues(text, "open-kanji")

    assert [issue.matched_text for issue in issues] == ["出来る", "出来る"]


def test_指摘16_括弧付きの名詞句を読点でつないだ列挙は指摘しない():
    texts = (
        "概要（必読）、これまでの変更点（任意）を確認します。",
        "入力（必須）、それぞれの出力（任意）を指定します。",
        "概要（必読）、これ以上の変更点（任意）を確認します。",
        "入力（必須）、それ自体の出力（任意）を指定します。",
    )

    for text in texts:
        assert _blog_rule_issues(text, "comma-sentence-join") == []


def test_指摘17_setext見出しを構成と見出し直後の検査に使う():
    citation = (
        "根拠\n----\n一（出典: A）\n二（出典: B）\n三（出典: C）"
    )
    opening = "手順\n----\nまず、設定します。"

    assert [
        issue.line_number
        for issue in _blog_rule_issues(citation, "citation-density")
    ] == [1]
    assert [
        issue.line_number
        for issue in _blog_rule_issues(opening, "section-opening-mazu")
    ] == [3]


def test_指摘18_エスケープ判定を無効化するとリンク先が漏れる():
    text = r"[説明](./a\)eufy)"

    assert _blog_rule_issues(text, "brand-capitalization") == []
    with patch("blog_linter.markdown_utils._is_escaped", return_value=False):
        assert _blog_rule_issues(text, "brand-capitalization")


def test_指摘18_文字参照の位置対応を無効化するとリンク先が漏れる():
    text = "&#65; [説明](./eufy)"

    assert _blog_rule_issues(text, "brand-capitalization") == []
    with patch(
        "blog_linter.markdown_utils.unescape",
        side_effect=lambda value: value,
    ):
        assert _blog_rule_issues(text, "brand-capitalization")


def test_指摘18_JSXの引用符判定を無効化するとタグ終端を確定できない():
    text = '<img alt=">" />\neufy を確認出来ます。'
    first_line_end = text.index("\n")

    assert len(_blog_rule_issues(text, "brand-capitalization")) == 1
    assert len(_blog_rule_issues(text, "open-kanji")) == 1
    from blog_linter.markdown_utils import _scan_html_tag

    assert _scan_html_tag(text, 0, len(text))[0] == first_line_end
    with patch("blog_linter.markdown_utils._is_escaped", return_value=True):
        assert _scan_html_tag(text, 0, len(text)) is None


def test_指摘18_表示文字の位置対応を無効化するとリンク先が漏れる():
    text = "[未定義] [説明](./eufy)"

    assert _blog_rule_issues(text, "brand-capitalization") == []
    with patch(
        "blog_linter.markdown_utils._advance_over_rendered_text",
        side_effect=lambda source, rendered, cursor, limit: cursor,
    ):
        assert _blog_rule_issues(text, "brand-capitalization")
