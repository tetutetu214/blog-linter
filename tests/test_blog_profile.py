from unittest.mock import patch

from blog_linter.ai_writing_checker import (
    BLOG_TEXTLINT_CONFIG,
    TEXTLINT_CONFIG,
)
from blog_linter.linter import lint_markdown
from blog_linter.profiles import get_profile_checks


def test_blogプロファイルは機密情報とAI文体だけをチェックする():
    assert get_profile_checks("blog") == ("secrets", "ai_writing")


def test_blogプロファイルはblog用textlint設定を渡す(tmp_path):
    article = tmp_path / "article.md"

    with patch("blog_linter.linter.check_ai_writing", return_value=[]) as checker:
        lint_markdown("本文", profile="blog", file_path=article)

    checker.assert_called_once_with(
        article,
        config_path=BLOG_TEXTLINT_CONFIG,
    )


def test_qiitaプロファイルは従来のtextlint設定を渡す(tmp_path):
    article = tmp_path / "article.md"

    with patch("blog_linter.linter.check_ai_writing", return_value=[]) as checker:
        lint_markdown("本文", profile="qiita", file_path=article)

    checker.assert_called_once_with(
        article,
        config_path=TEXTLINT_CONFIG,
    )
