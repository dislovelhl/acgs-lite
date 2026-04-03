"""
ACGS-2 Enhanced Agent Bus - Validation Strategies
Constitutional Hash: 608508a9bd224290

Validation strategy implementations for message validation.
"""

import base64
import binascii
import hashlib

from enhanced_agent_bus.observability.structured_logging import get_logger
from enhanced_agent_bus.shared.fail_closed import fail_closed

try:
    from .dependency_bridge import get_dependency, is_feature_available
    from .models import AgentMessage

    OPA_CLIENT_AVAILABLE: bool = is_feature_available("OPA")
    get_opa_client = get_dependency("get_opa_client")
except (ImportError, ValueError):
    from models import AgentMessage  # type: ignore[import-untyped]

    OPA_CLIENT_AVAILABLE = False
    get_opa_client = None

try:
    from .models import CONSTITUTIONAL_HASH, AgentMessage
except ImportError:
    from models import CONSTITUTIONAL_HASH, AgentMessage  # type: ignore[import-untyped]

# Import Protocol types for type safety
try:
    from .interfaces import (
        ConstitutionalVerifierProtocol,
        OPAClientProtocol,
        PolicyClientProtocol,
        PQCValidatorProtocol,
        RustProcessorProtocol,
        ValidationStrategy,
    )
except (ImportError, ValueError):
    # Fallback for standalone usage - define minimal protocols
    from typing import Protocol, runtime_checkable

    @runtime_checkable
    class PolicyClientProtocol(Protocol):  # type: ignore[no-redef]
        async def validate_message_signature(self, message: AgentMessage) -> object: ...

    @runtime_checkable
    class OPAClientProtocol(Protocol):  # type: ignore[no-redef]
        async def validate_constitutional(self, message: dict) -> object: ...

    @runtime_checkable
    class RustProcessorProtocol(Protocol):  # type: ignore[no-redef]
        def validate(self, message: dict) -> bool | dict: ...

    @runtime_checkable
    class PQCValidatorProtocol(Protocol):  # type: ignore[no-redef]
        def verify_governance_decision(
            self, decision: dict, signature: bytes, public_key: bytes
        ) -> bool: ...

    @runtime_checkable
    class ConstitutionalVerifierProtocol(Protocol):  # type: ignore[no-redef]
        async def verify_constitutional_compliance(
            self, action_data: dict, context: dict, session_id: str | None = None
        ) -> object: ...

    @runtime_checkable
    class ValidationStrategy(Protocol):  # type: ignore[no-redef]
        async def validate(self, message: AgentMessage) -> tuple[bool, str | None]: ...


# PQC imports (lazy loaded for optional dependency)
try:
    from quantum_research.post_quantum_crypto import (
        ConstitutionalHashValidator,
        PQCAlgorithm,
        PQCSignature,
    )

    PQC_AVAILABLE = True
except ImportError:
    PQC_AVAILABLE = False
    PQCAlgorithm = None  # type: ignore[assignment]
    PQCSignature = None  # type: ignore[assignment]
    ConstitutionalHashValidator = None  # type: ignore[assignment]

logger = get_logger(__name__)
_VALIDATION_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
)
_VALIDATION_DATA_ERRORS = (ValueError, TypeError, KeyError, binascii.Error)


class StaticHashValidationStrategy:
    """Validates messages using a static constitutional hash.

    Standard implementation that checks for hash consistency.
    Constitutional Hash: 608508a9bd224290
    """

    def __init__(self, strict: bool = True) -> None:
        """Initialize static hash validation.

        Args:
            strict: If True, reject messages with non-matching hashes
        """
        self._constitutional_hash = CONSTITUTIONAL_HASH
        self._strict = strict

    async def validate(self, message: AgentMessage) -> tuple[bool, str | None]:
        """Validate a message for constitutional compliance."""
        # Check message has content
        if message.content is None:
            return False, "Message content cannot be None"

        # Validate message_id exists
        if not message.message_id:
            return False, "Message ID is required"

        # Validate constitutional hash if strict mode
        if self._strict:
            if message.constitutional_hash != self._constitutional_hash:
                return False, f"Constitutional hash mismatch: expected {self._constitutional_hash}"

        return True, None


