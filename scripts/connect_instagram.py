"""GitHub Actions 上で Instagram を接続する（どの PC からでもブラウザだけで完了）。

Actions → 「Instagram を接続」→ Run workflow → 許可コードを貼り付けて実行。
許可コードをトークンに交換し、このリポジトリの Secrets（IG_ACCESS_TOKEN / IG_USER_ID）に保存する。
トークンはログに出さない。

必要な設定（リポジトリの Settings → Secrets and variables → Actions）:
  Variables: META_APP_ID, META_CONFIG_ID, IG_REDIRECT_URI   （運用者ツールが自動で登録）
  Secrets  : META_APP_SECRET（Meta アプリの app secret。運用者がブラウザで登録）
             GH_ADMIN_TOKEN（Secrets を書き込むための GitHub トークン。運用者ツールが自動で登録）
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import get_token  # noqa: E402
from setup_clinic import GitHub  # noqa: E402


def env(name: str) -> str:
    v = os.environ.get(name, "").strip()
    if not v:
        sys.exit(f"{name} が未設定です（Settings → Secrets and variables → Actions で登録してください）")
    return v


def main() -> int:
    code = env("IG_CODE")
    op = {"ig_app_id": env("META_APP_ID"), "ig_app_secret": env("META_APP_SECRET"), "ig_redirect_uri": env("IG_REDIRECT_URI"),
          "fb_config_id": os.environ.get("META_CONFIG_ID", "").strip()}
    res = get_token.exchange(op, code)
    token = res["access_token"]
    print(f"::add-mask::{token}", flush=True)
    owner, repo = env("GITHUB_REPOSITORY").split("/", 1)
    gh = GitHub(env("GH_ADMIN_TOKEN"))
    gh.put_secret(owner, repo, "IG_ACCESS_TOKEN", token)
    gh.put_secret(owner, repo, "IG_USER_ID", res["user_id"])
    days = res.get("expires_in_days")
    print(f"接続できました: @{res.get('username')}（有効期限: {'なし' if days is None else str(days) + ' 日・自動延長'}）")
    scopes = res.get("scopes")
    if scopes is not None and "instagram_manage_insights" not in scopes:
        print("注意: 分析用の許可（instagram_manage_insights）がないため、週次分析はいいね・コメント数のみになります")
    if res.get("other_accounts"):
        print(f"ほかに許可されたアカウント: {', '.join(res['other_accounts'])}（@{res.get('username')} を使います）")
    print("IG_ACCESS_TOKEN / IG_USER_ID を Secrets に保存しました。毎日の自動投稿が有効になります。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
