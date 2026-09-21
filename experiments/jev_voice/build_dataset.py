from __future__ import annotations

import html
import json
import re
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


DEFAULT_CORRECTIONS_PATH = Path(
    "/home/tetutetu/.claude/skills/blog-voice/corrections.md"
)
DEFAULT_ARTICLES_ROOT = Path(
    "/home/tetutetu/projects/blog-site-dev/content/posts"
)
DEFAULT_OUTPUT_PATH = Path(__file__).with_name("dataset.json")

TRAIN_ARTICLES = (
    "aws-lambda-durable-functions",
    "aws-lambda-microvms",
    "aws-lambda-managed-instances",
    "coop-temperature-device",
)
TEST_ARTICLES = (
    "hello-world",
    "aws-lambda-durable-functions-api-flow",
    "coop-camera-video",
)
ARTICLE_SPLITS = {
    **{article: "train" for article in TRAIN_ARTICLES},
    **{article: "test" for article in TEST_ARTICLES},
}

# corrections.md に記録されたスラッグと、現在の記事ディレクトリ名が食い違う場合の対応表。
# hello-world は本番公開時に blog-with-astro へリネームされた（2026-09-17 公開）。
# 指摘のラベルは旧スラッグで残るため、本文はこの対応表を経由して探す。
ARTICLE_SOURCE_ALIASES = {
    "hello-world": "blog-with-astro",
}

EXPECTED_CORRECTION_COUNT = 66
MIN_NORMAL_LENGTH = 20

DatasetRecord = dict[str, str]

HEADING_PATTERN = re.compile(r"^##\s+(.+)$")
FIELD_PATTERN = re.compile(r"^- (NG|OK|理由|記事):\s*(.*)$")
POST_SLUG_PATTERN = re.compile(r"(?:^|/)posts/([^/]+)/")
STATUS_PATTERN = re.compile(
    r"\s+→(?:STYLE|linter|モード|メモリ)[^\n]*$"
)
FENCE_PATTERN = re.compile(r"^\s*(`{3,}|~{3,})")
OPEN_TAG_PATTERN = re.compile(r"^<([A-Za-z][\w.:-]*)\b")
HEADING_LINE_PATTERN = re.compile(r"^\s{0,3}#{1,6}(?:\s+|$)")
LIST_LINE_PATTERN = re.compile(r"^\s*(?:[-+*]|\d+[.)])\s+")
LINK_ONLY_PATTERN = re.compile(
    r"^\s*\[[^]]+\]\([^)]+\)[。.]?\s*$"
)
REFERENCE_LINK_PATTERN = re.compile(r"^\s*\[[^]]+\]:\s*\S+")
RAW_URL_PATTERN = re.compile(r"^\s*<?https?://\S+>?[。.]?\s*$")
IMAGE_PATTERN = re.compile(r"!\[[^]]*\]\([^)]+\)")
INLINE_LINK_PATTERN = re.compile(r"(?<!!)\[([^]]+)\]\([^)]+\)")
REFERENCE_INLINE_LINK_PATTERN = re.compile(r"\[([^]]+)\]\[[^]]*\]")
HTML_TAG_PATTERN = re.compile(r"</?[A-Za-z][^>]*>")
SENTENCE_BOUNDARY_PATTERN = re.compile(r"(?<=[。！？!?])")


@dataclass(frozen=True)
class CorrectionPair:
    ng: str
    ok: str
    article: str
    split: str
    note: str
    raw_ng: str
    raw_ok: str


def _drop_trailing_parenthetical(text: str) -> str:
    stripped = text.rstrip()
    pairs = {"）": "（", ")": "("}
    if not stripped or stripped[-1] not in pairs:
        return text

    closing = stripped[-1]
    opening = pairs[closing]
    depth = 0
    for index in range(len(stripped) - 1, -1, -1):
        character = stripped[index]
        if character == closing:
            depth += 1
        elif character == opening:
            depth -= 1
            if depth == 0:
                return stripped[:index].rstrip()
    return text


