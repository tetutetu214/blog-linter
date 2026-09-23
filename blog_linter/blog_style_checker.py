"""blog プロファイル固有の文体チェッカー"""

import re

from blog_linter.markdown_utils import (
    mask_ranges,
    non_prose_ranges,
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
_KANJI_BOUNDARY_OPEN_KANJI_RULES = {
    "事が出来る",
    "事ができる",
    "の為",
}
_SENTENCE_PATTERN = re.compile(r"[^。！？!?\n]*[。！？!?]+")
_POLITE_ENDING_PATTERN = re.compile(
    r"(?:ませんでした|でした|ました|ません|でしょう|ください|です|ます)"
    r"[。！？!?]+$"
)
_PLAIN_ENDINGS = (
    "である",
    "だ",
    "する",
    "した",
    "しない",
    "できる",
    "できた",
    "なる",
    "なった",
    "ある",
    "ない",
    "いる",
    "いた",
    "書く",
    "読む",
    "使う",
)
# 形容詞の終止形は体言止めと機械的に区別できないため、意図的に数えない。
_PLAIN_ENDING_PATTERN = re.compile(
    rf"(?:{'|'.join(re.escape(ending) for ending in _PLAIN_ENDINGS)})"
    r"[。！？!?]+$"
)
_COMMA_SENTENCE_JOIN_PATTERN = re.compile(
    r"[）)]、\s*(?P<connector>そのため|したがって|しかし|ただし|"
    r"これ|それ|なお|また)"
)
_EXCLUDED_CONNECTOR_PREFIXES = ("その他", "その際", "その後", "その上")
_EMPHASIS_MARKERS = ("**", "__", "~~", "*", "_")
_HEADING_PATTERN = re.compile(r"^\s{0,3}#{1,6}\s+")
_LIST_ITEM_PATTERN = re.compile(r"^\s*(?:[-+*]|\d+[.)])\s+")
_KANJI_PATTERN = re.compile(r"[一-鿿々〆ヶ]")


def check_blog_style(text: str) -> list[LintIssue]:
    """blog 固有の文体ルールをチェックする"""
    lines = text.split("\n")
    ranges = non_prose_ranges(text)
    masked_lines = mask_ranges(text, ranges).split("\n")
    issues = []
    issues.extend(_check_open_kanji(lines, masked_lines))
    issues.extend(_check_style_mixing(lines, masked_lines))
    issues.extend(_check_comma_sentence_join(lines, masked_lines))
    issues.extend(_check_section_opening_mazu(lines, masked_lines))
    return issues


def _check_open_kanji(
    lines: list[str],
    masked_lines: list[str],
) -> list[LintIssue]:
    issues = []
    for line_index, masked_line in enumerate(masked_lines):
        line = lines[line_index]
        for match in _OPEN_KANJI_PATTERN.finditer(masked_line):
            matched_text = line[match.start():match.end()]
            if (
                matched_text in _KANJI_BOUNDARY_OPEN_KANJI_RULES
                and _is_kanji_compound(
                    line,
                    match.start(),
                    match.end(),
                    matched_text,
                )
            ):
                continue
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
    masked_lines: list[str],
) -> list[LintIssue]:
    endings: list[tuple[str, int, int, str]] = []
    for line_index, masked_line in enumerate(masked_lines):
        if _is_nominal_or_label_line(lines[line_index]):
            continue
        styled_line, source_columns = _remove_emphasis_markers(masked_line)
        for sentence_match in _SENTENCE_PATTERN.finditer(styled_line):
            sentence = sentence_match.group(0)
            polite_match = _POLITE_ENDING_PATTERN.search(sentence)
            if polite_match is not None:
                start = sentence_match.start() + polite_match.start()
                endings.append((
                    "polite",
                    line_index,
                    source_columns[start],
                    polite_match.group(0),
                ))
                continue
            plain_match = _PLAIN_ENDING_PATTERN.search(sentence)
            if plain_match is None:
                continue
            start = sentence_match.start() + plain_match.start()
            endings.append((
                "plain",
                line_index,
                source_columns[start],
                plain_match.group(0),
            ))

    polite_count = sum(style == "polite" for style, *_ in endings)
    plain_count = sum(style == "plain" for style, *_ in endings)
    if polite_count == 0 or plain_count == 0:
        return []

    minority_style = "plain" if polite_count > plain_count else "polite"
    issues = []
    for style, line_index, column, matched_text in endings:
        if polite_count != plain_count and style != minority_style:
            continue
        if polite_count == plain_count:
            suggestion = "敬体か常体のどちらか"
            message = "敬体と常体が混在しています。文体をどちらかに統一してください。"
        elif minority_style == "plain":
            suggestion = "敬体（です・ます調）"
            message = f"記事の多数派に合わせ、{suggestion}に統一してください。"
        else:
            suggestion = "常体（だ・である調）"
            message = f"記事の多数派に合わせ、{suggestion}に統一してください。"
        issues.append(LintIssue(
            line_number=line_index + 1,
            column=column + 1,
            matched_text=matched_text,
            category="style",
            rule_name="style-mixing",
            message=message,
            suggestion=suggestion,
        ))
    return issues


