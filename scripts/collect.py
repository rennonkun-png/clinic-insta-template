"""毎晩の記録: Instagram の数字を取り、分析サイト（analytics/site）が読む形（analytics/SCHEMA.md）で書き足す。

Claude は使わない。GitHub Actions から毎晩1回動かす。前日分（日本時間）を記録する。
取れなかった数字は null にして、記録そのものは止めない。

使い方:
  python scripts/collect.py --out <data フォルダ> --account genova [--name GENOVA] [--kind 自社]
必要: 環境変数 IG_ACCESS_TOKEN / IG_USER_ID
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import instagram  # noqa: E402

JST = timezone(timedelta(hours=9))
METRICS = ["reach", "views", "likes", "comments", "saves", "shares", "follows", "profile_visits",
           "reel_avg_watch_sec", "reel_skip_rate"]
KEEP_DAYS = 90  # 投稿日からこの日数は、投稿ごとの数字を毎晩記録する


def log(m: str) -> None:
    print(f"[collect] {m}", flush=True)


class Api:
    def __init__(self, token: str, user_id: str):
        self.t, self.uid, self.base = token, user_id, instagram._base(token)

    def get(self, path: str, **params) -> dict:
        params["access_token"] = self.t
        r = requests.get(f"{self.base}/{path}", params=params, timeout=60)
        d = r.json()
        if "error" in d:
            raise RuntimeError(d["error"].get("message", str(d["error"])))
        return d


def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


def save(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


# ------------------------------------------------------------------ アカウントの日ごとの数字
def account_day(api: Api, day: date) -> dict:
    since = int(datetime(day.year, day.month, day.day, tzinfo=JST).timestamp())
    until = min(since + 86400, int(datetime.now(JST).timestamp()) - 60)  # 今日の分は「今」まで
    row = {"date": day.isoformat()}

    def total(metric: str, **extra):
        # 今日の途中の分は、期間の指定によって空で返ることがあるので、指定のしかたを変えて取り直す
        last = None
        for rng in ({"since": since, "until": until}, {"since": since, "until": since + 86400}, {}):
            try:
                d = api.get(f"{api.uid}/insights", metric=metric, period="day", metric_type="total_value", **rng, **extra)
                if d.get("data"):
                    return d["data"][0]
            except Exception as e:  # noqa: BLE001
                last = e
        log(f"{metric} を取れませんでした: {last or '空でした'}")
        return None

    for key, metric in (("reach", "reach"), ("views", "views"), ("profile_views", "profile_views"),
                        ("website_clicks", "website_clicks"), ("accounts_engaged", "accounts_engaged"),
                        ("total_interactions", "total_interactions"), ("likes", "likes"),
                        ("comments", "comments"), ("saves", "saves"), ("shares", "shares")):
        d = total(metric)
        row[key] = ((d or {}).get("total_value") or {}).get("value") if d else None
    d = total("follows_and_unfollows", breakdown="follow_type")
    row["follows_new"] = row["unfollows"] = None
    if d:
        for b in ((d.get("total_value") or {}).get("breakdowns") or [{}])[0].get("results", []):
            kind = (b.get("dimension_values") or [""])[0]
            if kind == "FOLLOWER":
                row["follows_new"] = b.get("value")
            elif kind == "NON_FOLLOWER":
                row["unfollows"] = b.get("value")
    try:
        row["followers"] = api.get(api.uid, fields="followers_count").get("followers_count")
    except Exception as e:  # noqa: BLE001
        log(f"フォロワー数を取れませんでした: {e}")
        row["followers"] = None
    return row


# ------------------------------------------------------------------ 投稿
def list_media(api: Api, oldest: date) -> list[dict]:
    out, after = [], None
    for _ in range(10):
        params = {"fields": "id,timestamp,media_type,media_product_type,permalink,caption", "limit": 50}
        if after:
            params["after"] = after
        d = api.get(f"{api.uid}/media", **params)
        for m in d.get("data", []):
            ts = datetime.strptime(m["timestamp"], "%Y-%m-%dT%H:%M:%S%z").astimezone(JST)
            if ts.date() < oldest:
                return out
            m["_ts"] = ts
            out.append(m)
        after = (d.get("paging") or {}).get("cursors", {}).get("after")
        if not (d.get("paging") or {}).get("next"):
            break
    return out


def media_values(api: Api, m: dict) -> list:
    reel = m.get("media_product_type") == "REELS"
    names = ["reach", "views", "likes", "comments", "saved", "shares", "follows", "profile_visits"]
    if reel:
        names.append("ig_reels_avg_watch_time")
    got = {}
    try:
        d = api.get(f"{m['id']}/insights", metric=",".join(names))
        got = {x["name"]: (x.get("values") or [{}])[0].get("value", (x.get("total_value") or {}).get("value"))
               for x in d.get("data", [])}
    except Exception:  # noqa: BLE001  まとめて取れないときは1つずつ
        for nm in names:
            try:
                d = api.get(f"{m['id']}/insights", metric=nm)
                x = d["data"][0]
                got[nm] = (x.get("values") or [{}])[0].get("value", (x.get("total_value") or {}).get("value"))
            except Exception:  # noqa: BLE001
                got[nm] = None
    watch = got.get("ig_reels_avg_watch_time")
    return [got.get("reach"), got.get("views"), got.get("likes"), got.get("comments"), got.get("saved"),
            got.get("shares"), got.get("follows"), got.get("profile_visits"),
            round(watch / 1000, 1) if isinstance(watch, (int, float)) else None, None]


FORMAT = {"REELS": "リール", "CAROUSEL_ALBUM": "カルーセル", "IMAGE": "画像", "VIDEO": "リール"}


def post_meta(m: dict, posted_map: dict, content_map: dict) -> dict:
    ts = m["_ts"]
    info = posted_map.get(m["id"], {})
    c = content_map.get(info.get("id", ""), {})
    fmt = "リール" if m.get("media_product_type") == "REELS" else FORMAT.get(m.get("media_type"), "画像")
    cap = (m.get("caption") or "").replace("\n", " ")
    return {"id": m["id"], "date": ts.date().isoformat(), "time": ts.strftime("%H:%M"), "permalink": m.get("permalink"),
            "format": fmt, "reel_style": c.get("reel_style") if fmt == "リール" else None,
            "topic": c.get("topic") or c.get("category") or info.get("category"),
            "title": c.get("title") or cap[:40], "caption_head": cap[:100], "thumbnail_url": None}


# ------------------------------------------------------------------ フォロワーの属性（週1回）
def audience(api: Api, day: date) -> dict | None:
    snap = {"date": day.isoformat(), "followers": None, "gender_age": [], "cities": [], "regions": [], "countries": [],
            "online_hours": [[0] * 24 for _ in range(7)]}
    for bd, key in (("age,gender", "gender_age"), ("city", "cities"), ("country", "countries")):
        try:
            d = api.get(f"{api.uid}/insights", metric="follower_demographics", period="lifetime",
                        metric_type="total_value", breakdown=bd, timeframe="this_month")
            res = ((d["data"][0].get("total_value") or {}).get("breakdowns") or [{}])[0].get("results", [])
            for r in res:
                dv = r.get("dimension_values") or []
                if key == "gender_age" and len(dv) >= 2:
                    snap[key].append({"age": dv[0], "gender": dv[1], "count": r.get("value")})
                elif dv:
                    snap[key].append({"name": dv[0], "count": r.get("value")})
        except Exception as e:  # noqa: BLE001
            log(f"属性（{bd}）を取れませんでした: {e}")
    try:
        d = api.get(f"{api.uid}/insights", metric="online_followers", period="lifetime")
        for v in d["data"][0].get("values", []):
            dt = datetime.strptime(v["end_time"], "%Y-%m-%dT%H:%M:%S%z").astimezone(JST)
            for h, cnt in (v.get("value") or {}).items():
                hh = (int(h) + 17) % 24  # Instagram は太平洋時間の時刻で返すので日本時間に直す（+17時間）
                snap["online_hours"][dt.weekday()][hh] = cnt
    except Exception as e:  # noqa: BLE001
        log(f"オンラインの時間帯を取れませんでした: {e}")
    try:
        snap["followers"] = api.get(api.uid, fields="followers_count").get("followers_count")
    except Exception:  # noqa: BLE001
        pass
    return snap


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="分析サイトの data フォルダ")
    ap.add_argument("--account", required=True)
    ap.add_argument("--name", default="")
    ap.add_argument("--kind", default="自社")
    ap.add_argument("--day", default="", help="記録する日（既定は前日）")
    a = ap.parse_args()
    token, uid = os.environ.get("IG_ACCESS_TOKEN", "").strip(), os.environ.get("IG_USER_ID", "").strip()
    if not token or not uid:
        sys.exit("IG_ACCESS_TOKEN / IG_USER_ID がありません")
    api = Api(token, uid)
    day = date.fromisoformat(a.day) if a.day else (datetime.now(JST) - timedelta(days=1)).date()
    out = Path(a.out)
    acc_dir = out / a.account
    root = Path(__file__).resolve().parent.parent

    # 1) アカウントの日ごとの数字
    daily = load(acc_dir / "daily.json", {"days": []})
    daily["days"] = [d for d in daily["days"] if d["date"] != day.isoformat()] + [account_day(api, day)]
    daily["days"].sort(key=lambda d: d["date"])
    save(acc_dir / "daily.json", daily)

    # 2) 投稿の一覧と、投稿ごとの累計
    posted = load(root / "state" / "posted.json", {"posted": []}).get("posted", [])
    posted_map = {str(p.get("media_id")): p for p in posted if p.get("media_id")}
    content_map = {}
    for f in (root / "content").glob("*.json"):
        for p in load(f, []) if isinstance(load(f, []), list) else []:
            content_map[f"{p.get('category') or f.stem}:{p.get('id')}"] = p
            content_map[f"{f.stem}:{p.get('id')}"] = p
    media = list_media(api, day - timedelta(days=KEEP_DAYS))
    posts = load(acc_dir / "posts.json", {"posts": []})
    known = {p["id"]: p for p in posts["posts"]}
    for m in media:
        known[m["id"]] = {**known.get(m["id"], {}), **post_meta(m, posted_map, content_map)}
    posts["posts"] = sorted(known.values(), key=lambda p: (p["date"], p["time"]))
    save(acc_dir / "posts.json", posts)
    month = day.strftime("%Y-%m")
    pd_path = acc_dir / "post_daily" / f"{month}.json"
    pdj = load(pd_path, {"metrics": METRICS, "rows": []})
    pdj["rows"] = [r for r in pdj["rows"] if r[1] != day.isoformat()]
    for m in media:
        pdj["rows"].append([m["id"], day.isoformat()] + media_values(api, m))
    save(pd_path, pdj)
    log(f"{day} の記録: 投稿 {len(media)} 本")

    # 3) フォロワーの属性（月曜、または記録がまだ無いとき）
    aud = load(acc_dir / "audience.json", {"snapshots": []})
    if day.weekday() == 0 or not aud["snapshots"]:
        snap = audience(api, day)
        aud["snapshots"] = [s for s in aud["snapshots"] if s["date"] != day.isoformat()] + [snap]
        save(acc_dir / "audience.json", aud)

    # 4) 競合（state/competitors.json の最新を、サイトの形に写す）
    comp_hist = load(root / "state" / "competitors.json", {})
    if comp_hist:
        cj = load(acc_dir / "competitors.json", {"competitors": [], "snapshots": []})
        ids = {c["username"]: c["id"] for c in cj["competitors"]}
        for dt, rows in comp_hist.items():
            for r in rows:
                if r.get("error"):
                    continue
                u = r["username"]
                if u not in ids:
                    ids[u] = f"c{len(ids) + 1}"
                    cj["competitors"].append({"id": ids[u], "name": r.get("name") or u, "username": u, "is_self": False})
                cj["snapshots"] = [s for s in cj["snapshots"] if not (s["date"] == dt and s["competitor_id"] == ids[u])]
                cj["snapshots"].append({"date": dt, "competitor_id": ids[u], "followers": r.get("followers"),
                                        "media_count": r.get("media_count"), "posts_per_week": r.get("posts_per_week"),
                                        "avg_likes": r.get("avg_likes"), "avg_comments": r.get("avg_comments"),
                                        "engagement_rate": r.get("engagement_rate"), "reel_share": r.get("reel_share"),
                                        "top_posts": r.get("top_posts", [])})
        save(acc_dir / "competitors.json", cj)
    if not (acc_dir / "review.json").exists():
        save(acc_dir / "review.json", {"items": []})

    # 5) アカウントの一覧
    accs = load(out / "accounts.json", {"schema_version": 1, "accounts": []})
    accs["accounts"] = [x for x in accs["accounts"] if not x.get("sample")]
    me = next((x for x in accs["accounts"] if x["id"] == a.account), None)
    try:
        uname = api.get(uid, fields="username").get("username")
    except Exception:  # noqa: BLE001
        uname = me.get("username") if me else ""
    months = sorted({p.stem for p in (acc_dir / "post_daily").glob("*.json")})
    entry = {"id": a.account, "name": a.name or (me or {}).get("name") or a.account, "username": uname, "kind": a.kind,
             "record_start": (me or {}).get("record_start") or daily["days"][0]["date"],
             "last_date": daily["days"][-1]["date"], "post_daily_months": months, "sample": False}
    accs["accounts"] = [x for x in accs["accounts"] if x["id"] != a.account] + [entry]
    accs["generated_at"] = datetime.now(JST).isoformat(timespec="seconds")
    save(out / "accounts.json", accs)
    log("記録しました")
    return 0


if __name__ == "__main__":
    sys.exit(main())
