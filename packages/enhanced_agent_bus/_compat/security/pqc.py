"""Shim for src.core.shared.security.pqc."""
from __future__ import annotations

try:
    from src.core.shared.security.pqc import *  # noqa: F403
    from src.core.shared.security.pqc import (
        APPROVED_CLASSICAL,
        APPROVED_PQC,
        CONSTITUTIONAL_HASH,
        HYBRID_MODE_ENABLED,
        ClassicalKeyRejectedError,
        ConstitutionalHashMismatchError,
        KeyRegistryUnavailableError,
        MigrationRequiredError,
        PQCError,
        PQCKeyRequiredError,
        PQCVerificationError,
        SignatureSubstitutionError,
        UnsupportedAlgorithmError,
        UnsupportedPQCAlgorithmError,
    )
except ImportError:
    CONSTITUTIONAL_HASH = "608508a9bd224290"
    APPROVED_PQC = frozenset({"ML-KEM-768", "ML-DSA-65", "SLH-DSA-SHA2-128s"})
    APPROVED_CLASSICAL = frozenset({"RSA-4096", "ECDSA-P384", "Ed25519"})
    HYBRID_MODE_ENABLED = True

    class PQCError(Exception):
        """Base PQC error for standalone mode."""

    class UnsupportedPQCAlgorithmError(PQCError):
        pass

    class PQCKeyRequiredError(PQCError):
        pass

    class ClassicalKeyRejectedError(PQCError):
        pass

    class MigrationRequiredError(PQCError):
        pass

    class KeyRegistryUnavailableError(PQCError):
        pass

    class UnsupportedAlgorithmError(PQCError):
        pass

    class ConstitutionalHashMismatchError(PQCError):
        pass

    class PQCVerificationError(PQCError):
        pass

    class SignatureSubstitutionError(PQCError):
        pass

    class PQCKeyGenerationError(PQCError):
        pass

    class PQCSignatureError(PQCError):
        pass

    class PQCEncryptionError(PQCError):
        pass

    class PQCDecryptionError(PQCError):
        pass

    class PQCDeprecationWarning(PQCError):
        pass
