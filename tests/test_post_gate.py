"""post サブコマンドの投稿ゲートのテスト。

モックの理由: 実 Qiita API を叩くと本番に記事が作られる副作用があるため、
qiita_client の投稿関数をモックし「API が発火したか否か」を検証する。
"""
from unittest.mock import patch

import pytest

from blog_linter.__main__ import main
from blog_linter.qiita_client import QiitaResult


def _run_post(argv):
    """指定した引数で post サブコマンドを実行し、終了コードを返す。"""
    with patch("sys.argv", argv):
        with pytest.raises(SystemExit) as exc:
            main()
    return exc.value.code


def test_機密情報を含む記事はexit1でブロックされAPIが呼ばれない(tmp_path):
    md = tmp_path / "secret_article.md"
    # AWS アクセスキーID を本文に含める（secret_checker が検出する）
    md.write_text(
        "# サンプル記事\n\nアクセスキー: AKIAIOSFODNN7EXAMPLE\n",
        encoding="utf-8",
    )

    with patch("blog_linter.qiita_client.post_item") as mock_post, \
            patch("blog_linter.qiita_client.update_item") as mock_update:
        code = _run_post(["prog", "post", str(md), "--tags", "AWS"])

    assert code == 1
    mock_post.assert_not_called()
    mock_update.assert_not_called()


def test_表記ブレのみの記事は投稿処理まで進む(tmp_path):
    md = tmp_path / "notation_article.md"
    # 「サーバ」は表記ブレのみ（機密情報ではない）
    md.write_text(
        "# サンプル記事\n\nこれはサーバの構築手順です。\n",
        encoding="utf-8",
    )

    fake_result = QiitaResult(
        ok=True,
        status_code=201,
        url="https://qiita.com/items/dummy",
        item_id="dummy",
    )
    with patch("blog_linter.qiita_client.post_item", return_value=fake_result) as mock_post:
        code = _run_post(["prog", "post", str(md), "--tags", "AWS"])

    assert code == 0
    mock_post.assert_called_once()
