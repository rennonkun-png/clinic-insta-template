"""投稿データの品質チェック（納品前に必ず通す）。

使い方:
  python scripts/quality_check.py content/webmarketing.json            … 文章と構成のチェック
  python scripts/quality_check.py content/webmarketing.json --render   … 画像も書き出して、文字が縮みすぎていないか確認

見るもの:
  [重複]   同じページの中で同じことを2度言っていないか（見出し・数字・補足・比較・吹き出し）
  [重複]   キャプション冒頭がタイトルの言い直しになっていないか
  [単調]   となりの投稿と、ページ構成（kind の並び）・リールの場面の並び・デザインの型が同じでないか
  [単調]   分析画面の数字が他の投稿と同じでないか
  [文体]   AI っぽい言い回し・絵文字・「GENOVA」
  [長さ]   表紙・見出し・字幕の文字数
  [表示]   （--render）文字を縮めないと入らないページ
エラー（E）が1件でもあれば終了コード 1。注意（W）は目で確認する。
"""
from __future__ import annotations

import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

AI_PHRASES = ["重要です", "ポイントは", "しましょう", "効果的", "最適化", "活用し", "向上", "いかがでしたか", "大切です", "必須です",
              "欠かせません", "鍵となり", "ではないでしょうか", "することで", "ことが可能", "傾向です", "ちょうどいい", "の出番",
              "が勝負", "いかがでしょうか"]
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿⭐✨]")


def plain(s) -> str:
    return re.sub(r"==|\*|\\n|\n", "", str(s or ""))


def norm(s) -> str:
    return re.sub(r"[、。・「」『』（）()？?！!\s　,.:：]", "", plain(s))


def overlap(a: str, b: str) -> float:
    """短いほうの文字列のうち、長いほうと共通する最長部分の割合。"""
    a, b = norm(a), norm(b)
    if not a or not b:
        return 0.0
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    m = SequenceMatcher(None, short, long_).find_longest_match(0, len(short), 0, len(long_))
    return m.size / max(1, len(short))


def lcs_len(a: str, b: str) -> int:
    a, b = norm(a), norm(b)
    if not a or not b:
        return 0
    return SequenceMatcher(None, a, b).find_longest_match(0, len(a), 0, len(b)).size


class Report:
    def __init__(self):
        self.items: list[tuple[str, str, str]] = []

    def e(self, pid, msg):
        self.items.append(("E", pid, msg))

    def w(self, pid, msg):
        self.items.append(("W", pid, msg))


def check_point(r: Report, pid: str, i: int, pt: dict) -> None:
    k = pt.get("kind", "default")
    h, t = pt.get("h", ""), pt.get("t", "")
    shown = {"h": h}
    if k in ("default", "key", "stat", "voice"):
        shown["t"] = t  # 画面に補足が出る種類
    for key in ("num", "num_label", "ng", "ok", "voice", "q", "a"):
        if pt.get(key):
            shown[key] = pt[key]
    for j, it in enumerate(pt.get("items", []) or []):
        shown[f"items{j}"] = it
    keys = list(shown)
    for x in range(len(keys)):
        for y in range(x + 1, len(keys)):
            a, b = shown[keys[x]], shown[keys[y]]
            ov, ln = overlap(a, b), lcs_len(a, b)
            pair = {keys[x][:5], keys[y][:5]}
            if pair <= {"items"} or pair == {"ng", "ok"}:  # 項目どうし・比較の左右は書き出しが似ていてよい
                hit = ov >= 0.8 and ln >= 6
            else:
                hit = (ov >= 0.6 and ln >= 3) or ln >= 9
            if hit:
                r.e(pid, f"P{i} [重複] {keys[x]}「{plain(a)}」と {keys[y]}「{plain(b)}」が同じことを言っている")
    if k == "stat" and pt.get("num") and norm(pt["num"]) in norm(h):
        r.e(pid, f"P{i} [重複] 大きな数字「{pt['num']}」が見出しにも入っている（見出しは数字の意味を言う）")
    if len(plain(h).replace("\\n", "")) > 22:
        r.w(pid, f"P{i} [長さ] 見出しが長い: {plain(h)}")


