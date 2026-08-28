#!/usr/bin/env python3
"""Render a signed PDF to page images.

The viewer shows images, not an embedded PDF. No PDF viewer works reliably
across phones, and a rendering library costs more than a megabyte before it
draws anything. Rendered once at registration and cached, the pages load on
any device without JavaScript.

Two densities are produced so each phone downloads only what its screen can
use. WebP because it is roughly a third of the size of PNG at the same
quality and is supported everywhere that matters today.

Usage:
    python -m tools.render_pages sheet.pdf --out web/assets/sample
"""

from __future__ import annotations

import argparse
import io
from pathlib import Path

import fitz
from PIL import Image

DENSITIES = {"": 110, "@2x": 220}


def render(pdf: Path, out_dir: Path, quality: int = 82) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    document = fitz.open(str(pdf))
    try:
        for number, page in enumerate(document, start=1):
            for suffix, dpi in DENSITIES.items():
                pixmap = page.get_pixmap(dpi=dpi)
                image = Image.open(io.BytesIO(pixmap.tobytes("png")))
                target = out_dir / f"page-{number}{suffix}.webp"
                image.save(target, "WEBP", quality=quality, method=6)
                print(f"{target}  {target.stat().st_size} bytes  ({dpi} dpi)")
    finally:
        document.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--quality", type=int, default=82)
    args = parser.parse_args()
    render(args.pdf, args.out, args.quality)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
