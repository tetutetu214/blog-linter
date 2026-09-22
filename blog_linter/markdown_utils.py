"""Markdown 内で lint 対象外にする文字範囲を計算する共通処理"""

import re


TextRange = tuple[int, int]

_FRONTMATTER_OPEN_PATTERN = re.compile(r"^\ufeff?---[ \t]*$")
_FRONTMATTER_CLOSE_PATTERN = re.compile(r"^(?:---|\.\.\.)[ \t]*$")
_FENCE_PATTERN = re.compile(r"(?P<marker>`{3,}|~{3,})(?P<suffix>.*)$")
_BACKTICK_RUN_PATTERN = re.compile(r"`+")
_RAW_URL_PATTERN = re.compile(r"(?:https?://|www\.)[^\s<>\"'\])}]+")
_MARKDOWN_LINK_START_PATTERN = re.compile(r"!?\[")
_JSX_TAG_START_PATTERN = re.compile(
    r"<(?P<closing>/)?(?P<name>[A-Za-z][A-Za-z0-9_.:-]*)"
)
_JSX_ATTRIBUTE_NAME_PATTERN = re.compile(r"[A-Za-z_:][A-Za-z0-9_.:-]*")
_JSX_NON_PROSE_ATTRIBUTES = {"alt", "title"}


def non_prose_ranges(text: str) -> list[TextRange]:
    """blog の lint 対象外にする全文オフセット範囲を返す"""
    frontmatter_ranges = _frontmatter_ranges(text)
    fenced_code_ranges = _fenced_code_ranges(text, frontmatter_ranges)
    structural_ranges = _merge_ranges(
        [*frontmatter_ranges, *fenced_code_ranges]
    )

    inline_code_ranges = _inline_code_ranges(text, structural_ranges)
    code_ranges = _merge_ranges([*structural_ranges, *inline_code_ranges])

    url_ranges = _url_ranges(text, code_ranges)
    image_ranges = _markdown_image_ranges(text, code_ranges)
    jsx_ranges = _jsx_attribute_ranges(
        text,
        _merge_ranges([*code_ranges, *url_ranges, *image_ranges]),
    )
    return _merge_ranges(
        [*code_ranges, *url_ranges, *image_ranges, *jsx_ranges]
    )


def span_overlaps_ranges(
    start: int,
    end: int,
    ranges: list[TextRange],
) -> bool:
    """指定範囲が lint 対象外の範囲と重なるかを返す"""
    return any(
        start < range_end and range_start < end
        for range_start, range_end in ranges
    )


def mask_ranges(text: str, ranges: list[TextRange]) -> str:
    """改行と位置情報を保ったまま指定範囲を空白に置き換える"""
    characters = list(text)
    for start, end in ranges:
        for position in range(start, end):
            if characters[position] not in {"\n", "\r"}:
                characters[position] = " "
    return "".join(characters)


def line_start_offsets(text: str) -> list[int]:
    """各物理行の先頭に対応する全文オフセットを返す"""
    offsets = [0]
    offsets.extend(match.end() for match in re.finditer(r"\n", text))
    return offsets


def _frontmatter_ranges(text: str) -> list[TextRange]:
    """先頭の YAML frontmatter が占める範囲を返す"""
    lines = _line_ranges(text)
    if not lines:
        return []

    first_start, first_end = lines[0]
    first_line = _line_content(text, first_start, first_end)
    if _FRONTMATTER_OPEN_PATTERN.fullmatch(first_line) is None:
        return []

    for start, end in lines[1:]:
        line = _line_content(text, start, end)
        if _FRONTMATTER_CLOSE_PATTERN.fullmatch(line) is not None:
            return [(0, end)]
    return [(0, len(text))]


