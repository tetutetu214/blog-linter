from __future__ import annotations

import html
import json
import re
import subprocess
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from statistics import fmean
from typing import Mapping, Sequence


DEFAULT_ARTICLE_REPOSITORY = Path(
    "/home/tetutetu/projects/blog-site-dev"
)
DEFAULT_OUTPUT_PATH = Path(__file__).with_name("article_dataset.json")
DEFAULT_REPORT_PATH = Path(__file__).with_name(
    "article_dataset_report.md"
)

TRAIN_ARTICLES = (
    "aws-lambda-microvms",
    "aws-lambda-durable-functions",
    "coop-temperature-device",
)
TEST_ARTICLES = (
    "aws-lambda-managed-instances",
    "blog-with-astro",
)

# 200 文字未満では節固有の文体より見出しや短い列挙の影響が強いため除外する。
MIN_SECTION_CHARS = 200
# ほぼ同文の節はラベルだけが異なる無意味な評価例になるため両版から除外する。
UNCHANGED_SECTION_RATIO = 0.98
SURFACE_WARNING_ACCURACY = 0.80


@dataclass(frozen=True)
class ArticleSource:
    slug: str
    split: str
    draft_commit: str
    draft_path: str
    published_commit: str
    published_path: str

    def as_dict(self) -> dict[str, str]:
        return {
            "slug": self.slug,
            "split": self.split,
            "draft_commit": self.draft_commit,
            "draft_path": self.draft_path,
            "published_commit": self.published_commit,
            "published_path": self.published_path,
        }


ARTICLE_SOURCES = (
    # 1c4d179 は記事を draft として初めて追加した本文初稿のコミット。
    ArticleSource(
        slug="aws-lambda-microvms",
        split="train",
        draft_commit="1c4d179",
        draft_path="content/posts/aws-lambda-microvms/index.md",
        published_commit="07b4843",
        published_path="content/posts/aws-lambda-microvms/index.mdx",
    ),
    # 94eb16a は約 1 KB の骨子だけなので、本文が揃った 9ce53a4 を初稿にする。
    ArticleSource(
        slug="aws-lambda-durable-functions",
        split="train",
        draft_commit="9ce53a4",
        draft_path=(
            "content/posts/aws-lambda-durable-functions/index.mdx"
        ),
        published_commit="471e2c0",
        published_path=(
            "content/posts/aws-lambda-durable-functions/index.mdx"
        ),
    ),
    # 5fd4128 は素材ノートとともに記事本文を初めて追加した下書きコミット。
    ArticleSource(
        slug="coop-temperature-device",
        split="train",
        draft_commit="5fd4128",
        draft_path="content/posts/coop-temperature-device/index.md",
        published_commit="6bd110f",
        published_path="content/posts/coop-temperature-device/index.mdx",
    ),
    # 40eee73 は別記事から分割され、LMI 単独の記事になった最初の本文コミット。
    ArticleSource(
        slug="aws-lambda-managed-instances",
        split="test",
        draft_commit="40eee73",
        draft_path=(
            "content/posts/aws-lambda-managed-instances/index.md"
        ),
        published_commit="fd24cd4",
        published_path=(
            "content/posts/aws-lambda-managed-instances/index.mdx"
        ),
    ),
    # 4f16fe0 が構成を整えた本文初稿で、公開時に hello-world から改名された。
    ArticleSource(
        slug="blog-with-astro",
        split="test",
        draft_commit="4f16fe0",
        draft_path="content/posts/hello-world/index.mdx",
        published_commit="2edb94a",
        published_path="content/posts/blog-with-astro/index.mdx",
    ),
)

ARTICLE_BY_SLUG = {source.slug: source for source in ARTICLE_SOURCES}
VARIANT_LABELS = {"draft": "ai", "published": "human"}

FENCE_PATTERN = re.compile(r"^\s*(`{3,}|~{3,})")
HEADING_PATTERN = re.compile(r"^\s{0,3}#{1,6}(?:\s+|$)")
H2_PATTERN = re.compile(r"^\s{0,3}##(?!#)(?:\s+|$)(.*)$")
LIST_PATTERN = re.compile(r"^\s*(?:[-+*]|\d+[.)])\s+")
MODULE_PATTERN = re.compile(r"^\s*(?:import|export)\b")
REFERENCE_LINK_PATTERN = re.compile(r"^\s*\[[^]]+\]:\s*\S+")
LINK_ONLY_PATTERN = re.compile(
    r"^\s*(?:\[[^]]+\]\([^)]+\)|\[[^]]+\]\[[^]]*\]|"
    r"<?https?://\S+>?)[。.]?\s*$"
)
IMAGE_PATTERN = re.compile(r"!\[[^]]*\]\([^)]+\)")
REFERENCE_IMAGE_PATTERN = re.compile(r"!\[[^]]*\]\[[^]]*\]")
INLINE_LINK_PATTERN = re.compile(r"(?<!!)\[([^]]+)\]\([^)]+\)")
REFERENCE_INLINE_LINK_PATTERN = re.compile(r"\[([^]]+)\]\[[^]]*\]")
INLINE_CODE_PATTERN = re.compile(r"(`+)(.*?)\1")
SENTENCE_PATTERN = re.compile(r".+?(?:[。！？!?]+|$)")

