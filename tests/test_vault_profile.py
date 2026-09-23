from unittest.mock import patch

import pytest

from blog_linter.__main__ import main
from blog_linter.linter import lint_markdown
from blog_linter.secret_checker import LintIssue


def _run_check(arguments):
    with patch("sys.argv", ["prog", "check", *arguments]):
        with pytest.raises(SystemExit) as error:
            main()
    return error.value.code


def test_LintIssueは従来のimport先から利用できる():
    issue = LintIssue(1, 1, "x", "secret", "rule", "message")
    assert issue.file == ""


def test_qiitaプロファイルは表記ブレだけを返す():
    issues = lint_markdown(
        "frontmatter はありません。サーバを使います。", profile="qiita"
    )
    assert {issue.category for issue in issues} == {"notation"}


def test_vaultプロファイルは機密と構造をチェックし表記ブレは対象外(tmp_path):
    note = tmp_path / "docs" / "note.md"
    note.parent.mkdir()
    text = "サーバと api_key=abcdefghijklmnop を記載"
    issues = lint_markdown(
        text,
        profile="vault",
        file_path=note,
        vault_root=tmp_path,
        tag_vocabulary={"python"},
    )
    assert {issue.category for issue in issues} == {"secret", "frontmatter"}


def test_語彙ファイルがないときexit1になる(tmp_path, capsys):
    note = tmp_path / "docs" / "note.md"
    note.parent.mkdir()
    note.write_text("本文", encoding="utf-8")
    code = _run_check([
        str(note), "--profile", "vault", "--vault-root", str(tmp_path)
    ])
    assert code == 1
    assert "タグ語彙ファイルが見つかりません" in capsys.readouterr().out


def test_ディレクトリ走査は対象外領域を除外する(tmp_path, capsys):
    vocabulary = tmp_path / ".claude" / "tag-vocabulary.txt"
    vocabulary.parent.mkdir()
    vocabulary.write_text("python\n# コメント\n\n", encoding="utf-8")
    valid_text = "---\nauthor: human\ntags: [python]\n---\n本文"
    invalid_text = "---\nauthor: human\ntags: [語彙外]\n---\n本文"
    for relative_path in (
        "docs/note.md", "raw/ignored.md", ".obsidian/ignored.md",
        ".claude/ignored.md", "README.md", "wiki/raw/ignored.md",
    ):
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(valid_text if relative_path == "docs/note.md" else invalid_text, encoding="utf-8")

    code = _run_check([
        str(tmp_path), "--profile", "vault", "--vault-root", str(tmp_path)
    ])
    assert code == 0
    assert capsys.readouterr().out == "問題は見つかりませんでした。\n"


def test_ディレクトリ走査で各種違反を検出する(tmp_path, capsys):
    vocabulary = tmp_path / ".claude" / "tag-vocabulary.txt"
    vocabulary.parent.mkdir()
    vocabulary.write_text("python\n", encoding="utf-8")
    fixtures = {
        "docs/tag.md": "---\nauthor: human\ntags: [outside]\n---\n本文",
        "projects/author.md": "---\ntags: []\n---\n本文",
        "wiki/concepts/concept.md": "---\nauthor: human\n---\n[[one]]",
        "worklog/bad.md": "---\nauthor: human\n---\n本文",
        "reports/bad.md": "---\nauthor: human\nresearched_at: today\n---\n本文",
        "docs/no-frontmatter.md": "本文",
    }
    for relative_path, text in fixtures.items():
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    code = _run_check([
        str(tmp_path), "--profile", "vault", "--vault-root", str(tmp_path)
    ])
    output = capsys.readouterr().out
    assert code == 1
    assert all(expected in output for expected in (
        "タグ語彙", "author 必須", "frontmatter 必須", "sources 必須",
        "wikilink 必須", "worklog 命名規則", "reports 命名規則", "調査日と期限",
    ))


def test_適用開始日より前のworklogはwikilinkが無くても指摘しない(tmp_path, capsys):
    vocabulary = tmp_path / ".claude" / "tag-vocabulary.txt"
    vocabulary.parent.mkdir()
    vocabulary.write_text("python\n", encoding="utf-8")
    old_worklog = tmp_path / "worklog" / "2026-06-30.md"
    old_worklog.parent.mkdir()
    old_worklog.write_text("---\nauthor: claude\n---\n本文だけ", encoding="utf-8")

    code = _run_check([
        str(tmp_path), "--profile", "vault", "--vault-root", str(tmp_path)
    ])
    assert code == 0
    assert "wikilink 必須" not in capsys.readouterr().out


def test_適用開始日以降のworklogはwikilinkが無いと指摘する(tmp_path, capsys):
    vocabulary = tmp_path / ".claude" / "tag-vocabulary.txt"
    vocabulary.parent.mkdir()
    vocabulary.write_text("python\n", encoding="utf-8")
    new_worklog = tmp_path / "worklog" / "2026-07-01.md"
    new_worklog.parent.mkdir()
    new_worklog.write_text("---\nauthor: claude\n---\n本文だけ", encoding="utf-8")

    code = _run_check([
        str(tmp_path), "--profile", "vault", "--vault-root", str(tmp_path)
    ])
    assert code == 1
    assert "wikilink 必須" in capsys.readouterr().out
