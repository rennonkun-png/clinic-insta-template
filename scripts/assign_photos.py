"""中のページ（photo 型）とリール（photo 型）の写真を、投稿をまたいで1枚1回になるように割り当てる。
表紙の写真（cover_photo）とも重ねない。内容に近い系統の写真を優先する。
使い方: python scripts/assign_photos.py content/webmarketing.json
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def pref(pid: str) -> list[str]:
    if any(w in pid for w in ["treatment", "doctor", "staff", "recruit", "no-show", "recall", "accessib", "questionnaire",
                              "regional", "medical", "photo", "price", "access"]):
        return ["clinic", "writing", "desk"]
    if any(w in pid for w in ["analytics", "insights", "budget", "tracking", "estimate", "portal", "listing"]):
        return ["charts", "laptop", "desk"]
    if any(w in pid for w in ["sns", "insta", "reel", "youtube", "hashtag", "line", "review", "gbp"]):
        return ["phone", "desk", "writing"]
    return ["laptop", "desk", "writing"]


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "content" / "webmarketing.json")
    cat = json.load(open(ROOT / "assets" / "photos" / "catalog.json", encoding="utf-8"))
    groups = {k[6:]: list(v) for k, v in cat.items() if k.startswith("inner_")}
    posts = json.load(open(path, encoding="utf-8"))
    used = {p.get("cover_photo") for p in posts}
    short = 0
    for p in posts:
        n = (len(p["points"]) + 1 if p.get("design") == "photo" else 0) + (len(p["points"]) if p.get("reel_style") == "photo" else 0)
        order = pref(p["id"]) + [g for g in groups if g not in pref(p["id"])]
        picks, gi = [], 0
        while len(picks) < n and gi < 1000:
            g = order[gi % len(order)]
            gi += 1
            cand = [ph for ph in groups[g] if ph not in used]
            if cand:
                picks.append(cand[0])
                used.add(cand[0])
        short += n - len(picks)
        if n:
            p["page_photos"] = picks
        else:
            p.pop("page_photos", None)
    json.dump(posts, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"割り当てた写真 {len(used)} 枚" + (f"／足りない {short} 枚（写真を追加してください）" if short else ""))
    return 1 if short else 0


if __name__ == "__main__":
    sys.exit(main())
