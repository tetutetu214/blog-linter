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
    suggestion: str | None = ""
    file: str = ""
    needs_review: bool = False

    def __post_init__(self) -> None:
        """確認専用の指摘には自動修正候補を持たせない。"""
        if self.needs_review:
            self.suggestion = None
