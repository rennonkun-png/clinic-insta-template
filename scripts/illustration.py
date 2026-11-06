"""投稿の背景写真（AI生成）を無料で用意する。

優先順:
  1. 投稿に image_path があれば医院の写真をそのまま使う（例: assets/photos/whitening.jpg）
  2. config.image.ai_illustration が有効なら、投稿ごとの illustration_prompt から AI で写真風の画像を生成
       a. Cloudflare Workers AI（無料枠が大きく安定。CF_ACCOUNT_ID / CF_API_TOKEN）FLUX.1-schnell
       b. Hugging Face Inference（無料枠。HF_TOKEN）FLUX.1-schnell
       c. Pollinations.ai（APIキー不要。混雑時は失敗し、指示どおりに描かれないことも多い）
     生成結果は docs/images/ai/ にキャッシュ。同じ投稿は再生成しない
  3. どれも使えなければ None（文字だけのデザインになる。見栄えは保たれる）

生成に使うのは英語の短いプロンプトのみ（医院名・個人情報は送らない）。
"""
from __future__ import annotations

import base64
import hashlib
import io
import os
import time
from pathlib import Path
from urllib.parse import quote

import requests
from PIL import Image

from common import OUTPUT_DIR, ROOT, log

AI_DIR = OUTPUT_DIR / "ai"

CATEGORY_SUBJECTS = {
    "dental": "a toothbrush and a glass of water on a clean white bathroom counter, soft morning light",
    "internal": "a stethoscope and a notebook on a wooden table by a window",
    "gastroenterology": "a warm bowl of soup and a cup of tea on a calm kitchen table",
    "dermatology": "skincare bottles and a soft towel on a bathroom shelf with a small plant",
    "ent": "a tissue box, a scarf and a warm mug on a bedside table",
    "pediatrics": "a child's room with a teddy bear and a picture book in soft light",
    "ophthalmology": "a pair of glasses and a book on a desk by a bright window",
    "orthopedics": "walking shoes and a yoga mat in a bright room",
    "gynecology": "a calendar, a cup of herbal tea and flowers on a quiet table",
    "mental": "a window seat with a cushion and a cup of tea in soft light",
    "beauty": "fresh fruits and a glass of water on a bright table",
    "common": "a water bottle, fresh vegetables and walking shoes in morning light",
    "webmarketing": "a laptop, a smartphone, a notebook and coffee on a tidy desk in a bright office",
    "custom": "a bright clinic reception with plants and a wooden counter",
    "generated": "a bright clinic reception with plants and a wooden counter",
}

# 写真風。Instagram で止まって読んでもらうための「雑誌の表紙」のような絵作り
STYLE = (
    "editorial lifestyle photograph, natural soft light, calm muted colors, shallow depth of field, "
    "clean minimal composition with empty space at the top, high quality, realistic, "
    "no text, no letters, no logo, no watermark, no people faces"
)


def build_prompt(post: dict) -> str:
    if post.get("illustration_prompt"):
        return f"{post['illustration_prompt']}, {STYLE}"
    subject = CATEGORY_SUBJECTS.get(post.get("category", ""), CATEGORY_SUBJECTS["common"])
    return f"{subject}, {STYLE}"


def _save(content: bytes, out: Path, crop_bottom: float = 0.0) -> bool:
    try:
        im = Image.open(io.BytesIO(content)).convert("RGB")
    except Exception:
        return False
    if crop_bottom:  # 右下の透かしを避けるため、下端を少し切り落とす
        w, h = im.size
        cut = int(h * crop_bottom)
        im = im.crop((cut // 2, 0, w - cut // 2, h - cut))
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out, "JPEG", quality=90)
    return True


def _fetch_cloudflare(prompt: str, out: Path, seed: int) -> bool:
    acct = os.environ.get("CF_ACCOUNT_ID", "").strip()
    token = os.environ.get("CF_API_TOKEN", "").strip()
    if not acct or not token:
        return False
    url = f"https://api.cloudflare.com/client/v4/accounts/{acct}/ai/run/@cf/black-forest-labs/flux-1-schnell"
    for attempt in range(3):
        try:
            r = requests.post(url, headers={"Authorization": f"Bearer {token}"}, json={"prompt": prompt, "steps": 6, "seed": seed}, timeout=120)
            if r.status_code == 200:
                b64 = ((r.json().get("result") or {}).get("image")) or ""
                if b64:
                    return _save(base64.b64decode(b64), out)
            log(f"Cloudflare 画像生成 応答待ち… status={r.status_code} {r.text[:100]} (試行{attempt + 1}/3)")
        except (requests.RequestException, ValueError) as e:
            log(f"Cloudflare 画像生成 エラー: {e}")
        time.sleep(10)
    return False


def _fetch_hf(prompt: str, out: Path) -> bool:
    token = os.environ.get("HF_TOKEN", "").strip()
    if not token:
        return False
    model = os.environ.get("HF_IMAGE_MODEL", "black-forest-labs/FLUX.1-schnell")
    url = f"https://router.huggingface.co/hf-inference/models/{model}"
    for attempt in range(3):
        try:
            r = requests.post(url, headers={"Authorization": f"Bearer {token}"}, json={"inputs": prompt, "parameters": {"width": 1024, "height": 1024}}, timeout=180)
            if r.status_code == 200 and r.headers.get("content-type", "").startswith("image/"):
                return _save(r.content, out)
            log(f"HF 画像生成 応答待ち… status={r.status_code} {r.text[:80]} (試行{attempt + 1}/3)")
        except requests.RequestException as e:
            log(f"HF 画像生成 通信エラー: {e}")
        time.sleep(15)
    return False


def _fetch_pollinations(prompt: str, out: Path, size: int, seed: int) -> bool:
    url = f"https://image.pollinations.ai/prompt/{quote(prompt)}?width={size}&height={size}&nologo=true&seed={seed}&model=flux"
    for attempt in range(3):
        try:
            r = requests.get(url, timeout=120)
            if r.status_code == 200 and r.headers.get("content-type", "").startswith("image/") and len(r.content) > 10_000:
                return _save(r.content, out, crop_bottom=0.08)
            log(f"画像生成 応答待ち… status={r.status_code} (試行{attempt + 1}/3)")
        except requests.RequestException as e:
            log(f"画像生成 通信エラー: {e} (試行{attempt + 1}/3)")
        time.sleep(10)
    return False


def get_illustration(cfg: dict, post: dict, size: int = 1024) -> Path | None:
    if post.get("image_path"):
        p = Path(post["image_path"])
        p = p if p.is_absolute() else ROOT / p
        if p.exists():
            return p
        log(f"警告: image_path が見つかりません: {p}")
    img_cfg = cfg.get("image", {})
    if not img_cfg.get("ai_illustration", True):
        return None
    prompt = build_prompt(post)
    key = hashlib.md5(f"{post['id']}|{prompt}".encode()).hexdigest()[:12]
    out = AI_DIR / f"{key}.jpg"
    if out.exists():
        return out
    log(f"背景画像を生成中（無料AI）: {prompt[:90]}…")
    seed = int(hashlib.md5(post["id"].encode()).hexdigest()[:6], 16)
    ok = _fetch_cloudflare(prompt, out, seed) or _fetch_hf(prompt, out) or _fetch_pollinations(prompt, out, size, seed)
    if ok:
        log(f"背景画像を保存: {out}")
        return out
    log("画像生成に失敗したため、文字だけのデザインで作成します")
    return None
