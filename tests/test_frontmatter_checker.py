from pathlib import Path

from blog_linter.frontmatter_checker import check_frontmatter


def _check(text: str, relative_path: str, vocabulary=None):
    vault_root = Path("/tmp/test-vault")
    return check_frontmatter(
        text,
        vault_root / relative_path,
        vault_root,
        vocabulary or {"python", "obsidian"},
    )


def test_frontmatterがないとき指摘する():
    issues = _check("本文", "docs/note.md")
    assert [issue.rule_name for issue in issues] == ["frontmatter 必須"]


def test_frontmatterの閉じ区切りがないとき指摘する():
    issues = _check("---\nauthor: human\n本文", "docs/note.md")
    assert [issue.rule_name for issue in issues] == ["frontmatter 未終端"]


def test_authorがないとき指摘する():
    issues = _check("---\ntags: []\n---\n本文", "docs/note.md")
    assert any(issue.rule_name == "author 必須" for issue in issues)


def test_authorが許可値なら指摘しない():
    issues = _check("---\nauthor: claude\n---\n本文", "docs/note.md")
    assert not any(issue.rule_name == "author 必須" for issue in issues)


def test_インラインリストの語彙外タグを指摘する():
    issues = _check(
        "---\nauthor: human\ntags: [python, 未登録]\n---\n本文",
        "docs/note.md",
    )
    assert [issue.matched_text for issue in issues if issue.rule_name == "タグ語彙"] == ["未登録"]


def test_空のタグリストは指摘しない():
    issues = _check("---\nauthor: human\ntags: []\n---\n本文", "docs/note.md")
    assert not any(issue.rule_name == "タグ語彙" for issue in issues)


def test_ブロックリストとコメント行を解釈する():
    text = "---\n# コメント\nauthor: human\ntags:\n  - python\n  - unknown\n---\n本文"
    issues = _check(text, "docs/note.md")
    assert [issue.matched_text for issue in issues if issue.rule_name == "タグ語彙"] == ["unknown"]


def test_ブロックリスト形式のsourcesを認識する():
    text = "---\nauthor: claude\nsources:\n  - raw/a.md\n  - raw/b.md\n---\n[[a]] [[b]]"
    issues = _check(text, "wiki/concepts/note.md")
    assert not any(issue.rule_name == "sources 必須" for issue in issues)


def test_wiki_conceptsでsourcesがないとき指摘する():
    text = "---\nauthor: human\n---\n[[a]] [[b]]"
    issues = _check(text, "wiki/concepts/deep/note.md")
    assert any(issue.rule_name == "sources 必須" for issue in issues)


def test_wiki_conceptsでwikilinkが不足するとき指摘する():
    text = "---\nauthor: human\nsources: URL\n---\n[[a]]"
    issues = _check(text, "wiki/concepts/note.md")
    assert any(issue.message.endswith("2つ以上必要です") for issue in issues)


def test_worklogの名前が日付形式でないとき指摘する():
    text = "---\nauthor: human\n---\n[[note]]"
    issues = _check(text, "worklog/today.md")
    assert any(issue.rule_name == "worklog 命名規則" for issue in issues)


def test_worklogでwikilinkがないとき指摘する():
    text = "---\nauthor: human\n---\n本文"
    issues = _check(text, "worklog/2026-07-11.md")
    assert any(issue.message.endswith("1つ以上必要です") for issue in issues)


def test_reportsの名前が規則外のとき指摘する():
    text = "---\nauthor: human\n---\n本文"
    issues = _check(text, "reports/report.md")
    assert any(issue.rule_name == "reports 命名規則" for issue in issues)


def test_researched_atだけがあるとき指摘する():
    text = "---\nauthor: human\nresearched_at: 2026-07-11\n---\n本文"
    issues = _check(text, "reports/2026-07-11_topic.md")
    assert any(issue.rule_name == "調査日と期限" for issue in issues)
