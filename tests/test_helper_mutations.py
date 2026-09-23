from collections.abc import Callable
from dataclasses import dataclass
import inspect
import re
from unittest.mock import patch

from markdown_it import MarkdownIt
import pytest

from blog_linter import blog_style_checker as style
from blog_linter import markdown_utils as markdown


@dataclass(frozen=True)
class MutationCase:
    name: str
    observe: Callable[[], object]
    expected: object
    replacement: Callable[..., object]


_FRONT_MATTER = "---\ntitle: eufy\n---\n本文"
_FENCE = "```\neufy\n```\n本文"
_REFERENCE = "[x]: ./eufy\n[x]: ./other"
_REFERENCE_ENV: dict[str, object] = {}
markdown._MARKDOWN.parse(_REFERENCE, _REFERENCE_ENV)
_LINK = r"[説明](./a\)eufy)"


def _front_matter_token_types() -> list[str]:
    parser = markdown._create_markdown_parser()
    return [token.type for token in parser.parse(_FRONT_MATTER)]


def _parsed_token_types() -> list[str]:
    return [
        token.type
        for token in markdown.parse_markdown_tokens("根拠\n----\n本文")
    ]


def _block_ranges() -> list[tuple[int, int]]:
    tokens = markdown._MARKDOWN.parse(_FENCE)
    return markdown._block_non_prose_ranges(_FENCE, tokens)


def _inline_ranges() -> list[tuple[int, int]]:
    text = "`eufy`"
    tokens = markdown._MARKDOWN.parse(text)
    return markdown._inline_non_prose_ranges(text, tokens)


