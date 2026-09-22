"""表記ブレチェッカー: プリセットルールで表記の統一性をチェックする"""
import re

from blog_linter.markdown_utils import (
    excluded_line_indexes,
    non_prose_ranges_by_line,
    span_overlaps_ranges,
)
from blog_linter.models import LintIssue


# 表記ブレルール: (推奨表記, [ブレ表記の正規表現パターン, ...])
NOTATION_RULES = [
    # 長音記号の有無（JIS Z 8301 準拠: 3音以上は長音あり）
    {"preferred": "サーバー", "variants": [r"サーバ(?!ー)"], "note": "長音記号をつけるのが一般的です"},
    {"preferred": "ユーザー", "variants": [r"ユーザ(?!ー)"], "note": "長音記号をつけるのが一般的です"},
    {"preferred": "コンピューター", "variants": [r"コンピュータ(?!ー)"], "note": "長音記号をつけるのが一般的です"},
    {"preferred": "プロバイダー", "variants": [r"プロバイダ(?!ー)"], "note": "長音記号をつけるのが一般的です"},
    {"preferred": "パラメーター", "variants": [r"パラメータ(?!ー)"], "note": "長音記号をつけるのが一般的です"},
    {"preferred": "コンテナー", "variants": [r"コンテナ(?!ー)"], "note": "長音記号をつけるのが一般的です"},
    {"preferred": "レジスター", "variants": [r"レジスタ(?!ー)"], "note": "長音記号をつけるのが一般的です"},
    {"preferred": "ブラウザー", "variants": [r"ブラウザ(?!ー)"], "note": "長音記号をつけるのが一般的です"},
    {"preferred": "マネージャー", "variants": [r"マネージャ(?!ー)"], "note": "長音記号をつけるのが一般的です"},
    {"preferred": "ドライバー", "variants": [r"ドライバ(?!ー)"], "note": "長音記号をつけるのが一般的です"},

    # AWS サービス名の正式表記
    {"preferred": "AWS Lambda", "variants": [r"(?<!\w)lambda(?!\w)(?![\(:\.])", r"(?<!\w)Lambda(?!\w)(?![\(:\.]|.*関数)"], "note": "AWSサービス名はフル表記を推奨", "case_sensitive": False, "context_words": ["aws", "関数", "function", "serverless", "サーバーレス"]},
    {"preferred": "Amazon EC2", "variants": [r"(?<![A-Za-z])ec2(?![A-Za-z])"], "note": "AWSサービス名はフル表記を推奨", "case_sensitive": False},
    {"preferred": "Amazon S3", "variants": [r"(?<![A-Za-z])s3(?![A-Za-z])"], "note": "AWSサービス名はフル表記を推奨", "case_sensitive": False},
    {"preferred": "Amazon RDS", "variants": [r"(?<![A-Za-z])rds(?![A-Za-z])"], "note": "AWSサービス名はフル表記を推奨", "case_sensitive": False},
    {"preferred": "Amazon DynamoDB", "variants": [r"(?<![A-Za-z])dynamodb(?![A-Za-z])"], "note": "AWSサービス名はフル表記を推奨", "case_sensitive": False},
    {"preferred": "Amazon CloudWatch", "variants": [r"(?<![A-Za-z])cloudwatch(?![A-Za-z])"], "note": "AWSサービス名はフル表記を推奨", "case_sensitive": False},
    {"preferred": "AWS CloudFormation", "variants": [r"(?<![A-Za-z])cloudformation(?![A-Za-z])"], "note": "AWSサービス名はフル表記を推奨", "case_sensitive": False},
    {"preferred": "AWS IAM", "variants": [r"(?<![A-Za-z])iam(?![A-Za-z])"], "note": "AWSサービス名はフル表記を推奨", "case_sensitive": False},
    {"preferred": "Amazon VPC", "variants": [r"(?<![A-Za-z])vpc(?![A-Za-z])"], "note": "AWSサービス名はフル表記を推奨", "case_sensitive": False},
    {"preferred": "Amazon ECS", "variants": [r"(?<![A-Za-z])ecs(?![A-Za-z])"], "note": "AWSサービス名はフル表記を推奨", "case_sensitive": False},
    {"preferred": "Amazon EKS", "variants": [r"(?<![A-Za-z])eks(?![A-Za-z])"], "note": "AWSサービス名はフル表記を推奨", "case_sensitive": False},

    # 英語表記のブレ
    {"preferred": "GitHub", "variants": [r"(?<![A-Za-z])Github(?![A-Za-z])", r"(?<![A-Za-z])github(?![A-Za-z\.])"], "note": "正式表記は GitHub です"},
    {"preferred": "JavaScript", "variants": [r"(?<![A-Za-z])Javascript(?![A-Za-z])", r"(?<![A-Za-z])javascript(?![A-Za-z])"], "note": "正式表記は JavaScript です"},
    {"preferred": "TypeScript", "variants": [r"(?<![A-Za-z])Typescript(?![A-Za-z])", r"(?<![A-Za-z])typescript(?![A-Za-z])"], "note": "正式表記は TypeScript です"},
    {"preferred": "Node.js", "variants": [r"(?<![A-Za-z])NodeJS(?![A-Za-z])", r"(?<![A-Za-z])Nodejs(?![A-Za-z])", r"(?<![A-Za-z])nodejs(?![A-Za-z])"], "note": "正式表記は Node.js です"},
    {"preferred": "Docker", "variants": [r"(?<![A-Za-z])docker(?![A-Za-z\.\-/])"], "note": "正式表記は Docker です", "case_sensitive": True},
    {"preferred": "Kubernetes", "variants": [r"(?<![A-Za-z])kubernetes(?![A-Za-z])"], "note": "正式表記は Kubernetes です", "case_sensitive": True},
    {"preferred": "Terraform", "variants": [r"(?<![A-Za-z])terraform(?![A-Za-z])"], "note": "正式表記は Terraform です", "case_sensitive": True},

    # 一般的な IT 用語
    {"preferred": "ウェブ", "variants": [r"ウエブ"], "note": "「ウェブ」が一般的です"},
    {"preferred": "ファイアウォール", "variants": [r"ファイヤーウォール", r"ファイアーウォール", r"ファイヤウォール"], "note": "「ファイアウォール」が一般的です"},
    {"preferred": "インターフェース", "variants": [r"インターフェイス", r"インタフェース", r"インタフェイス"], "note": "「インターフェース」が一般的です"},
    {"preferred": "メソッド", "variants": [r"メッソド"], "note": "「メソッド」が一般的です"},
    {"preferred": "デプロイ", "variants": [r"ディプロイ"], "note": "「デプロイ」が一般的です"},
]


