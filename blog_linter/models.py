"""リンター共通のデータモデル"""
from dataclasses import dataclass


@dataclass
class LintIssue:
    line_number: int
    column: int
    matched_text: str
    category: str
    rule_name: str
    message: str
    suggestion: str = ""
    file: str = ""
