"""Markdown の構文トークンから lint 対象外の文字範囲を計算する。"""

from html import unescape
import re

from markdown_it import MarkdownIt
from markdown_it.rules_block import StateBlock
from markdown_it.token import Token


TextRange = tuple[int, int]

_BLOCK_TOKEN_TYPES = {"front_matter", "fence", "code_block"}
_RAW_URL_START_PATTERN = re.compile(r"(?:https?://|www\.)", re.IGNORECASE)
_URL_TRAILING_PUNCTUATION = ".,;:!?。、！？"
_URL_BOUNDARY_PUNCTUATION = "。、）」』】"
_RAW_HTML_ELEMENTS = {"script", "style"}
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
    if (
        start_line != 0
        or state.blkIndent != 0
        or state.tShift[start_line] != 0
        or state.bMarks[start_line] != 0
    ):
        return False

    start = state.bMarks[start_line] + state.tShift[start_line]
    end = state.eMarks[start_line]
    if state.src[start:end].removeprefix("\ufeff") != "---":
        return False

    closing_line: int | None = None
    candidate_line = start_line + 1
    while candidate_line < end_line:
        line_start = state.bMarks[candidate_line]
        line_end = state.eMarks[candidate_line]
        line = state.src[line_start:line_end]
        if state.tShift[candidate_line] == 0 and line in {"---", "..."}:
            closing_line = candidate_line + 1
            break
        candidate_line += 1

    if closing_line is None:
        return False

    if silent:
        return True

    token = state.push("front_matter", "", 0)
    token.map = [start_line, closing_line]
    token.content = state.getLines(start_line, closing_line, 0, False)
    state.line = closing_line
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
    return parser


_MARKDOWN = _create_markdown_parser()


def parse_markdown_tokens(text: str) -> list[Token]:
    """blog lint と同じ設定で Markdown token を返す。"""
    return _MARKDOWN.parse(text)


def non_prose_ranges(text: str) -> list[TextRange]:
    """blog の lint 対象外にする全文オフセット範囲を返す。"""
    environment: dict[str, object] = {}
    tokens = _MARKDOWN.parse(text, environment)
    block_ranges = _block_non_prose_ranges(text, tokens)
    inline_ranges = _inline_non_prose_ranges(text, tokens)
    reference_ranges = _reference_definition_ranges(text, environment)
    html_ranges = _html_tag_ranges(
        text,
        _merge_ranges([
            *block_ranges,
            *inline_ranges,
            *reference_ranges,
        ]),
    )
    structural_ranges = _merge_ranges([
        *block_ranges,
        *html_ranges,
        *inline_ranges,
        *reference_ranges,
    ])
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
    """コードと front matter のブロック範囲を返す。"""
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
    link_openings: list[tuple[str, int]] = []

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
                opening = _find_unescaped(text, "<", cursor, block_end)
                tag = (
                    _scan_html_tag(text, opening, block_end)
                    if opening is not None
                    else None
                )
                if tag is not None and opening is not None:
                    cursor = tag[0]
                continue
            if child.type == "link_open":
                kind = "autolink" if child.markup == "autolink" else "link"
                opening = "<" if kind == "autolink" else "["
                position = _find_unescaped(text, opening, cursor, block_end)
                if position is not None:
                    if kind != "autolink":
                        ranges.append((position, position + 1))
                    cursor = position + 1
                    link_openings.append((kind, position))
                continue
            if child.type == "link_close":
                kind, opening = (
                    link_openings.pop()
                    if link_openings
                    else ("link", cursor)
                )
                span = _locate_link_close(
                    text,
                    kind,
                    opening,
                    cursor,
                    block_end,
                )
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
                    ranges.append(span)
                    cursor = span[1]

    return ranges


def _reference_definition_ranges(
    text: str,
    environment: dict[str, object],
) -> list[TextRange]:
    """参照リンク定義をパーサが記録した行範囲から返す。"""
    offsets = line_start_offsets(text)
    ranges: list[TextRange] = []
    seen_maps: set[tuple[int, int]] = set()
    references = environment.get("references")
    reference_values = (
        list(references.values())
        if isinstance(references, dict)
        else []
    )
    duplicates = environment.get("duplicate_refs")
    if isinstance(duplicates, list):
        reference_values.extend(duplicates)

    for reference in reference_values:
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


