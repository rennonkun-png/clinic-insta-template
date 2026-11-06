"""PDCA: 投稿の反応データを取得・分析し、次の投稿選びを賢くする。

毎週実行（GitHub Actions: weekly-analyze.yml）
  1. 直近の投稿の insights（リーチ・保存・いいね・コメント・シェア・再生）を取得 → state/insights.json
  2. カテゴリ / 形式 / 切り口(hook) / サービス紹介有無 ごとの成績を集計し、重みを更新 → state/learning.json
  3. レポートを出力 → docs/report.json（ガイドサイトの「成果レポート」で表示）, GitHub Actions のサマリー
  4. (任意・ANTHROPIC_API_KEY があれば) 成績上位の傾向を学んで新しい投稿ネタを生成し、不調なネタを引退させる
"""
from __future__ import annotations

import os
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from common import (
    INSIGHTS_PATH,
    LEARNING_PATH,
    ROOT,
    load_config,
    load_json,
    load_learning,
    load_state,
    log,
    save_json,
)
import instagram

DIMENSIONS = ["category", "format", "hook", "service_post"]


def score_of(ins: dict, followers: int | None) -> float | None:
    """1投稿のスコア。反応率（保存・シェアを重視）＋ リーチの広がり。"""
    reach = ins.get("reach") or 0
    likes = ins.get("likes") or 0
    comments = ins.get("comments") or 0
    saved = ins.get("saved") or 0
    shares = ins.get("shares") or 0
    views = ins.get("views") or 0
    if reach == 0 and likes == 0 and views == 0:
        return None
    engagement = likes + 2 * comments + 3 * saved + 3 * shares
    base = max(reach, views, 1)
    rate = engagement / base * 100  # 反応率(%)
    spread = (reach / max(followers or 0, 100)) * 10  # フォロワー比でどれだけ届いたか
    return round(rate + spread, 2)


