"""リンター統合モジュール"""
from pathlib import Path

from blog_linter.frontmatter_checker import check_frontmatter
from blog_linter.models import LintIssue
from blog_linter.notation_checker import check_notation
from blog_linter.profiles import get_profile_checks
from blog_linter.secret_checker import check_secrets


def lint_markdown(
    text: str,
    profile: str = "qiita",
    file_path: Path | None = None,
    vault_root: Path | None = None,
    tag_vocabulary: set[str] | None = None,
) -> list[LintIssue]:
    """Markdownテキストに対して全チェックを実行する"""
    checks = get_profile_checks(profile)
    issues: list[LintIssue] = []
    if "secrets" in checks:
        issues.extend(check_secrets(text))
    if "notation" in checks:
        issues.extend(check_notation(text))
    if "frontmatter" in checks:
        if file_path is None or vault_root is None or tag_vocabulary is None:
            raise ValueError(
                "vault プロファイルには file_path、vault_root、tag_vocabulary が必要です"
            )
        issues.extend(check_frontmatter(
            text,
            file_path=file_path,
            vault_root=vault_root,
            tag_vocabulary=tag_vocabulary,
        ))
    for issue in issues:
        if file_path is not None:
            issue.file = str(file_path)
    issues.sort(key=lambda x: (x.line_number, x.column))
    return issues


def has_secret_issues(issues: list[LintIssue]) -> bool:
    """機密情報（category == "secret"）の指摘が1件でもあれば True を返す"""
    return any(issue.category == "secret" for issue in issues)
