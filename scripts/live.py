"""最新の数字（ほぼリアルタイム）: 今日ここまでのアカウントの数字と、投稿ごとの今の累計を取り、live.json に書く。

GitHub Actions から5分おきに動かす。Claude は使わない。
- 通常（5分おき）: アカウントの今日の数字 ＋ 直近 --recent 本の投稿
- --all（30分おき）: 投稿から90日以内の全投稿
Instagram への問い合わせ回数を抑えるため、取らなかった投稿は前回の値を残す。

使い方: python scripts/live.py --out live.json [--recent 3] [--all]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect  # noqa: E402

JST = timezone(timedelta(hours=9))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--recent", type=int, default=3)
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    token, uid = os.environ.get("IG_ACCESS_TOKEN", "").strip(), os.environ.get("IG_USER_ID", "").strip()
    if not token or not uid:
        sys.exit("IG_ACCESS_TOKEN / IG_USER_ID がありません")
    api = collect.Api(token, uid)
    now = datetime.now(JST)
    out = Path(a.out)
    prev = collect.load(out, {})

    # アカウント: 今日 0:00 から今までの合計（Instagram 側の集計の遅れはそのまま）
    today = now.date()
    acc = collect.account_day(api, today)
    acc["date"] = today.isoformat()

    media = collect.list_media(api, today - timedelta(days=collect.KEEP_DAYS))
    targets = media if a.all else media[: a.recent]
    posts = dict(prev.get("posts") or {})
    for m in targets:
        vals = collect.media_values(api, m)
        posts[m["id"]] = {"values": vals, "updated_at": now.isoformat(timespec="seconds"),
                          "date": m["_ts"].date().isoformat(), "time": m["_ts"].strftime("%H:%M"),
                          "permalink": m.get("permalink"),
                          "format": "リール" if m.get("media_product_type") == "REELS" else
                          collect.FORMAT.get(m.get("media_type"), "画像"),
                          "caption_head": (m.get("caption") or "").replace("\n", " ")[:60]}
    keep = {m["id"] for m in media}
    posts = {k: v for k, v in posts.items() if k in keep}
    data = {"updated_at": now.isoformat(timespec="seconds"), "mode": "all" if a.all else f"recent{a.recent}",
            "metrics": collect.METRICS, "account_today": acc, "posts": posts}
    collect.save(out, data)
    print(f"[live] {now:%H:%M} 更新: 投稿 {len(targets)} 本を取り直しました（記録中 {len(posts)} 本）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
