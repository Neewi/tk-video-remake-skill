#!/usr/bin/env python3
"""Prepare a video evidence bundle for visual/audio analysis with FFmpeg."""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps


def run(command: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
        stderr=subprocess.PIPE if capture else subprocess.DEVNULL,
    )


def remove_generated(folder: Path, pattern: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for path in folder.glob(pattern):
        if path.is_file():
            path.unlink()


def stream_value(probe: dict[str, Any], codec_type: str, key: str, default: Any = None) -> Any:
    for stream in probe.get("streams", []):
        if stream.get("codec_type") == codec_type:
            return stream.get(key, default)
    return default


def make_contact_sheet(frames: list[Path], target: Path, columns: int = 5) -> None:
    if not frames:
        return
    frames = frames[:40]
    cell_w, cell_h, label_h = 300, 534, 28
    rows = math.ceil(len(frames) / columns)
    canvas = Image.new("RGB", (columns * cell_w, rows * (cell_h + label_h)), "#111111")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    for index, path in enumerate(frames):
        with Image.open(path) as source:
            image = ImageOps.contain(source.convert("RGB"), (cell_w, cell_h))
        x = (index % columns) * cell_w + (cell_w - image.width) // 2
        y0 = (index // columns) * (cell_h + label_h)
        y = y0 + (cell_h - image.height) // 2
        canvas.paste(image, (x, y))
        draw.text((8 + (index % columns) * cell_w, y0 + cell_h + 7), path.stem, fill="white", font=font)
    canvas.save(target, quality=90)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument("--sample-fps", type=float, default=2.0)
    parser.add_argument("--scene-threshold", type=float, default=0.28)
    args = parser.parse_args()

    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise SystemExit("需要 ffmpeg 和 ffprobe")
    source = Path(args.input).expanduser().resolve()
    if not source.is_file():
        raise SystemExit(f"输入视频不存在：{source}")
    output = Path(args.output).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    dense_dir = output / "frames-dense"
    scene_dir = output / "frames-scenes"
    remove_generated(dense_dir, "frame_*.jpg")
    remove_generated(scene_dir, "scene_*.jpg")

    probe_result = run(
        [ffprobe, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(source)],
        capture=True,
    )
    probe = json.loads(probe_result.stdout)
    duration = float(probe.get("format", {}).get("duration") or 0)
    has_audio = any(stream.get("codec_type") == "audio" for stream in probe.get("streams", []))

    dense_filter = (
        f"fps={args.sample_fps},"
        "scale=720:-2:force_original_aspect_ratio=decrease"
    )
    run([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
        "-vf", dense_filter, "-q:v", "2", str(dense_dir / "frame_%05d.jpg"),
    ])

    scene_filter = (
        f"select=eq(n\\,0)+gt(scene\\,{args.scene_threshold}),"
        "scale=720:-2:force_original_aspect_ratio=decrease,showinfo"
    )
    scene_process = subprocess.run(
        [
            ffmpeg, "-hide_banner", "-loglevel", "info", "-y", "-i", str(source),
            "-vf", scene_filter, "-fps_mode", "vfr", "-q:v", "2",
            str(scene_dir / "scene_%04d.jpg"),
        ],
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        check=True,
    )
    candidate_times = [float(value) for value in re.findall(r"pts_time:([0-9]+(?:\.[0-9]+)?)", scene_process.stderr)]
    unique_times: list[float] = []
    for value in candidate_times:
        if not unique_times or abs(value - unique_times[-1]) > 0.03:
            unique_times.append(round(value, 3))

    if has_audio:
        run([
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
            "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(output / "audio-analysis.wav"),
        ])

    dense_frames = sorted(dense_dir.glob("frame_*.jpg"))
    make_contact_sheet(dense_frames, output / "contact-sheet.jpg")
    evidence = {
        "source": str(source),
        "duration_seconds": round(duration, 3),
        "width": stream_value(probe, "video", "width"),
        "height": stream_value(probe, "video", "height"),
        "average_frame_rate": stream_value(probe, "video", "avg_frame_rate"),
        "video_codec": stream_value(probe, "video", "codec_name"),
        "audio_codec": stream_value(probe, "audio", "codec_name"),
        "has_audio": has_audio,
        "sample_fps": args.sample_fps,
        "scene_threshold": args.scene_threshold,
        "scene_candidate_times_seconds": unique_times,
        "warning": "候选切点必须通过前后帧人工确认，不能直接当作真实剪辑点。",
        "ffprobe": probe,
    }
    (output / "metadata.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
