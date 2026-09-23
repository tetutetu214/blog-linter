"""Markdown の構文トークンから lint 対象外の文字範囲を計算する。"""

from html import unescape
import re

from markdown_it import MarkdownIt
from markdown_it.rules_block import StateBlock
from markdown_it.token import Token


TextRange = tuple[int, int]

_BLOCK_TOKEN_TYPES = {"front_matter", "fence", "code_block", "html_block"}
_RAW_URL_START_PATTERN = re.compile(r"(?:https?://|www\.)", re.IGNORECASE)
_URL_TRAILING_PUNCTUATION = ".,;:!?。、！？"
_INLINE_FORMAT_TOKEN_TYPES = {
    "em_open",
    "em_close",
    "strong_open",
    "strong_close",
    "s_open",
    "s_close",
}


def _front_matter_rule(
    state: StateBlock,
    start_line: int,
    end_line: int,
    silent: bool,
) -> bool:
    """文書先頭の YAML front matter をブロックトークンにする。"""
    if start_line != 0:
        return False

    start = state.bMarks[start_line] + state.tShift[start_line]
    end = state.eMarks[start_line]
    if state.src[start:end].removeprefix("\ufeff") != "---":
        return False

    next_line = start_line + 1
    while next_line < end_line:
        line_start = state.bMarks[next_line]
        line_end = state.eMarks[next_line]
        line = state.src[line_start:line_end]
        if state.tShift[next_line] == 0 and line in {"---", "..."}:
            next_line += 1
            break
        next_line += 1

    if silent:
        return True

    token = state.push("front_matter", "", 0)
    token.map = [start_line, next_line]
    token.content = state.getLines(start_line, next_line, 0, False)
    state.line = next_line
    return True


def _self_closing_html_block_rule(
    state: StateBlock,
    start_line: int,
    end_line: int,
    silent: bool,
) -> bool:
    """自己完結する HTML/JSX タグだけを一つのブロックにする。"""
    if state.sCount[start_line] - state.blkIndent >= 4:
        return False

    start = state.bMarks[start_line] + state.tShift[start_line]
    first_line_end = state.eMarks[start_line]
    if start >= first_line_end or state.src[start] != "<":
        return False

    name_start = start + 1
    if name_start >= first_line_end or not state.src[name_start].isalpha():
        return False

    name_end = name_start + 1
    while name_end < first_line_end and (
        state.src[name_end].isalnum() or state.src[name_end] in "_.:-"
    ):
        name_end += 1
    if (
        name_end < first_line_end
        and not state.src[name_end].isspace()
        and state.src[name_end] not in "/>"
    ):
        return False

    quote = ""
    brace_depth = 0
    position = name_end
    closing_position: int | None = None
    while position < len(state.src):
        character = state.src[position]
        if quote:
            if character == quote and not _is_escaped(state.src, position):
                quote = ""
            position += 1
            continue
        if character in {'"', "'", "`"}:
            quote = character
        elif character == "{":
            brace_depth += 1
        elif character == "}" and brace_depth:
            brace_depth -= 1
        elif (
            character == "/"
            and brace_depth == 0
            and position + 1 < len(state.src)
            and state.src[position + 1] == ">"
        ):
            closing_position = position + 2
            break
        elif character == ">" and brace_depth == 0:
            # 開始タグが `/>` ではなく `>` で閉じた＝自己終了ではない。
            # ここで抜けないと、次に現れる `/>` まで走査が続き、
            # 間にある本文を丸ごと飲み込む（`<style>` が 85 行先の
            # `<img ... />` まで伸び、その間の段落が検査されなかった。2026-09-23）。
            # 通常の html_block 規則に任せる。
            return False
        position += 1

    if closing_position is None:
        return False

    closing_line = start_line
    while (
        closing_line < end_line
        and closing_position > state.eMarks[closing_line]
    ):
        closing_line += 1
    if closing_line >= end_line:
        return False
    if state.src[closing_position:state.eMarks[closing_line]].strip():
        return False

    next_line = closing_line + 1
    if silent:
        return True

    token = state.push("html_block", "", 0)
    token.map = [start_line, next_line]
    token.content = state.getLines(start_line, next_line, 0, False)
    state.line = next_line
    return True


