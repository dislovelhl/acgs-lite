"""
ACGS-2 Shared PQC Cryptography Types
Constitutional Hash: 608508a9bd224290

Explicit Protocol definitions to avoid a hard boundary violation (shared → services).
These interfaces define the contract that concrete PQC implementations must fulfill.

Also provides generate_key_pair() for NIST FIPS 203/204 key generation.

Usage:
    from src.core.shared.security.pqc_crypto import (
        HybridSignature,
        PQCConfig,
        PQCCryptoService,
        PQCMetadata,
        ValidationResult,
        generate_key_pair,
    )
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Literal

    class PQCConfig:
        """Protocol defining post-quantum cryptography configuration."""

        pqc_enabled: bool
        pqc_mode: Literal["classical_only", "hybrid", "pqc_only"]
        verification_mode: Literal["strict", "classical_only", "pqc_only"]
        kem_algorithm: str
        migration_phase: str
        cache_max_size: int

        def validate(self) -> list[str]:
            """Validate the PQC configuration and return a list of error messages."""
            return []

    class PQCMetadata:
        """Protocol for post-quantum cryptography metadata."""

    class HybridSignature:
        """Protocol for hybrid classical/PQC signature data."""

        content_hash: str
        constitutional_hash: str

    class ValidationResult:
        """Protocol for PQC signature validation results."""

        is_valid: bool
        errors: list[str]

    class PQCCryptoService:
        """Protocol for the post-quantum cryptography service."""

        config: PQCConfig

        def process(self, input_value: str | None) -> str | None:
            """Process an input value through the PQC crypto service."""
            return input_value

else:
    # At runtime, these act as base object types to allow isinstance checks
    # or optional typing without breaking.
    from dataclasses import dataclass, field

    @dataclass
    class PQCConfig:
        """Runtime stub for PQCConfig."""

        pqc_enabled: bool = False
        pqc_mode: str = "classical_only"
        verification_mode: str = "strict"

    class PQCCryptoService:
        """Runtime stub for PQCCryptoService when pqc-crypto library is unavailable."""

    @dataclass
    class HybridSignature:
        """Runtime stub for HybridSignature."""

        content_hash: str = ""
        constitutional_hash: str = ""

    @dataclass
    class PQCMetadata:
        """Runtime stub for PQCMetadata."""

        pqc_enabled: bool = False
        pqc_algorithm: str | None = None
        classical_verified: bool = False
        pqc_verified: bool = False
        verification_mode: str = "classical_only"

    @dataclass
    class ValidationResult:
        """Runtime stub for ValidationResult."""

        valid: bool = False
        constitutional_hash: str = ""
        errors: list[str] = field(default_factory=list)
        warnings: list[str] = field(default_factory=list)
        pqc_metadata: PQCMetadata | None = None
        validation_duration_ms: float | None = None
        classical_verification_ms: float | None = None
        pqc_verification_ms: float | None = None


PQC_CRYPTO_AVAILABLE = True  # The interfaces are always available


# ---------------------------------------------------------------------------
# Key pair generation
# ---------------------------------------------------------------------------


def generate_key_pair(algorithm_variant: object) -> tuple[bytes, bytes]:
    """
    Generate a key pair for the given algorithm variant.

    Dispatches to liboqs-python for NIST PQC algorithms.

    Phase 5: Classical algorithms (Ed25519, X25519) have been decommissioned.

    Args:
        algorithm_variant: An ``AlgorithmVariant`` enum value from
            ``pqc_algorithm_registry``.

    Returns:
        (public_key_bytes, private_key_bytes) — callers must treat the
        second element as sensitive material and encrypt it immediately.

    Raises:
        UnsupportedAlgorithmError: If the variant is not in APPROVED_ALGORITHMS.

    Notes:
        - Private key bytes are never logged; only algorithm_variant and the
          public key fingerprint may appear in DEBUG logs.
        - All branches are handled explicitly via match/case.
    """
    # Late imports: keep the shared/ module free of hard service-layer deps.
    from src.core.services.policy_registry.app.services.pqc_algorithm_registry import (
        APPROVED_ALGORITHMS,
        AlgorithmVariant,
        UnsupportedAlgorithmError,
    )
    from src.core.shared.structured_logging import get_logger

    _logger = get_logger(__name__)

    if algorithm_variant not in APPROVED_ALGORITHMS:
        raise UnsupportedAlgorithmError(
            f"Algorithm '{algorithm_variant}' is not approved for key generation.",
            details={"algorithm": str(algorithm_variant)},
        )

    import hashlib

    match algorithm_variant:
        case AlgorithmVariant.ML_DSA_44 | AlgorithmVariant.ML_DSA_65 | AlgorithmVariant.ML_DSA_87:
            import oqs  # type: ignore[import-untyped]

            signer = oqs.Signature(algorithm_variant.value)
            pub = signer.generate_keypair()
            priv = signer.export_secret_key()
            _logger.debug(
                "ML-DSA key pair generated",
                algorithm_variant=algorithm_variant.value,
                public_key_fingerprint=hashlib.sha256(pub).hexdigest(),
            )
            return pub, priv

        case (
            AlgorithmVariant.ML_KEM_512 | AlgorithmVariant.ML_KEM_768 | AlgorithmVariant.ML_KEM_1024
        ):
            import oqs  # type: ignore[import-untyped]

            kem = oqs.KeyEncapsulation(algorithm_variant.value)
            pub = kem.generate_keypair()
            priv = kem.export_secret_key()
            _logger.debug(
                "ML-KEM key pair generated",
                algorithm_variant=algorithm_variant.value,
                public_key_fingerprint=hashlib.sha256(pub).hexdigest(),
            )
            return pub, priv

        case _:
            raise UnsupportedAlgorithmError(
                f"Algorithm '{algorithm_variant}' has no key generation handler.",
                details={"algorithm": str(algorithm_variant)},
            )


# ---------------------------------------------------------------------------
# Signature verification (Phase 1 PQC Migration — T029)
# ---------------------------------------------------------------------------


def verify_signature(
    algorithm_variant: object,
    public_key_bytes: bytes,
    message: bytes,
    signature: bytes,
) -> bool:
    """Verify *signature* over *message* using *public_key_bytes*.

    Dispatches to liboqs-python for ML-DSA variants and to the
    ``cryptography`` library for Ed25519.

    Args:
        algorithm_variant: An ``AlgorithmVariant`` enum value.
        public_key_bytes: Raw public key material.
        message: The signed message bytes.
        signature: The signature to verify.

    Returns:
        ``True`` if the signature is valid, ``False`` if the signature bytes
        are invalid.  Never raises on an invalid signature — only raises on
        algorithm errors.

    Raises:
        UnsupportedAlgorithmError: *algorithm_variant* is not approved.
    """
    from src.core.services.policy_registry.app.services.pqc_algorithm_registry import (
        APPROVED_ALGORITHMS,
        AlgorithmVariant,
        UnsupportedAlgorithmError,
    )
    from src.core.shared.structured_logging import get_logger

    _logger = get_logger(__name__)

    if algorithm_variant not in APPROVED_ALGORITHMS:
        raise UnsupportedAlgorithmError(
            f"Algorithm '{algorithm_variant}' is not approved for verification.",
            details={"algorithm": str(algorithm_variant)},
        )

    import hashlib

    _logger.debug(
        "Verifying signature",
        algorithm_variant=str(algorithm_variant),
        public_key_fingerprint=hashlib.sha256(public_key_bytes).hexdigest(),
    )

    match algorithm_variant:
        case AlgorithmVariant.ML_DSA_44 | AlgorithmVariant.ML_DSA_65 | AlgorithmVariant.ML_DSA_87:
            import oqs  # type: ignore[import-untyped]

            verifier = oqs.Signature(algorithm_variant.value)
            try:
                is_valid: bool = verifier.verify(message, signature, public_key_bytes)
            except (ValueError, TypeError, RuntimeError):
                return False
            return is_valid

        case (
            AlgorithmVariant.ML_KEM_512 | AlgorithmVariant.ML_KEM_768 | AlgorithmVariant.ML_KEM_1024
        ):
            raise UnsupportedAlgorithmError(
                f"ML-KEM algorithm '{algorithm_variant}' is a KEM and does not support signatures.",
                details={"algorithm": str(algorithm_variant)},
            )

        case _:
            raise UnsupportedAlgorithmError(
                f"Algorithm '{algorithm_variant}' has no signature verification handler.",
                details={"algorithm": str(algorithm_variant)},
            )


__all__ = [
    "PQC_CRYPTO_AVAILABLE",
    "HybridSignature",
    "PQCConfig",
    "PQCCryptoService",
    "PQCMetadata",
    "ValidationResult",
    "generate_key_pair",
    "verify_signature",
]
