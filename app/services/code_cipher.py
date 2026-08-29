"""QR code parameter: cipher and decipher.

The printed QR points at /<code>. That code must not be the polling station
number, nor derivable from it: otherwise anyone enumerates every tally sheet
in the country by editing the URL.

AES-256-GCM, authenticated, with the nonce carried alongside the ciphertext.
Deciphering fails closed: a tampered code raises rather than returning a
plausible-looking identifier.

    THE LENGTH TRADE-OFF, stated plainly

    A self-contained encrypted code cannot be short. The envelope alone is
    12 bytes of nonce plus 16 bytes of authentication tag, so a 15-character
    payload lands around 58 base64url characters. That is a denser QR than
    the 8-12 characters the specification suggests, which matters when the
    code is printed in the field on ordinary paper.

    The alternative is an opaque random identifier plus a server-side lookup
    table: 10 characters, revocable per sheet, no cryptography to break, at
    the cost of a table that must be generated with the ballot material and
    kept available. That is a decision for ONPE, not a technical detail.
"""

from __future__ import annotations

import base64
import os
from typing import Callable, Protocol, runtime_checkable

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

NONCE_BYTES = 12
KEY_BYTES = 32


class InvalidCode(ValueError):
    """The code is malformed, truncated, or was not produced by this key."""


@runtime_checkable
class CodeResolver(Protocol):
    """Turns the code printed in the QR into an internal identifier.

    The second seam a deployment is expected to move, after custody. An
    entity that prefers short opaque codes backed by a lookup table, or a
    different cipher, writes one class and changes one setting.
    """

    def decode(self, code: str) -> str:
        """Recover the identifier, or raise InvalidCode."""
        ...


_RESOLVERS: dict[str, Callable[[object], CodeResolver]] = {}


def register(name: str) -> Callable[[type], type]:
    """Register a resolver under a name usable in CODE_RESOLVER."""

    def decorator(cls: type) -> type:
        key = name.strip().lower()
        if key in _RESOLVERS:
            raise ValueError(f"code resolver '{key}' is already registered")
        _RESOLVERS[key] = cls
        return cls

    return decorator


def available_resolvers() -> list[str]:
    return sorted(_RESOLVERS)


def build_resolver(settings) -> CodeResolver:
    """Instantiate the resolver named by CODE_RESOLVER."""
    name = (getattr(settings, "code_resolver", "") or "aes-gcm").strip().lower()
    factory = _RESOLVERS.get(name)
    if factory is None:
        raise ValueError(
            f"unknown code resolver '{name}'. "
            f"Available: {', '.join(available_resolvers()) or 'none'}"
        )
    return factory(settings)


@register("aes-gcm")
class CodeCipher:
    """Ciphers and deciphers the identifier carried by the QR code.

    Accepts either the settings object -how the registry builds it- or a bare
    hex key, which keeps it usable from a shell and from tests.
    """

    def __init__(self, key_hex):
        if not isinstance(key_hex, str):
            key_hex = getattr(key_hex, "code_cipher_key", "")
        if not key_hex:
            raise ValueError("CODE_CIPHER_KEY is empty; check the .env file")
        try:
            key = bytes.fromhex(key_hex)
        except ValueError as exc:
            raise ValueError("CODE_CIPHER_KEY must be hexadecimal") from exc
        if len(key) != KEY_BYTES:
            raise ValueError(
                f"CODE_CIPHER_KEY must be {KEY_BYTES} bytes "
                f"({KEY_BYTES * 2} hex characters), got {len(key)}"
            )
        self._aead = AESGCM(key)

    def encode(self, identifier: str) -> str:
        """Turn an internal identifier into the code printed on the sheet."""
        if not identifier:
            raise ValueError("identifier is empty")
        nonce = os.urandom(NONCE_BYTES)
        sealed = self._aead.encrypt(nonce, identifier.encode("utf-8"), None)
        return _b64url_encode(nonce + sealed)

    def decode(self, code: str) -> str:
        """Recover the identifier. Fails closed on any tampering."""
        try:
            blob = _b64url_decode(code)
        except (ValueError, TypeError) as exc:
            raise InvalidCode("code is not valid base64url") from exc

        # Unpadded base64 is not canonical: the trailing character carries
        # bits that decoding discards, so several distinct strings map to the
        # same bytes. Left alone, one tally sheet would be reachable through
        # many different-looking URLs, which quietly defeats per-code rate
        # limiting and inflates access metrics. Require the canonical form.
        if _b64url_encode(blob) != code:
            raise InvalidCode("code is not in canonical form")

        if len(blob) <= NONCE_BYTES:
            raise InvalidCode("code is too short to contain a nonce")

        nonce, sealed = blob[:NONCE_BYTES], blob[NONCE_BYTES:]
        try:
            plain = self._aead.decrypt(nonce, sealed, None)
        except InvalidTag as exc:
            raise InvalidCode("code failed authentication") from exc

        try:
            return plain.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise InvalidCode("deciphered identifier is not valid UTF-8") from exc

    @staticmethod
    def generate_key() -> str:
        """A fresh key, for `python -m app.services.code_cipher`."""
        return os.urandom(KEY_BYTES).hex()


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


if __name__ == "__main__":
    print(CodeCipher.generate_key())
