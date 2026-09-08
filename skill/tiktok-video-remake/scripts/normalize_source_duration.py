#!/usr/bin/env python3
"""Trim an overlong run-bound source video to the configured leading segment."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

from create_run import file_sha256
from validate_generation_duration import max_clip_seconds, video_duration
from workspace_config import WorkspaceConfigError, load_workspace_config


def write_record(path: Path, record: dict) -> None:
    path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def bound_source(run_dir: Path, record: dict) -> tuple[Path, dict]:
    source_video = record.get("source_video")
    if not isinstance(source_video, dict):
        raise ValueError("run.json 缺少 source_video")
    relative = source_video.get("input_path")
    expected_hash = source_video.get("sha256")
    if not isinstance(relative, str) or not isinstance(expected_hash, str):
        raise ValueError("run.json 的 source_video 绑定信息不完整")
    source = (run_dir / relative).resolve()
    try:
        source.relative_to(run_dir)
    except ValueError as exc:
        raise ValueError("run.json 的源视频路径必须位于当前 run 内") from exc
    if not source.is_file():
        raise ValueError(f"run 绑定的源视频不存在：{source}")
    if file_sha256(source) != expected_hash:
        raise ValueError("源视频哈希与 run.json 不一致，不得裁剪或继续分析")
    return source, source_video


def trim_to_mp4(source: Path, target: Path, seconds: float) -> None:
    ffmpeg = os.environ.get("FFMPEG_BIN") or shutil.which("ffmpeg")
    if not ffmpeg:
        raise ValueError("需要 ffmpeg 自动裁剪超长源视频")
    temporary = target.with_name(".source-trimmed.tmp.mp4")
    temporary.unlink(missing_ok=True)
    try:
        subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(source),
                "-t",
                f"{seconds:g}",
                "-map",
                "0:v:0",
                "-map",
                "0:a:0?",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-movflags",
                "+faststart",
                str(temporary),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--workspace")
    args = parser.parse_args()

    run_dir = args.run_dir.expanduser().resolve()
    record_path = run_dir / "run.json"
    try:
        if not record_path.is_file():
            raise ValueError(f"任务记录不存在：{record_path}")
        record = json.loads(record_path.read_text(encoding="utf-8"))
        source, source_video = bound_source(run_dir, record)
        workspace = args.workspace or record.get("workspace")
        _, config = load_workspace_config(workspace)
        limit = max_clip_seconds(config)
        duration = video_duration(source)

        if duration <= limit:
            source_video["duration_seconds"] = duration
            source_video.setdefault("trimmed", False)
            write_record(record_path, record)
            print(f"PASS: 源视频 {duration:.3f} 秒，无需裁剪")
            print(source)
            return 0

        original_hash = source_video["sha256"]
        original_size = source_video.get("size_bytes")
        target = source.with_name("source.mp4")
        trim_to_mp4(source, target, limit)
        trimmed_duration = video_duration(target)
        if trimmed_duration > limit + 0.05:
            raise ValueError(
                f"裁剪结果 {trimmed_duration:.3f} 秒仍超过上限 {limit:g} 秒"
            )
        if source != target:
            source.unlink()

        source_video.update(
            {
                "input_path": target.relative_to(run_dir).as_posix(),
                "sha256": file_sha256(target),
                "size_bytes": target.stat().st_size,
                "duration_seconds": trimmed_duration,
                "trimmed": True,
                "trim_range_seconds": [0, limit],
                "original_sha256": original_hash,
                "original_size_bytes": original_size,
                "original_duration_seconds": duration,
            }
        )
        write_record(record_path, record)
        print(
            f"TRIMMED: 源视频 {duration:.3f} 秒，已自动截取前 {limit:g} 秒并继续"
        )
        print(target)
        return 0
    except (
        OSError,
        ValueError,
        WorkspaceConfigError,
        subprocess.CalledProcessError,
        json.JSONDecodeError,
    ) as exc:
        print(f"ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
