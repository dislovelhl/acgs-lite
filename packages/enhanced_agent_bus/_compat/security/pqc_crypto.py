"""Shim for src.core.shared.security.pqc_crypto."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

try:
    from src.core.shared.security.pqc_crypto import *  # noqa: F403
except ImportError:

    @runtime_checkable
    class PQCKeyPair(Protocol):
        public_key: bytes
        private_key: bytes

    @runtime_checkable
    class PQCCryptoProvider(Protocol):
        def generate_keypair(self) -> PQCKeyPair: ...
        def sign(self, data: bytes, private_key: bytes) -> bytes: ...
        def verify(self, data: bytes, signature: bytes, public_key: bytes) -> bool: ...
        def encrypt(self, data: bytes, public_key: bytes) -> bytes: ...
        def decrypt(self, data: bytes, private_key: bytes) -> bytes: ...

    class StubPQCKeyPair:
        def __init__(self) -> None:
            self.public_key = b""
            self.private_key = b""

    class StubPQCCryptoProvider:
        def generate_keypair(self) -> StubPQCKeyPair:
            return StubPQCKeyPair()

        def sign(self, data: bytes, private_key: bytes) -> bytes:
            return b""

        def verify(self, data: bytes, signature: bytes, public_key: bytes) -> bool:
            return False

        def encrypt(self, data: bytes, public_key: bytes) -> bytes:
            return data

        def decrypt(self, data: bytes, private_key: bytes) -> bytes:
            return data

    def get_pqc_provider(**kwargs: Any) -> StubPQCCryptoProvider:
        return StubPQCCryptoProvider()
