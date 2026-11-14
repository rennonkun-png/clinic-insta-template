"""カルーセルのデザインの型（note_style の「ノート」型に加える型）。

  color : ブランド色の背景に白いカード。表紙は上が写真・下が色の上下分割
  photo : 各ページの上半分が写真で、見出しを写真の上に重ねる。表紙は白地に大きな文字＋角丸の写真

投稿データの "design" で指定する（note / color / photo）。毎日同じ見た目にならないよう、投稿ごとに切り替える。
中身（比較・チェック・吹き出しなど）の描き方は note_style と共通。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw

import note_style as ns
from note_style import INK, PAPER, Note, _attach, _fit_size, _w, parse_rich, strip_rich

ROOT = Path(__file__).resolve().parent.parent
YELLOW = (255, 236, 90)


# ---------------------------------------------------------------- 共通
def _yellow(n: Note):
    return n.marker if ns.luminance(n.marker) > 0.6 else YELLOW


def _photos_for(post: dict, reel: bool = False) -> list[str]:
    """中のページ（photo 型）とリール（photo 型）で使う写真。投稿ごとに page_photos に割り当て済みで、
    同じ写真は投稿をまたいで2度使わない。前半が中のページ用、残りがリール用。"""
    photos = list(post.get("page_photos") or [])
    n_pages = len(post.get("points") or []) + 1 if post.get("design") == "photo" else 0
    if reel:
        rest = photos[n_pages:]
        return rest or photos
    return photos[:n_pages] or photos


def _body(d, img, n: Note, pt: dict, x: int, y: int, w: int, W: int, limit: int, dark=False) -> int:
    """中身を描く。はみ出すときは少しずつ縮める。描いた下端の y を返す。"""
    kind = pt.get("kind", "default")
    fns = {"compare": ns._body_compare, "stat": ns._body_stat, "check": ns._body_check, "voice": ns._body_voice,
           "qa": ns._body_qa, "table": ns._body_table, "template": ns._body_template}

    def run(dd, ws):
        if kind == "phone":
            return ns._body_phone(dd, n, pt, x, y, w, ws, limit - y)
        if kind == "mock":
            return ns._body_mock(dd, img, n, pt, x, y, w, ws, limit - y, W)
        if kind in fns:
            return fns[kind](dd, n, pt, x, y, w, ws)
        return ns._body_default(dd, n, pt, x, y, w, ws, dark=dark)

    scratch = ImageDraw.Draw(Image.new("RGB", img.size))
    ws = W
    for s in (1.0, 0.93, 0.86, 0.8, 0.74, 0.68):
        ws = int(W * s)
        if run(scratch, ws) <= limit:
            break
    ns.FIT_LOG.append((pt.get("h", ""), ws / W))
    return run(d, ws)


def _pill(d, n: Note, x: int, y: int, text: str, fill, color, W: int, outline=None) -> int:
    f = n.f(int(W * 0.03))
    pw = _w(d, text, f) + 44
    d.rounded_rectangle([x, y, x + pw, y + int(f.size * 1.8)], radius=int(f.size * 0.9), fill=fill, outline=outline,
                        width=3 if outline else 0)
    d.text((x + 22, y + int(f.size * 0.33)), text, font=f, fill=color)
    return y + int(f.size * 1.8)


def _foot(d, n: Note, W: int, H: int, M: int, right: str, color) -> None:
    f = n.f(int(W * 0.028))
    y = H - int(W * 0.085)
    d.text((M, y), n.name, font=f, fill=color)
    rw = _w(d, right, f)
    ns._bookmark(d, int(W - M - rw - f.size), y + int(f.size * 0.12), int(f.size * 0.95), color)
    d.text((W - M - rw, y), right, font=f, fill=color)


def _cover_text(d, n: Note, lines: list[str], x: int, y: int, max_w: int, big: int, color, accent, band_fill, band_text,
                stroke=0) -> int:
    plains = [strip_rich(s) for s in lines]
    size = _fit_size(d, plains, n, max_w, big, int(big * 0.55))
    f = n.f(size)
    lh = int(size * 1.32)
    for ln in lines:
        plain, styles = parse_rich(ln)
        xx = x
        for txt, st in _attach([plain], plain, styles)[0]:
            tw = _w(d, txt, f)
            if st & 2:
                d.rectangle([xx - 10, y + int(size * 0.06), xx + tw + 10, y + int(size * 1.26)], fill=band_fill)
                d.text((xx, y), txt, font=f, fill=band_text)
            else:
                d.text((xx, y), txt, font=f, fill=accent if st & 1 else color, stroke_width=stroke, stroke_fill=INK)
            xx += tw
        y += lh
    return y


# ---------------------------------------------------------------- color 型
PALETTES = [None, (28, 40, 66), (14, 74, 70)]  # None = 主色（ブランドの色）／紺／深緑。投稿ごとに切り替える


def _bg(n: Note):
    return getattr(n, "bg", None) or n.primary
def color_cover(n: Note, post: dict, W: int, H: int, page: str = "") -> Image.Image:
    img = Image.new("RGB", (W, H), _bg(n))
    ph = int(H * 0.56)
    if post.get("cover_photo"):
        img.paste(ns._photo_fill(post["cover_photo"], W, ph, float(post.get("cover_focus", 0.3))), (0, 0))
    d = ImageDraw.Draw(img)
    M = int(W * 0.07)
    _pill(d, n, M, int(W * 0.06), n.label, PAPER, _bg(n), W)
    # 写真と色の境目に斜めの切れ込み
    d.polygon([(0, ph - int(W * 0.08)), (W, ph), (W, ph + 2), (0, ph + 2)], fill=_bg(n))
    y = ph + int(W * 0.03)
    y = _cover_text(d, n, post.get("cover_lines") or [post["title"]], M, y, W - M * 2, int(W * 0.105), PAPER, _yellow(n),
                    PAPER, _bg(n))
    if post.get("lead"):
        fl = n.f(int(W * 0.036), bold=False)
        for ln in ns._wrap_c(d, post["lead"], fl, W - M * 2)[:2]:
            d.text((M, y + int(W * 0.01)), ln, font=fl, fill=ns.mix(_bg(n), PAPER, 0.85))
            y += int(fl.size * 1.5)
    if page:
        f = n.f(int(W * 0.028))
        d.text((W - M - _w(d, page, f), H - int(W * 0.07)), page, font=f, fill=ns.mix(_bg(n), PAPER, 0.6))
    return img


def color_point(n: Note, pt: dict, idx: int, total: int, W: int, H: int, page: str = "") -> Image.Image:
    kind = pt.get("kind", "default")
    if kind == "key":  # 結論は白地に主色の大きな文字（色のページが続いたところで抜けを作る）
        img = Image.new("RGB", (W, H), PAPER)
        d = ImageDraw.Draw(img)
        M = int(W * 0.08)
        _pill(d, n, M, int(W * 0.07), "結論", n.primary, PAPER, W)
        y = int(H * 0.22)
        y = ns.rich_heading(d, M, y, pt["h"], n, W - M * 2, int(W * 0.12), int(W * 0.07), n.primary, accent=INK,
                            lh_rate=1.3)
        d.rectangle([M, y + int(W * 0.04), M + int(W * 0.16), y + int(W * 0.04) + 12], fill=n.primary)
        ft = n.f(int(W * 0.05))
        yy = y + int(W * 0.12)
        for ln in ns._wrap_c(d, pt.get("t", ""), ft, W - M * 2):
            d.text((M, yy), ln, font=ft, fill=INK)
            yy += int(ft.size * 1.65)
        _foot(d, n, W, H, M, "次へ", INK)
        return img
    img = Image.new("RGB", (W, H), _bg(n))
    d = ImageDraw.Draw(img)
    M = int(W * 0.07)
    light = ns.mix(_bg(n), PAPER, 0.22)
    var = getattr(n, "variant", 0)
    if n.form and var == 1:  # 型の呼び方（NG 1 など）と丸の番号が二重にならないように
        var = 0
    fp = n.f(int(W * 0.04))
    y = int(H * 0.12)
    if var == 0:  # 見出しの上に大きめの番号（背景には置かない）
        _pill(d, n, M, int(W * 0.06), n.label, None, PAPER, W, outline=PAPER)
        fnum = n.f(int(W * 0.054))
        num = ns.point_label(n.form, idx, f"{idx:02d}")
        d.text((M, y - int(W * 0.02)), num, font=fnum, fill=_yellow(n))
        y += int(fnum.size * 1.15)
    elif var == 1:  # 黄色の丸に番号、大きな番号は出さない
        _pill(d, n, M, int(W * 0.06), n.label, None, PAPER, W, outline=PAPER)
        r = int(W * 0.036)
        d.ellipse([M, y - int(r * 0.35), M + r * 2, y - int(r * 0.35) + r * 2], fill=_yellow(n))
        fnum = n.f(int(W * 0.038))
        sn = str(idx)
        d.text((M + r - _w(d, sn, fnum) // 2, y - int(r * 0.35) + r - int(fnum.size * 0.62)), sn, font=fnum, fill=_bg(n))
        lab = f"/ {total}" if not n.form else f"{ns.point_label(n.form, idx)}  / {total}"
        d.text((M + r * 2 + int(W * 0.025), y), lab, font=fp, fill=ns.mix(_bg(n), PAPER, 0.7))
        y += int(r * 2)
    else:  # 上に進み具合の線、番号は小さく
        seg = (W - M * 2 - (total - 1) * 10) / max(1, total)
        for k in range(total):
            x0 = M + k * (seg + 10)
            d.rounded_rectangle([int(x0), int(W * 0.06), int(x0 + seg), int(W * 0.06) + 10], radius=5,
                                fill=_yellow(n) if k < idx else light)
        d.text((M, y), ns.point_label(n.form, idx, f"{idx}つめ"), font=fp, fill=_yellow(n))
        y += int(fp.size * 1.5)
    y = ns.rich_heading(d, M, y, pt["h"], n, W - M * 2, int(W * 0.088), int(W * 0.062), PAPER, accent=_yellow(n),
                        lh_rate=1.34)
    y += int(W * 0.035)
    card_bot = H - int(W * 0.12)
    P = int(W * 0.045)
    # 中身の高さに合わせてカードを作る（下に大きな空白を作らない）
    probe = Image.new("RGB", (W, H), PAPER)
    end = _body(ImageDraw.Draw(probe), probe, n, pt, M + P, y + P, W - M * 2 - P * 2, W, card_bot - P)
    ns.FIT_LOG.pop()
    bot = min(card_bot, max(end + P, y + int(W * 0.3)))
    d.rounded_rectangle([M, y, W - M, bot], radius=int(W * 0.035), fill=PAPER)
    _body(d, img, n, pt, M + P, y + P, W - M * 2 - P * 2, W, card_bot - P)
    _foot(d, n, W, H, M, "次へ", PAPER)
    if page:
        f = n.f(int(W * 0.028))
        d.text((W // 2 - _w(d, page, f) // 2, H - int(W * 0.085)), page, font=f, fill=ns.mix(_bg(n), PAPER, 0.7))
    return img


def color_summary(n: Note, post: dict, pts: list[dict], W: int, H: int, page: str = "") -> Image.Image:
    img = Image.new("RGB", (W, H), _bg(n))
    d = ImageDraw.Draw(img)
    M = int(W * 0.07)
    _pill(d, n, M, int(W * 0.06), n.label, None, PAPER, W, outline=PAPER)
    ft = n.f(int(W * 0.075))
    y = int(H * 0.13)
    d.text((M, y), ns.summary_of(post, pts)["title"], font=ft, fill=PAPER)
    y += int(ft.size * 1.6)
    card_bot = H - int(W * 0.13)
    P = int(W * 0.05)
    # カードは中身の高さに合わせる（下半分が空いたカードにしない）
    probe = Image.new("RGB", (W, H))
    end = _checks_and_cta(ImageDraw.Draw(probe), n, post, pts, M + P, y + P, W - M * 2 - P * 2, W, card_bot - P, compact=True)
    d.rounded_rectangle([M, y, W - M, end + P], radius=int(W * 0.035), fill=PAPER)
    _checks_and_cta(d, n, post, pts, M + P, y + P, W - M * 2 - P * 2, W, card_bot - P, compact=True)
    _foot(d, n, W, H, M, "保存して見返す", PAPER)
    return img


def _checks_and_cta(d, n: Note, post: dict, pts: list[dict], x: int, y: int, w: int, W: int, bottom: int,
                    compact: bool = False) -> int:
    """まとめの中身と相談の一言を描き、下端の y を返す。
    compact=True なら、相談の一言を中身のすぐ下に置く（カードを中身の高さに合わせるとき）。"""
    sm = ns.summary_of(post, pts)
    fc = n.f(int(W * 0.04))
    cl = ns._wrap_c(d, ns.one_cta(n.cfg, post), fc, w - int(W * 0.06))
    bh = len(cl) * int(fc.size * 1.5) + int(W * 0.06)
    by = bottom - bh
    if sm["type"] == "one":
        probe = ImageDraw.Draw(Image.new("RGB", (W, W * 2)))
        for big_r, note_r in ((0.095, 0.04), (0.082, 0.037), (0.07, 0.034)):
            big, small = int(W * big_r), int(W * big_r * 0.7)
            hh = ns.rich_heading(probe, x, 0, sm["text"], n, w, big, small, INK, lh_rate=1.38)
            fnote = n.f(int(W * note_r), bold=False)
            note_lines = ns._wrap_c(d, sm.get("note", ""), fnote, w)
            nh = len(note_lines) * int(fnote.size * 1.6) + (int(W * 0.04) if note_lines else 0)
            if y + hh + nh <= by - int(W * 0.04):
                break
        if compact:
            yy = y + int(W * 0.02)
            by = min(by, yy + hh + nh + int(W * 0.05))
        else:
            yy = y + max(0, (by - y - hh - nh) // 2) - int(W * 0.02)
        ns.rich_heading(d, x, yy, sm["text"], n, w, big, small, INK, lh_rate=1.38)
        if note_lines:
            ns._lines(d, x, yy + hh + int(W * 0.03), note_lines, fnote, ns.SUB, int(fnote.size * 1.6))
    elif sm["type"] == "template":
        probe = ImageDraw.Draw(Image.new("RGB", (W, W * 2)))
        tp = {"label": sm["label"], "text": sm["text"], "t": sm["note"]}
        ws = W
        for s_ in (1.0, 0.93, 0.86, 0.8):
            ws = int(W * s_)
            if ns._body_template(probe, n, tp, x, y, w, ws) <= by - int(W * 0.04):
                break
        y = ns._body_template(d, n, tp, x, y, w, ws)
        if compact:
            by = min(by, y + int(W * 0.04))
    else:
        for rate in (0.046, 0.042, 0.038, 0.035):
            fi = n.f(int(W * rate))
            s = int(fi.size * 1.1)
            tot = sum(len(ns._wrap_c(d, it, fi, w - s - int(W * 0.04))) * int(fi.size * 1.4) + int(W * 0.028) for it in sm["items"])
            if y + tot <= by - int(W * 0.03):
                break
        for it in sm["items"]:
            hl = ns._wrap_c(d, it, fi, w - s - int(W * 0.04))
            ns.draw_mark(d, x, y + 6, s, sm.get("mark", ""), INK)
            ns._lines(d, x + s + int(W * 0.03), y, hl, fi, INK, int(fi.size * 1.4))
            y += len(hl) * int(fi.size * 1.4) + int(W * 0.028)
        if compact:
            by = min(by, y + int(W * 0.03))
    ns.draw_cta_box(d, x, by, x + w, by + bh, cl, fc, int(fc.size * 1.5), ns.cta_style(post), INK, PAPER, INK,
                    int(W * 0.03))
    return by + bh


# ---------------------------------------------------------------- photo 型
def photo_cover(n: Note, post: dict, W: int, H: int, page: str = "") -> Image.Image:
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    M = int(W * 0.07)
    y = _pill(d, n, M, int(W * 0.06), n.label, n.primary, n.on_primary, W) + int(W * 0.05)
    lines = post.get("cover_lines") or [post["title"]]
    plains = [strip_rich(s) for s in lines]
    size = _fit_size(d, plains, n, W - M * 2, int(W * 0.11), int(W * 0.06))
    f = n.f(size)
    lh = int(size * 1.3)
    for ln in lines:
        plain, styles = parse_rich(ln)
        xx = M
        runs = _attach([plain], plain, styles)[0]
        for txt, st in runs:  # マーカーを先に塗る
            tw = _w(d, txt, f)
            if st & 2:
                d.rectangle([xx - 6, y + int(size * 0.62), xx + tw + 6, y + int(size * 1.12)], fill=_yellow(n))
            xx += tw
        xx = M
        for txt, st in runs:
            d.text((xx, y), txt, font=f, fill=n.primary if st & 1 else INK)
            xx += _w(d, txt, f)
        y += lh
    y += int(W * 0.04)
    top = y
    bot = H - int(W * 0.07)
    if post.get("cover_photo") and bot - top > 200:
        pw, phh = W - M * 2, bot - top
        ph = ns._photo_fill(post["cover_photo"], pw, phh, float(post.get("cover_focus", 0.3)))
        off = int(W * 0.022)
        d.rounded_rectangle([M + off, top + off, M + pw + off, top + phh + off], radius=int(W * 0.04), fill=n.primary)
        mask = Image.new("L", (pw, phh), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, pw - 1, phh - 1], radius=int(W * 0.04), fill=255)
        img.paste(ph, (M, top), mask)
        if post.get("lead"):
            fl = n.f(int(W * 0.036))
            ll = ns._wrap_c(d, post["lead"], fl, pw - int(W * 0.08))[:2]
            bh = len(ll) * int(fl.size * 1.45) + int(W * 0.05)
            d.rounded_rectangle([M + int(W * 0.03), top + phh - bh - int(W * 0.03), M + pw - int(W * 0.03),
                                 top + phh - int(W * 0.03)], radius=int(W * 0.02), fill=PAPER)
            yy = top + phh - bh - int(W * 0.03) + int(W * 0.025)
            for ln in ll:
                d.text((M + int(W * 0.055), yy), ln, font=fl, fill=INK)
                yy += int(fl.size * 1.45)
    return img


def photo_point(n: Note, pt: dict, idx: int, total: int, W: int, H: int, photo: str | None, page: str = "") -> Image.Image:
    kind = pt.get("kind", "default")
    img = Image.new("RGB", (W, H), PAPER)
    M = int(W * 0.07)
    band = int(H * (0.62 if kind == "key" else 0.33))
    if kind != "key" and idx != 1:  # 写真は最初の中ページだけ。あとは色の帯（素材写真を何枚も続けない）
        photo = None
    if photo:
        ph = ns._photo_fill(photo, W, band, 0.2).convert("RGBA")
        grad = Image.new("L", (1, band))
        for yy in range(band):
            grad.putpixel((0, yy), int(min(1.0, max(0.0, (yy / band - 0.15) / 0.85)) ** 1.2 * 215))
        shade = Image.new("RGBA", (W, band), (12, 12, 18, 255))
        shade.putalpha(grad.resize((W, band)))
        ph.alpha_composite(shade)
        img.paste(ph.convert("RGB"), (0, 0))
    else:  # 色の帯に、薄い大きな番号
        img.paste(Image.new("RGB", (W, band), _bg(n)), (0, 0))
        dd = ImageDraw.Draw(img)
        for k in range(6):  # 右上に斜めの線を数本（無地の帯にしない）
            x0 = W - int(W * 0.05) - k * int(W * 0.05)
            dd.line([(x0, 0), (x0 + int(W * 0.12), int(W * 0.12))], fill=ns.mix(_bg(n), PAPER, 0.18), width=8)
    d = ImageDraw.Draw(img)
    if page:  # 中のページは見出しを大きく見せるため、ラベルは出さずページ番号だけ
        f = n.f(int(W * 0.03))
        d.text((W - M - _w(d, page, f), int(W * 0.05)), page, font=f, fill=PAPER, stroke_width=3, stroke_fill=INK)
    # 見出しを写真の下端にそろえて重ねる
    plain, _ = parse_rich(pt["h"])
    lines, size = ns.heading_lines(d, plain, n, W - M * 2, int(W * (0.1 if kind == "key" else 0.085)), int(W * 0.06))
    lh = int(size * 1.32)
    fn = n.f(int(W * 0.038))
    hy = band - int(W * 0.06) - len(lines) * lh
    tag = "結論" if kind == "key" else ns.point_label(n.form, idx)
    tw = _w(d, tag, fn)
    d.rectangle([M, hy - int(fn.size * 1.9), M + tw + 30, hy - int(fn.size * 0.4)], fill=_yellow(n))
    d.text((M + 15, hy - int(fn.size * 1.78)), tag, font=fn, fill=INK)
    ns.rich_heading(d, M, hy, pt["h"], n, W - M * 2, int(W * (0.1 if kind == "key" else 0.085)), int(W * 0.06), PAPER,
                    accent=_yellow(n), lh_rate=1.32, stroke=max(4, size // 14), stroke_fill=INK)
    y = band + int(W * 0.05)
    bottom = H - int(W * 0.125)
    if kind == "key":
        ft = n.f(int(W * 0.05))
        for ln in ns._wrap_c(d, pt.get("t", ""), ft, W - M * 2):
            d.text((M, y), ln, font=ft, fill=INK)
            y += int(ft.size * 1.65)
    else:
        _body(d, img, n, pt, M, y, W - M * 2, W, bottom)
    d.line([(M, H - int(W * 0.11)), (W - M, H - int(W * 0.11))], fill=INK, width=3)
    _foot(d, n, W, H, M, "次へ", INK)
    return img


def photo_summary(n: Note, post: dict, pts: list[dict], W: int, H: int, photo: str | None, page: str = "") -> Image.Image:
    img = Image.new("RGB", (W, H), PAPER)
    band = int(H * 0.2)
    photo = None  # 最後のページの帯は色だけにする（意味のない飾りの写真を置かない）
    img.paste(Image.new("RGB", (W, band), _bg(n)), (0, 0))
    if photo:
        ph = ns._photo_fill(photo, W, band, 0.35)
        ph = Image.blend(ph.convert("L").convert("RGB"), Image.new("RGB", ph.size, (12, 12, 18)), 0.5)  # 写真の色かぶりを出さない
        img.paste(ph, (0, 0))
    d = ImageDraw.Draw(img)
    M = int(W * 0.07)
    ft = n.f(int(W * 0.08))
    d.text((M, band - int(ft.size * 1.4)), ns.summary_of(post, pts)["title"], font=ft, fill=PAPER)
    # 中身の高さを測って、見出しの帯と下の線のあいだの真ん中に置く（項目と相談の帯の間を空けすぎない）
    probe = Image.new("RGB", (W, H))
    top_y = band + int(W * 0.06)
    end = _checks_and_cta(ImageDraw.Draw(probe), n, post, pts, M, top_y, W - M * 2, W, H - int(W * 0.15), compact=True)
    shift = max(0, ((H - int(W * 0.15)) - end) // 2)
    _checks_and_cta(d, n, post, pts, M, top_y + shift, W - M * 2, W, H - int(W * 0.15), compact=True)
    d.line([(M, H - int(W * 0.11)), (W - M, H - int(W * 0.11))], fill=INK, width=3)
    _foot(d, n, W, H, M, "保存して見返す", INK)
    return img


# ---------------------------------------------------------------- 入口
def draw_cover(n: Note, post: dict, W: int, H: int, design: str, page: str = "") -> Image.Image:
    _set_palette(n, post)
    if post.get("cover_mock") and not post.get("cover_photo"):  # 写真のかわりに画面の図や文例を見せる表紙
        keep = n.primary
        if design == "color":
            n.primary = _bg(n)
        img = ns.draw_cover_mock(n, post, W, H, page=page)
        n.primary = keep
    elif design == "color":
        img = color_cover(n, post, W, H, page)
    elif design == "photo":
        img = photo_cover(n, post, W, H, page)
    else:
        return ns.draw_cover(n, post, W, H, page=page)
    ns.cover_tag(ImageDraw.Draw(img), n, post, W, int(W * 0.06))
    return img


def _set_palette(n: Note, post: dict) -> None:
    idx = post.get("palette")
    if idx is None:
        idx = int(hashlib.md5(post["id"].encode()).hexdigest()[:4], 16) % len(PALETTES)
    n.bg = PALETTES[int(idx) % len(PALETTES)]
    n.variant = int(hashlib.md5((post["id"] + "layout").encode()).hexdigest()[:4], 16) % 3
    n.form = post.get("form")


def render_pages(n: Note, post: dict, pts: list[dict], W: int, H: int, design: str) -> list[Image.Image]:
    _set_palette(n, post)
    total = len(pts) + 2
    imgs = [draw_cover(n, post, W, H, design)]  # 表紙にはページ番号を出さない
    photos = _photos_for(post)
    for i, p in enumerate(pts, 1):
        pg = f"{i + 1} / {total}"
        if design == "color":
            imgs.append(color_point(n, p, i, len(pts), W, H, pg))
        else:
            imgs.append(photo_point(n, p, i, len(pts), W, H, photos[(i - 1) % len(photos)] if photos else None, pg))
    pg = f"{total} / {total}"
    if design == "color":
        imgs.append(color_summary(n, post, pts, W, H, pg))
    else:
        imgs.append(photo_summary(n, post, pts, W, H, photos[len(pts) % len(photos)] if photos else None, pg))
    return imgs
