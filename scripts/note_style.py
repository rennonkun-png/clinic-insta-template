"""「図解ノート」デザイン（ビジネス向け・院長先生向け発信用）。

単調にならないよう、ポイントごとに見せ方（kind）を変える。
  default : 見出し＋補足（補足は色付きの箱）
  compare : よくある（✕）とおすすめ（○）を上下に並べる      ng / ok
  stat    : 大きな数字で見せる                            num / num_label
  check   : チェックリスト                                 items
  voice   : 吹き出しで「患者さんの本音」などを見せる        voice / voice_label
  qa      : 質問と回答の吹き出し                           q / a
  phone   : スマホ画面の図（ボタンの位置の良し悪し）        ng / ok
  key     : 黒背景の「結論」ページ（1投稿に1枚まで）
表紙はアクセント色、まとめは保存用チェックリスト。

投稿データ: cover_lines・lead・points（[{"h": 見出し, "t": 補足, "kind": ..., ...}]）。
t はキャプションにも使うので kind に関係なく必ず入れる。
config: theme.style = "note" で有効。theme.primary_color（番号など）/ theme.accent_color（表紙・マーカー）
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from generate_image import (GOTHIC_FONTS, Theme, _first_existing, font, hex_to_rgb, luminance, mix, one_cta,
                            split_point, wrap)

PAPER = (255, 255, 255)
GRID = (236, 239, 242)
INK = (22, 24, 28)
SUB = (70, 76, 84)
FAINT = (150, 156, 162)
LIGHT = (243, 244, 246)
DARK = (28, 30, 34)

FIT_LOG: list = []  # 品質チェック用: (見出し, 文字を縮めた割合)

REGULAR_FONTS = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "C:/Windows/Fonts/NotoSansJP-VF.ttf",
    "C:/Windows/Fonts/YuGothM.ttc",
    "C:/Windows/Fonts/meiryo.ttc",
]


class Note:
    def __init__(self, cfg: dict):
        th = Theme(cfg)
        t = cfg.get("theme", {})
        self.cfg = cfg
        self.primary = th.primary
        acc = hex_to_rgb(t.get("accent_color"), (255, 230, 90))
        self.marker = acc if luminance(acc) > 0.6 else mix((255, 255, 255), th.primary, 0.25)
        self.cover_bg = acc if luminance(acc) > 0.6 else mix((255, 255, 255), th.primary, 0.18)
        self.tint = mix((255, 255, 255), th.primary, 0.07)
        self.on_primary = (255, 255, 255) if luminance(th.primary) < 0.6 else INK
        self.bold = th.title_font if t.get("font", "gothic") != "serif" else _first_existing(GOTHIC_FONTS)
        self.reg = _first_existing(REGULAR_FONTS) or th.body_font
        self.label = cfg.get("series_label") or th.author or ""
        self.name = cfg.get("clinic_name", "")
        self.form = None  # 投稿の型（qa / steps / ng / myth / case）

    def f(self, size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
        return font(self.bold if bold else self.reg, size, bold=bold)


# ---------------------------------------------------------------- データ
def cta_style(post: dict) -> int:
    """相談の帯の形: 0=塗り 1=枠線 2=左に太い線。投稿ごとに決まる。"""
    import hashlib
    return int(hashlib.md5((post.get("id", "") + "ctabox").encode()).hexdigest()[:4], 16) % 3


def draw_cta_box(d, x0, y0, x1, y1, lines, f, lh, style, fill, on_fill, ink, pad):
    if style == 0:
        d.rectangle([x0, y0, x1, y1], fill=fill)
        _lines(d, x0 + pad, y0 + pad, lines, f, on_fill, lh)
    elif style == 1:
        d.rectangle([x0, y0, x1, y1], outline=fill, width=6)
        _lines(d, x0 + pad, y0 + pad, lines, f, ink, lh)
    else:
        d.rectangle([x0, y0, x0 + 14, y1], fill=fill)
        _lines(d, x0 + pad + 6, y0 + pad, lines, f, ink, lh)


def summary_of(post: dict, pts: list[dict]) -> dict:
    """最後のページの中身。summary があればそれを使い、なければ見出しを並べる。"""
    sm = post.get("summary") or {}
    if sm.get("type") == "one" and sm.get("text"):
        return {"type": "one", "title": sm.get("title") or "今日のまとめ", "text": sm["text"], "note": sm.get("note", "")}
    if sm.get("type") == "template" and sm.get("text"):
        return {"type": "template", "title": sm.get("title") or "そのまま使える文面", "label": sm.get("label") or "コピーして使えます",
                "text": sm["text"], "note": sm.get("note", "")}
    items = sm.get("items") or [strip_rich(p["h"]).replace("\n", "") for p in pts]
    return {"type": "check", "title": sm.get("title") or "保存用チェック", "items": items, "mark": sm.get("mark", "")}


def draw_mark(d, x: int, y: int, s: int, mark: str, color) -> None:
    """まとめの項目の頭の印。x はバツ（やらなくていいこと）、それ以外はチェック欄。"""
    if mark == "x":
        _cross(d, x + s // 2, y + s // 2, int(s * 0.42), (214, 69, 65), 7)
    else:
        d.rectangle([x, y, x + s, y + s], outline=color, width=5)


def points_of(post: dict) -> list[dict]:
    if post.get("points"):
        return [dict(p) for p in post["points"]][:5]
    out = []
    for b in post.get("body", [])[:5]:
        h, t = split_point(b)
        out.append({"h": h, "t": t})
    return out


def cover_lines(post: dict, d: ImageDraw.ImageDraw, f: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    if post.get("cover_lines"):
        return list(post["cover_lines"])
    return wrap(d, post["title"], f, max_w)


# ---------------------------------------------------------------- 強調つき文字（*主色* / ==マーカー==）
def parse_rich(s: str) -> tuple[str, list[int]]:
    """*x* → 1（主色）, ==x== → 2（マーカー）。改行は残す。"""
    plain, styles = [], []
    color = mark = False
    i = 0
    while i < len(s):
        if s.startswith("==", i):
            mark = not mark
            i += 2
            continue
        if s[i] == "*":
            color = not color
            i += 1
            continue
        plain.append(s[i])
        styles.append((1 if color else 0) | (2 if mark else 0))
        i += 1
    return "".join(plain), styles


def strip_rich(s: str) -> str:
    return parse_rich(s)[0]


def _attach(lines: list[str], plain: str, styles: list[int]) -> list[list[tuple[str, int]]]:
    out, k = [], 0
    for ln in lines:
        while k < len(plain) and plain[k] == "\n":
            k += 1
        runs: list[tuple[str, int]] = []
        for ch in ln:
            while k < len(plain) and plain[k] != ch:
                k += 1
            st = styles[k] if k < len(styles) else 0
            if runs and runs[-1][1] == st:
                runs[-1] = (runs[-1][0] + ch, st)
            else:
                runs.append((ch, st))
            k += 1
        out.append(runs)
    return out


def _draw_runs(d, x, y, runs, f, base, n: Note, marker=None, accent=None, stroke=0, stroke_fill=None) -> None:
    marker = marker or n.marker
    accent = accent or n.primary
    xx = x
    for txt, st in runs:
        w = _w(d, txt, f)
        if st & 2:
            d.rectangle([xx - 4, y + int(f.size * 0.6), xx + w + 4, y + int(f.size * 1.1)], fill=marker)
        xx += w
    xx = x
    for txt, st in runs:
        d.text((xx, y), txt, font=f, fill=accent if st & 1 else base, stroke_width=stroke, stroke_fill=stroke_fill)
        xx += _w(d, txt, f)


def rich_block(d, x, y, text, f, max_w, lh, base, n: Note, marker=None) -> int:
    plain, styles = parse_rich(text)
    lines = wrap(d, plain, f, max_w)
    for runs in _attach(lines, plain, styles):
        _draw_runs(d, x, y, runs, f, base, n, marker)
        y += lh
    return y


def rich_heading(d, x, y, text, n: Note, max_w, big, small, base, marker=None, lh_rate=1.34, accent=None, stroke=0,
                 stroke_fill=None) -> int:
    plain, styles = parse_rich(text)
    lines, size = heading_lines(d, plain, n, max_w, big, small)
    f = n.f(size)
    for runs in _attach(lines, plain, styles):
        _draw_runs(d, x, y, runs, f, base, n, marker, accent, stroke, stroke_fill)
        y += int(size * lh_rate)
    return y


# ---------------------------------------------------------------- 部品
def _paper(W: int, H: int, bg=PAPER, grid=GRID, step: int = 54) -> Image.Image:
    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)
    for x in range(0, W, step):
        d.line([(x, 0), (x, H)], fill=grid, width=1)
    for y in range(0, H, step):
        d.line([(0, y), (W, y)], fill=grid, width=1)
    return img


def _w(d, s, f) -> float:
    return d.textlength(s, font=f)


def _fit_size(d, lines: list[str], n: Note, max_w: int, start: int, minimum: int) -> int:
    size = start
    while size > minimum and max(_w(d, ln, n.f(size)) for ln in lines) > max_w:
        size -= 4
    return size


def heading_lines(d, text: str, n: "Note", max_w: int, big: int, small: int) -> tuple[list[str], int]:
    """見出しを 1 行で収められる大きさを探し、無理なら 2 行に「長さが釣り合う位置」で分ける。"""
    from generate_image import _good_break, _units
    if "\n" in text:
        lines = text.split("\n")
        size = _fit_size(d, lines, n, max_w, big, small)
        if max(_w(d, ln, n.f(size)) for ln in lines) > max_w:
            out = []
            for ln in lines:
                out += wrap(d, ln, n.f(size), max_w)
            return out, size
        return lines, size
    size = big
    while size >= int(big * 0.8):
        if _w(d, text, n.f(size)) <= max_w:
            return [text], size
        size -= 4
    units = _units(text)
    best = None
    for k in range(1, len(units)):
        if not _good_break(units, k):
            continue
        a, b = "".join(units[:k]), "".join(units[k:])
        score = max(_w(d, a, n.f(100)), _w(d, b, n.f(100)))
        if best is None or score < best[0]:
            best = (score, [a, b])
    if best is None:
        from generate_image import words_fit
        size = big
        while not words_fit(d, text, n.f(size), max_w) and size > small:
            size -= 4
        return wrap(d, text, n.f(size), max_w), size
    size = _fit_size(d, best[1], n, max_w, big, small)
    if max(_w(d, ln, n.f(size)) for ln in best[1]) > max_w:  # 2行でも入らない長い文は、小さめの文字で折り返す
        from generate_image import words_fit
        size = max(small, int(big * 0.85))
        while not words_fit(d, text, n.f(size), max_w) and size > small:
            size -= 4
        return wrap(d, text, n.f(size), max_w), size
    return best[1], size


def _marker_line(d, x: int, y: int, text: str, f, color) -> None:
    w = _w(d, text, f)
    d.rectangle([x - 6, y + int(f.size * 0.62), x + w + 6, y + int(f.size * 1.08)], fill=color)


def _lines(d, x: int, y: int, lines: list[str], f, fill, lh: int, marker=None) -> int:
    for ln in lines:
        if marker is not None:
            _marker_line(d, x, y, ln, f, marker)
        d.text((x, y), ln, font=f, fill=fill)
        y += lh
    return y


def _header(d, n: Note, W: int, M: int, y: int, right: str = "", ink=INK, sq_color=None, faint=FAINT) -> int:
    f = n.f(int(W * 0.03))
    sq = int(f.size * 0.7)
    d.rectangle([M, y + int(f.size * 0.28), M + sq, y + int(f.size * 0.28) + sq], fill=sq_color or n.primary)
    d.text((M + sq + int(f.size * 0.5), y), n.label, font=f, fill=ink)
    if right:
        d.text((W - M - _w(d, right, f), y), right, font=f, fill=faint)
    return y + int(f.size * 1.6)


def _bookmark(d, x: int, y: int, h: int, fill) -> None:
    w = int(h * 0.72)
    d.polygon([(x, y), (x + w, y), (x + w, y + h), (x + w // 2, y + int(h * 0.72)), (x, y + h)], fill=fill)


def _footer(d, n: Note, W: int, M: int, y: int, right: str, ink=INK, mark=None) -> None:
    d.line([(M, y), (W - M, y)], fill=ink, width=3)
    f = n.f(int(W * 0.028))
    ty = y + int(f.size * 0.7)
    d.text((M, ty), n.name, font=f, fill=ink)
    rw = _w(d, right, f)
    _bookmark(d, int(W - M - rw - f.size * 1.0), ty + int(f.size * 0.12), int(f.size * 0.95), mark or n.primary)
    d.text((W - M - rw, ty), right, font=f, fill=ink)


def _progress(d, n: Note, W: int, M: int, y: int, total: int, current: int, off=GRID) -> None:
    gap = 10
    seg = (W - M * 2 - gap * (total - 1)) / total
    for i in range(total):
        x0 = int(M + i * (seg + gap))
        d.rounded_rectangle([x0, y, int(x0 + seg), y + 10], radius=5, fill=n.primary if i < current else off)


def _num(i: int) -> str:
    return f"{i:02d}"


FORM_LABELS = {"qa": "Q{i}", "steps": "STEP {i}", "ng": "NG {i}", "myth": "誤解{i}", "case": "ケース{i}"}


def point_label(form, i: int, default: str | None = None) -> str:
    """投稿の型に合わせた番号の呼び方（型がなければ default か 01 形式）。"""
    if form in FORM_LABELS:
        return FORM_LABELS[form].format(i=i)
    return default if default is not None else _num(i)


def _cross(d, cx: int, cy: int, r: int, color, width: int) -> None:
    d.line([(cx - r, cy - r), (cx + r, cy + r)], fill=color, width=width)
    d.line([(cx - r, cy + r), (cx + r, cy - r)], fill=color, width=width)


def _circle(d, cx: int, cy: int, r: int, color, width: int) -> None:
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=width)


def _check(d, x: int, y: int, s: int, color, width: int) -> None:
    d.line([(x + s * 0.18, y + s * 0.52), (x + s * 0.42, y + s * 0.76), (x + s * 0.86, y + s * 0.22)], fill=color,
           width=width, joint="curve")


def _wrap_c(d, text: str, f, max_w: int) -> list[str]:
    if not text:
        return []
    lines = wrap(d, str(text).strip(), f, max_w)
    # 最後の行が2〜3文字だけになるときは、少し狭めて折り返し直す（「さい」「す」だけの行を作らない）
    for rate in (0.94, 0.88, 0.82):
        if len(lines) < 2 or len(lines[-1]) > 3:
            break
        alt = wrap(d, str(text).strip(), f, int(max_w * rate))
        if len(alt[-1]) > 3 and len(alt) <= len(lines) + 1:
            lines = alt
    return lines


# ---------------------------------------------------------------- 表紙
def draw_cover(n: Note, post: dict, W: int, H: int, reel: bool = False, page: str = "") -> Image.Image:
    if post.get("cover_photo"):
        img = draw_cover_photo(n, post, W, H, reel, page)
    elif post.get("cover_mock"):
        img = draw_cover_mock(n, post, W, H, reel, page)
    else:
        img = draw_cover_plain(n, post, W, H, reel, page)
    if isinstance(img, Image.Image) and not reel:
        cover_tag(ImageDraw.Draw(img), n, post, W, int(W * 0.06))
    return img


def _photo_fill(path: str, W: int, H: int, focus_y: float = 0.4) -> Image.Image:
    from generate_image import ROOT
    pth = Path(path)
    pth = pth if pth.is_absolute() else ROOT / pth
    im = Image.open(pth).convert("RGB")
    s = max(W / im.width, H / im.height)
    im = im.resize((int(im.width * s + 1), int(im.height * s + 1)), Image.LANCZOS)
    x = (im.width - W) // 2
    y = int((im.height - H) * focus_y)
    return im.crop((x, y, x + W, y + H))


def draw_cover_photo(n: Note, post: dict, W: int, H: int, reel: bool = False, page: str = "", layers: bool = False):
    """写真を全面に敷き、太い縁取り文字を重ねる表紙（伸びている投稿に多い形）。"""
    bg = _photo_fill(post["cover_photo"], W, H, float(post.get("cover_focus", 0.4)))
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))  # 文字と影だけの層（リールで写真と別に動かす）
    pos = post.get("cover_text_pos", "top")
    # 文字の側を暗くして読みやすくする
    grad = Image.new("L", (1, H), 0)
    for yy in range(H):
        t = yy / H
        a = (1 - t / 0.62) if pos == "top" else ((t - 0.38) / 0.62)
        grad.putpixel((0, yy), int(max(0.0, min(1.0, a)) ** 1.1 * 225))
    shade = Image.new("RGBA", (W, H), (10, 10, 16, 255))
    shade.putalpha(grad.resize((W, H)))
    img.alpha_composite(shade)
    d = ImageDraw.Draw(img)
    M = int(W * 0.07)
    top = int(H * 0.13) if reel else int(W * 0.07)
    f = n.f(int(W * 0.032))
    label = n.label
    pw = _w(d, label, f) + 48
    d.rounded_rectangle([M, top, M + pw, top + int(f.size * 1.85)], radius=int(f.size * 0.92), fill=n.primary)
    d.text((M + 24, top + int(f.size * 0.36)), label, font=f, fill=n.on_primary)
    lines = post.get("cover_lines") or [post["title"]]
    plains = [strip_rich(x) for x in lines]
    size = _fit_size(d, plains, n, W - M * 2, int(W * (0.125 if reel else 0.118)), int(W * 0.06))
    fh = n.f(size)
    lh = int(size * 1.3)
    stroke = max(7, int(size * 0.11))
    block = len(lines) * lh
    if pos == "top":
        y = top + int(f.size * 1.85) + int(W * 0.06)
    else:
        y = (int(H * 0.74) if reel else H - int(W * 0.1)) - block
    yellow = n.marker if luminance(n.marker) > 0.6 else (255, 236, 90)
    for ln in lines:
        plain, styles = parse_rich(ln)
        xx = M
        for txt, st in _attach([plain], plain, styles)[0]:
            tw = _w(d, txt, fh)
            if st & 2:
                d.rectangle([xx - 10, y + int(size * 0.06), xx + tw + 10, y + int(size * 1.26)], fill=n.primary)
                d.text((xx, y), txt, font=fh, fill=PAPER)
            else:
                d.text((xx, y), txt, font=fh, fill=yellow if st & 1 else PAPER, stroke_width=stroke, stroke_fill=INK)
            xx += tw
        y += lh
    if post.get("lead") and pos == "top":
        fl = n.f(int(W * 0.04))
        y += int(W * 0.015)
        for ln in _wrap_c(d, post["lead"], fl, W - M * 2):
            d.text((M, y), ln, font=fl, fill=PAPER, stroke_width=4, stroke_fill=INK)
            y += int(fl.size * 1.5)
    if layers:
        return bg, img
    out = bg.convert("RGBA")
    out.alpha_composite(img)
    return out.convert("RGB")


def draw_cover_mock(n: Note, post: dict, W: int, H: int, reel: bool = False, page: str = "") -> Image.Image:
    """主色の背景に大きな白文字、下に実際の画面のような図を斜めに置く表紙。"""
    import designs  # 背景色は投稿ごとにピンク・紺・深緑から（グリッドが1色に偏らないように）
    designs._set_palette(n, post)
    bg = n.bg or n.primary
    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)
    light = mix(bg, PAPER, 0.12)
    d.ellipse([int(W * 0.25), int(H * 0.42), int(W * 1.45), int(H * 0.42) + int(W * 1.2)], fill=light)
    M = int(W * 0.075)
    top = int(H * 0.13) if reel else int(W * 0.075)
    f = n.f(int(W * 0.03))
    label = n.label
    pw = _w(d, label, f) + 44
    d.rounded_rectangle([M, top, M + pw, top + int(f.size * 1.8)], radius=int(f.size * 0.9), outline=PAPER, width=3)
    d.text((M + 22, top + int(f.size * 0.33)), label, font=f, fill=PAPER)
    if page and not post.get("cover_tag"):
        d.text((W - M - _w(d, page, f), top + int(f.size * 0.33)), page, font=f, fill=mix(bg, PAPER, 0.6))
    lines = post.get("cover_lines") or [post["title"]]
    plains = [strip_rich(x) for x in lines]
    size = _fit_size(d, plains, n, W - M * 2, int(W * (0.12 if reel else 0.112)), int(W * 0.06))
    fh = n.f(size)
    lh = int(size * 1.36)
    y = top + int(f.size * 1.8) + int(W * 0.07)
    hl = (255, 245, 126) if luminance(n.marker) > 0.6 else PAPER
    for ln in lines:
        plain, styles = parse_rich(ln)
        xx = M
        for txt, st in _attach([plain], plain, styles)[0]:
            if st & 2:
                tw = _w(d, txt, fh)
                d.rectangle([xx - 8, y + int(size * 0.04), xx + tw + 8, y + int(size * 1.28)], fill=hl)
                d.text((xx, y), txt, font=fh, fill=INK)
            else:
                d.text((xx, y), txt, font=fh, fill=hl if st & 1 else PAPER)
            xx += _w(d, txt, fh)
        y += lh
    if post.get("lead"):
        fl = n.f(int(W * 0.04), bold=False)
        y += int(W * 0.02)
        for ln in _wrap_c(d, post["lead"], fl, W - M * 2):
            d.text((M, y), ln, font=fl, fill=mix(bg, PAPER, 0.85))
            y += int(fl.size * 1.5)
    spec = dict(post["cover_mock"], _seed=post.get("id", ""))
    im = make_mock(n, spec, angle=float(spec.get("angle", -8)))
    t = spec.get("type", "map")
    s = W * (1.05 if t == "hp_pair" else (0.95 if t in ("dashboard", "card") else 0.78)) / im.width
    im = im.resize((int(im.width * s), int(im.height * s)), Image.LANCZOS)
    bottom_limit = int(H * 0.8) if reel else H
    py = y - int(W * 0.02)
    im = im.crop((0, 0, im.width, max(10, min(im.height, bottom_limit - py))))
    img.paste(im, ((W - im.width) // 2 + int(W * 0.03), py) if t == "card" else (W - im.width + int(W * 0.08), py), im)
    return img


def draw_cover_plain(n: Note, post: dict, W: int, H: int, reel: bool = False, page: str = "") -> Image.Image:
    bg = n.cover_bg
    img = _paper(W, H, bg=bg, grid=mix(bg, INK, 0.06))
    d = ImageDraw.Draw(img)
    M = int(W * 0.08)
    top = int(H * 0.14) if reel else int(W * 0.08)
    _header(d, n, W, M, top, page, faint=mix(bg, INK, 0.45))
    probe = n.f(100)
    lines = cover_lines(post, d, probe, W - M * 2 - 40)
    size = _fit_size(d, lines, n, W - M * 2 - 40, int(W * (0.13 if reel else 0.125)), int(W * 0.07))
    f = n.f(size)
    lh = int(size * 1.42)
    lead = post.get("lead") or ""
    fl = n.f(int(W * 0.044))
    lead_lines = _wrap_c(d, lead, fl, W - M * 2 - int(W * 0.06))
    llh = int(fl.size * 1.55)
    block = len(lines) * lh + (int(W * 0.08) + len(lead_lines) * llh + int(W * 0.05) if lead_lines else 0)
    y = (int(H * 0.40) if reel else int(H * 0.47)) - block // 2
    for i, ln in enumerate(lines):
        if i == len(lines) - 1:
            # 最後の行（言いたいこと）だけ主色の帯に白抜き
            tw = _w(d, ln, f)
            d.rectangle([M - 14, y + int(size * 0.02), M + tw + 22, y + int(size * 1.3)], fill=n.primary)
            d.text((M, y), ln, font=f, fill=n.on_primary)
        else:
            d.text((M, y), ln, font=f, fill=INK)
        y += lh
    if lead_lines:
        y += int(W * 0.06)
        bh = len(lead_lines) * llh + int(W * 0.05)
        d.rectangle([M, y, W - M, y + bh], fill=PAPER, outline=INK, width=4)
        _lines(d, M + int(W * 0.03), y + int(W * 0.025), lead_lines, fl, INK, llh)
    if reel:
        _footer(d, n, W, M, int(H * 0.74), "最後まで見て保存", mark=INK)
    else:
        _footer(d, n, W, M, H - int(W * 0.13), "保存して見返す", mark=INK)
    return img


# ---------------------------------------------------------------- 中身（kind ごと）
def _body_default(d, n, pt, x, y, w, W, dark=False) -> int:
    ft = n.f(int(W * 0.05))
    tl = _wrap_c(d, pt.get("t"), ft, w - int(W * 0.08))
    if not tl:
        return y
    tlh = int(ft.size * 1.65)
    bh = len(tl) * tlh + int(W * 0.06)
    if dark:
        _lines(d, x, y, tl, ft, (230, 232, 235), tlh)
        return y + len(tl) * tlh
    d.rectangle([x, y, x + w, y + bh], fill=n.tint)
    d.rectangle([x, y, x + 10, y + bh], fill=n.primary)
    _lines(d, x + int(W * 0.045), y + int(W * 0.03), tl, ft, INK, tlh)
    return y + bh


def _body_compare(d, n, pt, x, y, w, W) -> int:
    fl = n.f(int(W * 0.034))
    ft = n.f(int(W * 0.05))
    tlh = int(ft.size * 1.5)
    r = int(W * 0.028)
    for kind, label, text in (("ng", "よくある", pt.get("ng", "")), ("ok", "こうする", pt.get("ok", ""))):
        tl = _wrap_c(d, text, ft, w - int(W * 0.2))
        bh = max(len(tl), 1) * tlh + int(W * 0.13)
        ok = kind == "ok"
        d.rectangle([x, y, x + w, y + bh], fill=PAPER if ok else LIGHT, outline=n.primary if ok else LIGHT, width=6)
        cx, cy = x + int(W * 0.075), y + int(W * 0.075)
        if ok:
            _circle(d, cx, cy, r, n.primary, 9)
        else:
            _cross(d, cx, cy, int(r * 0.8), FAINT, 9)
        d.text((x + int(W * 0.14), y + int(W * 0.045)), label, font=fl, fill=n.primary if ok else FAINT)
        _lines(d, x + int(W * 0.14), y + int(W * 0.1), tl, ft, INK if ok else SUB, tlh)
        y += bh + int(W * 0.035)
        if not ok:
            # 下向きの三角
            ax = x + w // 2
            d.polygon([(ax - 26, y - int(W * 0.03)), (ax + 26, y - int(W * 0.03)), (ax, y - 4)], fill=FAINT)
            y += int(W * 0.005)
    return y


def _body_stat(d, n, pt, x, y, w, W) -> int:
    num = str(pt.get("num", ""))
    fn = n.f(int(W * 0.26))
    size = _fit_size(d, [num], n, w, fn.size, int(W * 0.12))
    fn = n.f(size)
    d.text((x - int(size * 0.03), y - int(size * 0.12)), num, font=fn, fill=n.primary)
    y += int(size * 1.05)
    lab = pt.get("num_label", "")
    if lab:
        fl = n.f(int(W * 0.055))
        ll = _wrap_c(d, lab, fl, w)
        y = _lines(d, x, y, ll, fl, INK, int(fl.size * 1.4), marker=n.marker)
        y += int(W * 0.04)
    ft = n.f(int(W * 0.045), bold=False)
    tl = _wrap_c(d, pt.get("t"), ft, w)
    return _lines(d, x, y, tl, ft, SUB, int(ft.size * 1.65))


def _body_check(d, n, pt, x, y, w, W) -> int:
    items = pt.get("items", [])[:5]
    few = len(items) <= 3
    many = len(items) >= 5
    fi = n.f(int(W * (0.064 if few else 0.051 if many else 0.056)))  # 項目が少ないときは大きく、間隔も広く
    s = int(W * (0.072 if few else 0.06 if many else 0.065))
    gap = int(W * (0.05 if few else 0.022 if many else 0.03))
    ng = pt.get("mark") == "x"  # やってはいけないことの一覧は ✕ で見せる
    for it in items:
        il = _wrap_c(d, it, fi, w - s - int(W * 0.08))
        ih = max(s, len(il) * int(fi.size * 1.4))
        if ng:
            r = s // 2
            _cross(d, x + r, y + 4 + r, int(r * 0.75), (210, 50, 60), 10)
        else:
            d.rectangle([x, y + 4, x + s, y + 4 + s], outline=INK, width=5)
            _check(d, x + 4, y - 6, s + 8, n.primary, 11)
        _lines(d, x + s + int(W * 0.04), y + int((s - fi.size) * 0.3), il, fi, INK, int(fi.size * 1.4))
        y += ih + gap
        d.line([(x, y - gap // 2), (x + w, y - gap // 2)], fill=GRID, width=3)
    if pt.get("t"):  # 補足（なぜ・どうやって）は項目の数にかかわらず出す
        y += int(W * (0.02 if few else 0.01))
        ft = n.f(int(W * (0.042 if few else 0.038)), bold=False)
        y = _lines(d, x, y, _wrap_c(d, pt["t"], ft, w), ft, SUB, int(ft.size * 1.65))
    return y


def _body_table(d, n, pt, x, y, w, W) -> int:
    """比較表。rows の1行目が見出し行。"""
    rows = pt.get("rows") or []
    if not rows:
        return y
    cols = len(rows[0])
    fh = n.f(int(W * 0.036))
    fb = n.f(int(W * 0.04), bold=False)
    first_w = int(w * (0.34 if cols >= 3 else 0.42))
    other_w = (w - first_w) // max(1, cols - 1)
    widths = [first_w] + [other_w] * (cols - 1)
    pad = int(W * 0.018)
    for r_i, row in enumerate(rows):
        f = fh if r_i == 0 else fb
        cells = [_wrap_c(d, str(c), f if c_i else fh, widths[c_i] - pad * 2) for c_i, c in enumerate(row)]
        rh = max(len(c) for c in cells) * int(f.size * 1.4) + pad * 2
        xx = x
        for c_i, lines in enumerate(cells):
            if r_i == 0:
                fill = n.primary if c_i == cols - 1 else INK
                tcol = PAPER
            else:
                fill = LIGHT if c_i == 0 else (n.tint if c_i == cols - 1 else PAPER)
                tcol = INK
            d.rectangle([xx, y, xx + widths[c_i], y + rh], fill=fill, outline=GRID, width=2)
            yy = y + pad
            for ln in lines:
                d.text((xx + pad, yy), ln, font=fh if (c_i == 0 or r_i == 0) else fb, fill=tcol)
                yy += int(f.size * 1.4)
            xx += widths[c_i]
        y += rh
    if pt.get("t"):
        y += int(W * 0.035)
        ft = n.f(int(W * 0.04), bold=False)
        y = _lines(d, x, y, _wrap_c(d, pt["t"], ft, w), ft, SUB, int(ft.size * 1.6))
    return y


def _body_template(d, n, pt, x, y, w, W) -> int:
    """そのまま使える文例。点線の枠に入れて、コピーして使える見た目にする。"""
    fl = n.f(int(W * 0.034))
    label = pt.get("label") or "そのまま使える文例"
    lw = _w(d, label, fl) + 36
    d.rounded_rectangle([x, y, x + lw, y + int(fl.size * 1.7)], radius=int(fl.size * 0.85), fill=n.primary)
    d.text((x + 18, y + int(fl.size * 0.32)), label, font=fl, fill=n.on_primary)
    y += int(fl.size * 2.2)
    ft = n.f(int(W * 0.044), bold=False)
    lines = []
    for para in str(pt.get("text", "")).split("\n"):
        lines += _wrap_c(d, para, ft, w - int(W * 0.1)) or [""]
    lh = int(ft.size * 1.6)
    bh = len(lines) * lh + int(W * 0.07)
    d.rectangle([x, y, x + w, y + bh], fill=(250, 250, 247))
    for xx in range(x, x + w, 22):  # 点線の枠
        d.line([(xx, y), (min(x + w, xx + 11), y)], fill=FAINT, width=3)
        d.line([(xx, y + bh), (min(x + w, xx + 11), y + bh)], fill=FAINT, width=3)
    for yy in range(y, y + bh, 22):
        d.line([(x, yy), (x, min(y + bh, yy + 11))], fill=FAINT, width=3)
        d.line([(x + w, yy), (x + w, min(y + bh, yy + 11))], fill=FAINT, width=3)
    _lines(d, x + int(W * 0.05), y + int(W * 0.035), lines, ft, INK, lh)
    y += bh
    if pt.get("t"):
        y += int(W * 0.03)
        fs = n.f(int(W * 0.038), bold=False)
        y = _lines(d, x, y, _wrap_c(d, pt["t"], fs, w), fs, SUB, int(fs.size * 1.6))
    return y


def _bubble(d, x, y, w, lines, f, lh, fill, outline, text_color, tail="left", pad=None) -> int:
    pad = pad or int(f.size * 0.9)
    bh = len(lines) * lh + pad * 2 - int(lh - f.size)
    d.rounded_rectangle([x, y, x + w, y + bh], radius=int(f.size * 0.9), fill=fill, outline=outline,
                        width=5 if outline else 0)
    tx = x + int(w * 0.14) if tail == "left" else x + int(w * 0.82)
    tri = [(tx, y + bh - 3), (tx + 46, y + bh - 3), (tx + (0 if tail == "left" else 46), y + bh + 44)]
    d.polygon(tri, fill=fill)
    if outline:
        d.line([tri[0], tri[2]] if tail == "left" else [tri[1], tri[2]], fill=outline, width=5)
        d.line([tri[2], tri[1]] if tail == "left" else [tri[2], tri[0]], fill=outline, width=5)
    _lines(d, x + pad, y + pad - int(f.size * 0.08), lines, f, text_color, lh)
    return y + bh + 44


def _body_voice(d, n, pt, x, y, w, W) -> int:
    fl = n.f(int(W * 0.034))
    d.text((x, y), pt.get("voice_label") or "患者さんの本音", font=fl, fill=n.primary)
    y += int(fl.size * 1.7)
    fv = n.f(int(W * 0.058))
    vl = _wrap_c(d, "「" + str(pt.get("voice", "")).strip("「」") + "」", fv, w - int(fv.size * 1.8))
    y = _bubble(d, x, y, w, vl, fv, int(fv.size * 1.45), PAPER, INK, INK)
    y += int(W * 0.05)
    ft = n.f(int(W * 0.045), bold=False)
    tl = _wrap_c(d, pt.get("t"), ft, w)
    return _lines(d, x, y, tl, ft, SUB, int(ft.size * 1.65))


def _body_qa(d, n, pt, x, y, w, W) -> int:
    fb = n.f(int(W * 0.05))
    lh = int(fb.size * 1.45)
    badge = int(W * 0.09)
    fbadge = n.f(int(W * 0.05))
    for who, text in (("Q", pt.get("q", "")), ("A", pt.get("a", ""))):
        isq = who == "Q"
        bw = w - badge - int(W * 0.03)
        bx = x + badge + int(W * 0.03) if isq else x
        cx = x if isq else x + w - badge
        tl = _wrap_c(d, text, fb, bw - int(fb.size * 1.8))
        d.ellipse([cx, y, cx + badge, y + badge], fill=INK if isq else n.primary)
        d.text((cx + badge // 2, y + badge // 2), who, font=fbadge, fill=PAPER, anchor="mm")
        y = _bubble(d, bx, y, bw, tl, fb, lh, LIGHT if isq else n.tint, None, INK, tail="left" if isq else "right")
        y += int(W * 0.03)
    return y


def _phone(d, x, y, pw, ph, btn_top: bool, n, good: bool) -> None:
    d.rounded_rectangle([x, y, x + pw, y + ph], radius=int(pw * 0.13), fill=PAPER, outline=INK, width=6)
    d.rounded_rectangle([x + pw * 0.38, y + 18, x + pw * 0.62, y + 32], radius=7, fill=INK)
    ix, iw = x + int(pw * 0.1), int(pw * 0.8)
    yy = y + int(ph * 0.09)
    blocks = [0.2, 0.06, 0.06, 0.06, 0.14, 0.06, 0.06]
    btn_h = int(ph * 0.085)
    if btn_top:
        d.rectangle([ix, yy + int(ph * 0.21), ix + iw, yy + int(ph * 0.21) + btn_h], fill=n.primary)
    for k, bh in enumerate(blocks):
        h = int(ph * bh)
        if btn_top and k == 1:
            yy += btn_h + int(ph * 0.02)
        d.rectangle([ix, yy, ix + (iw if k != 2 else int(iw * 0.7)), yy + h], fill=GRID if k else (214, 218, 223))
        yy += h + int(ph * 0.025)
    if not btn_top:
        by = y + ph - int(ph * 0.04) - btn_h
        d.rectangle([ix, by, ix + iw, by + btn_h], fill=FAINT)
    # 最初に見える範囲の目安線
    fold = y + int(ph * 0.42)
    for xx in range(x - 16, x + pw + 16, 22):
        d.line([(xx, fold), (xx + 11, fold)], fill=n.primary if good else FAINT, width=4)


def _body_phone(d, n, pt, x, y, w, W, max_h) -> int:
    fl = n.f(int(W * 0.04))
    gap = int(W * 0.08)
    col = (w - gap) // 2
    cap_h = int(fl.size * 1.35) * 3 + int(W * 0.08)
    ph = max(int(W * 0.25), min(int(col * 0.62 * 1.8), max_h - cap_h))
    pw = int(ph / 1.8)
    end = y
    for k, (txt, top) in enumerate(((pt.get("ng", ""), False), (pt.get("ok", ""), True))):
        cx0 = x + k * (col + gap)
        px = cx0 + (col - pw) // 2
        _phone(d, px, y, pw, ph, top, n, top)
        cy = y + ph + int(W * 0.05)
        r = int(W * 0.022)
        if top:
            _circle(d, cx0 + r, cy + int(fl.size * 0.6), r, n.primary, 8)
        else:
            _cross(d, cx0 + r, cy + int(fl.size * 0.6), int(r * 0.8), FAINT, 8)
        tl = _wrap_c(d, txt, fl, col - r * 2 - 18)
        end = max(end, _lines(d, cx0 + r * 2 + 18, cy, tl, fl, INK if top else SUB, int(fl.size * 1.35)))
    return end


# ---------------------------------------------------------------- 実際の画面のような図
def _text_card(n: Note, label: str, text: str, angle: float) -> Image.Image:
    cw = 900
    probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    fl, ft = n.f(34), n.f(46)
    lines = []
    for para in strip_rich(text).split(chr(10)):
        lines += wrap(probe, para, ft, cw - 140)
    lines = lines[:7]
    hh = 70 + int(fl.size * 2.2) + len(lines) * int(ft.size * 1.6) + 70
    card = Image.new("RGBA", (cw, hh), (0, 0, 0, 0))
    d = ImageDraw.Draw(card)
    d.rounded_rectangle([0, 0, cw - 1, hh - 1], radius=36, fill=(255, 255, 255, 255))
    lw = _w(d, label, fl) + 48
    d.rounded_rectangle([60, 60, 60 + lw, 60 + int(fl.size * 1.6)], radius=int(fl.size * 0.8), fill=n.primary)
    d.text((84, 60 + int(fl.size * 0.25)), label, font=fl, fill=PAPER)
    y = 70 + int(fl.size * 2.2)
    d.rectangle([60, y, 70, y + len(lines) * int(ft.size * 1.6) - 20], fill=n.primary)
    for ln in lines:
        d.text((96, y), ln, font=ft, fill=INK)
        y += int(ft.size * 1.6)
    out = Image.new("RGBA", (cw + 60, hh + 60), (0, 0, 0, 0))
    sh = Image.new("RGBA", card.size, (0, 0, 0, 255))
    sh.putalpha(card.getchannel("A").point(lambda v: int(v * 0.28)))
    out.alpha_composite(sh, (30, 40))
    out.alpha_composite(card, (20, 10))
    return out.rotate(angle, expand=True, resample=Image.BICUBIC) if angle else out


def cover_tag(d, n: Note, post: dict, W: int, y: int) -> None:
    """表紙の右上に「文例つき」などの小さな札を出す（保存したくなる中身があることを伝える）。"""
    tag = post.get("cover_tag")
    if not tag:
        return
    f = n.f(int(W * 0.036))
    tw = _w(d, tag, f)
    M = int(W * 0.06)
    x1 = W - M
    x0 = x1 - tw - int(W * 0.05)
    d.rounded_rectangle([x0, y, x1, y + int(f.size * 1.75)], radius=int(f.size * 0.4), fill=(255, 226, 64), outline=INK, width=4)
    d.text((x0 + int(W * 0.025), y + int(f.size * 0.3)), tag, font=f, fill=INK)


def make_mock(n: Note, spec: dict, angle: float = 0.0) -> Image.Image:
    import mockups as mk
    import random
    c = mk.Ctx(lambda size, bold: n.f(size, bold=bold), n.primary)
    t = spec.get("type", "map")
    rnd = random.Random(str(spec.get("_seed", "")) + t)
    args = {k: v for k, v in spec.items() if k not in ("type", "angle", "_seed")}
    if t in ("profile", "hp_bad", "hp_good") and "name" not in args:  # 医院名・見出しは投稿ごとに変える（同じ画面の使い回しに見せない）
        nm, hero, sub = rnd.choice([("あおば歯科医院", "駅前ロータリー前", "平日は19時まで"), ("ひかり内科クリニック", "夜19時まで診療", "WEB予約は24時間"),
                                    ("こもれび小児科", "予防接種もWEB予約", "駐輪場あり"), ("はなみずき歯科", "キッズスペースあり", "ベビーカーで入れます"),
                                    ("まつもと眼科", "駅ビル2階すぐ", "コンタクトの処方も"), ("いずみ皮フ科", "女性医師が在籍", "土曜午前も診療"),
                                    ("おおぞら整形外科", "リハビリ併設", "駐車場20台"), ("みどり台デンタルオフィス", "土曜も診療", "駐車場あり")])
        args["name"] = nm
        if t != "profile":
            args.setdefault("hero", hero)
            args.setdefault("sub", sub)
    if t == "map" and "names" not in args:
        pool = [("さくら歯科クリニック", "駅から徒歩3分"), ("みどり台デンタルオフィス", "土曜も診療"), ("あおば歯科医院", "駐車場あり"),
                ("ひかり内科クリニック", "夜19時まで"), ("こもれび小児科", "WEB予約可"), ("まつもと眼科", "駅前ビル2階"),
                ("いずみ皮フ科", "女性医師在籍"), ("おおぞら整形外科", "リハビリ併設"), ("はなみずき歯科", "キッズスペースあり")]
        rnd.shuffle(pool)
        args["names"] = [(nm, round(rnd.uniform(3.8, 4.8), 1), rnd.randint(18, 240), note) for nm, note in pool[:3]]
        args.setdefault("highlight", rnd.randint(0, 2))
        args.setdefault("pins", [(rnd.uniform(0.12, 0.88), rnd.uniform(0.18, 0.8)) for _ in range(3)])
    if t == "chat" and "answer" not in args:
        pool = [("さくら歯科クリニック", "駅から徒歩3分。土曜も診療"), ("みどり台デンタルオフィス", "土曜午後も予約可。駐車場あり"),
                ("ひかり内科クリニック", "夜19時まで。WEB予約あり"), ("こもれび小児科", "予防接種の予約がWEBで取れる"),
                ("いずみ皮フ科", "女性医師が在籍。駅前ビル2階"), ("はなみずき歯科", "キッズスペースあり。託児の相談可")]
        rnd.shuffle(pool)
        args["answer"] = pool[:2]
    if t == "dashboard":
        args.setdefault("chart", rnd.choice(["line", "bar"]))
        if "series" not in args:
            v = rnd.randint(30, 60)
            ser = []
            for _ in range(12):
                v = max(5, v + rnd.randint(-6, 11))
                ser.append(v)
            if str(args.get("delta", "")).strip().startswith(("-", "−")):
                ser[-1] = int(ser[-2] * 0.8)  # 下がった月は最後を下げる
            args["series"] = ser
        if "kpis" not in args:
            args["kpis"] = [("電話", str(rnd.randint(20, 120))), ("ルート検索", str(rnd.randint(40, 220))),
                            ("サイトへ", str(rnd.randint(60, 300)))]
        args.setdefault("value", f"{rnd.randint(300, 2400):,}")
        args.setdefault("delta", f"+{rnd.randint(4, 28)}%")
    if t == "card":  # 文例そのものを白いカードで見せる
        return _text_card(n, args.get("label", "文例"), args.get("text", ""), angle)
    if t == "map":
        return mk.phone(mk.map_search(c, **args), angle)
    if t == "chat":
        if "answer" in args:
            args["answer"] = [tuple(a) for a in args["answer"]]
        return mk.phone(mk.ai_chat(c, **args), angle)
    if t == "profile":
        return mk.phone(mk.place_profile(c, good=bool(args.get("good", True)), name=args.get("name", "さくら歯科クリニック"), W=600,
                                         H=1300), angle)
    if t == "hp_bad":
        return mk.phone(mk.clinic_hp(c, good=False, **args), angle)
    if t == "hp_good":
        return mk.phone(mk.clinic_hp(c, good=True, **args), angle)
    if t == "hp_pair":
        a = mk.phone(mk.clinic_hp(c, good=False), -4)
        b = mk.phone(mk.clinic_hp(c, good=True), 4)
        out = Image.new("RGBA", (int(a.width * 1.75), int(a.height * 1.04)), (0, 0, 0, 0))
        out.alpha_composite(a, (0, int(a.height * 0.04)))
        out.alpha_composite(b, (int(a.width * 0.75), 0))
        return out
    if "kpis" in args:
        args["kpis"] = [tuple(k) for k in args["kpis"]]
    return mk.card(mk.dashboard(c, **args), angle=angle)


def _body_mock(d, img, n, pt, x, y, w, W, max_h, W0) -> int:
    """図を大きく置き、下にはみ出す分は切る（端末を下からのぞかせる見せ方）。d が下書き用なら高さだけ返す。"""
    spec = dict(pt.get("mock", {}), _seed=pt.get("h", ""))
    t = spec.get("type", "map")
    im = make_mock(n, spec, angle=float(spec.get("angle", 0)))
    want_w = {"dashboard": w * 1.12, "hp_pair": W0 * 0.95}.get(t, W0 * 0.66)
    s = want_w / im.width
    if t == "dashboard":
        s = min(s, max(max_h, 200) * 1.1 / im.height)
    nw, nh = int(im.width * s), int(im.height * s)
    if getattr(d, "_image", None) is img:
        im = im.resize((nw, nh), Image.LANCZOS)
        top = y - int(nh * 0.03)
        keep = min(nh, y + max_h - top + int(W0 * 0.03))
        im = im.crop((0, 0, nw, keep))
        img.paste(im, ((W0 - nw) // 2, top), im)
    return y + min(int(nh * 0.9), max_h)

def draw_point(n: Note, pt: dict, idx: int, total: int, W: int, H: int, reel: bool = False, show_text: bool = True,
               page: str = "") -> Image.Image:
    kind = pt.get("kind", "default")
    dark = kind == "key"
    ink = PAPER if dark else INK
    img = _paper(W, H, bg=DARK, grid=(40, 43, 48)) if dark else _paper(W, H)
    d = ImageDraw.Draw(img)
    M = int(W * 0.08)
    cw = W - M * 2
    top = int(H * 0.12) if reel else int(W * 0.08)
    if reel:
        _progress(d, n, W, M, top, total, idx, off=(70, 74, 80) if dark else GRID)
        _header(d, n, W, M, top + 40, ink=ink)
    else:
        _header(d, n, W, M, top, page, ink=ink)
    foot_y = int(H * 0.74) if reel else H - int(W * 0.13)
    # 番号と見出し
    y = int(H * 0.2) if reel else int(H * 0.12)
    fn = n.f(int(W * 0.06))
    numtxt = "結論" if dark else point_label(n.form, idx)
    nw = _w(d, numtxt, fn)
    d.rectangle([M, y, M + nw + 36, y + int(fn.size * 1.35)], fill=n.marker if dark else n.primary)
    d.text((M + 18, y + int(fn.size * 0.12)), numtxt, font=fn, fill=INK if dark else n.on_primary)
    y += int(fn.size * 1.35) + int(W * 0.045)
    big = int(W * (0.115 if dark else 0.09))
    y = rich_heading(d, M, y, pt["h"], n, cw, big, int(W * 0.065), ink, lh_rate=1.36)
    y += int(W * 0.06)
    if show_text:
        fns = {"compare": _body_compare, "stat": _body_stat, "check": _body_check, "voice": _body_voice,
               "qa": _body_qa, "table": _body_table, "template": _body_template}
        limit = foot_y - int(W * 0.04)

        def run(dd, ws):
            if kind == "phone":
                return _body_phone(dd, n, pt, M, y, cw, ws, limit - y)
            if kind == "mock":
                return _body_mock(dd, img, n, pt, M, y, cw, ws, limit - y, W)
            if kind in fns:
                return fns[kind](dd, n, pt, M, y, cw, ws)
            return _body_default(dd, n, pt, M, y, cw, ws, dark=dark)

        # はみ出すときは文字を少しずつ小さくする
        scratch = ImageDraw.Draw(Image.new("RGB", (W, H)))
        ws = W
        for s in (1.0, 0.93, 0.86, 0.8, 0.74, 0.68):
            ws = int(W * s)
            if run(scratch, ws) <= limit:
                break
        FIT_LOG.append((pt.get("h", ""), ws / W))
        run(d, ws)
    if reel:
        _footer(d, n, W, M, foot_y, f"{idx} / {total}", ink=ink)
    else:
        _footer(d, n, W, M, foot_y, "次へ", ink=ink)
    return img


def draw_summary(n: Note, post: dict, pts: list[dict], W: int, H: int, reel: bool = False, page: str = "") -> Image.Image:
    img = _paper(W, H)
    d = ImageDraw.Draw(img)
    M = int(W * 0.08)
    top = int(H * 0.12) if reel else int(W * 0.08)
    if reel:
        _progress(d, n, W, M, top, len(pts), len(pts))
        _header(d, n, W, M, top + 40)
    else:
        _header(d, n, W, M, top, page)
    y = int(H * 0.2) if reel else int(H * 0.12)
    sm = summary_of(post, pts)
    ft = n.f(int(W * 0.075))
    _marker_line(d, M, y, sm["title"], ft, n.marker)
    d.text((M, y), sm["title"], font=ft, fill=INK)
    y += int(ft.size * 1.7)
    foot = int(H * 0.74) if reel else H - int(W * 0.13)
    fc = n.f(int(W * 0.044))
    cl = _wrap_c(d, one_cta(n.cfg, post), fc, W - M * 2 - int(W * 0.08))
    bh = len(cl) * int(fc.size * 1.5) + int(W * 0.08)
    cta_y = foot - int(W * 0.05) - bh  # 相談の一言は、フッターと重ならない位置に固定
    if sm["type"] == "one":
        # 1行のまとめは大きく、空いている場所の真ん中に置く
        probe = ImageDraw.Draw(Image.new("RGB", (W, H)))
        for big_r, note_r in ((0.105, 0.044), (0.09, 0.04), (0.078, 0.037), (0.068, 0.034)):
            big = int(W * big_r)
            hh = rich_heading(probe, M, 0, sm["text"], n, W - M * 2 - int(W * 0.05), big, int(big * 0.75), INK, lh_rate=1.38)
            fnote = n.f(int(W * note_r), bold=False)
            note_lines = _wrap_c(d, sm.get("note", ""), fnote, W - M * 2 - int(W * 0.05))
            nh = len(note_lines) * int(fnote.size * 1.65) + (int(W * 0.05) if note_lines else 0)
            if y + hh + nh <= cta_y - int(W * 0.04):  # 相談の帯に重ならない大きさを選ぶ
                break
        yy = y + max(0, (cta_y - y - hh - nh) // 2) - int(W * 0.02)
        d.rectangle([M, yy - int(W * 0.04), M + 14, yy + hh - int(W * 0.02)], fill=n.primary)
        rich_heading(d, M + int(W * 0.05), yy, sm["text"], n, W - M * 2 - int(W * 0.05), big, int(big * 0.75), INK,
                     lh_rate=1.38)
        if note_lines:  # 1行まとめの理由や目安を小さく添える
            _lines(d, M + int(W * 0.05), yy + hh + int(W * 0.03), note_lines, fnote, SUB, int(fnote.size * 1.65))
    elif sm["type"] == "template":
        probe = ImageDraw.Draw(Image.new("RGB", (W, H)))
        ws = W
        for s_ in (1.0, 0.93, 0.86, 0.8):
            ws = int(W * s_)
            if _body_template(probe, n, {"label": sm["label"], "text": sm["text"], "t": sm["note"]}, M, y, W - M * 2, ws) <= cta_y - int(W * 0.04):
                break
        _body_template(d, n, {"label": sm["label"], "text": sm["text"], "t": sm["note"]}, M, y, W - M * 2, ws)
    else:
        # 項目が多いときは、相談の一言に重ならない大きさまで小さくする
        for rate in (0.05, 0.046, 0.042, 0.038, 0.035):
            fi = n.f(int(W * rate))
            s_ = int(fi.size * 1.1)
            tot = sum(len(_wrap_c(d, it, fi, W - M * 2 - s_ - int(W * 0.05))) * int(fi.size * 1.4) + int(W * 0.03)
                      for it in sm["items"])
            if y + tot <= cta_y - int(W * 0.03):
                break
        y += max(0, (cta_y - int(W * 0.03) - y - tot) // 2)  # 項目のまとまりを、見出しと相談の帯のあいだの真ん中に置く（下を空けない）
        for it in sm["items"]:
            hl = _wrap_c(d, it, fi, W - M * 2 - s_ - int(W * 0.05))
            draw_mark(d, M, y + 6, s_, sm.get("mark", ""), INK)
            _lines(d, M + s_ + int(W * 0.035), y, hl, fi, INK, int(fi.size * 1.4))
            y += len(hl) * int(fi.size * 1.4) + int(W * 0.03)
    draw_cta_box(d, M, cta_y, W - M, cta_y + bh, cl, fc, int(fc.size * 1.5), cta_style(post), n.primary, n.on_primary,
                 INK, int(W * 0.04))
    _footer(d, n, W, M, foot, "保存して見返す")
    return img


# ---------------------------------------------------------------- 出力
def render_square(cfg: dict, post: dict, out_path: Path, size: int = 1080, reel: bool = False) -> Path:
    """表紙の画像。reel=True のときはリール用の縦長（1080x1920）。
    プロフィールの一覧ではリールの表紙が縦3:4（上下240pxずつを除いた範囲）に切られるので、文字はその中に収まる配置で描く。"""
    n = Note(cfg)
    w, h = (1080, 1440) if reel else (size, size)  # リールは、一覧で見える3:4で描いてから縦長に広げる
    if post.get("design", "note") != "note":
        import designs
        img = designs.draw_cover(n, post, w, h, post["design"])
    else:
        img = draw_cover(n, post, w, h)
    if reel:
        img = img.convert("RGB")
        full = Image.new("RGB", (1080, 1920))
        # 上下の余白は、表紙の上端・下端の平均の色でなめらかにつなぐ（ぼかした文字が見えないように）
        top = img.crop((0, 0, 1080, 12)).resize((1, 1), Image.BOX).getpixel((0, 0))
        bot = img.crop((0, 1428, 1080, 1440)).resize((1, 1), Image.BOX).getpixel((0, 0))
        full.paste(Image.new("RGB", (1080, 240), top), (0, 0))
        full.paste(Image.new("RGB", (1080, 240), bot), (0, 1680))
        full.paste(img, (0, 240))
        img = full
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "JPEG", quality=93)
    return out_path


def render_carousel(cfg: dict, post: dict, out_dir: Path, stem: str, W: int = 1080, H: int = 1350) -> list[Path]:
    n = Note(cfg)
    n.form = post.get("form")
    pts = points_of(post)
    total = len(pts) + 2
    design = post.get("design", "note")
    if design != "note":  # 色・写真の型（designs.py）
        import designs
        imgs = designs.render_pages(n, post, pts, W, H, design)
    else:
        imgs = [draw_cover(n, post, W, H)]  # 表紙にはページ番号を出さない（型によって有無がばらつかないように）
        for i, p in enumerate(pts, 1):
            imgs.append(draw_point(n, p, i, len(pts), W, H, page=f"{i + 1} / {total}"))
        imgs.append(draw_summary(n, post, pts, W, H, page=f"{total} / {total}"))
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, im in enumerate(imgs, 1):
        p = out_dir / f"{stem}_{i:02d}.jpg"
        im.save(p, "JPEG", quality=93)
        paths.append(p)
    return paths


def _read_sec(pt: dict) -> float:
    text = "".join(str(pt.get(k, "")) for k in ("t", "ng", "ok", "voice", "q", "a", "num_label")) + "".join(pt.get("items", []))
    if pt.get("kind") in ("compare", "check", "qa", "phone"):
        text = text.replace(str(pt.get("t", "")), "")
    return max(2.8, min(5.5, len(text) / 9))


def render_reel_frames(cfg: dict, post: dict, out_dir: Path, stem: str, W: int = 1080, H: int = 1920) -> list[tuple[Path, float]]:
    n = Note(cfg)
    n.form = post.get("form")
    pts = points_of(post)
    out_dir.mkdir(parents=True, exist_ok=True)
    seq: list[tuple[Image.Image, float]] = [(draw_cover(n, post, W, H, reel=True), 2.6)]
    for i, p in enumerate(pts, 1):
        seq.append((draw_point(n, p, i, len(pts), W, H, reel=True, show_text=False), 1.2))
        seq.append((draw_point(n, p, i, len(pts), W, H, reel=True, show_text=True), _read_sec(p)))
    seq.append((draw_summary(n, post, pts, W, H, reel=True), 4.5))
    frames = []
    for k, (im, sec) in enumerate(seq):
        p = out_dir / f"{stem}_n{k:02d}.jpg"
        im.save(p, "JPEG", quality=93)
        frames.append((p, sec))
    return frames
