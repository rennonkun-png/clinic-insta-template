"""手動投稿モード: 数日分の投稿（画像・カルーセル・リール動画・キャプション）をまとめて生成する。

Meta アプリの準備ができるまでの間、または自動投稿を使わない医院向け。
本番（main.py）と同じネタ選び・同じデザイン・同じキャプションで、日付ごとのフォルダに出力し、
output/manual/index.html にまとめる（画像を保存 → キャプションをコピー → Instagram や Meta Business Suite で投稿）。

  python scripts/manual_batch.py                 # 今日から 7 日分
  python scripts/manual_batch.py --days 14       # 14 日分
  python scripts/manual_batch.py --start 2026-11-10 --days 7
  python scripts/manual_batch.py --format image  # 形式を固定（image / carousel / reel）

投稿履歴（state/posted.json）にも記録するので、後で自動投稿に切り替えても同じネタが続けて出ることはありません。
"""
from __future__ import annotations

import argparse
import html
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, STATE_PATH, build_caption, choose_format, load_config, load_learning, load_posts, load_state, log, pick_post, save_json, should_post_today, today_jst  # noqa: E402
from generate_image import render_carousel, render_reel_frames, render_square  # noqa: E402
from illustration import get_illustration  # noqa: E402
import media  # noqa: E402

OUT = ROOT / "output" / "manual"


def main() -> int:
    ap = argparse.ArgumentParser(description="手動投稿モード: 数日分の投稿をまとめて生成")
    ap.add_argument("--start", help="開始日 YYYY-MM-DD（省略時は今日）")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--format", choices=["image", "carousel", "reel"], help="形式を固定（省略時は目的・学習から自動）")
    ap.add_argument("--no-ai-image", action="store_true", help="背景写真の AI 生成を行わない（速い）")
    ap.add_argument("--force", action="store_true", help="投稿曜日・スキップ日の設定を無視")
    a = ap.parse_args()

    cfg = load_config()
    if a.no_ai_image:
        cfg.setdefault("image", {})["ai_illustration"] = False
    state = load_state()
    learning = load_learning()
    posts = load_posts(cfg, learning)
    start = datetime.strptime(a.start, "%Y-%m-%d").date() if a.start else today_jst()
    OUT.mkdir(parents=True, exist_ok=True)

    made: list[dict] = []
    for i in range(a.days):
        d = start + timedelta(days=i)
        ok, reason = should_post_today(cfg, d)
        if not ok and not a.force:
            log(f"{d}: 投稿日ではありません（{reason}）")
            continue
        post = pick_post(cfg, posts, d, state, learning)
        fmt = a.format or choose_format(cfg, post, d, learning, ffmpeg_ok=media.ffmpeg_available())
        day_dir = OUT / d.isoformat()
        if day_dir.exists():
            shutil.rmtree(day_dir)
        day_dir.mkdir(parents=True)
        log(f"{d}: [{post['category']}] {post['title']} 形式={fmt}")
        illust = get_illustration(cfg, post)
        files: list[Path] = []
        if fmt == "carousel":
            files = render_carousel(cfg, post, day_dir, "slide", illust=illust)
        elif fmt == "reel":
            frames = render_reel_frames(cfg, post, day_dir / "frames", "reel", illust=illust)
            files = [media.build_reel(frames, day_dir / "reel.mp4"), render_square(cfg, post, day_dir / "cover.jpg", illust=illust)]
            shutil.rmtree(day_dir / "frames", ignore_errors=True)
        else:
            files = [render_square(cfg, post, day_dir / "post.jpg", illust=illust)]
        caption = build_caption(cfg, post, fmt)
        (day_dir / "caption.txt").write_text(caption, encoding="utf-8")
        state.setdefault("posted", []).append(
            {"date": d.isoformat(), "id": post["id"], "category": post["category"], "title": post["title"], "format": fmt,
             "hook": post.get("hook", "none"), "service": post.get("service"), "goals": cfg.get("goals", []), "manual": True}
        )
        made.append({"date": d.isoformat(), "title": post["title"], "format": fmt, "files": [f.name for f in files], "caption": caption})

    save_json(STATE_PATH, state)
    write_index(cfg, made)
    log(f"完了: {len(made)} 日分を {OUT} に出力しました。{OUT / 'index.html'} を開いてください")
    return 0


def write_index(cfg: dict, made: list[dict]) -> None:
    fmt_name = {"image": "1枚画像", "carousel": "カルーセル（画像を順番に選択）", "reel": "リール（reel.mp4 を動画として投稿、cover.jpg はカバー）"}
    cards = []
    for m in made:
        thumbs = "".join(
            f'<a href="{m["date"]}/{html.escape(f)}" target="_blank"><img src="{m["date"]}/{html.escape(f)}" alt=""></a>' if f.endswith(".jpg") else f'<a class="file" href="{m["date"]}/{html.escape(f)}" download>{html.escape(f)}</a>'
            for f in m["files"]
        )
        cards.append(f'''<section class="day">
  <h2>{m["date"]}<span>{html.escape(fmt_name[m["format"]])}</span></h2>
  <p class="t">{html.escape(m["title"])}</p>
  <div class="thumbs">{thumbs}</div>
  <textarea readonly>{html.escape(m["caption"])}</textarea>
  <button type="button" onclick="copyCap(this)">キャプションをコピー</button>
</section>''')
    page = f'''<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>手動投稿 {html.escape(cfg.get("clinic_name",""))}</title>
<style>
body{{margin:0;background:#F5F6F4;color:#1C1F22;font-family:"Zen Kaku Gothic New","Noto Sans JP",system-ui,sans-serif;line-height:1.7;padding:24px 16px 60px}}
main{{max-width:900px;margin:0 auto}} h1{{font-size:22px}} .lead{{color:#626B72;font-size:14.5px}}
.day{{background:#fff;border-radius:10px;padding:18px 20px;margin:16px 0}}
.day h2{{font-size:18px;margin:0 0 4px}} .day h2 span{{font-size:13px;color:#626B72;font-weight:500;margin-left:12px}}
.t{{margin:0 0 10px;font-weight:700}}
.thumbs{{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px}} .thumbs img{{height:150px;border-radius:6px;border:1px solid #DDE2DF}}
.file{{display:inline-block;padding:10px 14px;border:1.5px solid #155E4C;border-radius:8px;color:#155E4C;text-decoration:none;font-weight:700;align-self:center}}
textarea{{width:100%;height:160px;border:1.5px solid #DDE2DF;border-radius:8px;padding:10px;font:inherit;font-size:14px;box-sizing:border-box}}
button{{margin-top:8px;background:#155E4C;color:#fff;border:0;border-radius:8px;padding:10px 18px;font-weight:700;font-size:15px;cursor:pointer;font-family:inherit}}
</style></head><body><main>
<h1>手動投稿 — {html.escape(cfg.get("clinic_name",""))}</h1>
<p class="lead">各日の画像を保存（画像をクリック → 右クリックで保存、またはフォルダから）し、「キャプションをコピー」して Instagram または Meta Business Suite の予約投稿に貼り付けてください。カルーセルは画像を番号順に選択します。</p>
{"".join(cards)}
</main>
<script>function copyCap(b){{const t=b.previousElementSibling.value;navigator.clipboard.writeText(t).then(()=>{{b.textContent='コピーしました';setTimeout(()=>b.textContent='キャプションをコピー',1500)}})}}</script>
</body></html>'''
    (OUT / "index.html").write_text(page, encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