BLOG_UNOFFICIAL_TRANSLATIONS = {
    "状態機械": "ステートマシン",
}

BLOG_NOTATION_RULES = [
    {
        "preferred": "Eufy",
        "variants": [r"(?<![A-Za-z0-9])eufy(?![A-Za-z0-9])"],
        "note": "ブランドの正式表記です",
        "case_sensitive": True,
        "excluded_terms": ("eufy-security-client",),
        "rule_name": "brand-capitalization",
    },
    {
        "preferred": "ニワトリ",
        "variants": [r"にわとり", r"鶏"],
        "note": "カタカナ表記に統一します",
        "rule_name": "chicken-notation",
    },
    *[
        {
            "preferred": preferred,
            "variants": [re.escape(variant)],
            "note": "公式に使われる用語に統一します",
            "rule_name": "unofficial-translation",
        }
        for variant, preferred in BLOG_UNOFFICIAL_TRANSLATIONS.items()
    ],
]

_BLOG_EXCLUDED_BASE_RULES = {
    "サーバー",
    "ユーザー",
    "コンピューター",
    "プロバイダー",
    "パラメーター",
    "コンテナー",
    "レジスター",
    "ブラウザー",
    "マネージャー",
    "ドライバー",
    "AWS Lambda",
    "Amazon EC2",
    "Amazon S3",
    "Amazon RDS",
    "Amazon DynamoDB",
    "Amazon CloudWatch",
    "AWS CloudFormation",
    "AWS IAM",
    "Amazon VPC",
    "Amazon ECS",
    "Amazon EKS",
}
_JAPANESE_CHARACTER_CLASS = "ぁ-んァ-ヶ一-鿿々〆ヶー"
_SLASH_JAPANESE_TERM = r"(?:[ぁ-ん]+|[ァ-ヶー]+|[一-鿿々〆ヶ]+)"
_SLASH_TERM = rf"(?:[A-Za-z][A-Za-z0-9+#-]*|[0-9]+|{_SLASH_JAPANESE_TERM})"
_SLASH_COORDINATION_PATTERN = re.compile(
    rf"(?<![A-Za-z0-9{_JAPANESE_CHARACTER_CLASS}/])"
    rf"(?P<left>{_SLASH_TERM})/(?P<right>{_SLASH_TERM})"
    rf"(?![A-Za-z0-9/])"
)
_ALNUM_JAPANESE_BOUNDARY_PATTERN = re.compile(
    rf"(?:(?<=[A-Za-z0-9])(?=[{_JAPANESE_CHARACTER_CLASS}])|"
    rf"(?<=[{_JAPANESE_CHARACTER_CLASS}])(?=[A-Za-z0-9]))"
)