def fetch_insights(token: str, posted: list[dict], insights: dict) -> dict:
    now = datetime.now(timezone.utc)
    for p in posted:
        mid = p.get("media_id")
        if not mid:
            continue
        try:
            post_dt = datetime.strptime(p["date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except Exception:
            post_dt = now
        age = now - post_dt
        prev = insights.get(mid)
        # 投稿後2日未満はまだ数字が育っていないので待つ。45日より古いものは確定済みとして再取得しない
        if age < timedelta(days=2) or (prev and age > timedelta(days=45)):
            continue
        data = instagram.get_media_insights(mid, token, p.get("format", "image"))
        if data:
            data["fetched_at"] = now.isoformat()
            insights[mid] = data
            log(f"insights: {p['date']} {p['title'][:20]}… reach={data.get('reach')} saved={data.get('saved')} likes={data.get('likes')}")
    return insights


def compute_weights(posted: list[dict], insights: dict, prev: dict) -> tuple[dict, list[dict]]:
    rows: list[dict] = []
    for p in posted:
        ins = insights.get(p.get("media_id") or "")
        if not ins:
            continue
        s = score_of(ins, p.get("followers_at_post"))
        if s is None:
            continue
        rows.append({**p, "score": s, "insights": ins})
    weights: dict = {}
    if len(rows) < 3:
        return prev.get("weights", {}), rows
    mean_all = statistics.mean(r["score"] for r in rows) or 1.0
    for dim in DIMENSIONS:
        groups: dict[str, list[float]] = defaultdict(list)
        for r in rows:
            key = ("yes" if r.get("service") else "no") if dim == "service_post" else str(r.get(dim) or "none")
            groups[key].append(r["score"])
        weights[dim] = {}
        for key, vals in groups.items():
            if len(vals) < 2:
                w = 1.0
            else:
                w = min(2.0, max(0.5, statistics.mean(vals) / mean_all))
            old = (prev.get("weights", {}).get(dim, {}) or {}).get(key, 1.0)
            weights[dim][key] = round(0.5 * old + 0.5 * w, 3)  # 急変を避けるため前回とならす
    return weights, rows


def build_report(cfg: dict, rows: list[dict], weights: dict, me: dict | None, learning: dict) -> dict:
    rows_sorted = sorted(rows, key=lambda r: r["score"], reverse=True)
    history = learning.get("follower_history", [])
    if me and me.get("followers_count") is not None:
        today = datetime.now(timezone.utc).date().isoformat()
        if not history or history[-1]["date"] != today:
            history.append({"date": today, "followers": me["followers_count"], "media": me.get("media_count")})
        learning["follower_history"] = history[-60:]

    def brief(r):
        i = r["insights"]
        return {
            "date": r["date"], "title": r["title"], "category": r["category"], "format": r.get("format"), "hook": r.get("hook"),
            "service": r.get("service"), "score": r["score"], "reach": i.get("reach"), "saved": i.get("saved"),
            "likes": i.get("likes"), "comments": i.get("comments"), "shares": i.get("shares"), "views": i.get("views"), "permalink": r.get("permalink"),
        }

    tips: list[str] = []
    fw = weights.get("format", {})
    if fw:
        best = max(fw, key=fw.get)
        tips.append(f"いちばん反応が良い形式は「{ {'image':'1枚画像','carousel':'カルーセル','reel':'リール'}.get(best,best) }」です。今後この形式を優先します。")
    cw = weights.get("category", {})
    if cw and len(cw) > 1:
        best = max(cw, key=cw.get)
        worst = min(cw, key=cw.get)
        tips.append(f"カテゴリ別では「{best}」が好調、「{worst}」は控えめです。")
    sw = weights.get("service_post", {})
    if sw.get("yes") and sw.get("no"):
        tips.append("サービス紹介つき投稿の反応が" + ("良い" if sw["yes"] >= sw["no"] else "弱い") + "ため、紹介の頻度を" + ("やや増やします。" if sw["yes"] >= sw["no"] else "抑えます。"))
    hw = weights.get("hook", {})
    if hw and len(hw) > 1:
        best = max(hw, key=hw.get)
        tips.append(f"切り口は「{best}」型（question=問いかけ / number=数字 / warning=注意喚起 / howto=手順 / myth=誤解）が効いています。")
    if len(history) >= 2:
        diff = history[-1]["followers"] - history[0]["followers"]
        tips.append(f"フォロワーは {history[0]['date']} から {diff:+d} 人です。")
    if not rows:
        tips.append("まだ分析できる投稿がありません。投稿から2日以上経つとデータが集まります。")

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "clinic_name": cfg.get("clinic_name"),
        "goals": cfg.get("goals"),
        "analyzed_posts": len(rows),
        "mean_score": round(statistics.mean(r["score"] for r in rows), 2) if rows else None,
        "top": [brief(r) for r in rows_sorted[:5]],
        "bottom": [brief(r) for r in rows_sorted[-5:][::-1]] if len(rows_sorted) > 5 else [],
        "weights": weights,
        "follower_history": history,
        "tips": tips,
        "retired_count": len(learning.get("retired", [])),
    }


def write_summary(report: dict) -> None:
    md = [f"## Instagram 分析レポート — {report['clinic_name']}", "",
          f"- 分析対象: {report['analyzed_posts']} 投稿 / 平均スコア: {report['mean_score']}", ""]
    md += [f"- {t}" for t in report["tips"]]
    if report["top"]:
        md += ["", "### 反応が良かった投稿", "", "| 日付 | タイトル | 形式 | スコア | リーチ | 保存 |", "|---|---|---|---|---|---|"]
        md += [f"| {r['date']} | {r['title']} | {r['format']} | {r['score']} | {r['reach']} | {r['saved']} |" for r in report["top"]]
    text = "\n".join(md)
    print(text)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(text + "\n")


def main() -> int:
    cfg = load_config()
    state = load_state()
    learning = load_learning()
    insights = load_json(INSIGHTS_PATH, {}) or {}
    token = os.environ.get("IG_ACCESS_TOKEN", "").strip()
    posted = state.get("posted", [])

    me = None
    if token:
        try:
            me = instagram.get_me(token)
        except Exception as e:  # noqa: BLE001
            log(f"アカウント情報の取得に失敗: {e}")
        insights = fetch_insights(token, posted, insights)
        save_json(INSIGHTS_PATH, insights)
    else:
        log("IG_ACCESS_TOKEN が無いため insights は取得せず、既存データで分析します")

    weights, rows = compute_weights(posted, insights, learning)
    learning["weights"] = weights
    learning["updated"] = datetime.now(timezone.utc).isoformat()
    report = build_report(cfg, rows, weights, me, learning)

    # 任意: AI によるブラッシュアップ
    if os.environ.get("ANTHROPIC_API_KEY") and cfg.get("ai", {}).get("auto_brushup", True) and len(rows) >= 5:
        try:
            import ai_generate

            result = ai_generate.brushup_from_report(cfg, report, rows)
            report["ai_brushup"] = result
            for rid in result.get("retired_ids", []):
                if rid not in learning.setdefault("retired", []):
                    learning["retired"].append(rid)
        except Exception as e:  # noqa: BLE001
            log(f"AIブラッシュアップをスキップ: {e}")
            report["ai_brushup"] = {"error": str(e)}

    save_json(LEARNING_PATH, learning)
    save_json(ROOT / "docs" / "report.json", report)
    write_summary(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
