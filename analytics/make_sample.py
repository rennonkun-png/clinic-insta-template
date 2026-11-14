"""分析サイトの試作データを作る（すべて乱数。本物の数字ではない）。

使い方:  python analytics/make_sample.py
出力先:  analytics/site/data/ （SCHEMA.md の形）

本物の記録プログラムができたら、このスクリプトは使わない。
"""
from __future__ import annotations

import json
import math
import random
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent / "site" / "data"
JST = timezone(timedelta(hours=9))
TODAY = datetime.now(JST).date()
LAST = TODAY - timedelta(days=1)          # 毎晩、前日分までを記録する想定
RNG = random.Random(20261115)

POST_METRICS = ["reach", "views", "likes", "comments", "saves", "shares", "follows",
                "profile_visits", "reel_avg_watch_sec", "reel_skip_rate"]

ACCOUNTS = [
    {
        "id": "genova", "name": "GENOVA（サンプルデータ）", "username": "sample_genova",
        "kind": "自社", "days": 90, "posts": 60, "followers0": 820, "base_reach": 140,
        "topics": ["Googleマップ・MEO", "ホームページ", "口コミ", "Instagram運用", "広告", "医療広告ガイドライン"],
        "competitors": [("c1", "サンプル競合A", "sample_comp_a"), ("c2", "サンプル競合B", "sample_comp_b"),
                        ("c3", "サンプル競合C", "sample_comp_c")],
    },
    {
        "id": "sample_dental", "name": "サンプル歯科クリニック（サンプルデータ）", "username": "sample_dental",
        "kind": "医院", "days": 60, "posts": 36, "followers0": 310, "base_reach": 60,
        "topics": ["予防・歯みがき", "むし歯", "歯周病", "小児歯科", "矯正", "医院の紹介", "季節の健康"],
        "competitors": [("d1", "サンプル近隣医院A", "sample_near_a"), ("d2", "サンプル近隣医院B", "sample_near_b"),
                        ("d3", "サンプル近隣医院C", "sample_near_c")],
    },
]
FORMATS = [("リール", 0.42), ("カルーセル", 0.43), ("画像", 0.15)]
REEL_STYLES = ["screen", "telop", "photo"]
HOURS = [7, 8, 12, 12, 13, 18, 19, 19, 20, 20, 21, 21, 22]


def iso(d: date) -> str:
    return d.isoformat()


def pick(weighted):
    r = RNG.random()
    for v, w in weighted:
        r -= w
        if r <= 0:
            return v
    return weighted[-1][0]


