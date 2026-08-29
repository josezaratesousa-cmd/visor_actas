"""Chains a QR code into everything the viewer needs.

    code → identifier → PDF in custody → SHA-256 → attestation → view

The lookup is by transaction id, which is sha1 of the sha256 of the PDF held
in custody. That makes the question "was this exact file registered?", and a
miss means the sheet is still on its way.

It cannot mean tampering, and the viewer must not read it that way. An
altered file has a different hash and therefore a different transaction id,
so it misses in exactly the way an unregistered sheet does. Detecting a
substituted document happens upstream, before this service is called; here a
miss is reported as PENDING and nothing more. Accusing a document on
evidence this thin would be worse than saying too little.

Because the question carries no identity of its own - only a file hash - the
public route answers it. The viewer therefore holds no credential at all: an
attacker who reaches this code finds no token to steal.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import Any

from app.config import Settings
from app.models import RecordData, RecordStatus, Results, decode_payload
from app.services.code_cipher import InvalidCode, build_resolver
from app.services.custody import CustodyError, CustodyStorage, Document, DocumentNotFound
from app.services.stamping import RecordNotFound, StampingClient, StampingError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResolvedRecord:
    status: RecordStatus
    identifier: str
    document: Document | None = None
    payload: dict[str, Any] | None = None


class RecordService:
    def __init__(self, settings: Settings, storage: CustodyStorage):
        self._settings = settings
        self._storage = storage
        self._cipher = build_resolver(settings)

    # ── identifiers ───────────────────────────────────────────────────────

    def decipher(self, code: str) -> str:
        """QR code → internal identifier, e.g. 'EMC-2026/035253'."""
        return self._cipher.decode(code)

    async def resolve_document(self, code: str) -> Document | None:
        """Solo el PDF: descifra el codigo y lo lee de custodia.

        Servir bytes no necesita la atestacion. Cuando el endpoint del PDF y
        el de las imagenes usaban la cadena completa, cada descarga provocaba
        una consulta al servicio de atestacion: una peticion barata contra
        nosotros generaba una cara contra un tercero, que es amplificacion y
        no solo gasto propio.
        """
        try:
            identifier = self.decipher(code)
        except InvalidCode:
            return None
        try:
            return await self._storage.fetch(identifier)
        except (DocumentNotFound, CustodyError):
            return None

    # ── the chain ─────────────────────────────────────────────────────────

    async def resolve(self, code: str) -> ResolvedRecord:
        try:
            identifier = self.decipher(code)
        except InvalidCode:
            return ResolvedRecord(RecordStatus.NOT_FOUND, identifier="")

        try:
            document = await self._storage.fetch(identifier)
        except DocumentNotFound:
            # In custody nothing, so nothing to show and nothing to compare.
            return ResolvedRecord(RecordStatus.PENDING, identifier)
        except CustodyError:
            logger.exception("custody failure for %s", identifier)
            return ResolvedRecord(RecordStatus.PENDING, identifier)

        trx_id = hashlib.sha1(document.sha256.encode()).hexdigest()  # noqa: S324
        try:
            async with StampingClient(self._settings) as api:
                payload = await api.get_by_trx_id(trx_id)
        except RecordNotFound:
            # Not registered: the sheet is still on its way. See the module
            # docstring for why this is never read as tampering.
            return ResolvedRecord(RecordStatus.PENDING, identifier, document)
        except StampingError:
            logger.exception("attestation lookup failed for %s", identifier)
            return ResolvedRecord(RecordStatus.PENDING, identifier, document)

        # The transaction id derives from the hash, so a hit already implies
        # the file matches. Compared again anyway: it costs nothing, and the
        # one thing this service must never do is report a match it did not
        # actually check.
        registered = (payload.get("result", {})
                             .get("integrity", {})
                             .get("evidence", ""))
        if registered != document.sha256:
            return ResolvedRecord(RecordStatus.PENDING, identifier, document)
        return ResolvedRecord(RecordStatus.VERIFIED, identifier, document, payload)

# ── shaping ───────────────────────────────────────────────────────────

    def to_view(self, record: ResolvedRecord, page_count: int,
                code: str = "") -> dict[str, Any]:
        """Everything the frontend needs, and nothing it does not.

        Fields the browser has no business seeing are dropped here rather
        than filtered later: the tenant token the API echoes back, the
        owner address, the registering IP.
        """
        base = {
            "status": record.status.value,
            "station": None,
            "process": None,
            "document": None,
            "attestation": None,
            "signature": None,
            "location": None,
            "results": None,
        }
        if record.document is None or record.payload is None:
            return base

        result = record.payload.get("result", {})
        integrity = result.get("integrity", {})
        ownership = result.get("ownership", {})
        existence = result.get("existence", {})
        block = result.get("block", {})
        mainnet = result.get("networks", {}).get("mainnet", {})

        data = _decode(integrity.get("data"), RecordData)
        results = _decode(integrity.get("info"), Results)

        station = (data.polling_station if data
                   else _station_from_subject(integrity.get("subject", "")))

        base["station"] = station
        base["process"] = ({"code": data.process.code, "name": data.process.name}
                           if data else
                           {"code": integrity.get("transactionType", ""), "name": ""})
        # Absolute paths, deliberately. The page lives at /<code>, so a
        # relative "pages/1" resolves against the parent directory and misses
        # by exactly one segment - a 404 that leaves the viewer blank with
        # nothing in the console to explain it.
        root = self._settings.app_root_path.rstrip("/")
        api = f"{root}/api/records/{code}"
        base["document"] = {
            "pages": [f"{api}/pages/{n}" for n in range(1, page_count + 1)],
            "pdf_url": f"{api}/pdf",
            "download_url": f"{api}/pdf?download=1",
            "filename": f"Mesa-{station}.pdf",
            "page_count": page_count,
            "size": _human_size(record.document.size),
        }
        base["attestation"] = {
            "evidence": record.document.sha256,
            "trx_id": hashlib.sha1(record.document.sha256.encode()).hexdigest(),  # noqa: S324
            "sealed_at": _epoch_ms(existence.get("timestamp")),
            "anchored_at": _utc(existence.get("anchored")),
            "block_number": block.get("number") or None,
            "anchors": _anchors(block, mainnet, integrity, result, self._settings),
        }
        base["signature"] = _signature(record.document.content)
        base["location"] = _location(data, ownership)
        base["results"] = _results(results)
        return base


# ── helpers ───────────────────────────────────────────────────────────────


def _decode(encoded: str | None, model):
    if not encoded:
        return None
    try:
        return decode_payload(encoded, model)
    except ValueError:
        # A malformed payload is the entity's problem to fix, not a reason to
        # fail the whole page: the rest of the sheet is still verifiable.
        logger.warning("could not decode %s payload", model.__name__)
        return None


def _station_from_subject(subject: str) -> str:
    digits = "".join(ch for ch in subject if ch.isdigit())
    return digits or subject


def _human_size(size: int) -> str:
    return f"{size / 1024:.1f} KB" if size < 1024 * 1024 else f"{size / 1048576:.1f} MB"


def _epoch_ms(value: Any) -> str | None:
    try:
        from datetime import datetime, timezone
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc) \
                       .strftime("%Y-%m-%d %H:%M:%S UTC")
    except (TypeError, ValueError):
        return None


def _utc(value: Any) -> str | None:
    return f"{value} UTC" if value else None


def _anchors(block, mainnet, integrity, result,
             settings: Settings) -> list[dict[str, Any]]:
    """Only anchors that actually exist.

    Four of them: IPFS, LACChain, Rollux and the Merkle root. That set is
    what the platform writes, so it is a list rather than a lookup - the
    response also carries polygon, celo, bsc and others, which stay empty
    and are deliberately ignored.

    Chain ids and explorer addresses come from settings. They change rarely,
    but when an explorer moves it should cost a line in the .env, not a
    release.

    The obvious fields are the wrong ones: integrity.tx_lacchain holds "0x"
    and integrity.infocid is empty even on a fully anchored record. An anchor
    whose value is absent is omitted rather than shown with a placeholder —
    a hash that leads nowhere in a block explorer is worse than no hash.
    """
    trx_id = hashlib.sha1(  # noqa: S324
        integrity.get("evidence", "").encode()).hexdigest()

    candidates = [
        ("IPFS", "anchors.ipfs", "InterPlanetary File System",
         block.get("ipfs"), settings.ipfs_gateway,
         "assets/networks/ipfs.svg", None, False),
        ("LNET", "anchors.lnet",
         f"LACChain \u00b7 chainId {settings.lacchain_chain_id}",
         mainnet.get("lacchain"), settings.lacchain_explorer,
         "assets/networks/lacchain.png", None, False),
        ("RLX", "anchors.rollux",
         f"Rollux \u00b7 chainId {settings.rollux_chain_id}",
         mainnet.get("rollux"), settings.rollux_explorer,
         "assets/networks/rollux.png", None, False),
        ("STP", "anchors.stamping", "Stamping.io \u00b7 Merkle tree",
         block.get("hashblock"), settings.merkle_viewer.format(trxid=trx_id),
         "assets/networks/stamping.ico", "verify.view_merkle", True),
    ]
    anchors = []
    for key, label, network, value, url, logo, action, root in candidates:
        if not value or value in {"0x", "0", ""}:
            continue
        anchors.append({
            "key": key, "label_key": label, "network": network, "value": value,
            "url": url.format(value=value) if "{value}" in url else url,
            "logo": logo, "action_key": action, "is_root": root,
        })
    return anchors


def _signature(content: bytes) -> dict[str, Any]:
    """Signature state, without claiming more than has been checked.

    Full PAdES validation belongs in the registration pipeline, where it runs
    once per sheet instead of once per visitor. Here we only report whether a
    signature is present. "Present but not yet validated" is reported as such:
    calling it valid would invent the one thing this product exists to prove.
    """
    if b"/ByteRange" not in content:
        return {"status": "unsigned", "signers": []}
    return {"status": "unverified", "signers": []}


def _location(data, ownership) -> dict[str, Any] | None:
    place = data.location if data else None
    latitude, longitude = ownership.get("lat"), ownership.get("long")
    if latitude in (0, "0", None) and longitude in (0, "0", None):
        latitude = longitude = None

    if place is None and latitude is None:
        return None

    payload = {
        "venue": place.venue if place else None,
        "district": place.district if place else None,
        "province": place.province if place else None,
        "ubigeo": place.ubigeo if place else None,
        "latitude": float(latitude) if latitude is not None else None,
        "longitude": float(longitude) if longitude is not None else None,
    }
    return payload if any(payload.values()) else None


def _results(results) -> dict[str, Any] | None:
    if results is None:
        return None
    return {
        "eligible_voters": results.eligible_voters,
        "voters": results.voters,
        "valid_votes": results.valid_votes,
        "null_votes": results.null_votes,
        "blank_votes": results.blank_votes,
        "options": [
            {"name": o.name, "party": o.party, "votes": o.votes, "color": o.color}
            for o in results.options
        ],
    }