def _create_markdown_parser() -> MarkdownIt:
    """blog lint 用の CommonMark パーサを作る。"""
    parser = MarkdownIt("commonmark").enable("table")
    parser.block.ruler.before(
        "table",
        "front_matter",
        _front_matter_rule,
        {"alt": []},
    )
    # CommonMark の HTML block は自己終了タグの後ろの本文まで空行まで
    # 取り込むため、MDX の自己終了タグだけは一タグ単位で先に閉じる。
    parser.block.ruler.before(
        "html_block",
        "self_closing_html_block",
        _self_closing_html_block_rule,
        {"alt": ["paragraph", "reference", "blockquote"]},
    )
    return parser


_MARKDOWN = _create_markdown_parser()


def non_prose_ranges(text: str) -> list[TextRange]:
    """blog の lint 対象外にする全文オフセット範囲を返す。"""
    environment: dict[str, object] = {}
    tokens = _MARKDOWN.parse(text, environment)
    ranges = [
        *_block_non_prose_ranges(text, tokens),
        *_inline_non_prose_ranges(text, tokens),
        *_reference_definition_ranges(text, environment),
    ]
    structural_ranges = _merge_ranges(ranges)
    return _merge_ranges([
        *structural_ranges,
        *_raw_url_ranges(text, structural_ranges),
    ])


def span_overlaps_ranges(
    start: int,
    end: int,
    ranges: list[TextRange],
) -> bool:
    """指定範囲が lint 対象外の範囲と重なるかを返す。"""
    return any(
        start < range_end and range_start < end
        for range_start, range_end in ranges
    )


def mask_ranges(text: str, ranges: list[TextRange]) -> str:
    """改行と位置情報を保ったまま指定範囲を空白に置き換える。"""
    characters = list(text)
    for start, end in ranges:
        for position in range(start, end):
            if characters[position] not in {"\n", "\r"}:
                characters[position] = " "
    return "".join(characters)


def line_start_offsets(text: str) -> list[int]:
    """各物理行の先頭に対応する全文オフセットを返す。"""
    offsets = [0]
    offsets.extend(match.end() for match in re.finditer(r"\n", text))
    return offsets


def _block_non_prose_ranges(
    text: str,
    tokens: list[Token],
) -> list[TextRange]:
    """コード・HTML・front matter のブロック範囲を返す。"""
    offsets = line_start_offsets(text)
    return [
        _line_map_range(text, offsets, token.map)
        for token in tokens
        if token.type in _BLOCK_TOKEN_TYPES and token.map is not None
    ]


def _inline_non_prose_ranges(
    text: str,
    tokens: list[Token],
) -> list[TextRange]:
    """インライン子トークンをソース順に追って非本文範囲を返す。"""
    offsets = line_start_offsets(text)
    ranges: list[TextRange] = []
    cursor = 0
    link_kinds: list[str] = []

    for token in tokens:
        if token.type != "inline" or token.map is None:
            continue
        block_start, block_end = _line_map_range(text, offsets, token.map)
        cursor = max(cursor, block_start)

        for child in token.children or []:
            if child.type == "text":
                cursor = _advance_over_rendered_text(
                    text,
                    child.content,
                    cursor,
                    block_end,
                )
                continue
            if child.type in {"softbreak", "hardbreak"}:
                newline = text.find("\n", cursor, block_end)
                cursor = block_end if newline < 0 else newline + 1
                continue
            if child.type == "code_inline":
                span = _locate_code_span(
                    text,
                    child.markup,
                    cursor,
                    block_end,
                )
                if span is not None:
                    ranges.append(span)
                    cursor = span[1]
                continue
            if child.type == "image":
                span = _locate_image_span(text, cursor, block_end)
                if span is not None:
                    ranges.append(span)
                    cursor = span[1]
                continue
            if child.type == "html_inline":
                span = _locate_literal(
                    text,
                    child.content,
                    cursor,
                    block_end,
                )
                if span is not None:
                    ranges.append(span)
                    cursor = span[1]
                continue
            if child.type == "link_open":
                kind = "autolink" if child.markup == "autolink" else "link"
                opening = "<" if kind == "autolink" else "["
                position = _find_unescaped(text, opening, cursor, block_end)
                if position is not None:
                    ranges.append((position, position + 1))
                    cursor = position + 1
                link_kinds.append(kind)
                continue
            if child.type == "link_close":
                kind = link_kinds.pop() if link_kinds else "link"
                span = _locate_link_close(text, kind, cursor, block_end)
                if span is not None:
                    ranges.append(span)
                    cursor = span[1]
                continue
            if child.type in _INLINE_FORMAT_TOKEN_TYPES and child.markup:
                span = _locate_literal(
                    text,
                    child.markup,
                    cursor,
                    block_end,
                )
                if span is not None:
                    cursor = span[1]

    return ranges


