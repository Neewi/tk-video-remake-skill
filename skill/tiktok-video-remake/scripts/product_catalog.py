#!/usr/bin/env python3
"""Resolve canonical product SKUs from a workspace product catalog."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from workspace_config import load_workspace_config, resolve_config_path


@dataclass(frozen=True)
class ProductEntry:
    sku: str
    product_name: str
    path: Path
    aliases: tuple[str, ...]
    enabled: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "sku": self.sku,
            "product_name": self.product_name,
            "path": str(self.path),
            "aliases": list(self.aliases),
            "enabled": self.enabled,
        }


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} 的顶层必须是 YAML 对象")
    return data


def load_product_catalog(
    workspace: str | Path | None = None,
) -> tuple[Path, dict[str, Any], list[ProductEntry]]:
    workspace_path, config = load_workspace_config(workspace)
    library = resolve_config_path(
        workspace_path, config.get("product_library"), "product_library"
    )
    catalog = load_yaml(library / "catalog.yaml")
    raw_products = catalog.get("products")
    if not isinstance(raw_products, list) or not raw_products:
        raise ValueError("catalog.yaml.products 必须是非空列表")

    entries: list[ProductEntry] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_products, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"catalog.yaml.products 第 {index} 项必须是对象")
        sku = str(raw.get("sku") or "").strip()
        if not sku:
            raise ValueError(f"catalog.yaml.products 第 {index} 项缺少 sku")
        folded = sku.casefold()
        if folded in seen:
            raise ValueError(f"catalog.yaml 中 SKU 重复：{sku}")
        seen.add(folded)

        relative = Path(str(raw.get("path") or f"./{sku}"))
        product_dir = relative.expanduser()
        if not product_dir.is_absolute():
            product_dir = library / product_dir
        product_dir = product_dir.resolve()
        try:
            product_dir.relative_to(library.resolve())
        except ValueError as exc:
            raise ValueError(f"SKU `{sku}` 的 path 必须位于产品资料库内") from exc

        enabled = raw.get("enabled", True) is not False
        product_file = product_dir / "product.yaml"
        if enabled or product_file.is_file():
            product = load_yaml(product_file)
        else:
            product = {}
        product_name = str(
            raw.get("product_name") or product.get("product_name") or sku
        ).strip()
        aliases: list[str] = []
        for source in (raw.get("aliases", []), product.get("aliases", [])):
            if isinstance(source, list):
                aliases.extend(str(value).strip() for value in source if str(value).strip())
        entries.append(
            ProductEntry(
                sku=sku,
                product_name=product_name,
                path=product_dir,
                aliases=tuple(dict.fromkeys(aliases)),
                enabled=enabled,
            )
        )
    return workspace_path, catalog, entries


def select_product(
    entries: list[ProductEntry], catalog: dict[str, Any], requested: str | None
) -> tuple[ProductEntry, str]:
    query = str(requested or "").strip()
    resolution = "explicit"
    if not query:
        query = str(catalog.get("default_sku") or "").strip()
        resolution = "default"
        if not query:
            raise ValueError("未指定 SKU，且 catalog.yaml 没有 default_sku")

    key = query.casefold()
    matches: list[ProductEntry] = []
    for entry in entries:
        terms = (entry.sku, entry.product_name, *entry.aliases)
        if entry.enabled and any(key == term.casefold() for term in terms):
            matches.append(entry)
    if not matches:
        available = "、".join(entry.sku for entry in entries if entry.enabled)
        raise ValueError(f"找不到 SKU 或别名 `{query}`。可选 SKU：{available or '无'}")
    if len(matches) > 1:
        choices = "、".join(entry.sku for entry in matches)
        raise ValueError(f"SKU 或别名 `{query}` 匹配多个产品：{choices}")
    return matches[0], resolution