def _check_comma_sentence_join(
    lines: list[str],
    masked_lines: list[str],
) -> list[LintIssue]:
    issues = []
    for line_index, masked_line in enumerate(masked_lines):
        line = lines[line_index]
        for match in _COMMA_SENTENCE_JOIN_PATTERN.finditer(masked_line):
            if _is_excluded_connector(
                masked_line,
                match.start("connector"),
                match.end("connector"),
            ):
                continue
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
    masked_lines: list[str],
) -> list[LintIssue]:
    issues = []
    for line_index, masked_line in enumerate(masked_lines):
        if not _HEADING_PATTERN.match(masked_line):
            continue

        paragraph_index = line_index + 1
        while (
            paragraph_index < len(masked_lines)
            and not masked_lines[paragraph_index].strip()
        ):
            paragraph_index += 1
        if paragraph_index >= len(masked_lines):
            continue

        paragraph = lines[paragraph_index]
        masked_paragraph = masked_lines[paragraph_index]
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
    if "|" in stripped:
        return True
    return _LIST_ITEM_PATTERN.match(line) is not None


def _remove_emphasis_markers(line: str) -> tuple[str, list[int]]:
    """強調記号を除いた文字列と元の列位置を返す。"""
    characters: list[str] = []
    source_columns: list[int] = []
    position = 0
    while position < len(line):
        marker = next(
            (
                candidate
                for candidate in _EMPHASIS_MARKERS
                if line.startswith(candidate, position)
            ),
            None,
        )
        if marker is not None:
            position += len(marker)
            continue
        characters.append(line[position])
        source_columns.append(position)
        position += 1
    return "".join(characters), source_columns


def _has_adjacent_kanji(line: str, start: int, end: int) -> bool:
    """対象表記の直前または直後が漢字かを返す。"""
    before_is_kanji = (
        start > 0 and _KANJI_PATTERN.fullmatch(line[start - 1]) is not None
    )
    after_is_kanji = (
        end < len(line) and _KANJI_PATTERN.fullmatch(line[end]) is not None
    )
    return before_is_kanji or after_is_kanji


def _is_kanji_compound(
    line: str,
    start: int,
    end: int,
    matched_text: str,
) -> bool:
    """置換すると壊れる漢字複合語の一部かを返す。"""
    if not _has_adjacent_kanji(line, start, end):
        return False
    if matched_text == "の為":
        return (
            end < len(line)
            and _KANJI_PATTERN.fullmatch(line[end]) is not None
        )
    return True


def _is_excluded_connector(line: str, start: int, end: int) -> bool:
    """列挙語など、文頭の接続語ではない一致かを返す。"""
    if end < len(line) and line[end] == "は":
        return True
    suffix = line[start:]
    return any(
        suffix.startswith(prefix)
        for prefix in _EXCLUDED_CONNECTOR_PREFIXES
    )
