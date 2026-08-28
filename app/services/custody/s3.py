"""S3 custody.

Works against AWS S3 and any S3-compatible service (MinIO, Wasabi, Backblaze,
a private gateway) through CUSTODY_ENDPOINT. Credentials come from the .env
and are never logged, never echoed in an error, and never leave this module.

boto3 is imported lazily so that a deployment using a different backend does
not need it installed at all.
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.config import Settings
from app.services.custody import (
    CustodyError,
    Document,
    DocumentNotFound,
    register,
    safe_identifier,
)


@register("s3")
class S3Custody:
    """Reads PDFs from an S3 bucket."""

    def __init__(self, settings: Settings):
        if not settings.custody_bucket:
            raise CustodyError("CUSTODY_BUCKET is empty; check the .env file")
        self._bucket = settings.custody_bucket
        self._prefix = str(settings.custody_path).strip("/")
        self._settings = settings
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import boto3  # noqa: PLC0415
            from botocore.config import Config  # noqa: PLC0415
        except ImportError as exc:
            raise CustodyError(
                "the s3 custody driver needs boto3: pip install boto3"
            ) from exc

        options: dict[str, Any] = {
            "config": Config(
                retries={"max_attempts": 3, "mode": "standard"},
                connect_timeout=5,
                read_timeout=15,
            )
        }
        if self._settings.custody_region:
            options["region_name"] = self._settings.custody_region
        if self._settings.custody_endpoint:
            options["endpoint_url"] = self._settings.custody_endpoint

        # When the keys are absent, boto3 falls back to the instance role or
        # the shared credentials file, which is the preferred setup in AWS.
        if self._settings.custody_access_key and self._settings.custody_secret_key:
            options["aws_access_key_id"] = self._settings.custody_access_key
            options["aws_secret_access_key"] = self._settings.custody_secret_key

        self._client = boto3.client("s3", **options)
        return self._client

    def _key(self, identifier: str) -> str:
        safe_identifier(identifier)
        return f"{self._prefix}/{identifier}.pdf" if self._prefix else f"{identifier}.pdf"

    async def fetch(self, identifier: str) -> Document:
        key = self._key(identifier)

        def _download() -> bytes:
            client = self._get_client()
            response = client.get_object(Bucket=self._bucket, Key=key)
            return response["Body"].read()

        try:
            content = await asyncio.to_thread(_download)
        except Exception as exc:  # noqa: BLE001 - normalised just below
            if _is_missing(exc):
                raise DocumentNotFound(f"no document for '{identifier}'") from exc
            # Deliberately terse: a botocore error can carry the bucket name,
            # the endpoint and parts of the request signature.
            raise CustodyError("custody storage is unavailable") from exc

        return Document(identifier=identifier, content=content)

    async def exists(self, identifier: str) -> bool:
        try:
            key = self._key(identifier)
        except CustodyError:
            return False

        def _head() -> bool:
            client = self._get_client()
            client.head_object(Bucket=self._bucket, Key=key)
            return True

        try:
            return await asyncio.to_thread(_head)
        except Exception as exc:  # noqa: BLE001
            if _is_missing(exc):
                return False
            raise CustodyError("custody storage is unavailable") from exc


def _is_missing(exc: Exception) -> bool:
    """True when the error means 'no such object', not 'storage is broken'."""
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return False
    code = str(response.get("Error", {}).get("Code", ""))
    status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
    return code in {"NoSuchKey", "404", "NotFound"} or status == 404
