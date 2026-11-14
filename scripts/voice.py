"""リールの読み上げ（AI音声）。

投稿の "narration"（場面ごとの台本の配列）を音声にし、場面の始まりに合わせて動画に重ねる。
- 音声は Microsoft Edge の読み上げ（edge-tts、無料・キー不要）。声は config の reel.voice で変えられる。
- 音声が作れなかったとき（ネットにつながらない等）は、無音のまま投稿を続ける。
"""
from __future__ import annotations

import asyncio
import re
import subprocess
import wave
from pathlib import Path

from media import ffmpeg_path

DEFAULT_VOICE = "ja-JP-NanamiNeural"
DEFAULT_RATE = "+15%"

# 読み間違えやすい語の読み（画面の字はそのまま、声だけ直す）
READINGS = {
    "Googleビジネスプロフィール": "グーグルビジネスプロフィール",
    "Googleマップ": "グーグルマップ",
    "Google": "グーグル",
    "PageSpeed Insights": "ページスピードインサイツ",
    "Search Console": "サーチコンソール",
    "Instagram": "インスタグラム",
    "LINE公式アカウント": "ラインこうしきアカウント",
    "LINE": "ライン",
    "ChatGPT": "チャットジーピーティー",
    "HP": "ホームページ",
    "MEO": "エムイーオー",
    "LLMO": "エルエルエムオー",
    "SEO": "エスイーオー",
    "DM": "ディーエム",
    "Web": "ウェブ",
    "WEB": "ウェブ",
    "〇〇": "まるまる",
    "院長": "いんちょう",
}


def speakable(text: str) -> str:
    """画面用の記号（*強調* ==マーカー== 改行）を外し、読みを直す。"""
    t = re.sub(r"[*=]", "", text or "").replace("\n", "、")
    for k, v in READINGS.items():
        t = t.replace(k, v)
    return t.strip()


def _duration(wav: Path) -> float:
    with wave.open(str(wav)) as w:
        return w.getnframes() / float(w.getframerate())


async def _synth_all(texts: list[str], work: Path, voice: str, rate: str) -> list[Path | None]:
    import edge_tts

    outs: list[Path | None] = []
    for i, tx in enumerate(texts):
        if not tx:
            outs.append(None)
            continue
        mp3 = work / f"n{i:02d}.mp3"
        for attempt in range(3):
            try:
                await asyncio.wait_for(edge_tts.Communicate(tx, voice, rate=rate).save(str(mp3)), timeout=60)  # つながらないまま止まらないように
                break
            except Exception:  # 一時的な失敗は少し待ってやり直す
                if attempt == 2:
                    raise
                await asyncio.sleep(2)
        outs.append(mp3)
    return outs