RECORD_KEYS = {
    "id",
    "article",
    "split",
    "variant",
    "label",
    "granularity",
    "heading",
    "section_index",
    "commit",
    "source_path",
    "text",
    "chars",
}

FEATURE_LABELS = {
    "chars": "文字数",
    "mean_sentence_chars": "1文あたりの平均文字数",
    "period_ending_rate": "文末句点率",
    "commas_per_sentence": "1文あたりの読点数",
    "list_line_rate": "箇条書き行の比率",
    "heading_count": "見出し数",
    "desu_masu_rate": "「です・ます」で終わる文の比率",
}


@dataclass(frozen=True)
class Section:
    heading: str
    index: int
    text: str

    @property
    def chars(self) -> int:
        return visible_character_count(self.text)


@dataclass(frozen=True)
class SectionExclusionCounts:
    short_draft: int = 0
    short_published: int = 0
    unchanged_draft: int = 0
    unchanged_published: int = 0

    def __add__(
        self,
        other: SectionExclusionCounts,
    ) -> SectionExclusionCounts:
        return SectionExclusionCounts(
            short_draft=self.short_draft + other.short_draft,
            short_published=(
                self.short_published + other.short_published
            ),
            unchanged_draft=(
                self.unchanged_draft + other.unchanged_draft
            ),
            unchanged_published=(
                self.unchanged_published
                + other.unchanged_published
            ),
        )


@dataclass(frozen=True)
class ThresholdResult:
    accuracy: float
    threshold: float
    ai_when: str


def _strip_frontmatter_and_fences(markdown: str) -> str:
    lines = markdown.lstrip("\ufeff").splitlines()
    if lines and lines[0].strip() == "---":
        end_index = next(
            (
                index
                for index, line in enumerate(lines[1:], start=1)
                if line.strip() == "---"
            ),
            None,
        )
        if end_index is None:
            return ""
        lines = lines[end_index + 1 :]

    kept_lines: list[str] = []
    fence_character: str | None = None
    fence_length = 0
    for line in lines:
        match = FENCE_PATTERN.match(line)
        if fence_character is not None:
            if match is not None:
                marker = match.group(1)
                if (
                    marker[0] == fence_character
                    and len(marker) >= fence_length
                ):
                    fence_character = None
                    fence_length = 0
            continue

        if match is not None:
            marker = match.group(1)
            fence_character = marker[0]
            fence_length = len(marker)
            continue

        kept_lines.append(line)

    return "\n".join(kept_lines)


def _remove_comments(text: str) -> str:
    without_mdx = re.sub(
        r"\{/\*.*?(?:\*/\}|\Z)",
        "",
        text,
        flags=re.DOTALL,
    )
    return re.sub(
        r"<!--.*?(?:-->|\Z)",
        "",
        without_mdx,
        flags=re.DOTALL,
    )


def _find_tag_end(text: str, start: int) -> int | None:
    quote: str | None = None
    escaped = False
    expression_depth = 0
    for index in range(start + 1, len(text)):
        character = text[index]
        if quote is not None:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            continue

        if character in {'"', "'"}:
            quote = character
        elif character == "{":
            expression_depth += 1
        elif character == "}" and expression_depth > 0:
            expression_depth -= 1
        elif character == ">" and expression_depth == 0:
            return index + 1
    return None


def _parse_tag(
    text: str,
    start: int,
) -> tuple[int, str, bool, bool] | None:
    if start >= len(text) or text[start] != "<":
        return None
    end = _find_tag_end(text, start)
    if end is None:
        return None
    token = text[start:end]
    match = re.match(
        r"<\s*(/?)\s*([A-Za-z][\w.:-]*)\b",
        token,
    )
    if match is None:
        return None
    return (
        end,
        match.group(2),
        bool(match.group(1)),
        token.rstrip().endswith("/>"),
    )


