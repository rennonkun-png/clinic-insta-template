"""医院のアクセストークンを「許可リンク」方式で取得する（運用者向け）。

流れ:
  1. python scripts/get_token.py --link
       → 医院に送る「許可リンク」を表示。医院は Instagram（または Facebook）にログインした状態で開き「許可」を押すだけ
       → 許可後に authorize.html が開き、コード（英数字）が表示される。それを送ってもらう
  2. python scripts/get_token.py --code <送られてきたコード>
       → アクセストークンと Instagram ユーザー ID を取得して表示
       → setup_clinic.py に渡すか、GitHub Secrets に登録する

方式（config/operator.json で自動判別）:
  - 統合ログイン（2026年以降に作ったアプリはこちらのみ）: fb_config_id を設定
      Meta for Developers → アプリ → ユースケース「Instagramでメッセージとコンテンツを管理」→ カスタマイズ
      → API setup with Unified login → 設定ID と リダイレクトURL（ig_redirect_uri と同じ）を登録
      ig_app_id / ig_app_secret は「アプリの設定 → ベーシック」のアプリID / app secret
      トークンはシステムユーザートークンで期限なし
  - Instagram ログイン（以前のアプリ）: fb_config_id を空にする。60 日トークン（投稿のたびに自動延長）

アプリが開発モードの間は、医院の Instagram アカウントをアプリの「役割 → Instagram テスター」に追加し、
医院側で承認（Instagram アプリ → 設定 → ウェブサイトのアクセス許可 → アプリとウェブサイト → テスター招待）してもらう。
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
V = "v24.0"
IG_SCOPES = "instagram_business_basic,instagram_business_content_publish,instagram_business_manage_insights"


def load_operator() -> dict:
    if not OPERATOR.exists():
        sys.exit("config/operator.json がありません。config/operator.example.json をコピーして作成してください。")
    op = json.load(open(OPERATOR, encoding="utf-8"))
    for k in ("ig_app_id", "ig_redirect_uri"):
        if not op.get(k) or op[k] == "1234567890":
            sys.exit(f"config/operator.json の {k} が未設定です")
    return op


def unified(op: dict) -> bool:
    return bool(str(op.get("fb_config_id", "")).strip())


def auth_link(op: dict) -> str:
    if unified(op):
        q = {"client_id": op["ig_app_id"], "config_id": op["fb_config_id"], "redirect_uri": op["ig_redirect_uri"],
             "response_type": "code", "override_default_response_type": "true"}
        return f"https://www.facebook.com/{V}/dialog/oauth?" + urlencode(q)
    q = {"client_id": op["ig_app_id"], "redirect_uri": op["ig_redirect_uri"], "scope": IG_SCOPES, "response_type": "code"}
    return "https://www.instagram.com/oauth/authorize?" + urlencode(q)


def _need_secret(op: dict) -> str:
    sec = op.get("ig_app_secret", "")
    if not sec or sec.startswith("xxxx"):
        sys.exit("config/operator.json の ig_app_secret が未設定です（アプリの設定 → ベーシック → app secret）")
    return sec


def exchange_unified(op: dict, code: str) -> dict:
    sec = _need_secret(op)
    r = requests.get(f"https://graph.facebook.com/{V}/oauth/access_token",
                     params={"client_id": op["ig_app_id"], "client_secret": sec, "redirect_uri": op["ig_redirect_uri"], "code": code}, timeout=30)
    data = r.json()
    if "access_token" not in data:
        sys.exit(f"コードの交換に失敗しました: {data}")
    token = data["access_token"]
    # どの Instagram アカウントが許可されたかは debug_token の granular_scopes に入っている
    dbg = requests.get(f"https://graph.facebook.com/{V}/debug_token",
                       params={"input_token": token, "access_token": f"{op['ig_app_id']}|{sec}"}, timeout=30).json().get("data", {})
    ids: list[str] = []
    for g in dbg.get("granular_scopes", []):
        if g.get("scope", "").startswith("instagram"):
            ids += [str(t) for t in g.get("target_ids", []) if str(t) not in ids]
    if not ids:  # 予備: 割り当て済みアカウント一覧
        try:
            res = requests.get(f"https://graph.facebook.com/{V}/me/assigned_instagram_accounts", params={"access_token": token}, timeout=30).json()
            ids = [str(x["id"]) for x in res.get("data", []) if x.get("id")]
        except Exception:  # noqa: BLE001
            pass
    accounts = []
    for i in ids:
        info = requests.get(f"https://graph.facebook.com/{V}/{i}", params={"fields": "id,username,followers_count", "access_token": token}, timeout=30).json()
        if "error" not in info:
            accounts.append(info)
    if not accounts:
        sys.exit("トークンは取得できましたが、Instagram アカウントが見つかりません。許可の画面で Instagram アカウントを選んだか確認してください。\n"
                 f"許可された権限: {dbg.get('scopes')}")
    exp = int(dbg.get("expires_at") or 0)
    return {"access_token": token, "user_id": str(accounts[0]["id"]), "username": accounts[0].get("username"), "account_type": "BUSINESS",
            "expires_in_days": None if exp == 0 else exp, "scopes": dbg.get("scopes", []),
            "other_accounts": [a.get("username") for a in accounts[1:]], "mode": "unified"}


def exchange_ig(op: dict, code: str) -> dict:
    sec = _need_secret(op)
    r = requests.post(
        "https://api.instagram.com/oauth/access_token",
        data={"client_id": op["ig_app_id"], "client_secret": sec, "grant_type": "authorization_code",
              "redirect_uri": op["ig_redirect_uri"], "code": code},
        timeout=30,
    )
    data = r.json()
    if "access_token" not in data:
        sys.exit(f"コードの交換に失敗しました: {data}")
    short = data["access_token"]
    user_id = str(data.get("user_id", ""))
    r = requests.get("https://graph.instagram.com/access_token",
                     params={"grant_type": "ig_exchange_token", "client_secret": sec, "access_token": short}, timeout=30)
    data2 = r.json()
    if "access_token" not in data2:
        sys.exit(f"長期トークンへの交換に失敗しました: {data2}")
    token = data2["access_token"]
    me = requests.get(f"https://graph.instagram.com/{V}/me", params={"fields": "id,username,account_type", "access_token": token}, timeout=30).json()
    return {"access_token": token, "user_id": str(me.get("id") or user_id), "username": me.get("username"), "account_type": me.get("account_type"),
            "expires_in_days": int(data2.get("expires_in", 0)) // 86400, "mode": "instagram"}


def exchange(op: dict, code: str) -> dict:
    code = code.strip().split("#")[0]  # 末尾に #_ や #_=_ が付くことがある
    return exchange_unified(op, code) if unified(op) else exchange_ig(op, code)


def main() -> int:
    ap = argparse.ArgumentParser(description="医院の Instagram トークンを許可リンク方式で取得")
    ap.add_argument("--link", action="store_true", help="医院に送る許可リンクを表示")
    ap.add_argument("--code", help="医院から送られてきたコード")
    ap.add_argument("--json", action="store_true", help="結果を JSON で出力（setup_clinic.py 連携用）")
    a = ap.parse_args()
    op = load_operator()
    if a.link or not a.code:
        print("医院に送る許可リンク（Instagram にログインしたスマホやパソコンで開いて「許可」を押してもらう）:\n")
        print(auth_link(op))
        print("\n許可後に表示されるコードを受け取ったら:  python scripts/get_token.py --code <コード>")
        return 0
    res = exchange(op, a.code)
    if a.json:
        print(json.dumps(res, ensure_ascii=False))
        return 0
    days = res["expires_in_days"]
    print(f"取得できました: @{res['username']}  有効期限: {'なし' if days is None else str(days) + ' 日（投稿のたびに自動延長）'}")
    print(f"IG_USER_ID      = {res['user_id']}")
    print(f"IG_ACCESS_TOKEN = {res['access_token'][:12]}...（全文は --json で出力）")
    if res.get("scopes") is not None:
        print(f"許可された権限: {', '.join(res['scopes'])}")
        if "instagram_manage_insights" not in res["scopes"]:
            print("注意: instagram_manage_insights がないため、週次分析ではリーチ・保存数が取れません（いいね・コメント数のみ）")
    if res.get("other_accounts"):
        print(f"ほかに許可されたアカウント: {', '.join(res['other_accounts'])}（先頭の @{res['username']} を使います）")
    if res.get("account_type") not in ("BUSINESS", "MEDIA_CREATOR"):
        print("注意: プロアカウント（ビジネス/クリエイター）ではありません。切り替えてから再度許可してもらってください。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
