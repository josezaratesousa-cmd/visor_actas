"""Page images, rendered once and cached.

The viewer shows images rather than an embedded PDF because no PDF viewer
works reliably across phones. Rendering is expensive, so it happens once per
sheet and the result is keyed by the document hash: if the file ever changes,
the key changes with it and a stale page cannot be served by mistake.
"""

from __future__ import annotations

import asyncio
import io
from pathlib import Path

from app.config import Settings

DENSITIES = {"": 110, "@2x": 220}


class PageRenderer:
    def __init__(self, settings: Settings):
        self._cache = Path(settings.cache_path)

    def _dir_for(self, sha256: str) -> Path:
        return self._cache / sha256[:2] / sha256

    async def page_count(self, content: bytes) -> int:
        return await asyncio.to_thread(self._count, content)

    async def page(self, content: bytes, sha256: str, number: int,
                   density: str = "") -> bytes:
        target = self._dir_for(sha256) / f"page-{number}{density}.webp"
        if target.is_file():
            return await asyncio.to_thread(target.read_bytes)
        return await asyncio.to_thread(self._render, content, sha256, number, density)

    # ── blocking work, always via to_thread ───────────────────────────────

    @staticmethod
    def _count(content: bytes) -> int:
        import fitz
        with fitz.open(stream=content, filetype="pdf") as document:
            return document.page_count

    def _render(self, content: bytes, sha256: str, number: int, density: str) -> bytes:
        import fitz
        from PIL import Image

        directory = self._dir_for(sha256)
        directory.mkdir(parents=True, exist_ok=True)

        with fitz.open(stream=content, filetype="pdf") as document:
            if not 1 <= number <= document.page_count:
                raise IndexError(number)
            pixmap = document[number - 1].get_pixmap(dpi=DENSITIES.get(density, 110))

        image = Image.open(io.BytesIO(pixmap.tobytes("png")))
        buffer = io.BytesIO()
        image.save(buffer, "WEBP", quality=82, method=6)
        data = buffer.getvalue()
        (directory / f"page-{number}{density}.webp").write_bytes(data)
        return data
