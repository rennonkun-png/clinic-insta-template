"""共通ユーティリティ: 設定・コンテンツの読み込み、当日の投稿選択、キャプション生成。

設定(config/clinic.json)の主な項目:
  specialties : 診療科（dental / internal / dermatology / pediatrics / ophthalmology / orthopedics / beauty / webmarketing）
  services    : 医院が提供しているサービス。紐付く投稿だけが使われ、末尾にご案内(CTA)が入る
  goals       : 運用の目的（複数可） reach=伸びる投稿 / reels=リール / followers=フォロワー増 / acquisition=集患
学習(state/learning.json)は analyze.py が週次で更新し、投稿選びの重みに使う。
"""
from __future__ import annotations

import json
import os
import random
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = Path(os.environ.get("CLINIC_CONFIG", ROOT / "config" / "clinic.json"))
CONTENT_DIR = ROOT / "content"
STATE_DIR = ROOT / "state"
STATE_PATH = STATE_DIR / "posted.json"
LEARNING_PATH = STATE_DIR / "learning.json"
INSIGHTS_PATH = STATE_DIR / "insights.json"
OUTPUT_DIR = ROOT / "docs" / "images"

JST = timezone(timedelta(hours=9))

MEDICAL_CATEGORIES = {"dental", "internal", "gastroenterology", "dermatology", "ent", "pediatrics", "ophthalmology", "orthopedics", "gynecology", "mental", "beauty", "common"}
ALL_GOALS = ["reach", "reels", "followers", "acquisition"]
FORMATS = ["image", "carousel", "reel"]

CATEGORY_LABELS = {
    "dental": "歯の健康コラム",
    "internal": "からだの健康コラム",
    "gastroenterology": "胃腸の健康コラム",
    "dermatology": "お肌の健康コラム",
    "ent": "耳・鼻・のどの健康コラム",
    "gynecology": "女性の健康コラム",
    "mental": "こころの健康コラム",
    "pediatrics": "こどもの健康コラム",
    "ophthalmology": "目の健康コラム",
    "orthopedics": "からだのケアコラム",
    "beauty": "美容と健康コラム",
    "common": "健康コラム",
    "webmarketing": "クリニックWEB集患コラム",
    "custom": "お知らせ",
    "generated": "健康コラム",
}


for _stream in (sys.stdout, sys.stderr):  # Windows の cp932 端末でも絵文字を出力できるように
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass


def log(msg: str) -> None:
    print(f"[instapost] {msg}", flush=True)


def today_jst() -> date:
    override = os.environ.get("POST_DATE")  # テスト用: 2026-11-10 など
    if override:
        return datetime.strptime(override, "%Y-%m-%d").date()
    return datetime.now(JST).date()


def load_json(path: Path, default=None):
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


# ---------------------------------------------------------------- 設定
def load_config() -> dict:
    if not CONFIG_PATH.exists():
        sys.exit(f"設定ファイルがありません: {CONFIG_PATH}")
    cfg = load_json(CONFIG_PATH)
    cfg.setdefault("specialties", ["dental"])
    cfg.setdefault("services", {})
    cfg.setdefault("goals", ["reach", "followers", "acquisition"])
    cfg.setdefault("theme", {})
    cfg.setdefault("caption", {})
    cfg.setdefault("schedule", {})
    cfg.setdefault("image", {})
    cfg.setdefault("formats", {})
    cfg.setdefault("ai", {})
    if "include_common" not in cfg:
        cfg["include_common"] = any(s in MEDICAL_CATEGORIES for s in cfg["specialties"])
    bad = [g for g in cfg["goals"] if g not in ALL_GOALS]
    if bad:
        log(f"警告: 不明な goals: {bad}（使えるのは {ALL_GOALS}）")
    return cfg


def load_state() -> dict:
    return load_json(STATE_PATH, {"posted": []})


def load_learning() -> dict:
    return load_json(LEARNING_PATH, {"weights": {}, "retired": [], "updated": None})


def label_for(post: dict) -> str:
    return post.get("label") or CATEGORY_LABELS.get(post.get("category", ""), "健康コラム")


# ---------------------------------------------------------------- 投稿日判定
def should_post_today(cfg: dict, d: date) -> tuple[bool, str]:
    sch = cfg.get("schedule", {})
    weekdays = sch.get("post_weekdays") or []
    if weekdays and d.isoweekday() not in weekdays:
        return False, f"{d} は投稿曜日ではありません（設定: {weekdays}）"
    if d.isoformat() in (sch.get("skip_dates") or []):
        return False, f"{d} はスキップ日に指定されています"
    start = sch.get("start_date")
    if start and d < datetime.strptime(start, "%Y-%m-%d").date():
        return False, f"開始日 {start} より前です"
    return True, ""


