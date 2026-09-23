"""表記ブレチェッカー: プリセットルールで表記の統一性をチェックする"""
import re

from blog_linter.markdown_utils import (
    mask_ranges,
    non_prose_ranges,
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


# 非公式訳語の辞書。**書き手が実際に使う語だけを入れる。**
# 「状態機械」は Claude が書いた語で、書き手が「聞き慣れていない」と指摘したもの。
# 書き手の文章には現れないため、検査するルールとしては筋違いだった（2026-09-23 に取り下げ）。
# Claude 自身が避けるべき語は blog-voice の STYLE.md に置く。
BLOG_UNOFFICIAL_TRANSLATIONS: dict[str, str] = {}

def build_blog_notation_rules() -> list[dict]:
    """blog プロファイルの表記ルールを組み立てる。

    モジュール読み込み時ではなく呼び出し時に作る。辞書（BLOG_UNOFFICIAL_TRANSLATIONS）へ
    語を足したときに、その場で効くようにするため。
    """
    return [
        {
            "preferred": "Eufy",
            "variants": [r"(?<![A-Za-z0-9])eufy(?![A-Za-z0-9])"],
            "case_sensitive": True,
            "rule_name": "brand-capitalization",
            "needs_review": True,
        },
        {
            "preferred": "ニワトリ",
            "variants": [r"にわとり", r"鶏"],
            "rule_name": "chicken-notation",
            "needs_review": True,
            "avoid_kanji_compound": True,
        },
        *[
            {
                "preferred": preferred,
                "variants": [re.escape(variant)],
                "rule_name": "unofficial-translation",
                "needs_review": True,
                "avoid_kanji_compound": True,
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
_KANJI_PATTERN = re.compile(r"[一-鿿々〆ヶ]")
_SLASH_TERM = rf"[A-Za-z0-9{_JAPANESE_CHARACTER_CLASS}+#-]+?"
_SLASH_COORDINATION_PATTERN = re.compile(
    rf"(?<![A-Za-z0-9{_JAPANESE_CHARACTER_CLASS}/])"
    rf"{_SLASH_TERM}(?:/{_SLASH_TERM})+"
    rf"(?=(?:\s|[。、！？）」』】]|$|を|に|へ|が|は|と|で|の|も|から|まで))"
)
_ALNUM_JAPANESE_BOUNDARY_PATTERN = re.compile(
    rf"(?:(?<=[A-Za-z0-9])(?=[{_JAPANESE_CHARACTER_CLASS}])|"
    rf"(?<=[{_JAPANESE_CHARACTER_CLASS}])(?=[A-Za-z0-9]))"
)


def _legacy_is_in_code_block(lines: list[str], line_idx: int) -> bool:
    """Qiita 変更前と同じ方法でコードブロック内か判定する"""
    in_block = False
    for i in range(line_idx):
        stripped = lines[i].strip()
        if stripped.startswith("```"):
            in_block = not in_block
    return in_block


def _legacy_is_in_inline_code(line: str, start: int) -> bool:
    """Qiita 変更前と同じ方法でインラインコード内か判定する"""
    before = line[:start]
    backtick_count = before.count("`")
    return backtick_count % 2 == 1


def check_notation(text: str, profile: str = "blog") -> list[LintIssue]:
    """テキスト内の表記ブレを検出する"""
    if profile != "blog":
        return _check_legacy_notation(text)

    issues = []
    lines = text.split("\n")
    ranges = non_prose_ranges(text)
    masked_lines = mask_ranges(text, ranges).split("\n")

    for rule in _notation_rules_for_profile("blog"):
        preferred = rule["preferred"]
        note = rule.get("note", "")
        case_sensitive = rule.get("case_sensitive", False)
        context_words = rule.get("context_words", [])

        for variant_pattern in rule["variants"]:
            flags = 0 if case_sensitive else re.IGNORECASE
            pattern = re.compile(variant_pattern, flags)

            for line_idx, masked_line in enumerate(masked_lines):
                line = lines[line_idx]
                for match in pattern.finditer(masked_line):
                    if (
                        rule.get("avoid_kanji_compound", False)
                        and _has_adjacent_kanji(
                            line,
                            match.start(),
                            match.end(),
                        )
                    ):
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

                    rule_name = rule.get(
                        "rule_name",
                        f"表記ブレ: {preferred}",
                    )
                    needs_review = rule.get("needs_review", False)
                    message = (
                        _review_message(rule_name, matched_text, preferred)
                        if needs_review
                        else (
                            f"「{matched_text}」→「{preferred}」に統一を推奨。"
                            f"{note}"
                        )
                    )
                    issues.append(LintIssue(
                        line_number=line_idx + 1,
                        column=match.start() + 1,
                        matched_text=matched_text,
                        category="notation",
                        rule_name=rule_name,
                        message=message,
                        suggestion=None if needs_review else preferred,
                        needs_review=needs_review,
                    ))

    issues.extend(_check_slash_coordination(lines, masked_lines))
    issues.extend(_check_alnum_japanese_spacing(lines, masked_lines))

    return issues


def _check_legacy_notation(text: str) -> list[LintIssue]:
    """main 版と同じ Qiita 向け表記チェックを実行する"""
    issues = []
    lines = text.split("\n")

    for rule in NOTATION_RULES:
        preferred = rule["preferred"]
        note = rule.get("note", "")
        case_sensitive = rule.get("case_sensitive", False)
        context_words = rule.get("context_words", [])

        for variant_pattern in rule["variants"]:
            flags = 0 if case_sensitive else re.IGNORECASE
            pattern = re.compile(variant_pattern, flags)

            for line_idx, line in enumerate(lines):
                if _legacy_is_in_code_block(lines, line_idx):
                    continue

                for match in pattern.finditer(line):
                    if _legacy_is_in_inline_code(line, match.start()):
                        continue

                    matched_text = match.group(0)
                    if matched_text == preferred:
                        continue

                    if context_words:
                        context_window = "\n".join(
                            lines[max(0, line_idx - 2):line_idx + 3]
                        ).lower()
                        if not any(
                            word in context_window for word in context_words
                        ):
                            continue

                    issues.append(LintIssue(
                        line_number=line_idx + 1,
                        column=match.start() + 1,
                        matched_text=matched_text,
                        category="notation",
                        rule_name=f"表記ブレ: {preferred}",
                        message=(
                            f"「{matched_text}」→「{preferred}」に統一を推奨。"
                            f"{note}"
                        ),
                        suggestion=preferred,
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
    rules.extend(build_blog_notation_rules())
    return rules


def _review_message(
    rule_name: str,
    matched_text: str,
    preferred: str,
) -> str:
    """文脈確認が必要な表記ルールのメッセージを返す。"""
    if rule_name == "brand-capitalization":
        return (
            f"「{matched_text}」は製品名なら「{preferred}」、ライブラリ名・"
            "アカウント名・URLならそのままです。文脈に合う表記か"
            "確認してください。"
        )
    if rule_name == "chicken-notation":
        return (
            f"「{matched_text}」をひらがな・漢字・カタカナのどれで書くかは"
            "文脈で決まります。表記を確認してください。"
        )
    return (
        f"「{matched_text}」が「{preferred}」を指すかは文脈で決まります。"
        "意図した用語か確認してください。"
    )


def _has_adjacent_kanji(line: str, start: int, end: int) -> bool:
    """対象語の直前または直後が漢字かを返す。"""
    before_is_kanji = (
        start > 0 and _KANJI_PATTERN.fullmatch(line[start - 1]) is not None
    )
    after_is_kanji = (
        end < len(line) and _KANJI_PATTERN.fullmatch(line[end]) is not None
    )
    return before_is_kanji or after_is_kanji


def _check_slash_coordination(
    lines: list[str],
    masked_lines: list[str],
) -> list[LintIssue]:
    """語をつなぐスラッシュを文脈確認として報告する。"""
    issues = []
    for line_index, masked_line in enumerate(masked_lines):
        line = lines[line_index]
        for match in _SLASH_COORDINATION_PATTERN.finditer(masked_line):
            matched_text = line[match.start():match.end()]
            issues.append(LintIssue(
                line_number=line_index + 1,
                column=match.start() + 1,
                matched_text=matched_text,
                category="notation",
                rule_name="slash-coordination",
                message=(
                    f"「{matched_text}」のスラッシュが並列、固有表記、"
                    "パスのどれに当たるかは文脈で決まります。表記を"
                    "確認してください。"
                ),
                suggestion=None,
                needs_review=True,
            ))
    return issues


def _check_alnum_japanese_spacing(
    lines: list[str],
    masked_lines: list[str],
) -> list[LintIssue]:
    issues = []
    for line_index, masked_line in enumerate(masked_lines):
        line = lines[line_index]
        for match in _ALNUM_JAPANESE_BOUNDARY_PATTERN.finditer(masked_line):
            boundary = match.start()
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
