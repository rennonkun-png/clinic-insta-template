"""リール動画の生成（ffmpeg を使用）。フレーム画像を順番に表示し、軽いズームとフェードを付ける。"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from common import log


def ffmpeg_path() -> str | None:
    """システムの ffmpeg、無ければ pip の imageio-ffmpeg 同梱バイナリを使う。"""
    p = shutil.which("ffmpeg")
    if p:
        return p
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def ffmpeg_available() -> bool:
    return ffmpeg_path() is not None


def build_reel(frames: list[tuple[Path, float]], out_path: Path, fps: int = 30) -> Path:
    """frames: [(画像パス, 秒数), ...] → 1080x1920 の mp4 (H.264 + 無音AAC)。
    Instagram リールの要件: 3秒〜15分、縦 9:16 推奨、H.264/AAC。
    """
    ff = ffmpeg_path()
    if not ff:
        raise RuntimeError("ffmpeg が見つかりません（GitHub Actions では自動インストールされます）")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    inputs: list[str] = []
    filters: list[str] = []
    for i, (p, sec) in enumerate(frames):
        inputs += ["-i", str(p)]  # 静止画1枚 → zoompan が sec 秒ぶんのフレームを生成
        n = int(sec * fps)
        # ゆっくりズームイン + 冒頭/末尾のフェード
        filters.append(
            f"[{i}:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
            f"zoompan=z='min(zoom+0.0006,1.08)':d={n}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps={fps},"
            f"fade=t=in:st=0:d=0.3,fade=t=out:st={max(0.0, sec - 0.3):.2f}:d=0.3,setsar=1,format=yuv420p[v{i}]"
        )
    concat = "".join(f"[v{i}]" for i in range(len(frames))) + f"concat=n={len(frames)}:v=1:a=0[vout]"
    total = sum(s for _, s in frames)
    cmd = [
        ff, "-y", "-loglevel", "error",
        *inputs,
        "-f", "lavfi", "-t", f"{total:.2f}", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-filter_complex", ";".join(filters) + ";" + concat,
        "-map", "[vout]", "-map", f"{len(frames)}:a",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-r", str(fps),
        "-c:a", "aac", "-b:a", "96k", "-shortest", "-movflags", "+faststart",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)
    log(f"リール動画を生成しました: {out_path} ({total:.1f}秒)")
    return out_path
