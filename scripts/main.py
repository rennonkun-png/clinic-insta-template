"""毎日の自動投稿エントリポイント。

環境変数:
  IG_ACCESS_TOKEN  Instagram の長期アクセストークン（GitHub Secrets）
  IG_USER_ID       Instagram ユーザーID（GitHub Secrets）
  IMAGE_BASE_URL   画像・動画の公開URLの先頭（GitHub Actions が自動で設定）
  DRY_RUN=1        画像・動画・キャプションを作るだけで投稿しない
  POST_DATE        テスト用の日付指定 (YYYY-MM-DD)
  FORCE=1          曜日・スキップ日の設定を無視して投稿
  FORMAT           image / carousel / reel を強制（テスト用）
"""
from __future__ import annotations

import os
import subprocess
import sys

from common import (
    OUTPUT_DIR,
    ROOT,
    STATE_PATH,
    build_caption,
    choose_format,
    load_config,
    load_learning,
    load_posts,
    load_state,
    log,
    pick_post,
    save_json,
    should_post_today,
    today_jst,
)
from generate_image import render_carousel, render_reel_frames, render_square
from illustration import get_illustration
import instagram
import media


def git(*args: str) -> None:
    subprocess.run(["git", *args], cwd=ROOT, check=True)


def commit_and_push(paths: list[str], message: str) -> None:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        log("ローカル実行のため git push はスキップします")
        return
    git("config", "user.name", "instapost-bot")
    git("config", "user.email", "instapost-bot@users.noreply.github.com")
    git("add", *paths)
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode == 0:
        log("コミットする変更がありません")
        return
    git("commit", "-m", message)
    for attempt in range(3):  # 他ジョブと競合した場合はリベースして再送
        try:
            git("push")
            return
        except subprocess.CalledProcessError:
            git("pull", "--rebase")
    git("push")


def main() -> int:
    cfg = load_config()
    state = load_state()
    learning = load_learning()
    d = today_jst()
    dry = os.environ.get("DRY_RUN") == "1"

    ok, reason = should_post_today(cfg, d)
    if not ok and os.environ.get("FORCE") != "1":
        log(f"本日は投稿しません: {reason}")
        return 0

    posts = load_posts(cfg, learning)
    post = pick_post(cfg, posts, d, state, learning)
    fmt = os.environ.get("FORMAT") or choose_format(cfg, post, d, learning, ffmpeg_ok=media.ffmpeg_available())
    log(f"本日の投稿: [{post['category']}] {post['title']}  形式={fmt}  目的={cfg.get('goals')}")

    stem = d.isoformat()
    illust = get_illustration(cfg, post)  # 医院の写真 or 無料AIイラスト or なし
    files: list[str] = []
    if fmt == "carousel":
        paths = render_carousel(cfg, post, OUTPUT_DIR, stem, illust=illust)
        files = [p.name for p in paths]
    elif fmt == "reel":
        frames = render_reel_frames(cfg, post, OUTPUT_DIR / "frames", stem, illust=illust)
        video = media.build_reel(frames, OUTPUT_DIR / f"{stem}.mp4")
        cover = render_square(cfg, post, OUTPUT_DIR / f"{stem}_cover.jpg", illust=illust)
        files = [video.name, cover.name]
    else:
        out = render_square(cfg, post, OUTPUT_DIR / f"{stem}.jpg", illust=illust)
        files = [out.name]

    caption = build_caption(cfg, post, fmt)
    (OUTPUT_DIR / "latest_caption.txt").write_text(caption, encoding="utf-8")
    log("---- キャプション ----\n" + caption + "\n----------------------")

    if dry:
        log("DRY_RUN のため投稿しません")
        return 0

    token = os.environ.get("IG_ACCESS_TOKEN", "").strip()
    user_id = os.environ.get("IG_USER_ID", "").strip()
    if not token or not user_id:
        sys.exit("IG_ACCESS_TOKEN / IG_USER_ID が設定されていません（GitHub Secrets を確認）")
    base_url = (cfg.get("image", {}).get("base_url") or os.environ.get("IMAGE_BASE_URL") or "").rstrip("/")
    if not base_url:
        sys.exit("公開URL(IMAGE_BASE_URL)が不明です。GitHub Pages を有効にしてください。")
    urls = [f"{base_url}/images/{name}" for name in files]

    # 1) 画像/動画を先に公開（GitHub Pages）
    commit_and_push(["docs/images"], f"メディア追加 {stem}")
    for u in urls:
        instagram.wait_until_public(u, expect_prefix="video/" if u.endswith(".mp4") else "image/")

    # 2) 投稿
    me = instagram.get_me(token)
    log(f"投稿アカウント: @{me.get('username')} ({me.get('account_type')}) フォロワー {me.get('followers_count')}")
    if fmt == "carousel":
        media_id = instagram.publish_carousel(user_id, token, urls, caption)
    elif fmt == "reel":
        media_id = instagram.publish_reel(user_id, token, urls[0], caption, cover_url=urls[1])
    else:
        media_id = instagram.publish_image(user_id, token, urls[0], caption)
    permalink = ""
    try:
        permalink = instagram.get_permalink(media_id, token)
    except Exception as e:  # noqa: BLE001
        log(f"パーマリンク取得失敗（無視）: {e}")

    # 3) 履歴を保存（分析はこの履歴をもとに行う）
    state.setdefault("posted", []).append(
        {
            "date": d.isoformat(),
            "id": post["id"],
            "category": post["category"],
            "title": post["title"],
            "format": fmt,
            "hook": post.get("hook", "none"),
            "service": post.get("service"),
            "goals": cfg.get("goals", []),
            "media_id": media_id,
            "permalink": permalink,
            "followers_at_post": me.get("followers_count"),
        }
    )
    save_json(STATE_PATH, state)
    commit_and_push(["state"], f"投稿履歴 {d.isoformat()}")

    # 4) トークン延長
    try:
        res = instagram.refresh_token(token)
        if not res.get("skipped"):
            log(f"トークンを延長しました（残り {int(res.get('expires_in', 0)) // 86400} 日）")
    except Exception as e:  # noqa: BLE001
        log(f"警告: トークン延長に失敗しました: {e}")

    log(f"完了: {permalink or media_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
