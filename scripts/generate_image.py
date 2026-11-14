"""投稿画像を生成する（Pillow のみ・絵文字不使用）。

設計の根拠は docs/リサーチ_伸びる投稿の分析.md（9 章: Instagram 実例の目視分析）。
伸びているクリニック系アカウントの表紙に共通する要素をそのまま型にしている:
  - 明るい背景（パステル or 明るい写真）に、画面いっぱいの太い縁取り文字
  - 助詞は小さく、名詞・数字は特大。キーワード 1〜2 語は色の箱で強調
  - 上部に「＼○○が解説／」の肩書き、下部に「保存して読み返す」の帯と「Swipe」
  - 医師・スタッフの写真（person_image）があれば右下に
  - リールは上部の白い帯タイトル＋中央の大きな縁取りテロップ「① …」

  render_square       : 1 枚画像 1080x1080
  render_carousel     : カルーセル 1080x1350
  render_reel_frames  : リール用フレーム 1080x1920（media.py が動画にする）
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from common import ROOT, label_for, log

GOTHIC_FONTS = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "C:/Windows/Fonts/NotoSansJP-VF.ttf",
    "C:/Windows/Fonts/YuGothB.ttc",
    "C:/Windows/Fonts/meiryob.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
]
SERIF_FONTS = [
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
    "C:/Windows/Fonts/NotoSerifJP-VF.ttf",
    "C:/Windows/Fonts/yumindb.ttf",
    "C:/Windows/Fonts/msmincho.ttc",
    "/System/Library/Fonts/ヒラギノ明朝 ProN.ttc",
]

WHITE = (255, 255, 255)
INK = (24, 26, 30)
GRAY = (110, 116, 124)

NO_HEAD = set("、。，．・：；？！）」』】〕〉》ゝゞヽヾ々ー〜…‥っゃゅょぁぃぅぇぉッャュョァィゥェォ")
NO_TAIL = set("（「『【〔〈《")
GOOD_BREAK_AFTER = set("、。，．・はがをにでとのもへや）」』】！？…")
AVOID_HEAD = set("はがをにでとのもへや")
PARTICLES = {"は", "が", "を", "に", "で", "と", "の", "も", "へ", "や", "より", "って", "から", "まで", "か", "しか", "だけ", "ほど", "など", "な", "ね", "よ", "、", "。", "，"}

AUTHOR_LABELS = {
    "dental": "歯科医師が解説",
    "internal": "内科医が解説",
    "gastroenterology": "消化器内科医が解説",
    "dermatology": "皮膚科医が解説",
    "ent": "耳鼻科医が解説",
    "pediatrics": "小児科医が解説",
    "ophthalmology": "眼科医が解説",
    "orthopedics": "整形外科医が解説",
    "gynecology": "婦人科医が解説",
    "mental": "心療内科医が解説",
    "beauty": "美容医療の医師が解説",
    "webmarketing": "クリニック集患の専門家が解説",
}


# ---------------------------------------------------------------- 基本
def hex_to_rgb(h: str | None, default: tuple[int, int, int]) -> tuple[int, int, int]:
    try:
        h = (h or "").strip().lstrip("#")
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except Exception:
        return default


def mix(a, b, t: float):
    return tuple(int(a[i] * (1 - t) + b[i] * t) for i in range(3))


def luminance(rgb) -> float:
    r, g, b = [c / 255 for c in rgb]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _first_existing(paths: list[str]) -> str | None:
    for p in paths:
        if p and Path(p).exists():
            return p
    return None


def font(path: str | None, size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    if not path:
        return ImageFont.load_default(size)  # type: ignore[return-value]
    try:
        f = ImageFont.truetype(path, size)
        try:
            names = [n.decode() if isinstance(n, bytes) else n for n in f.get_variation_names()]
            for want in (["Black", "Bold"] if bold else ["Regular"]):
                if want in names:
                    f.set_variation_by_name(want)
                    break
        except Exception:
            pass
        return f
    except Exception:
        return ImageFont.load_default(size)  # type: ignore[return-value]


class Theme:
    def __init__(self, cfg: dict):
        t = cfg.get("theme", {})
        self.primary = hex_to_rgb(t.get("primary_color"), (21, 94, 76))
        self.accent = hex_to_rgb(t.get("accent_color"), (255, 214, 10))
        self.pastel = mix(WHITE, self.primary, 0.13)       # 明るい背景
        self.pastel2 = mix(WHITE, self.accent, 0.35)       # 箱などに使う薄い色
        self.on_primary = WHITE if luminance(self.primary) < 0.6 else INK
        self.on_accent = INK if luminance(self.accent) > 0.45 else WHITE
        serif = t.get("font", "gothic") == "serif"
        extra = cfg.get("image", {}).get("font_candidates", []) or []
        self.title_font = _first_existing(extra + (SERIF_FONTS if serif else GOTHIC_FONTS)) or _first_existing(GOTHIC_FONTS)
        self.body_font = _first_existing(extra + GOTHIC_FONTS)
        if not self.body_font:
            log("警告: 日本語フォントが見つかりません。文字化けする可能性があります。")
        self.author = cfg.get("author_label") or next((AUTHOR_LABELS[s] for s in cfg.get("specialties", []) if s in AUTHOR_LABELS), "専門家が解説")
        self.person = None
        p = cfg.get("person_image") or ""
        if p:
            pp = Path(p) if os.path.isabs(p) else ROOT / p
            if pp.exists():
                self.person = pp


# ---------------------------------------------------------------- 折り返し
def _fits(d, s, f, max_w) -> bool:
    return d.textlength(s, font=f) <= max_w


_UNIT_RE = re.compile(r"「[^」]{1,12}」|『[^』]{1,12}』|\d+人に\d+人|\d+月\d+日|\d+(?:[.,．]\d+)?(?:[〜～]\d+(?:[.,．]\d+)?)?(?:か月|週間|時間|[割分つ本回人日歳年％%秒個枚件度倍歩選gmlLcm]{0,2})|[ァ-ヶー]+|[A-Za-z0-9]+|より|って|から|まで|しか|だけ|ほど|など|.")


def _kind(ch: str) -> str:
    if "\u4e00" <= ch <= "\u9fff" or ch in "々〆ヶ〇○△□":
        return "K"  # 漢字
    if "\u30a0" <= ch <= "\u30ff" or ch == "ー":
        return "T"  # カタカナ
    if "\u3040" <= ch <= "\u309f":
        return "H"  # ひらがな
    if ch.isascii() and (ch.isalnum() or ch in "%.,-+/:#&"):
        return "A"
    if ch in "０１２３４５６７８９％":
        return "A"
    return "P"  # 記号


# 文節の切れ目を作らない「後ろにつく」ひらがなの長さの上限（これより長いひらがなは助詞の後ろで切る）
_PARTICLE_ENDS = ("から", "まで", "より", "だけ", "など", "では", "には", "とは", "ので", "のに", "けど", "ても", "は", "を")


def _split_hira(run: str) -> list[str]:
    """長いひらがなの並びを、助詞・語尾のあとで区切る。"""
    if len(run) <= 8:
        return [run]
    out, cur = [], ""
    i = 0
    while i < len(run):
        cur += run[i]
        i += 1
        if len(cur) >= 3 and i < len(run):
            for pe in _PARTICLE_ENDS:
                if cur.endswith(pe) and run[i] not in "っゃゅょぁぃぅぇぉー":
                    out.append(cur)
                    cur = ""
                    break
    if cur:
        out.append(cur)
    return out


def _units(text: str) -> list[str]:
    """文節に近い単位に分ける。漢字・カタカナ・英数字のかたまりに、後ろのひらがな（送りがな・助詞）を付ける。
    折り返しはこの単位の切れ目でだけ行う（「大丈/夫」「ありがと/う」のような切れ方をしない）。"""
    units: list[str] = []
    cur = ""
    prev = ""
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        k = _kind(ch)
        if ch in "「『（【":  # 開きかっこは次の語とくっつける
            if cur:
                units.append(cur)
            cur, prev = ch, "open"
            i += 1
            continue
        if k == "P" and (ch in NO_HEAD or ch in "」』）】"):  # 閉じかっこ・句読点は前にくっつける
            cur += ch
            prev = "P"
            i += 1
            continue
        if k == "H":
            j = i
            while j < n and _kind(text[j]) == "H":
                j += 1
            run = text[i:j]
            parts = _split_hira(run)
            if prev in ("K", "T", "A", "open", "H") or not cur:
                cur += parts[0]
                rest = parts[1:]
            else:
                units.append(cur)
                cur = parts[0]
                rest = parts[1:]
            for part in rest:
                units.append(cur)
                cur = part
            prev = "H"
            i = j
            continue
        if k in ("K", "T", "A"):
            prefix = cur in ("お", "ご") or cur.endswith(("「お", "「ご", "（お", "（ご"))
            one_kana = (prev == "H" and len(cur) >= 2 and _kind(cur[-1]) == "H" and _kind(cur[-2]) == "K"
                        and cur[-1] not in "はがをにでとのもへやかよねな"
                        and i + 1 < n and _kind(text[i]) == "K")
            if prev == "H" and len(cur) > 1 and cur[-1] in "おご" and not one_kana:
                units.append(cur[:-1])  # 「にお待ち」→「に」｜「お待ち」（お・ご は後ろの語につける）
                cur = cur[-1]
            elif prev in ("H", "P") and cur and not prefix and not one_kana:
                units.append(cur)
                cur = ""
            # 漢字・カタカナ・英数字が続くところ（「電話タップ計測」「〇〇市歯医者」）は1つの語として切らない
            cur += ch
            prev = k
            i += 1
            continue
        if ch in " 　":
            cur += ch
            units.append(cur)
            cur, prev = "", ""
            i += 1
            continue
        cur += ch
        prev = "P"
        i += 1
    if cur:
        units.append(cur)
    return [u for u in units if u]


def _ok_break(units: list[str], k: int) -> bool:
    if k <= 0 or k >= len(units):
        return False
    nxt, prev = units[k], units[k - 1]
    if nxt[0] in NO_HEAD or prev[-1] in NO_TAIL:
        return False
    # 助詞（を・が・は・に・へ・で）を行頭に置かない（「」）を」の後などで起きやすい）
    if nxt[0] in "をがはにへで" and (prev[-1] in "」』）】" or _kind(prev[-1]) in "KTA"):
        return False
    return True


def _good_break(units: list[str], k: int) -> bool:
    return _ok_break(units, k) and units[k - 1][-1] in GOOD_BREAK_AFTER


def words_fit(d: ImageDraw.ImageDraw, text: str, f: ImageFont.FreeTypeFont, max_w: int) -> bool:
    """どの語（文節）も1行に収まるか。大きな見出しは、収まるまで文字を小さくしてから折り返す。"""
    return all(_fits(d, u, f, max_w) for para in str(text).split("\n") for u in _units(para))


def wrap(d: ImageDraw.ImageDraw, text: str, f: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    lines: list[str] = []
    for para in str(text).split("\n"):
        units = []
        for u in _units(para):  # 1単位だけで行に入らないときは、文字の種類の変わり目 → 1文字ずつ の順に分ける
            if _fits(d, u, f, max_w):
                units.append(u)
                continue
            parts, cur = [], ""
            for ch in u:  # 長すぎる語は、文字の種類の変わり目（漢字→ひらがな、漢字とカタカナ）で分ける
                # ひらがなの前では切らない（「を」「が」などが行頭に来ないように）。漢字・カタカナ・英数字の前で切る
                if cur and len(cur) >= 2 and ((_kind(ch) != _kind(cur[-1]) and _kind(ch) in "KTA") or cur[-1] in "を、"):
                    parts.append(cur)
                    cur = ""
                cur += ch
            parts.append(cur)
            for part in parts:
                units.extend([part] if _fits(d, part, f, max_w) else list(part))
        para_lines: list[str] = []
        while units:
            if _fits(d, "".join(units), f, max_w):
                para_lines.append("".join(units))
                break
            n = 1
            while n < len(units) and _fits(d, "".join(units[: n + 1]), f, max_w):
                n += 1
            cut = n
            # かっこ（「」（）など）の中では切らない。かっこの外で切れる所が近くにあれば、そこで切る
            depth, d_at = 0, [0]
            for u in units:
                depth += sum(u.count(c) for c in "（「『【") - sum(u.count(c) for c in "）」』】")
                d_at.append(depth)
            outside = [k for k in range(cut, max(0, cut - 5), -1) if k >= 1 and d_at[k] <= 0 and _ok_break(units, k)
                       and _fits(d, "".join(units[:k]), f, max_w) and d.textlength("".join(units[:k]), font=f) >= max_w * 0.25]
            if d_at[cut] > 0 and outside:
                cut = next((k for k in outside if _good_break(units, k)), outside[0])
            else:
              for k in range(cut, max(1, cut - 3), -1):
                if _good_break(units, k) and d_at[k] <= 0:
                    cut = k
                    break
              else:
                for k in range(cut, max(0, cut - 3), -1):
                    if _ok_break(units, k):
                        cut = k
                        break
            para_lines.append("".join(units[:cut]))
            units = units[cut:]
        # 最後の行が1〜3文字だけになるときは、前の行から1単位ずつ送る
        if len(para_lines) >= 2 and len(para_lines[-1]) <= 3:
            prev_units = _units(para_lines[-2])
            if len(prev_units) >= 2:
                moved = prev_units[-1]
                cand = moved + para_lines[-1]
                if _fits(d, cand, f, max_w):
                    para_lines[-2] = "".join(prev_units[:-1])
                    para_lines[-1] = cand
        lines.extend(para_lines)
    return lines


def _text_block(d, x, y, lines, f, fill, lh, stroke=0, stroke_fill=None) -> int:
    for ln in lines:
        d.text((x, y), ln, font=f, fill=fill, stroke_width=stroke, stroke_fill=stroke_fill)
        y += lh
    return y


def key_phrases(text: str) -> list[str]:
    found = re.findall(r"「([^」]{1,14})」", text)
    nums = re.findall(r"(?<![A-Za-z])\d+(?:[.,．]\d+)?(?:か月|週間|時間|人に\d+人|[割分つ本回人日歳年％%秒個枚件度倍歩選gmlLcm]{1,2})?", text)
    return [x for x in found + nums if x][:3]


def split_point(text: str, max_head: int = 22) -> tuple[str, str]:
    # 本文側に「①」「1.」などの番号があると、デザイン側の番号と二重になるので外す
    text = re.sub(r"^\s*(?:[①-⑳]|\(?\d{1,2}[.．)）、](?!\d))\s*", "", text)
    m = re.search(r"[、。：:]", text)
    if m and 6 <= m.start() <= max_head and len(text) - m.end() >= 6:
        return text[: m.start()], text[m.end():].strip("。 ")
    return text.rstrip("。"), ""


# ---------------------------------------------------------------- メリハリ見出し（助詞を小さく・数字と「」を箱で）
def _pop_tokens(text: str) -> list[tuple[str, str]]:
    """(kind, text) の列。kind = box（箱で強調）/ small（助詞）/ big（単語）。
    連続する通常文字は 1 つの単語にまとめ、改行で途中で切れないようにする。"""
    out: list[tuple[str, str]] = []
    units = _units(text)
    for i, u in enumerate(units):
        nxt = units[i + 1] if i + 1 < len(units) else ""
        if u.startswith("「") and u.endswith("」"):
            out.append(("box", u[1:-1]))
        elif re.match(r"^\d", u):
            out.append(("box", u))
        elif u in PARTICLES and not (nxt and "ぁ" <= nxt[0] <= "ん" and u not in ("、", "。", "，")):
            # 助詞は「次がひらがなでない」ときだけ小さくする（歯み「が」き のような語中を避ける）
            out.append(("small", u))
        elif u in "？！?!":
            if out:
                out[-1] = (out[-1][0], out[-1][1] + u)
            else:
                out.append(("big", u))
        elif out and out[-1][0] == "big":
            out[-1] = ("big", out[-1][1] + u)
        else:
            out.append(("big", u))
    return out


def _layout_pop(d, tokens, f_big, f_small, max_w, pad) -> list[list[tuple[str, str, float]]]:
    """トークンを幅に合わせて行に分ける。各要素は (kind, text, width)。単語が 1 行に収まらないときだけ文字で割る。"""
    def width(kind, t):
        f = f_small if kind == "small" else f_big
        return d.textlength(t, font=f) + (pad * 2 + 8 if kind == "box" else 0)

    # 1 行に入らない長い単語は分割
    expanded: list[tuple[str, str]] = []
    for kind, t in tokens:
        if kind == "big" and width(kind, t) > max_w:
            for ln in wrap(d, t, f_big, max_w):
                expanded.append(("split", ln))
        else:
            expanded.append((kind, t))

    lines: list[list[tuple[str, str, float]]] = [[]]
    cur_w = 0.0
    for kind, t in expanded:
        w = width(kind, t)
        if cur_w + w > max_w and lines[-1]:
            if t in "、。，" :  # 句読点が行頭に来る → サイズを下げて組み直す合図
                lines[-1].append(("split", t, w))
                continue
            if kind == "small" and len(lines[-1]) > 1 and lines[-1][-1][0] != "small":
                prev = lines[-1].pop()  # 助詞が行頭に来ないよう、直前の単語ごと送る
                lines.append([prev])
                cur_w = prev[2]
            else:
                lines.append([])
                cur_w = 0.0
        lines[-1].append((kind, t, w))
        cur_w += w
    return [ln for ln in lines if ln]


def draw_pop_title(img: Image.Image, text: str, th: Theme, x: int, y: int, max_w: int, size: int,
                   fill, stroke_fill, stroke: int, box_fill, box_text, max_lines: int = 4, align: str = "left") -> int:
    """伸びている投稿の見出し組版。収まるまで文字サイズを落とす。戻り値は下端 y。"""
    d = ImageDraw.Draw(img)
    tokens = _pop_tokens(text)
    s = size
    while True:
        f_big = font(th.title_font, s)
        f_small = font(th.title_font, int(s * 0.62))
        pad = int(s * 0.12)
        lines = _layout_pop(d, tokens, f_big, f_small, max_w, pad)
        orphan = len(lines) > 1 and len(lines[-1]) == 1 and sum(w for _, _, w in lines[-1]) < max_w * 0.28
        split_word = any(k == "split" for ln in lines for k, _, _ in ln)
        if (len(lines) <= max_lines and not orphan and not split_word) or s <= int(size * 0.55):
            break
        s = int(s * 0.92)
    lh = int(s * 1.28)
    for ln in lines:
        total = sum(w for _, _, w in ln)
        cx = x + ((max_w - total) / 2 if align == "center" else 0)
        for kind, t, w in ln:
            if kind == "box":
                # 実際の文字の外接矩形から箱を作る（フォントによる上下ずれを防ぐ）
                bx = cx + pad + 4
                bb = d.textbbox((bx, y), t, font=f_big)
                ref = d.textbbox((bx, y), "歯", font=f_big)  # 行内で高さを揃える基準
                top = min(bb[1], ref[1]) - int(pad * 0.7)
                bottom = max(bb[3], ref[3]) + int(pad * 0.7)
                d.rounded_rectangle([cx, top, cx + w, bottom], radius=int(s * 0.12), fill=box_fill)
                d.text((bx, y), t, font=f_big, fill=box_text)
            elif kind == "small":
                d.text((cx, y + int(s * 0.36)), t, font=f_small, fill=fill, stroke_width=max(1, stroke // 2), stroke_fill=stroke_fill)
            else:
                d.text((cx, y), t, font=f_big, fill=fill, stroke_width=stroke, stroke_fill=stroke_fill)
            cx += w
        y += lh
    return y


def pop_title_height(th: Theme, text: str, max_w: int, size: int, max_lines: int = 4) -> tuple[int, int]:
    """描画せずに高さと決定サイズを返す。"""
    d = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    tokens = _pop_tokens(text)
    s = size
    while True:
        lines = _layout_pop(d, tokens, font(th.title_font, s), font(th.title_font, int(s * 0.62)), max_w, int(s * 0.12))
        orphan = len(lines) > 1 and len(lines[-1]) == 1 and sum(w for _, _, w in lines[-1]) < max_w * 0.28
        split_word = any(k == "split" for ln in lines for k, _, _ in ln)
        if (len(lines) <= max_lines and not orphan and not split_word) or s <= int(size * 0.55):
            return len(lines) * int(s * 1.28), s
        s = int(s * 0.92)


# ---------------------------------------------------------------- 背景・部品
def _cover(path: Path, w: int, h: int, anchor_y: float = 0.5) -> Image.Image:
    im = Image.open(path).convert("RGB")
    iw, ih = im.size
    scale = max(w / iw, h / ih)
    im = im.resize((int(iw * scale) + 1, int(ih * scale) + 1), Image.LANCZOS)
    iw, ih = im.size
    x0 = (iw - w) // 2
    y0 = int((ih - h) * anchor_y)
    return im.crop((x0, y0, x0 + w, y0 + h))


def _light_background(th: Theme, W: int, H: int, illust: Path | None) -> tuple[Image.Image, bool]:
    """明るい背景。写真があれば白を重ねて明るくし、文字が読めるようにする。"""
    if illust:
        img = _cover(illust, W, H)
        img = img.filter(ImageFilter.GaussianBlur(1.2))
        img.paste(Image.new("RGB", (W, H), WHITE), (0, 0), Image.new("L", (W, H), 120))
        return img, True
    return Image.new("RGB", (W, H), th.pastel), False


def _paste_person(img: Image.Image, th: Theme, W: int, H: int, max_h_ratio: float = 0.42) -> None:
    """医師・スタッフの写真（背景透過 PNG 推奨）を右下に。"""
    if not th.person:
        return
    try:
        im = Image.open(th.person).convert("RGBA")
        scale = min((H * max_h_ratio) / im.height, (W * 0.45) / im.width)
        im = im.resize((int(im.width * scale), int(im.height * scale)), Image.LANCZOS)
        img.paste(im, (W - im.width - int(W * 0.03), H - im.height - int(H * 0.09)), im)
    except Exception as e:  # noqa: BLE001
        log(f"person_image 読み込み失敗: {e}")


def _author_strip(d, th: Theme, W: int, y: int, size: int) -> int:
    """「＼ 歯科医師が解説 ／」を中央に。"""
    f = font(th.body_font, size)
    t = f"＼ {th.author} ／"
    w = d.textlength(t, font=f)
    d.text(((W - w) / 2, y), t, font=f, fill=INK, stroke_width=3, stroke_fill=WHITE)
    return y + int(size * 1.4)


def _bookmark(d, x, y, h, fill):
    w = int(h * 0.68)
    d.polygon([(x, y), (x + w, y), (x + w, y + h), (x + w / 2, y + h * 0.72), (x, y + h)], fill=fill)


def _save_strip(img: Image.Image, th: Theme, W: int, H: int, M: int, right_text: str, left_text: str = "保存して読み返す") -> None:
    """下部の帯: 左にしおりと「保存して読み返す」、右に Swipe。"""
    d = ImageDraw.Draw(img)
    h = int(W * 0.066)
    y = H - int(W * 0.145)
    d.rounded_rectangle([M, y, W - M, y + h], radius=h // 2, fill=th.primary)
    f = font(th.body_font, int(h * 0.44))
    _bookmark(d, M + int(h * 0.5), y + int(h * 0.26), int(h * 0.48), th.on_primary)
    d.text((M + int(h * 1.1), y + int(h * 0.26)), left_text, font=f, fill=th.on_primary)
    tw = d.textlength(right_text, font=f)
    d.text((W - M - int(h * 0.5) - tw, y + int(h * 0.26)), right_text, font=f, fill=th.on_primary)


def _clinic_line(img, d, cfg, th, W, M, y, color):
    logo_rel = cfg.get("logo_path") or ""
    if logo_rel:
        lp = Path(logo_rel) if os.path.isabs(logo_rel) else ROOT / logo_rel
        if lp.exists():
            try:
                logo = Image.open(lp).convert("RGBA")
                logo.thumbnail((int(W * 0.28), int(W * 0.05)))
                img.paste(logo, (M, y), logo)
                return
            except Exception as e:  # noqa: BLE001
                log(f"ロゴ読み込み失敗: {e}")
    d.text((M, y), cfg.get("clinic_name", ""), font=font(th.body_font, int(W * 0.026)), fill=color)


def _page_header(d, th, W, H, M, left: str, page: str):
    f_label = font(th.body_font, int(W * 0.03))
    f_page = font(th.body_font, int(W * 0.028), bold=False)
    top = int(H * 0.09)
    lw = d.textlength(left, font=f_label)
    d.rounded_rectangle([M, top - 10, M + lw + 40, top + f_label.size + 12], radius=10, fill=th.primary)
    d.text((M + 20, top), left, font=f_label, fill=th.on_primary)
    d.text((W - M - d.textlength(page, font=f_page), top + 4), page, font=f_page, fill=GRAY)
    return top + f_label.size + 12, f_page


# ---------------------------------------------------------------- スライド
def _draw_cover(cfg: dict, post: dict, th: Theme, W: int, H: int, illust: Path | None, right_text: str) -> Image.Image:
    M = int(W * 0.07)
    img, photo = _light_background(th, W, H, illust)
    _paste_person(img, th, W, H)
    d = ImageDraw.Draw(img)
    y = _author_strip(d, th, W, int(H * 0.075), int(W * 0.034))

    size = int(W * 0.125)
    text_w = W - M * 2 - (int(W * 0.26) if th.person else 0)
    h, s = pop_title_height(th, post["title"], text_w, size, max_lines=4)
    top_zone = y + int(H * 0.02)
    bottom_zone = H - int(W * 0.16)
    ty = max(top_zone, top_zone + (bottom_zone - top_zone - h) // 2 - int(H * 0.03))
    draw_pop_title(img, post["title"], th, M, ty, text_w, s, fill=INK, stroke_fill=WHITE, stroke=max(3, s // 14),
                   box_fill=th.accent, box_text=th.on_accent, max_lines=4)
    _save_strip(img, th, W, H, M, right_text)
    d = ImageDraw.Draw(img)
    _clinic_line(img, d, cfg, th, W, M, H - int(W * 0.06), GRAY)
    return img


def _draw_point(cfg: dict, th: Theme, W: int, H: int, idx: int, total: int, page_no: int, text: str, illust: Path | None = None) -> Image.Image:
    M = int(W * 0.07)
    img = Image.new("RGB", (W, H), WHITE)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, int(W * 0.014)], fill=th.primary)
    top, f_page = _page_header(d, th, W, H, M, f"POINT {idx}", f"{page_no} / {total}")
    head, rest = split_point(text)
    f_body = font(th.body_font, int(W * 0.042), bold=False)
    size = int(W * 0.085)
    h, s = pop_title_height(th, head, W - M * 2, size, max_lines=3)
    rl = wrap(d, rest, f_body, W - M * 2)[:4] if rest else []
    block = h + (60 + len(rl) * int(f_body.size * 1.55) if rl else 0)
    hy = max(top + int(H * 0.08), (H - block) // 2 - int(H * 0.05))
    y = draw_pop_title(img, head, th, M, hy, W - M * 2, s, fill=INK, stroke_fill=WHITE, stroke=0,
                       box_fill=th.pastel2, box_text=INK, max_lines=3)
    d = ImageDraw.Draw(img)
    d.rectangle([M, y + 6, M + int(W * 0.08), y + 12], fill=th.accent)
    if rl:
        _text_block(d, M, y + 60, rl, f_body, mix(INK, GRAY, 0.2), int(f_body.size * 1.55))
    _clinic_line(img, d, cfg, th, W, M, H - int(W * 0.08), GRAY)
    nxt = "次へ ▶▶" if page_no < total - 1 else "まとめへ ▶▶"
    f_n = font(th.body_font, int(W * 0.03))
    d.text((W - M - d.textlength(nxt, font=f_n), H - int(W * 0.082)), nxt, font=f_n, fill=th.primary)
    return img


def _draw_map(cfg: dict, th: Theme, W: int, H: int, total: int, heads: list[str]) -> Image.Image:
    M = int(W * 0.07)
    img = Image.new("RGB", (W, H), WHITE)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, int(W * 0.014)], fill=th.primary)
    top, f_page = _page_header(d, th, W, H, M, "この投稿でわかること", f"2 / {total}")
    f_item = font(th.title_font, int(W * 0.052))
    f_no = font(th.title_font, int(W * 0.05))
    y = top + int(W * 0.1)
    for i, h in enumerate(heads, 1):
        d.rounded_rectangle([M, y - 4, M + int(W * 0.075), y + f_no.size + 6], radius=10, fill=th.accent)
        nw = d.textlength(f"{i:02d}", font=f_no)
        d.text((M + (int(W * 0.075) - nw) / 2, y), f"{i:02d}", font=f_no, fill=th.on_accent)
        hl = wrap(d, h, f_item, W - M * 2 - int(W * 0.11))[:2]
        _text_block(d, M + int(W * 0.11), y, hl, f_item, INK, int(f_item.size * 1.3))
        y += max(1, len(hl)) * int(f_item.size * 1.3) + int(W * 0.045)
        d.line([M, y - int(W * 0.022), W - M, y - int(W * 0.022)], fill=(225, 228, 231), width=2)
    _clinic_line(img, d, cfg, th, W, M, H - int(W * 0.08), GRAY)
    f_n = font(th.body_font, int(W * 0.03))
    d.text((W - M - d.textlength("次へ ▶▶", font=f_n), H - int(W * 0.082)), "次へ ▶▶", font=f_n, fill=th.primary)
    return img


def one_cta(cfg: dict, post: dict) -> str:
    variants = (cfg.get("caption", {}) or {}).get("cta_variants") or []
    if post.get("cta"):
        return post["cta"]
    if variants:
        import hashlib
        return variants[int(hashlib.md5((post.get("id", "") + "cta").encode()).hexdigest()[:6], 16) % len(variants)]
    svc = (cfg.get("services", {}).get(post.get("service", ""), {}) or {}).get("name")
    goals = cfg.get("goals", [])
    if svc and "acquisition" in goals:
        return f"「{svc}」のご相談はプロフィールのリンクから"
    if "reach" in goals or "followers" in goals:
        return "保存しておくと、あとで見返せます"
    return cfg.get("caption", {}).get("signature") or "ご相談はお気軽にどうぞ"


def _draw_summary(cfg: dict, post: dict, th: Theme, W: int, H: int, total: int, heads: list[str]) -> Image.Image:
    M = int(W * 0.07)
    img = Image.new("RGB", (W, H), WHITE)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, int(W * 0.014)], fill=th.primary)
    top, f_page = _page_header(d, th, W, H, M, "まとめ", f"{total} / {total}")
    f_item = font(th.title_font, int(W * 0.047))
    f_cta = font(th.title_font, int(W * 0.05))
    y = top + int(W * 0.1)
    for h in heads[:5]:
        d.rounded_rectangle([M, y + int(f_item.size * 0.3), M + int(W * 0.03), y + int(f_item.size * 0.3) + int(W * 0.03)], radius=6, fill=th.accent)
        hl = wrap(d, h, f_item, W - M * 2 - int(W * 0.06))[:2]
        _text_block(d, M + int(W * 0.06), y, hl, f_item, INK, int(f_item.size * 1.35))
        y += len(hl) * int(f_item.size * 1.35) + int(W * 0.03)
    cl = wrap(d, one_cta(cfg, post), f_cta, W - M * 2 - int(W * 0.08))[:3]
    bh = len(cl) * int(f_cta.size * 1.35) + int(W * 0.07)
    by = min(H - int(W * 0.2) - bh, max(y + int(W * 0.04), H - int(W * 0.3) - bh))
    d.rounded_rectangle([M, by, W - M, by + bh], radius=int(W * 0.02), fill=th.primary)
    _text_block(d, M + int(W * 0.04), by + int(W * 0.035), cl, f_cta, th.on_primary, int(f_cta.size * 1.35))
    _save_strip(img, th, W, H, M, "フォローで毎日届きます")
    d = ImageDraw.Draw(img)
    _clinic_line(img, d, cfg, th, W, M, H - int(W * 0.06), GRAY)
    return img


# ---------------------------------------------------------------- リール
def _reel_bg(th: Theme, W: int, H: int, illust: Path | None) -> Image.Image:
    if illust:
        img = _cover(illust, W, H)
        img = img.filter(ImageFilter.GaussianBlur(2))
        img.paste(Image.new("RGB", (W, H), WHITE), (0, 0), Image.new("L", (W, H), 90))
        return img
    return Image.new("RGB", (W, H), th.pastel)


def _reel_title_pill(d, th: Theme, W: int, y: int, text: str) -> int:
    """上部の白い帯タイトル（黒太字）。1 行に収まるサイズで。"""
    s = int(W * 0.052)
    while s > int(W * 0.03):
        f = font(th.title_font, s)
        if d.textlength(text, font=f) <= W * 0.82:
            break
        s -= 2
    f = font(th.title_font, s)
    tw = d.textlength(text, font=f)
    px, py = int(s * 0.6), int(s * 0.35)
    x0 = (W - tw) / 2 - px
    d.rounded_rectangle([x0, y, x0 + tw + px * 2, y + s + py * 2], radius=int(s * 0.5), fill=WHITE, outline=INK, width=3)
    d.text((x0 + px, y + py), text, font=f, fill=INK)
    return y + s + py * 2


def _draw_reel_point(cfg: dict, th: Theme, W: int, H: int, title: str, idx: int, text: str, illust: Path | None) -> Image.Image:
    img = _reel_bg(th, W, H, illust)
    _paste_person(img, th, W, H, max_h_ratio=0.5)
    d = ImageDraw.Draw(img)
    _reel_title_pill(d, th, W, int(H * 0.16), title)
    head, rest = split_point(text)
    label = f"{'①②③④⑤⑥'[idx - 1] if idx <= 6 else str(idx)} {head}"
    M = int(W * 0.07)
    size = int(W * 0.1)
    h, s = pop_title_height(th, label, W - M * 2, size, max_lines=3)
    ty = int(H * 0.5) - h // 2
    draw_pop_title(img, label, th, M, ty, W - M * 2, s, fill=th.accent, stroke_fill=INK, stroke=max(4, s // 9),
                   box_fill=WHITE, box_text=INK, max_lines=3, align="center")
    d = ImageDraw.Draw(img)
    if rest:
        f_body = font(th.body_font, int(W * 0.046))
        rl = wrap(d, rest, f_body, W - M * 2)[:3]
        y = ty + h + int(H * 0.02)
        for ln in rl:
            tw = d.textlength(ln, font=f_body)
            d.text(((W - tw) / 2, y), ln, font=f_body, fill=WHITE, stroke_width=6, stroke_fill=INK)
            y += int(f_body.size * 1.5)
    _clinic_line(img, d, cfg, th, W, M, H - int(W * 0.3), INK)
    return img


def _draw_reel_cover(cfg: dict, post: dict, th: Theme, W: int, H: int, illust: Path | None) -> Image.Image:
    img = _reel_bg(th, W, H, illust)
    _paste_person(img, th, W, H, max_h_ratio=0.5)
    d = ImageDraw.Draw(img)
    _author_strip(d, th, W, int(H * 0.14), int(W * 0.04))
    M = int(W * 0.07)
    size = int(W * 0.13)
    h, s = pop_title_height(th, post["title"], W - M * 2, size, max_lines=4)
    ty = int(H * 0.47) - h // 2
    draw_pop_title(img, post["title"], th, M, ty, W - M * 2, s, fill=WHITE, stroke_fill=INK, stroke=max(5, s // 9),
                   box_fill=th.accent, box_text=th.on_accent, max_lines=4, align="center")
    d = ImageDraw.Draw(img)
    f = font(th.body_font, int(W * 0.04))
    t = "最後まで見てね" if len(post.get("body", [])) < 2 else f"{len(post.get('body', []))}つのポイントを解説"
    d.text(((W - d.textlength(t, font=f)) / 2, ty + h + int(H * 0.03)), t, font=f, fill=INK, stroke_width=4, stroke_fill=WHITE)
    _clinic_line(img, d, cfg, th, W, M, H - int(W * 0.3), INK)
    return img


def _draw_reel_end(cfg: dict, post: dict, th: Theme, W: int, H: int, illust: Path | None) -> Image.Image:
    img = _reel_bg(th, W, H, illust)
    d = ImageDraw.Draw(img)
    M = int(W * 0.07)
    _reel_title_pill(d, th, W, int(H * 0.16), "まとめ")
    f_item = font(th.title_font, int(W * 0.05))
    heads = [split_point(b)[0] for b in post.get("body", [])[:5]]
    y = int(H * 0.3)
    for i, h in enumerate(heads, 1):
        line = f"{'①②③④⑤⑥'[i - 1] if i <= 6 else i} {h}"
        for ln in wrap(d, line, f_item, W - M * 2)[:2]:
            d.text((M, y), ln, font=f_item, fill=INK, stroke_width=4, stroke_fill=WHITE)
            y += int(f_item.size * 1.4)
        y += int(W * 0.02)
    cta = one_cta(cfg, post)
    f_cta = font(th.title_font, int(W * 0.056))
    cl = wrap(d, cta, f_cta, W - M * 2 - int(W * 0.08))[:3]
    bh = len(cl) * int(f_cta.size * 1.35) + int(W * 0.07)
    by = max(y + int(H * 0.03), int(H * 0.66))
    d.rounded_rectangle([M, by, W - M, by + bh], radius=int(W * 0.02), fill=th.primary)
    _text_block(d, M + int(W * 0.04), by + int(W * 0.035), cl, f_cta, th.on_primary, int(f_cta.size * 1.35))
    _clinic_line(img, d, cfg, th, W, M, H - int(W * 0.3), INK)
    return img


# ---------------------------------------------------------------- 公開 API
def is_note(cfg: dict) -> bool:
    return (cfg.get("theme") or {}).get("style") == "note"


def render_square(cfg: dict, post: dict, out_path: Path, size: int = 1080, illust: Path | None = None, reel: bool = False) -> Path:
    if is_note(cfg):
        import note_style
        note_style.render_square(cfg, post, out_path, size, reel=reel)
        log(f"画像を生成しました: {out_path}")
        return out_path
    th = Theme(cfg)
    img = _draw_cover(cfg, post, th, size, size, illust, "続きはキャプションへ")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "JPEG", quality=92, optimize=True)
    log(f"画像を生成しました: {out_path}")
    return out_path


def render_carousel(cfg: dict, post: dict, out_dir: Path, stem: str, W: int = 1080, H: int = 1350, illust: Path | None = None) -> list[Path]:
    if is_note(cfg):
        import note_style
        paths = note_style.render_carousel(cfg, post, out_dir, stem, W, H)
        log(f"カルーセル {len(paths)} 枚を生成しました: {out_dir}/{stem}_*.jpg")
        return paths
    th = Theme(cfg)
    body = post.get("body", [])[:6]
    heads = [split_point(b)[0] for b in body]
    use_map = len(body) >= 3
    total = 1 + (1 if use_map else 0) + len(body) + 1
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []

    def save(img):
        p = out_dir / f"{stem}_{len(paths) + 1:02d}.jpg"
        img.save(p, "JPEG", quality=92, optimize=True)
        paths.append(p)

    save(_draw_cover(cfg, post, th, W, H, illust, "Swipe ▶▶"))
    if use_map:
        save(_draw_map(cfg, th, W, H, total, heads))
    for i, b in enumerate(body, 1):
        save(_draw_point(cfg, th, W, H, i, total, len(paths) + 1, b))
    save(_draw_summary(cfg, post, th, W, H, total, heads))
    log(f"カルーセル {len(paths)} 枚を生成しました: {out_dir}/{stem}_*.jpg")
    return paths


def render_reel_frames(cfg: dict, post: dict, out_dir: Path, stem: str, W: int = 1080, H: int = 1920, illust: Path | None = None) -> list[tuple[Path, float]]:
    if is_note(cfg):
        import note_style
        frames = note_style.render_reel_frames(cfg, post, out_dir, stem, W, H)
        log(f"リール用フレーム {len(frames)} 枚を生成しました")
        return frames
    th = Theme(cfg)
    body = post.get("body", [])[:5]
    out_dir.mkdir(parents=True, exist_ok=True)
    frames: list[tuple[Path, float]] = []
    img = _draw_reel_cover(cfg, post, th, W, H, illust)
    p = out_dir / f"{stem}_r00.jpg"
    img.save(p, "JPEG", quality=92)
    frames.append((p, 3.0))
    for i, b in enumerate(body, 1):
        img = _draw_reel_point(cfg, th, W, H, post["title"], i, b, illust)
        p = out_dir / f"{stem}_r{i:02d}.jpg"
        img.save(p, "JPEG", quality=92)
        frames.append((p, max(3.2, min(6.0, len(b) / 11))))
    img = _draw_reel_end(cfg, post, th, W, H, illust)
    p = out_dir / f"{stem}_r99.jpg"
    img.save(p, "JPEG", quality=92)
    frames.append((p, 4.0))
    log(f"リール用フレーム {len(frames)} 枚を生成しました")
    return frames


if __name__ == "__main__":
    import sys

    from common import load_config, load_posts
    from illustration import get_illustration

    cfg = load_config()
    posts = load_posts(cfg)
    picks = [p for p in posts if len(p.get("body", [])) >= 3][:3]
    prev = ROOT / "docs" / "preview"
    stand_in = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    il = stand_in or get_illustration(cfg, picks[0])
    render_square(cfg, picks[0], prev / "square_0.jpg", illust=il)
    render_square(cfg, picks[1], prev / "square_1.jpg", illust=None)
    render_carousel(cfg, picks[0], prev, "carousel", illust=il)
    render_reel_frames(cfg, picks[2], prev, "reel", illust=stand_in)
