"""blog プロファイル固有の文体チェッカー"""

import re

from blog_linter.markdown_utils import (
    line_start_offsets,
    mask_ranges,
    non_prose_ranges,
    parse_markdown_tokens,
    span_overlaps_ranges,
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
    "できない",
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
_EXCLUDED_CONNECTOR_PREFIXES = (
    "その他",
    "その際",
    "その後",
    "その上",
)
_SENTENCE_TAIL_PATTERN = re.compile(r"[^。！？!?\n]*")
_BRACKETED_ITEM_PATTERN = re.compile(r"[（(][^（()）\n]*[）)]\s*[をがはにでとへも]")
_KANJI_PATTERN = re.compile(r"[一-鿿々〆ヶ]")
_LEXICAL_STEM_PATTERN = re.compile(r"[^\s、。！？!?はがをにへとでのも]+$")
_CONTENT_CHARACTER_PATTERN = re.compile(r"[A-Za-z0-9ァ-ヶー一-鿿々〆ヶ]")
# 五段動詞の未然形（あ段）。「動かない」「読まない」など。
_NEGATIVE_VERB_STEM_ENDINGS = frozenset("わかがさたなばまらり")
# 一段動詞の未然形（い段・え段）。「止めない」「呼ばれない」など。
_ICHIDAN_NEGATIVE_STEM_ENDINGS = frozenset("いきぎしじちにひびみりえけげせぜてでねべめれ")
# 語幹が漢字で終わる形容詞。動詞の否定形と形が同じなので語で除く。
_NAI_ADJECTIVE_STEMS = (
    "少",
    "危",
    "切",
    "汚",
    "情け",
    "申し訳",
    "味気",
    "何気",
    "素っ気",
    "大人げ",
    "勿体",
    "他愛",
)
# 「書いた」（イ音便の連用形）と「流れていた」（て・で + いた）で
# 「いた」の直前に来る仮名。
_I_ONBIN_STEM_ENDINGS = frozenset("いきぎしじちにひびみりつづてで")
_CLAUSE_PARTICLES = frozenset("をがはにでとへも")


def check_blog_style(text: str) -> list[LintIssue]:
    """blog 固有の文体ルールをチェックする"""
    lines = text.split("\n")
    tokens = parse_markdown_tokens(text)
    ranges = non_prose_ranges(text)
    masked_lines = mask_ranges(text, ranges).split("\n")
    heading_maps = [
        (token.map[0], token.map[1])
        for token in tokens
        if (
            token.type == "heading_open"
            and token.map is not None
            and masked_lines[token.map[0]].strip()
        )
    ]
    heading_lines = {
        line_index
        for start, end in heading_maps
        for line_index in range(start, end)
    }
    table_lines = {
        line_index
        for token in tokens
        if token.type == "table_open" and token.map is not None
        for line_index in range(token.map[0], token.map[1])
    }
    offsets = line_start_offsets(text)
    visible_lines = [
        _visible_line(line, offsets[line_index], ranges)
        for line_index, line in enumerate(lines)
    ]
    issues = []
    issues.extend(_check_open_kanji(lines, masked_lines))
    issues.extend(_check_style_mixing(
        visible_lines,
        heading_lines,
        table_lines,
    ))
    issues.extend(_check_comma_sentence_join(lines, masked_lines))
    issues.extend(_check_section_opening_mazu(
        lines,
        masked_lines,
        heading_maps,
    ))
    return issues


def _check_open_kanji(
    lines: list[str],
    masked_lines: list[str],
) -> list[LintIssue]:
    issues = []
    for line_index, masked_line in enumerate(masked_lines):
        line = lines[line_index]
        candidates = sorted(
            (
                (match.start(), match.end(), expression)
                for expression in OPEN_KANJI_RULES
                for match in re.finditer(re.escape(expression), masked_line)
            ),
            key=lambda candidate: (candidate[0], -(candidate[1] - candidate[0])),
        )
        accepted_ranges: list[tuple[int, int]] = []
        for start, end, matched_text in candidates:
            if (
                matched_text in _KANJI_BOUNDARY_OPEN_KANJI_RULES
                and _is_kanji_compound(
                    line,
                    start,
                    end,
                    matched_text,
                )
            ):
                continue
            if any(
                start < accepted_end and accepted_start < end
                for accepted_start, accepted_end in accepted_ranges
            ):
                continue
            accepted_ranges.append((start, end))
            suggestion = OPEN_KANJI_RULES[matched_text]
            issues.append(LintIssue(
                line_number=line_index + 1,
                column=start + 1,
                matched_text=matched_text,
                category="style",
                rule_name="open-kanji",
                message=f"「{matched_text}」は「{suggestion}」と開くことを推奨します。",
                suggestion=suggestion,
            ))
    return issues


def _check_style_mixing(
    visible_lines: list[tuple[str, list[int]]],
    heading_lines: set[int],
    table_lines: set[int],
) -> list[LintIssue]:
    endings: list[tuple[str, int, int, str]] = []
    for line_index, (visible_line, source_columns) in enumerate(visible_lines):
        if _is_nominal_or_label_line(
            line_index,
            heading_lines,
            table_lines,
        ):
            continue
        for sentence_match in _SENTENCE_PATTERN.finditer(visible_line):
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
            if plain_match is None or not _is_plain_ending(
                sentence,
                plain_match,
            ):
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
    heading_maps: list[tuple[int, int]],
) -> list[LintIssue]:
    issues = []
    for _, heading_end in heading_maps:
        paragraph_index = heading_end
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


