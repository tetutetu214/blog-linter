"""blog プロファイル固有の構成チェッカー"""

import re
from bisect import bisect_right

from blog_linter.markdown_utils import (
    line_start_offsets,
    mask_ranges,
    non_prose_ranges,
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
_DECLARATION_CUE_PATTERN = re.compile(
    r"(?:これ以降|以降|以後|以下)(?:の(?:本文|記事|節|例))?(?:では|は)?|"
    r"本(?:文|稿|記事)では"
)
_AFFIRMATIVE_DECLARATION_PATTERN = re.compile(
    r"(?:と|として|のように)\s*"
    r"(?:表記|略記|呼称)(?:する|します)|"
    r"(?:と|として|のように)\s*"
    r"(?:呼ぶ|呼びます|記す|記します|略す|略します)"
)
_FOREIGN_CLOUD_PATTERN = re.compile(
    r"(?:Google\s+Cloud|GCP|Azure|Microsoft\s+Entra|Oracle\s+Cloud)",
    flags=re.IGNORECASE,
)
_AWS_CONTEXT_PATTERN = re.compile(r"(?:AWS|Amazon)", flags=re.IGNORECASE)
_PROGRAMMING_LAMBDA_PATTERN = re.compile(
    r"(?:Python|Java|JavaScript|TypeScript|C#).{0,30}"
    r"(?:lambda|ラムダ).{0,12}(?:式|関数|expression)",
    flags=re.IGNORECASE,
)


def check_blog_structure(text: str) -> list[LintIssue]:
    """blog 固有の構成ルールをチェックする"""
    lines = text.split("\n")
    ranges = non_prose_ranges(text)
    masked_text = mask_ranges(text, ranges)
    masked_lines = masked_text.split("\n")
    issues = []
    issues.extend(_check_citation_density(lines, masked_lines))
    issues.extend(_check_aws_first_mentions(text, masked_text))
    return issues


def _check_citation_density(
    lines: list[str],
    masked_lines: list[str],
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

    for line_index, masked_line in enumerate(masked_lines):
        heading_match = _HEADING_PATTERN.match(masked_line)
        if heading_match is not None:
            append_section_issue()
            section_line = line_index
            section_title = lines[line_index][
                heading_match.start("title"):heading_match.end("title")
            ]
            citation_count = 0
            continue
        if section_line < 0:
            continue
        citation_count += len(_CITATION_PATTERN.findall(masked_line))

    append_section_issue()
    return issues


def _check_aws_first_mentions(
    text: str,
    masked_text: str,
) -> list[LintIssue]:
    prose_text = _mask_heading_lines(masked_text)
    offsets = line_start_offsets(text)

    issues = []
    for abbreviation, formal_name in AWS_SERVICES:
        first_mention = _find_first_undeclared_mention(
            prose_text,
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
                f"「{abbreviation}」の初出時に正式名「{formal_name}」と"
                "以降の略称表記を宣言してください。"
            ),
            suggestion=(
                f"{formal_name}（これ以降は {abbreviation} と表記する）"
            ),
        ))
    return issues


def _find_first_undeclared_mention(
    text: str,
    abbreviation: str,
    formal_name: str,
) -> tuple[int, int] | None:
    abbreviation_pattern = re.compile(
        rf"(?<![A-Za-z0-9]){re.escape(abbreviation)}(?![A-Za-z0-9])"
    )
    formal_pattern = re.compile(re.escape(formal_name), flags=re.IGNORECASE)

    for sentence_start, sentence_end in _sentence_ranges(text):
        sentence = text[sentence_start:sentence_end]
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
        relevant_mentions = [
            match
            for match in bare_mentions
            if not _has_non_aws_context(sentence, abbreviation)
        ]
        if not relevant_mentions:
            continue
        if _is_abbreviation_declaration(sentence, relevant_mentions):
            return None
        match = relevant_mentions[0]
        return (
            sentence_start + match.start(),
            sentence_start + match.end(),
        )
    return None


def _sentence_ranges(text: str) -> list[tuple[int, int]]:
    """句点単位の文の範囲を返す"""
    ranges = []
    start = 0
    for match in _SENTENCE_END_PATTERN.finditer(text):
        ranges.append((start, match.end()))
        start = match.end()
    if start < len(text):
        ranges.append((start, len(text)))
    return ranges


def _is_abbreviation_declaration(
    sentence: str,
    mentions: list[re.Match[str]],
) -> bool:
    """肯定的な略称宣言かどうかを返す"""
    for mention in mentions:
        prefix = sentence[max(0, mention.start() - 160):mention.start()]
        if _DECLARATION_CUE_PATTERN.search(prefix) is None:
            continue
        suffix = sentence[mention.end():mention.end() + 160]
        declaration = _AFFIRMATIVE_DECLARATION_PATTERN.search(suffix)
        if declaration is None:
            continue
        trailing = suffix[declaration.end():].lstrip()
        if trailing.startswith("こと"):
            continue
        return True
    return False


def _has_non_aws_context(sentence: str, abbreviation: str) -> bool:
    """AWS 以外の技術を明示している文かどうかを返す"""
    if (
        _FOREIGN_CLOUD_PATTERN.search(sentence) is not None
        and _AWS_CONTEXT_PATTERN.search(sentence) is None
    ):
        return True
    return (
        abbreviation == "Lambda"
        and _PROGRAMMING_LAMBDA_PATTERN.search(sentence) is not None
    )


def _mask_heading_lines(text: str) -> str:
    """AWS 初出判定から Markdown 見出しだけを除外する"""
    lines = text.split("\n")
    return "\n".join(
        " " * len(line) if _HEADING_PATTERN.match(line) else line
        for line in lines
    )
