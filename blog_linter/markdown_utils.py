"""Markdown 内で lint 対象外にする範囲を判定する共通処理"""

import re


_FENCE_PATTERN = re.compile(r"^\s*(`{3,}|~{3,})")
_INLINE_CODE_PATTERN = re.compile(r"(?P<ticks>`+).*?(?P=ticks)")
_URL_PATTERN = re.compile(r"(?:https?://|www\.)[^\s<>\]]+")
_MARKDOWN_LINK_DESTINATION_PATTERN = re.compile(r"\]\((?P<destination>[^)\s]+)")
_MDX_TAG_START_PATTERN = re.compile(r"<(?=[A-Za-z/])")
_MDX_STRING_ATTRIBUTE_PATTERN = re.compile(
    r"(?P<name>[A-Za-z_:][A-Za-z0-9_.:-]*)\s*=\s*(?P<quote>[\"'])"
)
_MDX_NON_PROSE_ATTRIBUTES = {"alt", "title"}


def excluded_line_indexes(lines: list[str]) -> set[int]:
    """frontmatter とフェンスコードの行番号を返す"""
    excluded = _frontmatter_line_indexes(lines)
    fence_character = ""
    fence_length = 0

    for line_index, line in enumerate(lines):
        if line_index in excluded:
            continue

        fence_match = _FENCE_PATTERN.match(line)
        if not fence_character:
            if fence_match is None:
                continue
            marker = fence_match.group(1)
            fence_character = marker[0]
            fence_length = len(marker)
            excluded.add(line_index)
            continue

        excluded.add(line_index)
        stripped = line.lstrip()
        if stripped.startswith(fence_character * fence_length):
            fence_character = ""
            fence_length = 0

    return excluded


def non_prose_ranges(
    line: str,
    *,
    include_urls: bool = False,
    include_link_destinations: bool = False,
) -> list[tuple[int, int]]:
    """インラインコードなど、行内の対象外範囲を返す"""
    ranges = [match.span() for match in _INLINE_CODE_PATTERN.finditer(line)]
    if include_urls:
        ranges.extend(match.span() for match in _URL_PATTERN.finditer(line))
    if include_link_destinations:
        ranges.extend(
            match.span("destination")
            for match in _MARKDOWN_LINK_DESTINATION_PATTERN.finditer(line)
        )
    return ranges


def non_prose_ranges_by_line(
    lines: list[str],
    *,
    include_urls: bool = False,
    include_link_destinations: bool = False,
    include_mdx_attributes: bool = False,
) -> list[list[tuple[int, int]]]:
    """行ごとの本文ではない範囲を返す"""
    attribute_ranges = (
        _mdx_attribute_value_ranges(lines) if include_mdx_attributes else {}
    )
    return [
        non_prose_ranges(
            line,
            include_urls=include_urls,
            include_link_destinations=include_link_destinations,
        ) + attribute_ranges.get(line_index, [])
        for line_index, line in enumerate(lines)
    ]


def span_overlaps_ranges(
    start: int,
    end: int,
    ranges: list[tuple[int, int]],
) -> bool:
    """指定範囲が lint 対象外の範囲と重なるかを返す"""
    return any(
        start < range_end and range_start < end
        for range_start, range_end in ranges
    )


def mask_ranges(line: str, ranges: list[tuple[int, int]]) -> str:
    """位置情報を保ったまま指定範囲を空白に置き換える"""
    characters = list(line)
    for start, end in ranges:
        characters[start:end] = " " * (end - start)
    return "".join(characters)


def _frontmatter_line_indexes(lines: list[str]) -> set[int]:
    """先頭の YAML frontmatter の行番号を返す"""
    if not lines or lines[0].lstrip("\ufeff").strip() != "---":
        return set()

    for line_index in range(1, len(lines)):
        if lines[line_index].strip() in {"---", "..."}:
            return set(range(line_index + 1))

    return set(range(len(lines)))


def _mdx_attribute_value_ranges(
    lines: list[str],
) -> dict[int, list[tuple[int, int]]]:
    """MDX の alt・title 属性値が占める範囲を返す"""
    excluded_lines = excluded_line_indexes(lines)
    ranges_by_line: dict[int, list[tuple[int, int]]] = {}
    in_tag = False
    active_quote = ""
    is_non_prose_attribute = False

    for line_index, line in enumerate(lines):
        if line_index in excluded_lines:
            in_tag = False
            active_quote = ""
            is_non_prose_attribute = False
            continue

        position = 0
        line_ranges = []
        while position < len(line):
            if not in_tag:
                tag_match = _MDX_TAG_START_PATTERN.search(line, position)
                if tag_match is None:
                    break
                in_tag = True
                position = tag_match.end()
                continue

            if active_quote:
                quote_end = _find_unescaped_quote(line, active_quote, position)
                range_end = len(line) if quote_end is None else quote_end
                if is_non_prose_attribute:
                    line_ranges.append((position, range_end))
                if quote_end is None:
                    position = len(line)
                    continue
                active_quote = ""
                is_non_prose_attribute = False
                position = quote_end + 1
                continue

            if line[position] == ">":
                in_tag = False
                position += 1
                continue

            attribute_match = _MDX_STRING_ATTRIBUTE_PATTERN.match(line, position)
            if attribute_match is None:
                position += 1
                continue

            active_quote = attribute_match.group("quote")
            is_non_prose_attribute = (
                attribute_match.group("name").lower()
                in _MDX_NON_PROSE_ATTRIBUTES
            )
            position = attribute_match.end()

        if line_ranges:
            ranges_by_line[line_index] = line_ranges

    return ranges_by_line


def _find_unescaped_quote(line: str, quote: str, start: int) -> int | None:
    """エスケープされていない閉じ引用符の位置を返す"""
    position = start
    while True:
        position = line.find(quote, position)
        if position < 0:
            return None
        backslash_count = 0
        preceding_position = position - 1
        while (
            preceding_position >= 0
            and line[preceding_position] == "\\"
        ):
            backslash_count += 1
            preceding_position -= 1
        if backslash_count % 2 == 0:
            return position
        position += 1