def check_post(r: Report, p: dict) -> None:
    pid = p["id"]
    text_all = json.dumps({k: p.get(k) for k in ("cover_lines", "lead", "caption_lead", "points", "reel")}, ensure_ascii=False)
    for ph in AI_PHRASES:
        if ph in text_all:
            r.w(pid, f"[文体] AIっぽい言い回し「{ph}」")
    if EMOJI.search(text_all):
        r.e(pid, "[文体] 絵文字が入っている")
    if "GENOVA" in text_all:
        r.e(pid, "[文体] 本文に GENOVA が入っている")
    if overlap(p.get("title", ""), (p.get("caption_lead") or "").split("。")[0]) >= 0.7:
        r.e(pid, "[重複] キャプション冒頭がタイトルの言い直しになっている")
    if overlap("".join(p.get("cover_lines", [])), p.get("lead", "")) >= 0.6:
        r.e(pid, "[重複] 表紙の大きな文字とその下の一言が同じことを言っている")
    pts = p.get("points") or []
    sm = p.get("summary") or {}
    m = re.search(r"([2-9])つ", plain("".join(p.get("cover_lines", [])) + p.get("title", "")))
    if m and int(m.group(1)) != len([x for x in pts if x.get("kind") != "key"]):
        r.e(pid, f"[構成] 表紙・タイトルは「{m.group(0)}」なのに、中身のページが {len([x for x in pts if x.get('kind') != 'key'])} 枚")
    if sm.get("type") == "one":
        for x in pts:
            if overlap(sm.get("text", ""), x.get("h")) >= 0.6:
                r.e(pid, f"[重複] 1行まとめ「{plain(sm.get('text'))}」が見出し「{plain(x.get('h'))}」の言い換えになっている")
    if not sm:
        r.e(pid, "[構成] まとめ（summary）がない。見出しの写しではなく、行動の形の項目か1行のまとめを書く")
    elif sm.get("type") != "one":
        heads = {norm(x.get("h")) for x in pts}
        same = [it for it in sm.get("items", []) if norm(it) in heads or any(overlap(it, x.get("h")) >= 0.85 for x in pts)]
        if same:
            r.e(pid, f"[重複] まとめの項目が見出しの写しになっている: {same}")
    one_form = p.get("form") in ("qa", "ng")  # 全ページを同じ見せ方にそろえる型（Q&A集・失敗集）は対象外
    if not one_form and not any(x.get("kind") in ("template", "table", "stat", "check") for x in pts):
        r.w(pid, "[保存価値] 文例・表・数字の目安・チェックのどれもない（保存したくなる実用の1枚を入れる）")
    if not 3 <= len(pts) <= 5:
        r.e(pid, f"[構成] ページ数が {len(pts)}（3〜5）")
    for i, pt in enumerate(pts, 1):
        check_point(r, pid, i, pt)
    check_narration(r, p)
    heads = [norm(pt.get("h")) for pt in pts]
    for i in range(len(heads)):
        for j in range(i + 1, len(heads)):
            if overlap(heads[i], heads[j]) >= 0.7:
                r.e(pid, f"[重複] P{i + 1} と P{j + 1} の見出しが似ている")
    for i in range(1, len(pts)):
        if pts[i].get("kind") == pts[i - 1].get("kind") and not one_form:
            r.w(pid, f"[単調] P{i} と P{i + 1} が同じ見せ方（{pts[i].get('kind')}）")
    for ln in p.get("cover_lines", []):
        if len(plain(ln)) > 12:
            r.w(pid, f"[長さ] 表紙の行が長い: {plain(ln)}")
    reel = p.get("reel") or {}
    for sc in reel.get("scenes", []):
        for ln in str(sc.get("say", "")).split("\n"):
            if len(plain(ln)) > 15 and sc.get("type") not in ("end", "text"):
                r.w(pid, f"[長さ] 字幕の行が長い: {plain(ln)}")
        if sc.get("type") == "end" and re.search(r"[にをでがとの]$", plain(sc.get("say", ""))):
            r.e(pid, f"[文章] リール最後の字幕が途中で終わっている: {plain(sc.get('say'))}")
        if sc.get("type") == "text":
            if overlap("".join(sc.get("lines", [])), sc.get("say", "")) >= 0.6:
                r.e(pid, "[重複] 文字だけの場面で、大きな文字と字幕が同じ")


def narration_slots(p: dict) -> int:
    """リールの場面の数（台本はこの数だけ要る）。"""
    style = p.get("reel_style") or ("screen" if p.get("reel") else "telop")
    if style == "screen" and p.get("reel"):
        return 1 + len(p["reel"].get("scenes", []))
    return 1 + len(p.get("points") or []) + 1