MARKDOWN_MUTATIONS = (
    MutationCase(
        "_front_matter_rule",
        _front_matter_token_types,
        ["front_matter", "paragraph_open", "inline", "paragraph_close"],
        lambda *args: False,
    ),
    MutationCase(
        "_create_markdown_parser",
        _front_matter_token_types,
        ["front_matter", "paragraph_open", "inline", "paragraph_close"],
        lambda: MarkdownIt("commonmark").enable("table"),
    ),
    MutationCase(
        "parse_markdown_tokens",
        _parsed_token_types,
        [
            "heading_open",
            "inline",
            "heading_close",
            "paragraph_open",
            "inline",
            "paragraph_close",
        ],
        lambda text: [],
    ),
    MutationCase(
        "non_prose_ranges",
        lambda: markdown.non_prose_ranges("`eufy`"),
        [(0, 6)],
        lambda text: [],
    ),
    MutationCase(
        "span_overlaps_ranges",
        lambda: markdown.span_overlaps_ranges(2, 3, [(1, 4)]),
        True,
        lambda start, end, ranges: False,
    ),
    MutationCase(
        "mask_ranges",
        lambda: markdown.mask_ranges("abc\ndef", [(1, 5)]),
        "a  \n ef",
        lambda text, ranges: text,
    ),
    MutationCase(
        "line_start_offsets",
        lambda: markdown.line_start_offsets("a\r\nb\n"),
        [0, 3, 5],
        lambda text: [0],
    ),
    MutationCase(
        "_block_non_prose_ranges",
        _block_ranges,
        [(0, 13)],
        lambda text, tokens: [],
    ),
    MutationCase(
        "_inline_non_prose_ranges",
        _inline_ranges,
        [(0, 6)],
        lambda text, tokens: [],
    ),
    MutationCase(
        "_reference_definition_ranges",
        lambda: markdown._reference_definition_ranges(
            _REFERENCE,
            _REFERENCE_ENV,
        ),
        [(0, 12), (12, 24)],
        lambda text, environment: [],
    ),
    MutationCase(
        "_html_tag_ranges",
        lambda: markdown._html_tag_ranges(
            '本文 <span\n title="x">表示</span>',
            [],
        ),
        [(3, 20), (22, 29)],
        lambda text, protected_ranges: [],
    ),
    MutationCase(
        "_scan_html_tag",
        lambda: markdown._scan_html_tag(
            '<img alt=">" />',
            0,
            len('<img alt=">" />'),
        ),
        (15, "img", False, True),
        lambda text, start, limit: None,
    ),
    MutationCase(
        "_is_blockquote_marker",
        lambda: markdown._is_blockquote_marker(
            '> 本文 <span\n> title="x">表示</span>',
            11,
            5,
        ),
        True,
        lambda text, position, tag_start: False,
    ),
    MutationCase(
        "_raw_url_ranges",
        lambda: markdown._raw_url_ranges(
            "詳しくは https://example.com。本文",
            [],
        ),
        [(5, 24)],
        lambda text, protected_ranges: [],
    ),
    MutationCase(
        "_line_map_range",
        lambda: markdown._line_map_range(
            "a\r\nb\n",
            [0, 3, 5],
            [1, 2],
        ),
        (3, 5),
        lambda text, offsets, line_map: (0, 0),
    ),
    MutationCase(
        "_advance_over_rendered_text",
        lambda: markdown._advance_over_rendered_text(
            "&#65; X",
            "A X",
            0,
            7,
        ),
        7,
        lambda source, rendered, cursor, limit: cursor,
    ),
    MutationCase(
        "_locate_code_span",
        lambda: markdown._locate_code_span(
            "a ``x```y`` z",
            "``",
            0,
            14,
        ),
        (2, 11),
        lambda text, marker, cursor, limit: None,
    ),
    MutationCase(
        "_locate_image_span",
        lambda: markdown._locate_image_span(
            "![`[`](./x) 本文",
            0,
            15,
        ),
        (0, 11),
        lambda text, cursor, limit: None,
    ),
    MutationCase(
        "_locate_link_close",
        lambda: markdown._locate_link_close(
            _LINK,
            "link",
            0,
            3,
            len(_LINK),
        ),
        (3, 15),
        lambda text, kind, opening, cursor, limit: None,
    ),
    MutationCase(
        "_locate_literal",
        lambda: markdown._locate_literal("a **b**", "**", 0, 7),
        (2, 4),
        lambda text, literal, cursor, limit: None,
    ),
    MutationCase(
        "_find_link_parenthesis_end",
        lambda: markdown._find_link_parenthesis_end(
            r"(./a\)eufy)",
            0,
            11,
        ),
        10,
        lambda text, start, limit: None,
    ),
    MutationCase(
        "_find_matching_delimiter",
        lambda: markdown._find_matching_delimiter(
            "[`[`] 本文",
            0,
            "[",
            "]",
            8,
        ),
        4,
        lambda text, start, opening, closing, limit: None,
    ),
    MutationCase(
        "_advance_over_code_span",
        lambda: markdown._advance_over_code_span("``x```y``", 0, 9),
        9,
        lambda text, start, limit: None,
    ),
    MutationCase(
        "_find_backtick_run",
        lambda: markdown._find_backtick_run("``` ``", 2, 0, 6),
        4,
        lambda text, length, start, limit: None,
    ),
    MutationCase(
        "_find_unescaped",
        lambda: markdown._find_unescaped(r"\[ [", "[", 0, 4),
        3,
        lambda text, needle, start, limit: None,
    ),
    MutationCase(
        "_is_escaped",
        lambda: markdown._is_escaped(r"a\)", 2),
        True,
        lambda text, position: False,
    ),
    MutationCase(
        "_merge_ranges",
        lambda: markdown._merge_ranges([(3, 5), (1, 3), (8, 9)]),
        [(1, 5), (8, 9)],
        lambda ranges: ranges,
    ),
)


_STYLE_VISIBLE_LINES = [
    ("設定します。", list(range(6))),
    ("確認します。", list(range(6))),
    ("操作する。", list(range(5))),
]
_PLAIN_MATCH = style._PLAIN_ENDING_PATTERN.search("操作する。")
assert isinstance(_PLAIN_MATCH, re.Match)