# ---------------------------------------------------------------- コンテンツ
def _load_file(key: str, path: Path, services: dict, retired: set[str]) -> list[dict]:
    out: list[dict] = []
    data = load_json(path)
    if data is None:
        log(f"警告: コンテンツファイルがありません: {path}")
        return out
    for p in data:
        p = dict(p)
        p.setdefault("category", key)
        p["id"] = f"{key}:{p['id']}"
        if p["id"] in retired or p.get("retired"):
            continue
        svc = p.get("service")
        if svc and svc not in services:  # 提供していないサービスの紹介は使わない
            continue
        out.append(p)
    return out


def load_posts(cfg: dict, learning: dict | None = None) -> list[dict]:
    """医院の診療科・提供サービスに合わせて投稿ネタを集める。"""
    learning = learning or load_learning()
    retired = set(learning.get("retired", []))
    services = cfg.get("services", {}) or {}
    keys = list(dict.fromkeys(cfg.get("specialties", [])))
    if cfg.get("include_common") and "common" not in keys:
        keys.append("common")
    posts: list[dict] = []
    for key in keys:
        posts += _load_file(key, CONTENT_DIR / f"{key}.json", services, retired)
    for extra in ("custom", "generated"):  # 医院独自 / AI生成
        path = CONTENT_DIR / f"{extra}.json"
        if path.exists():
            posts += _load_file(extra, path, services, retired)
    if not posts:
        sys.exit("投稿ネタが1件もありません。content/ フォルダと config の specialties を確認してください。")
    return posts


# ---------------------------------------------------------------- 投稿選択
def post_weight(post: dict, learning: dict) -> float:
    """学習済み重み（analyze.py が更新）を掛け合わせる。未学習なら 1.0。"""
    w = learning.get("weights", {}) or {}
    weight = 1.0
    weight *= w.get("category", {}).get(post.get("category", ""), 1.0)
    weight *= w.get("hook", {}).get(post.get("hook", "none"), 1.0)
    weight *= w.get("service_post", {}).get("yes" if post.get("service") else "no", 1.0)
    return max(0.2, weight)


def pick_post(cfg: dict, posts: list[dict], d: date, state: dict, learning: dict | None = None) -> dict:
    """当日の投稿を決める。
    1. 日付指定(date) があれば最優先
    2. 季節指定(months) に合うものを優先
    3. まだ投稿していないものから。全部使い切ったら最初から。
    4. サービス紹介が2回続いたら通常投稿を優先、直近と同じカテゴリは避ける
    5. 残った候補から学習済み重みで選ぶ（同じ日に再実行しても同じ結果になるよう日付でシード）
    """
    learning = learning or load_learning()
    iso = d.isoformat()
    for p in posts:
        if p.get("date") == iso:
            return p

    posted_ids = {x["id"] for x in state.get("posted", [])}
    unposted = [p for p in posts if p["id"] not in posted_ids and not p.get("date")]
    if not unposted:
        state["posted"] = []
        unposted = [p for p in posts if not p.get("date")]

    seasonal = [p for p in unposted if p.get("months") and d.month in p["months"]]
    anytime = [p for p in unposted if not p.get("months")]
    pool = seasonal or anytime or unposted

    history = state.get("posted", [])
    recent_service = [bool(h.get("service")) for h in history[-2:]]
    if len(recent_service) == 2 and all(recent_service):
        pool = [p for p in pool if not p.get("service")] or pool
    if history:
        last_cat = history[-1].get("category")
        pool = [p for p in pool if p.get("category") != last_cat] or pool

    rng = random.Random(f"{cfg.get('clinic_name','')}-{iso}")
    weights = [post_weight(p, learning) for p in pool]
    return rng.choices(pool, weights=weights, k=1)[0]


