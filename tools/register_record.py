#!/usr/bin/env python3
"""Register a tally sheet with Stamping. Operator tool, not part of the viewer.

This is the only place in the repository that writes to Stamping. It runs
from a shell, never from the request path, so the running web service has no
code path that can forge an attestation.

In production ONPE registers its own sheets; this exists to seed test data
and to diagnose the integration.

    THE ORDER MATTERS. The hash must be taken over the final, already
    signed PDF, byte for byte, exactly as it will be stored and served.
    Hash first and sign afterwards and every sheet in the country reports
    as altered. See docs/INTEGRATION-SPEC.md section 3.

Usage:
    python -m tools.register_record sheet.pdf \\
        --results tests/fixtures/results.json \\
        --data    tests/fixtures/data.json \\
        [--lat -12.0768 --long -77.0916] [--dry-run]
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.models import RecordData, Results  # noqa: E402


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def b64_json(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return base64.b64encode(raw.encode("utf-8")).decode("ascii")


def build_body(pdf: Path, results: dict, data: dict,
               lat: float | None, lng: float | None) -> dict[str, Any]:
    # Validate before sending. A sheet whose numbers do not add up is a
    # problem to fix here, not one to discover on a citizen's screen.
    checked_results = Results.model_validate(results)
    checked_data = RecordData.model_validate(data)

    if checked_results.polling_station != checked_data.polling_station:
        raise SystemExit(
            f"polling station mismatch: results says "
            f"{checked_results.polling_station}, data says "
            f"{checked_data.polling_station}"
        )

    station = checked_data.polling_station
    process = checked_data.process.code

    body: dict[str, Any] = {
        "async": "true",
        "evidence": sha256_of(pdf),
        "transactionType": process,
        "subject": f"Mesa {station}",
        "external_key": f"ONPE-{process}-{station}",
        "info": b64_json(results),
        "data": b64_json(data),
    }
    if lat is not None and lng is not None:
        body["lat"], body["long"] = lat, lng
    return body


def register(body: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    if not settings.stamping_token:
        raise SystemExit("STAMPING_TOKEN is empty; check the .env file")

    response = httpx.post(
        f"{settings.stamping_base_url.rstrip('/')}/stamp/",
        json=body,
        headers={
            "X-API-Token": settings.stamping_token,   # header, never a query string
            "Accept": "application/json",
            "User-Agent": "visor-actas-tools/1.0",
        },
        timeout=settings.stamping_timeout,
    )
    response.raise_for_status()
    return response.json()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("pdf", type=Path, help="the SIGNED PDF, already final")
    parser.add_argument("--results", type=Path, required=True, help="info JSON")
    parser.add_argument("--data", type=Path, required=True, help="data JSON")
    parser.add_argument("--lat", type=float, default=None)
    parser.add_argument("--long", dest="lng", type=float, default=None)
    parser.add_argument("--dry-run", action="store_true",
                        help="build and validate the body, send nothing")
    args = parser.parse_args()

    if not args.pdf.is_file():
        raise SystemExit(f"no such file: {args.pdf}")

    body = build_body(
        args.pdf,
        json.loads(args.results.read_text(encoding="utf-8")),
        json.loads(args.data.read_text(encoding="utf-8")),
        args.lat, args.lng,
    )

    trx_id = hashlib.sha1(body["evidence"].encode()).hexdigest()  # noqa: S324
    print(f"file      {args.pdf}  ({args.pdf.stat().st_size} bytes)")
    print(f"evidence  {body['evidence']}")
    print(f"trxid     {trx_id}")
    print(f"subject   {body['subject']}")
    print(f"key       {body['external_key']}")

    if args.dry_run:
        print("\ndry run: nothing sent")
        return 0

    payload = register(body)
    print(f"\nresponse  code={payload.get('code')} {payload.get('message', '')}")

    result = payload.get("result") or {}
    if result.get("proof"):
        # Stamping does not keep this. Whoever registers has to.
        proof_path = args.pdf.with_suffix(".proof.json")
        proof_path.write_text(json.dumps(result["proof"], indent=2), encoding="utf-8")
        print(f"proof     saved to {proof_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
