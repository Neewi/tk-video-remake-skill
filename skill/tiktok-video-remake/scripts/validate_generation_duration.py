#!/usr/bin/env python3
"""Validate source or approved-script duration against the workspace limit."""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from workspace_config import WorkspaceConfigError, load_workspace_config


EXECUTION_HEADINGS = (
    "复刻执行脚本（原样复刻，独立可执行）",
    "复刻执行脚本（后续唯一生效）",
)
SCRIPT_ID_RE = re.compile(r"^(?:BASE|V\d{2,})$")
VARIANT_HEADING_RE = re.compile(r"^##\s+(V\d{2,})(?:\s*[｜|].*)?$", re.MULTILINE)
TIME_RANGE_RE = re.compile(
    r"(?P<start>\d+(?:\.\d+)?)\s*[–—-]\s*(?P<end>\d+(?:\.\d+)?)\s*秒"
)


def max_clip_seconds(config: dict[str, Any]) -> float:
    generation = config.get("generation")
    value = generation.get("max_clip_seconds") if isinstance(generation, dict) else None
    if isinstance(value, bool):
        raise ValueError("workspace.yaml 的 generation.max_clip_seconds 必须是正数")
    try:
        limit = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("workspace.yaml 的 generation.max_clip_seconds 必须是正数") from exc
    if not math.isfinite(limit) or limit <= 0:
        raise ValueError("workspace.yaml 的 generation.max_clip_seconds 必须是正数")
    return limit


def video_duration(path: Path) -> float:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise ValueError("需要 ffprobe 读取源视频时长")
    if not path.is_file():
        raise ValueError(f"源视频不存在：{path}")
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    duration = float(json.loads(result.stdout).get("format", {}).get("duration") or 0)
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError(f"无法读取有效的源视频时长：{path}")
    return duration


def top_level_section(text: str, headings: tuple[str, ...]) -> str:
    heading_names = "|".join(re.escape(value) for value in headings)
    heading = re.search(rf"^#\s+(?:{heading_names})\s*$", text, flags=re.MULTILINE)
    if not heading:
        raise ValueError("审核文件缺少独立的“复刻执行脚本”标题")
    section = text[heading.end() :]
    next_heading = re.search(r"^#\s+", section, flags=re.MULTILINE)
    return section[: next_heading.start()] if next_heading else section


def variant_section(text: str, script_id: str) -> str:
    matches = list(VARIANT_HEADING_RE.finditer(text))
    selected = [(index, match) for index, match in enumerate(matches) if match.group(1) == script_id]
    if len(selected) > 1:
        raise ValueError(f"审核文件中变体 {script_id} 出现多次")
    for index, match in selected:
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        top_heading = re.search(r"^#\s+", text[match.end() : end], flags=re.MULTILINE)
        if top_heading:
            end = match.end() + top_heading.start()
        return text[match.end() : end]
    raise ValueError(f"审核文件中不存在变体 {script_id}")


def duration_from_ranges(section: str, label: str) -> float:
    ranges = [
        (float(match["start"]), float(match["end"]))
        for match in TIME_RANGE_RE.finditer(section)
    ]
    if not ranges:
        raise ValueError(f"{label}中没有可识别的“起始–结束 秒”时间码")
    if any(end <= start for start, end in ranges):
        raise ValueError(f"{label}包含结束时间不大于起始时间的镜头")
    return max(end for _, end in ranges)


def approved_script_duration(path: Path, script_id: str = "BASE") -> float:
    if not path.is_file():
        raise ValueError(f"审核文件不存在：{path}")
    text = path.read_text(encoding="utf-8")
    script_id = script_id.strip().upper()
    if not SCRIPT_ID_RE.fullmatch(script_id):
        raise ValueError("script_id 必须是 BASE 或 V 加至少两位数字，例如 V01")
    base_duration = duration_from_ranges(
        top_level_section(text, EXECUTION_HEADINGS), "复刻执行脚本"
    )
    if script_id == "BASE":
        return base_duration
    override = variant_section(text, script_id)
    override_ranges = list(TIME_RANGE_RE.finditer(override))
    if not override_ranges:
        return base_duration
    override_duration = duration_from_ranges(override, f"变体 {script_id}")
    return max(base_duration, override_duration)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--video", type=Path)
    source.add_argument("--script-review", type=Path)
    parser.add_argument("--script-id", default="BASE")
    args = parser.parse_args()

    try:
        _, config = load_workspace_config(args.workspace)
        limit = max_clip_seconds(config)
        if args.video:
            label = "源视频"
            duration = video_duration(args.video.expanduser().resolve())
        else:
            script_id = args.script_id.strip().upper()
            label = f"批准稿 {script_id} 目标视频"
            duration = approved_script_duration(
                args.script_review.expanduser().resolve(), script_id
            )
    except (OSError, ValueError, WorkspaceConfigError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 2

    if duration > limit:
        print(f"ERROR: {label}时长 {duration:.3f} 秒，超过 Symphony 单段上限 {limit:g} 秒")
        return 1

    print(f"PASS: {label}时长 {duration:.3f} 秒，不超过上限 {limit:g} 秒")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
