"""実際の画面のように見える図（スマホの検索結果・分析画面・AIチャット・HP）をコードで描く。

AI 画像だと日本語が崩れるため、文字が入る画面はすべてここで描く。数字は「イメージ」として表示する。
どれも RGBA 画像を返す。phone() で枠を付けると端末の写真のように見える。
"""
from __future__ import annotations

import math

from PIL import Image, ImageDraw, ImageFilter

INK = (32, 33, 36)
SUB = (95, 99, 104)
FAINT = (154, 160, 166)
LINE = (226, 229, 233)
BG = (255, 255, 255)
GREEN = (24, 128, 56)
STAR = (251, 188, 4)
BLUE = (26, 115, 232)


class Ctx:
    def __init__(self, fonts, primary):
        self.fonts = fonts  # callable(size, bold) -> font
        self.primary = primary

    def f(self, s, bold=False):
        return self.fonts(int(s), bold)


def _star(d, cx, cy, r, fill):
    pts = []
    for i in range(10):
        a = math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.45
        pts.append((cx + rr * math.cos(a), cy - rr * math.sin(a)))
    d.polygon(pts, fill=fill)


def stars(d, x, y, r, value):
    for i in range(5):
        fill = STAR if value >= i + 0.75 else ((STAR if value >= i + 0.25 else LINE))
        _star(d, x + r + i * r * 2.2, y + r, r, fill)
    return x + 5 * r * 2.2


def status_bar(d, c: Ctx, W, y=0, dark=False):
    col = BG if dark else INK
    f = c.f(W * 0.04, True)
    d.text((W * 0.08, y + W * 0.035), "9:41", font=f, fill=col)
    bx = W * 0.82
    d.rounded_rectangle([bx, y + W * 0.045, bx + W * 0.08, y + W * 0.08], radius=6, outline=col, width=3)
    d.rectangle([bx + 5, y + W * 0.045 + 5, bx + W * 0.06, y + W * 0.08 - 5], fill=col)
    for i in range(4):
        h = W * 0.012 * (i + 1)
        d.rectangle([W * 0.7 + i * W * 0.018, y + W * 0.08 - h, W * 0.7 + i * W * 0.018 + W * 0.01, y + W * 0.08], fill=col)
    return y + W * 0.12


