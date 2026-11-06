"""AI（Claude）で投稿ネタを生成する。

(1) 医院のHPや資料から投稿を作る
    python scripts/ai_generate.py --url https://example-clinic.jp --file 資料.pdf --count 20
    → content/custom.json に追記。提供サービスとCTAの候補も提案し、--apply-services で config に反映できる。

(2) 分析レポートをもとにブラッシュアップ（analyze.py から自動で呼ばれる）
    反応が良かった投稿の傾向を学び、新しいネタを content/generated.json に追加。
    不調なネタは引退(retired)させる。

必要: pip install anthropic pypdf / 環境変数 ANTHROPIC_API_KEY
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import anthropic

from common import CONFIG_PATH, CONTENT_DIR, load_config, load_json, log, save_json

MODEL = "claude-opus-5-5"

POST_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "id": {"type": "string", "description": "英数字とハイフンのみの短いID"},
        "title": {"type": "string", "description": "28文字以内。画像の見出しになる"},
        "body": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 5, "description": "各60文字以内の箇条書き"},
        "caption_extra": {"type": "string", "description": "キャプション用の補足1〜2文（なければ空文字）"},
        "hook": {"type": "string", "enum": ["question", "number", "warning", "howto", "myth", "story"]},
        "service": {"type": "string", "description": "紐付くサービスのキー。無ければ空文字"},
        "hashtags": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
        "months": {"type": "array", "items": {"type": "integer"}, "description": "季節性があれば月の配列。なければ空"},
    },
    "required": ["id", "title", "body", "caption_extra", "hook", "service", "hashtags", "months"],
}

COMPLIANCE_RULES = """
あなたは日本の歯科・医科クリニックのInstagram運用を支援する編集者です。医療広告ガイドラインを厳守してください:
- 「必ず治る」「最新」「No.1」「地域一番」「痛くない」などの誇大・比較優良表現は使わない
- 患者の体験談・ビフォーアフター写真を想起させる表現は使わない
- 自由診療に触れる場合は「自由診療です／費用・リスクは診察時にご説明します」と添える前提で書く
- 医学的に不確かな断定は避け、「〜とされています」「〜が一般的です」など穏当な表現にする
- 読者は一般の患者さん。専門用語には短い説明を添え、やさしい日本語で書く
- 投稿は「役に立つ情報 → 最後にさりげなく当院のサービス紹介（service）」の順。売り込み臭を出さない
- タイトルは思わず止まって読みたくなる具体的なもの（数字・問いかけ・意外性）にする
"""


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic()


def _ask_json(system: str, user: str, schema: dict, max_tokens: int = 16000) -> dict:
    client = _client()
    with client.beta.messages.stream(
        model=MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_config={"format": {"type": "json_schema", "schema": schema}, "effort": "high"},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    ) as stream:
        msg = stream.get_final_message()
    if msg.stop_reason == "refusal":
        raise RuntimeError(f"生成が拒否されました: {getattr(msg.stop_details, 'explanation', '')}")
    text = "".join(b.text for b in msg.content if b.type == "text")
    return json.loads(text)


# ---------------------------------------------------------------- 入力テキストの収集
def fetch_url_text(url: str) -> str:
    import requests

    r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0 (clinic-instapost)"})
    r.raise_for_status()
    t = re.sub(r"(?is)<(script|style|noscript|svg).*?</\1>", " ", r.text)
    t = re.sub(r"(?s)<[^>]+>", " ", t)
    t = html.unescape(t)
    return re.sub(r"\s+", " ", t).strip()


def read_file_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader

        return "\n".join((pg.extract_text() or "") for pg in PdfReader(str(path)).pages)
    return path.read_text(encoding="utf-8", errors="ignore")


def _merge_posts(path: Path, new_posts: list[dict], source: str) -> int:
    existing = load_json(path, []) or []
    ids = {p["id"] for p in existing}
    added = 0
    for p in new_posts:
        pid = re.sub(r"[^a-z0-9-]", "-", p["id"].lower()).strip("-") or f"ai-{added}"
        base, n = pid, 2
        while pid in ids:
            pid, n = f"{base}-{n}", n + 1
        p["id"] = pid
        p["source"] = source
        p["created_at"] = datetime.now(timezone.utc).date().isoformat()
        if not p.get("service"):
            p.pop("service", None)
        if not p.get("months"):
            p.pop("months", None)
        if not p.get("caption_extra"):
            p.pop("caption_extra", None)
        existing.append(p)
        ids.add(pid)
        added += 1
    save_json(path, existing)
    return added


# ---------------------------------------------------------------- (1) HP・資料から生成
def generate_from_materials(cfg: dict, texts: list[str], count: int, notes: str) -> dict:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "clinic_summary": {"type": "string"},
            "suggested_services": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "key": {"type": "string", "description": "英小文字のキー 例: whitening, beauty_iv"},
                        "name": {"type": "string"},
                        "cta": {"type": "string", "description": "投稿末尾に添える穏当なご案内文(80〜120文字)"},
                    },
                    "required": ["key", "name", "cta"],
                },
            },
            "suggested_hashtags": {"type": "array", "items": {"type": "string"}, "maxItems": 10},
            "posts": {"type": "array", "items": POST_SCHEMA},
        },
        "required": ["clinic_summary", "suggested_services", "suggested_hashtags", "posts"],
    }
    material = "\n\n-----\n\n".join(t[:40000] for t in texts)
    user = f"""以下は医院のホームページ・資料のテキストです。これを読み込んで、
