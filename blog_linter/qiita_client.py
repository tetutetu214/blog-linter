"""Qiita API v2 クライアント: 記事の新規投稿・更新を行う。

セキュリティ方針: 認証トークンの値は print / log / 例外メッセージのいずれにも
含めない。ネットワークエラーを整形する際もトークンが混入しないよう、requests の
例外メッセージをそのまま連結せず、種類ごとに固定文言へ変換する。
"""
import os
import re
from dataclasses import dataclass
from pathlib import Path

import requests
from dotenv import dotenv_values

QIITA_API_BASE = "https://qiita.com/api/v2"

# ~/.secrets/qiita.env にトークンを置く運用（リポジトリ外）
_SECRETS_ENV_PATH = "~/.secrets/qiita.env"

# API 呼び出しのタイムアウト（秒）
_REQUEST_TIMEOUT = 30


@dataclass
class QiitaResult:
    ok: bool
    status_code: int
    url: str = ""
    item_id: str = ""
    error_message: str = ""


def load_token() -> str | None:
    """Qiita API トークンを読み込む。

    優先順位:
      1. 環境変数 QIITA_TOKEN
      2. ~/.secrets/qiita.env の QIITA_TOKEN（python-dotenv で読む）
    見つからなければ None を返す。トークンの値はログ等に出さない。
    """
    env_token = os.environ.get("QIITA_TOKEN")
    if env_token:
        return env_token

    env_path = Path(_SECRETS_ENV_PATH).expanduser()
    if env_path.exists():
        values = dotenv_values(env_path)
        token = values.get("QIITA_TOKEN")
        if token:
            return token

    return None


def extract_title(markdown: str) -> str:
    """先頭に現れる H1（`# 見出し`）行からタイトルを抽出する。

    見つからなければ空文字を返す。`##` 以降の見出しは対象外。
    """
    for line in markdown.split("\n"):
        match = re.match(r"^#\s+(.+?)\s*$", line)
        if match:
            return match.group(1)
    return ""


def _build_tags(tags: list[str]) -> list[dict]:
    """タグ名のリストを Qiita API のタグ構造へ変換する。"""
    return [{"name": t, "versions": []} for t in tags]


def _extract_api_message(response: requests.Response) -> str:
    """エラーレスポンスから message を安全に取り出す。

    JSON でない/message が無い場合はステータス由来の文言にフォールバックする。
    """
    try:
        payload = response.json()
        message = payload.get("message")
        if message:
            return str(message)
    except ValueError:
        pass
    return f"HTTP {response.status_code}"


def _send(
    method: str,
    endpoint: str,
    title: str,
    body: str,
    tags: list[str],
    private: bool,
    tweet: bool,
    token: str | None,
    success_status: int,
) -> QiitaResult:
    """post_item / update_item 共通の送信処理。"""
    # 事前バリデーション（API を叩かずに弾く）
    if not token:
        return QiitaResult(
            ok=False,
            status_code=0,
            error_message="QIITA_TOKEN が設定されていません",
        )
    if not tags:
        return QiitaResult(
            ok=False,
            status_code=0,
            error_message="タグを最低1つ指定してください",
        )

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "title": title,
        "body": body,
        "tags": _build_tags(tags),
        "private": private,
        "tweet": tweet,
    }

    try:
        response = requests.request(
            method,
            endpoint,
            headers=headers,
            json=payload,
            timeout=_REQUEST_TIMEOUT,
        )
    except requests.Timeout:
        # トークンが混ざらないよう固定文言に変換する
        return QiitaResult(
            ok=False,
            status_code=0,
            error_message="Qiita API への接続がタイムアウトしました",
        )
    except requests.RequestException:
        return QiitaResult(
            ok=False,
            status_code=0,
            error_message="Qiita API への接続に失敗しました",
        )

    if response.status_code == success_status:
        try:
            data = response.json()
        except ValueError:
            data = {}
        return QiitaResult(
            ok=True,
            status_code=response.status_code,
            url=data.get("url", ""),
            item_id=data.get("id", ""),
        )

    return QiitaResult(
        ok=False,
        status_code=response.status_code,
        error_message=_extract_api_message(response),
    )


def post_item(
    title: str,
    body: str,
    tags: list[str],
    private: bool = True,
    tweet: bool = False,
    token: str | None = None,
) -> QiitaResult:
    """新規記事を投稿する（POST /items）。成功は 201。"""
    return _send(
        method="POST",
        endpoint=f"{QIITA_API_BASE}/items",
        title=title,
        body=body,
        tags=tags,
        private=private,
        tweet=tweet,
        token=token,
        success_status=201,
    )


def update_item(
    item_id: str,
    title: str,
    body: str,
    tags: list[str],
    private: bool = True,
    token: str | None = None,
) -> QiitaResult:
    """既存記事を更新する（PATCH /items/{item_id}）。成功は 200。"""
    return _send(
        method="PATCH",
        endpoint=f"{QIITA_API_BASE}/items/{item_id}",
        title=title,
        body=body,
        tags=tags,
        private=private,
        tweet=False,
        token=token,
        success_status=200,
    )