# ---------------------------------------------------------------- 地図つき検索結果
def map_search(c: Ctx, query="〇〇駅 歯医者", names=None, highlight=None, W=600, H=1300, pins=None) -> Image.Image:
    names = names or [("さくら歯科クリニック", 4.6, 128, "駅から徒歩3分"),
                      ("みどり台デンタルオフィス", 4.4, 86, "土曜も診療"),
                      ("あおば歯科医院", 4.1, 42, "駐車場あり")]
    img = Image.new("RGBA", (W, H), BG)
    d = ImageDraw.Draw(img)
    y = status_bar(d, c, W)
    # 検索窓
    sx, sw, sh = W * 0.05, W * 0.9, W * 0.13
    d.rounded_rectangle([sx, y, sx + sw, y + sh], radius=int(sh / 2), fill=BG, outline=LINE, width=3)
    fq = c.f(W * 0.045)
    d.text((sx + sh * 0.9, y + sh / 2), query, font=fq, fill=INK, anchor="lm")
    mx, my = sx + sh * 0.45, y + sh / 2
    d.ellipse([mx - 13, my - 15, mx + 9, my + 7], outline=SUB, width=4)
    d.line([(mx + 6, my + 4), (mx + 16, my + 14)], fill=SUB, width=4)
    y += sh + W * 0.04
    # タブ
    ft = c.f(W * 0.036)
    tx = W * 0.06
    for i, t in enumerate(["すべて", "地図", "画像", "ニュース", "動画"]):
        tw = d.textlength(t, font=ft)
        d.text((tx, y), t, font=ft, fill=BLUE if i == 0 else SUB)
        if i == 0:
            d.rectangle([tx, y + W * 0.062, tx + tw, y + W * 0.07], fill=BLUE)
        tx += tw + W * 0.06
    y += W * 0.075
    d.line([(0, y), (W, y)], fill=LINE, width=2)
    # 地図
    mh = W * 0.62
    m = Image.new("RGBA", (W, int(mh)), (236, 240, 228))
    md = ImageDraw.Draw(m)
    md.polygon([(0, mh * 0.62), (W * 0.32, mh * 0.5), (W * 0.38, mh), (0, mh)], fill=(205, 230, 200))
    md.ellipse([W * 0.62, mh * 0.08, W * 0.95, mh * 0.42], fill=(205, 230, 200))
    md.line([(W * 0.45, -10), (W * 0.62, mh + 10)], fill=(170, 210, 240), width=int(W * 0.05))
    for a, b, w in (((0, mh * 0.3), (W, mh * 0.22), 18), ((W * 0.2, 0), (W * 0.28, mh), 14), ((0, mh * 0.78), (W, mh * 0.7), 22),
                    ((W * 0.75, 0), (W * 0.7, mh), 12), ((W * 0.05, mh * 0.05), (W * 0.5, mh * 0.55), 8)):
        md.line([a, b], fill=(255, 255, 255), width=w)
    md.line([(0, mh * 0.78), (W, mh * 0.7)], fill=(255, 224, 140), width=10)
    for k, (px, py) in enumerate(pins or ((0.36, 0.42), (0.72, 0.58), (0.16, 0.2))):
        px, py = W * px, mh * py
        col = c.primary if (highlight is None or highlight == k) else (200, 70, 70)
        md.ellipse([px - 22, py - 54, px + 22, py - 10], fill=col)
        md.polygon([(px - 18, py - 26), (px + 18, py - 26), (px, py + 4)], fill=col)
        md.ellipse([px - 8, py - 40, px + 8, py - 24], fill=BG)
    img.paste(m, (0, int(y)))
    y += mh
    # 一覧
    fn = c.f(W * 0.05, True)
    fs = c.f(W * 0.036)
    for k, (name, rate, cnt, note) in enumerate(names):
        y0 = y
        y += W * 0.045
        if highlight == k:
            d.rectangle([0, y0, W, y0 + W * 0.33], fill=(255, 247, 214))
        d.text((W * 0.06, y), name, font=fn, fill=INK)
        y += W * 0.075
        d.text((W * 0.06, y), f"{rate}", font=fs, fill=SUB)
        ex = stars(d, W * 0.06 + d.textlength(f"{rate} ", font=fs), y + W * 0.006, W * 0.017, rate)
        d.text((ex + 8, y), f"({cnt})", font=fs, fill=SUB)
        y += W * 0.058
        d.text((W * 0.06, y), f"歯科医院・{note}", font=fs, fill=SUB)
        y += W * 0.058
        d.text((W * 0.06, y), "営業中", font=fs, fill=GREEN)
        d.text((W * 0.06 + d.textlength("営業中 ", font=fs), y), "・19:00 まで", font=fs, fill=SUB)
        th = W * 0.22
        d.rounded_rectangle([W * 0.7, y0 + W * 0.05, W * 0.7 + th, y0 + W * 0.05 + th], radius=14,
                            fill=(220 - k * 12, 228 - k * 8, 236))
        y = y0 + W * 0.33
        d.line([(W * 0.06, y), (W, y)], fill=LINE, width=2)
        if y > H - W * 0.1:
            break
    return img


