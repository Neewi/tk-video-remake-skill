#!/usr/bin/env python3
"""Discover and resolve a portable TikTok remake workspace configuration."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


WORKSPACE_ENV = "TIKTOK_VIDEO_REMAKE_WORKSPACE"
WORKSPACE_FILENAME = "workspace.yaml"


class WorkspaceConfigError(ValueError):
    """Raised when the workspace configuration cannot be found or parsed."""


def _require_file(value: str | Path, source: str) -> Path:
    path = Path(os.path.expandvars(str(value))).expanduser().resolve()
    if not path.is_file():
        raise WorkspaceConfigError(f"{source} 指向的配置文件不存在：{path}")
    return path


def discover_workspace(
    explicit: str | Path | None = None,
    *,
    start: str | Path | None = None,
) -> Path:
    """Resolve workspace.yaml by explicit argument, environment, then parent search."""
    if explicit:
        return _require_file(explicit, "--workspace")

    environment_value = os.environ.get(WORKSPACE_ENV)
    if environment_value:
        return _require_file(environment_value, WORKSPACE_ENV)

    current = Path(start or Path.cwd()).expanduser().resolve()
    if current.is_file():
        current = current.parent
    for folder in (current, *current.parents):
        candidate = folder / WORKSPACE_FILENAME
        if candidate.is_file():
            return candidate.resolve()

    raise WorkspaceConfigError(
        "找不到 workspace.yaml。请在当前项目或其上级目录放置配置文件，"
        f"或使用 --workspace，或设置环境变量 {WORKSPACE_ENV}。"
    )


def load_workspace_config(
    explicit: str | Path | None = None,
    *,
    start: str | Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    workspace_path = discover_workspace(explicit, start=start)
    try:
        with workspace_path.open("r", encoding="utf-8") as handle:
            config = yaml.safe_load(handle)
    except (OSError, yaml.YAMLError) as exc:
        raise WorkspaceConfigError(f"无法读取 {workspace_path}：{exc}") from exc
    if not isinstance(config, dict):
        raise WorkspaceConfigError(f"{workspace_path} 的顶层必须是 YAML 对象")
    return workspace_path, config


def resolve_config_path(workspace_path: Path, value: Any, key: str) -> Path:
    """Resolve an absolute path or a path relative to workspace.yaml."""
    if not isinstance(value, (str, os.PathLike)) or not str(value).strip():
        raise WorkspaceConfigError(f"workspace.yaml 缺少有效配置：{key}")
    expanded = Path(os.path.expandvars(str(value))).expanduser()
    if not expanded.is_absolute():
        expanded = workspace_path.parent / expanded
    return expanded.resolve()
