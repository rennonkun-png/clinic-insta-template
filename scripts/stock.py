"""投稿ネタの残りを数える（自動制作を始めるかどうかの判断に使う）。

使い方:
  python -X utf8 scripts/stock.py                      # config/clinic.json と state/posted.json を見る
  python -X utf8 scripts/stock.py --root <リポジトリ>   # 別の場所に clone したリポジトリを見る
  python -X utf8 scripts/stock.py --threshold 14        # 残りがこの本数以下なら終了コード 2

出力: まだ出していない本数、使い切る日（投稿曜日・開始日・スキップ日を反映）、補充が必要か。
Claude を使わないので、何度動かしても無料。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    ap.add_argument("--config", default="")
    ap.add_argument("--threshold", type=int, default=14)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    root = Path(a.root)
    os.environ["CLINIC_CONFIG"] = a.config or str(root / "config" / "clinic.json")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import common  # CLINIC_CONFIG を決めてから読み込む

    common.ROOT = root
    common.CONTENT_DIR = root / "content"
    cfg = common.load_config()
    posts = common.load_posts(cfg, {})
    state = common.load_json(root / "state" / "posted.json", {"posted": []}) or {"posted": []}
    posted = {h["id"] for h in state.get("posted", [])}
    left = [p for p in posts if p["id"] not in posted and not p.get("date")]

    # 使い切る日: 今日から、投稿する日を残りの本数だけ数える
    d, n, runout = common.today_jst(), 0, None
    for _ in range(3650):
        ok, _why = common.should_post_today(cfg, d)
        if ok:
            n += 1
            if n == len(left):
                runout = d
                break
        d += timedelta(days=1)
    need = len(left) <= a.threshold
    res = {"total": len(posts), "posted": len(posted), "left": len(left),
           "runout": runout.isoformat() if runout else None, "threshold": a.threshold, "need_refill": need}
    if a.json:
        print(json.dumps(res, ensure_ascii=False))
    else:
        print(f"ネタ {res['total']} 本のうち、まだ出していないのは {res['left']} 本")
        print(f"使い切る日: {res['runout'] or '（残りなし）'}")
        print("補充が必要です" if need else f"補充はまだ不要です（{a.threshold} 本以下になったら補充）")
    return 2 if need else 0


if __name__ == "__main__":
    sys.exit(main())
