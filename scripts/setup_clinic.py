"""運用者向け: 医院を 1 件、コマンド 1 本でセットアップする。

  python scripts/setup_clinic.py --name "たびかわ歯科クリニック" --specialties dental --code <医院から届いた許可コード>

やること（GitHub の REST API を使う。gh コマンド不要）:
  1. テンプレートリポジトリから医院用リポジトリを作成（Public。トークンは Secrets なので公開されない）
  2. 許可コード → 長期トークンに交換（get_token.py と同じ）し、Secrets に登録
     （IG_ACCESS_TOKEN / IG_USER_ID / CF_ACCOUNT_ID / CF_API_TOKEN / ANTHROPIC_API_KEY / HF_TOKEN）
  3. GitHub Pages を有効化（main / docs）、Actions の書き込み権限を有効化
  4. config/clinic.json を生成してコミット
  5. テスト実行（DRY_RUN）を起動

必要: config/operator.json（config/operator.example.json を参照）、pip install requests pynacl
対話モード: 引数を省略すると質問に答える形で進みます。
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import get_token  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
API = "https://api.github.com"

SPECIALTIES = {
    "dental": "歯科", "internal": "内科", "gastroenterology": "消化器内科", "dermatology": "皮膚科", "ent": "耳鼻咽喉科",
    "pediatrics": "小児科", "ophthalmology": "眼科", "orthopedics": "整形外科", "gynecology": "婦人科", "mental": "心療内科",
    "beauty": "美容医療", "webmarketing": "クリニックWEB集患コラム（自社発信用）",
}
GOALS = {"reach": "伸びる投稿", "reels": "リール動画", "followers": "フォロワーを増やす", "acquisition": "集患"}
SERVICE_NAMES = {
    "whitening": "ホワイトニング", "ceramic": "セラミック治療", "orthodontics": "矯正治療", "implant": "インプラント", "pediatric_dental": "小児歯科",
    "perio": "歯周病治療・予防", "sleep_apnea": "睡眠時無呼吸の検査・治療", "beauty_iv": "美容点滴", "placenta": "プラセンタ注射", "laser": "レーザー治療",
    "aga": "AGA治療", "vaccination": "予防接種", "health_check": "健康診断・検査", "allergy": "アレルギー・花粉症治療", "endoscopy": "胃カメラ・大腸カメラ",
    "pylori": "ピロリ菌検査・除菌", "hearing": "聴力検査・補聴器相談", "contact": "コンタクトレンズ処方", "myopia_control": "近視の進行抑制", "rehab": "リハビリテーション",
    "osteoporosis": "骨密度検査", "sports": "スポーツ整形", "pill": "低用量ピル・月経移動", "hpv": "HPVワクチン・子宮頸がん検診", "menopause": "更年期外来",
    "counseling": "カウンセリング", "web_consulting": "クリニック向けWEB集患支援",
}
AUTHOR = {"dental": "歯科医師が解説", "internal": "内科医が解説", "gastroenterology": "消化器内科医が解説", "dermatology": "皮膚科医が解説",
          "ent": "耳鼻科医が解説", "pediatrics": "小児科医が解説", "ophthalmology": "眼科医が解説", "orthopedics": "整形外科医が解説",
          "gynecology": "婦人科医が解説", "mental": "心療内科医が解説", "beauty": "美容医療の医師が解説", "webmarketing": "クリニック集患の専門家が解説"}


def log(m: str) -> None:
    print(f"[setup] {m}", flush=True)


class GitHub:
    def __init__(self, token: str):
        self.h = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}

    def req(self, method: str, path: str, ok=(200, 201, 204), **kw) -> dict:
        r = requests.request(method, API + path, headers=self.h, timeout=60, **kw)
        if r.status_code not in ok:
            sys.exit(f"GitHub API エラー {method} {path}: {r.status_code} {r.text[:300]}")
        return r.json() if r.text else {}

    def create_from_template(self, template: str, owner: str, name: str, description: str) -> dict:
        exists = requests.get(f"{API}/repos/{owner}/{name}", headers=self.h, timeout=30)
        if exists.status_code == 200:
            log(f"リポジトリ {owner}/{name} はすでにあります。そのまま使います")
            return exists.json()
        return self.req("POST", f"/repos/{template}/generate", json={"owner": owner, "name": name, "description": description, "private": False, "include_all_branches": False})

    def put_secret(self, owner: str, repo: str, name: str, value: str) -> None:
        from nacl import encoding, public  # pynacl

        key = self.req("GET", f"/repos/{owner}/{repo}/actions/secrets/public-key")
        pk = public.PublicKey(key["key"].encode(), encoding.Base64Encoder())
        sealed = public.SealedBox(pk).encrypt(value.encode())
        self.req("PUT", f"/repos/{owner}/{repo}/actions/secrets/{name}", json={"encrypted_value": base64.b64encode(sealed).decode(), "key_id": key["key_id"]})

    def enable_pages(self, owner: str, repo: str) -> str:
        r = requests.post(f"{API}/repos/{owner}/{repo}/pages", headers=self.h, json={"source": {"branch": "main", "path": "/docs"}}, timeout=60)
        if r.status_code not in (201, 409):  # 409 = すでに有効
            sys.exit(f"Pages の有効化に失敗: {r.status_code} {r.text[:200]}")
        info = self.req("GET", f"/repos/{owner}/{repo}/pages")
        return info.get("html_url", f"https://{owner}.github.io/{repo}/")

    def workflow_write(self, owner: str, repo: str) -> None:
        self.req("PUT", f"/repos/{owner}/{repo}/actions/permissions/workflow", json={"default_workflow_permissions": "write", "can_approve_pull_request_reviews": False})

    def put_file(self, owner: str, repo: str, path: str, content: str, message: str) -> None:
        cur = requests.get(f"{API}/repos/{owner}/{repo}/contents/{path}", headers=self.h, timeout=30)
        body = {"message": message, "content": base64.b64encode(content.encode("utf-8")).decode()}
        if cur.status_code == 200:
            body["sha"] = cur.json()["sha"]
        self.req("PUT", f"/repos/{owner}/{repo}/contents/{path}", json=body)

    def dispatch(self, owner: str, repo: str, workflow: str, inputs: dict) -> None:
        self.req("POST", f"/repos/{owner}/{repo}/actions/workflows/{workflow}/dispatches", json={"ref": "main", "inputs": inputs})


def ask(prompt: str, default: str = "") -> str:
    v = input(f"{prompt}{f' [{default}]' if default else ''}: ").strip()
    return v or default


def ask_multi(prompt: str, options: dict, default: list[str]) -> list[str]:
    print(prompt)
    for k, v in options.items():
        print(f"  {k:16} {v}")
    v = ask("カンマ区切りで入力", ",".join(default))
    chosen = [x.strip() for x in v.split(",") if x.strip() in options]
    return chosen or default


def _strip(o):
    if isinstance(o, dict):
        return {k: _strip(v) for k, v in o.items() if not k.startswith("_")}
    return o


def build_config(a, specialties: list[str], goals: list[str]) -> dict:
    base = _strip(json.load(open(ROOT / "config" / "clinic.json", encoding="utf-8")))
    cfg = dict(base)
    cfg["clinic_name"] = a.name
    cfg["clinic_name_short"] = a.short or a.name
    cfg["specialties"] = specialties
    cfg["include_common"] = specialties != ["webmarketing"]
    cfg["goals"] = goals
    cfg["author_label"] = a.author or next((AUTHOR[s] for s in specialties if s in AUTHOR), "")
    cfg["footer_text"] = a.footer or ""
    cfg["theme"] = {"primary_color": a.primary, "accent_color": a.accent, "font": a.font}
    cfg["services"] = {k: v for k, v in base.get("services", {}).items() if k in (a.services or [])} if a.services is not None else base.get("services", {})
    for k in (a.services or []):
        cfg["services"].setdefault(k, {"name": SERVICE_NAMES.get(k, k)})
    cap = cfg.setdefault("caption", {})
    cap["hashtags_fixed"] = [t if t.startswith("#") else f"#{t}" for t in (a.hashtags or [])]
    cap["disclaimer"] = "" if specialties == ["webmarketing"] else cap.get("disclaimer", "")
    cfg["schedule"]["start_date"] = a.start or time.strftime("%Y-%m-%d")
    cfg["schedule"]["post_weekdays"] = [int(x) for x in a.weekdays.split(",")] if a.weekdays else cfg["schedule"]["post_weekdays"]
    return cfg


def main() -> int:
    ap = argparse.ArgumentParser(description="医院を1件セットアップ")
    ap.add_argument("--name", help="医院名")
    ap.add_argument("--short", help="短い医院名（ハッシュタグ用）")
    ap.add_argument("--repo", help="リポジトリ名（省略時は医院名から自動）")
    ap.add_argument("--specialties", help="診療科キー（カンマ区切り）例: dental")
    ap.add_argument("--goals", help="目的（カンマ区切り）例: reach,followers,acquisition")
    ap.add_argument("--services", help="提供サービスキー（カンマ区切り）。省略時はテンプレートの既定")
    ap.add_argument("--hashtags", help="固定ハッシュタグ（カンマ区切り）")
    ap.add_argument("--footer", help="画像下の一行（住所・電話）")
    ap.add_argument("--author", help="肩書き（例: 歯科衛生士が解説）")
    ap.add_argument("--primary", default="#2A7A6E")
    ap.add_argument("--accent", default="#F4C542")
    ap.add_argument("--font", default="gothic", choices=["gothic", "serif"])
    ap.add_argument("--start", help="投稿開始日 YYYY-MM-DD")
    ap.add_argument("--weekdays", help="投稿曜日 例: 1,2,3,4,5,6")
    ap.add_argument("--code", help="医院から届いた許可コード")
    ap.add_argument("--token", help="（代替）長期アクセストークンを直接指定")
    ap.add_argument("--user-id", help="（代替）Instagram ユーザーID")
    ap.add_argument("--no-test", action="store_true", help="テスト実行を起動しない")
    a = ap.parse_args()

    op = get_token.load_operator()
    for k in ("github_owner", "github_token", "template_repo"):
        if not op.get(k):
            sys.exit(f"config/operator.json の {k} が未設定です")

    # ---- 対話
    if not a.name:
        a.name = ask("医院名")
    specialties = [s.strip() for s in a.specialties.split(",")] if a.specialties else ask_multi("診療科（複数可）", SPECIALTIES, ["dental"])
    goals = [g.strip() for g in a.goals.split(",")] if a.goals else ask_multi("運用の目的（複数可）", GOALS, ["reach", "followers", "acquisition"])
    if a.services is None and not a.specialties:
        v = ask("提供サービスキー（例: whitening,orthodontics。空ならテンプレート既定）", "")
        a.services = [x.strip() for x in v.split(",") if x.strip()] if v else None
    elif a.services is not None:
        a.services = [x.strip() for x in a.services.split(",") if x.strip()]
    if a.hashtags is None and not a.specialties:
        a.hashtags = [x.strip() for x in ask("固定ハッシュタグ（カンマ区切り）", "").split(",") if x.strip()]
    elif a.hashtags:
        a.hashtags = [x.strip() for x in a.hashtags.split(",") if x.strip()]
    if not a.footer and not a.specialties:
        a.footer = ask("画像下の一行（住所・電話。空でも可）", "")

    # ---- トークン
    if a.token and a.user_id:
        token, user_id, username = a.token, a.user_id, "(指定)"
    else:
        code = a.code or ask("医院から届いた許可コード（python scripts/get_token.py --link で作ったリンクの先）")
        res = get_token.exchange(op, code)
        token, user_id, username = res["access_token"], res["user_id"], res.get("username")
        log(f"トークン取得: @{username} ({res.get('account_type')})")
        if res.get("account_type") not in ("BUSINESS", "MEDIA_CREATOR"):
            log("警告: プロアカウントではありません。投稿に失敗します。医院側で切り替えてから再度許可してもらってください")

    # ---- GitHub
    gh = GitHub(op["github_token"])
    owner = op["github_owner"]
    repo = a.repo or ("clinic-insta-" + re.sub(r"[^a-z0-9]+", "-", (username or a.name).lower()).strip("-") or "clinic")
    log(f"リポジトリを作成: {owner}/{repo}")
    gh.create_from_template(op["template_repo"], owner, repo, f"{a.name} Instagram 自動投稿")
    time.sleep(5)  # 生成直後は中身が揃うまで少し待つ

    log("Secrets を登録")
    secrets = {"IG_ACCESS_TOKEN": token, "IG_USER_ID": user_id}
    for k, v in (("CF_ACCOUNT_ID", op.get("cf_account_id")), ("CF_API_TOKEN", op.get("cf_api_token")),
                 ("ANTHROPIC_API_KEY", op.get("anthropic_api_key")), ("HF_TOKEN", op.get("hf_token"))):
        if v:
            secrets[k] = v
    for k, v in secrets.items():
        gh.put_secret(owner, repo, k, v)

    log("Actions の書き込み権限と GitHub Pages を有効化")
    gh.workflow_write(owner, repo)
    pages_url = gh.enable_pages(owner, repo)

    log("config/clinic.json を書き込み")
    cfg = build_config(a, specialties, goals)
    gh.put_file(owner, repo, "config/clinic.json", json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", f"設定: {a.name}")

    if not a.no_test:
        log("テスト実行（DRY_RUN）を起動")
        time.sleep(3)
        gh.dispatch(owner, repo, "daily-post.yml", {"dry_run": "true", "force": "true"})

    print("\n完了しました。")
    print(f"  リポジトリ : https://github.com/{owner}/{repo}")
    print(f"  Actions    : https://github.com/{owner}/{repo}/actions  （テスト結果はここ。Artifacts に画像が出ます）")
    print(f"  設定画面   : {pages_url}  （Pages の反映に数分かかります）")
    print("  本番投稿を始めるには: Actions → 「Instagram 毎日自動投稿」→ Run workflow（テスト実行なし・曜日無視あり）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
