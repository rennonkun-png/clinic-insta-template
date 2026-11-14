"""競合アカウントの公開情報を集めて比べる（自社の Instagram 接続をそのまま使う。外部サービスは使わない）。

Instagram の「ビジネスディスカバリー」機能で、ほかのビジネス／クリエイターアカウントの公開情報
（フォロワー数・投稿数・最近の投稿のいいね数・コメント数・種類・投稿日時）を読む。読むだけで、相手には何も通知されない。

使い方:
  config の "competitors": ["ユーザー名", ...] に比べたいアカウントを書く（@ は付けない）
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


def main() -> int:
    token = os.environ.get("IG_ACCESS_TOKEN", "").strip()
    user_id = os.environ.get("IG_USER_ID", "").strip()
    if not token or not user_id:
        log("IG_ACCESS_TOKEN / IG_USER_ID がないため、競合の比較は行いません")
        return 0
    if instagram.is_ig_login_token(token):
        log("この接続の種類（以前の Instagram ログイン）では、他のアカウントの公開情報を読めません")
        return 0
    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        names = sys.argv[2:]
    else:
        names = [str(x).lstrip("@") for x in (load_config().get("competitors") or [])]
    if not names:
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
    date = datetime.now(JST).strftime("%Y-%m-%d")
    if len(sys.argv) > 1 and sys.argv[1] == "--check":  # 試すだけのときは記録しない
        print(report_md(rows, date))
        return 0
    path = STATE_DIR / "competitors.json"
    hist = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    hist[date] = rows
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(hist, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    md = report_md(rows, date)
    (STATE_DIR / "competitors_report.md").write_text(md + "\n", encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