def _reference_definition_ranges(
    text: str,
    environment: dict[str, object],
) -> list[TextRange]:
    """参照リンク定義をパーサが記録した行範囲から返す。"""
    references = environment.get("references")
    if not isinstance(references, dict):
        return []

    offsets = line_start_offsets(text)
    ranges: list[TextRange] = []
    seen_maps: set[tuple[int, int]] = set()
    for reference in references.values():
        if not isinstance(reference, dict):
            continue
        line_map = reference.get("map")
        if (
            not isinstance(line_map, list)
            or len(line_map) != 2
            or not all(isinstance(value, int) for value in line_map)
        ):
            continue
        map_key = (line_map[0], line_map[1])
        if map_key in seen_maps:
            continue
        seen_maps.add(map_key)
        ranges.append(_line_map_range(text, offsets, line_map))
    return ranges


def _raw_url_ranges(
    text: str,
    protected_ranges: list[TextRange],
) -> list[TextRange]:
    """本文 text トークンに残った素の URL の範囲を返す。"""
    searchable_text = mask_ranges(text, protected_ranges)
    ranges: list[TextRange] = []
    for match in _RAW_URL_START_PATTERN.finditer(searchable_text):
        position = match.end()
        brackets: list[str] = []
        while position < len(searchable_text):
            character = searchable_text[position]
            if character.isspace() or character in '<>"\'':
                break
            if character in "([{":
                brackets.append({"(": ")", "[": "]", "{": "}"}[character])
            elif character in ")]}":
                if not brackets or brackets[-1] != character:
                    break
                brackets.pop()
            position += 1

        while (
            position > match.start()
            and searchable_text[position - 1] in _URL_TRAILING_PUNCTUATION
        ):
            position -= 1
        ranges.append((match.start(), position))
    return ranges


def _line_map_range(
    text: str,
    offsets: list[int],
    line_map: list[int],
) -> TextRange:
    """markdown-it の行 map を全文オフセットへ変換する。"""
    start_line, end_line = line_map
    start = offsets[start_line] if start_line < len(offsets) else len(text)
    end = offsets[end_line] if end_line < len(offsets) else len(text)
    return start, end


def _advance_over_rendered_text(
    source: str,
    rendered: str,
    cursor: int,
    limit: int,
) -> int:
    """エスケープと文字参照を考慮して text 子の末尾まで進める。"""
    source_position = cursor
    rendered_position = 0
    while rendered_position < len(rendered) and source_position < limit:
        if (
            source[source_position] == "\\"
            and source_position + 1 < limit
            and source[source_position + 1] == rendered[rendered_position]
        ):
            source_position += 2
            rendered_position += 1
            continue
        if source[source_position] == "&":
            semicolon = source.find(";", source_position + 1, limit)
            if semicolon >= 0:
                decoded = unescape(source[source_position:semicolon + 1])
                if rendered.startswith(decoded, rendered_position):
                    source_position = semicolon + 1
                    rendered_position += len(decoded)
                    continue
        if source[source_position] == rendered[rendered_position]:
            source_position += 1
            rendered_position += 1
            continue
        source_position += 1
    return source_position


def _locate_code_span(
    text: str,
    marker: str,
    cursor: int,
    limit: int,
) -> TextRange | None:
    """code_inline 子に対応するソース範囲を返す。"""
    opening = text.find(marker, cursor, limit)
    if opening < 0:
        return None
    closing = text.find(marker, opening + len(marker), limit)
    if closing < 0:
        return None
    return opening, closing + len(marker)


