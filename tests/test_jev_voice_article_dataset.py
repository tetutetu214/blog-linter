from __future__ import annotations

from collections import Counter

import pytest

from experiments.jev_voice.build_article_dataset import (
    ARTICLE_SOURCES,
    DEFAULT_ARTICLE_REPOSITORY,
    Section,
    SectionExclusionCounts,
    build_dataset,
    extract_article_text,
    filter_evaluation_sections,
    generate_report,
    read_git_blob,
    split_into_sections,
    validate_article_sources,
    validate_records,
    visible_character_count,
)


def test_frontmatterを本文に含めない():
    markdown = """\
---
title: 除外するタイトル
description: 除外する説明
---

# 残す見出し

残す本文です。
"""

    text = extract_article_text(markdown)

    assert text == "# 残す見出し\n\n残す本文です。"


def test_コードブロックの中身を本文に含めない():
    markdown = """\
前の本文です。

```python
print("除外するコードです")
```

~~~text
除外する別形式のコードです。
~~~

後ろの本文です。
"""

    text = extract_article_text(markdown)

    assert text == "前の本文です。\n\n後ろの本文です。"


def test_MDXコンポーネントとimport行を本文に含めない():
    markdown = """\
import Sample from "./Sample.astro"

前の本文です。

<SampleCard
  title="除外する属性です"
>
除外するコンポーネント本文です。
</SampleCard>

<Image src="sample.png" alt="除外する画像です" />

後ろの本文です。
"""

    text = extract_article_text(markdown)

    assert text == "前の本文です。\n\n後ろの本文です。"


def test_表と出典行を本文に含めない():
    markdown = """\
前の本文です。

| 項目 | 値 |
| --- | --- |
| 除外する表 | 除外する値 |

（出典: https://example.com/source）
出典：https://example.com/other

後ろの本文です。
"""

    text = extract_article_text(markdown)

    assert text == "前の本文です。\n\n後ろの本文です。"


def test_インライン記法は表示テキストだけを残す():
    markdown = (
        "**強調**と[表示](https://example.com/)と"
        "`inline_code`を残します。"
    )

    text = extract_article_text(markdown)

    assert text == "強調と表示とinline_codeを残します。"


def test_h2ごとに節へ分割し最初のh2より前を前文として扱う():
    text = """\
# 記事タイトル

導入です。

## 一つ目

一つ目の本文です。

### 小見出し

続きです。

## 二つ目

二つ目の本文です。
"""

    sections = split_into_sections(text)

    assert [(section.heading, section.index) for section in sections] == [
        ("（前文）", 0),
        ("一つ目", 1),
        ("二つ目", 2),
    ]
    assert sections[1].text.startswith("## 一つ目")
    assert "### 小見出し" in sections[1].text


def test_可視文字数が200文字未満の節を除外する():
    draft = [Section("短い節", 0, "あ" * 199)]
    published = [Section("残る節", 0, "い" * 200)]

    kept_draft, kept_published, counts = filter_evaluation_sections(
        draft,
        published,
    )

    assert kept_draft == []
    assert kept_published == published
    assert counts.short_draft == 1
    assert counts.short_published == 0


def test_初稿と公開版で実質同じ節を両方除外する():
    draft = [
        Section("対象", 0, "ＡＢＣ　" + "同じ本文です。" * 40),
        Section("初稿だけ", 1, "初稿だけの本文です。" * 30),
    ]
    published = [
        Section("対象", 0, "ABC" + "同じ本文です。" * 40),
        Section("公開版だけ", 1, "公開版だけの本文です。" * 30),
    ]

    kept_draft, kept_published, counts = filter_evaluation_sections(
        draft,
        published,
    )

    assert [section.heading for section in kept_draft] == ["初稿だけ"]
    assert [section.heading for section in kept_published] == ["公開版だけ"]
    assert counts.unchanged_draft == 1
    assert counts.unchanged_published == 1


def test_blobが取れないときはValueErrorを出す(tmp_path):
    with pytest.raises(ValueError, match="git blob を取得できません"):
        read_git_blob(tmp_path, "存在しないsha", "存在しない.md")


def _valid_article_records() -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for source in ARTICLE_SOURCES:
        for variant, label, commit, source_path in (
            (
                "draft",
                "ai",
                source.draft_commit,
                source.draft_path,
            ),
            (
                "published",
                "human",
                source.published_commit,
                source.published_path,
            ),
        ):
            text = f"{source.slug} の {variant} 本文です。"
            records.append(
                {
                    "id": f"{source.slug}:{variant}:article",
                    "article": source.slug,
                    "split": source.split,
                    "variant": variant,
                    "label": label,
                    "granularity": "article",
                    "heading": None,
                    "section_index": None,
                    "commit": commit,
                    "source_path": source_path,
                    "text": text,
                    "chars": visible_character_count(text),
                }
            )
    return records


