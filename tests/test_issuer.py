"""The attestation must belong to the electoral body, not merely exist.

The transaction id is derived from the file hash, so anyone who seals the
same PDF under their own account produces a record that matches. Without
this check the viewer would confirm that somebody sealed the document -
not that the entity did, which is the only claim worth making on a page
carrying a state emblem.
"""

import pytest

from app.config import Settings
from app.services.record_service import RecordService

ENTITY = "ef60e6d0b2603e41328af4aa4c00a5ee3df7c47d"
KEY = "ab" * 32


def service(issuer: str) -> RecordService:
    settings = Settings(expected_issuer_id=issuer, code_cipher_key=KEY,
                        stamping_token="", custody_driver="local",
                        _env_file=None)
    return RecordService(settings, storage=None)


def payload(user_id: str, name: str = "ONPE") -> dict:
    return {"result": {"ownership": {"userId": user_id, "name": name}}}


def test_the_entity_own_record_is_accepted():
    assert service(ENTITY)._issued_by_the_entity(payload(ENTITY), "EMC/1")


def test_a_record_from_another_account_is_refused():
    """The forgery this exists to stop: same file, someone else's seal."""
    assert not service(ENTITY)._issued_by_the_entity(
        payload("dead" * 10, "Otro Tenant"), "EMC/1")


def test_a_record_without_ownership_is_refused():
    assert not service(ENTITY)._issued_by_the_entity({"result": {}}, "EMC/1")
    assert not service(ENTITY)._issued_by_the_entity({}, "EMC/1")


def test_comparison_ignores_case_and_padding():
    assert service(ENTITY)._issued_by_the_entity(
        payload(f"  {ENTITY.upper()}  "), "EMC/1")


def test_an_empty_setting_disables_the_check():
    """A weaker posture, allowed on purpose and warned about in the .env."""
    assert service("")._issued_by_the_entity(payload("anyone at all"), "EMC/1")


def test_the_mismatch_is_logged_loudly(caplog):
    """An operator has to see this the same day, not in a weekly review."""
    with caplog.at_level("ERROR"):
        service(ENTITY)._issued_by_the_entity(payload("dead" * 10), "EMC/1")
    assert any(r.levelname == "ERROR" for r in caplog.records)
    assert "issued by" in caplog.text
