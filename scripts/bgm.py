"""リールの BGM を自分で作る（権利の心配がない、落ち着いたピアノとパッドのループ）。

投稿ごとに調・速さ・コード進行・伴奏の形を変える（同じ曲が続かないように）。
"""
from __future__ import annotations

import hashlib
import wave
from pathlib import Path

import numpy as np

SR = 44100

# よく使う落ち着いたコード進行（度数。0=主和音）
PROGRESSIONS = [
    [0, 5, 3, 4],   # I - vi - IV - V
    [0, 4, 5, 3],   # I - V - vi - IV
    [3, 4, 0, 5],   # IV - V - I - vi
    [5, 3, 0, 4],   # vi - IV - I - V
    [0, 3, 5, 4],   # I - IV - vi - V
]
MAJOR = [0, 2, 4, 5, 7, 9, 11]
KEYS = [0, 2, 3, 5, 7, 8, 10]  # C, D, Eb, F, G, Ab, Bb


def _freq(midi: float) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def _chord(root_deg: int, key: int, octave: int = 4) -> list[int]:
    """度数から3和音（＋7th）を作る。"""
    notes = []
    for k in (0, 2, 4, 6):
        d = root_deg + k
        notes.append(12 * (octave + 1) + key + MAJOR[d % 7] + 12 * (d // 7))
    return notes


def _piano(f: float, dur: float, vel: float) -> np.ndarray:
    t = np.arange(int(SR * dur)) / SR
    env = np.exp(-t * 2.6) * (1 - np.exp(-t * 300))
    w = (np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * 2 * f * t) * np.exp(-t * 4)
         + 0.12 * np.sin(2 * np.pi * 3 * f * t) * np.exp(-t * 7))
    return w * env * vel


def _pad(freqs: list[float], dur: float) -> np.ndarray:
    t = np.arange(int(SR * dur)) / SR
    a = np.minimum(1, t / 0.8) * np.minimum(1, (dur - t) / 0.8)
    w = sum(np.sin(2 * np.pi * f * t + np.sin(2 * np.pi * 0.3 * t) * 0.5) for f in freqs)
    return w * a * 0.05


def make_bgm(seed: str, sec: float, out: Path) -> Path:
    h = int(hashlib.md5(seed.encode()).hexdigest(), 16)
    rng = np.random.default_rng(h % (2 ** 32))
    key = KEYS[h % len(KEYS)]
    prog = PROGRESSIONS[(h // 7) % len(PROGRESSIONS)]
    bpm = 72 + (h // 49) % 18           # 72〜89
    pattern = (h // 900) % 3             # 伴奏の形
    beat = 60 / bpm
    bar = beat * 4
    n = int(SR * (sec + 2))
    mix = np.zeros(n + SR * 4)
    t0, i = 0.0, 0
    while t0 < sec + 1:
        ch = _chord(prog[i % len(prog)], key)
        s = int(t0 * SR)
        pad = _pad([_freq(m - 12) for m in ch[:3]], bar + 0.5)
        mix[s:s + len(pad)] += pad
        bass = _piano(_freq(ch[0] - 24), bar, 0.22)
        mix[s:s + len(bass)] += bass
        if pattern == 0:     # 8分の分散和音
            seq = [ch[0], ch[1], ch[2], ch[3], ch[2] + 12, ch[3], ch[2], ch[1]]
            step = beat / 2
        elif pattern == 1:   # 4分でゆっくり
            seq = [ch[1] + 12, ch[2] + 12, ch[3], ch[2] + 12]
            step = beat
        else:                # 付点のリズム
            seq = [ch[0] + 12, ch[2] + 12, ch[1] + 12, ch[3] + 12, ch[2] + 12, ch[1] + 12]
            step = bar / 6
        for k, m in enumerate(seq):
            v = 0.10 + 0.03 * rng.random()
            note = _piano(_freq(m), 1.6, v)
            st = s + int(k * step * SR)
            mix[st:st + len(note)] += note
        t0 += bar
        i += 1
    mix = mix[:n]
    # 簡単な残響（短い遅延を重ねる）
    for d, g in ((0.11, 0.25), (0.23, 0.15), (0.37, 0.08)):
        k = int(d * SR)
        mix[k:] += mix[:-k] * g
    mix /= max(1e-6, np.abs(mix).max()) / 0.8
    fade = int(SR * 1.5)
    mix[:fade] *= np.linspace(0, 1, fade)
    mix[-fade:] *= np.linspace(1, 0, fade)
    pcm = (mix * 32767).astype(np.int16)
    out.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return out
