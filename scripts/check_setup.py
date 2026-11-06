"""初期設定の確認ツール。トークン・ユーザーID・設定ファイルが正しいかを調べる。
使い方: python scripts/check_setup.py
"""
from __future__ import annotations

import os
import sys

from common import CONFIG_PATH, load_config, load_posts, log
import instagram


def main() -> int:
    ok = True
    log(f"設定ファイル: {CONFIG_PATH}")
    cfg = load_config()
    log(f"医院名: {cfg.get('clinic_name')}  診療科: {cfg.get('specialties')}")
    posts = load_posts(cfg)
    log(f"投稿ネタ: {len(posts)} 件")

    token = os.environ.get("IG_ACCESS_TOKEN", "").strip()
    user_id = os.environ.get("IG_USER_ID", "").strip()
    if not token:
        log("NG: IG_ACCESS_TOKEN が未設定です")
        return 1
    try:
        me = instagram.get_me(token)
        log(f"OK: トークン有効  @{me.get('username')}  id={me.get('id')}  type={me.get('account_type')}")
        if me.get("account_type") not in ("BUSINESS", "MEDIA_CREATOR"):
            log("NG: アカウントが ビジネス/クリエイター ではありません。Instagram アプリでプロアカウントに切り替えてください。")
            ok = False
        if user_id and str(me.get("id")) != user_id:
            log(f"注意: IG_USER_ID({user_id}) とトークンのID({me.get('id')}) が一致しません。IG_USER_ID は {me.get('id')} にしてください。")
            ok = False
    except Exception as e:  # noqa: BLE001
        log(f"NG: トークン確認に失敗: {e}")
        ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
