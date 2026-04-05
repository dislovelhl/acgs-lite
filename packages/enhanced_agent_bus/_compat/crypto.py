"""Shim for src.core.shared.crypto."""

from __future__ import annotations

from typing import Any

try:
    from src.core.shared.crypto import *  # noqa: F403
except ImportError:

    class CryptoService:
        """Stub crypto service — raises on real crypto operations."""

        def __init__(self, **kwargs: Any) -> None:
            pass

        def hash(self, data: str | bytes) -> str:
            import hashlib

            if isinstance(data, str):
                data = data.encode()
            return hashlib.sha256(data).hexdigest()

        def verify_hash(self, data: str | bytes, expected: str) -> bool:
            return self.hash(data) == expected

        def encrypt(self, data: bytes, key: bytes = b"") -> bytes:
            raise NotImplementedError("CryptoService.encrypt not available in standalone mode")

        def decrypt(self, data: bytes, key: bytes = b"") -> bytes:
            raise NotImplementedError("CryptoService.decrypt not available in standalone mode")

        def generate_token(self, length: int = 32) -> str:
            import secrets

            return secrets.token_hex(length)

    def get_crypto_service(**kwargs: Any) -> CryptoService:
        return CryptoService(**kwargs)