def _is_in_code_block(lines: list[str], line_idx: int) -> bool:
    """コードブロック内かどうかを判定"""
    in_block = False
    for i in range(line_idx):
        stripped = lines[i].strip()
        if stripped.startswith("```"):
            in_block = not in_block
    return in_block


def _is_in_inline_code(line: str, start: int, end: int) -> bool:
    """インラインコード内かどうかを判定"""
    before = line[:start]
    backtick_count = before.count("`")
    return backtick_count % 2 == 1


def check_notation(text: str, profile: str = "qiita") -> list[LintIssue]:
    """テキスト内の表記ブレを検出する"""
    issues = []
    lines = text.split("\n")
    excluded_lines = excluded_line_indexes(lines) if profile == "blog" else set()
    ranges_by_line = non_prose_ranges_by_line(
        lines,
        include_urls=True,
        include_link_destinations=True,
        include_mdx_attributes=profile == "blog",
    )

    for rule in _notation_rules_for_profile(profile):
        preferred = rule["preferred"]
        note = rule.get("note", "")
        case_sensitive = rule.get("case_sensitive", False)
        context_words = rule.get("context_words", [])

        for variant_pattern in rule["variants"]:
            flags = 0 if case_sensitive else re.IGNORECASE
            pattern = re.compile(variant_pattern, flags)

            for line_idx, line in enumerate(lines):
                if line_idx in excluded_lines:
                    continue
                if _is_in_code_block(lines, line_idx):
                    continue

                for match in pattern.finditer(line):
                    if span_overlaps_ranges(
                        match.start(),
                        match.end(),
                        ranges_by_line[line_idx],
                    ):
                        continue
                    if _matches_excluded_term(line, match.start(), rule):
                        continue

                    matched_text = match.group(0)

                    # 既に推奨表記と一致している場合はスキップ
                    if matched_text == preferred:
                        continue

                    # コンテキスト依存のルールの場合
                    if context_words:
                        context_window = "\n".join(
                            lines[max(0, line_idx - 2):line_idx + 3]
                        ).lower()
                        if not any(w in context_window for w in context_words):
                            continue

                    issues.append(LintIssue(
                        line_number=line_idx + 1,
                        column=match.start() + 1,
                        matched_text=matched_text,
                        category="notation",
                        rule_name=rule.get("rule_name", f"表記ブレ: {preferred}"),
                        message=f"「{matched_text}」→「{preferred}」に統一を推奨。{note}",
                        suggestion=preferred,
                    ))

    if profile == "blog":
        issues.extend(_check_slash_coordination(
            lines,
            excluded_lines,
            ranges_by_line,
        ))
        issues.extend(_check_alnum_japanese_spacing(
            lines,
            excluded_lines,
            ranges_by_line,
        ))

    return issues


