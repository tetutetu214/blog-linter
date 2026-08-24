"""対象別に実行するチェックの組み合わせを定義する"""

PROFILE_CHECKS: dict[str, tuple[str, ...]] = {
    "qiita": ("secrets", "notation", "ai_writing"),
    "blog": ("secrets", "ai_writing"),
    # vault に notation を含めない理由: 内部ノートに公開記事水準の表記統一を
    # 強制すると過去ログへの指摘がノイズになる（2026-07-11 実測185件）。
    # 表記ブレは記事化するときに qiita プロファイルで掛ける。
    # ai_writing も内部ノートではノイズになるため、記事化するときだけ掛ける。
    "vault": ("secrets", "frontmatter"),
}


def get_profile_checks(profile: str) -> tuple[str, ...]:
    """プロファイルに対応するチェック名を返す"""
    try:
        return PROFILE_CHECKS[profile]
    except KeyError as error:
        raise ValueError(f"不明なプロファイルです: {profile}") from error