def _clean_inline_markdown(text: str) -> str:
    cleaned = IMAGE_PATTERN.sub("", text)
    cleaned = INLINE_LINK_PATTERN.sub(r"\1", cleaned)
    cleaned = REFERENCE_INLINE_LINK_PATTERN.sub(r"\1", cleaned)
    cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
    cleaned = cleaned.replace("**", "").replace("__", "")
    cleaned = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"\1", cleaned)
    cleaned = re.sub(r"~~([^~]+)~~", r"\1", cleaned)
    cleaned = re.sub(r"\[\^[^]]+\]", "", cleaned)
    cleaned = HTML_TAG_PATTERN.sub("", cleaned)
    cleaned = re.sub(r"\\([\\`*{}\[\]()#+.!_-])", r"\1", cleaned)
    return " ".join(html.unescape(cleaned).split())


def clean_correction_text(value: str) -> str:
    """指摘値から引用記号と明らかな末尾注釈を除く。"""
    body = value.strip()
    without_parenthetical = _drop_trailing_parenthetical(body)
    if without_parenthetical != body and without_parenthetical.endswith("」"):
        body = without_parenthetical

    if (
        body.startswith("「")
        and body.endswith("」")
        and body.count("「") == 1
        and body.count("」") == 1
    ):
        body = body[1:-1]

    return _clean_inline_markdown(body)


def _heading_to_note(heading: str) -> str:
    note = re.sub(r"^\d{4}-\d{2}-\d{2}\s+", "", heading).strip()
    note = STATUS_PATTERN.sub("", note).strip()

    while True:
        shortened = _drop_trailing_parenthetical(note)
        if shortened == note:
            return note
        note = shortened


def _article_split(article: str) -> str:
    try:
        return ARTICLE_SPLITS[article]
    except KeyError as error:
        raise ValueError(f"分割が定義されていない記事です: {article}") from error


def _build_correction_pair(
    heading: str,
    fields: dict[str, str],
) -> CorrectionPair | None:
    if "NG" not in fields or "OK" not in fields:
        return None

    article_path = fields.get("記事")
    if article_path is None:
        raise ValueError(f"記事欄がない指摘です: {heading}")

    normalized_path = article_path.replace("\\", "/")
    slug_match = POST_SLUG_PATTERN.search(normalized_path)
    if slug_match is None:
        raise ValueError(f"記事スラッグを読み取れません: {article_path}")

    article = slug_match.group(1)
    ng = clean_correction_text(fields["NG"])
    ok = clean_correction_text(fields["OK"])
    if not ng or not ok:
        raise ValueError(f"NG または OK が空の指摘です: {heading}")

    return CorrectionPair(
        ng=ng,
        ok=ok,
        article=article,
        split=_article_split(article),
        note=_heading_to_note(heading),
        raw_ng=fields["NG"],
        raw_ok=fields["OK"],
    )


def parse_corrections(path: Path) -> list[CorrectionPair]:
    """corrections.md から NG/OK が揃った指摘だけを読み取る。"""
    pairs: list[CorrectionPair] = []
    heading: str | None = None
    fields: dict[str, str] = {}

    for line in path.read_text(encoding="utf-8").splitlines():
        heading_match = HEADING_PATTERN.match(line)
        if heading_match is not None:
            if heading is not None:
                pair = _build_correction_pair(heading, fields)
                if pair is not None:
                    pairs.append(pair)
            heading = heading_match.group(1)
            fields = {}
            continue

        field_match = FIELD_PATTERN.match(line)
        if heading is not None and field_match is not None:
            fields[field_match.group(1)] = field_match.group(2)

    if heading is not None:
        pair = _build_correction_pair(heading, fields)
        if pair is not None:
            pairs.append(pair)

    return pairs


def _is_self_closing_tag(line: str) -> bool:
    return re.search(r"/\s*>", line) is not None


