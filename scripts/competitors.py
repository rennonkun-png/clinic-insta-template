"""競合アカウントの公開情報を集めて比べる（自社の Instagram 接続をそのまま使う。外部サービスは使わない）。

Instagram の「ビジネスディスカバリー」機能で、ほかのビジネス／クリエイターアカウントの公開情報
（フォロワー数・投稿数・最近の投稿のいいね数・コメント数・種類・投稿日時）を読む。読むだけで、相手には何も通知されない。

使い方:
  config の "competitors": ["ユーザー名", ...] に、ずっと比べ続けるアカウントを書く（@ は付けない）
  state/competitor_pool.json の "accounts" に、毎週の調査で見つけたアカウントが入る（Claude が毎週足し、入れ替える）
    読めなかったアカウント（個人アカウント・非公開・存在しない）は、ここで自動的に status: "unreadable" にして次から外す
  config の "competitor_hashtags": ["タグ名", ...] があれば、そのハッシュタグで今伸びている投稿（上位）も集める
    （アカウント名は Instagram が公開しないため、投稿の中身・形式・反応の数を見る。7日で30タグまでの決まりがある）
  python scripts/competitors.py            # state/competitors.json に記録し、state/competitors_report.md を作る
  python scripts/competitors.py --check a b  # 設定に関係なく、指定したアカウントを読めるか試す

必要: 環境変数 IG_ACCESS_TOKEN / IG_USER_ID（毎日の投稿と同じもの）
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import instagram  # noqa: E402
from common import STATE_DIR, load_config, log  # noqa: E402

JST = timezone(timedelta(hours=9))
FIELDS = ("business_discovery.username({u}){{username,name,followers_count,media_count,"
          "media.limit(30){{timestamp,media_type,media_product_type,like_count,comments_count,permalink,caption}}}}")


def fetch(user_id: str, token: str, username: str) -> dict:
    r = requests.get(f"{instagram._base(token)}/{user_id}", params={"fields": FIELDS.format(u=username), "access_token": token},
                     timeout=60)
    data = r.json()
    if "error" in data:
        raise RuntimeError(data["error"].get("message", str(data["error"])))
    return data.get("business_discovery", {})


POOL_PATH = STATE_DIR / "competitor_pool.json"


def load_pool() -> dict:
    return json.loads(POOL_PATH.read_text(encoding="utf-8")) if POOL_PATH.exists() else {"accounts": []}


def hashtag_top(user_id: str, token: str, tag: str, limit: int = 15) -> list[dict]:
    """ハッシュタグの「人気の投稿」を読む。"""
    base = instagram._base(token)
    r = requests.get(f"{base}/ig_hashtag_search", params={"user_id": user_id, "q": tag, "access_token": token}, timeout=60).json()
    if "error" in r:
        raise RuntimeError(r["error"].get("message", str(r["error"])))
    if not r.get("data"):
        return []
    hid = r["data"][0]["id"]
    m = requests.get(f"{base}/{hid}/top_media", params={
        "user_id": user_id, "access_token": token, "limit": 50,
        "fields": "id,caption,media_type,media_product_type,like_count,comments_count,permalink,timestamp"}, timeout=60).json()
    if "error" in m:
        raise RuntimeError(m["error"].get("message", str(m["error"])))
    items = sorted(m.get("data", []), key=lambda x: (x.get("like_count") or 0) + (x.get("comments_count") or 0), reverse=True)
    return [{"permalink": x.get("permalink"), "likes": x.get("like_count"), "comments": x.get("comments_count"),
             "type": x.get("media_product_type") or x.get("media_type"),
             "timestamp": x.get("timestamp"), "caption": (x.get("caption") or "").replace("\n", " ")[:120]} for x in items[:limit]]


def summarize(bd: dict) -> dict:
    media = (bd.get("media") or {}).get("data", [])
    now = datetime.now(timezone.utc)
    recent = [m for m in media if m.get("timestamp")]
    times = [datetime.strptime(m["timestamp"], "%Y-%m-%dT%H:%M:%S%z") for m in recent]
    days = max(1.0, (now - min(times)).total_seconds() / 86400) if times else 0
    likes = [m.get("like_count") or 0 for m in recent]
    comments = [m.get("comments_count") or 0 for m in recent]
    kinds = Counter((m.get("media_product_type") or "") + ("_CAROUSEL" if m.get("media_type") == "CAROUSEL_ALBUM" else "")
                    for m in recent)
    hours = Counter(t.astimezone(JST).hour for t in times)
    fol = bd.get("followers_count") or 0
    eng = (sum(likes) + sum(comments)) / len(recent) if recent else 0
    top = sorted(recent, key=lambda m: (m.get("like_count") or 0) + (m.get("comments_count") or 0), reverse=True)[:3]
    return {
        "username": bd.get("username"), "name": bd.get("name"), "followers": fol, "media_count": bd.get("media_count"),
        "posts_per_week": round(len(recent) / days * 7, 1) if days else 0,
        "avg_likes": round(sum(likes) / len(likes), 1) if likes else 0,
        "avg_comments": round(sum(comments) / len(comments), 1) if comments else 0,
        "engagement_rate": round(eng / fol * 100, 2) if fol else None,
        "reel_share": round(sum(v for k, v in kinds.items() if k.startswith("REELS")) / len(recent) * 100) if recent else 0,
        "carousel_share": round(sum(v for k, v in kinds.items() if k.endswith("_CAROUSEL")) / len(recent) * 100) if recent else 0,
        "top_hours_jst": [h for h, _ in hours.most_common(3)],
        "top_posts": [{"permalink": m.get("permalink"), "likes": m.get("like_count"), "comments": m.get("comments_count"),
                       "type": m.get("media_product_type"), "caption": (m.get("caption") or "").split("\n")[0][:60]} for m in top],
    }


def report_md(rows: list[dict], date: str) -> str:
    out = [f"# 競合アカウントの比較（{date} 時点・最近30投稿）", "",
           "| アカウント | フォロワー | 週の投稿数 | 平均いいね | 平均コメント | 反応率 | リールの割合 | よく投稿する時刻 |",
           "|---|---:|---:|---:|---:|---:|---:|---|"]
    for r in rows:
        if r.get("error"):
            out.append(f"| @{r['username']} | 読めませんでした（{r['error'][:40]}） | | | | | | |")
            continue
        er = "" if r["engagement_rate"] is None else f"{r['engagement_rate']}%"
        hrs = "・".join(f"{h}時" for h in r["top_hours_jst"])
        out.append(f"| @{r['username']} | {r['followers']:,} | {r['posts_per_week']} | {r['avg_likes']} | {r['avg_comments']} "
                   f"| {er} | {r['reel_share']}% | {hrs} |")
    out += ["", "反応率 = 1投稿あたりの（いいね＋コメント）÷ フォロワー数。保存数・再生数は、他人のアカウントでは公開されていないため比べられません。", ""]
    for r in rows:
        if r.get("error") or not r.get("top_posts"):
            continue
        out.append(f"## @{r['username']} の反応が多かった投稿")
        for p in r["top_posts"]:
            out.append(f"- いいね{p['likes']}・コメント{p['comments']}（{p['type']}）{p['caption']} … {p['permalink']}")
        out.append("")
    return "\n".join(out)


def hashtag_md(tag_rows: dict) -> str:
    if not tag_rows:
        return ""
    out = ["", "# ハッシュタグで今伸びている投稿（人気の投稿の上位）", ""]
    for t, items in tag_rows.items():
        out.append(f"## #{t}")
        if isinstance(items, str):
            out.append(f"- {items[:80]}")
        for p in items[:5] if isinstance(items, list) else []:
            out.append(f"- いいね{p['likes']}・コメント{p['comments']}（{p['type']}）{p['caption'][:60]} … {p['permalink']}")
        out.append("")
    return "\n".join(out)


def main() -> int:
    token = os.environ.get("IG_ACCESS_TOKEN", "").strip()
    user_id = os.environ.get("IG_USER_ID", "").strip()
    if not token or not user_id:
        log("IG_ACCESS_TOKEN / IG_USER_ID がないため、競合の比較は行いません")
        return 0
    if instagram.is_ig_login_token(token):
        log("この接続の種類（以前の Instagram ログイン）では、他のアカウントの公開情報を読めません")
        return 0
    check = len(sys.argv) > 1 and sys.argv[1] == "--check"
    cfg = load_config()
    pool = load_pool()
    tags: list[str] = []
    if check:
        names = [x.lstrip("@") for x in sys.argv[2:] if not x.startswith("#")]
        tags = [x.lstrip("#") for x in sys.argv[2:] if x.startswith("#")]
    else:
        names = [str(x).lstrip("@") for x in (cfg.get("competitors") or [])]
        names += [a["username"].lstrip("@") for a in pool.get("accounts", []) if a.get("status", "active") == "active"]
        names = list(dict.fromkeys(names))
        tags = [str(x).lstrip("#") for x in (cfg.get("competitor_hashtags") or [])][:10]
    if not names and not tags:
        log("config に competitors がないため、競合の比較は行いません")
        return 0
    rows = []
    for u in names:
        try:
            rows.append(summarize(fetch(user_id, token, u)))
            log(f"読めました: @{u}")
        except Exception as e:  # 個人アカウント・非公開・存在しない等
            rows.append({"username": u, "error": str(e)})
            log(f"読めませんでした: @{u}（{e}）")
    if all(r.get("error") for r in rows):  # 全部だめなら、接続にどの権限があるかを出す（トークンそのものは出さない）
        try:
            pr = requests.get(f"{instagram._base(token)}/me/permissions", params={"access_token": token}, timeout=30).json()
            granted = [x["permission"] for x in pr.get("data", []) if x.get("status") == "granted"]
            log(f"この接続で許可されている権限: {', '.join(granted) or pr}")
        except Exception as e:  # noqa: BLE001
            log(f"権限を確かめられませんでした: {e}")
    tag_rows: dict[str, list | str] = {}
    for t in tags:
        try:
            tag_rows[t] = hashtag_top(user_id, token, t)
            log(f"ハッシュタグを読めました: #{t}（{len(tag_rows[t])} 件）")
        except Exception as e:  # noqa: BLE001
            tag_rows[t] = f"読めませんでした: {e}"
            log(f"ハッシュタグを読めませんでした: #{t}（{e}）")
    date = datetime.now(JST).strftime("%Y-%m-%d")
    md = report_md(rows, date) + hashtag_md(tag_rows)
    if check:  # 試すだけのときは記録しない
        print(md)
        return 0
    # 読めなかった、調査で見つけたアカウントは次から外す（ずっと比べる分は外さない）
    bad = {r["username"] for r in rows if r.get("error")}
    for a in pool.get("accounts", []):
        if a["username"].lstrip("@") in bad and a.get("status", "active") == "active":
            a["status"] = "unreadable"
            a["checked"] = date
    if pool.get("accounts"):
        POOL_PATH.write_text(json.dumps(pool, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if tag_rows:
        hp = STATE_DIR / "hashtag_top.json"
        hh = json.loads(hp.read_text(encoding="utf-8")) if hp.exists() else {}
        hh[date] = tag_rows
        for k in sorted(hh)[:-12]:  # 12週分だけ残す
            hh.pop(k)
        hp.write_text(json.dumps(hh, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    path = STATE_DIR / "competitors.json"
    hist = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    hist[date] = rows
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(hist, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (STATE_DIR / "competitors_report.md").write_text(md + "\n", encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
