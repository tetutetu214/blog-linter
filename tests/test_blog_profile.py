from unittest.mock import patch

from blog_linter.ai_writing_checker import (
    BLOG_TEXTLINT_CONFIG,
    TEXTLINT_CONFIG,
)
from blog_linter.linter import lint_markdown
from blog_linter.profiles import get_profile_checks


def test_blogプロファイルは機密情報と表記ブレとAI文体をチェックする():
    assert get_profile_checks("blog") == ("secrets", "notation", "ai_writing")


def test_blogプロファイルはblog用textlint設定を渡す(tmp_path):
    article = tmp_path / "article.md"

    with patch("blog_linter.linter.check_ai_writing", return_value=[]) as checker:
        lint_markdown("本文", profile="blog", file_path=article)

    checker.assert_called_once_with(
        article,
        config_path=BLOG_TEXTLINT_CONFIG,
    )


def test_blogプロファイルは80字を超える一文を指摘する(tmp_path):
    article = tmp_path / "article.md"
    text = (
        "読者が迷わず内容を理解できるように、前提と手順と結果を一つずつ"
        "順序立てて説明し、必要な補足情報も省略せず具体的に記載することで、"
        "技術記事全体の読みやすさと正確さを高めます。"
    )
    assert 80 < len(text) < 100
    article.write_text(text, encoding="utf-8")

    issues = lint_markdown(text, profile="blog", file_path=article)

    assert any(issue.rule_name == "sentence-length" for issue in issues)


def test_拡張子がmdxでも80字を超える一文を指摘する(tmp_path):
    """textlint は .md 以外を無言でスキップするため、ブログ記事の .mdx で偽クリーンになっていた"""
    article = tmp_path / "article.mdx"
    text = (
        "読者が迷わず内容を理解できるように、前提と手順と結果を一つずつ"
        "順序立てて説明し、必要な補足情報も省略せず具体的に記載することで、"
        "技術記事全体の読みやすさと正確さを高めます。"
    )
    article.write_text(text, encoding="utf-8")

    issues = lint_markdown(text, profile="blog", file_path=article)

    assert any(issue.rule_name == "sentence-length" for issue in issues)


def test_同じ本文なら拡張子がmdでもmdxでも同じ件数を指摘する(tmp_path):
    text = (
        "読者が迷わず内容を理解できるように、前提と手順と結果を一つずつ"
        "順序立てて説明し、必要な補足情報も省略せず具体的に記載することで、"
        "技術記事全体の読みやすさと正確さを高めます。"
    )
    counts = []
    for name in ("article.md", "article.mdx"):
        article = tmp_path / name
        article.write_text(text, encoding="utf-8")
        issues = lint_markdown(text, profile="blog", file_path=article)
        counts.append(len([i for i in issues if i.category == "ai_writing"]))

    assert counts[0] == counts[1]
    assert counts[0] > 0


def test_qiitaプロファイルは従来のtextlint設定を渡す(tmp_path):
    article = tmp_path / "article.md"

    with patch("blog_linter.linter.check_ai_writing", return_value=[]) as checker:
        lint_markdown("本文", profile="qiita", file_path=article)

    checker.assert_called_once_with(
        article,
        config_path=TEXTLINT_CONFIG,
    )
