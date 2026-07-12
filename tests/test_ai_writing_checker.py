from pathlib import Path
import subprocess
from unittest.mock import patch

from blog_linter.ai_writing_checker import check_ai_writing
from blog_linter.linter import lint_markdown


def test_qiitaプロファイルはAIらしい文章を行番号付きで指摘する(tmp_path):
    article = tmp_path / "article.md"
    text = "革命的な方法を紹介します:\n- ✅ **項目**: 内容\n"
    article.write_text(text, encoding="utf-8")

    issues = lint_markdown(text, profile="qiita", file_path=article)
    ai_issues = [issue for issue in issues if issue.category == "ai_writing"]

    assert ai_issues
    assert {issue.line_number for issue in ai_issues} == {1, 2}


def test_vaultプロファイルはAI文体チェックを実行しない(tmp_path):
    note = tmp_path / "docs" / "note.md"
    note.parent.mkdir()
    text = "革命的な方法を紹介します:\n- ✅ **項目**: 内容\n"

    with patch(
        "blog_linter.linter.check_ai_writing",
        side_effect=AssertionError("vault では呼び出さない"),
    ):
        issues = lint_markdown(
            text,
            profile="vault",
            file_path=note,
            vault_root=tmp_path,
            tag_vocabulary=set(),
        )

    assert all(issue.category != "ai_writing" for issue in issues)


def test_textlint未導入時は理由を報告する(tmp_path):
    article = tmp_path / "article.md"
    article.write_text("本文", encoding="utf-8")

    # 実行環境差を再現するため、未導入経路だけコマンド探索をモックする。
    with patch("blog_linter.ai_writing_checker.shutil.which", return_value=None):
        issues = check_ai_writing(article)

    assert len(issues) == 1
    assert "textlint 未導入" in issues[0].message


def test_textlint未導入でも既存チェックは実行される(tmp_path):
    article = tmp_path / "article.md"
    text = "サーバを使います。"
    article.write_text(text, encoding="utf-8")

    with patch("blog_linter.ai_writing_checker.shutil.which", return_value=None):
        issues = lint_markdown(text, profile="qiita", file_path=article)

    assert {issue.category for issue in issues} == {"notation", "ai_writing"}


def test_タイムアウト時は理由を報告する(tmp_path):
    article = tmp_path / "article.md"
    article.write_text("本文", encoding="utf-8")

    with patch(
        "blog_linter.ai_writing_checker.subprocess.run",
        side_effect=subprocess.TimeoutExpired("textlint", 60),
    ):
        issues = check_ai_writing(article)

    assert "60 秒以内に完了しなかった" in issues[0].message


def test_不正なJSON結果は理由を報告する(tmp_path):
    article = tmp_path / "article.md"
    article.write_text("本文", encoding="utf-8")

    completed = subprocess.CompletedProcess([], 1, "not-json", "")
    with patch("blog_linter.ai_writing_checker.subprocess.run", return_value=completed):
        issues = check_ai_writing(Path(article))

    assert "結果を解析できなかった" in issues[0].message
