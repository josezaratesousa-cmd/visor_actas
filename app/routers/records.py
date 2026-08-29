"""Everything the browser can ask for. Three endpoints, all GET."""

from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Request, Response

from app.models import RecordStatus
from app.services.custody import Document

router = APIRouter(prefix="/api/records", tags=["records"])

CODE = r"^[A-Za-z0-9_-]{6,120}$"

# A verified record does not change, and on a night when one sheet gets
# shared widely the same lookup arrives thousands of times. Serving it from
# memory is what keeps the upstream service from carrying that load; the
# rate limiter is only the backstop behind it.
_cache: dict[str, tuple[float, dict]] = {}


async def _resolve(request: Request, code: str):
    service = request.app.state.records
    record = await service.resolve(code)
    if record.status is RecordStatus.NOT_FOUND:
        # Deliberately the same answer as an unknown code: a distinct message
        # for "well-formed but unknown" would confirm which codes exist.
        raise HTTPException(status_code=404, detail="not found")
    return service, record


@router.get("/{code}")
async def get_record(request: Request, code: str):
    ttl = request.app.state.settings.record_cache_seconds
    cached = _cache.get(code)
    if cached and time.monotonic() - cached[0] < ttl:
        return cached[1]

    service, record = await _resolve(request, code)
    pages = 0
    if record.document is not None:
        pages = await request.app.state.renderer.page_count(record.document.content)
    view = service.to_view(record, pages, code)

    # Only verified records are cached. A pending one is expected to change,
    # and a citizen who comes back after the anchor lands should see it.
    if view.get("status") == "verified":
        if len(_cache) > 20000:
            _cache.clear()
        _cache[code] = (time.monotonic(), view)
    return view


@router.get("/{code}/pdf")
async def get_pdf(request: Request, code: str, download: bool = False):
    """The signed PDF.

    `download=1` asks for it as a file to keep rather than something to look
    at, and that changes both headers.

    iOS Safari previews anything served as application/pdf, and it does so
    even when Content-Disposition says attachment: the citizen sees the
    document, closes it, and has no file. Announcing the download variant as
    an opaque binary is what actually makes Safari save it. The bytes are
    identical and the name still ends in .pdf, so Files opens it correctly.
    """
    service, record = await _resolve(request, code)
    document = _require_document(record.document)
    station = record.identifier.split("/")[-1]
    disposition = "attachment" if download else "inline"
    return Response(
        content=document.content,
        media_type="application/octet-stream" if download else "application/pdf",
        headers={
            "Content-Disposition": f'{disposition}; filename="Mesa-{station}.pdf"',
            # Keyed by content: a changed file is a changed URL.
            "ETag": f'"{document.sha256}"',
            "Cache-Control": "public, max-age=3600",
        },
    )


@router.get("/{code}/pages/{number}")
async def get_page(request: Request, code: str, number: int, density: str = ""):
    _, record = await _resolve(request, code)
    document = _require_document(record.document)
    if density not in {"", "@2x"}:
        raise HTTPException(status_code=400, detail="unknown density")
    try:
        image = await request.app.state.renderer.page(
            document.content, document.sha256, number, density)
    except IndexError:
        raise HTTPException(status_code=404, detail="no such page") from None
    return Response(
        content=image,
        media_type="image/webp",
        headers={"ETag": f'"{document.sha256}-{number}{density}"',
                 "Cache-Control": "public, max-age=86400"},
    )


def _require_document(document: Document | None) -> Document:
    if document is None:
        raise HTTPException(status_code=404, detail="document not in custody")
    return document
