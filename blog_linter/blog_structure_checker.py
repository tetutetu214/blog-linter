"""blog プロファイル固有の構成チェッカー"""

import re

from blog_linter.markdown_utils import (
    excluded_line_indexes,
    mask_ranges,
    non_prose_ranges_by_line,
)
from blog_linter.models import LintIssue


AWS_SERVICES = (
    ("Lambda", "AWS Lambda"),
    ("S3", "Amazon S3"),
    ("EC2", "Amazon EC2"),
    ("RDS", "Amazon RDS"),
    ("DynamoDB", "Amazon DynamoDB"),
    ("CloudWatch", "Amazon CloudWatch"),
    ("CloudFormation", "AWS CloudFormation"),
    ("IAM", "AWS IAM"),
    ("VPC", "Amazon VPC"),
    ("ECS", "Amazon ECS"),
    ("EKS", "Amazon EKS"),
)

_HEADING_PATTERN = re.compile(r"^\s{0,3}(?P<marker>#{1,6})\s+(?P<title>.+?)\s*$")
_CITATION_PATTERN = re.compile(r"（出典\s*[:：]")
_SENTENCE_END_PATTERN = re.compile(r"[。！？!?]+")


def check_blog_structure(text: str) -> list[LintIssue]:
    """blog 固有の構成ルールをチェックする"""
    lines = text.split("\n")
    excluded_lines = excluded_line_indexes(lines)
    ranges_by_line = non_prose_ranges_by_line(
        lines,
        include_urls=True,
        include_link_destinations=True,
        include_mdx_attributes=True,
    )
    issues = []
    issues.extend(_check_citation_density(
        lines,
        excluded_lines,
        ranges_by_line,
    ))
    issues.extend(_check_aws_first_mentions(
        lines,
        excluded_lines,
        ranges_by_line,
    ))
    return issues


def _check_citation_density(
    lines: list[str],
    excluded_lines: set[int],
    ranges_by_line: list[list[tuple[int, int]]],
) -> list[LintIssue]:
    issues = []
    section_line = -1
    section_title = ""
    citation_count = 0

    def append_section_issue() -> None:
        if section_line < 0 or citation_count < 3:
            return
        issues.append(LintIssue(
            line_number=section_line + 1,
            column=1,
            matched_text=section_title,
            category="structure",
            rule_name="citation-density",
            message=(
                f"同一小節に出典表記が {citation_count} 回あります。"
                "本文に統合するか、出典をまとめてください。"
            ),
            suggestion="出典表記を 2 回以下に整理する",
        ))

    for line_index, line in enumerate(lines):
        if line_index in excluded_lines:
            continue
        heading_match = _HEADING_PATTERN.match(line)
        if heading_match is not None:
            append_section_issue()
            section_line = line_index
            section_title = heading_match.group("title")
            citation_count = 0
            continue
        if section_line < 0:
            continue
        masked_line = mask_ranges(line, ranges_by_line[line_index])
        citation_count += len(_CITATION_PATTERN.findall(masked_line))

    append_section_issue()
    return issues


def _check_aws_first_mentions(
    lines: list[str],
    excluded_lines: set[int],
    ranges_by_line: list[list[tuple[int, int]]],
) -> list[LintIssue]:
    prose_lines = []
    for line_index, line in enumerate(lines):
        if line_index in excluded_lines or _HEADING_PATTERN.match(line):
            prose_lines.append(" " * len(line))
            continue
        prose_lines.append(mask_ranges(line, ranges_by_line[line_index]))

    issues = []
    for abbreviation, formal_name in AWS_SERVICES:
        first_mention = _find_first_undeclared_mention(
            prose_lines,
            abbreviation,
            formal_name,
        )
        if first_mention is None:
            continue
        line_index, start, end = first_mention
        issues.append(LintIssue(
            line_number=line_index + 1,
            column=start + 1,
            matched_text=lines[line_index][start:end],
            category="structure",
            rule_name="aws-first-mention",
            message=(
                f"「{abbreviation}」の初出時に正式名「{formal_name}」と"
                "以降の略称表記を宣言してください。"
            ),
            suggestion=(
                f"{formal_name}（これ以降は {abbreviation} と表記する）"
            ),
        ))
    return issues


def _find_first_undeclared_mention(
    lines: list[str],
    abbreviation: str,
    formal_name: str,
) -> tuple[int, int, int] | None:
    abbreviation_pattern = re.compile(
        rf"(?<![A-Za-z0-9]){re.escape(abbreviation)}(?![A-Za-z0-9])",
        flags=re.IGNORECASE,
    )
    formal_pattern = re.compile(re.escape(formal_name), flags=re.IGNORECASE)

    for line_index, line in enumerate(lines):
        for sentence_start, sentence_end in _sentence_ranges(line):
            sentence = line[sentence_start:sentence_end]
            formal_ranges = [
                match.span() for match in formal_pattern.finditer(sentence)
            ]
            bare_mentions = [
                match
                for match in abbreviation_pattern.finditer(sentence)
                if not any(
                    start <= match.start() and match.end() <= end
                    for start, end in formal_ranges
                )
            ]
            if not bare_mentions:
                continue
            if formal_ranges or _is_abbreviation_declaration(
                sentence,
                abbreviation,
            ):
                return None
            match = bare_mentions[0]
            return (
                line_index,
                sentence_start + match.start(),
                sentence_start + match.end(),
            )
    return None


def _sentence_ranges(line: str) -> list[tuple[int, int]]:
    """句点単位の文の範囲を返す"""
    ranges = []
    start = 0
    for match in _SENTENCE_END_PATTERN.finditer(line):
        ranges.append((start, match.end()))
        start = match.end()
    if start < len(line):
        ranges.append((start, len(line)))
    return ranges


def _is_abbreviation_declaration(
    sentence: str,
    abbreviation: str,
) -> bool:
    """正式名を伴わない略称宣言かどうかを返す"""
    abbreviation_expression = (
        rf"(?:[「『]\s*{re.escape(abbreviation)}\s*[」』]|"
        rf"{re.escape(abbreviation)})"
    )
    notice_pattern = re.compile(
        rf"(?:これ以降|以降|以後|以下).{{0,60}}?"
        rf"{abbreviation_expression}.{{0,20}}?"
        rf"(?:表記|略記|呼称|呼ぶ|記す|略す)",
        flags=re.IGNORECASE,
    )
    return notice_pattern.search(sentence) is not None