(1) 医院の特徴を3行で要約
(2) 医院が提供しているサービス（自由診療・特徴的な診療）を抽出し、投稿末尾の「ご案内文(cta)」を作成
(3) Instagram 投稿ネタを {count} 件作成。読者の役に立つ情報が主で、そのうち約4割はサービスに紐付け(service にキーを入れる)、
    残りはサービスに紐付かない一般的な健康情報にする。
現在の設定: 医院名={cfg.get('clinic_name')} 診療科={cfg.get('specialties')} 目的={cfg.get('goals')}
既存の services キー: {list((cfg.get('services') or {}).keys())}
運用者からの補足: {notes or 'なし'}

=== 資料 ===
{material}
"""
    return _ask_json(COMPLIANCE_RULES, user, schema, max_tokens=32000)


# ---------------------------------------------------------------- (2) 分析結果からブラッシュアップ
def brushup_from_report(cfg: dict, report: dict, rows: list[dict]) -> dict:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "insights": {"type": "array", "items": {"type": "string"}, "description": "成績から読み取れる傾向 3〜5行"},
            "new_posts": {"type": "array", "items": POST_SCHEMA},
            "retire_ids": {"type": "array", "items": {"type": "string"}, "description": "引退させる投稿ID（最大3件、成績が明確に低いもの）"},
        },
        "required": ["insights", "new_posts", "retire_ids"],
    }
    n_new = int(cfg.get("ai", {}).get("brushup_new_posts", 7))
    top = report.get("top", [])
    bottom = report.get("bottom", [])
    # 投稿IDをスコアと一緒に渡す（引退判断用）
    scored = [{"id": r["id"], "title": r["title"], "score": r["score"], "format": r.get("format"), "hook": r.get("hook")} for r in sorted(rows, key=lambda r: r["score"])]
    user = f"""Instagram の運用データです。反応が良い投稿の共通点（切り口・テーマ・形式・言い回し）を分析し、
その傾向を取り入れた新しい投稿ネタを {n_new} 件作ってください。既存のタイトルの焼き直しではなく、新しいテーマにしてください。
また、スコアが平均の半分未満で明確に不調な投稿があれば最大3件まで retire_ids に入れてください（なければ空配列）。

医院: {cfg.get('clinic_name')} / 診療科: {cfg.get('specialties')} / 目的: {cfg.get('goals')}
提供サービス(キー: 名前): { {k: v.get('name') for k, v in (cfg.get('services') or {}).items()} }
平均スコア: {report.get('mean_score')}
学習済み重み: {json.dumps(report.get('weights'), ensure_ascii=False)}

【反応が良かった投稿】
{json.dumps(top, ensure_ascii=False, indent=1)}

【反応が弱かった投稿】
{json.dumps(bottom, ensure_ascii=False, indent=1)}

【全投稿のスコア（低い順）】
{json.dumps(scored, ensure_ascii=False)}
"""
    res = _ask_json(COMPLIANCE_RULES, user, schema, max_tokens=24000)
    added = _merge_posts(CONTENT_DIR / "generated.json", res.get("new_posts", []), source="brushup")
    valid_ids = {r["id"] for r in rows}
    retired = [i for i in res.get("retire_ids", []) if i in valid_ids][:3]
    log(f"AIブラッシュアップ: 新規 {added} 件追加 / 引退 {len(retired)} 件")
    return {"insights": res.get("insights", []), "added": added, "retired_ids": retired, "at": datetime.now(timezone.utc).isoformat()}


# ---------------------------------------------------------------- CLI
def main() -> int:
    ap = argparse.ArgumentParser(description="HP・資料からInstagram投稿ネタを生成")
    ap.add_argument("--url", action="append", default=[], help="医院HPなどのURL（複数可）")
    ap.add_argument("--file", action="append", default=[], help="PDF/テキスト資料（複数可）")
    ap.add_argument("--notes", default="", help="補足メモ（例: 11月から美容点滴を開始）")
    ap.add_argument("--count", type=int, default=20)
    ap.add_argument("--out", default=str(CONTENT_DIR / "custom.json"))
    ap.add_argument("--apply-services", action="store_true", help="提案されたサービスを config/clinic.json に追加")
    args = ap.parse_args()
    if not args.url and not args.file and not args.notes:
        ap.error("--url か --file か --notes を指定してください")

    cfg = load_config()
    texts: list[str] = []
    for u in args.url:
        log(f"取得中: {u}")
        texts.append(f"[URL] {u}\n" + fetch_url_text(u))
    for f in args.file:
        log(f"読込中: {f}")
        texts.append(f"[FILE] {f}\n" + read_file_text(Path(f)))
    if args.notes:
        texts.append("[NOTES]\n" + args.notes)

    res = generate_from_materials(cfg, texts, args.count, args.notes)
    log("医院の要約:\n" + res.get("clinic_summary", ""))
    added = _merge_posts(Path(args.out), res.get("posts", []), source="materials")
    log(f"{added} 件の投稿ネタを {args.out} に追加しました")

    if res.get("suggested_services"):
        log("提案された提供サービス（config/clinic.json の services に追加できます）:")
        print(json.dumps({s["key"]: {"name": s["name"], "cta": s["cta"]} for s in res["suggested_services"]}, ensure_ascii=False, indent=2))
        if args.apply_services:
            raw = load_json(CONFIG_PATH)
            raw.setdefault("services", {})
            for s in res["suggested_services"]:
                raw["services"].setdefault(s["key"], {"name": s["name"], "cta": s["cta"]})
            save_json(CONFIG_PATH, raw)
            log("config/clinic.json に services を追加しました")
    if res.get("suggested_hashtags"):
        log("おすすめハッシュタグ: " + " ".join(res["suggested_hashtags"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
