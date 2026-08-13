#!/usr/bin/env python3
"""Crop a 6/9/12-cell storyboard grid into optional per-cell reference images."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


LAYOUTS = {
    6: (2, 3),
    9: (3, 3),
    12: (3, 4),
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="Storyboard grid image")
    parser.add_argument("output", help="Directory for cell-01.png, cell-02.png, ...")
    parser.add_argument("--cells", type=int, choices=sorted(LAYOUTS), required=True)
    args = parser.parse_args()

    source_path = Path(args.input).expanduser().resolve()
    if not source_path.is_file():
        raise SystemExit(f"输入宫格不存在：{source_path}")
    output_dir = Path(args.output).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    rows, columns = LAYOUTS[args.cells]
    with Image.open(source_path) as source:
        image = source.convert("RGB")
        width, height = image.size
        if width < columns or height < rows:
            raise SystemExit(f"宫格尺寸过小：{width}x{height}")

        for index in range(args.cells):
            row = index // columns
            column = index % columns
            left = round(column * width / columns)
            right = round((column + 1) * width / columns)
            top = round(row * height / rows)
            bottom = round((row + 1) * height / rows)
            cell = image.crop((left, top, right, bottom))
            cell.save(output_dir / f"cell-{index + 1:02d}.png", format="PNG")

    print(output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