class DynamicPolicyValidationStrategy:
    """Validates messages using a dynamic policy client.

    Retrieves current policies and validates signatures.
    Constitutional Hash: 608508a9bd224290
    """

    def __init__(self, policy_client: PolicyClientProtocol | None) -> None:
        """Initialize with policy client.

        Args:
            policy_client: Client implementing PolicyClientProtocol for
                          dynamic policy validation. Must have
                          validate_message_signature method.
        """
        self._policy_client = policy_client

    async def validate(self, message: AgentMessage) -> tuple[bool, str | None]:
        """Validate message signature against dynamic policy server."""
        if not self._policy_client:
            return False, "Policy client not available"

        return await self._validate_with_policy_client(message)

    @fail_closed(
        lambda self, message, *, error: self._handle_dynamic_policy_error(error),
        exceptions=_VALIDATION_OPERATION_ERRORS,
    )
    async def _validate_with_policy_client(self, message: AgentMessage) -> tuple[bool, str | None]:
        result = await self._policy_client.validate_message_signature(message)
        if not result.is_valid:
            return False, "; ".join(result.errors)
        return True, None

    def _handle_dynamic_policy_error(self, error: BaseException) -> tuple[bool, str | None]:
        logger.error(f"Dynamic policy validation error: {error}")
        return False, f"Dynamic validation error: {error!s}"