# ---------------------------------------------------------------- 分析画面
def dashboard(c: Ctx, title="プロフィールの閲覧数", value="1,284", delta="+32%", series=None,
              kpis=None, W=900, H=760, chart="line") -> Image.Image:
    if not series:  # 下がった数字のときは、最後の月が下がるグラフにする（字幕・矢印と食い違わないように）
        down = str(delta).strip().startswith(("-", "−"))
        series = [60, 63, 61, 66, 64, 68, 70, 67, 69, 72, 70, 57] if down else [38, 42, 40, 47, 52, 50, 58, 63, 61, 70, 78, 86]
    kpis = kpis or [("電話", "86"), ("ルート検索", "142"), ("サイトへ", "211")]
    img = Image.new("RGBA", (W, H), BG)
    d = ImageDraw.Draw(img)
    P = W * 0.06
    fh = c.f(W * 0.034)
    d.text((P, P), title, font=fh, fill=SUB)
    fi = c.f(W * 0.036, True)  # 実際の数字と誤解されないよう、はっきり見える大きさで
    iw = d.textlength("イメージ", font=fi) + W * 0.04
    d.rounded_rectangle([W - P - iw, P - W * 0.008, W - P, P + fi.size * 1.35], radius=int(fi.size * 0.6), fill=(236, 238, 241))
    d.text((W - P - iw / 2, P + fi.size * 0.62), "イメージ", font=fi, fill=SUB, anchor="mm")
    fv = c.f(W * 0.1, True)
    d.text((P, P + W * 0.05), value, font=fv, fill=INK)
    vx = P + d.textlength(value, font=fv) + W * 0.03
    fd = c.f(W * 0.038, True)
    dw = d.textlength(delta, font=fd) + W * 0.05
    yy = P + W * 0.09
    down = str(delta).strip().startswith(("-", "−", "▲-"))  # 下がったときは赤い下向きの矢印
    col = (214, 69, 65) if down else GREEN
    d.rounded_rectangle([vx, yy, vx + dw, yy + W * 0.06], radius=int(W * 0.03), fill=(251, 232, 231) if down else (230, 244, 234))
    if down:
        d.polygon([(vx + W * 0.018, yy + W * 0.022), (vx + W * 0.03, yy + W * 0.044), (vx + W * 0.042, yy + W * 0.022)], fill=col)
    else:
        d.polygon([(vx + W * 0.018, yy + W * 0.04), (vx + W * 0.03, yy + W * 0.018), (vx + W * 0.042, yy + W * 0.04)], fill=col)
    d.text((vx + W * 0.048, yy + W * 0.03), str(delta).lstrip("+-−"), font=fd, fill=col, anchor="lm")
    # グラフ
    gx0, gx1 = P, W - P
    gy0, gy1 = P + W * 0.22, H - W * 0.25
    for i in range(4):
        gy = gy0 + (gy1 - gy0) * i / 3
        d.line([(gx0, gy), (gx1, gy)], fill=LINE, width=2)
    lo, hi = min(series) * 0.8, max(series) * 1.05
    pts = [(gx0 + (gx1 - gx0) * i / (len(series) - 1), gy1 - (gy1 - gy0) * (v - lo) / (hi - lo)) for i, v in enumerate(series)]
    if chart == "bar":  # 棒グラフ（最後の月だけ濃く）
        bw = (gx1 - gx0) / len(series) * 0.62
        for i, (px, py) in enumerate(pts):
            col = c.primary if i == len(pts) - 1 else tuple(int(v * 0.35 + 255 * 0.65) for v in c.primary)
            d.rounded_rectangle([px - bw / 2, py, px + bw / 2, gy1], radius=6, fill=col)
    else:
        fill = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        fd2 = ImageDraw.Draw(fill)
        fd2.polygon(pts + [(gx1, gy1), (gx0, gy1)], fill=c.primary + (40,))
        img.alpha_composite(fill)
        d.line(pts, fill=c.primary, width=int(W * 0.008), joint="curve")
        lx, ly = pts[-1]
        d.ellipse([lx - 12, ly - 12, lx + 12, ly + 12], fill=BG, outline=c.primary, width=6)
    fm = c.f(W * 0.026)
    for i, m in enumerate(["4月", "6月", "8月", "10月", "12月", "2月"]):
        d.text((gx0 + (gx1 - gx0) * i * 2 / (len(series) - 1), gy1 + W * 0.02), m, font=fm, fill=FAINT, anchor="ma")
    # 指標
    ky = H - W * 0.17
    kw = (W - P * 2 - W * 0.04) / len(kpis)
    for i, (k, v) in enumerate(kpis):
        kx = P + i * (kw + W * 0.02)
        d.rounded_rectangle([kx, ky, kx + kw, ky + W * 0.13], radius=int(W * 0.02), fill=(246, 247, 249))
        d.text((kx + W * 0.025, ky + W * 0.02), k, font=c.f(W * 0.028), fill=SUB)
        d.text((kx + W * 0.025, ky + W * 0.058), v, font=c.f(W * 0.05, True), fill=INK)
    return img


