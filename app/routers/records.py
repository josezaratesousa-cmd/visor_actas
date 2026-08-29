"""Everything the browser can ask for. Three endpoints, all GET."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response

from app.models import RecordStatus
from app.services.custody import Document

router = APIRouter(prefix="/api/records", tags=["records"])

CODE = r"^[A-Za-z0-9_-]{6,120}$"


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
    service, record = await _resolve(request, code)
    pages = 0
    if record.document is not None:
        pages = await request.app.state.renderer.page_count(record.document.content)
    return service.to_view(record, pages)


@router.get("/{code}/pdf")
async def get_pdf(request: Request, code: str):
    _, record = await _resolve(request, code)
    document = _require_document(record.document)
    return Response(
        content=document.content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="acta-{record.identifier.split("/")[-1]}.pdf"',
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
