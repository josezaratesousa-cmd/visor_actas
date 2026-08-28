"""Custody: the seam the client replaces, and the checks that keep it safe."""

import pytest

from app.config import Settings
from app.services.custody import (
    CustodyError,
    CustodyStorage,
    Document,
    DocumentNotFound,
    available_drivers,
    build_storage,
    register,
    safe_identifier,
)

PDF = b"%PDF-1.7\nsynthetic tally sheet\n%%EOF\n"


def settings_for(tmp_path) -> Settings:
    return Settings(
        custody_driver="local",
        custody_path=tmp_path,
        stamping_token="test",
        code_cipher_key="ab" * 32,
        _env_file=None,
    )


# ── the contract ─────────────────────────────────────────────────────────


def test_both_builtin_drivers_are_registered():
    assert {"local", "s3"} <= set(available_drivers())


def test_local_driver_satisfies_the_protocol(tmp_path):
    storage = build_storage(settings_for(tmp_path))
    assert isinstance(storage, CustodyStorage)


def test_unknown_driver_names_the_alternatives(tmp_path):
    settings = settings_for(tmp_path)
    settings.custody_driver = "wishful"
    with pytest.raises(CustodyError, match="local"):
        build_storage(settings)


# ── reading ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_returns_the_exact_bytes(tmp_path):
    (tmp_path / "EMC-2026").mkdir()
    (tmp_path / "EMC-2026" / "035253.pdf").write_bytes(PDF)

    storage = build_storage(settings_for(tmp_path))
    document = await storage.fetch("EMC-2026/035253")

    assert document.content == PDF
    assert document.size == len(PDF)
    # The hash is recomputed from the bytes, never taken on trust.
    assert document.sha256 == Document("x", PDF).sha256


@pytest.mark.asyncio
async def test_missing_document_is_distinguishable_from_a_broken_store(tmp_path):
    storage = build_storage(settings_for(tmp_path))
    with pytest.raises(DocumentNotFound):
        await storage.fetch("EMC-2026/999999")
    assert await storage.exists("EMC-2026/999999") is False


# ── hostile identifiers ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "identifier",
    [
        "../../../../etc/passwd",
        "/etc/passwd",
        "EMC-2026/../../../etc/visor-actas/.env",
        "a//b",
        "",
        " ",
        "EMC-2026/035253\x00.pdf",
        "x" * 300,
    ],
)
def test_traversal_and_junk_are_rejected(identifier):
    with pytest.raises(CustodyError):
        safe_identifier(identifier)


@pytest.mark.asyncio
async def test_traversal_never_reaches_the_filesystem(tmp_path):
    secret = tmp_path.parent / "secret.pdf"
    secret.write_bytes(b"credentials")

    storage = build_storage(settings_for(tmp_path))
    with pytest.raises(CustodyError):
        await storage.fetch("../secret")
    assert await storage.exists("../secret") is False


@pytest.mark.asyncio
async def test_symlink_out_of_the_root_is_refused(tmp_path):
    """A validated identifier is not enough: resolve() follows symlinks."""
    outside = tmp_path.parent / "outside.pdf"
    outside.write_bytes(b"outside the root")
    (tmp_path / "escape.pdf").symlink_to(outside)

    storage = build_storage(settings_for(tmp_path))
    with pytest.raises(CustodyError, match="escapes"):
        await storage.fetch("escape")


# ── replacing the backend ────────────────────────────────────────────────


def test_a_client_can_plug_in_their_own_backend(tmp_path):
    """The whole point of the seam: one class, one setting, nothing else."""

    @register("client-dms")
    class ClientDocumentSystem:
        def __init__(self, settings: Settings):
            self.settings = settings

        async def fetch(self, identifier: str) -> Document:
            return Document(identifier=identifier, content=PDF)

        async def exists(self, identifier: str) -> bool:
            return True

    settings = settings_for(tmp_path)
    settings.custody_driver = "client-dms"
    storage = build_storage(settings)

    assert isinstance(storage, ClientDocumentSystem)
    assert isinstance(storage, CustodyStorage)


def test_a_driver_name_cannot_be_registered_twice():
    with pytest.raises(ValueError, match="already registered"):

        @register("local")
        class Duplicate:
            pass
