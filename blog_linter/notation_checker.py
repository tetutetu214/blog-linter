"""表記ブレチェッカー: プリセットルールで表記の統一性をチェックする"""
import re
from blog_linter.secret_checker import LintIssue


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


def check_notation(text: str) -> list[LintIssue]:
    """テキスト内の表記ブレを検出する"""
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
                if _is_in_code_block(lines, line_idx):
                    continue

                for match in pattern.finditer(line):
                    if _is_in_inline_code(line, match.start(), match.end()):
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
                        rule_name=f"表記ブレ: {preferred}",
                        message=f"「{matched_text}」→「{preferred}」に統一を推奨。{note}",
                        suggestion=preferred,
                    ))

    return issues
