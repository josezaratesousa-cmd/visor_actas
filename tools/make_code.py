#!/usr/bin/env python3
"""Produce the code printed in the QR for an internal identifier.

    python -m tools.make_code EMC-2026/035253
"""
import sys
from app.config import get_settings
from app.services.code_cipher import CodeCipher

def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    cipher = CodeCipher(get_settings().code_cipher_key)
    for identifier in sys.argv[1:]:
        print(f"{identifier:24s} {cipher.encode(identifier)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