def _find_matching_tag_end(
    text: str,
    start: int,
    tag_name: str,
) -> int | None:
    depth = 1
    cursor = start
    folded_name = tag_name.casefold()
    while cursor < len(text):
        tag_start = text.find("<", cursor)
        if tag_start < 0:
            return None
        parsed = _parse_tag(text, tag_start)
        if parsed is None:
            cursor = tag_start + 1
            continue
        end, name, is_closing, is_self_closing = parsed
        if name.casefold() == folded_name:
            if is_closing:
                depth -= 1
                if depth == 0:
                    return end
            elif not is_self_closing:
                depth += 1
        cursor = end
    return None


def _remove_jsx_components(text: str) -> str:
    output: list[str] = []
    cursor = 0
    while cursor < len(text):
        tag_start = text.find("<", cursor)
        if tag_start < 0:
            output.append(text[cursor:])
            break
        output.append(text[cursor:tag_start])
        parsed = _parse_tag(text, tag_start)
        if parsed is None:
            output.append("<")
            cursor = tag_start + 1
            continue

        end, name, is_closing, is_self_closing = parsed
        if is_closing or is_self_closing:
            cursor = end
            continue

        matching_end = _find_matching_tag_end(text, end, name)
        cursor = matching_end if matching_end is not None else end

    return "".join(output)


def _remove_mdx_expressions(text: str) -> str:
    output: list[str] = []
    cursor = 0
    while cursor < len(text):
        if text[cursor] != "{":
            output.append(text[cursor])
            cursor += 1
            continue

        depth = 1
        cursor += 1
        quote: str | None = None
        escaped = False
        while cursor < len(text) and depth > 0:
            character = text[cursor]
            if quote is not None:
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == quote:
                    quote = None
            elif character in {'"', "'", "`"}:
                quote = character
            elif character == "{":
                depth += 1
            elif character == "}":
                depth -= 1
            cursor += 1
    return "".join(output)


def _clean_inline_markdown(text: str) -> str:
    cleaned = IMAGE_PATTERN.sub("", text)
    cleaned = REFERENCE_IMAGE_PATTERN.sub("", cleaned)
    cleaned = INLINE_LINK_PATTERN.sub(r"\1", cleaned)
    cleaned = REFERENCE_INLINE_LINK_PATTERN.sub(r"\1", cleaned)
    cleaned = INLINE_CODE_PATTERN.sub(r"\2", cleaned)
    cleaned = re.sub(r"(\*\*|__)(.+?)\1", r"\2", cleaned)
    cleaned = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"\1", cleaned)
    cleaned = re.sub(r"(?<!_)_([^_]+)_(?!_)", r"\1", cleaned)
    cleaned = re.sub(r"~~([^~]+)~~", r"\1", cleaned)
    cleaned = re.sub(r"\[\^[^]]+\]", "", cleaned)
    cleaned = re.sub(r"\\([\\`*{}\[\]()#+.!_-])", r"\1", cleaned)
    return " ".join(html.unescape(cleaned).split())


def extract_article_text(markdown: str) -> str:
    """Markdown/MDX から両ラベル共通の規則で本文だけを抽出する。"""
    text = _strip_frontmatter_and_fences(markdown)
    text = _remove_comments(text)
    text = _remove_jsx_components(text)
    text = _remove_mdx_expressions(text)

    blocks: list[str] = []
    paragraph_lines: list[str] = []

    def flush_paragraph() -> None:
        if not paragraph_lines:
            return
        paragraph = _clean_inline_markdown(" ".join(paragraph_lines))
        paragraph_lines.clear()
        if paragraph:
            blocks.append(paragraph)

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            continue
        if MODULE_PATTERN.match(line) is not None:
            flush_paragraph()
            continue
        if stripped.startswith(("|", ">", "//", ":::")):
            flush_paragraph()
            continue
        if stripped in {"---", "***", "___"}:
            flush_paragraph()
            continue
        if stripped.startswith(("（出典:", "（出典：", "出典:", "出典：")):
            flush_paragraph()
            continue
        if REFERENCE_LINK_PATTERN.match(line) is not None:
            flush_paragraph()
            continue
        if LINK_ONLY_PATTERN.match(line) is not None:
            flush_paragraph()
            continue

        without_images = IMAGE_PATTERN.sub("", stripped)
        without_images = REFERENCE_IMAGE_PATTERN.sub("", without_images)
        if not without_images.strip():
            flush_paragraph()
            continue

        if HEADING_PATTERN.match(line) is not None:
            flush_paragraph()
            heading = _clean_inline_markdown(stripped)
            if heading:
                blocks.append(heading)
            continue
        if LIST_PATTERN.match(line) is not None:
            flush_paragraph()
            item = _clean_inline_markdown(stripped)
            if item:
                blocks.append(item)
            continue

        paragraph_lines.append(stripped)

    flush_paragraph()
    return "\n\n".join(blocks).strip()