def write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def make_account(acc: dict) -> dict:
    start = LAST - timedelta(days=acc["days"] - 1)
    days = [start + timedelta(days=i) for i in range(acc["days"])]
    base = OUT / acc["id"]

    # ---- 投稿 ----
    post_days = sorted(RNG.sample(range(acc["days"] - 1), acc["posts"]))
    posts, curves = [], {}
    for n, di in enumerate(post_days, 1):
        d = days[di]
        fmt = pick(FORMATS)
        topic = RNG.choice(acc["topics"])
        hour = RNG.choice(HOURS)
        pid = f"{acc['id']}_{d.strftime('%Y%m%d')}_{n:02d}"
        posts.append({
            "id": pid, "date": iso(d), "time": f"{hour:02d}:{RNG.choice([0, 15, 30]):02d}",
            "permalink": None, "format": fmt,
            "reel_style": RNG.choice(REEL_STYLES) if fmt == "リール" else None,
            "topic": topic,
            "title": f"サンプル投稿{n}：{topic}の話",
            "caption_head": f"これはサンプルの投稿文です（{topic}）。本物の投稿ではありません。",
            "thumbnail_url": None,
        })
        # 最終的な累計（もっともらしい比率で）
        mult = {"リール": RNG.lognormvariate(math.log(1400), 0.6), "カルーセル": RNG.lognormvariate(math.log(650), 0.5),
                "画像": RNG.lognormvariate(math.log(380), 0.45)}[fmt]
        scale = acc["followers0"] / 820
        reach = mult * scale * (1 + 0.004 * di)
        final = {
            "reach": reach, "views": reach * RNG.uniform(1.25, 2.1),
            "likes": reach * RNG.uniform(0.02, 0.06), "comments": reach * RNG.uniform(0.001, 0.005),
            "saves": reach * (RNG.uniform(0.02, 0.05) if fmt == "カルーセル" else RNG.uniform(0.005, 0.02)),
            "shares": reach * RNG.uniform(0.004, 0.018), "follows": reach * RNG.uniform(0.002, 0.009),
            "profile_visits": reach * RNG.uniform(0.01, 0.03),
        }
        tau = RNG.uniform(3, 7) if fmt == "リール" else RNG.uniform(1, 2.5)
        watch = round(RNG.uniform(3.5, 12.0), 1) if fmt == "リール" else None
        skip = round(RNG.uniform(38, 74), 1) if fmt == "リール" else None
        curves[pid] = (di, final, tau, watch, skip)

    # 投稿×日の累計（投稿日から記録の最終日まで）
    by_month: dict[str, list] = {}
    inc_by_day = [{k: 0 for k in POST_METRICS[:8]} for _ in days]
    for pid, (di, final, tau, watch, skip) in curves.items():
        prev = {k: 0 for k in final}
        for j in range(di, len(days)):
            age = j - di + 1
            frac = 1 - math.exp(-age / tau)
            row = [pid, iso(days[j])]
            for k in POST_METRICS[:8]:
                v = max(prev[k], int(round(final[k] * frac)))
                inc_by_day[j][k] += v - prev[k]
                prev[k] = v
                row.append(v)
            if watch is not None:
                row += [round(watch + RNG.uniform(-0.3, 0.3), 1), round(skip + RNG.uniform(-1, 1), 1)]
            else:
                row += [None, None]
            by_month.setdefault(days[j].strftime("%Y-%m"), []).append(row)
    for m, rows in by_month.items():
        write(base / "post_daily" / f"{m}.json", {"metrics": POST_METRICS, "rows": rows})
    write(base / "posts.json", {"posts": posts})

    # ---- アカウントの日ごと ----
    daily, followers = [], acc["followers0"]
    for i, d in enumerate(days):
        inc = inc_by_day[i]
        wk = 0.85 if d.weekday() >= 5 else 1.0
        reach = int(acc["base_reach"] * wk * RNG.uniform(0.7, 1.3) + inc["reach"] * 0.85)
        views = int(reach * RNG.uniform(1.6, 2.4))
        new = int(RNG.uniform(0, 3) * acc["followers0"] / 820 + inc["follows"])
        lost = int(RNG.uniform(0, 2.2) * acc["followers0"] / 820)
        followers += new - lost
        likes, comments, saves, shares = inc["likes"], inc["comments"], inc["saves"], inc["shares"]
        daily.append({
            "date": iso(d), "followers": followers, "follows_new": new, "unfollows": lost,
            "reach": reach, "views": views,
            "profile_views": int(inc["profile_visits"] + RNG.uniform(3, 15) * acc["followers0"] / 820),
            "website_clicks": int(RNG.uniform(0, 4) + inc["profile_visits"] * 0.12),
            "accounts_engaged": int((likes + comments + saves + shares) * 0.8 + RNG.uniform(0, 5)),
            "total_interactions": likes + comments + saves + shares,
            "likes": likes, "comments": comments, "saves": saves, "shares": shares,
        })
    write(base / "daily.json", {"days": daily})

    # ---- オーディエンス（週1回のスナップショット） ----
    snaps = []
    for w in range(3):
        d = LAST - timedelta(days=7 * (2 - w))
        total = next(x["followers"] for x in daily if x["date"] == iso(d))
        ages = ["13-17", "18-24", "25-34", "35-44", "45-54", "55-64", "65+"]
        wts = [0.01, 0.10, 0.31, 0.30, 0.17, 0.08, 0.03] if acc["kind"] == "自社" else [0.02, 0.09, 0.26, 0.30, 0.18, 0.10, 0.05]
        female = 0.58 if acc["kind"] == "自社" else 0.71
        ga = []
        for a, wv in zip(ages, wts):
            n = total * wv * RNG.uniform(0.9, 1.1)
            ga.append({"age": a, "gender": "F", "count": int(n * female)})
            ga.append({"age": a, "gender": "M", "count": int(n * (1 - female) * 0.97)})
            ga.append({"age": a, "gender": "U", "count": int(n * 0.01)})
        cities = ["サンプル市A", "サンプル市B", "サンプル市C", "サンプル市D", "サンプル市E", "サンプル市F", "その他の市区町村"]
        cw = [0.22, 0.14, 0.11, 0.08, 0.06, 0.05, 0.34]
        regions = ["東京都", "神奈川県", "大阪府", "埼玉県", "愛知県", "福岡県", "その他"]
        rw = [0.31, 0.12, 0.10, 0.07, 0.06, 0.05, 0.29]
        online = []
        for wd in range(7):
            row = []
            for h in range(24):
                lvl = 0.05 + 0.5 * math.exp(-((h - 12.5) ** 2) / 2) + 0.9 * math.exp(-((h - 21) ** 2) / 4) + 0.3 * math.exp(-((h - 8) ** 2) / 2)
                lvl *= 1.1 if wd >= 5 else 1.0
                row.append(int(total * 0.35 * lvl * RNG.uniform(0.9, 1.1)))
            online.append(row)
        snaps.append({
            "date": iso(d), "followers": total, "gender_age": ga,
            "cities": [{"name": c, "count": int(total * x * RNG.uniform(0.9, 1.1))} for c, x in zip(cities, cw)],
            "regions": [{"name": c, "count": int(total * x * RNG.uniform(0.9, 1.1))} for c, x in zip(regions, rw)],
            "countries": [{"name": "日本", "count": int(total * 0.97)}, {"name": "その他", "count": int(total * 0.03)}],
            "online_hours": online,
        })
    write(base / "audience.json", {"snapshots": snaps})

    # ---- 競合（週1回） ----
    comps = [{"id": cid, "name": nm, "username": un, "is_self": False} for cid, nm, un in acc["competitors"]]
    comps.insert(0, {"id": "self", "name": acc["name"], "username": acc["username"], "is_self": True})
    snaps = []
    weeks = acc["days"] // 7
    params = {c["id"]: (RNG.uniform(0.6, 4.0) * acc["followers0"], RNG.uniform(1.5, 5), RNG.uniform(0.01, 0.045), RNG.uniform(0.2, 0.7))
              for c in comps}
    for w in range(weeks + 1):
        d = LAST - timedelta(days=7 * (weeks - w))
        if d < start:
            continue
        for c in comps:
            f0, ppw, er, rs = params[c["id"]]
            if c["is_self"]:
                fol = next(x["followers"] for x in daily if x["date"] == iso(d))
                ppw_v = round(acc["posts"] / acc["days"] * 7 * RNG.uniform(0.8, 1.2), 1)
            else:
                fol = int(f0 * (1 + 0.003 * w) + RNG.uniform(-5, 5))
                ppw_v = round(ppw * RNG.uniform(0.7, 1.3), 1)
            al = round(fol * er * RNG.uniform(0.8, 1.2), 1)
            ac = round(al * RNG.uniform(0.03, 0.08), 1)
            tops = []
            for k in range(3):
                pd = d - timedelta(days=RNG.randint(0, 27))
                mt = RNG.choice(["リール", "カルーセル", "画像"])
                lk = int(al * RNG.uniform(1.4, 3.5))
                tops.append({"date": iso(pd), "format": mt, "permalink": None,
                             "caption_head": f"{c['name']}のサンプル投稿{k + 1}（本物ではありません）",
                             "likes": lk, "comments": int(lk * RNG.uniform(0.02, 0.08))})
            tops.sort(key=lambda x: -x["likes"])
            snaps.append({"date": iso(d), "competitor_id": c["id"], "followers": fol,
                          "media_count": int(120 + w * ppw_v + params[c["id"]][1] * 30),
                          "posts_per_week": ppw_v, "avg_likes": al, "avg_comments": ac,
                          "engagement_rate": round((al + ac) / max(fol, 1) * 100, 2),
                          "reel_share": round(min(0.95, rs * RNG.uniform(0.85, 1.15)) * 100, 1),
                          "top_posts": tops})
    write(base / "competitors.json", {"competitors": comps, "snapshots": snaps})

    # ---- 確認待ち（形だけ） ----
    write(base / "review.json", {"items": [
        {"id": f"{acc['id']}_review_01", "created_at": f"{iso(LAST)}T21:00:00+09:00",
         "scheduled_for": f"{iso(TODAY + timedelta(days=1))}T19:00:00+09:00", "format": "カルーセル",
         "reel_style": None, "topic": acc["topics"][0], "title": "サンプルの確認待ち投稿",
         "caption": "これはサンプルです。", "media_urls": [], "status": "pending",
         "quality_notes": ["サンプルの指摘です"], "decided_by": None, "decided_at": None, "comment": None},
    ]})

    return {"id": acc["id"], "name": acc["name"], "username": acc["username"], "kind": acc["kind"],
            "record_start": iso(start), "last_date": iso(LAST),
            "post_daily_months": sorted(by_month), "sample": True}


def main() -> None:
    entries = [make_account(a) for a in ACCOUNTS]
    write(OUT / "accounts.json", {"generated_at": datetime.now(JST).isoformat(timespec="seconds"),
                                  "schema_version": 1, "accounts": entries})
    print("試作データを書き出しました:", OUT)


if __name__ == "__main__":
    main()