def _html_tag_ranges(
    text: str,
    protected_ranges: list[TextRange],
) -> list[TextRange]:
    """コード等の外にある HTML/JSX のタグ範囲だけを返す。"""
    ranges: list[TextRange] = []
    protected = _merge_ranges(protected_ranges)
    position = 0
    while position < len(text):
        opening = text.find("<", position)
        if opening < 0:
            break

        containing_range = next(
            (
                protected_range
                for protected_range in protected
                if protected_range[0] <= opening < protected_range[1]
            ),
            None,
        )
        if containing_range is not None:
            position = containing_range[1]
            continue

        tag = _scan_html_tag(text, opening, len(text))
        if tag is None:
            position = opening + 1
            continue
        end, name, is_closing, is_self_closing = tag

        if (
            name in _RAW_HTML_ELEMENTS
            and not is_closing
            and not is_self_closing
        ):
            closing_pattern = re.compile(
                rf"</\s*{re.escape(name)}(?=[\s>])",
                re.IGNORECASE,
            )
            closing_match = closing_pattern.search(text, end)
            if closing_match is not None:
                closing_tag = _scan_html_tag(
                    text,
                    closing_match.start(),
                    len(text),
                )
                if (
                    closing_tag is not None
                    and closing_tag[1] == name
                    and closing_tag[2]
                ):
                    ranges.append((opening, closing_tag[0]))
                    position = closing_tag[0]
                    continue

        ranges.append((opening, end))
        position = end
    return ranges


def _scan_html_tag(
    text: str,
    start: int,
    limit: int,
) -> tuple[int, str, bool, bool] | None:
    """一つの HTML/JSX タグを走査し、閉じ位置を確定できた場合だけ返す。"""
    if start >= limit or text[start] != "<":
        return None
    if text.startswith("<!--", start):
        closing = text.find("-->", start + 4, limit)
        if closing < 0:
            return None
        return closing + 3, "!--", False, False
    if text.startswith("<![CDATA[", start):
        closing = text.find("]]>", start + 9, limit)
        if closing < 0:
            return None
        return closing + 3, "![cdata[", False, False
    if text.startswith("<?", start):
        closing = text.find("?>", start + 2, limit)
        if closing < 0:
            return None
        return closing + 2, "?", False, False

    position = start + 1
    is_closing = position < limit and text[position] == "/"
    if is_closing:
        position += 1
    if position < limit and text[position] == ">":
        return position + 1, "", is_closing, not is_closing
    if (
        position >= limit
        or not text[position].isascii()
        or not text[position].isalpha()
    ):
        return None

    name_start = position
    position += 1
    while position < limit and (
        (
            text[position].isascii()
            and text[position].isalnum()
        )
        or text[position] in "_.:-"
    ):
        position += 1
    name = text[name_start:position].lower()
    if (
        position < limit
        and not text[position].isspace()
        and text[position] not in "/>={"
    ):
        return None

    quote = ""
    brace_depth = 0
    while position < limit:
        character = text[position]
        if quote:
            if character == quote and not _is_escaped(text, position):
                quote = ""
            position += 1
            continue
        if character in {'"', "'", "`"}:
            quote = character
        elif character == "{":
            brace_depth += 1
        elif character == "}" and brace_depth:
            brace_depth -= 1
        elif character == "\n" and brace_depth == 0:
            next_line_end = text.find("\n", position + 1, limit)
            if next_line_end < 0:
                next_line_end = limit
            continuation = text[position + 1:next_line_end]
            container = re.match(
                r"[ \t]{0,3}(?:>(?=[> \t])[ \t]?)+",
                continuation,
            )
            if container is not None:
                continuation = continuation[container.end():]
            stripped = continuation.lstrip(" \t")
            has_indent = stripped != continuation
            if (
                not stripped
                or (
                    not has_indent
                    and re.match(
                        r"(?:/?>|\{|[A-Za-z_:][A-Za-z0-9_.:-]*\s*=)",
                        stripped,
                    ) is None
                )
            ):
                return None
        elif (
            character == ">"
            and brace_depth == 0
            and not _is_blockquote_marker(text, position, start)
        ):
            before = text[start:position].rstrip()
            return position + 1, name, is_closing, before.endswith("/")
        position += 1
    return None


