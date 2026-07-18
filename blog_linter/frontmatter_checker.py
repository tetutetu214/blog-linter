"""Vault ノートの frontmatter・命名・wikilink を検証する"""
import re
from pathlib import Path

from blog_linter.models import LintIssue

# worklog の wikilink 必須ルールの適用開始日（ISO 形式の文字列比較で判定）
# ルール整備前の過去分（2026-06 以前）は免除する。2026-07-18 kb-lint で決定
WORKLOG_WIKILINK_RULE_START = "2026-07-01"


def load_tag_vocabulary(vault_root: Path) -> set[str]:
    """Vault のタグ語彙ファイルを読み込む"""
    vocabulary_path = vault_root / ".claude" / "tag-vocabulary.txt"
    if not vocabulary_path.is_file():
        raise FileNotFoundError(
            f"タグ語彙ファイルが見つかりません: {vocabulary_path}"
        )

    return {
        line.strip()
        for line in vocabulary_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def _issue(
    rule_name: str,
    message: str,
    line_number: int = 1,
    matched_text: str = "",
) -> LintIssue:
    return LintIssue(
        line_number=line_number,
        column=1,
        matched_text=matched_text,
        category="frontmatter",
        rule_name=rule_name,
        message=message,
    )


def _parse_frontmatter(
    text: str,
) -> tuple[dict[str, str | list[str]] | None, int | None, list[LintIssue]]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, None, [
            _issue("frontmatter 必須", "frontmatter ブロックがありません")
        ]

    closing_index = next(
        (index for index, line in enumerate(lines[1:], start=1)
         if line.strip() == "---"),
        None,
    )
    if closing_index is None:
        return None, None, [
            _issue(
                "frontmatter 未終端",
                "frontmatter を閉じる区切り（---）がありません",
            )
        ]

    values: dict[str, str | list[str]] = {}
    current_list_key: str | None = None
    for line in lines[1:closing_index]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if current_list_key and stripped.startswith("-"):
            item = stripped[1:].strip()
            if item:
                current_value = values[current_list_key]
                if isinstance(current_value, list):
                    current_value.append(item)
            continue
        current_list_key = None
        if ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        key = key.strip()
        raw_value = raw_value.strip()
        if not key:
            continue
        if raw_value.startswith("[") and raw_value.endswith("]"):
            values[key] = [
                item.strip()
                for item in raw_value[1:-1].split(",")
                if item.strip()
            ]
        elif not raw_value:
            # 値が空のキーはブロックリスト（次行以降の "- item"）の開始とみなす
            values[key] = []
            current_list_key = key
        else:
            values[key] = raw_value

    return values, closing_index, []


def check_frontmatter(
    text: str,
    file_path: Path,
    vault_root: Path,
    tag_vocabulary: set[str],
) -> list[LintIssue]:
    """Vault ノート固有の規則を検証する"""
    values, closing_index, issues = _parse_frontmatter(text)
    if values is None or closing_index is None:
        return issues

    author = values.get("author", "")
    if author not in {"human", "claude"}:
        issues.append(_issue(
            "author 必須",
            "author は human または claude を指定してください",
        ))

    tags = values.get("tags")
    if isinstance(tags, list):
        for tag in tags:
            if tag not in tag_vocabulary:
                issues.append(_issue(
                    "タグ語彙",
                    f"タグ「{tag}」はタグ語彙に登録されていません",
                    matched_text=tag,
                ))

    try:
        relative_path = file_path.resolve().relative_to(vault_root.resolve())
    except ValueError:
        relative_path = file_path
    parts = relative_path.parts
    body = "\n".join(text.splitlines()[closing_index + 1:])
    wikilink_count = len(re.findall(r"\[\[[^\[\]]+\]\]", body))

    if len(parts) >= 2 and parts[0] == "wiki" and parts[1] == "concepts":
        if not values.get("sources"):
            issues.append(_issue(
                "sources 必須",
                "wiki/concepts のノートには sources が必要です",
            ))
        if wikilink_count < 2:
            issues.append(_issue(
                "wikilink 必須",
                "wiki/concepts の本文には wikilink が2つ以上必要です",
            ))

    if parts and parts[0] == "worklog":
        name_match = re.fullmatch(r"(\d{4}-\d{2}-\d{2})\.md", file_path.name)
        if not name_match:
            issues.append(_issue(
                "worklog 命名規則",
                "worklog のファイル名は YYYY-MM-DD.md 形式にしてください",
                matched_text=file_path.name,
            ))
        # wikilink ルールはルール整備日以降の worklog にのみ適用する
        # （それ以前の過去分はバックフィルせず免除。日付が読めない名前は適用側に倒す）
        rule_applies = name_match is None or name_match.group(1) >= WORKLOG_WIKILINK_RULE_START
        if rule_applies and wikilink_count < 1:
            issues.append(_issue(
                "wikilink 必須",
                "worklog の本文には wikilink が1つ以上必要です",
            ))

    if parts and parts[0] == "reports":
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}_[^/]+\.md", file_path.name):
            issues.append(_issue(
                "reports 命名規則",
                "reports のファイル名は YYYY-MM-DD_slug.md 形式にしてください",
                matched_text=file_path.name,
            ))
        if values.get("researched_at") and not values.get("expires"):
            issues.append(_issue(
                "調査日と期限",
                "researched_at がある場合は expires も指定してください",
            ))

    return issues
