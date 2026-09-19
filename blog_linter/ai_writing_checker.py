"""textlint を使って AI らしい文章パターンを検出する"""
import json
from pathlib import Path
import tempfile
import shutil
import subprocess

from blog_linter.models import LintIssue


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
TEXTLINT_CONFIG = REPOSITORY_ROOT / ".textlintrc.json"
BLOG_TEXTLINT_CONFIG = REPOSITORY_ROOT / ".textlintrc.blog.json"
TEXTLINT_BINARY = REPOSITORY_ROOT / "node_modules" / ".bin" / "textlint"


def _skip_issue(message: str) -> LintIssue:
    """AI 文体チェックを実行できない理由を指摘形式で返す"""
    return LintIssue(
        line_number=0,
        column=0,
        matched_text="",
        category="ai_writing",
        rule_name="チェックをスキップ",
        message=message,
    )


def _short_rule_name(rule_id: object) -> str:
    """textlint の ruleId から表示用の短い名前を作る"""
    if not isinstance(rule_id, str) or not rule_id:
        return "不明なルール"
    return rule_id.rsplit("/", maxsplit=1)[-1]


def check_ai_writing(
    file_path: Path,
    config_path: Path = TEXTLINT_CONFIG,
) -> list[LintIssue]:
    """対象ファイルを textlint で検査し、共通の指摘型に変換する"""
    if shutil.which("npx") is None or not TEXTLINT_BINARY.exists():
        return [_skip_issue(
            "textlint 未導入のため AI 文体チェックをスキップしました"
        )]

    # textlint は .md 以外（ブログ記事の .mdx 等）を無言でスキップし、
    # 指摘 0 件・終了コード 0 を返す。偽のクリーン判定になるため、
    # 拡張子が .md でなければ同じ内容を .md の一時ファイルへ写して検査する。
    # 内容は一字一句同じなので行番号・桁はそのまま元ファイルに対応する。
    with tempfile.TemporaryDirectory() as work_dir:
        target = file_path.resolve()
        if target.suffix.lower() != ".md":
            copied = Path(work_dir) / (target.stem + ".md")
            try:
                copied.write_bytes(target.read_bytes())
            except OSError as error:
                return [_skip_issue(
                    f"一時ファイルを作れなかったため AI 文体チェックをスキップしました: {error}"
                )]
            target = copied
        return _run_textlint(target, config_path)


def _run_textlint(
    file_path: Path,
    config_path: Path,
) -> list[LintIssue]:
    """textlint を実行して結果を共通の指摘型に変換する"""
    command = [
        "npx",
        "--no-install",
        "textlint",
        "--config",
        str(config_path),
        "-f",
        "json",
        str(file_path.resolve()),
    ]
    try:
        result = subprocess.run(
            command,
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return [_skip_issue(
            "textlint が 60 秒以内に完了しなかったため AI 文体チェックをスキップしました"
        )]
    except OSError as error:
        return [_skip_issue(
            f"textlint を実行できなかったため AI 文体チェックをスキップしました: {error}"
        )]

    try:
        reports = json.loads(result.stdout)
        if not isinstance(reports, list):
            raise ValueError("JSON のルートが配列ではありません")
    except (json.JSONDecodeError, ValueError) as error:
        return [_skip_issue(
            f"textlint の結果を解析できなかったため AI 文体チェックをスキップしました: {error}"
        )]

    issues: list[LintIssue] = []
    for report in reports:
        if not isinstance(report, dict):
            continue
        messages = report.get("messages", [])
        if not isinstance(messages, list):
            continue
        for message in messages:
            if not isinstance(message, dict):
                continue
            line = message.get("line", 0)
            column = message.get("column", 0)
            text = message.get("message", "textlint が AI 文体の可能性を検出しました")
            issues.append(LintIssue(
                line_number=line if isinstance(line, int) else 0,
                column=column if isinstance(column, int) else 0,
                matched_text="",
                category="ai_writing",
                rule_name=_short_rule_name(message.get("ruleId")),
                message=text if isinstance(text, str) else str(text),
            ))
    return issues
