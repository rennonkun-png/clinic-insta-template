"""まとめ投稿: state/batch_queue.json の今日の分（または NOW=1 で全部）を、順番に投稿する。

batch_queue.json の形: {"date": "2026-11-15", "items": [{"id": "t1115-1", "format": "carousel"}, ...], "gap_sec": 60}
投稿が終わった分は items から消して記録する（途中で止まっても、次の回は続きから）。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
Q = ROOT / "state" / "batch_queue.json"
JST = timezone(timedelta(hours=9))


def git(*a: str) -> None:
    subprocess.run(["git", *a], cwd=ROOT, check=False)


def main() -> int:
    if not Q.exists():
        print("[batch] 予約はありません")
        return 0
    q = json.loads(Q.read_text(encoding="utf-8"))
    today = datetime.now(JST).date().isoformat()
    if os.environ.get("NOW") != "1" and q.get("date") != today:
        print(f"[batch] 今日（{today}）の予約はありません（予約日 {q.get('date')}）")
        return 0
    items = list(q.get("items", []))
    gap = int(q.get("gap_sec", 60))
    failed = []
    for n, it in enumerate(items):
        env = dict(os.environ, POST_ID=it["id"], FORMAT=it.get("format", ""), FORCE="1", DRY_RUN="0")
        print(f"[batch] {n + 1}/{len(items)} 本目: {it['id']}（{it.get('format') or '自動'}）", flush=True)
        r = subprocess.run([sys.executable, "scripts/main.py"], cwd=ROOT, env=env)
        if r.returncode != 0:
            failed.append(it)
            print(f"[batch] 失敗しました: {it['id']}", flush=True)
        q["items"] = [x for x in q["items"] if x["id"] != it["id"]] if r.returncode == 0 else q["items"]
        Q.write_text(json.dumps(q, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        git("add", "state")
        git("-c", "user.name=instapost-bot", "-c", "user.email=instapost-bot@users.noreply.github.com",
            "commit", "-q", "-m", f"まとめ投稿 {it['id']}")
        git("pull", "--rebase", "-q")
        git("push", "-q")
        if n < len(items) - 1:
            time.sleep(gap)
    if failed:
        print(f"[batch] 失敗: {[x['id'] for x in failed]}（予約に残しています）")
        return 1
    print("[batch] 全部出しました")
    return 0


if __name__ == "__main__":
    sys.exit(main())
