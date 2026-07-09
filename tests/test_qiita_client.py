"""qiita_client のテスト。

モックの理由: 実 Qiita API を叩くと本番に記事が作られる副作用があり、かつ
認証トークンも不在のため、HTTP 層(requests)をモックする。
"""
from unittest.mock import patch

from blog_linter import qiita_client
from blog_linter.qiita_client import extract_title, post_item, update_item


class _FakeResponse:
    """requests.Response の最小スタブ。"""

    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def test_タグが空のときはAPIを呼ばずに失敗を返す():
    with patch("blog_linter.qiita_client.requests.request") as mock_request:
        result = post_item(title="タイトル", body="本文", tags=[], token="dummy-token")

    assert result.ok is False
    assert result.error_message == "タグを最低1つ指定してください"
    mock_request.assert_not_called()


def test_トークンが空のときはAPIを呼ばずに失敗を返す():
    with patch("blog_linter.qiita_client.requests.request") as mock_request:
        result = post_item(title="タイトル", body="本文", tags=["Python"], token="")

    assert result.ok is False
    assert result.error_message == "QIITA_TOKEN が設定されていません"
    mock_request.assert_not_called()


def test_201応答で記事URLとIDを返す():
    fake = _FakeResponse(
        201,
        {"url": "https://qiita.com/items/abc123", "id": "abc123"},
    )
    with patch("blog_linter.qiita_client.requests.request", return_value=fake):
        result = post_item(
            title="タイトル", body="本文", tags=["Python"], token="dummy-token"
        )

    assert result.ok is True
    assert result.status_code == 201
    assert result.url == "https://qiita.com/items/abc123"
    assert result.item_id == "abc123"


def test_401応答でエラーメッセージを整形して返す():
    fake = _FakeResponse(401, {"message": "Unauthorized"})
    with patch("blog_linter.qiita_client.requests.request", return_value=fake):
        result = post_item(
            title="タイトル", body="本文", tags=["Python"], token="invalid-token"
        )

    assert result.ok is False
    assert result.status_code == 401
    assert result.error_message == "Unauthorized"


def test_更新は200応答で成功を返す():
    fake = _FakeResponse(
        200, {"url": "https://qiita.com/items/xyz789", "id": "xyz789"}
    )
    with patch("blog_linter.qiita_client.requests.request", return_value=fake) as mock_request:
        result = update_item(
            item_id="xyz789",
            title="更新後タイトル",
            body="更新後本文",
            tags=["Python"],
            token="dummy-token",
        )

    assert result.ok is True
    assert result.item_id == "xyz789"
    # PATCH メソッドで記事IDのエンドポイントを叩いていること
    method, endpoint = mock_request.call_args.args
    assert method == "PATCH"
    assert endpoint.endswith("/items/xyz789")


def test_トークンの値がエラーメッセージに漏れない():
    # 接続失敗時でも Authorization に載せたトークンが error_message に混入しないこと
    import requests

    with patch(
        "blog_linter.qiita_client.requests.request",
        side_effect=requests.ConnectionError("boom"),
    ):
        result = post_item(
            title="タイトル",
            body="本文",
            tags=["Python"],
            token="super-secret-token-value",
        )

    assert result.ok is False
    assert "super-secret-token-value" not in result.error_message


def test_extract_titleは先頭H1からタイトルを取り出す():
    markdown = "# 私の記事タイトル\n\n本文です。\n## 見出し2"
    assert extract_title(markdown) == "私の記事タイトル"


def test_extract_titleはH1が無いとき空文字を返す():
    markdown = "## 見出しレベル2\n\n本文にH1はありません。"
    assert extract_title(markdown) == ""