# ---------------------------------------------------------------- AI チャット
def ai_chat(c: Ctx, question="駅の近くで、土曜もやっている歯医者を教えて", answer=None, W=600, H=1300) -> Image.Image:
    answer = answer or [("さくら歯科クリニック", "駅から徒歩3分。土曜も診療。小児歯科あり"),
                        ("みどり台デンタルオフィス", "土曜午後も予約可。駐車場4台")]
    img = Image.new("RGBA", (W, H), BG)
    d = ImageDraw.Draw(img)
    y = status_bar(d, c, W)
    d.text((W / 2, y + W * 0.02), "AIアシスタント", font=c.f(W * 0.042, True), fill=INK, anchor="ma")
    y += W * 0.11
    d.line([(0, y), (W, y)], fill=LINE, width=2)
    y += W * 0.08
    fq = c.f(W * 0.044)
    from generate_image import wrap
    ql = wrap(d, question, fq, int(W * 0.6))
    qh = len(ql) * fq.size * 1.45 + W * 0.06
    qw = max(d.textlength(x, font=fq) for x in ql) + W * 0.08
    d.rounded_rectangle([W - W * 0.05 - qw, y, W - W * 0.05, y + qh], radius=int(W * 0.05), fill=(240, 242, 245))
    ty = y + W * 0.03
    for ln in ql:
        d.text((W - W * 0.05 - qw + W * 0.04, ty), ln, font=fq, fill=INK)
        ty += fq.size * 1.45
    y += qh + W * 0.08
    av = W * 0.09
    d.ellipse([W * 0.05, y, W * 0.05 + av, y + av], fill=INK)
    d.text((W * 0.05 + av / 2, y + av / 2), "AI", font=c.f(W * 0.034, True), fill=BG, anchor="mm")
    x0 = W * 0.05 + av + W * 0.04
    fa = c.f(W * 0.042)
    d.text((x0, y + W * 0.015), "条件に合う医院は、たとえば", font=fa, fill=INK)
    y += W * 0.1
    d.text((x0, y), "次の2つです。", font=fa, fill=INK)
    y += W * 0.1
    for i, (nm, desc) in enumerate(answer, 1):
        d.rounded_rectangle([x0, y, W - W * 0.05, y + W * 0.26], radius=int(W * 0.03), outline=LINE, width=3,
                            fill=(255, 251, 230) if i == 1 else BG)
        d.text((x0 + W * 0.04, y + W * 0.035), f"{i}. {nm}", font=c.f(W * 0.043, True), fill=INK)
        dl = wrap(d, desc, c.f(W * 0.035), int(W * 0.66))
        yy = y + W * 0.11
        for ln in dl[:2]:
            d.text((x0 + W * 0.04, yy), ln, font=c.f(W * 0.035), fill=SUB)
            yy += W * 0.055
        y += W * 0.3
    d.text((x0, y + W * 0.02), "情報元：各医院のホームページ", font=c.f(W * 0.03), fill=FAINT)
    # 入力欄
    d.rounded_rectangle([W * 0.05, H - W * 0.2, W * 0.95, H - W * 0.08], radius=int(W * 0.06), outline=LINE, width=3)
    d.text((W * 0.1, H - W * 0.14), "質問を入力", font=c.f(W * 0.038), fill=FAINT, anchor="lm")
    return img


