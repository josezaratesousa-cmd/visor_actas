"""Local filesystem custody.

Useful for development, for an on-premise deployment where the documents
sit on the same machine, and as the reference implementation a client can
copy when writing a driver for their own system.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from app.config import Settings
from app.services.custody import (
    CustodyError,
    Document,
    DocumentNotFound,
    register,
    safe_identifier,
)


@register("local")
class LocalCustody:
    """Reads PDFs from a directory tree."""

    def __init__(self, settings: Settings):
        self._root = Path(settings.custody_path).resolve()

    def _resolve(self, identifier: str) -> Path:
        safe_identifier(identifier)
        candidate = (self._root / f"{identifier}.pdf").resolve()

        # Belt and braces: even with a validated identifier, confirm the
        # resolved path really sits under the root. Symlinks inside the tree
        # can point anywhere, and resolve() follows them.
        if not candidate.is_relative_to(self._root):
            raise CustodyError("resolved path escapes the storage root")
        return candidate

    async def fetch(self, identifier: str) -> Document:
        path = self._resolve(identifier)
        try:
            content = await asyncio.to_thread(path.read_bytes)
        except FileNotFoundError as exc:
            raise DocumentNotFound(f"no document for '{identifier}'") from exc
        except OSError as exc:
            raise CustodyError(f"cannot read document: {exc}") from exc

        return Document(identifier=identifier, content=content)

    async def exists(self, identifier: str) -> bool:
        try:
            path = self._resolve(identifier)
        except CustodyError:
            return False
        return await asyncio.to_thread(path.is_file)