def _is_blockquote_marker(text: str, position: int, tag_start: int) -> bool:
    """複数行タグ内に挟まった Markdown 引用記号かを返す。"""
    line_start = text.rfind("\n", tag_start, position) + 1
    if line_start <= tag_start:
        return False
    prefix = text[line_start:position]
    next_character = text[position + 1:position + 2]
    return (
        re.fullmatch(r"[ \t]{0,3}(?:>[ \t]?)*", prefix) is not None
        and next_character in {" ", "\t", ">"}
    )


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
            if (
                character.isspace()
                or character in '<>"\''
                or character in _URL_BOUNDARY_PUNCTUATION
            ):
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
    marker_length = len(marker)
    opening = _find_backtick_run(text, marker_length, cursor, limit)
    if opening is None:
        return None
    closing = _find_backtick_run(
        text,
        marker_length,
        opening + marker_length,
        limit,
    )
    if closing is None:
        return None
    return opening, closing + marker_length


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
    opening: int,
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
        return opening, end

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
    """destination と title を区別してリンク先の閉じ括弧を探す。"""
    position = start + 1
    while position < limit and text[position].isspace():
        position += 1

    if position < limit and text[position] == "<":
        position += 1
        while position < limit:
            character = text[position]
            if character in {"\n", "\r", "<"}:
                return None
            if character == ">" and not _is_escaped(text, position):
                position += 1
                break
            position += 2 if character == "\\" else 1
        else:
            return None
    else:
        depth = 0
        while position < limit:
            character = text[position]
            if character.isspace():
                break
            if character == "(" and not _is_escaped(text, position):
                depth += 1
            elif character == ")" and not _is_escaped(text, position):
                if depth == 0:
                    return position
                depth -= 1
            position += 1
        if depth != 0:
            return None

    while position < limit and text[position].isspace():
        position += 1
    if position < limit and text[position] == ")":
        return position
    if position >= limit or text[position] not in {'"', "'", "("}:
        return None

    opening_quote = text[position]
    closing_quote = ")" if opening_quote == "(" else opening_quote
    position += 1
    while position < limit:
        character = text[position]
        if character == "\\" and position + 1 < limit:
            position += 2
            continue
        if character == closing_quote:
            position += 1
            break
        position += 1
    else:
        return None

    while position < limit and text[position].isspace():
        position += 1
    if position < limit and text[position] == ")":
        return position
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
        if character == "`":
            code_end = _advance_over_code_span(text, position, limit)
            if code_end is not None:
                position = code_end
                continue
        if character == opening:
            depth += 1
        elif character == closing:
            depth -= 1
            if depth == 0:
                return position
        position += 1
    return None


def _advance_over_code_span(
    text: str,
    start: int,
    limit: int,
) -> int | None:
    """同じ本数の閉じ列がある場合にコードスパン末尾まで進める。"""
    marker_end = start
    while marker_end < limit and text[marker_end] == "`":
        marker_end += 1
    marker_length = marker_end - start
    closing = _find_backtick_run(text, marker_length, marker_end, limit)
    if closing is None:
        return None
    return closing + marker_length


def _find_backtick_run(
    text: str,
    length: int,
    start: int,
    limit: int,
) -> int | None:
    """指定本数と完全一致するバッククォート列を探す。"""
    position = start
    while position < limit:
        position = text.find("`", position, limit)
        if position < 0:
            return None
        run_end = position
        while run_end < limit and text[run_end] == "`":
            run_end += 1
        if run_end - position == length:
            return position
        position = run_end
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
