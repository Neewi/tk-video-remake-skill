#!/usr/bin/env python3
"""Create a non-destructive run folder for one TikTok remake job."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from datetime import datetime
from pathlib import Path

from workspace_config import WorkspaceConfigError, load_workspace_config, resolve_config_path


SUBDIRS = (
    "00-input",
    "01-analysis",
    "02-storyboard",
    "03-symphony",
)


def safe_part(value: str) -> str:
    value = value.strip().replace(" ", "-")
    value = re.sub(r"[^0-9A-Za-z\u3400-\u9fff._-]+", "-", value)
    return value.strip("-._") or "untitled"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace")
    parser.add_argument("--sku", required=True)
    parser.add_argument("--label", default="爆款复刻")
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()

    source = args.source.expanduser().resolve()
    if not source.is_file():
        raise SystemExit(f"错误：源视频不存在：{source}")

    try:
        workspace_path, config = load_workspace_config(args.workspace)
        output_root = resolve_config_path(workspace_path, config.get("output_root"), "output_root")
    except WorkspaceConfigError as exc:
        raise SystemExit(f"错误：{exc}") from exc
    output_root.mkdir(parents=True, exist_ok=True)

    stem = f"{datetime.now():%Y%m%d-%H%M%S}_{safe_part(args.sku)}_{safe_part(args.label)}"
    run_dir = output_root / stem
    suffix = 2
    while run_dir.exists():
        run_dir = output_root / f"{stem}-{suffix}"
        suffix += 1

    for subdir in SUBDIRS:
        (run_dir / subdir).mkdir(parents=True, exist_ok=True)

    input_name = f"source{source.suffix.lower()}"
    input_path = run_dir / "00-input" / input_name
    shutil.copy2(source, input_path)

    record = {
        "run_id": run_dir.name,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "workspace": str(workspace_path),
        "sku": args.sku,
        "source_video": {
            "original_name": source.name,
            "input_path": input_path.relative_to(run_dir).as_posix(),
            "sha256": file_sha256(input_path),
            "size_bytes": input_path.stat().st_size,
        },
        "status": "created",
        "current_script": None,
        "deliveries": {},
    }
    (run_dir / "run.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
