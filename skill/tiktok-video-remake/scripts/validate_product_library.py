#!/usr/bin/env python3
"""Validate the mutable product library without modifying product assets."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from workspace_config import WorkspaceConfigError, load_workspace_config, resolve_config_path


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
REQUIRED_FIELDS = ("sku", "product_name", "bundle_includes", "allowed_claims", "forbidden_claims")


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} 的顶层必须是 YAML 对象")
    return data


def list_images(folder: Path) -> list[str]:
    if not folder.exists():
        return []
    return sorted(
        str(path.relative_to(folder.parent.parent))
        for path in folder.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace")
    parser.add_argument("--sku")
    parser.add_argument("--json-output")
    args = parser.parse_args()

    errors: list[str] = []
    warnings: list[str] = []
    report: dict[str, Any] = {}

    try:
        workspace_path, workspace = load_workspace_config(args.workspace)
        library = resolve_config_path(
            workspace_path, workspace.get("product_library"), "product_library"
        )
        catalog = load_yaml(library / "catalog.yaml")
    except (OSError, KeyError, ValueError, WorkspaceConfigError, yaml.YAMLError) as exc:
        print(f"错误：{exc}")
        return 2

    sku = args.sku or str(catalog.get("default_sku") or "").strip()
    if not sku:
        print("错误：未指定 SKU，且 catalog.yaml 没有 default_sku")
        return 2

    product_dir = library / sku
    if not product_dir.is_dir() or sku.startswith(("_", ".")):
        print(f"错误：SKU 目录不存在：{product_dir}")
        return 2

    product_file = product_dir / "product.yaml"
    try:
        product = load_yaml(product_file)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"错误：{exc}")
        return 2

    for field in REQUIRED_FIELDS:
        if field not in product or product[field] in (None, "", []):
            errors.append(f"product.yaml 缺少有效字段：{field}")
    if product.get("sku") != sku:
        errors.append(f"目录 SKU `{sku}` 与 product.yaml.sku `{product.get('sku')}` 不一致")

    images_root = product_dir / "images"
    categories = {
        name: list_images(images_root / name)
        for name in ("tablet", "accessories", "bundle", "screen")
    }
    if not categories["tablet"]:
        errors.append("images/tablet 中没有平板主体参考图")
    if not categories["bundle"]:
        warnings.append("images/bundle 中没有全套合照，套装空间关系可能不稳定")
    if len(categories["tablet"]) < 3:
        warnings.append("平板主体图少于 3 张，建议补充正面、背面和 3/4 透视")
    includes = {str(item).lower() for item in product.get("bundle_includes", [])}
    if len(includes - {"tablet"}) > 0 and not categories["accessories"]:
        warnings.append("声明包含配件，但 images/accessories 中没有独立配件图")

    offer = product.get("offer")
    if isinstance(offer, dict) and offer.get("valid_until"):
        try:
            if date.fromisoformat(str(offer["valid_until"])) < date.today():
                warnings.append("offer 已过期，脚本中不得继续使用该价格或活动")
        except ValueError:
            warnings.append("offer.valid_until 不是 YYYY-MM-DD 格式")

    priority = product.get("reference_priority", [])
    for relative in priority if isinstance(priority, list) else []:
        if not (product_dir / str(relative)).is_file():
            warnings.append(f"首选参考图不存在：{relative}")

    report = {
        "sku": sku,
        "product_name": product.get("product_name"),
        "product_dir": str(product_dir),
        "images": categories,
        "errors": errors,
        "warnings": warnings,
        "valid": not errors,
    }
    output = json.dumps(report, ensure_ascii=False, indent=2)
    print(output)
    if args.json_output:
        target = Path(args.json_output).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(output + "\n", encoding="utf-8")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
