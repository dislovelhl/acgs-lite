"""Optional post-quantum signature support for audit entries.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import hmac
from typing import Protocol


class PQCSigner(Protocol):
    def sign(self, data: bytes) -> str: ...

    def verify(self, data: bytes, sig: str) -> bool: ...


class InMemoryPQCSigner:
    def sign(self, data: bytes) -> str:
        return hmac.new(b"test-key", data, "sha256").hexdigest()

    def verify(self, data: bytes, sig: str) -> bool:
        expected = self.sign(data)
        return hmac.compare_digest(expected, sig)


try:
    from oqs import Signature as _OQSSignature
except BaseException:  # pragma: no cover - optional dependency may fail during import-time setup
    _OQSSignature = None


class _DilithiumSigner:
    """oqs-backed ML-DSA-44 signer."""

    def __init__(self) -> None:
        if _OQSSignature is None:
            raise RuntimeError("oqs Signatures are unavailable in this environment")
        self._algorithm = "ML-DSA-44"
        with _OQSSignature(self._algorithm) as signer:
            self._public_key = signer.generate_keypair()
            self._secret_key = signer.export_secret_key()

    def sign(self, data: bytes) -> str:
        if _OQSSignature is None:
            raise RuntimeError("oqs Signatures are unavailable in this environment")
        with _OQSSignature(self._algorithm, secret_key=self._secret_key) as signer:
            return signer.sign(data).hex()

    def verify(self, data: bytes, sig: str) -> bool:
        if _OQSSignature is None:
            raise RuntimeError("oqs Signatures are unavailable in this environment")
        with _OQSSignature(self._algorithm) as verifier:
            return verifier.verify(data, bytes.fromhex(sig), self._public_key)


DilithiumSigner = _DilithiumSigner if _OQSSignature is not None else None
