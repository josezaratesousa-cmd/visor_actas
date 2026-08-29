"""Placeholder custody, for demos and integration tests.

THIS IS THE PIECE THE CLIENT REPLACES. In production the tally sheets live in
the entity's own storage — an S3 bucket, a document management system — and
the viewer reads them from there. That storage does not exist yet, so this
driver serves one fixed PDF for every identifier.

It is deliberately loud about what it is. A demo that quietly reads a local
file is a demo someone eventually mistakes for a working integration; this
one logs a warning on every read and refuses to start when APP_ENV is
production.

To replace it: write a class with `fetch` and `exists` (see the package
docstring), and set CUSTODY_DRIVER to its name. Nothing else changes.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from app.config import Settings
from app.services.custody import (
    CustodyError,
    Document,
    DocumentNotFound,
    register,
    safe_identifier,
)

logger = logging.getLogger(__name__)


@register("stub")
class StubCustody:
    """Returns the same document for any identifier."""

    def __init__(self, settings: Settings):
        if settings.is_production:
            raise CustodyError(
                "the stub custody driver must not run in production; "
                "configure CUSTODY_DRIVER for the entity's real storage"
            )
        self._path = Path(settings.custody_path)
        logger.warning(
            "custody driver 'stub' is active: every identifier resolves to %s. "
            "This stands in for the entity's storage and must be replaced.",
            self._path,
        )

    async def fetch(self, identifier: str) -> Document:
        safe_identifier(identifier)
        try:
            content = await asyncio.to_thread(self._path.read_bytes)
        except FileNotFoundError as exc:
            raise DocumentNotFound(f"stub document missing at {self._path}") from exc
        logger.warning("stub custody served the placeholder for '%s'", identifier)
        return Document(identifier=identifier, content=content)

    async def exists(self, identifier: str) -> bool:
        safe_identifier(identifier)
        return await asyncio.to_thread(self._path.is_file)
