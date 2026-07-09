"""機密情報チェッカー: 正規表現ベースでシークレットを検出する"""
import re
from dataclasses import dataclass


@dataclass
class LintIssue:
    line_number: int
    column: int
    matched_text: str
    category: str  # "secret" or "notation"
    rule_name: str
    message: str
    suggestion: str = ""


SECRET_PATTERNS = [
    {
        "name": "AWS Access Key ID",
        "pattern": r"(?<![A-Z0-9])(AKIA[0-9A-Z]{16})(?![A-Z0-9])",
        "message": "AWSアクセスキーIDが含まれています",
    },
    {
        "name": "AWS Secret Access Key",
        "pattern": r"(?i)(?:aws_secret_access_key|secret_?access_?key|aws_secret)\s*[=:]\s*['\"]?([A-Za-z0-9/+=]{40})['\"]?",
        "message": "AWSシークレットアクセスキーが含まれています",
    },
    {
        "name": "AWS Session Token",
        "pattern": r"(?i)(?:aws_session_token|session_?token)\s*[=:]\s*['\"]?([A-Za-z0-9/+=]{100,})['\"]?",
        "message": "AWSセッショントークンが含まれています",
    },
    {
        "name": "AWS Account ID",
        "pattern": r"(?<!\d)(\d{12})(?!\d)",
        "message": "AWSアカウントID（12桁数字）の可能性があります",
        "context_required": True,
    },
    {
        "name": "GitHub Token",
        "pattern": r"(ghp_[A-Za-z0-9_]{36,}|gho_[A-Za-z0-9_]{36,}|ghs_[A-Za-z0-9_]{36,}|ghr_[A-Za-z0-9_]{36,}|github_pat_[A-Za-z0-9_]{22,})",
        "message": "GitHubトークンが含まれています",
    },
    {
        "name": "Slack Token",
        "pattern": r"(xoxb-[0-9A-Za-z\-]+|xoxp-[0-9A-Za-z\-]+|xoxs-[0-9A-Za-z\-]+)",
        "message": "Slackトークンが含まれています",
    },
    {
        "name": "Private Key",
        "pattern": r"-----BEGIN\s+(RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----",
        "message": "秘密鍵が含まれています",
    },
    {
        "name": "Generic API Key",
        "pattern": r"(?i)(?:api_?key|apikey|api_?secret|access_?token|auth_?token|secret_?key)\s*[=:]\s*['\"]?([A-Za-z0-9_\-]{16,})['\"]?",
        "message": "APIキー/トークンが含まれています",
    },
    {
        "name": "Password",
        "pattern": r"(?i)(?:password|passwd|pwd)\s*[=:]\s*['\"]?([^\s'\"]{4,})['\"]?",
        "message": "パスワードが含まれています",
    },
    {
        "name": "Database Connection String",
        "pattern": r"(?i)(?:mysql|postgresql|postgres|mongodb|redis|mssql)://[^\s'\"]+",
        "message": "データベース接続文字列が含まれています",
    },
    {
        "name": "Private IP Address",
        "pattern": r"(?<!\d)(10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3})(?!\d)",
        "message": "プライベートIPアドレスが含まれています",
    },
    {
        "name": "Generic Secret",
        "pattern": r"(?i)(?:secret|credential)\s*[=:]\s*['\"]?([A-Za-z0-9_\-/+=]{16,})['\"]?",
        "message": "シークレット情報が含まれています",
    },
]

AWS_ACCOUNT_CONTEXT_WORDS = [
    "account", "アカウント", "aws", "arn:", "iam", "sts",
    "role", "policy", "resource", "principal",
]


def check_secrets(text: str) -> list[LintIssue]:
    """テキスト内の機密情報を検出する"""
    issues = []
    lines = text.split("\n")

    for rule in SECRET_PATTERNS:
        pattern = re.compile(rule["pattern"])

        for line_idx, line in enumerate(lines):
            for match in pattern.finditer(line):
                if rule.get("context_required"):
                    context_window = "\n".join(
                        lines[max(0, line_idx - 2):line_idx + 3]
                    ).lower()
                    if not any(w in context_window for w in AWS_ACCOUNT_CONTEXT_WORDS):
                        continue

                matched = match.group(0)
                if len(matched) > 8:
                    masked = matched[:4] + "*" * (len(matched) - 8) + matched[-4:]
                else:
                    masked = "*" * len(matched)

                issues.append(LintIssue(
                    line_number=line_idx + 1,
                    column=match.start() + 1,
                    matched_text=matched,
                    category="secret",
                    rule_name=rule["name"],
                    message=rule["message"],
                    suggestion=f"この値を削除またはダミー値に置き換えてください（検出: {masked}）",
                ))

    return issues
