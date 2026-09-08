#!/usr/bin/env python3
"""Create and track one BASE or Vxx delivery without overwriting other branches."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from run_modes import BATCH_SCRIPT_IDS, DIRECT_BATCH
from validate_generation_duration import EXECUTION_HEADINGS, top_level_section, variant_section


SCRIPT_ID_RE = re.compile(r"^(?:BASE|V\d{2,})$")
GRID_FILES = ("storyboard-grid-b1.png",)


def timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def source_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def branch_titles(review_text: str) -> dict[str, str]:
    titles = {"BASE": "原样复刻"}
    for match in re.finditer(
        r"^##\s+(V\d{2,})\s*[｜|]\s*(.+?)\s*$", review_text, re.MULTILINE
    ):
        titles[match.group(1)] = match.group(2).strip()
    return titles


def update_batch_summary(run_dir: Path, review_text: str, record: dict) -> None:
    if record.get("run_mode") != DIRECT_BATCH:
        return
    deliveries = record.get("deliveries", {})
    titles = branch_titles(review_text)
    lines = [
        "# 六版直出交付汇总",
        "",
        f"- SKU：{record.get('sku', '')}",
        f"- Run：{record.get('run_id', run_dir.name)}",
        f"- 状态：{record.get('status', '')}",
        "",
        "| 分支 | 标题 | 状态 | B1 宫格 | Symphony 提示词 |",
        "|---|---|---|---|---|",
    ]
    for script_id in BATCH_SCRIPT_IDS:
        branch = deliveries.get(script_id, {})
        status = branch.get("status", "pending") if isinstance(branch, dict) else "pending"
        grid = f"02-storyboard/{script_id}/storyboard-grid-b1.png"
        prompt = f"03-symphony/{script_id}/symphony-prompt.txt"
        lines.append(
            f"| {script_id} | {titles.get(script_id, '')} | {status} | "
            f"[B1]({grid}) | [提示词]({prompt}) |"
        )
        if isinstance(branch, dict) and branch.get("last_error"):
            lines.append(f"|  | 失败原因 | {branch['last_error']} |  |  |")
    (run_dir / "delivery-summary.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("start", "complete", "fail"))
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("script_review", type=Path)
    parser.add_argument("script_id")
    parser.add_argument("--reason", default="未记录具体原因")
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
        for folder in (storyboard, symphony):
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
        branch.pop("last_error", None)
        record["current_script"] = script_id
        record["status"] = (
            "batch_generating"
            if record.get("run_mode") == DIRECT_BATCH
            else "generating"
        )
        if changed:
            print(
                "WARNING: 审核文件已不同于先前完成分支的版本；这些旧分支不会自动更新："
                + ", ".join(changed)
            )
        print(storyboard)
        print(symphony)
    elif args.action == "complete":
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
        branch.pop("last_error", None)
        if record.get("current_script") == script_id:
            record["current_script"] = None
        if record.get("run_mode") == DIRECT_BATCH:
            complete = all(
                isinstance(deliveries.get(item), dict)
                and deliveries[item].get("status") == "complete"
                for item in BATCH_SCRIPT_IDS
            )
            record["status"] = "complete" if complete else "batch_generating"
        else:
            record["status"] = "ready_for_another_script"
        print(f"PASS: {script_id} 已标记完成")
    else:
        branch.update(
            {
                "status": "failed",
                "failed_at": timestamp(),
                "last_error": args.reason.strip() or "未记录具体原因",
                "script_review_sha256": digest,
            }
        )
        if record.get("current_script") == script_id:
            record["current_script"] = None
        record["status"] = (
            "batch_partial_failure"
            if record.get("run_mode") == DIRECT_BATCH
            else "delivery_failed"
        )
        print(f"FAILED: {script_id} 已记录，可从该分支继续")

    update_batch_summary(run_dir, review_text, record)
    record_path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