def _contains_closing_tag(line: str, tag: str) -> bool:
    pattern = rf"</{re.escape(tag)}\s*>"
    return re.search(pattern, line, flags=re.IGNORECASE) is not None


def _normalization_key(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", _clean_inline_markdown(text))
    normalized = "".join(normalized.split())
    normalized = normalized.strip("\"'「」『』")
    return normalized.rstrip("。．.!！？?")


def _is_long_enough(text: str, min_length: int) -> bool:
    visible = re.sub(r"\s+", "", text)
    if len(visible) < min_length:
        return False
    return re.search(r"[A-Za-z0-9ぁ-んァ-ヶ一-龠々]", visible) is not None


def extract_normal_sentences(
    markdown: str,
    min_length: int = MIN_NORMAL_LENGTH,
) -> list[str]:
    """Markdown/MDX の地の文を文単位で取り出す。"""
    lines = markdown.lstrip("\ufeff").splitlines()
    if lines and lines[0].strip() == "---":
        frontmatter_end = next(
            (
                index
                for index, line in enumerate(lines[1:], start=1)
                if line.strip() == "---"
            ),
            None,
        )
        if frontmatter_end is None:
            return []
        lines = lines[frontmatter_end + 1 :]

    sentences: list[str] = []
    paragraph_lines: list[str] = []
    fence_character: str | None = None
    block_tag: str | None = None
    pending_tag: str | None = None
    in_mdx_comment = False
    in_html_comment = False
    expression_depth = 0

    def flush_paragraph() -> None:
        if not paragraph_lines:
            return

        paragraph = _clean_inline_markdown(" ".join(paragraph_lines))
        paragraph_lines.clear()
        for part in SENTENCE_BOUNDARY_PATTERN.split(paragraph):
            sentence = part.strip()
            if _is_long_enough(sentence, min_length):
                sentences.append(sentence)

    for line in lines:
        stripped = line.strip()
        fence_match = FENCE_PATTERN.match(line)

        if fence_character is not None:
            if (
                fence_match is not None
                and fence_match.group(1)[0] == fence_character
            ):
                fence_character = None
            continue

        if fence_match is not None:
            flush_paragraph()
            fence_character = fence_match.group(1)[0]
            continue

        if block_tag is not None:
            if _contains_closing_tag(line, block_tag):
                block_tag = None
            continue

        if pending_tag is not None:
            if ">" in line:
                if not _is_self_closing_tag(line):
                    block_tag = pending_tag
                pending_tag = None
            continue

        if in_mdx_comment:
            if "*/}" in line:
                in_mdx_comment = False
            continue

        if in_html_comment:
            if "-->" in line:
                in_html_comment = False
            continue

        if expression_depth > 0:
            expression_depth += line.count("{") - line.count("}")
            expression_depth = max(expression_depth, 0)
            continue

        if "{/*" in line:
            flush_paragraph()
            if "*/}" not in line:
                in_mdx_comment = True
            continue

        if "<!--" in line:
            flush_paragraph()
            if "-->" not in line:
                in_html_comment = True
            continue

        if stripped.startswith("{"):
            flush_paragraph()
            expression_depth = max(line.count("{") - line.count("}"), 0)
            continue

        if stripped.startswith(("import ", "export ")):
            flush_paragraph()
            continue

        tag_match = OPEN_TAG_PATTERN.match(stripped)
        if tag_match is not None:
            flush_paragraph()
            tag = tag_match.group(1)
            if ">" not in stripped:
                pending_tag = tag
            elif (
                not _is_self_closing_tag(stripped)
                and not _contains_closing_tag(stripped, tag)
            ):
                block_tag = tag
            continue

        if stripped.startswith("</"):
            flush_paragraph()
            continue

        is_structural_line = (
            not stripped
            or HEADING_LINE_PATTERN.match(line) is not None
            or LIST_LINE_PATTERN.match(line) is not None
            or stripped.startswith((">", "|", ":::", "//"))
            or stripped in {"---", "***", "___"}
            or LINK_ONLY_PATTERN.match(line) is not None
            or REFERENCE_LINK_PATTERN.match(line) is not None
            or RAW_URL_PATTERN.match(line) is not None
            or IMAGE_PATTERN.search(line) is not None
            or stripped.startswith(("（出典:", "（出典：", "出典:", "出典："))
        )
        if is_structural_line:
            flush_paragraph()
            continue

        paragraph_lines.append(stripped)

    flush_paragraph()

    unique_sentences: list[str] = []
    seen: set[str] = set()
    for sentence in sentences:
        key = _normalization_key(sentence)
        if key and key not in seen:
            unique_sentences.append(sentence)
            seen.add(key)
    return unique_sentences


def _correction_forbidden_texts(
    pairs: Sequence[CorrectionPair],
) -> set[str]:
    forbidden: set[str] = set()
    for pair in pairs:
        for cleaned, raw in (
            (pair.ng, pair.raw_ng),
            (pair.ok, pair.raw_ok),
        ):
            forbidden.add(cleaned)
            forbidden.update(
                part.strip()
                for part in SENTENCE_BOUNDARY_PATTERN.split(cleaned)
                if part.strip()
            )
            forbidden.update(
                quoted.strip()
                for quoted in re.findall(r"「([^」]+)」", raw)
                if quoted.strip()
            )
    return forbidden


def _find_article_path(article_root: Path, article: str) -> Path | None:
    # リネーム済みの記事は、旧スラッグのディレクトリが無いので別名も探す
    directory_names = [article]
    alias = ARTICLE_SOURCE_ALIASES.get(article)
    if alias is not None:
        directory_names.append(alias)
    for directory_name in directory_names:
        article_directory = article_root / directory_name
        for filename in ("index.md", "index.mdx"):
            candidate = article_directory / filename
            if candidate.is_file():
                return candidate
    return None


def load_normal_candidates(
    article_root: Path,
    articles: Sequence[str],
) -> tuple[dict[str, list[str]], list[str]]:
    """存在する記事から normal 候補を読み取り、欠落記事も返す。"""
    candidates: dict[str, list[str]] = {}
    missing: list[str] = []
    for article in articles:
        article_path = _find_article_path(article_root, article)
        if article_path is None:
            missing.append(article)
            continue
        candidates[article] = extract_normal_sentences(
            article_path.read_text(encoding="utf-8")
        )
    return candidates, missing


def select_normal_records(
    candidates_by_article: dict[str, list[str]],
    target_count: int,
    forbidden_texts: Iterable[str],
) -> list[DatasetRecord]:
    """記事を順番に巡回し、偏りを抑えて normal レコードを選ぶ。"""
    forbidden_keys = {
        key
        for text in forbidden_texts
        if (key := _normalization_key(text))
    }
    article_order = [
        article
        for article in TRAIN_ARTICLES + TEST_ARTICLES
        if article in candidates_by_article
    ]
    article_order.extend(
        sorted(set(candidates_by_article).difference(article_order))
    )

    indexes = {article: 0 for article in article_order}
    seen: set[str] = set()
    records: list[DatasetRecord] = []

    while len(records) < target_count:
        selected_in_round = False
        for article in article_order:
            candidates = candidates_by_article[article]
            while indexes[article] < len(candidates):
                text = candidates[indexes[article]]
                indexes[article] += 1
                key = _normalization_key(text)
                if not key or key in forbidden_keys or key in seen:
                    continue

                records.append(
                    {
                        "text": text,
                        "label": "normal",
                        "article": article,
                        "split": _article_split(article),
                        "source": "article",
                        "note": "記事本文から抽出",
                    }
                )
                seen.add(key)
                selected_in_round = True
                break

            if len(records) == target_count:
                break

        if not selected_in_round:
            raise ValueError(
                "normal 候補が不足しています: "
                f"必要 {target_count} 件、採用可能 {len(records)} 件"
            )

    return records


def _correction_records(
    pairs: Sequence[CorrectionPair],
) -> list[DatasetRecord]:
    records: list[DatasetRecord] = []
    for pair in pairs:
        for label, text in (("ng", pair.ng), ("ok", pair.ok)):
            records.append(
                {
                    "text": text,
                    "label": label,
                    "article": pair.article,
                    "split": pair.split,
                    "source": "corrections",
                    "note": pair.note,
                }
            )
    return records


def validate_dataset(
    records: Sequence[DatasetRecord],
    expected_correction_count: int | None = None,
) -> None:
    """件数、重複、記事単位の分割を検証する。"""
    required_keys = {"text", "label", "article", "split", "source", "note"}
    for record in records:
        if set(record) != required_keys:
            raise ValueError("データセットのキーが定義と一致しません")
        if not all(record[key] for key in required_keys):
            raise ValueError("空の値を持つレコードがあります")

    counts = Counter(record["label"] for record in records)
    if set(counts) != {"ng", "ok", "normal"}:
        raise ValueError(f"label の種類が不正です: {sorted(counts)}")
    if counts["ng"] != counts["ok"]:
        raise ValueError("ng と ok の件数が一致しません")
    if expected_correction_count is not None and (
        counts["ng"] != expected_correction_count
        or counts["ok"] != expected_correction_count
    ):
        raise ValueError(
            "指摘件数が期待値と一致しません: "
            f"ng={counts['ng']}, ok={counts['ok']}"
        )
    if counts["normal"] < counts["ng"]:
        raise ValueError("normal が ng より少ないです")

    train_articles = {
        record["article"] for record in records if record["split"] == "train"
    }
    test_articles = {
        record["article"] for record in records if record["split"] == "test"
    }
    overlap = train_articles & test_articles
    if overlap:
        raise ValueError(
            "train と test に同じ記事があります: "
            + ", ".join(sorted(overlap))
        )

    for record in records:
        expected_split = _article_split(record["article"])
        if record["split"] != expected_split:
            raise ValueError(
                f"記事 {record['article']} の split が不正です"
            )

    correction_keys = {
        _normalization_key(record["text"])
        for record in records
        if record["label"] in {"ng", "ok"}
    }
    normal_keys = {
        _normalization_key(record["text"])
        for record in records
        if record["label"] == "normal"
    }
    if correction_keys & normal_keys:
        raise ValueError("normal に ng または ok と同じ文が含まれています")


def build_dataset(
    corrections_path: Path = DEFAULT_CORRECTIONS_PATH,
    article_root: Path = DEFAULT_ARTICLES_ROOT,
) -> list[DatasetRecord]:
    """入力ファイルから評価セット全体を組み立てる。"""
    pairs = parse_corrections(corrections_path)
    correction_records = _correction_records(pairs)
    target_articles = [
        article
        for article in TRAIN_ARTICLES + TEST_ARTICLES
        if any(pair.article == article for pair in pairs)
    ]
    candidates, missing_articles = load_normal_candidates(
        article_root,
        target_articles,
    )
    if missing_articles:
        print(
            "警告: 本文が見つからない記事は normal 抽出をスキップします: "
            + ", ".join(missing_articles),
            file=sys.stderr,
        )

    normal_records = select_normal_records(
        candidates,
        target_count=len(pairs),
        forbidden_texts=_correction_forbidden_texts(pairs),
    )
    records = correction_records + normal_records
    validate_dataset(records)
    return records


def write_dataset(records: Sequence[DatasetRecord], output_path: Path) -> None:
    """日本語をエスケープせず JSON ファイルへ保存する。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    records = build_dataset()
    validate_dataset(
        records,
        expected_correction_count=EXPECTED_CORRECTION_COUNT,
    )
    write_dataset(records, DEFAULT_OUTPUT_PATH)

    counts = Counter(record["label"] for record in records)
    print(
        f"{DEFAULT_OUTPUT_PATH} を生成しました "
        f"(ng={counts['ng']}, ok={counts['ok']}, "
        f"normal={counts['normal']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