def _is_nominal_or_label_line(
    line_index: int,
    heading_lines: set[int],
    table_lines: set[int],
) -> bool:
    """パーサが見出しまたは表と認識した行かを返す。"""
    return line_index in heading_lines or line_index in table_lines


def _visible_line(
    line: str,
    line_start: int,
    ranges: list[tuple[int, int]],
) -> tuple[str, list[int]]:
    """非本文を除いた表示行と、各文字に対応する元の列を返す。"""
    characters: list[str] = []
    source_columns: list[int] = []
    for column, character in enumerate(line):
        position = line_start + column
        if span_overlaps_ranges(position, position + 1, ranges):
            continue
        characters.append(character)
        source_columns.append(column)
    return "".join(characters), source_columns


def _is_plain_ending(sentence: str, match: re.Match[str]) -> bool:
    """常体候補が語中ではなく活用語尾として現れているかを返す。"""
    ending = match.group(0).rstrip("。！？!?")
    stem_match = _LEXICAL_STEM_PATTERN.search(sentence[:match.start()])
    stem = stem_match.group(0) if stem_match is not None else ""
    if ending == "ない":
        return _is_negative_verb_stem(stem)
    if ending == "いた":
        # 「まないた」のような名詞を拾わないよう、イ音便の語幹だけを数える。
        return (
            bool(stem)
            and _KANJI_PATTERN.search(stem) is not None
            and (
                _KANJI_PATTERN.fullmatch(stem[-1]) is not None
                or stem[-1] in _I_ONBIN_STEM_ENDINGS
            )
        )
    if ending == "した":
        return _CONTENT_CHARACTER_PATTERN.search(stem) is not None
    return True


def _is_negative_verb_stem(stem: str) -> bool:
    """「〜ない。」の直前が動詞の未然形かを返す（形容詞・名詞は数えない）。"""
    if not stem or _KANJI_PATTERN.search(stem) is None:
        # 仮名だけの語（「つまらない」「まないた」）は動詞と区別できない。
        return False
    if any(stem.endswith(adjective) for adjective in _NAI_ADJECTIVE_STEMS):
        return False
    last_character = stem[-1]
    return (
        last_character in _NEGATIVE_VERB_STEM_ENDINGS
        or last_character in _ICHIDAN_NEGATIVE_STEM_ENDINGS
        # 「出ない」のように語幹が漢字だけで終わる一段動詞。
        or _KANJI_PATTERN.fullmatch(last_character) is not None
    )


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
    connector = line[start:end]
    following = line[end:end + 1]
    # 「または」は列挙の接続語。「これは」「それは」は次の文の主語なので残す。
    if connector == "また" and following == "は":
        return True
    if (
        connector in {"これ", "それ"}
        and following
        and not following.isspace()
        and following not in _CLAUSE_PARTICLES
        and following not in "、。！？!?"
    ):
        return True
    if _is_bracketed_enumeration(line, end):
        return True
    suffix = line[start:]
    return any(
        suffix.startswith(prefix)
        for prefix in _EXCLUDED_CONNECTOR_PREFIXES
    )


def _is_bracketed_enumeration(line: str, position: int) -> bool:
    """接続語の後ろにも括弧付きの名詞句が続く、一文の中の並べ立てかを返す。"""
    tail = _SENTENCE_TAIL_PATTERN.match(line, position)
    if tail is None:
        return False
    return _BRACKETED_ITEM_PATTERN.search(tail.group(0)) is not None
