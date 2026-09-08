#!/usr/bin/env python3
"""List available products or resolve a user-provided SKU/alias."""

from __future__ import annotations

import argparse
import json

import yaml

from product_catalog import load_product_catalog, select_product
from workspace_config import WorkspaceConfigError


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace")
    parser.add_argument("--sku", help="SKU、产品名或别名；省略时选择 default_sku")
    parser.add_argument("--list", action="store_true", help="列出所有启用的 SKU")
    args = parser.parse_args()

    try:
        _, catalog, entries = load_product_catalog(args.workspace)
        enabled = [entry for entry in entries if entry.enabled]
        if args.list:
            print(
                json.dumps(
                    {
                        "default_sku": catalog.get("default_sku"),
                        "products": [entry.as_dict() for entry in enabled],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        selected, resolution = select_product(entries, catalog, args.sku)
        result = selected.as_dict()
        result["requested"] = args.sku
        result["resolution"] = resolution
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, KeyError, ValueError, WorkspaceConfigError, yaml.YAMLError) as exc:
        print(f"错误：{exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
