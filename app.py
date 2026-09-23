"""Streamlit Web UI"""
import streamlit as st
from pathlib import Path
from blog_linter.linter import lint_markdown, has_secret_issues
from blog_linter import qiita_client

QIITA_REPO_PATH = Path("/home/tetutetu/qiita-articles")

st.set_page_config(page_title="ブログ記事リンター", page_icon="🔍", layout="wide")
st.title("ブログ記事リンター")
st.caption("機密情報の漏洩チェック & 表記ブレチェック")

# 入力方法の選択
input_method = st.radio(
    "入力方法を選択",
    ["テキスト入力", "ファイルアップロード", "Qiita記事を選択"],
    horizontal=True,
)

text = ""

if input_method == "テキスト入力":
    text = st.text_area(
        "Markdownテキストを貼り付けてください",
        height=400,
        placeholder="# タイトル\n\nここにMarkdownを入力...",
    )

elif input_method == "ファイルアップロード":
    uploaded = st.file_uploader("Markdownファイル (.md)", type=["md", "txt"])
    if uploaded:
        text = uploaded.read().decode("utf-8")
        st.code(text, language="markdown")

elif input_method == "Qiita記事を選択":
    if QIITA_REPO_PATH.exists():
        md_files = sorted(QIITA_REPO_PATH.rglob("*.md"))
        if md_files:
            # ファイルパスを相対パスで表示
            file_options = {str(f.relative_to(QIITA_REPO_PATH)): f for f in md_files}
            selected = st.selectbox("記事を選択", list(file_options.keys()))
            if selected:
                text = file_options[selected].read_text(encoding="utf-8")
                st.code(text, language="markdown")
        else:
            st.warning("Markdownファイルが見つかりませんでした。")
    else:
        st.warning(
            f"Qiita記事リポジトリが見つかりません: {QIITA_REPO_PATH}\n\n"
            "テキスト入力またはファイルアップロードをご利用ください。"
        )

# チェック実行（結果を session_state に保持し、投稿セクションで再利用する）
if st.button("チェック実行", type="primary", disabled=not text):
    st.session_state["linted_text"] = text
    st.session_state["linted_issues"] = lint_markdown(text)

if "linted_issues" in st.session_state:
    issues = st.session_state["linted_issues"]
    text = st.session_state["linted_text"]

    if not issues:
        st.success("問題は見つかりませんでした！")
    else:
        secret_issues = [i for i in issues if i.category == "secret"]
        notation_issues = [i for i in issues if i.category == "notation"]
        style_issues = [i for i in issues if i.category == "style"]
        structure_issues = [i for i in issues if i.category == "structure"]

        # サマリー
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("合計", f"{len(issues)} 件")
        col2.metric("機密情報", f"{len(secret_issues)} 件")
        col3.metric("表記ブレ", f"{len(notation_issues)} 件")
        col4.metric("文体", f"{len(style_issues)} 件")
        col5.metric("構成", f"{len(structure_issues)} 件")

        category_displays = (
            ("secret", "🔐 機密情報の検出", "red"),
            ("notation", "📝 表記ブレの検出", "orange"),
            ("ai_writing", "🤖 AI 文体の検出", "gray"),
            ("style", "✍️ blog 文体ルールの検出", "blue"),
            ("structure", "🏗️ blog 構成ルールの検出", "violet"),
            ("frontmatter", "📋 Vault ルールの検出", "green"),
        )
        lines = text.split("\n")
        for category, label, divider in category_displays:
            category_issues = [
                issue for issue in issues if issue.category == category
            ]
            if not category_issues:
                continue
            st.subheader(label, divider=divider)
            for issue in category_issues:
                issue_type = "確認" if issue.needs_review else "提案"
                with st.expander(
                    f"L{issue.line_number} [{issue_type}] "
                    f"[{issue.rule_name}] {issue.matched_text}",
                    expanded=True,
                ):
                    st.markdown(f"**種別:** {issue_type}")
                    st.markdown(
                        f"**行番号:** {issue.line_number}, **列:** {issue.column}"
                    )
                    st.markdown(f"**ルール:** {issue.rule_name}")
                    st.markdown(f"**メッセージ:** {issue.message}")
                    if issue.suggestion:
                        st.markdown(f"**提案:** {issue.suggestion}")
                    if 0 < issue.line_number <= len(lines):
                        st.code(lines[issue.line_number - 1], language="text")

    # ---- Qiita 投稿セクション ----
    st.divider()
    st.subheader("🚀 Qiita に投稿")

    if has_secret_issues(issues):
        # 機密情報がある間は投稿を封じる
        st.error("機密情報が検出されているため投稿できません。先に修正してください")
        st.button("Qiita に投稿", type="primary", disabled=True, key="qiita_post_blocked")
    else:
        default_title = qiita_client.extract_title(text)
        post_title = st.text_input("タイトル", value=default_title, key="qiita_title")
        post_tags_raw = st.text_input(
            "タグ（カンマ区切り、最低1つ必須）",
            placeholder="Python, Qiita",
            key="qiita_tags",
        )
        post_private = st.toggle("限定共有（自分だけ閲覧可）", value=True, key="qiita_private")
        post_item_id = st.text_input(
            "更新する記事ID（任意・空なら新規投稿）",
            placeholder="新規投稿する場合は空のまま",
            key="qiita_item_id",
        )

        tags = [t.strip() for t in post_tags_raw.split(",") if t.strip()]

        if st.button("Qiita に投稿", type="primary", key="qiita_post"):
            if not post_title.strip():
                st.error("タイトルを入力してください")
            elif not tags:
                st.error("タグを最低1つ指定してください")
            else:
                token = qiita_client.load_token()
                if post_item_id.strip():
                    result = qiita_client.update_item(
                        item_id=post_item_id.strip(),
                        title=post_title,
                        body=text,
                        tags=tags,
                        private=post_private,
                        token=token,
                    )
                else:
                    result = qiita_client.post_item(
                        title=post_title,
                        body=text,
                        tags=tags,
                        private=post_private,
                        token=token,
                    )

                if result.ok:
                    st.success(f"投稿に成功しました： [{result.url}]({result.url})")
                else:
                    st.error(f"投稿に失敗しました：{result.error_message}")
