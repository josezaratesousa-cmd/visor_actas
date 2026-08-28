"""Custody: where the signed PDFs live.

This is the seam the client is expected to move. Everything above it — the
hashing, the Stamping lookup, the viewer — only knows that some object can
hand back the bytes of a tally sheet. Whether those bytes come from S3, a
local directory, or an internal document management system is a matter of
one setting and one class.

    Swapping the backend

    1. Write a class with `fetch` and `exists` (see CustodyStorage below).
    2. Decorate it with @register("your-name").
    3. Import it in this file so the decorator runs.
    4. Set CUSTODY_DRIVER=your-name in the .env.

    Nothing else in the project changes. Credentials live only in the .env,
    outside the repository, and are read once here.

Identifiers are treated as hostile input throughout: they arrive from a
deciphered QR code, and a driver that concatenates them into a path or a
key without checking is one crafted code away from serving an arbitrary
file. Every driver must call `safe_identifier` before touching storage.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Callable, Protocol, runtime_checkable

from app.config import Settings

__all__ = [
    "Document",
    "CustodyStorage",
    "CustodyError",
    "DocumentNotFound",
    "register",
    "build_storage",
    "safe_identifier",
]


class CustodyError(RuntimeError):
    """Storage could not be reached, or refused the request."""


class DocumentNotFound(CustodyError):
    """No document under that identifier."""


@dataclass(frozen=True)
class Document:
    """A signed tally sheet, exactly as stored.

    `content` must be the bytes that were signed and hashed. Any
    re-encoding, optimisation or metadata rewrite between storage and here
    changes the sha256 and the viewer will report the sheet as altered.
    """

    identifier: str
    content: bytes = field(repr=False)
    content_type: str = "application/pdf"

    @property
    def size(self) -> int:
        return len(self.content)

    @property
    def sha256(self) -> str:
        """The evidence hash. Recomputed from the bytes, never trusted."""
        return hashlib.sha256(self.content).hexdigest()


@runtime_checkable
class CustodyStorage(Protocol):
    """The contract a custody backend has to satisfy."""

    async def fetch(self, identifier: str) -> Document:
        """Return the document, or raise DocumentNotFound."""
        ...

    async def exists(self, identifier: str) -> bool:
        """True when the document is retrievable."""
        ...


# ── driver registry ──────────────────────────────────────────────────────

_DRIVERS: dict[str, Callable[[Settings], CustodyStorage]] = {}


def register(name: str) -> Callable[[type], type]:
    """Register a custody backend under a name usable in CUSTODY_DRIVER."""

    def decorator(cls: type) -> type:
        key = name.strip().lower()
        if key in _DRIVERS:
            raise ValueError(f"custody driver '{key}' is already registered")
        _DRIVERS[key] = cls
        return cls

    return decorator


def available_drivers() -> list[str]:
    return sorted(_DRIVERS)


def build_storage(settings: Settings) -> CustodyStorage:
    """Instantiate the backend named by CUSTODY_DRIVER."""
    name = (settings.custody_driver or "").strip().lower()
    factory = _DRIVERS.get(name)
    if factory is None:
        raise CustodyError(
            f"unknown custody driver '{name}'. "
            f"Available: {', '.join(available_drivers()) or 'none'}"
        )
    return factory(settings)


# ── identifier hygiene ───────────────────────────────────────────────────

_SAFE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$")


def safe_identifier(identifier: str) -> str:
    """Reject anything that could escape the storage root.

    Identifiers come from a deciphered QR code. Authenticated, yes — but
    authenticated by a key that also lives on this server, so it is not a
    reason to skip the check.
    """
    if not identifier or not _SAFE.match(identifier):
        raise CustodyError("identifier has an unacceptable shape")
    if ".." in identifier or identifier.startswith("/") or "//" in identifier:
        raise CustodyError("identifier attempts to traverse the storage root")
    return identifier


# Importing the built-in drivers runs their @register decorators.
from app.services.custody import local as _local  # noqa: E402,F401
from app.services.custody import s3 as _s3        # noqa: E402,F401