def visible_character_count(text: str) -> int:
    """画面に表示されない Markdown の構造記号と空白を除いて数える。"""
    visible_lines: list[str] = []
    for line in text.splitlines():
        without_heading = re.sub(
            r"^\s{0,3}#{1,6}(?:\s+|$)",
            "",
            line,
        )
        without_list_marker = LIST_PATTERN.sub("", without_heading)
        visible_lines.append(without_list_marker)
    return len(re.sub(r"\s+", "", "".join(visible_lines)))


def split_into_sections(text: str) -> list[Section]:
    """抽出済み本文を h2 ごとに分け、前文も独立した節にする。"""
    sections: list[Section] = []
    current_heading = "（前文）"
    current_lines: list[str] = []

    def flush_section() -> None:
        section_text = "\n".join(current_lines).strip()
        if not section_text:
            return
        sections.append(
            Section(
                heading=current_heading,
                index=len(sections),
                text=section_text,
            )
        )

    for line in text.splitlines():
        match = H2_PATTERN.match(line)
        if match is None:
            current_lines.append(line)
            continue

        flush_section()
        heading = re.sub(r"\s+#+\s*$", "", match.group(1)).strip()
        current_heading = heading or "（無題）"
        current_lines = [line]

    flush_section()
    return sections


def _section_comparison_key(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", "", normalized)


def filter_evaluation_sections(
    draft_sections: Sequence[Section],
    published_sections: Sequence[Section],
    min_chars: int = MIN_SECTION_CHARS,
    unchanged_ratio: float = UNCHANGED_SECTION_RATIO,
) -> tuple[list[Section], list[Section], SectionExclusionCounts]:
    """短い節と版間で実質同じ節を評価対象から除外する。"""
    if min_chars < 0:
        raise ValueError("節の最小文字数は 0 以上で指定してください")
    if not 0 <= unchanged_ratio <= 1:
        raise ValueError("同一節の類似度は 0 以上 1 以下で指定してください")

    short_draft = {
        section.index
        for section in draft_sections
        if section.chars < min_chars
    }
    short_published = {
        section.index
        for section in published_sections
        if section.chars < min_chars
    }
    eligible_draft = [
        section
        for section in draft_sections
        if section.index not in short_draft
    ]
    eligible_published = [
        section
        for section in published_sections
        if section.index not in short_published
    ]

    unchanged_draft: set[int] = set()
    unchanged_published: set[int] = set()
    published_keys = {
        section.index: _section_comparison_key(section.text)
        for section in eligible_published
    }
    for draft_section in eligible_draft:
        draft_key = _section_comparison_key(draft_section.text)
        for published_section in eligible_published:
            ratio = SequenceMatcher(
                None,
                draft_key,
                published_keys[published_section.index],
                autojunk=False,
            ).ratio()
            if ratio >= unchanged_ratio:
                unchanged_draft.add(draft_section.index)
                unchanged_published.add(published_section.index)

    kept_draft = [
        section
        for section in eligible_draft
        if section.index not in unchanged_draft
    ]
    kept_published = [
        section
        for section in eligible_published
        if section.index not in unchanged_published
    ]
    counts = SectionExclusionCounts(
        short_draft=len(short_draft),
        short_published=len(short_published),
        unchanged_draft=len(unchanged_draft),
        unchanged_published=len(unchanged_published),
    )
    return kept_draft, kept_published, counts


def read_git_blob(
    repository: Path,
    commit: str,
    source_path: str,
) -> str:
    """checkout せず、指定コミットの blob を UTF-8 で読み取る。"""
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(repository),
                "show",
                f"{commit}:{source_path}",
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as error:
        raise ValueError(
            f"git blob を取得できません: {commit}:{source_path}"
        ) from error

    if result.returncode != 0:
        raise ValueError(
            f"git blob を取得できません: {commit}:{source_path}"
        )
    try:
        return result.stdout.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(
            f"git blob が UTF-8 ではありません: {commit}:{source_path}"
        ) from error


def validate_article_sources(
    article_sources: Sequence[ArticleSource],
) -> None:
    """入力表が指定された5記事と完全に一致することを検証する。"""
    slugs = [source.slug for source in article_sources]
    if len(slugs) != len(set(slugs)):
        raise ValueError("記事表に同じ記事が複数あります")

    unknown = set(slugs).difference(ARTICLE_BY_SLUG)
    if unknown:
        raise ValueError(
            "表にない記事です: " + ", ".join(sorted(unknown))
        )
    missing = set(ARTICLE_BY_SLUG).difference(slugs)
    if missing:
        raise ValueError(
            "記事表に必要な記事がありません: "
            + ", ".join(sorted(missing))
        )

    for source in article_sources:
        if source != ARTICLE_BY_SLUG[source.slug]:
            raise ValueError(
                f"指定表と異なる版が含まれています: {source.slug}"
            )

    overlap = set(TRAIN_ARTICLES) & set(TEST_ARTICLES)
    if overlap:
        raise ValueError(
            "train と test に同じ記事があります: "
            + ", ".join(sorted(overlap))
        )

    # 表の split と TRAIN/TEST 定数がずれると、漏れの無い分割のつもりで
    # 実際には片側へ寄った状態を黙って生成してしまう。
    for source in article_sources:
        if source.slug in TRAIN_ARTICLES:
            expected_split = "train"
        elif source.slug in TEST_ARTICLES:
            expected_split = "test"
        else:
            raise ValueError(
                f"train/test のどちらにも属さない記事です: {source.slug}"
            )
        if source.split != expected_split:
            raise ValueError(
                f"記事 {source.slug} の split が TRAIN/TEST 定数と"
                "食い違っています"
            )


def _make_record(
    source: ArticleSource,
    variant: str,
    granularity: str,
    text: str,
    heading: str | None = None,
    section_index: int | None = None,
) -> dict[str, object]:
    commit = (
        source.draft_commit
        if variant == "draft"
        else source.published_commit
    )
    source_path = (
        source.draft_path
        if variant == "draft"
        else source.published_path
    )
    suffix = (
        "article"
        if granularity == "article"
        else f"section-{section_index}"
    )
    return {
        "id": f"{source.slug}:{variant}:{suffix}",
        "article": source.slug,
        "split": source.split,
        "variant": variant,
        "label": VARIANT_LABELS[variant],
        "granularity": granularity,
        "heading": heading,
        "section_index": section_index,
        "commit": commit,
        "source_path": source_path,
        "text": text,
        "chars": visible_character_count(text),
    }


def validate_records(
    records: Sequence[Mapping[str, object]],
) -> None:
    """レコードの出典、分割、版の組、IDを fail-closed で検証する。"""
    seen_ids: set[str] = set()
    article_variants: dict[str, Counter[str]] = {
        slug: Counter() for slug in ARTICLE_BY_SLUG
    }
    section_counts: dict[str, Counter[str]] = {
        slug: Counter() for slug in ARTICLE_BY_SLUG
    }
    article_texts: dict[str, dict[str, str]] = {
        slug: {} for slug in ARTICLE_BY_SLUG
    }
    split_articles: dict[str, set[str]] = {
        "train": set(),
        "test": set(),
    }

    for record in records:
        if set(record) != RECORD_KEYS:
            raise ValueError("レコードのキーが定義と一致しません")

        record_id = record["id"]
        if not isinstance(record_id, str) or not record_id:
            raise ValueError("空または文字列でない id があります")
        if record_id in seen_ids:
            raise ValueError(f"同一 id が重複しています: {record_id}")
        seen_ids.add(record_id)

        article = record["article"]
        if not isinstance(article, str) or article not in ARTICLE_BY_SLUG:
            raise ValueError(f"表にない記事です: {article}")
        source = ARTICLE_BY_SLUG[article]

        split = record["split"]
        if split not in split_articles:
            raise ValueError(f"split が不正です: {split}")
        if split != source.split:
            raise ValueError(f"記事 {article} の split が不正です")
        split_articles[split].add(article)

        variant = record["variant"]
        if variant not in VARIANT_LABELS:
            raise ValueError(f"variant が不正です: {variant}")
        if record["label"] != VARIANT_LABELS[variant]:
            raise ValueError(f"記事 {article} の label が不正です")

        expected_commit = (
            source.draft_commit
            if variant == "draft"
            else source.published_commit
        )
        expected_path = (
            source.draft_path
            if variant == "draft"
            else source.published_path
        )
        if record["commit"] != expected_commit:
            raise ValueError(f"記事 {article} の commit が不正です")
        if record["source_path"] != expected_path:
            raise ValueError(f"記事 {article} の source_path が不正です")

        text = record["text"]
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"記事 {article} の抽出本文が空です")
        chars = record["chars"]
        if (
            not isinstance(chars, int)
            or isinstance(chars, bool)
            or chars != visible_character_count(text)
        ):
            raise ValueError(f"記事 {article} の chars が不正です")

        granularity = record["granularity"]
        heading = record["heading"]
        section_index = record["section_index"]
        if granularity == "article":
            if heading is not None or section_index is not None:
                raise ValueError("記事レコードの節情報は null にしてください")
            article_variants[article][variant] += 1
            article_texts[article][variant] = text
        elif granularity == "section":
            if not isinstance(heading, str) or not heading:
                raise ValueError("節レコードの heading が空です")
            if (
                not isinstance(section_index, int)
                or isinstance(section_index, bool)
                or section_index < 0
            ):
                raise ValueError("節レコードの section_index が不正です")
            section_counts[article][variant] += 1
        else:
            raise ValueError(f"granularity が不正です: {granularity}")

    overlap = split_articles["train"] & split_articles["test"]
    if overlap:
        raise ValueError(
            "train と test に同じ記事があります: "
            + ", ".join(sorted(overlap))
        )

    for article, variants in article_variants.items():
        if variants != Counter({"draft": 1, "published": 1}):
            raise ValueError(
                f"記事 {article} に draft/published の両方が揃っていません"
            )

    # 片側のラベルだけ節が消えると、節の評価がラベルの偏りにすり替わる。
    # 抽出や除外規則が片側にだけ効いた事故なので、黙って通さない。
    for article, counts in section_counts.items():
        draft_sections = counts["draft"]
        published_sections = counts["published"]
        if (draft_sections == 0) != (published_sections == 0):
            raise ValueError(
                f"記事 {article} の節が片方の版にしかありません: "
                f"draft={draft_sections}, published={published_sections}"
            )

    # 両版の本文が同一なら、表の sha を取り違えて同じ版を 2 回読んでいる。
    # ラベルだけが違う同一テキストは評価として無意味なので止める。
    for article, texts in article_texts.items():
        if (
            len(texts) == 2
            and texts["draft"].strip() == texts["published"].strip()
        ):
            raise ValueError(
                f"記事 {article} の初稿と公開版の本文が同一です"
            )


