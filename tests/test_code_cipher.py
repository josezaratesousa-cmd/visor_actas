"""The QR code must be opaque, authenticated, and fail closed."""

import pytest

from app.services.code_cipher import CodeCipher, InvalidCode

KEY = CodeCipher.generate_key()


def test_round_trip():
    cipher = CodeCipher(KEY)
    code = cipher.encode("EMC-2026/035253")
    assert cipher.decode(code) == "EMC-2026/035253"


def test_code_does_not_leak_the_polling_station():
    """Editing the URL must not walk to a neighbouring sheet."""
    cipher = CodeCipher(KEY)
    code = cipher.encode("EMC-2026/035253")
    assert "035253" not in code
    assert "EMC" not in code


def test_same_identifier_yields_different_codes():
    """A fresh nonce each time: codes are not comparable to each other."""
    cipher = CodeCipher(KEY)
    assert cipher.encode("EMC-2026/035253") != cipher.encode("EMC-2026/035253")


def test_tampered_code_is_rejected():
    """Flip a character in the middle: the ciphertext really changes."""
    cipher = CodeCipher(KEY)
    code = cipher.encode("EMC-2026/035253")
    middle = len(code) // 2
    flipped = code[:middle] + ("A" if code[middle] != "A" else "B") + code[middle + 1:]
    with pytest.raises(InvalidCode):
        cipher.decode(flipped)


def test_non_canonical_encoding_is_rejected():
    """Unpadded base64 admits several spellings of the same bytes.

    Without this check one tally sheet is reachable through many distinct
    URLs, which defeats per-code rate limiting and inflates metrics.
    """
    cipher = CodeCipher(KEY)
    code = cipher.encode("EMC-2026/035253")
    last = code[-1]
    alternatives = [c for c in "ABCDEFGH" if c != last]
    rejected = 0
    for candidate in alternatives:
        variant = code[:-1] + candidate
        try:
            cipher.decode(variant)
        except InvalidCode:
            rejected += 1
    assert rejected == len(alternatives)


def test_another_key_cannot_read_the_code():
    code = CodeCipher(KEY).encode("EMC-2026/035253")
    with pytest.raises(InvalidCode):
        CodeCipher(CodeCipher.generate_key()).decode(code)


def test_garbage_is_rejected_without_leaking_why():
    cipher = CodeCipher(KEY)
    for bad in ["", "!!!!", "AAAA", "x" * 3]:
        with pytest.raises((InvalidCode, ValueError)):
            cipher.decode(bad)


def test_key_must_be_32_bytes_of_hex():
    with pytest.raises(ValueError, match="empty"):
        CodeCipher("")
    with pytest.raises(ValueError, match="hexadecimal"):
        CodeCipher("zz" * 32)
    with pytest.raises(ValueError, match="32 bytes"):
        CodeCipher("ab" * 16)


# ── the seam ─────────────────────────────────────────────────────────────


def test_a_deployment_can_plug_in_another_resolver(tmp_path):
    """One class and one setting, same shape as the custody seam."""
    from app.config import Settings
    from app.services.code_cipher import (
        CodeResolver, available_resolvers, build_resolver, register)

    assert "aes-gcm" in available_resolvers()

    @register("lookup-table")
    class TableResolver:
        """Short opaque codes resolved against a table, not deciphered."""

        TABLE = {"a1b2c3d4e5": "EMC-2026/035253"}

        def __init__(self, settings):
            self.settings = settings

        def decode(self, code: str) -> str:
            try:
                return self.TABLE[code]
            except KeyError:
                raise InvalidCode("unknown code") from None

    settings = Settings(code_resolver="lookup-table", code_cipher_key=KEY,
                        stamping_token="", _env_file=None)
    resolver = build_resolver(settings)

    assert isinstance(resolver, CodeResolver)
    assert resolver.decode("a1b2c3d4e5") == "EMC-2026/035253"
    with pytest.raises(InvalidCode):
        resolver.decode("nope")


def test_unknown_resolver_names_the_alternatives():
    from app.config import Settings
    from app.services.code_cipher import build_resolver

    settings = Settings(code_resolver="wishful", code_cipher_key=KEY,
                        stamping_token="", _env_file=None)
    with pytest.raises(ValueError, match="aes-gcm"):
        build_resolver(settings)
