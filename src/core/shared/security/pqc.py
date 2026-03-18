"""
ACGS-2 Post-Quantum Cryptography Wrapper
Constitutional Hash: cdd01ef066bc6cf2

Low-level PQC wrapper using liboqs-python for quantum-resistant cryptography.

This module provides:
- PQC key generation (ML-KEM (Kyber), ML-DSA (Dilithium), SLH-DSA (SPHINCS+))
- PQC signing and verification operations
- PQC key encapsulation mechanism (KEM)
- Data structures for PQC keys, signatures, and KEM results
- Comprehensive error handling for PQC operations

Supported Algorithms:
- ML-KEM / Kyber (FIPS 203): ml-kem-512, kyber512, kyber768, kyber1024
- ML-DSA / Dilithium (FIPS 204): ml-dsa-44, dilithium2, dilithium3, dilithium5
- SLH-DSA / SPHINCS+ (FIPS 205): slh-dsa-sha2-128s, sphincssha2128ssimple, sphincssha2256fsimple

Performance Targets:
- Kyber768 key generation: ~20 µs
- Dilithium3 signing: ~230 µs
- Dilithium3 verification: ~130 µs
"""

import base64
import os
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from importlib.util import find_spec
from typing import Literal, cast

from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.errors.exceptions import ACGSBaseError
from src.core.shared.structured_logging import get_logger

logger = get_logger(__name__)

# ============================================================================
# Exception Hierarchy
# ============================================================================


class PQCError(ACGSBaseError):
    """Base exception for all PQC errors (Q-H4 migration)."""

    http_status_code = 500
    error_code = "PQC_ERROR"


class PQCKeyGenerationError(PQCError):
    """Failed to generate PQC key pair."""

    pass


class PQCSignatureError(PQCError):
    """Failed to create PQC signature."""

    pass


class PQCVerificationError(PQCError):
    """Failed to verify PQC signature (not invalid signature)."""

    pass


class PQCEncapsulationError(PQCError):
    """Failed to encapsulate shared secret."""

    pass


class PQCDecapsulationError(PQCError):
    """Failed to decapsulate shared secret."""

    pass


class UnsupportedAlgorithmError(PQCError):
    """Unsupported PQC algorithm requested."""

    pass


class ConstitutionalHashMismatchError(PQCError):
    """Constitutional hash does not match expected value."""

    pass


class SignatureSubstitutionError(PQCError):
    """Content hash mismatch (possible signature substitution attack)."""

    pass


class PQCConfigurationError(PQCError):
    """Invalid PQC configuration."""

    pass


class KeyRegistryUnavailableError(PQCError):
    """Key Registry is unavailable."""

    pass


class ClassicalKeyRejectedError(PQCError):
    """Classical (non-PQC) key rejected in strict enforcement mode."""

    http_status_code = 403
    error_code = "CLASSICAL_KEY_REJECTED"

    def __init__(
        self,
        message: str = "Classical key rejected: PQC key required in strict mode",
        supported_algorithms: list[str] | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message, details=details)
        self.supported_algorithms = supported_algorithms or []


