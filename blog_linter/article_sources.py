"""記事ソース: UI が参照する記事・下書きの置き場所と一覧取得"""
from pathlib import Path

# Qiita 記事の正本リポジトリ（qiita-cli 管理。記事本体は public/ 配下）
QIITA_ARTICLES_PATH = Path.home() / "projects" / "qiita-articles" / "public"

# Obsidian Vault のブログ下書き（人と Claude の共同編集領域）
VAULT_DRAFTS_PATH = Path("/mnt/c/Users/lemon/Vault/drafts")

# 一覧から除外するディレクトリ名
_EXCLUDED_DIRS = {"node_modules", ".git", ".obsidian", ".venv"}


def list_markdown_files(root: Path) -> list[Path]:
    """root 配下の Markdown ファイルを再帰的に列挙する（除外ディレクトリ配下は含めない）"""
    if not root.is_dir():
        return []
    return sorted(
        f for f in root.rglob("*.md")
        if not _EXCLUDED_DIRS.intersection(f.relative_to(root).parts[:-1])
    )
