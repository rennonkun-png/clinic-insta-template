"""スマホを実際に操作しているように見せるリール（画面収録風）。

投稿データの "reel" に台本を書くと、その順に場面を作る。
  {"hook": {"photo": "assets/photos/xxx.jpg", "lines": ["その医院、", "*検索で*出てきます？"]},
   "scenes": [
     {"type": "type",    "query": "〇〇駅 歯医者", "say": "患者さんと同じように検索してみます"},
     {"type": "results", "say": "まず出てくるのは、HPじゃなくて*地図*"},
     {"type": "zoom_top3", "say": "この*3件*に入れるかで決まります"},
     {"type": "profile", "good": false, "say": "情報が古いと…"},
     {"type": "profile", "good": true,  "say": "…"},
     {"type": "chat", "question": "…", "say": "…"},
     {"type": "checklist", "title": "…", "items": [...], "say": "…"},
     {"type": "end", "lines": [...], "say": "…"}]}
字幕（say）は *強調* が使える。1 場面 2〜4 秒で、テンポよく切り替える。
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

import mockups as mk
import note_style as ns
from common import log
import voice
from reel_anim import FPS, H, W, Writer, _zoom, hold_until, ease_back, ease_in_out, ease_out

SW, SH = 780, 1690                      # スマホ画面の大きさ
PX, PY = (W - SW) // 2, 520             # 画面の左上（ステージ上）
BEZ = 30
STAGE_BG = (18, 19, 24)
RED = (230, 50, 60)


class Ctx:
    def __init__(self, cfg: dict, post: dict):
        self.n = ns.Note(cfg)
        self.post = post
        self.c = mk.Ctx(lambda s, b: self.n.f(s, bold=b), self.n.primary)
        self.mask = Image.new("L", (SW, SH), 0)
        ImageDraw.Draw(self.mask).rounded_rectangle([0, 0, SW - 1, SH - 1], radius=int(SW * 0.12), fill=255)
        self.bg = self._stage_bg()

    def _stage_bg(self) -> Image.Image:
        img = Image.new("RGB", (W, H), STAGE_BG)
        glow = Image.new("RGB", (W, H), STAGE_BG)
        ImageDraw.Draw(glow).ellipse([-200, 900, W + 200, 2600], fill=ns.mix(STAGE_BG, self.n.primary, 0.35))
        return Image.blend(img, glow.filter(ImageFilter.GaussianBlur(160)), 0.9)

    # ---- ステージ（背景＋スマホ）
    def stage(self, screen: Image.Image, phone_dy: int = 0, bg: Image.Image | None = None) -> Image.Image:
        st = (bg or self.bg).copy()
        d = ImageDraw.Draw(st)
        x0, y0 = PX - BEZ, PY - BEZ + phone_dy
        d.rounded_rectangle([x0, y0, x0 + SW + BEZ * 2, y0 + SH + BEZ * 2], radius=int(SW * 0.12) + BEZ, fill=(8, 8, 10),
                            outline=(70, 72, 78), width=4)
        st.paste(screen.convert("RGB"), (PX, PY + phone_dy), self.mask)
        d.rounded_rectangle([W / 2 - SW * 0.14, PY + phone_dy + 18, W / 2 + SW * 0.14, PY + phone_dy + 56], radius=19,
                            fill=(8, 8, 10))
        return st

    # ---- 字幕
    def caption(self, text: str, y: int = 190, size: float = 0.072, box: bool = True) -> Image.Image:
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        if not text:
            return layer
        d = ImageDraw.Draw(layer)
        n = self.n
        f = n.f(int(W * size))
        plain, styles = ns.parse_rich(text)
        from generate_image import words_fit
        while not words_fit(d, plain, f, int(W * 0.9)) and f.size > W * 0.05:  # 語の途中で切らない
            f = n.f(int(f.size * 0.94))
        if not box and "\n" not in plain:  # 大きな1行の文字は、はみ出さない大きさまで縮めて1行に収める
            while f.size > W * 0.055 and d.textlength(plain, font=f) > W * 0.9:
                f = n.f(int(f.size * 0.94))
        lines = ns.wrap(d, plain, f, int(W * 0.9)) if "\n" not in plain else plain.split("\n")
        runs_all = ns._attach(lines, plain, styles)
        lh = int(f.size * 1.32)
        stroke = max(6, int(f.size * 0.11))
        yellow = n.marker if ns.luminance(n.marker) > 0.6 else (255, 236, 90)
        if box:  # 下の画面と重なっても読めるよう、うすい黒の帯を敷く
            widths = [sum(d.textlength(t, font=f) for t, _ in runs) for runs in runs_all]
            bw = max(widths) + f.size * 1.2
            d.rounded_rectangle([(W - bw) / 2, y - f.size * 0.35, (W + bw) / 2, y + len(runs_all) * lh + f.size * 0.1],
                                radius=int(f.size * 0.5), fill=(0, 0, 0, 165))
        for i, runs in enumerate(runs_all):
            tw = sum(d.textlength(t, font=f) for t, _ in runs)
            x = (W - tw) / 2
            for t, st in runs:
                d.text((x, y + i * lh), t, font=f, fill=yellow if st & 1 else (255, 255, 255), stroke_width=stroke,
                       stroke_fill=(10, 10, 12))
                x += d.textlength(t, font=f)
        return layer


def _pop(layer: Image.Image, t: float, dur: float = 0.35) -> Image.Image:
    """字幕を少し大きい状態からポンと出す。"""
    if t >= dur:
        return layer
    e = ease_back(t / dur)
    a = ease_out(t / (dur * 0.6))
    s = 0.86 + 0.14 * e
    box = layer.getbbox()
    if not box:
        return layer
    piece = layer.crop(box)
    pw, ph = max(1, int(piece.width * s)), max(1, int(piece.height * s))
    piece = piece.resize((pw, ph), Image.BILINEAR)
    piece.putalpha(piece.getchannel("A").point(lambda v: int(v * a)))
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    cx, cy = (box[0] + box[2]) // 2, (box[1] + box[3]) // 2
    out.alpha_composite(piece, (cx - pw // 2, cy - ph // 2))
    return out


def _over(base: Image.Image, layer: Image.Image) -> Image.Image:
    b = base.convert("RGBA")
    b.alpha_composite(layer)
    return b.convert("RGB")


def _stamp(d, x, y, r, good: bool, color) -> None:
    if good:
        d.ellipse([x - r, y - r, x + r, y + r], outline=color, width=max(6, r // 4))
    else:
        w = max(7, r // 4)
        d.line([(x - r, y - r), (x + r, y + r)], fill=RED, width=w)
        d.line([(x - r, y + r), (x + r, y - r)], fill=RED, width=w)


class ScreenReel:
    def __init__(self, cfg: dict, post: dict, out: Path):
        self.x = Ctx(cfg, post)
        self.cfg, self.post = cfg, post
        self.spec = post["reel"]
        self.out = out
        self.screen: Image.Image | None = None  # 今スマホに映っている画面
        self.last: Image.Image | None = None    # 直前のコマ

    def put(self, wr: Writer, im: Image.Image) -> None:
        wr.put(im)
        self.last = im

    # ---------------------------------------------------------------- 場面
    def hook(self, wr: Writer, sec: float = 1.9) -> None:
        hk = self.spec["hook"]
        n = self.x.n
        bg = ns._photo_fill(hk["photo"], W, H, float(hk.get("focus", 0.35))) if hk.get("photo") else self.x.bg
        shade = Image.new("RGBA", (W, H), (0, 0, 0, 120))
        layers = []
        y0 = int(H * 0.3)
        for i, ln in enumerate(hk["lines"]):
            layers.append(self.x.caption(ln, y=y0 + i * int(W * 0.13), size=0.105, box=False))
        label = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(label)
        f = n.f(int(W * 0.036))
        lab = n.label
        lw = d.textlength(lab, font=f) + 56
        d.rounded_rectangle([(W - lw) / 2, y0 - 130, (W + lw) / 2, y0 - 130 + f.size * 1.9], radius=int(f.size), fill=n.primary)
        d.text((W / 2, y0 - 130 + f.size * 0.95), lab, font=f, fill=n.on_primary, anchor="mm")
        steps = int(sec * FPS)
        for k in range(steps):
            t = k / FPS
            fr = _zoom(bg.convert("RGB"), 1.0 + 0.16 * ease_out(k / steps), 0.4).convert("RGBA")
            fr.alpha_composite(shade)
            fr.alpha_composite(_pop(label, t))
            for i, ly in enumerate(layers):
                tt = t - 0.12 - i * 0.14
                if tt > 0:
                    fr.alpha_composite(_pop(ly, tt, 0.38))
            self.put(wr, fr.convert("RGB"))

    def _phone_in(self, wr: Writer, screen: Image.Image, cap: Image.Image, sec: float = 0.45) -> None:
        """表紙からスマホが下から入ってくる。"""
        prev = self.last
        steps = int(sec * FPS)
        for k in range(1, steps + 1):  # 前の場面を薄めながら、同じコマでスマホが上がってくる（空のコマを挟まない）
            e = ease_out(k / steps)
            st = _over(self.x.stage(screen, phone_dy=int((1 - e) * 900)), _pop(cap, k / FPS + 0.15))
            if prev is not None and k <= 3:
                st = Image.blend(prev.convert("RGB"), st.convert("RGB"), k / 3)
            self.put(wr, st)
        self.screen = screen

    def _swap(self, wr: Writer, new: Image.Image, cap: Image.Image, sec: float = 0.3) -> None:
        """スマホの中で画面が横に切り替わる。"""
        old = self.screen
        steps = int(sec * FPS)
        for k in range(1, steps + 1):
            e = ease_in_out(k / steps)
            dx = int(SW * e)
            scr = Image.new("RGB", (SW, SH), (255, 255, 255))
            scr.paste(old.convert("RGB"), (-dx, 0))
            scr.paste(new.convert("RGB"), (SW - dx, 0))
            self.put(wr, _over(self.x.stage(scr), _pop(cap, k / FPS)))
        self.screen = new

    def _show(self, wr: Writer, screen: Image.Image, cap: Image.Image) -> None:
        """スマホが出ていなければ下から入れ、出ていれば画面を切り替える。"""
        if self.screen is None:
            self._phone_in(wr, screen, cap)
        else:
            self._swap(wr, screen, cap)

    def _push_to(self, wr: Writer, nxt: Image.Image, sec: float = 0.35) -> None:
        steps = int(sec * FPS)
        prev = self.last
        for k in range(1, steps + 1):
            e = ease_in_out(k / steps)
            fr = Image.new("RGB", (W, H))
            fr.paste(prev, (-int(W * e), 0))
            fr.paste(nxt, (W - int(W * e), 0))
            self.put(wr, fr)
        self.screen = None

    def _hold(self, wr: Writer, cap: Image.Image, sec: float, t0: float, cam=None, extra=None) -> None:
        steps = int(sec * FPS)
        for k in range(steps):
            st = self.x.stage(self.screen)
            if extra:
                st = extra(st, k / max(1, steps - 1))
            if cam:
                z, cx, cy = cam(k / max(1, steps - 1))
                st = _cam(st, z, cx, cy)
            self.put(wr, _over(st, _pop(cap, t0 + k / FPS)))

    def type_search(self, wr: Writer, sc: dict, first: bool) -> None:
        c = self.x.c
        q = sc.get("query", "〇〇駅 歯医者")
        cap = self.x.caption(sc.get("say", ""))
        empty = mk.search_typing(c, "", W=SW, H=SH)
        self._show(wr, empty, cap)
        t = 0.45
        per = max(0.09, min(0.16, 1.4 / max(1, len(q))))
        for i in range(1, len(q) + 1):
            self.screen = mk.search_typing(c, q[:i], W=SW, H=SH)
            self._hold(wr, cap, per, t)
            t += per
        self._hold(wr, cap, 0.35, t)
        # 検索キーをタップ
        ky = SH - SW * 0.78
        bx, by = PX + SW * 0.85, PY + ky + SW * 0.03 + 3 * SW * 0.13 + SW * 0.055

        def ripple(st, p):
            d = ImageDraw.Draw(st, "RGBA")
            r = 20 + 90 * ease_out(p)
            d.ellipse([bx - r, by - r, bx + r, by + r], fill=(255, 255, 255, int(150 * (1 - p))))
            return st
        self._hold(wr, cap, 0.3, t + 0.35, extra=ripple)
        self.query = q

    def results(self, wr: Writer, sc: dict) -> None:
        c = self.x.c
        cap = self.x.caption(sc.get("say", ""))
        import random
        rnd = random.Random(self.x.post.get("id", ""))
        pool = [("さくら歯科クリニック", "駅から徒歩3分"), ("みどり台デンタルオフィス", "土曜も診療"), ("あおば歯科医院", "駐車場あり"),
                ("ひかり内科クリニック", "夜19時まで"), ("こもれび小児科", "WEB予約可"), ("まつもと眼科", "駅前ビル2階"),
                ("いずみ皮フ科", "女性医師在籍"), ("はなみずき歯科", "キッズスペースあり")]
        rnd.shuffle(pool)
        names = [(nm, round(rnd.uniform(3.8, 4.8), 1), rnd.randint(18, 240), note) for nm, note in pool[:3]]
        res = mk.map_search(c, query=getattr(self, "query", "〇〇駅 歯医者"), names=names, highlight=rnd.randint(0, 2), W=SW, H=SH)
        if self.screen is None:
            self._phone_in(wr, mk.search_typing(c, getattr(self, "query", "〇〇駅 歯医者"), cursor=False, W=SW, H=SH, suggest=[]), cap)
        top = mk.search_typing(c, getattr(self, "query", ""), cursor=False, W=SW, H=SH, suggest=[])
        steps = int(0.5 * FPS)
        cut = int(SW * 0.37)
        for k in range(1, steps + 1):
            e = ease_out(k / steps)
            scr = Image.new("RGB", (SW, SH), (255, 255, 255))
            scr.paste(res.convert("RGB").crop((0, 0, SW, cut)), (0, 0))
            off = int((1 - e) * 500)
            body = res.convert("RGB").crop((0, cut, SW, SH - off))
            scr.paste(body, (0, cut + off))
            if k < steps // 2:
                scr = Image.blend(top.convert("RGB"), scr, k / (steps / 2))
            self.screen = scr
            self.put(wr, _over(self.x.stage(scr), _pop(self.x.caption(sc.get("say", "")), k / FPS)))
        self.screen = res
        self._hold(wr, cap, float(sc.get("sec", 2.4)), 0.5)

    def zoom_top3(self, wr: Writer, sc: dict) -> None:
        cap = self.x.caption(sc.get("say", ""))
        y0 = PY + SW * 0.985 - 10
        y1 = PY + SW * (0.985 + 0.33 * 3) + 4
        cy = (y0 + y1) / 2

        def frame(st, p):
            d = ImageDraw.Draw(st, "RGBA")
            a = ease_out(p / 0.25)
            d.rounded_rectangle([PX + 10, y0, PX + SW - 10, y1], radius=26, outline=self.x.n.primary + (int(255 * a),), width=12)
            return st
        self._hold(wr, cap, float(sc.get("sec", 2.6)), 0.0, cam=lambda p: (1 + 0.32 * ease_in_out(min(1, p / 0.45)), W / 2, cy),
                   extra=frame)

    def profile(self, wr: Writer, sc: dict) -> None:
        good = bool(sc.get("good", True))
        cap = self.x.caption(sc.get("say", ""))
        scr = mk.place_profile(self.x.c, good=good, W=SW, H=SH)
        self._show(wr, scr, cap)
        rows_y = SW * (0.12 + 0.5 + 0.05 + 0.1 + 0.1 + 0.24 + 0.04)
        marks = [(PX + SW * 0.86, PY + SW * 0.12 + SW * 0.5 - 37)] + [
            (PX + SW * 0.86, PY + rows_y + SW * 0.15 * i + SW * 0.07) for i in ((0, 2, 3) if not good else (0, 3))]
        col = self.x.n.primary

        def stamps(st, p):
            d = ImageDraw.Draw(st)
            for i, (mx, my) in enumerate(marks):
                q = (p * len(marks) * 1.6) - i * 0.5
                if q > 0:
                    r = int(34 * min(1.0, ease_back(min(1.0, q))))
                    _stamp(d, mx, my, max(4, r), good, col)
            return st
        self._hold(wr, cap, float(sc.get("sec", 2.8)), 0.3, cam=lambda p: (1 + 0.12 * ease_in_out(p), W / 2, PY + SH * 0.45),
                   extra=stamps)

    def chat(self, wr: Writer, sc: dict, first: bool) -> None:
        cap = self.x.caption(sc.get("say", ""))
        import random
        rnd = random.Random(self.x.post.get("id", "") + "chat")
        pool = [("さくら歯科クリニック", "駅から徒歩3分。土曜も診療"), ("みどり台デンタルオフィス", "土曜午後も予約可。駐車場あり"),
                ("ひかり内科クリニック", "夜19時まで。WEB予約あり"), ("こもれび小児科", "予防接種の予約がWEBで取れる"),
                ("いずみ皮フ科", "女性医師が在籍。駅前ビル2階"), ("はなみずき歯科", "キッズスペースあり。託児の相談可")]
        rnd.shuffle(pool)
        full = mk.ai_chat(self.x.c, question=sc.get("question", "駅の近くで、土曜もやっている歯医者を教えて"),
                          answer=sc.get("answer") and [tuple(a) for a in sc["answer"]] or pool[:2], W=SW, H=SH)
        self._show(wr, full, cap)
        # 回答が上から順に出てくる
        base = full.copy()
        y_cut = int(SW * 0.62)
        ImageDraw.Draw(base).rectangle([0, y_cut, SW, SH - SW * 0.22], fill=(255, 255, 255))
        steps = int(float(sc.get("sec", 3.0)) * FPS)
        for k in range(steps):
            p = min(1.0, k / (steps * 0.6))
            h = int((SH - SW * 0.22 - y_cut) * ease_in_out(p))
            scr = base.copy()
            scr.paste(full.crop((0, y_cut, SW, y_cut + h)), (0, y_cut))
            self.screen = scr
            self.put(wr, _over(self.x.stage(scr), _pop(cap, 0.3 + k / FPS)))
        self.screen = full

    def checklist(self, wr: Writer, sc: dict) -> None:
        n = self.x.n
        items = sc.get("items", [])
        card = ns._paper(W, H)
        d = ImageDraw.Draw(card)
        M = int(W * 0.09)
        ft = n.f(int(W * 0.095))
        fi = n.f(int(W * 0.084)) if len(items) <= 4 else n.f(int(W * 0.072))
        tmpd = ImageDraw.Draw(Image.new("RGB", (8, 8)))
        title_txt = ns.strip_rich(sc.get("title", ""))
        while tmpd.textlength(title_txt, font=ft) > W - M * 2 and ft.size > W * 0.06:
            ft = n.f(int(ft.size * 0.94))
        while items and max(tmpd.textlength(it, font=fi) for it in items) > W - M * 2 - fi.size * 1.2 - W * 0.04                 and fi.size > W * 0.052:
            fi = n.f(int(fi.size * 0.94))
        block = int(ft.size * 1.9) + len(items) * int(fi.size * 1.9)
        cap_h = int(W * 0.072 * 1.32) * (sc.get("say", "").count("\n") + 1) + int(W * 0.08)
        y = max(int(H * 0.2), (H - block - cap_h) // 2 + int(H * 0.03))  # 画面の縦の真ん中に
        cap_y = y + block + int(W * 0.06)
        ns._marker_line(d, M, y, ns.strip_rich(sc.get("title", "")), ft, n.marker)
        d.text((M, y), ns.strip_rich(sc.get("title", "")), font=ft, fill=ns.INK)
        y += int(ft.size * 1.9)
        s = int(fi.size * 1.15)
        rows = []
        for it in items:
            d.rectangle([M, y + 4, M + s, y + 4 + s], outline=ns.INK, width=6)
            rows.append((M, y, s))
            d.text((M + s + int(W * 0.04), y - 2), it, font=fi, fill=ns.INK)
            y += int(fi.size * 1.9)
        cap = self.x.caption(sc.get("say", ""), y=cap_y, box=True)  # 白地に縁取り文字は汚く見えるので帯付き
        empty = ns._paper(W, H)
        # 1 項目ずつ出てチェックが付く
        per = 0.5
        total = int((per * len(items) + float(sc.get("sec", 1.6))) * FPS)
        title_part = card.crop((0, 0, W, rows[0][1] - 10)) if rows else card
        first = empty.copy()
        first.paste(title_part, (0, 0))
        self._push_to(wr, first)
        for k in range(total):
            t = k / FPS + 0.15
            fr = empty.copy()
            fr.paste(title_part, (0, 0))
            for i, (x, yy, s_) in enumerate(rows):
                ti = t - i * per
                if ti <= 0:
                    continue
                e = ease_out(ti / 0.3)
                off = int((1 - e) * 60)
                band = card.crop((0, yy - 8, W, yy + int(fi.size * 1.6)))
                fr.paste(band, (0, yy - 8 + off))
                if ti > 0.22:
                    dd = ImageDraw.Draw(fr)
                    q = min(1.0, (ti - 0.22) / 0.2)
                    pts = [(x + s_ * 0.15, yy + s_ * 0.55), (x + s_ * 0.42, yy + s_ * 0.85), (x + s_ * 1.05, yy - s_ * 0.05)]
                    if q < 0.5:
                        a, b = pts[0], pts[1]
                        dd.line([a, (a[0] + (b[0] - a[0]) * q * 2, a[1] + (b[1] - a[1]) * q * 2)], fill=n.primary, width=14)
                    else:
                        dd.line([pts[0], pts[1], (pts[1][0] + (pts[2][0] - pts[1][0]) * (q - 0.5) * 2,
                                                  pts[1][1] + (pts[2][1] - pts[1][1]) * (q - 0.5) * 2)], fill=n.primary, width=14,
                                joint="curve")
            if cap.getbbox() and t > per * len(items) * 0.5:
                fr = _over(fr, _pop(cap, t - per * len(items) * 0.5))
            self.put(wr, fr)

    def end(self, wr: Writer, sc: dict) -> None:
        style = sc.get("style") or self.x.post.get("end_style") or "save"
        if style == "ask":
            return self.end_ask(wr, sc)
        if style == "recap":
            return self.end_recap(wr, sc)
        n = self.x.n
        bg = Image.new("RGB", (W, H), n.primary)
        lines = [self.x.caption(ln, y=int(H * 0.32) + i * int(W * 0.15), size=0.11, box=False) for i, ln in enumerate(sc.get("lines", []))]
        cap = self.x.caption(sc.get("say", ""), y=int(H * 0.56), size=0.074, box=False)
        cb = cap.getbbox()
        mark_y = (cb[3] if cb else int(H * 0.6)) + 50
        first = bg.convert("RGBA")
        for ly in lines:
            first.alpha_composite(ly)
        self._push_to(wr, first.convert("RGB"))
        total = int(float(sc.get("sec", 3.2)) * FPS)
        for k in range(total):
            t = k / FPS + 0.6  # 文字は入ってきた時点で出ている
            fr = bg.convert("RGBA")
            for i, ly in enumerate(lines):
                if t - i * 0.15 > 0:
                    fr.alpha_composite(_pop(ly, t - i * 0.15, 0.4))
            if t > 0.5:
                fr.alpha_composite(_pop(cap, t - 0.5))
            if t > 0.8:  # 保存アイコンが弾む
                d = ImageDraw.Draw(fr)
                bounce = abs(((t - 0.8) * 2.2) % 2 - 1)
                hh = 120
                bx, by = W // 2 - 43, mark_y + 30 - int(30 * bounce)
                ns._bookmark(d, bx, by, hh, (255, 255, 255))
            self.put(wr, fr.convert("RGB"))


    def end_ask(self, wr: Writer, sc: dict) -> None:
        """締め: 院長に問いかけて、コメントを促す（黒地に吹き出し）。"""
        n = self.x.n
        bg = Image.new("RGB", (W, H), (22, 24, 30))
        q = sc.get("ask") or "あなたの医院では、どうしていますか？"
        f = n.f(int(W * 0.074))
        d0 = ImageDraw.Draw(bg)
        ql = ns.wrap(d0, q, f, int(W * 0.74))
        lh = int(f.size * 1.45)
        bw, bh_ = int(W * 0.84), len(ql) * lh + int(W * 0.12)
        bx, by = (W - bw) // 2, max(int(H * 0.2), (int(H * 0.8) - bh_ - 360) // 2)  # まとまりを縦の真ん中に
        bubble = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        db = ImageDraw.Draw(bubble)
        db.rounded_rectangle([bx, by, bx + bw, by + bh_], radius=48, fill=(255, 255, 255, 255))
        db.polygon([(bx + 120, by + bh_ - 2), (bx + 190, by + bh_ - 2), (bx + 110, by + bh_ + 70)], fill=(255, 255, 255, 255))
        yy = by + int(W * 0.06)
        for ln in ql:
            db.text((W / 2, yy), ln, font=f, fill=ns.INK + (255,), anchor="ma")
            yy += lh
        cap = self.x.caption("コメントで*教えてください*", y=by + bh_ + 150, size=0.068, box=False)
        sub = self.x.caption(sc.get("say", "") or "保存して、あとで見返してください", y=by + bh_ + 290, size=0.06, box=False)
        first = bg.convert("RGBA")
        first.alpha_composite(bubble)
        self._push_to(wr, first.convert("RGB"))
        for k in range(int(float(sc.get("sec", 3.2)) * FPS)):
            t = k / FPS
            fr = bg.convert("RGBA")
            fr.alpha_composite(bubble, (0, -int(10 * math.sin(t * 3))))
            if t > 0.3:
                fr.alpha_composite(_pop(cap, t - 0.3))
            if t > 0.8:
                fr.alpha_composite(_pop(sub, t - 0.8))
            self.put(wr, fr.convert("RGB"))

    def end_recap(self, wr: Writer, sc: dict) -> None:
        """締め: おさらい（ポイントが1つずつ出る）→ 保存を促す。"""
        n = self.x.n
        sm = self.x.post.get("summary") or {}
        if sm.get("items"):
            heads, title = list(sm["items"])[:5], sm.get("title") or "今日やること"
        elif sm.get("type") == "template" and sm.get("text"):
            heads, title = [x for x in ns.strip_rich(sm["text"]).split(chr(10)) if x.strip()][:3], sm.get("title") or "そのまま使える文面"
        elif sm.get("text"):
            heads, title = [ns.strip_rich(sm["text"])], sm.get("title") or "次の一歩"  # 補足の文は項目にしない
        else:
            heads, title = [ns.strip_rich(sc.get("say", "")) or "保存して、あとで見返してください"], "次の一歩"
        bg = ns._paper(W, H)
        d0 = ImageDraw.Draw(bg)
        M = int(W * 0.09)
        ft = n.f(int(W * 0.088))
        say = sc.get("say", "") or "保存して、あとで見返してください"
        cap_h = int(W * 0.05 * 1.4) * (2 if len(say) > 16 else 1) + 90
        for r in (0.074, 0.066, 0.058, 0.052, 0.046):  # 項目と保存の帯が、画面の下20%より上に収まる大きさ
            fi = n.f(int(W * r))
            est = int(ft.size * 2.0)
            for h in heads:
                est += max(1, len(ns.wrap(d0, h, fi, int(W - M * 2 - fi.size * 1.8)))) * int(fi.size * 1.4) + int(W * 0.04)
            if int(H * 0.14) + est + cap_h <= int(H * 0.8):
                break
        y0 = max(int(H * 0.14), (int(H * 0.8) - est - cap_h) // 2)
        ns._marker_line(d0, M, y0, title, ft, n.marker)
        d0.text((M, y0), title, font=ft, fill=ns.INK)
        rows, y = [], y0 + int(ft.size * 2.0)
        for i, h in enumerate(heads, 1):
            ly = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            dl = ImageDraw.Draw(ly)
            dl.ellipse([M, y, M + int(fi.size * 1.3), y + int(fi.size * 1.3)], fill=n.primary + (255,))
            dl.text((M + int(fi.size * 0.65), y + int(fi.size * 0.65)), str(i), font=n.f(int(fi.size * 0.8)), fill=(255, 255, 255, 255), anchor="mm")
            hl = ns.wrap(dl, h, fi, int(W - M * 2 - fi.size * 1.8))
            yy = y + int(fi.size * 0.1)
            for ln in hl:
                dl.text((M + int(fi.size * 1.8), yy), ln, font=fi, fill=ns.INK + (255,))
                yy += int(fi.size * 1.4)
            rows.append(ly)
            y = max(yy, y + int(fi.size * 1.4)) + int(W * 0.04)
        cap = self.x.caption(say, y=y + 40, size=0.05, box=True)  # 項目のすぐ下（重ならない）
        self._push_to(wr, bg)
        per = 0.45
        total = int((per * len(rows) + float(sc.get("sec", 2.4))) * FPS)
        for k in range(total):
            t = k / FPS
            fr = bg.convert("RGBA")
            for i, ly in enumerate(rows):
                ti = t - i * per
                if ti > 0:
                    e = ease_out(min(1.0, ti / 0.3))
                    piece = ly.copy()
                    piece.putalpha(piece.getchannel("A").point(lambda v, e=e: int(v * e)))
                    fr.alpha_composite(piece, (int((1 - e) * 80), 0))
            if t > per * len(rows):
                fr.alpha_composite(_pop(cap, t - per * len(rows)))
            self.put(wr, fr.convert("RGB"))

    def hp(self, wr: Writer, sc: dict) -> None:
        """医院 HP をスマホで開いて、ゆっくり下にスクロールする。"""
        good = bool(sc.get("good", True))
        cap = self.x.caption(sc.get("say", ""))
        import random
        rnd = random.Random(self.x.post.get("id", "") + "hp")
        name, hero, sub = rnd.choice([("あおば歯科医院", "駅前ロータリー前", "平日は19時まで"), ("ひかり内科クリニック", "夜19時まで診療", "WEB予約は24時間"),
                                      ("こもれび小児科", "予防接種もWEB予約", "駐輪場あり"), ("はなみずき歯科", "キッズスペースあり", "ベビーカーで入れます"),
                                      ("まつもと眼科", "駅ビル2階すぐ", "コンタクトの処方も"), ("さくら歯科クリニック", "駅から徒歩3分", "土曜も診療しています")])
        scr = mk.clinic_hp(self.x.c, good=good, name=name, hero=hero, sub=sub, W=SW, H=SH)
        self._show(wr, scr, cap)
        steps = int(float(sc.get("sec", 2.6)) * FPS)
        for k in range(steps):
            p = ease_in_out(k / max(1, steps - 1))
            st = self.x.stage(self.screen)
            if not good and k > steps * 0.3:
                d = ImageDraw.Draw(st)
                q = min(1.0, (k - steps * 0.3) / (steps * 0.15))
                _stamp(d, PX + SW * 0.82, PY + SH * 0.45, int(46 * ease_back(q)) + 4, False, self.x.n.primary)
            st = _cam(st, 1 + 0.14 * p, W / 2, PY + SH * 0.4)  # 画面にゆっくり寄る
            self.put(wr, _over(st, _pop(cap, 0.3 + k / FPS)))

    def dashboard(self, wr: Writer, sc: dict) -> None:
        """分析画面のカード。グラフが左から伸び、数字が数え上がる。"""
        cap = self.x.caption(sc.get("say", ""))
        title = sc.get("title", "プロフィールの閲覧数（イメージ）")
        target = int(str(sc.get("value", "1284")).replace(",", ""))
        delta = sc.get("delta", "+32%")
        kpis = [tuple(k) for k in sc["kpis"]] if sc.get("kpis") else None  # 下段の数字も内容に合わせる
        cw = int(W * 0.88)
        ch = int(cw * 760 / 900)
        cx0, cy0 = (W - cw) // 2, int(H * 0.36)
        mask = Image.new("L", (cw, ch), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, cw - 1, ch - 1], radius=36, fill=255)
        steps = int(float(sc.get("sec", 3.0)) * FPS)
        first = self.x.bg.copy()
        kp0 = [(k, "–") for k, _ in kpis] if kpis else [("電話", "–"), ("ルート検索", "–"), ("サイトへ", "–")]
        first.paste(mk.dashboard(self.x.c, title=title, value="0", delta="+0%", kpis=kp0, series=[1] * 11 + [1.01], W=cw,
                                 H=ch).convert("RGB"), (cx0, cy0), mask)
        self._push_to(wr, first)
        for k in range(steps):
            p = ease_out(min(1.0, k / (steps * 0.65)))
            val = f"{int(target * p):,}"
            try:  # 増加率も数字と一緒に数え上げる
                dnum = float(str(delta).strip("+%"))
                v = int(round(dnum * p))
                dshow = f"{'-' if dnum < 0 else '+'}{abs(v)}%"  # 下がった数字は「-」のまま数える
            except ValueError:
                dshow = delta
            kp = kpis if p >= 0.999 else ([(k, "–") for k, _ in kpis] if kpis else [("電話", "–"), ("ルート検索", "–"), ("サイトへ", "–")])
            card = mk.dashboard(self.x.c, title=title, value=val, delta=dshow, kpis=kp, W=cw, H=ch).convert("RGB")
            if p < 1:
                blank = mk.dashboard(self.x.c, title=title, value=val, delta=dshow, kpis=kp, series=[1] * 11 + [1.01], W=cw,
                                     H=ch).convert("RGB")
                cut = int(cw * (0.06 + 0.88 * p))
                blank.paste(card.crop((0, int(ch * 0.25), cut, int(ch * 0.78))), (0, int(ch * 0.25)))
                card = blank
            st = self.x.bg.copy()
            st.paste(card, (cx0, cy0), mask)
            self.put(wr, _over(st, _pop(cap, k / FPS)))

    def compare(self, wr: Writer, sc: dict) -> None:
        """よくある（✕）→ こうする（○）のカードが順に出る。"""
        n = self.x.n
        cap = self.x.caption(sc.get("say", ""))
        cards = []
        f_l = n.f(int(W * 0.046))
        f_t = n.f(int(W * 0.07))
        tmp = ImageDraw.Draw(Image.new("RGB", (10, 10)))
        for kind, label, txt in (("ng", "よくある", sc.get("ng", "")), ("ok", "こうする", sc.get("ok", ""))):
            cw = int(W * 0.86)  # 左右に余白をとる
            tl = ns.wrap(tmp, txt, f_t, int(cw * 0.78))
            chh = int(len(tl) * f_t.size * 1.45 + W * 0.2)
            card = Image.new("RGB", (cw, chh), (255, 255, 255) if kind == "ok" else (238, 239, 242))
            d = ImageDraw.Draw(card)
            if kind == "ok":
                d.rectangle([0, 0, cw - 1, chh - 1], outline=n.primary, width=10)
            r = int(W * 0.035)
            _stamp(d, int(W * 0.09), int(W * 0.09), r, kind == "ok", n.primary)
            d.text((int(W * 0.17), int(W * 0.055)), label, font=f_l, fill=n.primary if kind == "ok" else (130, 134, 140))
            yy = int(W * 0.12)
            for ln in tl:
                d.text((int(W * 0.17), yy), ln, font=f_t, fill=ns.INK)
                yy += int(f_t.size * 1.45)
            cards.append(card)
        steps = int(float(sc.get("sec", 3.2)) * FPS)
        tot = sum(c.height for c in cards) + int(W * 0.06)
        y_top = max(int(H * 0.26), (H - tot) // 2 + int(H * 0.04))  # 2枚のまとまりを縦の真ん中に
        first = self.x.bg.copy()
        first.paste(cards[0], (int((W - cards[0].width) / 2), y_top))
        self._push_to(wr, first)
        for k in range(steps):
            t = k / FPS + 0.5  # 1枚目は入ってきた時点で出ている
            st = self.x.bg.copy()
            y = y_top
            for i, card in enumerate(cards):
                ti = t - i * 0.9 + 0.25  # 1枚目は切り替えと同時に入ってくる
                if ti > 0:
                    e = ease_back(min(1.0, ti / 0.4))
                    x = int((W - card.width) / 2 + (1 - e) * W * 0.6)
                    st.paste(card, (x, y))
                y += card.height + int(W * 0.06)
            self.put(wr, _over(st, _pop(cap, t + 0.2)))

    def text(self, wr: Writer, sc: dict) -> None:
        """言いたいことを大きな文字だけで見せる。"""
        import random
        n = self.x.n
        rnd = random.Random(self.x.post.get("id", "") + "text")
        label = sc.get("label") or rnd.choice(["ここが大事", "覚えておきたい", "ひとこと", "先に知っておく"])
        cw = int(W * 0.86)
        P = int(W * 0.07)
        probe = ImageDraw.Draw(Image.new("RGB", (W, H)))
        head = "\n".join(sc.get("lines", []))
        hh = ns.rich_heading(probe, 0, 0, head, n, cw - P * 2, int(W * 0.105), int(W * 0.075), ns.INK, lh_rate=1.3)
        fs = n.f(int(W * 0.046), bold=False)
        sl = ns._wrap_c(probe, ns.strip_rich(sc.get("say", "")), fs, cw - P * 2)
        fl = n.f(int(W * 0.036))
        lab_h = int(fl.size * 1.9)
        ch = P + lab_h + int(W * 0.05) + hh + int(W * 0.05) + len(sl) * int(fs.size * 1.6) + P
        card = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        d = ImageDraw.Draw(card)
        d.rounded_rectangle([0, 0, cw - 1, ch - 1], radius=int(W * 0.04), fill=(255, 255, 255, 255))
        lw = int(d.textlength(label, font=fl)) + 48
        d.rounded_rectangle([P, P, P + lw, P + lab_h], radius=lab_h // 2, fill=n.primary)
        d.text((P + 24, P + int(fl.size * 0.4)), label, font=fl, fill=n.on_primary)
        y = P + lab_h + int(W * 0.05)
        ns.rich_heading(d, P, y, head, n, cw - P * 2, int(W * 0.105), int(W * 0.075), ns.INK, accent=n.primary, lh_rate=1.3)
        y += hh + int(W * 0.03)
        d.rectangle([P, y, P + int(W * 0.12), y + 8], fill=n.primary)
        y += int(W * 0.04)
        for ln in sl:
            d.text((P, y), ln, font=fs, fill=ns.SUB)
            y += int(fs.size * 1.6)
        cx, cy = (W - cw) // 2, max(int(H * 0.2), (H - ch) // 2 - int(H * 0.03))
        bg = self.x.bg
        first = bg.convert("RGBA")
        first.alpha_composite(card, (cx, cy))
        self._push_to(wr, first.convert("RGB"))
        steps = int(float(sc.get("sec", 2.6)) * FPS)
        for k in range(steps):
            z = 1.0 + 0.04 * (k / max(1, steps - 1))  # 止まって見えないよう、ゆっくり寄る
            c2 = card.resize((int(cw * z), int(ch * z)), Image.BILINEAR)
            fr = bg.convert("RGBA")
            fr.alpha_composite(c2, (cx - (c2.width - cw) // 2, cy - (c2.height - ch) // 2))
            self.put(wr, fr.convert("RGB"))

    # ---------------------------------------------------------------- 全体
    def render(self) -> Path:
        wr = Writer(self.out, 60)
        nar = voice.Narration(self.cfg, self.post, self.out.parent / f"{self.out.stem}_voice")

        def voiced(idx, start):
            last = hold_until(wr, start, nar.need(idx), self.last)
            if last is not None:
                self.last = last

        nar.mark(0, 0.0)
        self.hook(wr)
        voiced(0, 0)
        first_phone = True
        for si, sc in enumerate(self.spec.get("scenes", []), 1):
            start = wr.n
            nar.mark(si, start / FPS)
            self._scene(wr, sc, first_phone)
            if sc.get("type") in ("type", "chat"):
                first_phone = False
            voiced(si, start)
        sec = wr.close()
        nar.mux(self.out, sec)
        log(f"リール動画を生成しました: {self.out} ({sec:.1f}秒)")
        return self.out

    def _scene(self, wr: Writer, sc: dict, first_phone: bool) -> None:
        if True:
            t = sc.get("type")
            if t == "type":
                self.type_search(wr, sc, first_phone)
            elif t == "chat":
                self.chat(wr, sc, first_phone)
            elif t == "results":
                self.results(wr, sc)
            elif t == "zoom_top3":
                self.zoom_top3(wr, sc)
            elif t == "profile":
                self.profile(wr, sc)
            elif t == "checklist":
                self.checklist(wr, sc)
            elif t == "end":
                self.end(wr, sc)
            elif t == "hp":
                self.hp(wr, sc)
            elif t == "dashboard":
                self.dashboard(wr, sc)
            elif t == "compare":
                self.compare(wr, sc)
            elif t == "text":
                self.text(wr, sc)


def _cam(st: Image.Image, z: float, cx: float, cy: float, keep_top: int = 430) -> Image.Image:
    if z <= 1.001:
        return st
    w, h = W / z, H / z
    x0 = min(max(0, cx - w / 2), W - w)
    y0 = min(max(0, cy - h / 2), H - h)
    y0 = max(0, min(y0, PY - BEZ - keep_top / z))  # 寄ってもスマホの上端が字幕の帯より下にあるように
    return st.crop((int(x0), int(y0), int(x0 + w), int(y0 + h))).resize((W, H), Image.BILINEAR)


def render_screen_reel(cfg: dict, post: dict, out_path: Path) -> Path:
    return ScreenReel(cfg, post, out_path).render()