def _section_record(source, variant, label, index):
    text = f"{source.slug} の {variant} 第{index}節です。"
    return {
        "id": f"{source.slug}:{variant}:section-{index}",
        "article": source.slug,
        "split": source.split,
        "variant": variant,
        "label": label,
        "granularity": "section",
        "heading": f"見出し{index}",
        "section_index": index,
        "commit": (
            source.draft_commit
            if variant == "draft"
            else source.published_commit
        ),
        "source_path": (
            source.draft_path
            if variant == "draft"
            else source.published_path
        ),
        "text": text,
        "chars": visible_character_count(text),
    }


def test_節が片方の版にしかないときはValueErrorを出す():
    records = _valid_article_records()
    source = ARTICLE_SOURCES[0]
    records.append(_section_record(source, "published", "human", 0))

    with pytest.raises(ValueError, match="片方の版にしかありません"):
        validate_records(records)


def test_節が両方の版にあるときは通る():
    records = _valid_article_records()
    source = ARTICLE_SOURCES[0]
    records.append(_section_record(source, "draft", "ai", 0))
    records.append(_section_record(source, "published", "human", 0))

    validate_records(records)


def test_初稿と公開版の本文が同一のときはValueErrorを出す():
    records = _valid_article_records()
    slug = ARTICLE_SOURCES[0].slug
    same = "まったく同じ本文です。"
    for record in records:
        if record["article"] == slug and record["granularity"] == "article":
            record["text"] = same
            record["chars"] = visible_character_count(same)

    with pytest.raises(ValueError, match="本文が同一です"):
        validate_records(records)


def test_記事表のsplitがTRAINTEST定数と食い違うときはValueErrorを出す(
    monkeypatch,
):
    # 表そのものを書き換えた状況を作る（定数と表の両方がずれていても
    # 気づけることを確かめる）
    from dataclasses import replace

    import experiments.jev_voice.build_article_dataset as module

    sources = list(ARTICLE_SOURCES)
    index = next(i for i, s in enumerate(sources) if s.split == "train")
    broken = replace(sources[index], split="test")
    sources[index] = broken
    monkeypatch.setitem(module.ARTICLE_BY_SLUG, broken.slug, broken)

    with pytest.raises(ValueError, match="食い違っています"):
        validate_article_sources(sources)


def test_表にない記事があるときはValueErrorを出す():
    records = _valid_article_records()
    records[0]["article"] = "表にない記事"

    with pytest.raises(ValueError, match="表にない記事"):
        validate_records(records)


def test_記事の両方の版が揃わないときはValueErrorを出す():
    records = _valid_article_records()
    records.pop(0)

    with pytest.raises(ValueError, match="両方が揃っていません"):
        validate_records(records)


def test_同一idが重複するときはValueErrorを出す():
    records = _valid_article_records()
    records[1]["id"] = records[0]["id"]

    with pytest.raises(ValueError, match="同一 id が重複"):
        validate_records(records)


def test_trainとtestに同じ記事があるときはValueErrorを出す():
    records = _valid_article_records()
    records[0]["split"] = "test"

    with pytest.raises(ValueError, match="split が不正"):
        validate_records(records)


def test_単一特徴でラベルを分けられるときは警告を出す():
    records = _valid_article_records()
    for record in records:
        if record["label"] == "ai":
            record["text"] = "短いです。"
        else:
            record["text"] = "長い本文です。" * 100
        record["chars"] = visible_character_count(str(record["text"]))

    report = generate_report(
        records,
        SectionExclusionCounts(),
        "2026-09-21T00:00:00Z",
    )

    assert "その特徴だけで当てられるので" in report
    assert "この評価セットは文体判定の当否を測れない" in report


def _real_repository_is_readable() -> bool:
    if not DEFAULT_ARTICLE_REPOSITORY.is_dir():
        return False
    for source in ARTICLE_SOURCES:
        for commit, source_path in (
            (source.draft_commit, source.draft_path),
            (source.published_commit, source.published_path),
        ):
            try:
                read_git_blob(
                    DEFAULT_ARTICLE_REPOSITORY,
                    commit,
                    source_path,
                )
            except ValueError:
                return False
    return True


@pytest.mark.skipif(
    not _real_repository_is_readable(),
    reason="記事リポジトリがないか、サンドボックスから git blob を読めません",
)
def test_実リポジトリから全記事の両方の版を構築する():
    payload = build_dataset(
        DEFAULT_ARTICLE_REPOSITORY,
        generated_at="2026-09-21T00:00:00Z",
    )
    records = payload["records"]
    assert isinstance(records, list)
    article_records = [
        record
        for record in records
        if record["granularity"] == "article"
    ]

    assert len(article_records) == 10
    assert Counter(record["label"] for record in article_records) == {
        "ai": 5,
        "human": 5,
    }
    assert {record["article"] for record in article_records} == {
        source.slug for source in ARTICLE_SOURCES
    }