STYLE_MUTATIONS = (
    MutationCase(
        "check_blog_style",
        lambda: [
            issue.rule_name
            for issue in style.check_blog_style("実行出来ます。")
        ],
        ["open-kanji"],
        lambda text: [],
    ),
    MutationCase(
        "_check_open_kanji",
        lambda: [
            issue.matched_text
            for issue in style._check_open_kanji(
                ["仕事が出来る。"],
                ["仕事が出来る。"],
            )
        ],
        ["出来る"],
        lambda lines, masked_lines: [],
    ),
    MutationCase(
        "_check_style_mixing",
        lambda: [
            issue.line_number
            for issue in style._check_style_mixing(
                _STYLE_VISIBLE_LINES,
                set(),
                set(),
            )
        ],
        [3],
        lambda visible_lines, heading_lines, table_lines: [],
    ),
    MutationCase(
        "_check_comma_sentence_join",
        lambda: [
            issue.matched_text
            for issue in style._check_comma_sentence_join(
                ["説明（補足）、これを使います。"],
                ["説明（補足）、これを使います。"],
            )
        ],
        ["）、これ"],
        lambda lines, masked_lines: [],
    ),
    MutationCase(
        "_check_section_opening_mazu",
        lambda: [
            issue.line_number
            for issue in style._check_section_opening_mazu(
                ["手順", "----", "まず、設定します。"],
                ["手順", "----", "まず、設定します。"],
                [(0, 2)],
            )
        ],
        [3],
        lambda lines, masked_lines, heading_maps: [],
    ),
    MutationCase(
        "_is_nominal_or_label_line",
        lambda: style._is_nominal_or_label_line(2, set(), {2}),
        True,
        lambda line_index, heading_lines, table_lines: False,
    ),
    MutationCase(
        "_visible_line",
        lambda: style._visible_line(
            "[実行する](./doc)。",
            0,
            [(0, 1), (5, 13)],
        ),
        ("実行する。", [1, 2, 3, 4, 13]),
        lambda line, line_start, ranges: (line, list(range(len(line)))),
    ),
    MutationCase(
        "_is_plain_ending",
        lambda: style._is_plain_ending("操作する。", _PLAIN_MATCH),
        True,
        lambda sentence, match: False,
    ),
    MutationCase(
        "_has_adjacent_kanji",
        lambda: style._has_adjacent_kanji("日本の為替", 3, 4),
        True,
        lambda line, start, end: False,
    ),
    MutationCase(
        "_is_kanji_compound",
        lambda: style._is_kanji_compound("日本の為替", 2, 4, "の為"),
        True,
        lambda line, start, end, matched_text: False,
    ),
    MutationCase(
        "_is_excluded_connector",
        lambda: style._is_excluded_connector("これまでの変更", 0, 2),
        True,
        lambda line, start, end: False,
    ),
    MutationCase(
        "_is_negative_verb_stem",
        lambda: style._is_negative_verb_stem("止め"),
        True,
        lambda stem: False,
    ),
    MutationCase(
        "_is_bracketed_enumeration",
        lambda: style._is_bracketed_enumeration(
            "これを使った出力（任意）を指定します。",
            2,
        ),
        True,
        lambda line, position: False,
    ),
)


@pytest.mark.parametrize(
    "case",
    MARKDOWN_MUTATIONS,
    ids=lambda case: case.name,
)
def test_Markdown補助処理は無効化すると契約を満たさない(case: MutationCase):
    assert case.observe() == case.expected
    with patch(
        f"blog_linter.markdown_utils.{case.name}",
        new=case.replacement,
    ):
        assert case.observe() != case.expected


@pytest.mark.parametrize(
    "case",
    STYLE_MUTATIONS,
    ids=lambda case: case.name,
)
def test_文体補助処理は無効化すると契約を満たさない(case: MutationCase):
    assert case.observe() == case.expected
    with patch(
        f"blog_linter.blog_style_checker.{case.name}",
        new=case.replacement,
    ):
        assert case.observe() != case.expected


def test_変異ケースは対象モジュールの全関数を網羅する():
    markdown_functions = {
        name
        for name, function in inspect.getmembers(markdown, inspect.isfunction)
        if function.__module__ == markdown.__name__
    }
    style_functions = {
        name
        for name, function in inspect.getmembers(style, inspect.isfunction)
        if function.__module__ == style.__name__
    }

    assert {case.name for case in MARKDOWN_MUTATIONS} == markdown_functions
    assert {case.name for case in STYLE_MUTATIONS} == style_functions