def _fenced_code_ranges(
    text: str,
    protected_ranges: list[TextRange],
) -> list[TextRange]:
    """フェンスされたコードブロックが占める範囲を返す"""
    ranges: list[TextRange] = []
    opening_start: int | None = None
    fence_character = ""
    fence_length = 0

    for start, end in _line_ranges(text):
        if span_overlaps_ranges(start, end, protected_ranges):
            continue

        line = _strip_markdown_containers(
            _line_content(text, start, end)
        )
        fence_match = _FENCE_PATTERN.fullmatch(line)
        if opening_start is None:
            if fence_match is None:
                continue
            marker = fence_match.group("marker")
            opening_start = start
            fence_character = marker[0]
            fence_length = len(marker)
            continue

        if fence_match is None:
            continue
        marker = fence_match.group("marker")
        if (
            marker[0] == fence_character
            and len(marker) >= fence_length
            and not fence_match.group("suffix").strip()
        ):
            ranges.append((opening_start, end))
            opening_start = None
            fence_character = ""
            fence_length = 0

    if opening_start is not None:
        ranges.append((opening_start, len(text)))
    return ranges


def _inline_code_ranges(
    text: str,
    protected_ranges: list[TextRange],
) -> list[TextRange]:
    """同数のバッククォートで閉じたコードスパンを返す"""
    ranges: list[TextRange] = []
    for segment_start, segment_end in _prose_segments(
        len(text),
        protected_ranges,
    ):
        runs = list(
            _BACKTICK_RUN_PATTERN.finditer(
                text,
                segment_start,
                segment_end,
            )
        )
        run_index = 0
        while run_index < len(runs):
            opening = runs[run_index]
            closing_index = run_index + 1
            while closing_index < len(runs):
                closing = runs[closing_index]
                if len(closing.group(0)) == len(opening.group(0)):
                    ranges.append((opening.start(), closing.end()))
                    run_index = closing_index + 1
                    break
                closing_index += 1
            else:
                run_index += 1
    return ranges


def _url_ranges(
    text: str,
    protected_ranges: list[TextRange],
) -> list[TextRange]:
    """素の URL と Markdown リンク先が占める範囲を返す"""
    ranges = [
        destination
        for _, destination, _, _ in _markdown_link_parts(
            text,
            protected_ranges,
        )
        if destination is not None
    ]
    ranges.extend(
        match.span()
        for match in _RAW_URL_PATTERN.finditer(text)
        if not span_overlaps_ranges(
            match.start(),
            match.end(),
            protected_ranges,
        )
    )
    return ranges


def _markdown_image_ranges(
    text: str,
    protected_ranges: list[TextRange],
) -> list[TextRange]:
    """Markdown 画像の alt と title が占める範囲を返す"""
    ranges: list[TextRange] = []
    for is_image, _, alt_range, title_range in _markdown_link_parts(
        text,
        protected_ranges,
    ):
        if not is_image:
            continue
        if alt_range is not None:
            ranges.append(alt_range)
        if title_range is not None:
            ranges.append(title_range)
    return ranges


def _jsx_attribute_ranges(
    text: str,
    protected_ranges: list[TextRange],
) -> list[TextRange]:
    """JSX の alt・title 属性値が占める範囲を返す"""
    ranges: list[TextRange] = []
    position = 0
    while position < len(text):
        tag_match = _JSX_TAG_START_PATTERN.search(text, position)
        if tag_match is None:
            break
        protected_end = _containing_range_end(
            tag_match.start(),
            protected_ranges,
        )
        if protected_end is not None:
            position = protected_end
            continue
        if tag_match.group("closing"):
            position = _find_tag_end(text, tag_match.end())
            continue

        position = tag_match.end()
        while position < len(text):
            protected_end = _containing_range_end(position, protected_ranges)
            if protected_end is not None:
                position = protected_end
                continue
            if text.startswith("/>", position):
                position += 2
                break
            if text[position] == ">":
                position += 1
                break
            if text[position].isspace():
                position += 1
                continue
            if text[position] == "{":
                expression_end = _find_jsx_expression_end(text, position)
                position = expression_end + 1
                continue

            attribute_match = _JSX_ATTRIBUTE_NAME_PATTERN.match(
                text,
                position,
            )
            if attribute_match is None:
                position += 1
                continue
            attribute_name = attribute_match.group(0).lower()
            position = attribute_match.end()
            while position < len(text) and text[position].isspace():
                position += 1
            if position >= len(text) or text[position] != "=":
                continue
            position += 1
            while position < len(text) and text[position].isspace():
                position += 1
            if position >= len(text):
                break

            value_start = position
            value_end = position
            if text[position] in {'"', "'"}:
                quote = text[position]
                closing_quote = _find_unescaped_character(
                    text,
                    quote,
                    position + 1,
                )
                value_start = position + 1
                value_end = (
                    len(text) if closing_quote is None else closing_quote
                )
                position = (
                    len(text) if closing_quote is None else closing_quote + 1
                )
            elif text[position] == "{":
                expression_end = _find_jsx_expression_end(text, position)
                value_end = min(expression_end + 1, len(text))
                position = value_end
            else:
                while (
                    position < len(text)
                    and not text[position].isspace()
                    and text[position] != ">"
                ):
                    position += 1
                value_end = position

            if (
                attribute_name in _JSX_NON_PROSE_ATTRIBUTES
                and value_start < value_end
            ):
                ranges.append((value_start, value_end))
    return ranges