def _timestamp() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _assemble_dataset(
    repository: Path,
    article_sources: Sequence[ArticleSource],
    generated_at: str | None,
) -> tuple[dict[str, object], SectionExclusionCounts]:
    validate_article_sources(article_sources)
    records: list[dict[str, object]] = []
    exclusion_counts = SectionExclusionCounts()

    for source in article_sources:
        extracted: dict[str, str] = {}
        for variant, commit, source_path in (
            ("draft", source.draft_commit, source.draft_path),
            (
                "published",
                source.published_commit,
                source.published_path,
            ),
        ):
            markdown = read_git_blob(repository, commit, source_path)
            text = extract_article_text(markdown)
            if not text:
                raise ValueError(
                    f"抽出後の本文が空です: {source.slug} ({variant})"
                )
            extracted[variant] = text
            records.append(
                _make_record(source, variant, "article", text)
            )

        draft_sections = split_into_sections(extracted["draft"])
        published_sections = split_into_sections(extracted["published"])
        (
            kept_draft,
            kept_published,
            article_exclusions,
        ) = filter_evaluation_sections(
            draft_sections,
            published_sections,
        )
        exclusion_counts += article_exclusions

        for variant, sections in (
            ("draft", kept_draft),
            ("published", kept_published),
        ):
            for section in sections:
                records.append(
                    _make_record(
                        source,
                        variant,
                        "section",
                        section.text,
                        heading=section.heading,
                        section_index=section.index,
                    )
                )

    validate_records(records)
    # 全記事で節が消えた場合は記事ごとの排他判定を素通りするので、
    # 実際に組み立てる経路でだけ止める（合成データの単体検証は縛らない）。
    if not any(
        record["granularity"] == "section" for record in records
    ):
        raise ValueError("節レコードが 1 件もありません")

    payload: dict[str, object] = {
        "generated_at": generated_at or _timestamp(),
        "articles": [source.as_dict() for source in article_sources],
        "records": records,
    }
    return payload, exclusion_counts