def check_narration(r: Report, p: dict) -> None:
    pid = p["id"]
    nar = p.get("narration")
    if not nar:
        r.w(pid, "[音声] リールの読み上げ台本（narration）がない")
        return
    need = narration_slots(p)
    if len(nar) != need:
        r.e(pid, f"[音声] 台本が {len(nar)} 個（場面は {need} 個。冒頭＋各場面＋最後）")
    if any(re.search(r"[*=]", x or "") for x in nar):
        r.e(pid, "[音声] 台本に * や == が入っている（読み上げの文には飾りを付けない）")
    if nar and len(nar[0] or "") > 32:
        r.w(pid, f"[音声] 冒頭の台本が長い（{len(nar[0])}字。32字以内で掴む）")
    for i, x in enumerate(nar):
        if len(x or "") > 110:
            r.w(pid, f"[音声] 場面{i}の台本が長い（{len(x)}字。110字以内）")
    total = sum(len(x or "") for x in nar)
    if not 200 <= total <= 340:
        r.w(pid, f"[音声] 台本の合計が {total}字（200〜340字＝読み上げ約35〜55秒）")
    pts = p.get("points") or []
    for i, x in enumerate(nar[1:1 + len(pts)], 1):
        h = plain(pts[i - 1].get("h", "")) if i - 1 < len(pts) else ""
        if h and overlap(x, h + plain(pts[i - 1].get("t", ""))) >= 0.85:
            r.w(pid, f"[音声] 場面{i}の台本が画面の字の読み上げだけになっている（画面にない理由・やり方・例を足す）")