def _markdown_link_parts(
    text: str,
    protected_ranges: list[TextRange],
) -> list[
    tuple[bool, TextRange | None, TextRange | None, TextRange | None]
]:
    """Markdown リンクと画像を構成する範囲へ分解する"""
    parts = []
    for match in _MARKDOWN_LINK_START_PATTERN.finditer(text):
        if _is_escaped(text, match.start()) or span_overlaps_ranges(
            match.start(),
            match.end(),
            protected_ranges,
        ):
            continue
        is_image = match.group(0).startswith("!")
        bracket_start = match.end() - 1
        bracket_end = _find_matching_delimiter(
            text,
            bracket_start,
            "[",
            "]",
            protected_ranges,
        )
        if bracket_end is None:
            continue
        parenthesis_start = bracket_end + 1
        if (
            parenthesis_start >= len(text)
            or text[parenthesis_start] != "("
        ):
            continue
        parenthesis_end = _find_link_parenthesis_end(
            text,
            parenthesis_start,
            protected_ranges,
        )
        if parenthesis_end is None:
            continue

        destination, title = _link_destination_and_title(
            text,
            parenthesis_start + 1,
            parenthesis_end,
        )
        alt = (bracket_start + 1, bracket_end) if is_image else None
        parts.append((is_image, destination, alt, title))
    return parts


def _link_destination_and_title(
    text: str,
    start: int,
    end: int,
) -> tuple[TextRange | None, TextRange | None]:
    """リンク括弧内からリンク先と任意の title を取り出す"""
    position = start
    while position < end and text[position].isspace():
        position += 1
    if position >= end:
        return None, None

    if text[position] == "<":
        destination_start = position + 1
        destination_end = text.find(">", destination_start, end)
        if destination_end < 0:
            return None, None
        position = destination_end + 1
    else:
        destination_start = position
        nested_parentheses = 0
        while position < end:
            character = text[position]
            if character == "\\":
                position += 2
                continue
            if character == "(":
                nested_parentheses += 1
            elif character == ")" and nested_parentheses:
                nested_parentheses -= 1
            elif character.isspace() and nested_parentheses == 0:
                break
            position += 1
        destination_end = position

    while position < end and text[position].isspace():
        position += 1
    title: TextRange | None = None
    if position < end and text[position] in {'"', "'"}:
        quote = text[position]
        title_end = _find_unescaped_character(
            text,
            quote,
            position + 1,
            end,
        )
        if title_end is not None:
            title = (position + 1, title_end)
    elif position < end and text[position] == "(":
        title_end = _find_matching_delimiter(
            text,
            position,
            "(",
            ")",
            [],
            limit=end,
        )
        if title_end is not None:
            title = (position + 1, title_end)

    destination = (
        (destination_start, destination_end)
        if destination_start < destination_end
        else None
    )
    return destination, title