def _notation_rules_for_profile(profile: str) -> list[dict]:
    """プロファイルに適用する表記ルールを返す"""
    if profile != "blog":
        return NOTATION_RULES

    rules = [
        rule
        for rule in NOTATION_RULES
        if rule["preferred"] not in _BLOG_EXCLUDED_BASE_RULES
    ]
    rules.extend(BLOG_NOTATION_RULES)
    return rules


def _matches_excluded_term(line: str, start: int, rule: dict) -> bool:
    """ライブラリ名などの除外語に含まれるかを返す"""
    return any(
        line.startswith(term, start)
        for term in rule.get("excluded_terms", ())
    )


def _check_slash_coordination(
    lines: list[str],
    excluded_lines: set[int],
    ranges_by_line: list[list[tuple[int, int]]],
) -> list[LintIssue]:
    issues = []
    for line_index, line in enumerate(lines):
        if line_index in excluded_lines:
            continue
        for match in _SLASH_COORDINATION_PATTERN.finditer(line):
            if span_overlaps_ranges(
                match.start(),
                match.end(),
                ranges_by_line[line_index],
            ):
                continue
            left = match.group("left")
            right = match.group("right")
            if _looks_like_path_or_date(line, match, left, right):
                continue
            matched_text = match.group(0)
            suggestion = f"{left} と {right}"
            issues.append(LintIssue(
                line_number=line_index + 1,
                column=match.start() + 1,
                matched_text=matched_text,
                category="notation",
                rule_name="slash-coordination",
                message=(
                    f"「{matched_text}」はスラッシュではなく"
                    "助詞でつなぐことを推奨します。"
                ),
                suggestion=suggestion,
            ))
    return issues


def _looks_like_path_or_date(
    line: str,
    match: re.Match,
    left: str,
    right: str,
) -> bool:
    """スラッシュがパスや日付の区切りかを判定する"""
    if left.isdigit() and right.isdigit():
        return True
    if match.start() > 0 and line[match.start() - 1] in ".=~/":
        return True
    if match.end() < len(line) and line[match.end()] in "./":
        return True

    left_is_ascii_word = left.isascii() and left.isalpha()
    right_is_ascii_word = right.isascii() and right.isalpha()
    if left_is_ascii_word and right_is_ascii_word:
        return left.islower() and right.islower()
    if left_is_ascii_word and not right_is_ascii_word:
        return left.islower()
    if right_is_ascii_word and not left_is_ascii_word:
        return right.islower()
    return False


def _check_alnum_japanese_spacing(
    lines: list[str],
    excluded_lines: set[int],
    ranges_by_line: list[list[tuple[int, int]]],
) -> list[LintIssue]:
    issues = []
    for line_index, line in enumerate(lines):
        if line_index in excluded_lines:
            continue
        for match in _ALNUM_JAPANESE_BOUNDARY_PATTERN.finditer(line):
            boundary = match.start()
            if span_overlaps_ranges(
                boundary - 1,
                boundary + 1,
                ranges_by_line[line_index],
            ):
                continue
            matched_text = line[boundary - 1:boundary + 1]
            suggestion = f"{line[boundary - 1]} {line[boundary]}"
            issues.append(LintIssue(
                line_number=line_index + 1,
                column=boundary,
                matched_text=matched_text,
                category="notation",
                rule_name="alnum-japanese-spacing",
                message="英数字と日本語の間に半角スペースを入れてください。",
                suggestion=suggestion,
            ))
    return issues