# ---------------------------------------------------------------- 医院 HP（スマホ）
def clinic_hp(c: Ctx, good=True, name="さくら歯科クリニック", W=600, H=1300, hero="駅から徒歩3分",
              sub="土曜も診療しています") -> Image.Image:
    img = Image.new("RGBA", (W, H), BG)
    d = ImageDraw.Draw(img)
    y = status_bar(d, c, W)
    d.rectangle([0, y, W, y + W * 0.13], fill=BG)
    d.text((W * 0.06, y + W * 0.065), name, font=c.f(W * (0.045 if good else 0.03), True), fill=INK, anchor="lm")
    for i in range(3):
        d.rectangle([W * 0.84, y + W * 0.045 + i * W * 0.025, W * 0.94, y + W * 0.052 + i * W * 0.025], fill=INK)
    y += W * 0.13
    if good:
        hero_img = Image.new("RGBA", (W, int(W * 0.7)), (0, 0, 0, 0))
        hd = ImageDraw.Draw(hero_img)
        for k in range(int(W * 0.7)):
            t = k / (W * 0.7)
            hd.line([(0, k), (W, k)], fill=(int(214 + 20 * t), int(232 + 10 * t), int(240 + 8 * t)))
        img.paste(hero_img, (0, int(y)))
        d.text((W * 0.06, y + W * 0.38), hero, font=c.f(W * 0.07, True), fill=INK)
        d.text((W * 0.06, y + W * 0.48), sub, font=c.f(W * 0.045), fill=SUB)
        y += W * 0.74
        d.rounded_rectangle([W * 0.06, y, W * 0.94, y + W * 0.15], radius=int(W * 0.075), fill=c.primary)
        d.text((W / 2, y + W * 0.075), "WEBで予約する", font=c.f(W * 0.05, True), fill=BG, anchor="mm")
        y += W * 0.19
        d.rounded_rectangle([W * 0.06, y, W * 0.94, y + W * 0.15], radius=int(W * 0.075), outline=c.primary, width=4)
        d.text((W / 2, y + W * 0.075), "電話する", font=c.f(W * 0.05, True), fill=c.primary, anchor="mm")
        y += W * 0.22
        for k in range(3):
            d.rounded_rectangle([W * 0.06, y, W * 0.94, y + W * 0.16], radius=16, fill=(246, 247, 249))
            d.text((W * 0.1, y + W * 0.08), ["診療時間", "診療内容", "アクセス"][k], font=c.f(W * 0.042, True), fill=INK, anchor="lm")
            y += W * 0.19
    else:
        d.rectangle([0, y, W, y + W * 0.45], fill=(210, 212, 216))
        y += W * 0.5
        fs = c.f(W * 0.022)
        for k in range(26):
            d.text((W * 0.04, y), "当院では患者様一人ひとりに寄り添った診療を心がけております。" if k % 3 else "■お知らせ 2019年 年末年始の休診について",
                   font=fs, fill=SUB)
            y += W * 0.034
        d.rectangle([W * 0.04, H - W * 0.12, W * 0.4, H - W * 0.06], fill=(200, 200, 200))
        d.text((W * 0.22, H - W * 0.09), "ご予約", font=fs, fill=INK, anchor="mm")
    return img


# ---------------------------------------------------------------- 端末の枠と影
def phone(screen: Image.Image, angle: float = 0.0) -> Image.Image:
    W, H = screen.size
    b = int(W * 0.045)
    r = int(W * 0.14)
    body = Image.new("RGBA", (W + b * 2, H + b * 2), (0, 0, 0, 0))
    bd = ImageDraw.Draw(body)
    bd.rounded_rectangle([0, 0, body.width - 1, body.height - 1], radius=r + b, fill=(26, 27, 30))
    bd.rounded_rectangle([3, 3, body.width - 4, body.height - 4], radius=r + b - 3, outline=(70, 72, 78), width=3)
    mask = Image.new("L", screen.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, W - 1, H - 1], radius=r, fill=255)
    body.paste(screen, (b, b), mask)
    bd.rounded_rectangle([body.width / 2 - W * 0.14, b + W * 0.025, body.width / 2 + W * 0.14, b + W * 0.075],
                         radius=int(W * 0.025), fill=(10, 10, 12))
    return _shadow(body, angle)