class OPAValidationStrategy:
    """Validates messages using OPA (Open Policy Agent).

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(self, opa_client: OPAClientProtocol | None) -> None:
        """Initialize with OPA client.

        Args:
            opa_client: Client implementing OPAClientProtocol for
                       OPA policy evaluation. Must have
                       validate_constitutional method.
        """
        self._opa_client = opa_client

    async def validate(self, message: AgentMessage) -> tuple[bool, str | None]:
        """Validate message against OPA constitutional policies."""
        if not self._opa_client:
            return False, "OPA client not available"

        return await self._validate_with_opa(message)

    @fail_closed(
        lambda self, message, *, error: self._handle_opa_validation_error(error),
        exceptions=_VALIDATION_OPERATION_ERRORS,
    )
    async def _validate_with_opa(self, message: AgentMessage) -> tuple[bool, str | None]:
        result = await self._opa_client.validate_constitutional(message.to_dict())
        if not result.is_valid:
            return False, "; ".join(result.errors)
        return True, None

    def _handle_opa_validation_error(self, error: BaseException) -> tuple[bool, str | None]:
        logger.error(f"OPA validation execution error: {error}")
        return False, f"OPA validation error: {error!s}"


class RustValidationStrategy:
    """High-performance validation using the Rust backend.

    Constitutional Hash: 608508a9bd224290

    SECURITY: This strategy implements fail-closed behavior by default.
    Validation only returns True when the Rust backend explicitly confirms
    the message is valid. Every error or unavailability results in rejection.
    """

    def __init__(
        self, rust_processor: RustProcessorProtocol | None, fail_closed: bool = True
    ) -> None:
        """Initialize with Rust processor.

        Args:
            rust_processor: Processor implementing RustProcessorProtocol
                           for high-performance validation. May have
                           validate_message, validate, or constitutional_validate
                           methods.
            fail_closed: If True, reject on any validation uncertainty (default: True)
        """
        self._rust_processor = rust_processor
        self._fail_closed = fail_closed
        self._constitutional_hash = CONSTITUTIONAL_HASH

    async def validate(self, message: AgentMessage) -> tuple[bool, str | None]:
        """Validate message using Rust backend.

        SECURITY: Implements fail-closed validation. Only returns True when
        the Rust backend explicitly confirms validation success.
        """
        if not self._rust_processor:
            return False, "Rust processor not available"

        return await self._validate_with_rust_processor(message)

    @fail_closed(
        lambda self, message, *, error: self._handle_rust_validation_error(error),
        exceptions=_VALIDATION_OPERATION_ERRORS,
    )
    async def _validate_with_rust_processor(
        self, message: AgentMessage
    ) -> tuple[bool, str | None]:
        # Attempt to use Rust processor's validation method
        # Check for validate_message method (preferred)
        if hasattr(self._rust_processor, "validate_message"):
            result = await self._rust_processor.validate_message(message.to_dict())
            if isinstance(result, bool):
                if result:
                    return True, None
                return False, "Rust validation rejected message"
            elif isinstance(result, dict):
                is_valid = result.get("is_valid", False)
                if is_valid:
                    return True, None
                error = result.get("error", "Rust validation failed")
                return False, error

        # Check for synchronous validate method
        if hasattr(self._rust_processor, "validate"):
            result = self._rust_processor.validate(message.to_dict())
            if isinstance(result, bool):
                if result:
                    return True, None
                return False, "Rust validation rejected message"
            elif isinstance(result, dict):
                is_valid = result.get("is_valid", False)
                if is_valid:
                    return True, None
                error = result.get("error", "Rust validation failed")
                return False, error

        # Check for constitutional_validate method
        if hasattr(self._rust_processor, "constitutional_validate"):
            result = self._rust_processor.constitutional_validate(
                message.constitutional_hash, self._constitutional_hash
            )
            if result:
                return True, None
            return False, "Constitutional hash validation failed in Rust backend"

        logger.warning(
            "RustValidationStrategy: No validation method found on Rust processor. "
            "Failing closed for security."
        )
        return False, "Rust processor has no validation method - fail closed"

    def _handle_rust_validation_error(self, error: BaseException) -> tuple[bool, str | None]:
        logger.error(f"Rust validation execution error: {error}")
        return False, f"Rust validation error: {error!s}"


class PQCValidationStrategy:
    """
    Post-Quantum Cryptographic Validation Strategy.

    Validates messages using NIST-approved post-quantum algorithms
    (CRYSTALS-Kyber and CRYSTALS-Dilithium) for quantum-resistant
    constitutional hash validation.

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(
        self, validator: PQCValidatorProtocol | None = None, hybrid_mode: bool = True
    ) -> None:
        """
        Initialize PQC validation strategy.

        Args:
            validator: Validator implementing PQCValidatorProtocol
                      (ConstitutionalHashValidator instance). If None,
                      attempts to create one from quantum_research module.
            hybrid_mode: Allow fallback to static hash if PQC fails
        """
        self._hybrid_mode = hybrid_mode
        self._constitutional_hash = CONSTITUTIONAL_HASH

        # Initialize PQC validator
        if validator is not None:
            self._validator = validator
        else:
            # Lazy import to avoid circular dependencies
            try:
                from quantum_research.post_quantum_crypto import (
                    ConstitutionalHashValidator,
                    PQCAlgorithm,
                    PQCSignature,
                )

                self._validator = ConstitutionalHashValidator()
                self._PQCSignature = PQCSignature
                self._PQCAlgorithm = PQCAlgorithm
            except ImportError:
                logger.warning("Post-quantum crypto not available, PQC validation disabled")
                self._validator = None
                self._PQCSignature = None
                self._PQCAlgorithm = None

    async def validate(self, message: AgentMessage) -> tuple[bool, str | None]:
        """
        Validate message using post-quantum cryptography.

        Algorithm:
        1. Check if message has PQC signature
        2. If PQC signature present, validate it
        3. If no PQC signature and hybrid mode enabled, fall back to static hash
        4. If no PQC signature and hybrid mode disabled, reject

        Returns:
            Tuple of (is_valid, error_message)
        """
        # If PQC validator is not available, fall back to static hash in hybrid mode
        if not self._validator:
            if self._hybrid_mode:
                # Fall back to static hash validation when PQC is unavailable
                if message.constitutional_hash != self._constitutional_hash:
                    return (
                        False,
                        f"Constitutional hash mismatch: expected {self._constitutional_hash}",
                    )
                return True, None
            return False, "PQC validator not available"

        # Check if message has PQC signature
        if not message.pqc_signature:
            if self._hybrid_mode:
                # Fall back to static hash validation
                if message.constitutional_hash != self._constitutional_hash:
                    return (
                        False,
                        f"Constitutional hash mismatch: expected {self._constitutional_hash}",
                    )
                return True, None
            else:
                return False, "PQC signature required but not provided"

        # Validate PQC signature
        try:
            # Convert base64 signature and public key back to bytes for validation
            # import base64  # Removed unused import

            signature_bytes = base64.b64decode(message.pqc_signature)

            # Create decision dict for validation
            decision = {
                "message_id": message.message_id,
                "content": message.content,
                "from_agent": message.from_agent,
                "tenant_id": message.tenant_id,
                "timestamp": message.created_at.isoformat(),
                "constitutional_hash": message.constitutional_hash,
            }

            # Parse public key (expecting base64 encoded bytes)
            if not message.pqc_public_key:
                return False, "PQC public key is required for signature verification"

            try:
                public_key_bytes = base64.b64decode(message.pqc_public_key)
            except (ValueError, TypeError) as e:
                # Try hex decoding as fallback
                try:
                    public_key_bytes = bytes.fromhex(message.pqc_public_key)
                except (ValueError, TypeError):
                    return False, f"Invalid PQC public key format: {e!s}"

            # Create PQCSignature object for validation
            if self._PQCSignature is None or self._PQCAlgorithm is None:
                return False, "PQC classes not available"

            signature_obj = self._PQCSignature(
                algorithm=self._PQCAlgorithm.DILITHIUM_3,
                signature=signature_bytes,
                message_hash=hashlib.sha3_256(str(decision).encode()).digest(),
                signer_key_id=f"pqc-{message.message_id[:16]}",
            )

            # Validate the signature
            is_valid = self._validator.verify_governance_decision(
                decision=decision, signature=signature_obj, public_key=public_key_bytes
            )

            if is_valid:
                return True, None
            else:
                return False, "PQC signature verification failed"

        except _VALIDATION_DATA_ERRORS as e:
            logger.error(f"PQC validation error: {e}")
            if self._hybrid_mode:
                # Fall back to static hash in case of PQC errors
                if message.constitutional_hash == self._constitutional_hash:
                    return True, None
            return False, f"PQC validation error: {e!s}"


