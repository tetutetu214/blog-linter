from blog_linter.article_sources import list_markdown_files


def test_markdown以外と除外ディレクトリ配下を一覧に含めない(tmp_path):
    (tmp_path / "a.md").write_text("A", encoding="utf-8")
    (tmp_path / "b.txt").write_text("B", encoding="utf-8")
    nested = tmp_path / "sub" / "deep"
    nested.mkdir(parents=True)
    (nested / "c.md").write_text("C", encoding="utf-8")
    excluded = tmp_path / "node_modules" / "pkg"
    excluded.mkdir(parents=True)
    (excluded / "readme.md").write_text("X", encoding="utf-8")

    files = list_markdown_files(tmp_path)

    names = [f.relative_to(tmp_path).as_posix() for f in files]
    assert names == ["a.md", "sub/deep/c.md"]


def test_存在しないディレクトリは空リストを返す(tmp_path):
    assert list_markdown_files(tmp_path / "missing") == []