def card(img: Image.Image, radius: int = 28, angle: float = 0.0) -> Image.Image:
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, img.width - 1, img.height - 1], radius=radius, fill=255)
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return _shadow(out, angle)


def _shadow(im: Image.Image, angle: float) -> Image.Image:
    if angle:
        im = im.rotate(angle, expand=True, resample=Image.BICUBIC)
    pad = int(max(im.size) * 0.08)
    out = Image.new("RGBA", (im.width + pad * 2, im.height + pad * 2), (0, 0, 0, 0))
    sh = Image.new("RGBA", out.size, (0, 0, 0, 0))
    alpha = im.split()[3].point(lambda a: int(a * 0.28))
    sh.paste((20, 20, 30, 255), (pad, pad + int(pad * 0.45)), alpha)
    sh = sh.filter(ImageFilter.GaussianBlur(pad * 0.45))
    out.alpha_composite(sh)
    out.alpha_composite(im, (pad, pad))
    return out


# ---------------------------------------------------------------- 検索の入力中（キーボード付き）
def search_typing(c: Ctx, text: str, cursor: bool = True, W=600, H=1300, suggest=None) -> Image.Image:
    img = Image.new("RGBA", (W, H), BG)
    d = ImageDraw.Draw(img)
    y = status_bar(d, c, W)
    sx, sw, sh = W * 0.05, W * 0.9, W * 0.13
    d.rounded_rectangle([sx, y, sx + sw, y + sh], radius=int(sh / 2), fill=BG, outline=BLUE, width=4)
    fq = c.f(W * 0.045)
    tx = sx + sh * 0.9
    if text:
        d.text((tx, y + sh / 2), text, font=fq, fill=INK, anchor="lm")
    else:
        d.text((tx, y + sh / 2), "検索またはURLを入力", font=fq, fill=FAINT, anchor="lm")
    if cursor:
        cx = tx + (d.textlength(text, font=fq) if text else 0) + 4
        d.rectangle([cx, y + sh * 0.25, cx + 4, y + sh * 0.75], fill=BLUE)
    mx, my = sx + sh * 0.45, y + sh / 2
    d.ellipse([mx - 13, my - 15, mx + 9, my + 7], outline=SUB, width=4)
    d.line([(mx + 6, my + 4), (mx + 16, my + 14)], fill=SUB, width=4)
    y += sh + W * 0.04
    fs = c.f(W * 0.042)
    for sg in (suggest or ([text + " 土曜", text + " 口コミ", text + " 予約"] if text else [])):
        d.ellipse([W * 0.07, y + 8, W * 0.07 + 30, y + 38], outline=FAINT, width=3)
        d.text((W * 0.15, y), sg, font=fs, fill=INK)
        y += W * 0.11
    # キーボード
    ky = H - W * 0.78
    d.rectangle([0, ky, W, H], fill=(209, 212, 219))
    rows = ["あかさたなはまやらわ", "いきしちにひみゆりを", "うくすつぬふむよるん"]
    kw = W / 10
    for r, row in enumerate(rows):
        for k, ch in enumerate(row):
            x0 = k * kw + 5
            y0 = ky + W * 0.03 + r * W * 0.13
            d.rounded_rectangle([x0, y0, x0 + kw - 10, y0 + W * 0.11], radius=10, fill=BG)
            d.text((x0 + (kw - 10) / 2, y0 + W * 0.055), ch, font=c.f(W * 0.045), fill=INK, anchor="mm")
    by = ky + W * 0.03 + 3 * W * 0.13
    d.rounded_rectangle([W * 0.2, by, W * 0.7, by + W * 0.11], radius=10, fill=BG)
    d.text((W * 0.45, by + W * 0.055), "空白", font=c.f(W * 0.04), fill=INK, anchor="mm")
    d.rounded_rectangle([W * 0.72, by, W * 0.98, by + W * 0.11], radius=10, fill=BLUE)
    d.text((W * 0.85, by + W * 0.055), "検索", font=c.f(W * 0.04, True), fill=BG, anchor="mm")
    return img