def build_dataset(
    repository: Path = DEFAULT_ARTICLE_REPOSITORY,
    article_sources: Sequence[ArticleSource] = ARTICLE_SOURCES,
    generated_at: str | None = None,
) -> dict[str, object]:
    """固定された git 上の2版から記事・節レコードを構築する。"""
    payload, _ = _assemble_dataset(
        repository,
        article_sources,
        generated_at,
    )
    return payload


def _sentences(text: str) -> list[str]:
    sentences: list[str] = []
    for line in text.splitlines():
        if HEADING_PATTERN.match(line) is not None:
            continue
        body = LIST_PATTERN.sub("", line).strip()
        if not body:
            continue
        sentences.extend(
            part.strip()
            for part in SENTENCE_PATTERN.findall(body)
            if part.strip()
        )
    return sentences


def calculate_surface_features(text: str) -> dict[str, float]:
    """出典を露呈しやすい単純な表層特徴をレコード単位で計算する。"""
    sentences = _sentences(text)
    sentence_count = len(sentences)
    nonempty_lines = [line for line in text.splitlines() if line.strip()]
    list_lines = [
        line
        for line in nonempty_lines
        if LIST_PATTERN.match(line) is not None
    ]
    heading_lines = [
        line
        for line in nonempty_lines
        if HEADING_PATTERN.match(line) is not None
    ]

    if sentence_count:
        mean_sentence_chars = fmean(
            visible_character_count(sentence) for sentence in sentences
        )
        period_ending_rate = (
            sum(sentence.endswith("。") for sentence in sentences)
            / sentence_count
        )
        commas_per_sentence = (
            sum(sentence.count("、") for sentence in sentences)
            / sentence_count
        )
        desu_masu_rate = (
            sum(
                re.search(r"(?:です|ます)[。！？!?]?$", sentence)
                is not None
                for sentence in sentences
            )
            / sentence_count
        )
    else:
        mean_sentence_chars = 0.0
        period_ending_rate = 0.0
        commas_per_sentence = 0.0
        desu_masu_rate = 0.0

    return {
        "chars": float(visible_character_count(text)),
        "mean_sentence_chars": mean_sentence_chars,
        "period_ending_rate": period_ending_rate,
        "commas_per_sentence": commas_per_sentence,
        "list_line_rate": (
            len(list_lines) / len(nonempty_lines) if nonempty_lines else 0.0
        ),
        "heading_count": float(len(heading_lines)),
        "desu_masu_rate": desu_masu_rate,
    }


