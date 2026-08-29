"""Application entry point.

Serves the API, the static frontend, and an index page carrying the Open
Graph tags. Those tags have to be rendered server-side: the crawlers behind
WhatsApp, Facebook and X do not execute JavaScript, so a link preview built
in the browser would never be seen.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.routers import records
from app.services.custody import build_storage
from app.services.record_service import RecordService
from app.services.rendering import PageRenderer

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

WEB = Path(__file__).resolve().parent.parent / "web"
CODE_PATTERN = r"^[A-Za-z0-9_-]{6,120}$"


@asynccontextmanager
async def lifespan(application: FastAPI):
    settings = get_settings()
    # STAMPING_TOKEN is optional: the viewer only uses public lookups.
    if not settings.code_cipher_key:
        raise RuntimeError("CODE_CIPHER_KEY is empty; check the .env file")

    storage = build_storage(settings)
    application.state.settings = settings
    application.state.records = RecordService(settings, storage)
    application.state.renderer = PageRenderer(settings)
    logger.info("custody driver: %s", settings.custody_driver)
    yield


settings = get_settings()
app = FastAPI(title="Visor de actas electorales", version="1.0",
              root_path=settings.app_root_path, lifespan=lifespan,
              docs_url=None, redoc_url=None, openapi_url=None)

app.include_router(records.router)


@app.exception_handler(500)
async def on_error(request: Request, exc: Exception):
    # Never surface an internal message: it can name tables, paths and hosts.
    logger.exception("unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "internal error"})


for folder in ("css", "js", "i18n", "assets"):
    app.mount(f"/{folder}", StaticFiles(directory=WEB / folder), name=folder)


@app.get("/health", include_in_schema=False)
async def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
@app.get("/{code}", response_class=HTMLResponse, include_in_schema=False)
async def index(request: Request, code: str = ""):
    """The single page. Open Graph tags are filled in per record."""
    html = (WEB / "index.html").read_text(encoding="utf-8")

    if not code:
        return HTMLResponse(html)

    import re
    if not re.match(CODE_PATTERN, code):
        return HTMLResponse(html, status_code=404)

    record = await request.app.state.records.resolve(code)
    view = request.app.state.records.to_view(record, 0)
    station = view.get("station") or ""
    process = (view.get("process") or {}).get("name") or ""

    title = f"Acta de la Mesa {station}" if station else "Verificador de actas"
    description = (f"{process}. Acta verificada en blockchain."
                   if view["status"] == "verified"
                   else "Consulte la autenticidad de un acta electoral.")
    base = request.app.state.settings.app_base_url.rstrip("/")

    tags = (
        f'<meta property="og:title" content="{_esc(title)}">\n'
        f'<meta property="og:description" content="{_esc(description)}">\n'
        f'<meta property="og:url" content="{_esc(base)}/{_esc(code)}">\n'
        f'<meta property="og:type" content="website">\n'
        f'<meta name="twitter:card" content="summary_large_image">\n'
    )
    html = html.replace("</head>", tags + "</head>")
    status = 200 if view["status"] != "not_found" else 404
    return HTMLResponse(html, status_code=status)


def _esc(value: str) -> str:
    return (value.replace("&", "&amp;").replace("<", "&lt;")
                 .replace(">", "&gt;").replace('"', "&quot;"))
