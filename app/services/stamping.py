"""Client for the Stamping.io evidence API.

One rule drives the whole module: the API token travels in a header, never
in a query string. Stamping's own public viewer passes it as `?token=`, and
that token now sits in plain text in the web server access logs, hundreds of
times over. Not repeating that here is the entire point of having a backend.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)


class StampingError(RuntimeError):
    """The API could not be reached or answered with an error."""


class RecordNotFound(StampingError):
    """No evidence registered under that identifier (yet)."""


@dataclass(frozen=True)
class StampingResponse:
    status_code: int
    payload: dict[str, Any]


class StampingClient:
    """Thin async wrapper over the two endpoints the viewer needs."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self._settings = settings
        self._client = client
        self._owns_client = client is None

    async def __aenter__(self) -> "StampingClient":
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._settings.stamping_base_url.rstrip("/"),
                timeout=self._settings.stamping_timeout,
                headers={
                    # Header, not query string. See module docstring.
                    "X-API-Token": self._settings.stamping_token,
                    "Accept": "application/json",
                    "User-Agent": "visor-actas/1.0",
                },
            )
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    # ── lookup ────────────────────────────────────────────────────────────

    async def get_by_trx_id(self, trx_id: str) -> dict[str, Any]:
        """Fetch the attestation for a transaction id (sha1 of the evidence)."""
        return await self._get({"byTrxid": trx_id})

    async def get_by_evidence(self, evidence: str) -> dict[str, Any]:
        """Fetch by the sha256 of the signed PDF."""
        return await self._get({"byHash": evidence})

    async def get_by_external_key(self, external_key: str) -> dict[str, Any]:
        """Fetch by ONPE's own identifier. Requires a valid token."""
        return await self._get({"byExternalKey": external_key})

    async def _get(self, params: dict[str, str]) -> dict[str, Any]:
        response = await self._request("GET", "/stamp/get/", params=params)

        result = response.payload.get("result")
        if not result:
            raise RecordNotFound(f"no evidence for {params}")
        return response.payload

    # ── registration ──────────────────────────────────────────────────────

    async def register(self, body: dict[str, Any]) -> dict[str, Any]:
        """Register a new piece of evidence.

        `info` is only accepted on a POST body with async=true, so the
        caller cannot opt out of it.
        """
        body = {**body, "async": "true"}
        response = await self._request("POST", "/stamp/", json=body)
        return response.payload

    # ── transport ─────────────────────────────────────────────────────────

    async def _request(self, method: str, path: str, **kwargs: Any) -> StampingResponse:
        if self._client is None:
            raise StampingError("client used outside its context manager")
        if not self._settings.stamping_token:
            raise StampingError("STAMPING_TOKEN is empty; check the .env file")

        try:
            response = await self._client.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            raise StampingError(f"Stamping timed out after "
                                f"{self._settings.stamping_timeout}s") from exc
        except httpx.HTTPError as exc:
            raise StampingError(f"Stamping unreachable: {exc}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            # A non-JSON body from an API that only speaks JSON usually means
            # an HTML error page from the web server in front of it.
            raise StampingError(
                f"Stamping returned non-JSON (HTTP {response.status_code})"
            ) from exc

        code = int(payload.get("code", response.status_code))
        if code >= 400:
            # Never log the token, and never surface the raw message to the
            # citizen: it can name tables, columns and internal paths.
            logger.warning(
                "Stamping error: http=%s code=%s message=%s",
                response.status_code, code, payload.get("message"),
            )
            raise StampingError(f"Stamping returned code {code}")

        return StampingResponse(status_code=response.status_code, payload=payload)
