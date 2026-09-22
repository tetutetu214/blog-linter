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
_SENTENCE_PATTERN = re.compile(r"[^。！？!?\n]*[。！？!?]+")
_POLITE_ENDING_PATTERN = re.compile(
    r"(?:ませんでした|でした|ました|ません|でしょう|ください|です|ます)"
    r"[。！？!?]+$"
)
_PLAIN_ENDING_PATTERN = re.compile(
    r"(?:ではなかった|じゃなかった|である|ではない|じゃない|"
    r"なかった|しない|する|した|だった|ない|だ|た|る|う|く|ぐ|"
    r"す|つ|ぬ|ぶ|む)[。！？!?]+$"
)
_COMMA_SENTENCE_JOIN_PATTERN = re.compile(
    r"[）)]、\s*(?:これ|それ|あれ|この|その|一方|ただし|なお|"
    r"また(?!は)|次に|そして)"
)
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
                matched_text.startswith("事")
                and match.start() > 0
                and _KANJI_PATTERN.fullmatch(line[match.start() - 1])
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
        if _is_nominal_or_label_line(masked_line):
            continue
        line = lines[line_index]
        for sentence_match in _SENTENCE_PATTERN.finditer(masked_line):
            sentence = sentence_match.group(0)
            polite_match = _POLITE_ENDING_PATTERN.search(sentence)
            if polite_match is not None:
                start = sentence_match.start() + polite_match.start()
                end = sentence_match.start() + polite_match.end()
                endings.append((
                    "polite",
                    line_index,
                    start,
                    line[start:end],
                ))
                continue
            plain_match = _PLAIN_ENDING_PATTERN.search(sentence)
            if plain_match is None:
                continue
            start = sentence_match.start() + plain_match.start()
            end = sentence_match.start() + plain_match.end()
            endings.append((
                "plain",
                line_index,
                start,
                line[start:end],
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
    has_sentence = re.search(r"[。！？!?]", stripped) is not None
    if "|" in stripped:
        return not has_sentence
    list_match = _LIST_ITEM_PATTERN.match(line)
    if list_match is None:
        return False
    return not has_sentence