def choose_format(cfg: dict, post: dict, d: date, learning: dict | None = None, ffmpeg_ok: bool = True) -> str:
    """目的(goals)と学習結果から投稿形式を決める: image / carousel / reel"""
    learning = learning or load_learning()
    goals = cfg.get("goals", [])
    fmts = cfg.get("formats", {})
    fw = (learning.get("weights", {}) or {}).get("format", {})
    body_n = len(post.get("body", []))

    if "reels" in goals and ffmpeg_ok and body_n >= 2:
        reel_days = fmts.get("reel_weekdays") or [3, 6]
        if d.isoweekday() in reel_days and fw.get("reel", 1.0) >= 0.5:
            return "reel"
    car, img = fw.get("carousel", 1.0), fw.get("image", 1.0)
    if body_n >= 3:
        # 学習結果で明確な差があれば強いほうに寄せる
        if car > 1.2 * img:
            return "carousel"
        if img > 1.2 * car:
            return "image"
        # 「伸びる投稿」目的なら、1枚画像とカルーセルを交互に（単調にならないように）
        if "reach" in goals and d.toordinal() % 2 == 0:
            return "carousel"
    return "image"


# ---------------------------------------------------------------- キャプション
def service_cta(cfg: dict, post: dict) -> str:
    if post.get("cta"):
        return post["cta"]
    svc = post.get("service")
    if svc:
        s = (cfg.get("services") or {}).get(svc) or {}
        if s.get("cta"):
            return s["cta"]
        if s.get("name"):
            return f"当院では「{s['name']}」のご相談も承っています。気になる方はお気軽にお問い合わせください。"
    return cfg.get("caption", {}).get("default_cta", "")


def goal_lines(cfg: dict, post: dict, fmt: str) -> list[str]:
    """目的に応じて末尾に添える一言（保存・フォロー・予約の呼びかけ）。"""
    goals = cfg.get("goals", [])
    cap = cfg.get("caption", {})
    lines: list[str] = []
    if "reach" in goals:
        lines.append(cap.get("save_cta") or "あとで見返せるように、保存しておくと便利です。")
    if "followers" in goals:
        lines.append(cap.get("follow_cta") or f"フォローすると「{label_for(post)}」が毎日届きます。")
    if "acquisition" in goals and cap.get("signature"):
        lines.append(cap["signature"])
    return lines


def build_caption(cfg: dict, post: dict, fmt: str = "image") -> str:
    """1行目=フック（タイトル）→ 結論1行 → 箇条書き → CTAは1つ → 免責 → 医院名 → ハッシュタグ5〜10個。"""
    cap = cfg.get("caption", {})
    body = list(post.get("body", []))
    lines = [post["title"], ""]
    if body:
        lines += [body[0], ""]
        lines += [f"・{b}" for b in body[1:]]
    if post.get("caption_extra"):
        lines += ["", post["caption_extra"]]

    # CTA は 1 つだけ（サービス案内 > 投稿固有 > 目的別）
    goals = cfg.get("goals", [])
    cta = post.get("cta") or ""
    svc = post.get("service")
    if not cta and svc:
        cta = service_cta(cfg, post)
    if not cta:
        cta = cap.get("default_cta") or ""
    if not cta:
        if "acquisition" in goals and cap.get("signature"):
            cta = cap["signature"]
        elif "reach" in goals:
            cta = cap.get("save_cta") or "あとで見返せるように、保存しておくと便利です。"
        elif "followers" in goals:
            cta = cap.get("follow_cta") or f"フォローすると「{label_for(post)}」が毎日届きます。"
    if cta:
        lines += ["", cta]

    is_medical = post.get("category") in MEDICAL_CATEGORIES or bool(svc) or post.get("category") in ("custom", "generated")
    if is_medical and post.get("category") != "webmarketing":
        disclaimer = cap.get("disclaimer", "※ 効果や経過には個人差があります。症状や治療については、必ず医師・歯科医師にご相談ください。")
        if disclaimer:
            lines += ["", disclaimer]
    lines += ["", cfg["clinic_name"]]
    if cfg.get("footer_text"):
        lines.append(cfg["footer_text"])

    # ハッシュタグ: 地域・医院名（fixed）を先に、テーマタグを後に。5〜10 個が目安
    fixed = [t if t.startswith("#") else f"#{t}" for t in cap.get("hashtags_fixed", []) if t]
    topic = [t if t.startswith("#") else f"#{t}" for t in post.get("hashtags", [])] if cap.get("include_specialty_hashtags", True) else []
    tags: list[str] = []
    for t in fixed + topic:
        if t not in tags:
            tags.append(t)
    if fmt == "reel" and "#リール" not in tags:
        tags.append("#リール")
    tags = tags[: int(cap.get("hashtags_max", 10))]
    if tags:
        lines += ["", " ".join(tags)]
    return "\n".join(lines)[:2150]
