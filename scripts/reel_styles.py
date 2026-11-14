"""リールの型（スマホ操作型 reel_screen.py に加える2つの型）。投稿の points から自動で作る。

  telop : 大きな文字の型。見出しが叩き込まれるように出て、数字が数え上がり、✕○やチェックが判子のように押される。
          背景は黒・主色・白を場面ごとに切り替える
  photo : 写真ストーリーの型。ポイントごとに別の写真が全画面でゆっくり動き、下に字幕が1行ずつ出る。
          比較やチェックは写真の上にカードで出す

投稿データの "reel_style"（screen / telop / photo）で切り替える。
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

import designs
import note_style as ns
import reel_screen as rs
import voice
from common import log
from reel_anim import FPS, H, W, Writer, _zoom, hold_until, ease_back, ease_in_out, ease_out

BLACK = (16, 17, 20)
NL = chr(10)  # 改行


def _layer() -> Image.Image:
    return Image.new("RGBA", (W, H), (0, 0, 0, 0))


def _text_layer(n, text: str, y: int, size: float, color=(255, 255, 255), accent=None, stroke=0, align="left",
                max_w: float = 0.86) -> tuple[Image.Image, int]:
    """強調つきの文字を1枚の透明レイヤーに描く。下端の y を返す。"""
    ly = _layer()
    d = ImageDraw.Draw(ly)
    plain, styles = ns.parse_rich(text)
    f = n.f(int(W * size))
    from generate_image import words_fit
    while not words_fit(d, plain, f, int(W * max_w)) and f.size > W * 0.05:  # 語の途中で切れないよう、収まるまで小さくする
        f = n.f(int(f.size * 0.94))
    lines = plain.split("\n") if "\n" in plain else ns.wrap(d, plain, f, int(W * max_w))
    while max(d.textlength(x, font=f) for x in lines) > W * 0.9 and f.size > W * 0.05:
        f = n.f(int(f.size * 0.94))
    lh = int(f.size * 1.3)
    for runs in ns._attach(lines, plain, styles):
        tw = sum(d.textlength(t, font=f) for t, _ in runs)
        x = (W - tw) / 2 if align == "center" else W * 0.08
        for t, st in runs:
            d.text((x, y), t, font=f, fill=(accent or n.primary) if st & 1 else color, stroke_width=stroke,
                   stroke_fill=(10, 10, 12))
            x += d.textlength(t, font=f)
        y += lh
    return ly, y


def _slam(layer: Image.Image, t: float, dur: float = 0.32) -> Image.Image:
    """大きい状態から叩きつけるように縮んで止まる。"""
    if t >= dur:
        return layer
    if t <= 0:
        return _layer()
    p = t / dur
    s = 1.0 + 0.55 * (1 - ease_out(p))
    a = min(1.0, p * 5)
    box = layer.getbbox()
    if not box:
        return layer
    piece = layer.crop(box)
    pw, ph = int(piece.width * s), int(piece.height * s)
    piece = piece.resize((max(1, pw), max(1, ph)), Image.BILINEAR)
    piece.putalpha(piece.getchannel("A").point(lambda v: int(v * a)))
    out = _layer()
    cx, cy = (box[0] + box[2]) // 2, (box[1] + box[3]) // 2
    out.alpha_composite(piece, (cx - pw // 2, cy - ph // 2))
    return out


def _rise(layer: Image.Image, t: float, dur: float = 0.35, dist: int = 90) -> Image.Image:
    if t >= dur:
        return layer
    if t <= 0:
        return _layer()
    e = ease_out(t / dur)
    out = _layer()
    piece = layer.copy()
    piece.putalpha(piece.getchannel("A").point(lambda v: int(v * e)))
    out.alpha_composite(piece, (0, int((1 - e) * dist)))
    return out


def _shake(t: float, dur: float = 0.18, amp: int = 14) -> tuple[int, int]:
    if t <= 0 or t >= dur:
        return 0, 0
    k = (1 - t / dur)
    return int(math.sin(t * 90) * amp * k), int(math.cos(t * 70) * amp * 0.6 * k)


class Base:
    def __init__(self, cfg: dict, post: dict, out: Path):
        self.n = ns.Note(cfg)
        self.post = post
        self.pts = ns.points_of(post)
        self.out = out
        self.x = rs.Ctx(cfg, post)
        self.last: Image.Image | None = None
        self.nar = voice.Narration(cfg, post, out.parent / f"{out.stem}_voice")

    def voiced(self, wr, idx: int, scene) -> None:
        """場面を描き、読み上げが長ければ話し終わるまで絵を残す。"""
        start = wr.n
        self.nar.mark(idx, start / FPS)
        scene()
        last = hold_until(wr, start, self.nar.need(idx), self.last)
        if last is not None:
            self.last = last

    def put(self, wr, im):
        im = im.convert("RGB")
        wr.put(im)
        self.last = im

    def progress(self, fr: Image.Image, i: int, color=(255, 255, 255), frac: float = 1.0) -> None:
        """上の進行バー。いまの場面の区切りは、読み上げに合わせて左から伸びていく（止まって見えないように）。"""
        d = ImageDraw.Draw(fr)
        total = len(self.pts)
        M, gap = int(W * 0.08), 10
        seg = (W - M * 2 - gap * (total - 1)) / total
        dim = tuple(int(c * 0.35) for c in color)
        y0 = int(H * 0.08)
        for k in range(total):
            x0 = int(M + k * (seg + gap))
            if k < i - 1 or (k == i - 1 and frac >= 1):
                d.rounded_rectangle([x0, y0, int(x0 + seg), y0 + 9], radius=4, fill=color)
            else:
                d.rounded_rectangle([x0, y0, int(x0 + seg), y0 + 9], radius=4, fill=dim)
                if k == i - 1 and frac > 0:
                    d.rounded_rectangle([x0, y0, int(x0 + max(9, seg * frac)), y0 + 9], radius=4, fill=color)

    def kind_card(self, pt: dict, w: int) -> Image.Image | None:
        """リール用のカード。カルーセルの中身をそのまま縮めず、要点（×→○、Q→A、数字、項目3つまで）だけを大きな文字で出す。"""
        kind = pt.get("kind", "default")
        if kind in ("default", "key"):
            return None
        n = self.n
        S = ns.strip_rich
        RED, GRN = (214, 69, 65), n.primary
        rows, big, label = [], None, None
        if kind in ("compare", "phone") and pt.get("ng") and pt.get("ok"):
            rows = [("×", S(pt["ng"]), RED), ("○", S(pt["ok"]), GRN)]
        elif kind == "qa":
            rows = [("Q", S(pt.get("q", "")), ns.INK), ("A", S(pt.get("a", "")), GRN)]
        elif kind == "check":
            bad = pt.get("mark") == "x"
            rows = [("×" if bad else "✓", S(it), RED if bad else GRN) for it in pt.get("items", [])[:3]]
        elif kind == "stat":
            big, label = S(str(pt.get("num", ""))), S(pt.get("num_label", ""))
        elif kind == "voice":
            label = pt.get("voice_label") or "よくある声（例）"
            rows = [("“", S(pt.get("voice", "")), GRN)]
        elif kind == "template":
            label = pt.get("label") or "文例"
            body = [x for x in S(pt.get("text", "")).split(NL) if x.strip()][:2]
            rows = [("", NL.join(body), GRN)]
        elif kind == "table":
            rr = pt.get("rows") or []
            rows = [("→", f"{S(r[0])}：{S(r[1])}", GRN) for r in rr[1:4] if len(r) >= 2]
        if not rows and big is None:
            t = S(pt.get("t", ""))
            if not t:
                return None
            rows = [("", t.split("。")[0] + ("。" if "。" in t else ""), GRN)]
        P = int(W * 0.055)
        probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
        for rate in (0.062, 0.056, 0.05, 0.045):  # 1.3倍ほどの大きさ。収まらなければ少しずつ小さく
            f = n.f(int(W * rate))
            tag = int(f.size * 1.35)
            tw = w - P * 2 - (tag + int(W * 0.03))
            wrapped = []
            for mk, txt, col in rows:
                ls = []
                for para in txt.split(NL):
                    ls += ns._wrap_c(probe, para, f, tw if mk else w - P * 2)  # 1〜3字だけの行を作らない
                wrapped.append((mk, ls, col))
            nlines = sum(len(ls) for _, ls, _ in wrapped)
            if nlines <= 7:
                break
        lh = int(f.size * 1.42)
        gap = int(W * 0.04)
        fl = n.f(int(W * 0.04))
        hh = P
        if label:
            hh += int(fl.size * 1.9)
        if big is not None:
            fb = n.f(int(W * 0.17))
            hh += int(fb.size * 1.15) + (int(W * 0.07) if label else 0)
        for mk, ls, _ in wrapped:
            hh += max(len(ls) * lh, tag if mk else 0) + gap
        hh += P - (gap if wrapped else 0)
        card = Image.new("RGBA", (w, hh), (0, 0, 0, 0))
        d = ImageDraw.Draw(card)
        d.rounded_rectangle([0, 0, w - 1, hh - 1], radius=int(W * 0.04), fill=(255, 255, 255, 255))
        y = P
        self._rows = []
        if big is not None:
            bw = d.textlength(big, font=fb)
            d.text(((w - bw) / 2, y), big, font=fb, fill=n.primary)
            y += int(fb.size * 1.15)
            if label:
                for ln in ns.wrap(probe, label, fl, w - P * 2):
                    lw = d.textlength(ln, font=fl)
                    d.text(((w - lw) / 2, y), ln, font=fl, fill=ns.SUB)
                    y += int(fl.size * 1.5)
            return card.crop((0, 0, w, min(hh, y + P)))
        if label:
            d.text((P, y), label, font=fl, fill=ns.SUB)
            y += int(fl.size * 1.9)
        self._rows = []
        self._line_rows = []
        for j, (mk, ls, col) in enumerate(wrapped):
            row_top = y
            x = P
            if mk:
                # 記号の四角は、1行目の文字の見た目の上下の真ん中にそろえる（フォントの余白の分だけ下にずれないように）
                gb = d.textbbox((0, 0), "国", font=f)
                top = int(y + (gb[1] + gb[3]) / 2 - tag / 2)
                d.rounded_rectangle([P, top, P + tag, top + tag], radius=int(tag * 0.25), fill=col)
                mf = n.f(int(tag * 0.66))
                mb = d.textbbox((0, 0), mk, font=mf)
                d.text((P + (tag - (mb[2] - mb[0])) / 2 - mb[0], top + (tag - (mb[3] - mb[1])) / 2 - mb[1]), mk, font=mf,
                       fill=(255, 255, 255))
                x = P + tag + int(W * 0.03)
            elif kind == "template":
                d.rectangle([P, y, P + 10, y + len(ls) * lh - int(f.size * 0.3)], fill=col)
                x = P + int(W * 0.035)
            line_rows = []
            for ln in ls:
                d.text((x, y), ln, font=f, fill=RED if (mk == "×" and kind in ("compare", "phone")) else ns.INK)
                line_rows.append((max(0, y - int(lh * 0.12)), y + lh - int(lh * 0.12)))
                y += lh
            if len(wrapped) == 1 and not mk:  # 項目が1つだけの文は、1行ずつ出す
                self._line_rows = line_rows
            y = max(y, y if not mk else y) + gap
            self._rows.append((max(0, row_top - gap // 3), min(hh, y - gap // 3)))
            if j < len(wrapped) - 1 and kind in ("compare", "phone", "qa"):
                d.line([(P, y - gap // 2), (w - P, y - gap // 2)], fill=(228, 230, 234), width=3)
        if len(self._rows) <= 1 and len(self._line_rows) >= 2:
            self._rows = self._line_rows
        return card

    def card_at(self, card: Image.Image, rows: list, t: float, t0: float, dur: float) -> Image.Image:
        """カードの項目を、読み上げに合わせて1つずつ出す。いま話している項目には左に印を付ける。
        rows はカードの中の各項目の上下の位置。項目が1つ以下なら、そのまま返す。"""
        if len(rows) <= 1:
            return card
        empty = card.copy()
        de = ImageDraw.Draw(empty)
        for r0, r1 in rows:
            de.rectangle([int(W * 0.02), r0, card.width - int(W * 0.02), r1], fill=(255, 255, 255, 255))
        span = max(0.35 * len(rows), (dur - t0) * 0.62)  # 読み上げの前半〜6割ほどで全部出しきる
        out = empty
        latest = None
        for j, (r0, r1) in enumerate(rows):
            tj = t0 + span * j / len(rows)
            if t < tj:
                break
            a = ease_out(min(1.0, (t - tj) / 0.35))
            piece = card.crop((0, r0, card.width, r1))
            if a < 1:
                piece.putalpha(piece.getchannel("A").point(lambda v, a=a: int(v * a)))
            out.alpha_composite(piece, (int((1 - a) * 60), r0))
            latest = (r0, r1)
        if latest is not None:
            ImageDraw.Draw(out).rounded_rectangle([int(W * 0.012), latest[0] + 8, int(W * 0.012) + 10, latest[1] - 8],
                                                  radius=5, fill=self.n.primary + (255,))
        return out

    def end_scene(self, wr: Writer) -> None:
        sc = (self.post.get("reel") or {}).get("scenes", [])
        end = next((s for s in sc if s.get("type") == "end"), None) or {
            "lines": ["保存して", "*自院でも*確かめて"], "say": "あとで見返せるように"}
        scr = rs.ScreenReel.__new__(rs.ScreenReel)
        scr.x, scr.spec, scr.out, scr.screen, scr.last = self.x, {}, self.out, None, self.last
        scr.end(wr, dict(end, sec=end.get("sec", 3.0)))
        self.last = scr.last


# ---------------------------------------------------------------- telop 型
class Telop(Base):
    BGS = None

    def bgs(self):
        return [BLACK, self.n.primary, (255, 255, 255)]

    def hook(self, wr: Writer) -> None:
        post = self.post
        lines = (post.get("reel") or {}).get("hook", {}).get("lines") or post.get("cover_lines") or [post["title"]]
        photo = post.get("cover_photo") or ((post.get("reel") or {}).get("hook") or {}).get("photo") or post.get("hook_photo")
        bg = ns._photo_fill(photo, W, H, float(post.get("cover_focus", 0.3))) if photo else Image.new("RGB", (W, H), BLACK)
        bg = Image.blend(bg, Image.new("RGB", (W, H), BLACK), 0.45)
        layers = []
        y = int(H * 0.36)
        for ln in lines:
            ly, y = _text_layer(self.n, ln, y, 0.115, stroke=10, accent=designs._yellow(self.n), align="center")
            layers.append(ly)
            y += int(W * 0.02)
        steps = int(2.2 * FPS)
        for k in range(steps):
            t = k / FPS + 0.12  # 1コマ目から文字が出ている（黒い空白のコマを作らない）
            fr = _zoom(bg, 1.0 + 0.2 * ease_out(k / steps), 0.4).convert("RGBA")
            dx = dy = 0
            for i, ly in enumerate(layers):
                ti = t - 0.1 - i * 0.28
                fr.alpha_composite(_slam(ly, ti))
                sx, sy = _shake(ti - 0.32)
                dx, dy = dx + sx, dy + sy
            if dx or dy:
                fr = Image.new("RGBA", (W, H), BLACK + (255,)).copy()
                base = _zoom(bg, 1.0 + 0.2 * ease_out(k / steps), 0.4).convert("RGBA")
                for i, ly in enumerate(layers):
                    base.alpha_composite(_slam(ly, t - 0.1 - i * 0.28))
                fr.paste(base, (dx, dy))
            self.put(wr, fr)

    def point(self, wr: Writer, i: int, pt: dict) -> None:
        n = self.n
        bg_col = self.bgs()[i % 3] if pt.get("kind") != "key" else BLACK
        light = bg_col == (255, 255, 255)
        ink = ns.INK if light else (255, 255, 255)
        accent = n.primary if light else designs._yellow(n)
        bg = Image.new("RGB", (W, H), bg_col)
        # 大きな番号（背景に薄く）
        num = _layer()
        dn = ImageDraw.Draw(num)
        fbig = n.f(int(W * 0.62))
        tag = f"{i:02d}"
        tint = tuple(int(c * 0.88 + (255 if not light else 0) * 0.12) for c in bg_col) if not light else (236, 238, 241)
        dn.text((W - dn.textlength(tag, font=fbig) + int(W * 0.04), int(H * 0.5)), tag, font=fbig, fill=tint + (255,))
        has_card = pt.get("kind") not in ("default", "key")
        head_y = int(H * 0.2) if has_card else int(H * 0.27)
        head, hy = _text_layer(n, pt["h"], head_y, 0.105 if has_card else 0.12, color=ink, accent=accent)
        # まとまりの高さを測り、上の進行バーと下の操作ボタンのあいだの真ん中に寄せる
        card_probe = self.kind_card(pt, int(W * 0.9)) if has_card else None
        if card_probe is not None:
            body_h = card_probe.height
        else:
            _, by_ = _text_layer(n, pt.get("t", ""), hy + int(W * 0.08), 0.064, color=ink, accent=accent)
            body_h = by_ - hy - int(W * 0.08)
        block = (hy - head_y) + int(W * 0.08) + body_h
        new_y = max(int(H * 0.15), int(H * 0.5) - block // 2)
        if abs(new_y - head_y) > 10:
            head_y = new_y
            head, hy = _text_layer(n, pt["h"], head_y, 0.105 if has_card else 0.12, color=ink, accent=accent)
        # 見出しを1行ずつの層に分ける（1行ずつ叩き込む）
        head_lines = []
        hb = head.getbbox()
        if hb:
            rows = [y for y in range(hb[1], hb[3]) if head.crop((0, y, W, y + 1)).getbbox()]
            groups, start, prev_y = [], rows[0], rows[0]
            for y in rows[1:]:
                if y - prev_y > 6:
                    groups.append((start, prev_y + 1))
                    start = y
                prev_y = y
            groups.append((start, prev_y + 1))
            for y0, y1 in groups:
                ly = _layer()
                ly.paste(head.crop((0, y0, W, y1)), (0, y0))
                head_lines.append(ly)
        lab = _layer()
        ImageDraw.Draw(lab).text((W * 0.08, head_y - int(W * 0.08)), "結論" if pt.get("kind") == "key" else ns.point_label(self.x.post.get("form"), i, f"POINT {i}"),
                                 font=n.f(int(W * 0.045)), fill=accent + (255,))
        card = self.kind_card(pt, int(W * 0.9))
        rows = list(getattr(self, "_rows", []) or [])
        if card is not None:  # 見出しと重ならないよう、入りきらないカードは縮める
            avail = int(H * 0.78) - int(hy + W * 0.07)
            if card.height > avail:
                s_ = avail / card.height
                card = card.resize((int(card.width * s_), avail), Image.LANCZOS)
                rows = [(int(a * s_), int(b * s_)) for a, b in rows]
        body = None
        if card is None:
            body, _ = _text_layer(n, pt.get("t", ""), hy + int(W * 0.08), 0.064, color=ink, accent=accent)
        stat_num = pt.get("num") if pt.get("kind") == "stat" else None
        dur = max(1.6 + min(2.8, ns._read_sec(pt) * 0.7), self.nar.need(i))  # 話し終わるまで、この場面の中で動かし続ける
        steps = int(dur * FPS)
        # 前の場面を押し出して入る（縦方向にワイプ）
        prev = self.last
        for k in range(steps):
            t = k / FPS + 0.22  # 切り替えの途中から見出しが見えている（空の画面を挟まない）
            fr = bg.convert("RGBA")
            drift = k / max(1, steps - 1)  # 止まって見えないよう、全体をゆっくり動かし続ける
            if card is None:  # カードがある場面は背景の番号を出さない（半分隠れて見えるため）
                nl = _rise(num, t, 0.5, 200)
                fr.alpha_composite(nl.crop((0, 0, W, H - int(70 * drift))), (0, int(70 * drift)))
            fr.alpha_composite(_rise(lab, t - 0.05))
            for j, hl in enumerate(head_lines or [head]):
                fr.alpha_composite(_slam(hl, t - 0.1 - j * 0.22))
            if card is not None:
                tc = t - 0.35
                if tc > 0:  # カードは上から順に現れる（項目が1つずつ出てくるように見える）
                    e = ease_in_out(min(1.0, tc / 0.6))
                    x = int((W - card.width) / 2)
                    y = int(hy + W * 0.07)
                    h_show = max(1, int(card.height * e))
                    cv = self.card_at(card, rows, t, 0.55, dur)
                    fr.alpha_composite(cv.crop((0, 0, card.width, h_show)), (x, y - int(36 * drift)))
            elif body is not None:
                bl = _rise(body, t - 0.7, 0.4, 60)
                fr.alpha_composite(bl.crop((0, int(30 * drift), W, H)), (0, 0))
            self.progress(fr, i, ink if not light else ns.INK, frac=(k + 1) / steps)
            fr = _zoom(fr.convert("RGB"), 1.0 + 0.035 * drift, 0.45).convert("RGBA")  # ゆっくり寄り続ける
            if k < 6 and prev is not None:  # 6コマで前の場面からワイプ
                cut = int(H * ease_in_out((k + 1) / 6))
                p = prev.copy()
                p.paste(fr.convert("RGB").crop((0, 0, W, cut)), (0, 0))
                fr = p
            self.put(wr, fr)

    def render(self) -> Path:
        wr = Writer(self.out, 70)
        self.voiced(wr, 0, lambda: self.hook(wr))
        for i, pt in enumerate(self.pts, 1):
            self.voiced(wr, i, lambda: self.point(wr, i, pt))
        self.voiced(wr, len(self.pts) + 1, lambda: self.end_scene(wr))
        sec = wr.close()
        self.nar.mux(self.out, sec)
        log(f"リール動画を生成しました（文字の型）: {self.out} ({sec:.1f}秒)")
        return self.out


# ---------------------------------------------------------------- photo 型
class PhotoStory(Base):
    def hook(self, wr: Writer) -> None:
        post = self.post
        lines = (post.get("reel") or {}).get("hook", {}).get("lines") or post.get("cover_lines") or [post["title"]]
        hp = post.get("cover_photo") or ((post.get("reel") or {}).get("hook") or {}).get("photo") or post.get("hook_photo")
        bg = ns._photo_fill(hp, W, H, float(post.get("cover_focus", 0.3))) if hp else Image.new("RGB", (W, H), BLACK)
        shade = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        g = Image.new("L", (1, H))
        for yy in range(H):
            g.putpixel((0, yy), int(max(0.0, (yy / H - 0.35) / 0.65) ** 1.2 * 220))
        shade = Image.new("RGBA", (W, H), (8, 8, 12, 255))
        shade.putalpha(g.resize((W, H)))
        layers, y = [], int(H * 0.56)
        for ln in lines:
            ly, y = _text_layer(self.n, ln, y, 0.1, stroke=8, accent=designs._yellow(self.n))
            layers.append(ly)
        steps = int(2.4 * FPS)
        for k in range(steps):
            t = k / FPS
            fr = _zoom(bg, 1.12 - 0.12 * ease_out(k / steps), 0.35).convert("RGBA")
            fr.alpha_composite(shade)
            for j, ly in enumerate(layers):
                fr.alpha_composite(_rise(ly, t - 0.15 - j * 0.18))
            self.put(wr, fr)

    def point(self, wr: Writer, i: int, pt: dict, photo: str | None) -> None:
        n = self.n
        bg = ns._photo_fill(photo, W, H, 0.3) if photo else Image.new("RGB", (W, H), BLACK)
        bg = Image.blend(bg, Image.new("RGB", (W, H), (8, 8, 12)), 0.25)
        pan_right = i % 2 == 0
        card = self.kind_card(pt, int(W * 0.9))
        rows = list(getattr(self, "_rows", []) or [])
        head, hy = _text_layer(n, pt["h"], int(H * 0.14), 0.088, stroke=8, accent=designs._yellow(n))
        badge = _layer()
        db = ImageDraw.Draw(badge)
        fb = n.f(int(W * 0.04))
        tag = "結論" if pt.get("kind") == "key" else f"{i} / {len(self.pts)}"
        tw = db.textlength(tag, font=fb)
        db.rounded_rectangle([W * 0.08, H * 0.14 - fb.size * 2.1, W * 0.08 + tw + 40, H * 0.14 - fb.size * 0.5],
                             radius=int(fb.size * 0.8), fill=n.primary + (255,))
        db.text((W * 0.08 + 20, H * 0.14 - fb.size * 1.95), tag, font=fb, fill=(255, 255, 255, 255))
        # 字幕（下に1行ずつ）
        f = n.f(int(W * 0.062))
        probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
        sub_lines = ns.wrap(probe, ns.strip_rich(pt.get("t", "")), f, int(W * 0.8))
        while len(sub_lines) > 4 and f.size > W * 0.052:  # 3行に収まるまで小さくする（途中で切らない）
            f = n.f(int(f.size * 0.92))
            sub_lines = ns.wrap(probe, ns.strip_rich(pt.get("t", "")), f, int(W * 0.84))
        dur = max(1.6 + min(3.8, ns._read_sec(pt) * 0.95), self.nar.need(i))  # 字幕を読み切れて、話し終わるまでの長さ
        steps = int(dur * FPS)
        for k in range(steps):
            t = k / FPS
            z = 1.04 + 0.1 * (k / steps)
            cx = 0.35 + (0.3 if pan_right else -0.0) * (k / steps)
            w2, h2 = int(W / z), int(H / z)
            x0 = int((W - w2) * min(1.0, max(0.0, cx)))
            fr = bg.crop((x0, (H - h2) // 3, x0 + w2, (H - h2) // 3 + h2)).resize((W, H), Image.BILINEAR).convert("RGBA")
            top = Image.new("RGBA", (W, int(H * 0.42)), (0, 0, 0, 0))
            gt = Image.new("L", (1, top.height))
            for yy in range(top.height):
                gt.putpixel((0, yy), int((1 - yy / top.height) ** 1.1 * 190))
            dark = Image.new("RGBA", top.size, (8, 8, 12, 255))
            dark.putalpha(gt.resize(top.size))
            fr.alpha_composite(dark, (0, 0))
            fr.alpha_composite(_rise(badge, t))
            fr.alpha_composite(_rise(head, t - 0.08, 0.4, 70))
            if card is not None and t > 0.7:
                e = ease_out(min(1.0, (t - 0.7) / 0.4))
                c = self.card_at(card, rows, t, 0.9, dur).copy()
                c.putalpha(c.getchannel("A").point(lambda v: int(v * e)))
                fr.alpha_composite(c, (int((W - card.width) / 2), int(max(hy + W * 0.06, H * 0.72 - card.height) + (1 - e) * 80)))
            elif card is None:
                d = ImageDraw.Draw(fr)
                yy = int(H * 0.62)
                for j, ln in enumerate(sub_lines):
                    tj = t - 0.5 - j * 0.35  # 1行ずつ、読める速さで続けて出す
                    if tj <= 0:
                        continue
                    a = int(255 * min(1.0, tj / 0.25))
                    lw = d.textlength(ln, font=f)
                    d.rounded_rectangle([(W - lw) / 2 - 24, yy - 14, (W + lw) / 2 + 24, yy + f.size * 1.25],
                                        radius=14, fill=(0, 0, 0, int(a * 0.7)))
                    d.text(((W - lw) / 2, yy), ln, font=f, fill=(255, 255, 255, a))
                    yy += int(f.size * 1.75)
            self.progress(fr, i, frac=(k + 1) / steps)
            if k < 7 and self.last is not None:  # 前の写真を横に押し出して切り替える
                e = ease_in_out((k + 1) / 7)
                pf = Image.new("RGBA", (W, H))
                pf.paste(self.last.convert("RGBA"), (-int(W * e), 0))
                pf.paste(fr, (W - int(W * e), 0))
                fr = pf
            self.put(wr, fr)

    def render(self) -> Path:
        wr = Writer(self.out, 70)
        self.voiced(wr, 0, lambda: self.hook(wr))
        photos = designs._photos_for(self.post, reel=True)
        for i, pt in enumerate(self.pts, 1):
            self.voiced(wr, i, lambda: self.point(wr, i, pt, photos[(i - 1) % len(photos)] if photos else None))
        self.voiced(wr, len(self.pts) + 1, lambda: self.end_scene(wr))
        sec = wr.close()
        self.nar.mux(self.out, sec)
        log(f"リール動画を生成しました（写真の型）: {self.out} ({sec:.1f}秒)")
        return self.out


def render_reel(cfg: dict, post: dict, out_path: Path) -> Path:
    """投稿の reel_style に合わせてリールを作る。"""
    style = post.get("reel_style") or ("screen" if post.get("reel") else "telop")
    if style == "screen" and post.get("reel"):
        return rs.render_screen_reel(cfg, post, out_path)
    if style == "photo":
        return PhotoStory(cfg, post, out_path).render()
    return Telop(cfg, post, out_path).render()