def find_best_threshold(
    values_and_labels: Sequence[tuple[float, str]],
) -> ThresholdResult:
    """両向きの単一しきい値を総当たりして最高 accuracy を返す。"""
    if not values_and_labels:
        raise ValueError("しきい値探索に使うレコードがありません")
    if any(label not in {"ai", "human"} for _, label in values_and_labels):
        raise ValueError("しきい値探索の label が不正です")

    unique_values = sorted({value for value, _ in values_and_labels})
    thresholds = [unique_values[0] - 1.0]
    thresholds.extend(
        (left + right) / 2
        for left, right in zip(unique_values, unique_values[1:])
    )
    thresholds.append(unique_values[-1])

    best = ThresholdResult(
        accuracy=-1.0,
        threshold=thresholds[0],
        ai_when="<=",
    )
    total = len(values_and_labels)
    for threshold in thresholds:
        for ai_when in ("<=", ">"):
            correct = 0
            for value, label in values_and_labels:
                predicts_ai = (
                    value <= threshold
                    if ai_when == "<="
                    else value > threshold
                )
                predicted = "ai" if predicts_ai else "human"
                correct += predicted == label
            accuracy = correct / total
            if accuracy > best.accuracy:
                best = ThresholdResult(
                    accuracy=accuracy,
                    threshold=threshold,
                    ai_when=ai_when,
                )
    return best


def _format_number(value: float) -> str:
    return f"{value:.3f}"


