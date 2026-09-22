"""blog プロファイル固有の文体チェッカー"""

import re

from blog_linter.markdown_utils import (
    excluded_line_indexes,
    mask_ranges,
    non_prose_ranges_by_line,
)
from blog_linter.models import LintIssue


OPEN_KANJI_RULES = {
    "事が出来る": "ことができる",
    "事ができる": "ことができる",
    "出来ます": "できます",
    "出来ません": "できません",
    "出来る": "できる",
    "出来ない": "できない",
    "出来た": "できた",
    "の為": "のため",
}

_OPEN_KANJI_PATTERN = re.compile(
    "|".join(
        re.escape(expression)
        for expression in sorted(OPEN_KANJI_RULES, key=len, reverse=True)
    )
)
_POLITE_ENDING_PATTERN = re.compile(
    r"(?:でした|ました|ません|でしょう|ください|です|ます)[。！？!?]"
)
_PLAIN_ENDING_PATTERN = re.compile(r"(?:である|する|だ)[。！？!?]")
_COMMA_SENTENCE_JOIN_PATTERN = re.compile(
    r"[）)]、\s*(?:これ|それ|あれ|この|その|一方|ただし|なお|また|次に|そして)"
)
_HEADING_PATTERN = re.compile(r"^\s{0,3}#{1,6}\s+")
_LIST_ITEM_PATTERN = re.compile(r"^\s*(?:[-+*]|\d+[.)])\s+")


def check_blog_style(text: str) -> list[LintIssue]:
    """blog 固有の文体ルールをチェックする"""
    lines = text.split("\n")
    excluded_lines = excluded_line_indexes(lines)
    ranges_by_line = non_prose_ranges_by_line(
        lines,
        include_mdx_attributes=True,
    )
    issues = []
    issues.extend(_check_open_kanji(lines, excluded_lines, ranges_by_line))
    issues.extend(_check_style_mixing(lines, excluded_lines, ranges_by_line))
    issues.extend(_check_comma_sentence_join(
        lines,
        excluded_lines,
        ranges_by_line,
    ))
    issues.extend(_check_section_opening_mazu(
        lines,
        excluded_lines,
        ranges_by_line,
    ))
    return issues


def _check_open_kanji(
    lines: list[str],
    excluded_lines: set[int],
    ranges_by_line: list[list[tuple[int, int]]],
) -> list[LintIssue]:
    issues = []
    for line_index, line in enumerate(lines):
        if line_index in excluded_lines:
            continue
        masked_line = mask_ranges(line, ranges_by_line[line_index])
        for match in _OPEN_KANJI_PATTERN.finditer(masked_line):
            matched_text = line[match.start():match.end()]
            suggestion = OPEN_KANJI_RULES[matched_text]
            issues.append(LintIssue(
                line_number=line_index + 1,
                column=match.start() + 1,
                matched_text=matched_text,
                category="style",
                rule_name="open-kanji",
                message=f"「{matched_text}」は「{suggestion}」と開くことを推奨します。",
                suggestion=suggestion,
            ))
    return issues


def _check_style_mixing(
    lines: list[str],
    excluded_lines: set[int],
    ranges_by_line: list[list[tuple[int, int]]],
) -> list[LintIssue]:
    endings: list[tuple[str, int, int, str]] = []
    for line_index, line in enumerate(lines):
        if line_index in excluded_lines or _is_nominal_or_label_line(line):
            continue
        masked_line = mask_ranges(line, ranges_by_line[line_index])
        for match in _POLITE_ENDING_PATTERN.finditer(masked_line):
            endings.append(("polite", line_index, match.start(), match.group(0)))
        for match in _PLAIN_ENDING_PATTERN.finditer(masked_line):
            endings.append(("plain", line_index, match.start(), match.group(0)))

    polite_count = sum(style == "polite" for style, *_ in endings)
    plain_count = sum(style == "plain" for style, *_ in endings)
    if polite_count == 0 or plain_count == 0 or polite_count == plain_count:
        return []

    minority_style = "plain" if polite_count > plain_count else "polite"
    suggestion = "敬体（です・ます調）" if minority_style == "plain" else "常体（だ・である調）"
    issues = []
    for style, line_index, column, matched_text in endings:
        if style != minority_style:
            continue
        issues.append(LintIssue(
            line_number=line_index + 1,
            column=column + 1,
            matched_text=matched_text,
            category="style",
            rule_name="style-mixing",
            message=f"記事の多数派に合わせ、{suggestion}に統一してください。",
            suggestion=suggestion,
        ))
    return issues


def _check_comma_sentence_join(
    lines: list[str],
    excluded_lines: set[int],
    ranges_by_line: list[list[tuple[int, int]]],
) -> list[LintIssue]:
    issues = []
    for line_index, line in enumerate(lines):
        if line_index in excluded_lines:
            continue
        masked_line = mask_ranges(line, ranges_by_line[line_index])
        for match in _COMMA_SENTENCE_JOIN_PATTERN.finditer(masked_line):
            matched_text = line[match.start():match.end()]
            suggestion = matched_text.replace("、", "。", 1)
            issues.append(LintIssue(
                line_number=line_index + 1,
                column=match.start() + 1,
                matched_text=matched_text,
                category="style",
                rule_name="comma-sentence-join",
                message="閉じ括弧後の読点で別の文をつないでいます。",
                suggestion=suggestion,
            ))
    return issues


def _check_section_opening_mazu(
    lines: list[str],
    excluded_lines: set[int],
    ranges_by_line: list[list[tuple[int, int]]],
) -> list[LintIssue]:
    issues = []
    for line_index, line in enumerate(lines):
        if line_index in excluded_lines or not _HEADING_PATTERN.match(line):
            continue

        paragraph_index = line_index + 1
        while paragraph_index < len(lines) and not lines[paragraph_index].strip():
            paragraph_index += 1
        if paragraph_index >= len(lines) or paragraph_index in excluded_lines:
            continue

        paragraph = lines[paragraph_index]
        masked_paragraph = mask_ranges(
            paragraph,
            ranges_by_line[paragraph_index],
        )
        match = re.match(r"\s*まず[、,]", masked_paragraph)
        if match is None:
            continue
        start = paragraph.find("まず", 0, match.end())
        issues.append(LintIssue(
            line_number=paragraph_index + 1,
            column=start + 1,
            matched_text=paragraph[start:match.end()],
            category="style",
            rule_name="section-opening-mazu",
            message="見出し直後の段落を「まず、」以外で始めることを推奨します。",
            suggestion="対象や目的を直接説明する",
        ))
    return issues


def _is_nominal_or_label_line(line: str) -> bool:
    """見出し・表・箇条書きラベルの体言止めを判定する"""
    stripped = line.strip()
    if _HEADING_PATTERN.match(line):
        return True
    if stripped.startswith("|") and stripped.endswith("|"):
        return True
    list_match = _LIST_ITEM_PATTERN.match(line)
    if list_match is None:
        return False
    content = line[list_match.end():].strip().strip("*_")
    return not re.search(r"[。！？!?]$", content)
