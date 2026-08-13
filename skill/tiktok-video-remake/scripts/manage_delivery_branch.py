#!/usr/bin/env python3
"""Create and track one BASE or Vxx delivery without overwriting other branches."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from validate_generation_duration import EXECUTION_HEADINGS, top_level_section, variant_section


SCRIPT_ID_RE = re.compile(r"^(?:BASE|V\d{2,})$")
CROP_DIRS = ("crops-a1", "crops-a2", "crops-b1", "crops-b2")
GRID_FILES = (
    "storyboard-grid-a1.png",
    "storyboard-grid-a2.png",
    "storyboard-grid-b1.png",
    "storyboard-grid-b2.png",
)


def timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def source_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("start", "complete"))
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("script_review", type=Path)
    parser.add_argument("script_id")
    args = parser.parse_args()

    run_dir = args.run_dir.expanduser().resolve()
    review = args.script_review.expanduser().resolve()
    script_id = args.script_id.strip().upper()
    record_path = run_dir / "run.json"

    if not SCRIPT_ID_RE.fullmatch(script_id):
        raise SystemExit("错误：script_id 必须是 BASE 或 V 加至少两位数字，例如 V01")
    if not record_path.is_file():
        raise SystemExit(f"错误：任务记录不存在：{record_path}")
    if not review.is_file():
        raise SystemExit(f"错误：审核文件不存在：{review}")

    review_text = review.read_text(encoding="utf-8")
    try:
        top_level_section(review_text, EXECUTION_HEADINGS)
        if script_id != "BASE":
            variant_section(review_text, script_id)
    except ValueError as exc:
        raise SystemExit(f"错误：{exc}") from exc

    record = json.loads(record_path.read_text(encoding="utf-8"))
    deliveries = record.setdefault("deliveries", {})
    digest = source_hash(review)
    branch = deliveries.setdefault(script_id, {})

    if args.action == "start":
        storyboard = run_dir / "02-storyboard" / script_id
        symphony = run_dir / "03-symphony" / script_id
        for folder in (storyboard, symphony, *(storyboard / name for name in CROP_DIRS)):
            folder.mkdir(parents=True, exist_ok=True)

        changed = sorted(
            key
            for key, value in deliveries.items()
            if key != script_id
            and isinstance(value, dict)
            and value.get("status") == "complete"
            and value.get("script_review_sha256") != digest
        )
        branch.update(
            {
                "status": "in_progress",
                "started_at": timestamp(),
                "script_review_sha256": digest,
            }
        )
        record["current_script"] = script_id
        record["status"] = "generating"
        if changed:
            print(
                "WARNING: 审核文件已不同于先前完成分支的版本；这些旧分支不会自动更新："
                + ", ".join(changed)
            )
        print(storyboard)
        print(symphony)
    else:
        required = [
            *(run_dir / "02-storyboard" / script_id / name for name in GRID_FILES),
            run_dir / "03-symphony" / script_id / "symphony-prompt.txt",
        ]
        missing = [str(path) for path in required if not path.is_file() or path.stat().st_size == 0]
        if missing:
            raise SystemExit("错误：分支交付文件缺失或为空：\n" + "\n".join(missing))
        branch.update(
            {
                "status": "complete",
                "completed_at": timestamp(),
                "script_review_sha256": digest,
            }
        )
        if record.get("current_script") == script_id:
            record["current_script"] = None
        record["status"] = "ready_for_another_script"
        print(f"PASS: {script_id} 已标记完成")

    record_path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