def _locate_image_span(
    text: str,
    cursor: int,
    limit: int,
) -> TextRange | None:
    """image 子に対応するインライン画像全体の範囲を返す。"""
    opening = _find_unescaped(text, "![", cursor, limit)
    if opening is None:
        return None
    label_end = _find_matching_delimiter(text, opening + 1, "[", "]", limit)
    if label_end is None:
        return None

    end = label_end + 1
    if end < limit and text[end] == "(":
        destination_end = _find_link_parenthesis_end(text, end, limit)
        if destination_end is not None:
            end = destination_end + 1
    elif end < limit and text[end] == "[":
        reference_end = _find_matching_delimiter(text, end, "[", "]", limit)
        if reference_end is not None:
            end = reference_end + 1
    return opening, end


def _locate_link_close(
    text: str,
    kind: str,
    cursor: int,
    limit: int,
) -> TextRange | None:
    """link_close と後続するリンク先・参照ラベルの範囲を返す。"""
    closing_character = ">" if kind == "autolink" else "]"
    closing = _find_unescaped(text, closing_character, cursor, limit)
    if closing is None:
        return None
    end = closing + 1
    if kind == "autolink":
        return closing, end

    if end < limit and text[end] == "(":
        destination_end = _find_link_parenthesis_end(text, end, limit)
        if destination_end is not None:
            end = destination_end + 1
    elif end < limit and text[end] == "[":
        reference_end = _find_matching_delimiter(text, end, "[", "]", limit)
        if reference_end is not None:
            end = reference_end + 1
    return closing, end


def _locate_literal(
    text: str,
    literal: str,
    cursor: int,
    limit: int,
) -> TextRange | None:
    """現在位置より後ろにあるトークン文字列の範囲を返す。"""
    start = text.find(literal, cursor, limit)
    if start < 0:
        return None
    return start, start + len(literal)


def _find_link_parenthesis_end(
    text: str,
    start: int,
    limit: int,
) -> int | None:
    """引用符と入れ子を考慮してリンク先の閉じ括弧を探す。"""
    depth = 1
    quote = ""
    position = start + 1
    while position < limit:
        character = text[position]
        if quote:
            if character == quote and not _is_escaped(text, position):
                quote = ""
            position += 1
            continue
        if character in {'"', "'"}:
            quote = character
        elif character == "(" and not _is_escaped(text, position):
            depth += 1
        elif character == ")" and not _is_escaped(text, position):
            depth -= 1
            if depth == 0:
                return position
        position += 1
    return None


def _find_matching_delimiter(
    text: str,
    start: int,
    opening: str,
    closing: str,
    limit: int,
) -> int | None:
    """エスケープと入れ子を考慮して対応する閉じ記号を探す。"""
    depth = 1
    position = start + 1
    while position < limit:
        character = text[position]
        if character == "\\":
            position += 2
            continue
        if character == opening:
            depth += 1
        elif character == closing:
            depth -= 1
            if depth == 0:
                return position
        position += 1
    return None


def _find_unescaped(
    text: str,
    needle: str,
    start: int,
    limit: int,
) -> int | None:
    """カーソル以降にあるエスケープされていない文字列を探す。"""
    position = start
    while position < limit:
        position = text.find(needle, position, limit)
        if position < 0:
            return None
        if not _is_escaped(text, position):
            return position
        position += len(needle)
    return None


def _is_escaped(text: str, position: int) -> bool:
    """指定位置の文字がバックスラッシュでエスケープされているか返す。"""
    backslash_count = 0
    position -= 1
    while position >= 0 and text[position] == "\\":
        backslash_count += 1
        position -= 1
    return backslash_count % 2 == 1


def _merge_ranges(ranges: list[TextRange]) -> list[TextRange]:
    """重複または隣接する範囲を統合する。"""
    merged: list[TextRange] = []
    for start, end in sorted(ranges):
        if start >= end:
            continue
        if not merged or merged[-1][1] < start:
            merged.append((start, end))
            continue
        previous_start, previous_end = merged[-1]
        merged[-1] = (previous_start, max(previous_end, end))
    return merged