def check_series(r: Report, posts: list[dict]) -> None:
    """となり合う投稿どうしで、見た目と構成が同じになっていないか。"""
    # 投稿をまたいで、文例・答え・吹き出しが同じになっていないか（例「駐車場は医院の裏に3台」を何度も使わない）
    texts = []
    for p in posts:
        for x in p.get("points") or []:
            for key in ("text", "a", "voice", "ok", "ng"):
                if len(norm(x.get(key))) >= 10:
                    texts.append((p["id"], key, x[key]))
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            if texts[i][0] != texts[j][0] and (lcs_len(texts[i][2], texts[j][2]) >= 15 or SequenceMatcher(None, norm(texts[i][2]), norm(texts[j][2])).ratio() >= 0.55):
                r.e(texts[j][0], f"[重複] {texts[i][0]} と同じような文（{texts[j][1]}）: 「{plain(texts[j][2])[:30]}…」")
    dash = {}
    for i, p in enumerate(posts):
        pid = p["id"]
        for pt in p.get("points") or []:
            m = pt.get("mock") or {}
            if m.get("type") == "dashboard":
                key = (str(m.get("value", "既定")), json.dumps(m.get("kpis", "既定"), ensure_ascii=False))
                if key in dash:
                    r.e(pid, f"[単調] 分析画面の数字が {dash[key]} と同じ（value / kpis を内容に合わせて変える）")
                dash.setdefault(key, pid)
        if i == 0:
            continue
        q = posts[i - 1]
        ka = [x.get("kind") for x in p.get("points") or []]
        kb = [x.get("kind") for x in q.get("points") or []]
        if ka == kb:
            r.e(pid, f"[単調] ページ構成が前の投稿 {q['id']} と同じ: {ka}")
        sa = [s.get("type") for s in (p.get("reel") or {}).get("scenes", [])]
        sb = [s.get("type") for s in (q.get("reel") or {}).get("scenes", [])]
        if sa and sa == sb:
            r.e(pid, f"[単調] リールの場面の並びが前の投稿 {q['id']} と同じ")
        if p.get("design") and p.get("design") == q.get("design"):
            r.e(pid, f"[単調] デザインの型（{p.get('design')}）が前の投稿と同じ")
        if p.get("reel_style") and p.get("reel_style") == q.get("reel_style"):
            r.e(pid, f"[単調] リールの型（{p.get('reel_style')}）が前の投稿と同じ")
        near = [x.get("cover_photo") for x in posts[max(0, i - 12):i]]
        if p.get("cover_photo") and p.get("cover_photo") in near:
            r.e(pid, "[単調] 表紙の写真が直近12投稿のどれかと同じ")
    # 同じ写真は2度使わない（表紙・中のページ・リールのすべてで、投稿をまたいで1枚1回）
    seen: dict[str, str] = {}
    for p in posts:
        mine = []
        if p.get("cover_photo"):
            mine.append(p["cover_photo"])
        mine += [x for x in (p.get("page_photos") or []) if x]
        if p.get("hook_photo"):
            mine.append(p["hook_photo"])
        hook = ((p.get("reel") or {}).get("hook") or {}).get("photo")
        if hook and hook != p.get("cover_photo"):
            mine.append(hook)
        for ph in mine:
            if ph in seen and seen[ph] != p["id"] + "#":
                r.e(p["id"], f"[写真] {ph} は {seen[ph].rstrip('#')} でも使われている（同じ写真は2度使わない）")
            elif ph in seen:
                r.e(p["id"], f"[写真] {ph} がこの投稿の中で2回使われている")
            seen[ph] = p["id"] + "#"
    # 同じ種類の図を使い回さない（全体での上限）
    limits = {"map": 2, "dashboard": 3, "chat": 1, "hp": 1, "phone": 1}
    used: dict[str, list[str]] = {}
    for p in posts:
        kinds = set()
        for x in p.get("points") or []:
            if x.get("kind") == "phone":
                kinds.add("phone")
            t = (x.get("mock") or {}).get("type", "")
            if t:
                kinds.add("hp" if t.startswith("hp") else t)
        for k in kinds:
            used.setdefault(k, []).append(p["id"])
    for k, ids in used.items():
        if k in limits and len(ids) > limits[k]:
            r.e("全体", f"[単調] 同じ種類の図（{k}）が {len(ids)} 投稿で使われている（上限 {limits[k]}）: {ids}")
    comp_n = sum(1 for p in posts if any(x.get("kind") == "compare" for x in p.get("points") or []))
    if posts and comp_n > len(posts) * 0.3:
        r.e("全体", f"[単調] 比較（よくある→こうする）のページがある投稿が {comp_n}/{len(posts)} 本。3割以下にする")
    for p in posts:
        end = next((sc for sc in (p.get("reel") or {}).get("scenes", []) if sc.get("type") == "end"), {})
        if p.get("end_style") == "ask" and not end.get("ask"):
            r.e(p["id"], "[構成] リールの締めが問いかけ（ask）なのに、問いかけの文（reel の end の ask）がない")
        sm = p.get("summary") or {}
        if sm.get("type") == "one" and not sm.get("note"):
            r.w(p["id"], "[表示] 1行まとめに補足（summary.note）がなく、ページの下が空く")
    voice_n = sum(1 for p in posts if any(x.get("kind") == "voice" for x in p.get("points") or []))
    if posts and voice_n > max(15, len(posts) * 0.3):
        r.w("全体", f"[単調] 吹き出し（voice）のページがある投稿が {voice_n}/{len(posts)} 本。ほかの見せ方に替える")
    for p in posts:  # 文例の日付は曜日と食い違うので「○月○日」にする
        if re.search(r"\d+月\d+日[（(][月火水木金土日][）)]", json.dumps(p.get("points"), ensure_ascii=False)):
            r.e(p["id"], "[事実] 文例に具体的な日付と曜日が入っている（年によって曜日が合わない）。「○月○日（○）」にする")
    ends_key = sum(1 for p in posts if (p.get("points") or [{}])[-1].get("kind") == "key")
    if posts and ends_key / len(posts) > 0.5:
        r.w("全体", f"[単調] 最後のページが「結論」で終わる投稿が {ends_key}/{len(posts)} 本。終わり方を変える")
    q_end = sum(1 for p in posts if plain((p.get("cover_lines") or [""])[-1]).endswith(("？", "?")))
    if posts and q_end / len(posts) > 0.45:
        r.w("全体", f"[単調] 表紙が「？」で終わる投稿が {q_end}/{len(posts)} 本。言い切りの表紙も混ぜる")


def check_render(r: Report, posts: list[dict], cfg_path: Path) -> None:
    import tempfile

    import note_style
    cfg = json.load(open(cfg_path, encoding="utf-8"))
    out = Path(tempfile.mkdtemp())
    for p in posts:
        note_style.FIT_LOG.clear()
        note_style.render_carousel(cfg, p, out / p["id"], p["id"])
        for h, rate in note_style.FIT_LOG:
            if rate < 0.845:
                r.w(p["id"], f"[表示] 「{plain(h)}」のページは文字を {int(rate * 100)}% まで縮めて収めている（中身を減らす）")


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "content" / "webmarketing.json")
    posts = json.load(open(path, encoding="utf-8"))
    r = Report()
    for p in posts:
        check_post(r, p)
    check_series(r, posts)
    if "--render" in sys.argv:
        cfg = Path(sys.argv[sys.argv.index("--config") + 1]) if "--config" in sys.argv else ROOT / "config" / "genova.json"
        check_render(r, posts, cfg)
    errs = [x for x in r.items if x[0] == "E"]
    for lv, pid, msg in r.items:
        print(f"{lv} {pid}: {msg}")
    print(f"\nエラー {len(errs)} 件 / 注意 {len(r.items) - len(errs)} 件")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
