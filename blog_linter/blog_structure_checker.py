"""blog プロファイル固有の構成チェッカー"""

import re
from bisect import bisect_right

from blog_linter.markdown_utils import (
    line_start_offsets,
    mask_ranges,
    non_prose_ranges,
    parse_markdown_tokens,
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

_CITATION_PATTERN = re.compile(r"（出典\s*[:：]")


def check_blog_structure(text: str) -> list[LintIssue]:
    """blog 固有の構成ルールをチェックする"""
    lines = text.split("\n")
    ranges = non_prose_ranges(text)
    masked_text = mask_ranges(text, ranges)
    masked_lines = masked_text.split("\n")
    tokens = parse_markdown_tokens(text)
    headings: list[tuple[int, int, str]] = []
    for token_index, token in enumerate(tokens):
        if (
            token.type != "heading_open"
            or token.map is None
            or not masked_lines[token.map[0]].strip()
        ):
            continue
        title = lines[token.map[0]].strip()
        if (
            token_index + 1 < len(tokens)
            and tokens[token_index + 1].type == "inline"
        ):
            title = tokens[token_index + 1].content
        headings.append((token.map[0], token.map[1], title))
    issues = []
    issues.extend(_check_citation_density(masked_lines, headings))
    issues.extend(_check_aws_first_mentions(text, masked_text))
    return issues


def _check_citation_density(
    masked_lines: list[str],
    headings: list[tuple[int, int, str]],
) -> list[LintIssue]:
    issues = []
    for heading_index, (start, end, title) in enumerate(headings):
        next_start = (
            headings[heading_index + 1][0]
            if heading_index + 1 < len(headings)
            else len(masked_lines)
        )
        citation_count = sum(
            len(_CITATION_PATTERN.findall(line))
            for line in masked_lines[end:next_start]
        )
        if citation_count < 3:
            continue
        issues.append(LintIssue(
            line_number=start + 1,
            column=1,
            matched_text=title,
            category="structure",
            rule_name="citation-density",
            message=(
                f"同一小節に出典表記が {citation_count} 回あります。"
                "本文に統合するか、出典をまとめてください。"
            ),
            suggestion="出典表記を 2 回以下に整理する",
        ))
    return issues


def _check_aws_first_mentions(
    text: str,
    masked_text: str,
) -> list[LintIssue]:
    offsets = line_start_offsets(text)

    issues = []
    for abbreviation, formal_name in AWS_SERVICES:
        first_mention = _find_first_bare_mention(
            masked_text,
            abbreviation,
            formal_name,
        )
        if first_mention is None:
            continue
        start, end = first_mention
        line_index = bisect_right(offsets, start) - 1
        issues.append(LintIssue(
            line_number=line_index + 1,
            column=start - offsets[line_index] + 1,
            matched_text=text[start:end],
            category="structure",
            rule_name="aws-first-mention",
            message=(
                f"「{text[start:end]}」が AWS サービスを指すなら、初出時に"
                f"正式名「{formal_name}」を示します。別サービス名やコード上の"
                "用語ならそのままです。文脈を確認してください。"
            ),
            suggestion=None,
            needs_review=True,
        ))
    return issues


def _find_first_bare_mention(
    text: str,
    abbreviation: str,
    formal_name: str,
) -> tuple[int, int] | None:
    """正式名より前に現れる最初の略称を返す。"""
    abbreviation_pattern = re.compile(
        rf"(?<![A-Za-z0-9]){re.escape(abbreviation)}(?![A-Za-z0-9])",
        flags=re.IGNORECASE,
    )
    formal_pattern = re.compile(re.escape(formal_name), flags=re.IGNORECASE)
    formal_ranges = [match.span() for match in formal_pattern.finditer(text)]
    bare_mentions = [
        match
        for match in abbreviation_pattern.finditer(text)
        if not any(
            start <= match.start() and match.end() <= end
            for start, end in formal_ranges
        )
    ]
    if not bare_mentions:
        return None

    first_bare = bare_mentions[0]
    if formal_ranges and formal_ranges[0][0] < first_bare.start():
        return None
    return first_bare.span()
