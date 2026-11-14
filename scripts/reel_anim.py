"""動きのあるリール動画を作る（図解ノート／写真表紙のデザイン用）。

静止画の切り替えではなく、1 コマずつ描いて ffmpeg に流し込む。
  表紙   : 写真がゆっくり寄る（ズーム）＋文字が下からせり上がる
  切替   : 次のページが右から押し出すように入ってくる
  中身   : 見出しが先に出て、補足や図があとから出る（リストは上から順に現れる）
  図     : 出たあともゆっくり上に動き続ける
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image, ImageChops

import note_style as ns
from common import log
from media import ffmpeg_path

W, H, FPS = 1080, 1920, 30


def ease_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def ease_in_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def ease_back(t: float) -> float:
    t = max(0.0, min(1.0, t))
    c1, c3 = 1.4, 2.4
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


class Writer:
    def __init__(self, out: Path, total_sec: float):
        ff = ffmpeg_path()
        if not ff:
            raise RuntimeError("ffmpeg が見つかりません")
        out.parent.mkdir(parents=True, exist_ok=True)
        self.out = out
        self.n = 0
        self.p = subprocess.Popen([
            ff, "-y", "-loglevel", "error",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
            "-f", "lavfi", "-t", f"{max(total_sec, 600) + 1:.2f}", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "medium", "-crf", "21", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "96k", "-shortest", "-movflags", "+faststart", str(out),
        ], stdin=subprocess.PIPE)

    def put(self, im: Image.Image) -> None:
        self.p.stdin.write(im.convert("RGB").tobytes())
        self.n += 1

    def close(self) -> float:
        self.p.stdin.close()
        self.p.wait()
        if self.p.returncode:
            raise RuntimeError("ffmpeg でリールを作れませんでした")
        return self.n / FPS


def hold_until(wr: "Writer", start_frame: int, need_sec: float, last: Image.Image | None) -> Image.Image | None:
    """読み上げが場面より長いとき、最後の絵をゆっくり寄せながら話し終わるまで待つ。"""
    if last is None:
        return last
    rest = int(need_sec * FPS) - (wr.n - start_frame)
    fr = last
    for k in range(max(0, rest)):
        fr = _zoom(last.convert("RGB"), 1.0 + 0.025 * (k + 1) / max(rest, 1), 0.45)
        wr.put(fr)
    return fr


def _zoom(im: Image.Image, z: float, cy: float = 0.45) -> Image.Image:
    if z <= 1.0001:
        return im
    w, h = int(W / z), int(H / z)
    x = (W - w) // 2
    y = int((H - h) * cy)
    return im.crop((x, y, x + w, y + h)).resize((W, H), Image.BILINEAR)


def _push(a: Image.Image, b: Image.Image, t: float) -> Image.Image:
    """b が右から入り、a が左へ出る。"""
    e = ease_in_out(t)
    dx = int(W * e)
    out = Image.new("RGB", (W, H))
    out.paste(a, (-dx, 0))
    out.paste(b, (W - dx, 0))
    return out


def _diff_box(a: Image.Image, b: Image.Image):
    box = ImageChops.difference(a.convert("RGB"), b.convert("RGB")).getbbox()
    if not box:
        return None
    x0, y0, x1, y1 = box
    return (0, max(0, y0 - 6), W, min(H, y1 + 6))


class Reel:
    def __init__(self, cfg: dict, post: dict):
        self.n = ns.Note(cfg)
        self.post = post
        self.pts = ns.points_of(post)
        self.frames: list[Image.Image] = []  # 書き出す前に溜めず、直接 Writer に流す
        self.last: Image.Image | None = None

    # ---- 部品
    def cover(self, wr: Writer, sec: float) -> None:
        n, post = self.n, self.post
        steps = int(sec * FPS)
        if post.get("cover_photo"):
            bg, over = ns.draw_cover_photo(n, post, W, H, reel=True, layers=True)
            bg = bg.convert("RGB")
            for k in range(steps):
                t = k / FPS
                frame = _zoom(bg, 1.0 + 0.1 * (k / steps), 0.4).convert("RGBA")
                a = ease_out(t / 0.5)
                rise = int((1 - ease_back(min(1.0, max(0.0, (t - 0.1) / 0.55)))) * 140)
                layer = over.copy()
                if a < 1:
                    layer.putalpha(layer.getchannel("A").point(lambda v, a=a: int(v * a)))
                frame.alpha_composite(layer, (0, rise))
                wr.put(frame)
            self.last = frame.convert("RGB")
            return
        img = ns.draw_cover(n, post, W, H, reel=True)
        for k in range(steps):
            t = k / FPS
            z = 1.06 - 0.06 * ease_out(t / 0.6)
            wr.put(_zoom(img, z, 0.5))
        self.last = img

    def transition(self, wr: Writer, nxt: Image.Image, sec: float = 0.35) -> None:
        steps = int(sec * FPS)
        for k in range(1, steps + 1):
            wr.put(_push(self.last, nxt, k / steps))
        self.last = nxt

    def hold(self, wr: Writer, sec: float) -> None:
        for _ in range(int(sec * FPS)):
            wr.put(self.last)

    def reveal(self, wr: Writer, a: Image.Image, b: Image.Image, kind: str, sec: float, hold: float) -> None:
        box = _diff_box(a, b)
        if not box:
            self.last = b
            self.hold(wr, sec + hold)
            return
        x0, y0, x1, y1 = box
        region = b.crop(box)
        base = a.copy()
        steps = int(sec * FPS)
        wipe = kind in ("check", "compare", "qa", "phone")
        for k in range(1, steps + 1):
            t = k / steps
            fr = base.copy()
            if wipe:  # 上から順に現れる
                e = ease_in_out(t)
                h = int((y1 - y0) * e)
                if h > 0:
                    fr.paste(region.crop((0, 0, x1 - x0, h)), (x0, y0))
            else:  # 下からふわっと出る
                e = ease_out(t)
                off = int((1 - e) * 70)
                piece = Image.blend(a.crop(box), region, e)
                fr.paste(a.crop((x0, y0, x1, y1)), (x0, y0))
                fr.paste(piece.crop((0, 0, x1 - x0, y1 - y0 - off)), (x0, y0 + off))
            wr.put(fr)
        self.last = b
        if kind == "mock":  # 図はゆっくり上に流れ続ける
            drift_steps = int(hold * FPS)
            for k in range(drift_steps):
                dy = int(36 * k / max(1, drift_steps))
                fr = a.copy()
                fr.paste(region.crop((0, dy, x1 - x0, y1 - y0)), (x0, y0))
                wr.put(fr)
            self.last = fr
        else:
            self.hold(wr, hold)


def render_reel_video(cfg: dict, post: dict, out_path: Path) -> Path:
    r = Reel(cfg, post)
    n, pts = r.n, r.pts
    total_guess = 3.0 + sum(1.0 + ns._read_sec(p) for p in pts) + 4.5
    wr = Writer(out_path, total_guess + 5)
    r.cover(wr, 3.0)
    for i, p in enumerate(pts, 1):
        a = ns.draw_point(n, p, i, len(pts), W, H, reel=True, show_text=False)
        b = ns.draw_point(n, p, i, len(pts), W, H, reel=True, show_text=True)
        r.transition(wr, a)
        r.hold(wr, 0.45)
        r.reveal(wr, a, b, p.get("kind", "default"), 0.6 if p.get("kind") in ("check", "compare") else 0.45,
                 ns._read_sec(p))
    end = ns.draw_summary(n, post, pts, W, H, reel=True)
    # 見出しだけ残した「まとめ」から、項目と相談の一言を上から順に出す
    blank = end.copy()
    y0, y1 = int(H * 0.2) + int(W * 0.075 * 1.7), int(H * 0.74) - 4
    blank.paste(ns._paper(W, H).crop((0, y0, W, y1)), (0, y0))
    r.transition(wr, blank)
    r.reveal(wr, blank, end, "check", 0.9, 3.8)
    sec = wr.close()
    log(f"リール動画を生成しました: {out_path} ({sec:.1f}秒)")
    return out_path
