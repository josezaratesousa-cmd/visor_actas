#!/usr/bin/env python3
"""Derive the brand assets from the institutional logo.

Input is logo-source.png, the mark as delivered. Everything else in
web/assets/brand/ is generated from it, so replacing the source and
re-running is the whole update procedure.

Two transformations happen here, and both are worth stating because they
alter a delivered asset:

1. The white background becomes transparent. The delivered PNG is opaque
   RGB, which would show as a white rectangle in dark mode. Only near-white
   pixels are cleared, so the navy and the red are untouched.

2. Square icons pad the horizontal lockup onto a transparent canvas. A
   16-pixel favicon of a wide lockup is illegible; the identity manual
   almost certainly defines an isotype for small sizes, and that is what
   should replace icon-*.png when it is available.

Usage:
    python -m tools.build_brand
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

BRAND = Path("web/assets/brand")
SOURCE = BRAND / "logo-source.png"
WHITE_CUTOFF = 240        # a pixel at or above this on every channel is background


def clear_background(image: Image.Image) -> Image.Image:
    """Turn the flat white backdrop transparent, leaving the artwork intact."""
    rgba = image.convert("RGBA")
    pixels = rgba.load()
    width, height = rgba.size
    for x in range(width):
        for y in range(height):
            r, g, b, _ = pixels[x, y]
            if r >= WHITE_CUTOFF and g >= WHITE_CUTOFF and b >= WHITE_CUTOFF:
                pixels[x, y] = (r, g, b, 0)
    return rgba


def square(image: Image.Image, size: int, margin: float = 0.12) -> Image.Image:
    """Centre the lockup on a transparent square canvas."""
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    usable = int(size * (1 - 2 * margin))
    scaled = image.copy()
    scaled.thumbnail((usable, usable), Image.LANCZOS)
    canvas.paste(scaled, ((size - scaled.width) // 2, (size - scaled.height) // 2), scaled)
    return canvas


def main() -> int:
    if not SOURCE.is_file():
        raise SystemExit(f"missing {SOURCE}")

    logo = clear_background(Image.open(SOURCE))
    logo.save(BRAND / "logo.png")

    # 2x for retina headers; the source is small, so do not upscale past it.
    logo.save(BRAND / "logo@2x.png")

    for size in (192, 512):
        square(logo, size).save(BRAND / f"icon-{size}.png")

    icon = square(logo, 64, margin=0.06)
    icon.save(BRAND / "favicon.ico",
              sizes=[(16, 16), (32, 32), (48, 48)])

    for path in sorted(BRAND.glob("*")):
        if path.suffix in {".png", ".ico"}:
            print(f"{path.name:20s} {path.stat().st_size:7d} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