class PQCKeyRequiredError(PQCError):
    """PQC key is required but not present."""

    http_status_code = 403
    error_code = "PQC_KEY_REQUIRED"

    def __init__(
        self,
        message: str = "PQC key required for this operation",
        supported_algorithms: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.supported_algorithms = supported_algorithms or []


class MigrationRequiredError(PQCError):
    """Record must be migrated to PQC before this operation."""

    http_status_code = 403
    error_code = "MIGRATION_REQUIRED"

    def __init__(
        self,
        message: str = "PQC migration required before this operation",
        supported_algorithms: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.supported_algorithms = supported_algorithms or []


class UnsupportedPQCAlgorithmError(PQCError):
    """Requested PQC algorithm is not in the approved set."""

    http_status_code = 400
    error_code = "UNSUPPORTED_PQC_ALGORITHM"

    def __init__(
        self,
        message: str = "Unsupported PQC algorithm",
        supported_algorithms: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.supported_algorithms = supported_algorithms or []


# ============================================================================
# Data Classes
# ============================================================================


@dataclass
class PQCKeyPair:
    """Post-quantum cryptographic key pair."""

    public_key: bytes  # Variable size based on algorithm
    private_key: bytes  # Variable size based on algorithm
    algorithm: Literal[
        "ml-kem-512",
        "ml-kem-768",
        "ml-kem-1024",
        "kyber512",
        "kyber768",
        "kyber1024",
        "ml-dsa-44",
        "ml-dsa-65",
        "ml-dsa-87",
        "dilithium2",
        "dilithium3",
        "dilithium5",
        "slh-dsa-sha2-128s",
        "slh-dsa-sha2-256f",
        "sphincssha2128ssimple",
        "sphincssha2256fsimple",
    ]
    security_level: Literal[1, 2, 3, 4, 5]  # NIST security level
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    key_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    @property
    def public_key_size(self) -> int:
        """Get public key size in bytes."""
        return len(self.public_key)

    @property
    def private_key_size(self) -> int:
        """Get private key size in bytes."""
        return len(self.private_key)

    def serialize(self) -> dict:
        """Serialize for storage/transmission (public key only)."""
        return {
            "key_id": self.key_id,
            "algorithm": self.algorithm,
            "security_level": self.security_level,
            "public_key": base64.b64encode(self.public_key).decode(),
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class PQCSignature:
    """Post-quantum cryptographic signature (Dilithium or SPHINCS+)."""

    signature: bytes  # Variable size based on algorithm
    algorithm: Literal[
        "ml-dsa-44",
        "ml-dsa-65",
        "ml-dsa-87",
        "dilithium2",
        "dilithium3",
        "dilithium5",
        "slh-dsa-sha2-128s",
        "slh-dsa-sha2-256f",
        "sphincssha2128ssimple",
        "sphincssha2256fsimple",
    ]
    signer_key_id: str  # Key ID used for signing
    signed_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def signature_size(self) -> int:
        """Get signature size in bytes."""
        return len(self.signature)

    def to_dict(self) -> dict:
        """Serialize for storage/transmission."""
        return {
            "signature": base64.b64encode(self.signature).decode(),
            "algorithm": self.algorithm,
            "signer_key_id": self.signer_key_id,
            "signed_at": self.signed_at.isoformat(),
        }


@dataclass
class KEMResult:
    """Result of key encapsulation operation."""

    ciphertext: bytes  # Encapsulated shared secret
    shared_secret: bytes  # Symmetric key for AES-256-GCM (32 bytes)
    algorithm: str  # e.g., "kyber768"
    encapsulated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def ciphertext_size(self) -> int:
        """Get ciphertext size in bytes."""
        return len(self.ciphertext)

    @property
    def shared_secret_size(self) -> int:
        """Get shared secret size in bytes (should be 32 for AES-256)."""
        return len(self.shared_secret)

    def to_dict(self) -> dict:
        """Serialize for storage/transmission (excludes shared secret for security)."""
        return {
            "ciphertext": base64.b64encode(self.ciphertext).decode(),
            "algorithm": self.algorithm,
            "encapsulated_at": self.encapsulated_at.isoformat(),
            # Note: shared_secret is NOT serialized for security reasons
        }


# ============================================================================
# Algorithm Constants & Hybrid Mode (Phase 1 PQC Migration — T026)
# ============================================================================

NIST_ALGORITHM_ALIASES: dict[str, str] = {
    "dilithium2": "ML-DSA-44",
    "dilithium3": "ML-DSA-65",
    "dilithium5": "ML-DSA-87",
    "kyber512": "ML-KEM-512",
    "kyber768": "ML-KEM-768",
    "kyber1024": "ML-KEM-1024",
}

APPROVED_CLASSICAL: frozenset[str] = frozenset({"Ed25519", "X25519"})

APPROVED_PQC: frozenset[str] = frozenset(
    {
        "ML-DSA-44",
        "ML-DSA-65",
        "ML-DSA-87",
        "ML-KEM-512",
        "ML-KEM-768",
        "ML-KEM-1024",
    }
)

HYBRID_MODE_ENABLED: bool = os.environ.get("PQC_HYBRID_MODE", "true").lower() == "true"


def normalize_to_nist(algorithm_name: str) -> str:
    """Return the NIST canonical name for *algorithm_name*.

    If *algorithm_name* is already a canonical NIST name or an approved
    classical algorithm, it is returned unchanged.  Legacy aliases (e.g.
    ``dilithium3``) are mapped via :data:`NIST_ALGORITHM_ALIASES`.

    Raises:
        UnsupportedAlgorithmError: *algorithm_name* is neither a known alias
            nor a recognised canonical name.
    """
    if algorithm_name in APPROVED_PQC or algorithm_name in APPROVED_CLASSICAL:
        return algorithm_name
    canonical = NIST_ALGORITHM_ALIASES.get(algorithm_name.lower())
    if canonical is not None:
        return canonical
    raise UnsupportedAlgorithmError(
        f"Algorithm '{algorithm_name}' is not a recognised NIST PQC or classical algorithm.",
        details={"algorithm": algorithm_name},
    )


# ============================================================================
# PQC Wrapper Implementation
# ============================================================================


class PQCWrapper:
    """
    Low-level PQC wrapper using liboqs-python.

    Provides quantum-resistant cryptographic operations including key generation,
    signing/verification, and key encapsulation mechanisms.

    Thread-safe: Yes (liboqs operations are thread-safe)
    Performance: Optimized for production use with <10% overhead target
    """

    def __init__(self):
        """Initialize PQC wrapper."""
        self._check_liboqs_available()
        logger.info("PQCWrapper initialized successfully")

    def _check_liboqs_available(self) -> None:
        """
        Check if liboqs-python is available.

        Raises:
            PQCConfigurationError: If liboqs is not installed
        """
        if find_spec("oqs") is None:
            logger.error("liboqs-python not installed. Install with: pip install liboqs-python")
            raise PQCConfigurationError(
                "liboqs-python not installed. Required for PQC operations."
            )
        logger.debug("liboqs-python is available")

    # ========================================================================
    # Key Generation Methods
    # ========================================================================

    def generate_kyber_keypair(
        self,
        security_level: Literal["ml-kem-512", "ml-kem-768", "ml-kem-1024", 512, 768, 1024] = 768,
    ) -> PQCKeyPair:
        """
        Generate ML-KEM (Kyber) key pair (FIPS 203).

        Args:
            security_level: Kyber variant (512, 768, or 1024)

        Returns:
            PQCKeyPair with Kyber keys

        Raises:
            PQCKeyGenerationError: If key generation fails
            UnsupportedAlgorithmError: If security level not supported

        Performance:
            - Kyber768: ~20 µs (target)
        """
        try:
            import oqs

            # Map new FIPS names to liboqs Kyber implementation
            if str(security_level).startswith("ml-kem"):
                security_level = security_level.split("-")[-1]
            algorithm_name = f"Kyber{security_level}"

            algorithm_enum = f"kyber{security_level}"

            # Map security level to NIST level
            nist_level_map = {512: 1, 768: 3, 1024: 5}
            nist_level = nist_level_map.get(security_level)

            if nist_level is None:
                raise UnsupportedAlgorithmError(
                    f"Unsupported Kyber security level: {security_level}. Supported: 512, 768, 1024"
                )

            logger.debug(f"Generating {algorithm_name} key pair")

            with oqs.KeyEncapsulation(algorithm_name) as kem:
                public_key = kem.generate_keypair()
                private_key = kem.export_secret_key()

            logger.info(
                f"Generated {algorithm_name} key pair: "
                f"public={len(public_key)} bytes, private={len(private_key)} bytes"
            )

            return PQCKeyPair(
                public_key=public_key,
                private_key=private_key,
                algorithm=algorithm_enum,  # type: ignore[arg-type]
                security_level=nist_level,  # type: ignore[arg-type]
            )

        except UnsupportedAlgorithmError:
            raise
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as e:
            logger.error(f"Kyber key generation failed: {e}")
            raise PQCKeyGenerationError(f"Failed to generate Kyber{security_level} key pair") from e

    def generate_dilithium_keypair(
        self, security_level: Literal["ml-dsa-44", "ml-dsa-65", "ml-dsa-87", 2, 3, 5] = 3
    ) -> PQCKeyPair:
        """
        Generate ML-DSA (Dilithium) signature key pair (FIPS 204).

        Args:
            security_level: Dilithium variant (2, 3, or 5)

        Returns:
            PQCKeyPair with Dilithium keys

        Raises:
            PQCKeyGenerationError: If key generation fails
            UnsupportedAlgorithmError: If security level not supported

        Performance:
            - Dilithium3: ~100 µs (target)
        """
        try:
            import oqs

            # Map security levels to NIST FIPS 204 algorithm names (liboqs >= 0.15)
            _nist_sig_names = {2: "ML-DSA-44", 3: "ML-DSA-65", 5: "ML-DSA-87"}
            fips_to_level = {"ml-dsa-44": 2, "ml-dsa-65": 3, "ml-dsa-87": 5}
            if str(security_level) in fips_to_level:
                security_level = fips_to_level[str(security_level)]
            algorithm_name = _nist_sig_names.get(security_level)

            algorithm_enum = f"dilithium{security_level}"

            # Map security level to NIST level
            nist_level_map = {2: 2, 3: 3, 5: 5}
            nist_level = nist_level_map.get(security_level)

            if algorithm_name is None or nist_level is None:
                raise UnsupportedAlgorithmError(
                    f"Unsupported Dilithium security level: {security_level}. Supported: 2, 3, 5"
                )

            logger.debug(f"Generating {algorithm_name} key pair")

            with oqs.Signature(algorithm_name) as sig:
                public_key = sig.generate_keypair()
                private_key = sig.export_secret_key()

            logger.info(
                f"Generated {algorithm_name} key pair: "
                f"public={len(public_key)} bytes, private={len(private_key)} bytes"
            )

            return PQCKeyPair(
                public_key=public_key,
                private_key=private_key,
                algorithm=algorithm_enum,  # type: ignore[arg-type]
                security_level=nist_level,  # type: ignore[arg-type]
            )

        except UnsupportedAlgorithmError:
            raise
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as e:
            logger.error(f"Dilithium key generation failed: {e}")
            raise PQCKeyGenerationError(
                f"Failed to generate Dilithium{security_level} key pair"
            ) from e

    def generate_sphincs_keypair(
        self, variant: Literal["sha2-128s-simple", "sha2-256f-simple"] = "sha2-128s-simple"
    ) -> PQCKeyPair:
        """
        Generate SPHINCS+ signature key pair (backup/archival use).

        Args:
            variant: SPHINCS+ variant

        Returns:
            PQCKeyPair with SPHINCS+ keys

        Raises:
            PQCKeyGenerationError: If key generation fails

        Performance:
            - SPHINCS+-SHA2-128s: ~15 ms (slow, for archival only)

        Note:
            SPHINCS+ is slower than Dilithium but provides additional security
            guarantees. Recommended for long-term archival signatures.
        """
        try:
            import oqs

            # Map variant to NIST FIPS 205 / SLH-DSA algorithm names (liboqs >= 0.15)
            variant_map = {
                "sha2-128s-simple": "SLH_DSA_PURE_SHA2_128S",
                "sha2-256f-simple": "SLH_DSA_PURE_SHA2_256F",
            }

            enum_map = {
                "sha2-128s-simple": "sphincssha2128ssimple",
                "sha2-256f-simple": "sphincssha2256fsimple",
            }

            nist_level_map = {"sha2-128s-simple": 1, "sha2-256f-simple": 5}

            algorithm_name = variant_map.get(variant)
            algorithm_enum = enum_map.get(variant)
            nist_level = nist_level_map.get(variant)

            if not algorithm_name:
                raise UnsupportedAlgorithmError(
                    f"Unsupported SPHINCS+ variant: {variant}. "
                    f"Supported: sha2-128s-simple, sha2-256f-simple"
                )

            logger.debug(f"Generating {algorithm_name} key pair")

            with oqs.Signature(algorithm_name) as sig:
                public_key = sig.generate_keypair()
                private_key = sig.export_secret_key()

            logger.info(
                f"Generated {algorithm_name} key pair: "
                f"public={len(public_key)} bytes, private={len(private_key)} bytes"
            )

            return PQCKeyPair(
                public_key=public_key,
                private_key=private_key,
                algorithm=algorithm_enum,  # type: ignore[arg-type]
                security_level=nist_level,  # type: ignore[arg-type]
            )

        except UnsupportedAlgorithmError:
            raise
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as e:
            logger.error(f"SPHINCS+ key generation failed: {e}")
            raise PQCKeyGenerationError(f"Failed to generate SPHINCS+ {variant} key pair") from e

    # ========================================================================
    # Signing and Verification Methods
    # ========================================================================

    def sign_dilithium(
        self,
        message: bytes,
        private_key: bytes,
        security_level: Literal["ml-dsa-44", "ml-dsa-65", "ml-dsa-87", 2, 3, 5] = 3,
    ) -> bytes:
        """
        Sign message with Dilithium.

        Args:
            message: Message to sign
            private_key: Dilithium private key
            security_level: Dilithium variant

        Returns:
            Signature bytes (~3,293 bytes for Dilithium3)

        Raises:
            PQCSignatureError: If signing fails

        Performance:
            - Dilithium3: ~230 µs (target)
        """
        try:
            import oqs

            # Map to NIST FIPS 204 algorithm names (liboqs >= 0.15)
            _nist_sig_names = {2: "ML-DSA-44", 3: "ML-DSA-65", 5: "ML-DSA-87"}
            fips_to_level = {"ml-dsa-44": 2, "ml-dsa-65": 3, "ml-dsa-87": 5}
            if str(security_level) in fips_to_level:
                security_level = fips_to_level[str(security_level)]
            algorithm_name = _nist_sig_names.get(security_level, f"ML-DSA-{security_level}")

            logger.debug(f"Signing with {algorithm_name}, message size: {len(message)} bytes")

            with oqs.Signature(algorithm_name, secret_key=private_key) as sig:
                signature = sig.sign(message)

            logger.info(f"Signed with {algorithm_name}, signature size: {len(signature)} bytes")

            return cast(bytes, signature)

        except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as e:
            logger.error(f"Dilithium signing failed: {e}")
            raise PQCSignatureError(f"Failed to sign with Dilithium{security_level}") from e

    def verify_dilithium(
        self,
        message: bytes,
        signature: bytes,
        public_key: bytes,
        security_level: Literal["ml-dsa-44", "ml-dsa-65", "ml-dsa-87", 2, 3, 5] = 3,
    ) -> bool:
        """
        Verify Dilithium signature.

        Args:
            message: Original message
            signature: Signature to verify
            public_key: Dilithium public key
            security_level: Dilithium variant

        Returns:
            True if signature is valid, False otherwise

        Raises:
            PQCVerificationError: If verification fails (not invalid signature)

        Performance:
            - Dilithium3: ~130 µs (target)
        """
        try:
            import oqs

            # Map to NIST FIPS 204 algorithm names (liboqs >= 0.15)
            _nist_sig_names = {2: "ML-DSA-44", 3: "ML-DSA-65", 5: "ML-DSA-87"}
            fips_to_level = {"ml-dsa-44": 2, "ml-dsa-65": 3, "ml-dsa-87": 5}
            if str(security_level) in fips_to_level:
                security_level = fips_to_level[str(security_level)]
            algorithm_name = _nist_sig_names.get(security_level, f"ML-DSA-{security_level}")

            logger.debug(
                f"Verifying {algorithm_name} signature, "
                f"message size: {len(message)} bytes, signature size: {len(signature)} bytes"
            )

            with oqs.Signature(algorithm_name) as sig:
                is_valid = sig.verify(message, signature, public_key)

            logger.info(
                f"{algorithm_name} signature verification: {'valid' if is_valid else 'invalid'}"
            )

            return cast(bool, is_valid)

        except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as e:
            logger.error(f"Dilithium verification failed: {e}")
            raise PQCVerificationError(
                f"Failed to verify Dilithium{security_level} signature"
            ) from e

    # ========================================================================
    # Key Encapsulation Methods
    # ========================================================================

    def encapsulate_kyber(
        self,
        public_key: bytes,
        security_level: Literal["ml-kem-512", "ml-kem-768", "ml-kem-1024", 512, 768, 1024] = 768,
    ) -> KEMResult:
        """
        Encapsulate shared secret with Kyber.

        Args:
            public_key: Kyber public key
            security_level: Kyber variant

        Returns:
            KEMResult with ciphertext and shared secret

        Raises:
            PQCEncapsulationError: If encapsulation fails

        Performance:
            - Kyber768: ~30 µs (target)
        """
        try:
            import oqs

            # Map new FIPS names to liboqs Kyber implementation
            if str(security_level).startswith("ml-kem"):
                security_level = security_level.split("-")[-1]
            algorithm_name = f"Kyber{security_level}"

            algorithm_enum = f"kyber{security_level}"

            logger.debug(f"Encapsulating with {algorithm_name}")

            with oqs.KeyEncapsulation(algorithm_name) as kem:
                ciphertext, shared_secret = kem.encap_secret(public_key)

            logger.info(
                f"Encapsulated with {algorithm_name}: "
                f"ciphertext={len(ciphertext)} bytes, shared_secret={len(shared_secret)} bytes"
            )

            return KEMResult(
                ciphertext=ciphertext, shared_secret=shared_secret, algorithm=algorithm_enum
            )

        except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as e:
            logger.error(f"Kyber encapsulation failed: {e}")
            raise PQCEncapsulationError(f"Failed to encapsulate with Kyber{security_level}") from e

    def decapsulate_kyber(
        self,
        ciphertext: bytes,
        private_key: bytes,
        security_level: Literal["ml-kem-512", "ml-kem-768", "ml-kem-1024", 512, 768, 1024] = 768,
    ) -> bytes:
        """
        Decapsulate shared secret with Kyber.

        Args:
            ciphertext: Kyber ciphertext
            private_key: Kyber private key
            security_level: Kyber variant

        Returns:
            Shared secret (32 bytes)

        Raises:
            PQCDecapsulationError: If decapsulation fails

        Performance:
            - Kyber768: ~30 µs (target)
        """
        try:
            import oqs

            # Map new FIPS names to liboqs Kyber implementation
            if str(security_level).startswith("ml-kem"):
                security_level = security_level.split("-")[-1]
            algorithm_name = f"Kyber{security_level}"

            logger.debug(
                f"Decapsulating with {algorithm_name}, ciphertext size: {len(ciphertext)} bytes"
            )

            with oqs.KeyEncapsulation(algorithm_name, secret_key=private_key) as kem:
                shared_secret = kem.decap_secret(ciphertext)

            logger.info(
                f"Decapsulated with {algorithm_name}, shared_secret={len(shared_secret)} bytes"
            )

            return cast(bytes, shared_secret)

        except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as e:
            logger.error(f"Kyber decapsulation failed: {e}")
            raise PQCDecapsulationError(f"Failed to decapsulate with Kyber{security_level}") from e


# ============================================================================
# Exports
# ============================================================================

__all__ = [
    "APPROVED_CLASSICAL",
    "APPROVED_PQC",
    # Constants
    "CONSTITUTIONAL_HASH",
    "HYBRID_MODE_ENABLED",
    # Phase 1 PQC Migration (T026)
    "NIST_ALGORITHM_ALIASES",
    "ClassicalKeyRejectedError",
    "ConstitutionalHashMismatchError",
    "KEMResult",
    "MigrationRequiredError",
    "PQCConfigurationError",
    "PQCDecapsulationError",
    "PQCEncapsulationError",
    # Exceptions
    "PQCError",
    "PQCKeyGenerationError",
    # Data classes
    "PQCKeyPair",
    "PQCKeyRequiredError",
    "PQCSignature",
    "PQCSignatureError",
    "PQCVerificationError",
    # Wrapper class
    "PQCWrapper",
    "SignatureSubstitutionError",
    "UnsupportedAlgorithmError",
    "UnsupportedPQCAlgorithmError",
    "normalize_to_nist",
]
