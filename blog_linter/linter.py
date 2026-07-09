"""リンター統合モジュール"""
from blog_linter.secret_checker import check_secrets, LintIssue
from blog_linter.notation_checker import check_notation


def lint_markdown(text: str) -> list[LintIssue]:
    """Markdownテキストに対して全チェックを実行する"""
    issues = []
    issues.extend(check_secrets(text))
    issues.extend(check_notation(text))
    issues.sort(key=lambda x: (x.line_number, x.column))
    return issues


def has_secret_issues(issues: list[LintIssue]) -> bool:
    """機密情報（category == "secret"）の指摘が1件でもあれば True を返す"""
    return any(issue.category == "secret" for issue in issues)