class CompositeValidationStrategy:
    """
    Combines multiple validation strategies with intelligent orchestration.

    Features:
    - Runs all strategies and aggregates results
    - Prioritizes PQC validation when available
    - Falls back gracefully on validation failures
    - Supports hybrid classical/PQC modes

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(
        self, strategies: list[ValidationStrategy] | None = None, enable_pqc: bool = True
    ) -> None:
        """
        Initialize with list of validation strategies.

        Args:
            strategies: List of validation strategies implementing ValidationStrategy
                       protocol (must have async validate method)
            enable_pqc: Whether to automatically include PQC validation
        """
        self._strategies: list[ValidationStrategy] = strategies or []
        self._constitutional_hash = CONSTITUTIONAL_HASH
        self._enable_pqc = enable_pqc

        # Auto-include PQC validation if enabled and not already present
        if enable_pqc and not any(isinstance(s, PQCValidationStrategy) for s in self._strategies):
            try:
                pqc_strategy = PQCValidationStrategy(hybrid_mode=True)
                self._strategies.append(pqc_strategy)
                logger.info("PQC validation strategy auto-enabled in composite validation")
            except _VALIDATION_OPERATION_ERRORS as e:
                logger.warning(f"Failed to initialize PQC validation strategy: {e}")

    def add_strategy(self, strategy: ValidationStrategy) -> None:
        """Add a validation strategy.

        Args:
            strategy: Strategy implementing ValidationStrategy protocol
                     (must have async validate method returning tuple[bool, str | None])
        """
        self._strategies.append(strategy)

    async def validate(self, message: AgentMessage) -> tuple[bool, str | None]:
        """
        Run all validation strategies with intelligent orchestration.

        Algorithm:
        1. If PQC signature present, prioritize PQC validation
        2. Run all strategies and collect results
        3. Require ALL strategies to pass (fail-closed security)
        4. Aggregate error messages for debugging

        Returns:
            Tuple of (is_valid, error_message)
        """
        errors = []

        # Prioritize PQC validation if signature is present
        for strategy in self._strategies:
            if isinstance(strategy, PQCValidationStrategy) and message.pqc_signature:
                is_valid, error = await strategy.validate(message)
                if not is_valid:
                    errors.append(f"PQC: {error}")
                else:
                    pass
                continue

        # Run remaining strategies
        for strategy in self._strategies:
            if isinstance(strategy, PQCValidationStrategy) and message.pqc_signature:
                continue  # Already handled above

            is_valid, error = await strategy.validate(message)
            if not is_valid and error:
                strategy_name = strategy.__class__.__name__.replace("ValidationStrategy", "")
                errors.append(f"{strategy_name}: {error}")

        if errors:
            return False, "; ".join(errors)

        return True, None


class ConstitutionalValidationStrategy:
    """Validates messages using formal Z3-based constitutional verification.

    This strategy leverages the Breakthrough Verification layer to provide
    mathematical guarantees of policy compliance, supporting per-session
    overrides.

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(self, verifier: ConstitutionalVerifierProtocol | None) -> None:
        """Initialize with ConstitutionalVerifier instance.

        Args:
            verifier: Verifier implementing ConstitutionalVerifierProtocol
                     for Z3-based formal verification. Must have
                     verify_constitutional_compliance method.
        """
        self._verifier = verifier

    async def validate(self, message: AgentMessage) -> tuple[bool, str | None]:
        """Validate message against constitutional policies including session overrides."""
        if not self._verifier:
            return False, "Constitutional verifier not available"

        return await self._validate_with_constitutional_verifier(message)

    @fail_closed(
        lambda self, message, *, error: self._handle_constitutional_validation_error(error),
        exceptions=_VALIDATION_OPERATION_ERRORS,
    )
    async def _validate_with_constitutional_verifier(
        self, message: AgentMessage
    ) -> tuple[bool, str | None]:
        context = {
            "message_type": message.message_type.name,
            "priority": message.priority.name,
            "sender": message.from_agent,
            "tenant_id": message.tenant_id,
        }

        if isinstance(message.content, dict):
            context.update(
                {k: v for k, v in message.content.items() if isinstance(v, (int, bool, float))}  # type: ignore[misc]
            )

        result = await self._verifier.verify_constitutional_compliance(
            action_data=message.to_dict(),
            context=context,
            session_id=message.conversation_id,
        )

        if not result.is_valid:
            return False, f"Constitutional violation: {result.failure_reason}"

        return True, None

    def _handle_constitutional_validation_error(
        self, error: BaseException
    ) -> tuple[bool, str | None]:
        logger.error(f"Constitutional validation error: {error}")
        return False, f"Formal verification error: {error!s}"


__all__ = [
    "CompositeValidationStrategy",
    "ConstitutionalValidationStrategy",
    "DynamicPolicyValidationStrategy",
    "OPAValidationStrategy",
    "PQCValidationStrategy",
    "RustValidationStrategy",
    "StaticHashValidationStrategy",
]
