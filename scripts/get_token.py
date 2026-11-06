"""医院のアクセストークンを「許可リンク」方式で取得する（運用者向け）。

流れ:
  1. python scripts/get_token.py --link
       → 医院に送る「許可リンク」を表示。医院は Instagram にログインした状態でタップして「許可」を押すだけ
       → 許可後に authorize.html が開き、コード（英数字）が表示される。それを送ってもらう
  2. python scripts/get_token.py --code <送られてきたコード>
       → 長期アクセストークン（60日・自動延長）と Instagram ユーザー ID を取得して表示
       → setup_clinic.py に渡すか、GitHub Secrets に登録する

事前準備（運用者が1回だけ）:
  - Meta for Developers でアプリを作成し「Instagram（Instagram ログイン）」を追加
  - API setup with Instagram login → Business login settings → OAuth redirect URIs に
    config/operator.json の ig_redirect_uri を登録
  - アプリが開発モードの間は、医院の Instagram アカウントを「Instagram テスター」として追加し、
    医院側で承認（Instagram アプリ → 設定 → ウェブサイトのアクセス許可 → アプリとウェブサイト → テスター招待）
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlencode

import requests

ROOT = Path(__file__).resolve().parent.parent
OPERATOR = ROOT / "config" / "operator.json"
SCOPES = "instagram_business_basic,instagram_business_content_publish,instagram_business_manage_insights"


def load_operator() -> dict:
    if not OPERATOR.exists():
        sys.exit("config/operator.json がありません。config/operator.example.json をコピーして作成してください。")
    op = json.load(open(OPERATOR, encoding="utf-8"))
    for k in ("ig_app_id", "ig_app_secret", "ig_redirect_uri"):
        if not op.get(k):
            sys.exit(f"config/operator.json の {k} が未設定です")
    return op


def auth_link(op: dict) -> str:
    q = {"client_id": op["ig_app_id"], "redirect_uri": op["ig_redirect_uri"], "scope": SCOPES, "response_type": "code"}
    return "https://www.instagram.com/oauth/authorize?" + urlencode(q)


def exchange(op: dict, code: str) -> dict:
    code = code.strip().split("#")[0]  # 末尾に #_ が付くことがある
    r = requests.post(
        "https://api.instagram.com/oauth/access_token",
        data={"client_id": op["ig_app_id"], "client_secret": op["ig_app_secret"], "grant_type": "authorization_code",
              "redirect_uri": op["ig_redirect_uri"], "code": code},
        timeout=30,
    )
    data = r.json()
    if "access_token" not in data:
        sys.exit(f"コードの交換に失敗しました: {data}")
    short = data["access_token"]
    user_id = str(data.get("user_id", ""))
    r = requests.get(
        "https://graph.instagram.com/access_token",
        params={"grant_type": "ig_exchange_token", "client_secret": op["ig_app_secret"], "access_token": short},
        timeout=30,
    )
    data2 = r.json()
    if "access_token" not in data2:
        sys.exit(f"長期トークンへの交換に失敗しました: {data2}")
    token = data2["access_token"]
    me = requests.get("https://graph.instagram.com/v24.0/me", params={"fields": "id,username,account_type", "access_token": token}, timeout=30).json()
    return {"access_token": token, "user_id": str(me.get("id") or user_id), "username": me.get("username"), "account_type": me.get("account_type"),
            "expires_in_days": int(data2.get("expires_in", 0)) // 86400}


def main() -> int:
    ap = argparse.ArgumentParser(description="医院の Instagram トークンを許可リンク方式で取得")
    ap.add_argument("--link", action="store_true", help="医院に送る許可リンクを表示")
    ap.add_argument("--code", help="医院から送られてきたコード")
    ap.add_argument("--json", action="store_true", help="結果を JSON で出力（setup_clinic.py 連携用）")
    a = ap.parse_args()
    op = load_operator()
    if a.link or not a.code:
        print("医院に送る許可リンク（Instagram にログインしたスマホで開いて「許可」を押してもらう）:\n")
        print(auth_link(op))
        print("\n許可後に表示されるコードを受け取ったら:  python scripts/get_token.py --code <コード>")
        return 0
    res = exchange(op, a.code)
    if a.json:
        print(json.dumps(res, ensure_ascii=False))
        return 0
    print(f"取得できました: @{res['username']} ({res['account_type']})  有効 {res['expires_in_days']} 日（投稿のたびに自動延長）")
    print(f"IG_USER_ID      = {res['user_id']}")
    print(f"IG_ACCESS_TOKEN = {res['access_token'][:12]}...（全文は --json で出力）")
    if res.get("account_type") not in ("BUSINESS", "MEDIA_CREATOR"):
        print("注意: プロアカウント（ビジネス/クリエイター）ではありません。切り替えてから再度許可してもらってください。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
