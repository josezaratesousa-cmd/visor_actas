"""Read-only client for the Stamping.io evidence API.

The viewer looks up attestations. It never creates them. Registration lives
in tools/register_record.py, which runs from an operator's shell and is not
importable from the request path.

That separation is structural rather than a matter of discipline: this class
refuses any method other than GET, so an attacker who reaches the request
handling code still has no way to forge an attestation through it. The token
this service uses can — and should — be one that only grants reads.

The second rule is that the API token travels in a header, never in a query
string. Query strings are written to web server access logs in plain text
and kept there through every rotation and backup, so a credential sent that
way is a credential published to everyone who can read a log file. Keeping
it out of the URL is much of the point of having a backend at all.
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
        """Fetch by the entity's own identifier.

        This lookup needs authentication, and the token travels in a header.
        The query endpoint used to read parameters only from $_GET and
        $_REQUEST, which forced the token into the URL and from there into the
        access log; it accepts X-API-Token now, so that is no longer the price
        of authenticating.
        """
        return await self._get({"byExternalKey": external_key})

    async def _get(self, params: dict[str, str]) -> dict[str, Any]:
        response = await self._request("GET", "/stamp/get/", params=params)

        result = response.payload.get("result")
        if not result:
            raise RecordNotFound(f"no evidence for {params}")
        return response.payload

    # ── transport ─────────────────────────────────────────────────────────

    async def _request(self, method: str, path: str, **kwargs: Any) -> StampingResponse:
        if method != "GET":
            # Structural, not a policy check. See the module docstring.
            raise StampingError("the viewer is read-only")
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