def _gain_to(path: Path, target_db: float) -> float:
    """曲の平均音量を測り、target_db にそろえる倍率を返す。"""
    r = subprocess.run([ffmpeg_path(), "-i", str(path), "-t", "60", "-af", "volumedetect", "-vn", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=120)
    m = re.search(r"mean_volume: (-?[0-9.]+)", r.stderr)
    return 10 ** ((target_db - float(m.group(1))) / 20) if m else 1.0


class Narration:
    """場面ごとの音声。need(i) で i 番目の場面に必要な長さ（秒）がわかる。"""

    def __init__(self, cfg: dict, post: dict, work: Path):
        self.items: list[tuple[Path, float] | None] = []
        self.work = work
        rc0 = cfg.get("reel") or {}
        self.bgm_src = rc0.get("bgm", "generate")
        self.bgm_volume = float(rc0.get("bgm_volume", 0.14))
        self.seed = str(post.get("id", ""))
        self.reel_days = (cfg.get("formats") or {}).get("reel_weekdays")
        work.mkdir(parents=True, exist_ok=True)
        self.starts: list[float] = []
        lines = post.get("narration") or []
        if not lines or (cfg.get("reel") or {}).get("voice") is False:
            return
        rc = cfg.get("reel") or {}
        voice = rc.get("voice") or DEFAULT_VOICE
        rate = rc.get("voice_rate") or DEFAULT_RATE
        ff = ffmpeg_path()
        work.mkdir(parents=True, exist_ok=True)
        try:
            print(f"[voice] 読み上げを作ります（{len(lines)} 場面）", flush=True)
            mp3s = asyncio.run(_synth_all([speakable(x) for x in lines], work, voice, rate))
            for mp3 in mp3s:
                if mp3 is None:
                    self.items.append(None)
                    continue
                wav = mp3.with_suffix(".wav")
                subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(mp3), "-ar", "44100", "-ac", "2", str(wav)], check=True, timeout=120)
                self.items.append((wav, _duration(wav)))
        except Exception as e:  # 音声が作れなくても動画は出す
            print(f"[voice] 読み上げを作れなかったため無音にします: {e}")
            self.items = []

    def music(self, total_sec: float) -> Path | None:
        """BGM のファイル。config の reel.bgm: "generate"（自作）/ フォルダ（素材の曲から投稿ごとに選ぶ）/ false（なし）。"""
        src = self.bgm_src
        if not src:
            return None
        try:
            if src == "generate":
                import bgm
                return bgm.make_bgm(self.seed, total_sec, self.work / "bgm.wav")
            files = sorted(p for p in Path(src).glob("*") if p.suffix.lower() in (".mp3", ".wav", ".m4a", ".ogg"))
            if files:
                import random
                # 並びを決まった順に混ぜ（同じ作曲者が続かないように）、リールを出す日ごとに1曲ずつ進める。
                # 全曲を1回ずつ使い切るまで、同じ曲は出ない。
                random.Random(7).shuffle(files)
                f = files[self.reel_number() % len(files)]
                self.music_gain = _gain_to(f, -14.0)  # 曲ごとの音量の差をそろえる
                return f
            import bgm  # 曲のファイルが無いときは自作の曲にする
            return bgm.make_bgm(self.seed, total_sec, self.work / "bgm.wav")
        except Exception as e:
            print(f"[voice] BGM を付けられなかったため声だけにします: {e}")
        return None

    def reel_number(self) -> int:
        """今日が何本目のリールか（2026-01-01 から数えた、リールを出す曜日の日数）。"""
        import datetime
        days = set(self.reel_days or [3, 6])  # common.choose_format と同じ初期値
        d0, today = datetime.date(2026, 1, 1), datetime.date.today()
        return sum(1 for k in range((today - d0).days + 1)
                   if (d0 + datetime.timedelta(days=k)).isoweekday() in days)

    def __bool__(self) -> bool:
        return any(self.items)

    def need(self, i: int) -> float:
        """i 番目の場面に必要な秒数（話し終わり＋少しの間）。"""
        if i < len(self.items) and self.items[i]:
            return self.items[i][1] + 0.45
        return 0.0

    def mark(self, i: int, sec: float) -> None:
        while len(self.starts) <= i:
            self.starts.append(-1.0)
        self.starts[i] = sec

    def mux(self, video: Path, total_sec: float) -> None:
        """場面の始まりに合わせて音声を重ね、動画の音を差し替える。"""
        segs = [(it[0], st) for it, st in zip(self.items, self.starts) if it and st >= 0]
        music = self.music(total_sec)
        if not segs and not music:
            return
        ff = ffmpeg_path()
        tmp = video.with_name(video.stem + "_v.mp4")
        video.replace(tmp)
        args = [ff, "-y", "-loglevel", "error", "-i", str(tmp)]
        filt = []
        for k, (wav, st) in enumerate(segs, 1):
            args += ["-i", str(wav)]
            ms = int((st + 0.2) * 1000)
            filt.append(f"[{k}:a]adelay={ms}|{ms}[a{k}]")
        labels = [f"[a{k}]" for k in range(1, len(segs) + 1)]
        if music:  # BGM は声の後ろで小さく流し、最後はフェードアウト
            m = len(segs) + 1
            args += ["-stream_loop", "-1", "-i", str(music)]
            vol = (self.bgm_volume if segs else self.bgm_volume * 2.2) * getattr(self, "music_gain", 1.0)
            filt.append(f"[{m}:a]aresample=44100,aformat=channel_layouts=stereo,atrim=0:{total_sec:.2f},"
                        f"volume={vol:.3f},afade=t=in:d=1,afade=t=out:st={max(0, total_sec - 2):.2f}:d=2[bg]")
            labels.append("[bg]")
        filt.append(f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0,apad[aout]")
        args += ["-filter_complex", ";".join(filt), "-map", "0:v", "-map", "[aout]",
                 "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-t", f"{total_sec:.2f}", "-movflags", "+faststart", str(video)]
        print(f"[voice] 声 {len(segs)} 場面と BGM（{'あり' if music else 'なし'}）を重ねます", flush=True)
        subprocess.run(args, check=True, timeout=600)
        tmp.unlink(missing_ok=True)
        import shutil
        shutil.rmtree(self.work, ignore_errors=True)  # 作業用の音声は消す
