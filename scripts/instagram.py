"""Instagram API のラッパー。Facebook ページは不要。

2 つの方式に対応（トークンの種類で自動判別）:
  - 統合ログイン（Unified Login, 2026年以降の新しいアプリ）: graph.facebook.com / システムユーザートークン（期限なし）
      権限: instagram_basic, instagram_content_publish（分析には instagram_manage_insights）
  - Instagram ログイン（以前のアプリ）: graph.instagram.com / "IG" で始まる 60 日トークン（自動延長）
"""
from __future__ import annotations

import os
import time

import requests

from common import log

API_VERSION = "v24.0"


def is_ig_login_token(token: str) -> bool:
    return token.strip().startswith("IG")


def _base(token: str) -> str:
    host = "graph.instagram.com" if is_ig_login_token(token) else "graph.facebook.com"
    return f"https://{host}/{API_VERSION}"


class InstagramError(RuntimeError):
    pass


def _check(resp: requests.Response) -> dict:
    try:
        data = resp.json()
    except ValueError:
        raise InstagramError(f"APIから不正な応答: {resp.status_code} {resp.text[:300]}")
    if "error" in data:
        err = data["error"]
        raise InstagramError(
            f"Instagram API エラー (code={err.get('code')}, subcode={err.get('error_subcode')}): "
            f"{err.get('message')} / {err.get('error_user_msg', '')}"
        )
    return data


def get_me(token: str, ig_user_id: str | None = None) -> dict:
    """投稿先アカウントの情報。統合ログインでは /me がシステムユーザーを指すので IG ユーザー ID で取得する。"""
    if is_ig_login_token(token):
        r = requests.get(f"{_base(token)}/me", params={"fields": "id,username,account_type,followers_count,media_count", "access_token": token}, timeout=30)
        return _check(r)
    uid = ig_user_id or os.environ.get("IG_USER_ID", "").strip()
    if not uid:
        raise InstagramError("IG_USER_ID が未設定です")
    r = requests.get(f"{_base(token)}/{uid}", params={"fields": "id,username,followers_count,media_count", "access_token": token}, timeout=30)
    me = _check(r)
    me.setdefault("account_type", "BUSINESS")  # このAPIで取得できる時点でプロアカウント
    return me


def wait_until_public(url: str, timeout_sec: int = 480, expect_prefix: str = "image/") -> None:
    """GitHub Pages の反映待ち。URL が 200 を返すまで待つ。"""
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            r = requests.head(url, timeout=20, allow_redirects=True)
            ct = r.headers.get("content-type", "")
            if r.status_code == 200 and (ct.startswith(expect_prefix) or ct.startswith("application/octet-stream")):
                log(f"公開を確認: {url}")
                return
            log(f"公開待機中... status={r.status_code} ct={ct}")
        except requests.RequestException as e:
            log(f"公開待機中... {e}")
        time.sleep(15)
    raise InstagramError(f"URLが公開されませんでした（GitHub Pages の設定を確認してください）: {url}")


def _wait_container(container_id: str, token: str, tries: int = 60, interval: int = 5) -> None:
    for _ in range(tries):
        s = requests.get(f"{_base(token)}/{container_id}", params={"fields": "status_code,status", "access_token": token}, timeout=30)
        st = _check(s)
        code = st.get("status_code")
        if code == "FINISHED":
            return
        if code in ("ERROR", "EXPIRED"):
            raise InstagramError(f"コンテナ処理エラー: {st.get('status')}")
        time.sleep(interval)
    raise InstagramError("コンテナ処理がタイムアウトしました")


def _publish(ig_user_id: str, token: str, container_id: str) -> str:
    r = requests.post(f"{_base(token)}/{ig_user_id}/media_publish", data={"creation_id": container_id, "access_token": token}, timeout=60)
    media_id = _check(r)["id"]
    log(f"投稿完了: media_id={media_id}")
    return media_id


def publish_image(ig_user_id: str, token: str, image_url: str, caption: str) -> str:
    r = requests.post(f"{_base(token)}/{ig_user_id}/media", data={"image_url": image_url, "caption": caption, "access_token": token}, timeout=60)
    cid = _check(r)["id"]
    log(f"コンテナ作成: {cid}")
    _wait_container(cid, token)
    return _publish(ig_user_id, token, cid)


def publish_carousel(ig_user_id: str, token: str, image_urls: list[str], caption: str) -> str:
    if not 2 <= len(image_urls) <= 10:
        raise InstagramError("カルーセルは2〜10枚である必要があります")
    children: list[str] = []
    for url in image_urls:
        r = requests.post(f"{_base(token)}/{ig_user_id}/media", data={"image_url": url, "is_carousel_item": "true", "access_token": token}, timeout=60)
        children.append(_check(r)["id"])
    for cid in children:
        _wait_container(cid, token)
    r = requests.post(
        f"{_base(token)}/{ig_user_id}/media",
        data={"media_type": "CAROUSEL", "children": ",".join(children), "caption": caption, "access_token": token},
        timeout=60,
    )
    cid = _check(r)["id"]
    log(f"カルーセルコンテナ作成: {cid} ({len(children)}枚)")
    _wait_container(cid, token)
    return _publish(ig_user_id, token, cid)


def publish_reel(ig_user_id: str, token: str, video_url: str, caption: str, cover_url: str | None = None) -> str:
    data = {"media_type": "REELS", "video_url": video_url, "caption": caption, "share_to_feed": "true", "access_token": token}
    if cover_url:
        data["cover_url"] = cover_url
    r = requests.post(f"{_base(token)}/{ig_user_id}/media", data=data, timeout=60)
    cid = _check(r)["id"]
    log(f"リールコンテナ作成: {cid}（動画処理を待ちます）")
    _wait_container(cid, token, tries=90, interval=10)
    return _publish(ig_user_id, token, cid)


def get_permalink(media_id: str, token: str) -> str:
    r = requests.get(f"{_base(token)}/{media_id}", params={"fields": "permalink", "access_token": token}, timeout=30)
    return _check(r).get("permalink", "")


def get_media_insights(media_id: str, token: str, media_type: str = "image") -> dict:
    """投稿ごとの指標。取れない指標があっても落ちないように段階的に取得。"""
    metrics = "reach,saved,likes,comments,shares,views" if media_type != "reel" else "reach,saved,likes,comments,shares,views,total_interactions"
    out: dict = {}
    try:
        r = requests.get(f"{_base(token)}/{media_id}/insights", params={"metric": metrics, "access_token": token}, timeout=30)
        for item in _check(r).get("data", []):
            vals = item.get("values") or [{}]
            out[item["name"]] = vals[0].get("value", 0)
    except InstagramError as e:
        log(f"insights 取得失敗（基本指標のみ使用）: {e}")
    try:
        r = requests.get(f"{_base(token)}/{media_id}", params={"fields": "like_count,comments_count,timestamp,media_type", "access_token": token}, timeout=30)
        m = _check(r)
        out.setdefault("likes", m.get("like_count", 0))
        out.setdefault("comments", m.get("comments_count", 0))
        out["timestamp"] = m.get("timestamp")
    except InstagramError as e:
        log(f"メディア情報取得失敗: {e}")
    return out


def refresh_token(token: str) -> dict:
    """長期トークンを60日延長する（発行から24時間以上経過が条件）。統合ログインのトークンは期限がないので何もしない。"""
    if not is_ig_login_token(token):
        return {"skipped": True}
    r = requests.get("https://graph.instagram.com/refresh_access_token", params={"grant_type": "ig_refresh_token", "access_token": token}, timeout=30)
    return _check(r)