def _find_link_parenthesis_end(
    text: str,
    start: int,
    protected_ranges: list[TextRange],
) -> int | None:
    """引用符と入れ子を考慮してリンクの閉じ括弧を探す"""
    depth = 1
    quote = ""
    position = start + 1
    while position < len(text):
        if _containing_range_end(position, protected_ranges) is not None:
            return None
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
    protected_ranges: list[TextRange],
    *,
    limit: int | None = None,
) -> int | None:
    """エスケープと入れ子を考慮して対応する閉じ記号を探す"""
    depth = 1
    end = len(text) if limit is None else limit
    position = start + 1
    while position < end:
        if _containing_range_end(position, protected_ranges) is not None:
            return None
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


def _find_jsx_expression_end(text: str, start: int) -> int:
    """文字列とコメントを飛ばしながら JSX 式の閉じ波括弧を探す"""
    depth = 0
    quote = ""
    position = start
    while position < len(text):
        character = text[position]
        if quote:
            if character == quote and not _is_escaped(text, position):
                quote = ""
            position += 1
            continue
        if text.startswith("//", position):
            newline = text.find("\n", position + 2)
            position = len(text) if newline < 0 else newline + 1
            continue
        if text.startswith("/*", position):
            comment_end = text.find("*/", position + 2)
            position = len(text) if comment_end < 0 else comment_end + 2
            continue
        if character in {'"', "'", "`"}:
            quote = character
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return position
        position += 1
    return len(text) - 1


def _find_tag_end(text: str, start: int) -> int:
    """閉じ JSX タグの末尾直後を返す"""
    end = text.find(">", start)
    return len(text) if end < 0 else end + 1


def _find_unescaped_character(
    text: str,
    character: str,
    start: int,
    end: int | None = None,
) -> int | None:
    """エスケープされていない指定文字を探す"""
    limit = len(text) if end is None else end
    position = start
    while position < limit:
        position = text.find(character, position, limit)
        if position < 0:
            return None
        if not _is_escaped(text, position):
            return position
        position += 1
    return None


def _is_escaped(text: str, position: int) -> bool:
    """指定位置の文字がバックスラッシュでエスケープされているか返す"""
    backslash_count = 0
    position -= 1
    while position >= 0 and text[position] == "\\":
        backslash_count += 1
        position -= 1
    return backslash_count % 2 == 1


def _strip_markdown_containers(line: str) -> str:
    """フェンスより前の引用記号・リスト記号・インデントを外す"""
    remainder = line.lstrip(" \t")
    while remainder.startswith(">"):
        remainder = remainder[1:]
        if remainder.startswith((" ", "\t")):
            remainder = remainder[1:]
        remainder = remainder.lstrip(" \t")
    list_match = re.match(r"(?:[-+*]|\d+[.)])[ \t]+", remainder)
    if list_match is not None:
        remainder = remainder[list_match.end():].lstrip(" \t")
    while remainder.startswith(">"):
        remainder = remainder[1:].lstrip(" \t")
    return remainder


def _line_ranges(text: str) -> list[TextRange]:
    """改行を含む物理行の全文オフセット範囲を返す"""
    starts = line_start_offsets(text)
    return [
        (start, starts[index + 1] if index + 1 < len(starts) else len(text))
        for index, start in enumerate(starts)
    ]


def _line_content(text: str, start: int, end: int) -> str:
    """物理行から末尾の改行コードだけを除いて返す"""
    return text[start:end].rstrip("\r\n")


def _prose_segments(
    text_length: int,
    protected_ranges: list[TextRange],
) -> list[TextRange]:
    """保護範囲を除いた連続領域を返す"""
    segments: list[TextRange] = []
    position = 0
    for start, end in _merge_ranges(protected_ranges):
        if position < start:
            segments.append((position, start))
        position = max(position, end)
    if position < text_length:
        segments.append((position, text_length))
    return segments


def _containing_range_end(
    position: int,
    ranges: list[TextRange],
) -> int | None:
    """指定位置を含む範囲の末尾を返す"""
    for start, end in ranges:
        if start <= position < end:
            return end
        if start > position:
            break
    return None


def _merge_ranges(ranges: list[TextRange]) -> list[TextRange]:
    """重複または隣接する範囲を統合する"""
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