def generate_report(
    records: Sequence[Mapping[str, object]],
    exclusion_counts: SectionExclusionCounts,
    generated_at: str,
) -> str:
    """件数と表層特徴によるラベル分離度を Markdown にまとめる。"""
    lines = [
        "# Jev 記事単位評価データ レポート",
        "",
        f"生成日時: {generated_at}",
        "",
        "## レコード件数",
        "",
        "| 粒度 | ラベル | train | test | 合計 |",
        "|---|---|---:|---:|---:|",
    ]
    for granularity in ("article", "section"):
        for label in ("ai", "human"):
            counts = Counter(
                str(record["split"])
                for record in records
                if record["granularity"] == granularity
                and record["label"] == label
            )
            lines.append(
                f"| {granularity} | {label} | {counts['train']} | "
                f"{counts['test']} | {sum(counts.values())} |"
            )

    short_total = (
        exclusion_counts.short_draft
        + exclusion_counts.short_published
    )
    unchanged_total = (
        exclusion_counts.unchanged_draft
        + exclusion_counts.unchanged_published
    )
    lines.extend(
        [
            "",
            "## 除外した節",
            "",
            "短い節を先に除外し、残った節だけを版間比較した件数です。",
            "",
            "| 理由 | ai (draft) | human (published) | 合計 |",
            "|---|---:|---:|---:|",
            (
                f"| 可視文字数が {MIN_SECTION_CHARS} 文字未満 | "
                f"{exclusion_counts.short_draft} | "
                f"{exclusion_counts.short_published} | {short_total} |"
            ),
            (
                f"| 版間の正規化類似度が {UNCHANGED_SECTION_RATIO:.2f} "
                f"以上 | {exclusion_counts.unchanged_draft} | "
                f"{exclusion_counts.unchanged_published} | "
                f"{unchanged_total} |"
            ),
            "",
            "## 表層特徴の分離度",
            "",
            (
                "accuracy は、特徴値に対して ai 側の向きも含めて単一しきい値を"
                "総当たりした最高値です。"
            ),
        ]
    )

    warnings: list[str] = []
    for granularity in ("article", "section"):
        selected = [
            record
            for record in records
            if record["granularity"] == granularity
            and record["label"] in {"ai", "human"}
        ]
        feature_rows = [
            (
                calculate_surface_features(str(record["text"])),
                str(record["label"]),
            )
            for record in selected
        ]
        # accuracy は多数派ベースラインと並べないと読み違える。
        # 例えば ai 32 / human 21 なら、全部 ai と答えるだけで 0.604 になる。
        ai_count = sum(
            1 for _, row_label in feature_rows if row_label == "ai"
        )
        human_count = len(feature_rows) - ai_count
        baseline = (
            max(ai_count, human_count) / len(feature_rows)
            if feature_rows
            else 0.0
        )
        lines.extend(
            [
                "",
                f"### {granularity}",
                "",
                (
                    f"件数 ai {ai_count} / human {human_count}、"
                    f"多数派ベースライン accuracy "
                    f"{_format_number(baseline)}"
                    "（これを超えない特徴は、その特徴だけでは何も"
                    "当てていない）。1 件の取り違えが accuracy "
                    f"{_format_number(1 / len(feature_rows))} "
                    "に相当する。"
                    if feature_rows
                    else "レコードがありません。"
                ),
                "",
                (
                    "| 特徴 | ai 平均 | human 平均 | 最良 accuracy | "
                    "ai と判定する規則 |"
                ),
                "|---|---:|---:|---:|---|",
            ]
        )
        for key, label in FEATURE_LABELS.items():
            ai_values = [
                features[key]
                for features, row_label in feature_rows
                if row_label == "ai"
            ]
            human_values = [
                features[key]
                for features, row_label in feature_rows
                if row_label == "human"
            ]
            if not ai_values or not human_values:
                lines.append(f"| {label} | — | — | — | — |")
                continue

            threshold = find_best_threshold(
                [
                    (features[key], row_label)
                    for features, row_label in feature_rows
                ]
            )
            direction = "以下" if threshold.ai_when == "<=" else "より大きい"
            lines.append(
                f"| {label} | {_format_number(fmean(ai_values))} | "
                f"{_format_number(fmean(human_values))} | "
                f"{_format_number(threshold.accuracy)} | "
                f"{_format_number(threshold.threshold)} {direction} |"
            )
            if threshold.accuracy >= SURFACE_WARNING_ACCURACY:
                warnings.append(
                    f"> 警告: {granularity} 粒度の「{label}」は単一しきい値で "
                    f"accuracy={threshold.accuracy:.3f} です。その特徴だけで"
                    "当てられるので、この評価セットは文体判定の当否を測れない。"
                )

    lines.extend(["", "## 警告", ""])
    if warnings:
        lines.extend(warnings)
    else:
        lines.append("警告対象の特徴はありません。")
    return "\n".join(lines) + "\n"


def write_dataset(
    payload: Mapping[str, object],
    output_path: Path,
) -> None:
    """日本語をエスケープせず、評価データを JSON で保存する。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_report(report: str, report_path: Path) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")


def main() -> int:
    payload, exclusion_counts = _assemble_dataset(
        DEFAULT_ARTICLE_REPOSITORY,
        ARTICLE_SOURCES,
        generated_at=None,
    )
    records = payload["records"]
    if not isinstance(records, list):
        raise ValueError("records がリストではありません")
    generated_at = payload["generated_at"]
    if not isinstance(generated_at, str):
        raise ValueError("generated_at が文字列ではありません")

    write_dataset(payload, DEFAULT_OUTPUT_PATH)
    write_report(
        generate_report(records, exclusion_counts, generated_at),
        DEFAULT_REPORT_PATH,
    )
    print(
        f"{DEFAULT_OUTPUT_PATH} と {DEFAULT_REPORT_PATH} を生成しました "
        f"(records={len(records)})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
