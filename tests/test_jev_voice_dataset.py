from collections import Counter

from experiments.jev_voice.build_dataset import (
    clean_correction_text,
    extract_normal_sentences,
    load_normal_candidates,
    parse_corrections,
    select_normal_records,
)


def test_NGとOKが揃わない見出しは採用しない(tmp_path):
    corrections = tmp_path / "corrections.md"
    corrections.write_text(
        """\
## 2026-09-01 NGだけの指摘
- NG: 「直す前の文です」
- 記事: ~/projects/blog-site/content/posts/aws-lambda-microvms/index.md

## 2026-09-02 両方がある指摘 →STYLE昇格済
- NG: 「直す前の文です」
- OK: 「直した後の文です」
- 記事: ~/projects/blog-site/content/posts/aws-lambda-microvms/index.md

## 2026-09-03 OKだけの指摘
- OK: 「直した後の文です」
- 記事: ~/projects/blog-site/content/posts/aws-lambda-microvms/index.md
""",
        encoding="utf-8",
    )

    pairs = parse_corrections(corrections)

    assert len(pairs) == 1
    assert pairs[0].note == "両方がある指摘"


def test_記事パスはルートや拡張子によらずスラッグで分割する(tmp_path):
    corrections = tmp_path / "corrections.md"
    corrections.write_text(
        """\
## 2026-09-01 train の指摘
- NG: 「直す前の文です」
- OK: 「直した後の文です」
- 記事: ~/projects/blog-site/content/posts/aws-lambda-microvms/index.md

## 2026-09-02 test の指摘
- NG: 「直す前の文です」
- OK: 「直した後の文です」
- 記事: ~/projects/blog-site-dev/content/posts/coop-camera-video/index.mdx
""",
        encoding="utf-8",
    )

    pairs = parse_corrections(corrections)

    assert [(pair.article, pair.split) for pair in pairs] == [
        ("aws-lambda-microvms", "train"),
        ("coop-camera-video", "test"),
    ]


def test_引用末尾の丸括弧注釈は本文から除外する():
    value = "「QEMU は汎用品で重かったためです」（比較相手がない）"

    assert clean_correction_text(value) == "QEMU は汎用品で重かったためです"


def test_複数の引用は一つの指摘本文として残す():
    value = "「使うときの注意点」「採用する条件」（一般論の列挙）"

    assert clean_correction_text(value) == "「使うときの注意点」「採用する条件」"


def test_normal抽出は地の文以外を除外する():
    markdown = """\
---
title: frontmatter にある十分に長い文章です。
---

# 本文の見出しです。

// MDX のコメントにある十分に長い文章です。

これは抽出されるのに十分な長さを持つ最初の本文です。

短い。

```python
print("コードブロックにある十分に長い文章です。")
```

<SampleCard
  description="コンポーネントにある十分に長い文章です。"
/>

<figure>
  <figcaption>図を説明する十分に長い文章です。</figcaption>
</figure>

<style>{`
  .sample { color: red; }
`}</style>

![構成図の説明](./diagram.png)

[参考リンクだけの行](https://example.com/)

| 項目 | 十分に長い表の説明です。 |
| --- | --- |

- 箇条書きにある十分に長い文章です。

これは [公式資料](https://example.com/) を参照して書いた、十分に長い二つ目の本文です。
"""

    sentences = extract_normal_sentences(markdown)

    assert sentences == [
        "これは抽出されるのに十分な長さを持つ最初の本文です。",
        "これは 公式資料 を参照して書いた、十分に長い二つ目の本文です。",
    ]


def test_normal抽出は句点で分割して短い断片を捨てる():
    markdown = (
        "これは一つ目として抽出するのに十分な長さがある本文です。"
        "短い。"
        "これは二つ目として抽出するのに十分な長さがある本文です。"
    )

    sentences = extract_normal_sentences(markdown)

    assert sentences == [
        "これは一つ目として抽出するのに十分な長さがある本文です。",
        "これは二つ目として抽出するのに十分な長さがある本文です。",
    ]


def test_normal選択は指摘文と同じ文を除外する():
    candidates = {
        "aws-lambda-microvms": [
            "指摘文と同じ文章です。",
            "通常文として採用する一つ目の文章です。",
            "通常文として採用する二つ目の文章です。",
        ]
    }

    records = select_normal_records(
        candidates,
        target_count=2,
        forbidden_texts={"指摘文と同じ文章です"},
    )

    assert [record["text"] for record in records] == [
        "通常文として採用する一つ目の文章です。",
        "通常文として採用する二つ目の文章です。",
    ]


def test_normal選択は記事ごとに均等に散らす():
    articles = (
        "aws-lambda-microvms",
        "aws-lambda-durable-functions",
        "coop-camera-video",
    )
    candidates = {
        article: [f"{article} の通常文 {number} です。" for number in range(3)]
        for article in articles
    }

    records = select_normal_records(
        candidates,
        target_count=6,
        forbidden_texts=set(),
    )

    assert Counter(record["article"] for record in records) == {
        article: 2 for article in articles
    }


def test_リネームされた記事は別名のディレクトリから本文を探す(tmp_path):
    article_root = tmp_path / "posts"
    renamed_directory = article_root / "blog-with-astro"
    renamed_directory.mkdir(parents=True)
    (renamed_directory / "index.md").write_text(
        "リネーム後のディレクトリにある地の文です。これも本文の地の文になります。\n",
        encoding="utf-8",
    )

    candidates, missing = load_normal_candidates(article_root, ["hello-world"])

    assert missing == []
    assert candidates["hello-world"]


def test_対応表に無い記事が見つからなければ欠落として報告する(tmp_path):
    article_root = tmp_path / "posts"
    article_root.mkdir(parents=True)

    candidates, missing = load_normal_candidates(article_root, ["存在しない記事"])

    assert missing == ["存在しない記事"]
    assert "存在しない記事" not in candidates