# ---------------------------------------------------------------- 医院のプロフィール（Google マップ風）
def place_profile(c: Ctx, good=True, name="さくら歯科クリニック", W=600, H=1300) -> Image.Image:
    img = Image.new("RGBA", (W, H), BG)
    d = ImageDraw.Draw(img)
    y = status_bar(d, c, W)
    ph = W * 0.5
    if good:
        cols = [(196, 214, 228), (226, 214, 200), (208, 226, 210)]
        d.rectangle([0, y, W * 0.6, y + ph], fill=cols[0])
        d.rectangle([W * 0.61, y, W, y + ph / 2 - 2], fill=cols[1])
        d.rectangle([W * 0.61, y + ph / 2 + 2, W, y + ph], fill=cols[2])
        d.rounded_rectangle([W * 0.66, y + ph - 60, W * 0.97, y + ph - 14], radius=20, fill=(0, 0, 0))
        d.text((W * 0.815, y + ph - 37), "写真 48枚", font=c.f(W * 0.032, True), fill=BG, anchor="mm")
    else:
        d.rectangle([0, y, W, y + ph], fill=(214, 216, 220))
        d.rounded_rectangle([W * 0.7, y + ph - 60, W * 0.97, y + ph - 14], radius=20, fill=(0, 0, 0))
        d.text((W * 0.835, y + ph - 37), "写真 1枚", font=c.f(W * 0.032, True), fill=BG, anchor="mm")
    y += ph + W * 0.05
    d.text((W * 0.06, y), name, font=c.f(W * 0.062, True), fill=INK)
    y += W * 0.1
    fs = c.f(W * 0.038)
    rate, cnt = (4.6, 128) if good else (3.2, 4)
    d.text((W * 0.06, y), f"{rate}", font=fs, fill=SUB)
    ex = stars(d, W * 0.06 + d.textlength(f"{rate} ", font=fs), y + 6, W * 0.018, rate)
    d.text((ex + 8, y), f"({cnt})・歯科医院", font=fs, fill=SUB)
    y += W * 0.1
    for k, lab in enumerate(["経路", "電話", "保存", "共有"]):
        cx = W * (0.14 + k * 0.24)
        d.ellipse([cx - W * 0.055, y, cx + W * 0.055, y + W * 0.11], outline=LINE, width=3, fill=(232, 240, 254) if k == 0 else BG)
        d.text((cx, y + W * 0.15), lab, font=c.f(W * 0.032), fill=BLUE, anchor="ma")
    y += W * 0.24
    d.line([(0, y), (W, y)], fill=LINE, width=2)
    rows = ([("営業時間", "営業中・19:00 まで", GREEN), ("住所", "〇〇市〇〇町1-2-3", INK), ("ウェブサイト", "sakura-dental.jp", BLUE),
             ("診療内容", "一般歯科・小児歯科・矯正", INK)] if good else
            [("営業時間", "営業時間を追加", BLUE), ("住所", "〇〇市〇〇町1-2-3", INK), ("ウェブサイト", "ウェブサイトを追加", BLUE),
             ("診療内容", "未登録", FAINT)])
    y += W * 0.04
    for lab, val, col in rows:
        d.text((W * 0.06, y), lab, font=c.f(W * 0.032), fill=SUB)
        d.text((W * 0.06, y + W * 0.05), val, font=c.f(W * 0.044, True), fill=col)
        y += W * 0.15
        d.line([(W * 0.06, y - W * 0.025), (W, y - W * 0.025)], fill=LINE, width=2)
    return img
