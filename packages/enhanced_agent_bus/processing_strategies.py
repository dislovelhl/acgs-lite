# pyright: reportMissingImports=false, reportAttributeAccessIssue=false, reportOptionalMemberAccess=false, reportAssignmentType=false, reportArgumentType=false, reportMissingTypeArgument=false
"""Processing strategies for the Enhanced Agent Bus message processing pipeline.

Constitutional Hash: 608508a9bd224290

This module provides a hierarchy of processing strategies that handle message
validation and execution within the Enhanced Agent Bus architecture. Each strategy
implements a consistent interface for processing AgentMessages through validation
and handler execution phases.

Strategy Types:
    - PythonProcessingStrategy: Pure Python processing with configurable validation.
    - RustProcessingStrategy: High-performance Rust-backed processing with circuit breaker.
    - CompositeProcessingStrategy: Chains multiple strategies with fail-fast semantics.
    - DynamicPolicyProcessingStrategy: Dynamic policy-based validation via policy client.
    - OPAProcessingStrategy: Open Policy Agent integration for policy evaluation.
    - MACIProcessingStrategy: MACI (Multi-Agent Constitutional Integrity) enforcement wrapper.

Example:
    Basic usage with Python strategy::

        from processing_strategies import PythonProcessingStrategy
        from validation_strategies import StaticHashValidationStrategy

        strategy = PythonProcessingStrategy(
            validation_strategy=StaticHashValidationStrategy(strict=True)
        )
        result = await strategy.process(message, handlers)

    Composite strategy with Rust fallback::

        composite = CompositeProcessingStrategy([
            RustProcessingStrategy(rust_processor=rp),
            PythonProcessingStrategy()
        ])
        result = await composite.process(message, handlers)
# pyright: reportMissingImports=false, reportAttributeAccessIssue=false, reportOptionalMemberAccess=false, reportArgumentType=false, reportAssignmentType=false
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from importlib import import_module
from threading import Lock
from typing import TYPE_CHECKING, Protocol, cast

from enhanced_agent_bus.observability.structured_logging import get_logger
from enhanced_agent_bus.plugin_registry import available, require
from enhanced_agent_bus.shared.fail_closed import fail_closed

if TYPE_CHECKING:
    from .validation_strategies import (
        DynamicPolicyValidationStrategy,
        OPAValidationStrategy,
        RustValidationStrategy,
        StaticHashValidationStrategy,
    )


class _StrategyLike(Protocol):
    async def process(
        self,
        msg: AgentMessage,
        handlers: dict[object, list[Callable[[AgentMessage], object]]],
    ) -> ValidationResult: ...

    def is_available(self) -> bool: ...

    def get_name(self) -> str: ...


try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

    from .models import AgentMessage, MessageStatus
    from .validation_strategies import (
        DynamicPolicyValidationStrategy,
        OPAValidationStrategy,
        RustValidationStrategy,
        StaticHashValidationStrategy,
    )
    from .validators import ValidationResult
except (ImportError, ValueError):
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

    from .models import (  # type: ignore[no-redef]
        AgentMessage,
        MessageStatus,
    )
    from .validation_strategies import (  # type: ignore[no-redef]
        DynamicPolicyValidationStrategy,
        OPAValidationStrategy,
        RustValidationStrategy,
        StaticHashValidationStrategy,
    )
    from .validators import ValidationResult  # type: ignore[no-redef]

logger = get_logger(__name__)
try:
    from .maci_imports import MACIError
except (ImportError, ValueError):
    MACIError = RuntimeError  # type: ignore[assignment,misc]

_PROCESSING_STRATEGY_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    asyncio.TimeoutError,
    MACIError,
)


class HandlerExecutorMixin:
    """Mixin providing common handler execution logic for processing strategies.

    This mixin encapsulates the pattern of executing registered message handlers
    for a given message type, managing message status transitions, and handling
    exceptions consistently across different processing strategies.
    """

    async def _execute_handlers(
        self,
        msg: AgentMessage,
        handlers: dict[object, list[Callable[[AgentMessage], object]]],
    ) -> ValidationResult:
        msg.status, msg.updated_at = MessageStatus.PROCESSING, datetime.now(UTC)
        try:
            for h in handlers.get(msg.message_type, []):
                if inspect.iscoroutinefunction(h):
                    await h(msg)
                else:
                    h(msg)
            msg.status, msg.updated_at = MessageStatus.DELIVERED, datetime.now(UTC)
            return ValidationResult(is_valid=True)
        except _PROCESSING_STRATEGY_ERRORS as e:
            msg.status = MessageStatus.FAILED
            # Standardize error message for regression tests
            error_type = type(e).__name__
            if error_type == "RuntimeError":
                err_msg = f"Runtime error: {e!s}"
            else:
                err_msg = f"{error_type}: {e!s}"
            logger.error(f"Handler error: {err_msg}")
            return ValidationResult(is_valid=False, errors=[err_msg])


class PythonProcessingStrategy(HandlerExecutorMixin):
    """Pure Python message processing strategy with configurable validation.

    This is the default processing strategy that provides reliable message
    processing using pure Python. It supports pluggable validation strategies
    and optional metrics collection.

    Attributes:
        _constitutional_hash: The constitutional hash for integrity verification.
        _metrics_enabled: Whether metrics collection is enabled.
        _validation_strategy: The validation strategy used for message validation.
    """

    def __init__(
        self,
        validation_strategy: (
            StaticHashValidationStrategy
            | DynamicPolicyValidationStrategy
            | OPAValidationStrategy
            | RustValidationStrategy
            | None
        ) = None,
        metrics_enabled: bool = False,
    ) -> None:
        """Initialize the Python processing strategy.

        Args:
            validation_strategy: The validation strategy to use for message
                validation. If None, defaults to StaticHashValidationStrategy
                with strict mode enabled.
            metrics_enabled: Whether to enable metrics collection for
                processing operations. Defaults to False.
        """
        self._constitutional_hash: str = CONSTITUTIONAL_HASH
        self._metrics_enabled: bool = metrics_enabled
        self._validation_strategy: (
            StaticHashValidationStrategy
            | DynamicPolicyValidationStrategy
            | OPAValidationStrategy
            | RustValidationStrategy
        ) = validation_strategy or StaticHashValidationStrategy(strict=True)

    async def process(
        self,
        msg: AgentMessage,
        handlers: dict[object, list[Callable[[AgentMessage], object]]],
    ) -> ValidationResult:
        """Process a message through validation and handler execution.

        Validates the message using the configured validation strategy, then
        executes all registered handlers for the message type. If validation
        fails, the message status is set to FAILED and processing stops.

        Args:
            msg: The agent message to process. Will be modified in-place to
                update status and timestamps.
            handlers: Dictionary mapping message types to lists of handler
                callables. Both sync and async handlers are supported.

        Returns:
            ValidationResult indicating success or failure with error details.

        Raises:
            No exceptions are raised; all errors are captured in the
            ValidationResult.errors list.
        """
        v: bool
        e: str | None
        v, e = await self._validation_strategy.validate(msg)
        if not v:
            msg.status = MessageStatus.FAILED
            return ValidationResult(is_valid=False, errors=[e] if e else [])

        if not hasattr(msg, "message_type") or msg.message_type is None:
            from .models import MessageType

            msg.message_type = MessageType.COMMAND

        return await self._execute_handlers(msg, handlers)

    def is_available(self) -> bool:
        """Check if this processing strategy is available for use.

        Returns:
            True always, as the Python strategy has no external dependencies.
        """
        return True

    def get_name(self) -> str:
        """Get the canonical name of this processing strategy.

        Returns:
            The string "python" identifying this strategy type.
        """
        return "python"


class RustProcessingStrategy(HandlerExecutorMixin):
    """High-performance Rust-backed message processing strategy.

    This strategy leverages a Rust processor for performance-critical validation
    and processing operations. It includes a circuit breaker pattern to handle
    Rust backend failures gracefully, automatically falling back when the Rust
    processor becomes unavailable.

    The circuit breaker trips after 3 consecutive failures and resets after
    5 consecutive successes.

    Attributes:
        _rp: The Rust processor instance.
        _rb: The Rust bus bindings for message conversion.
        _validation_strategy: The Rust validation strategy.
        _metrics_enabled: Whether metrics collection is enabled.
        _failure_count: Current consecutive failure count.
        _success_count: Current consecutive success count.
        _breaker_tripped: Whether the circuit breaker is currently tripped.
        _circuit_breaker_lock: Thread lock protecting circuit breaker state.
    """

    def __init__(
        self,
        rust_processor=None,
        rust_bus=None,
        validation_strategy=None,
        metrics_enabled: bool = False,
    ) -> None:
        """Initialize the Rust processing strategy.

        Args:
            rust_processor: The Rust processor instance providing validate and
                process methods. If None, the strategy will report as unavailable.
            rust_bus: The Rust bus bindings module containing AgentMessage,
                MessageType, Priority, and MessageStatus classes for conversion.
            validation_strategy: The validation strategy to use. If None,
                defaults to RustValidationStrategy wrapping the rust_processor.
            metrics_enabled: Whether to enable metrics collection for
                processing operations. Defaults to False.
        """
        self._rp = rust_processor
        self._rb = rust_bus
        self._validation_strategy = validation_strategy or RustValidationStrategy(rust_processor)
        self._metrics_enabled: bool = metrics_enabled
        self._failure_count: int = 0
        self._success_count: int = 0
        self._breaker_tripped: bool = False
        # LOCK-002: Protect circuit breaker state from race conditions
        # Using threading.Lock for compatibility with sync test calls
        self._circuit_breaker_lock: Lock = Lock()

    async def process(
        self,
        msg: AgentMessage,
        handlers: dict[object, list[Callable[[AgentMessage], object]]],
    ) -> ValidationResult:
        """Process a message using the Rust backend.

        Validates and processes the message through the Rust processor, then
        executes Python handlers on success. Updates circuit breaker state
        based on processing outcome.

        Args:
            msg: The agent message to process. Will be converted to Rust format
                and modified in-place to update status.
            handlers: Dictionary mapping message types to lists of handler
                callables. Handlers execute after successful Rust processing.

        Returns:
            ValidationResult indicating success or failure. On failure, errors
            contain details about validation or processing issues.

        Raises:
            No exceptions are raised; all errors are captured in the
            ValidationResult.errors list and logged.
        """
        if not self.is_available():
            return ValidationResult(is_valid=False, errors=["Rust not available"])
        try:
            v: bool
            e: str | None
            v, e = await self._validation_strategy.validate(msg)
            if not v:
                msg.status = MessageStatus.FAILED
                return ValidationResult(is_valid=False, errors=[e] if e else [])

            if self._rp is None or self._rb is None:
                msg.status = MessageStatus.FAILED
                return ValidationResult(is_valid=False, errors=["Rust backend not initialized"])

            res = (
                await self._rp.process(self._to_rust(msg))
                if inspect.iscoroutinefunction(self._rp.process)
                else self._rp.process(self._to_rust(msg))
            )
            if res.is_valid:
                self._record_success()
                h_res: ValidationResult = await self._execute_handlers(msg, handlers)
                if not h_res.is_valid:
                    return h_res
                msg.status = MessageStatus.DELIVERED
                return ValidationResult(is_valid=True)
            else:
                msg.status = MessageStatus.FAILED
                return ValidationResult(
                    is_valid=False, errors=list(res.errors) if hasattr(res, "errors") else []
                )
        except _PROCESSING_STRATEGY_ERRORS as exc:
            self._record_failure()
            logger.error(f"Rust execution failed: {exc}")
            return ValidationResult(is_valid=False, errors=[f"Rust processing error: {exc!s}"])

    async def process_bulk(self, messages: list[AgentMessage]) -> list[ValidationResult]:
        """Process a batch of messages using Rust SIMD-accelerated backend.

        Performs bulk cryptographic validation using SIMD operations for improved
        throughput. Messages are serialized to canonical JSON and validated in
        parallel. Falls back to serial processing if the bulk API is unavailable
        or fails.

        Args:
            messages: List of agent messages to process in batch. Each message
                should have content, headers with 'signature' and 'sender_key'.

        Returns:
            List of ValidationResult objects corresponding to each input message,
            in the same order. Each result indicates validation success/failure.

        Raises:
            No exceptions are raised; errors trigger fallback to serial
            processing and are logged.

        Note:
            This method does not execute handlers; it only performs validation.
            For full processing with handlers, use process() individually.
        """
        if self._rp is None or not self.is_available() or not hasattr(self._rp, "process_bulk"):
            # Fallback to serial
            fallback_results: list[ValidationResult] = []
            for m in messages:
                fallback_results.append(await self.process(m, {}))
            return fallback_results

        try:
            # Prepare bulk data structures
            # For simplicity, using the object-based bulk API first.
            # Ideally, we would flatten this for process_bulk_buffer.

            # Serialize for Rust
            # Optimization: We only need specific fields for crypto validation
            # Current Rust impl expects Vec<Vec<u8>> for messages

            # Convert messages to bytes (mocking serialization for now as we don't have full proto)
            # In prod, this would use the same serialization as the single message path

            # Since we can't easily access the raw bytes of the message content without
            # defined serialization, we'll serialize the content map to JSON bytes
            import json

            msgs_bytes: list[bytes] = []
            sigs_bytes: list[bytes] = []
            keys_bytes: list[bytes] = []

            for m in messages:
                # Extract content bytes (canonical JSON)
                content_str = json.dumps(m.content, sort_keys=True)
                msgs_bytes.append(content_str.encode("utf-8"))

                # Extract signature and key (mocking extraction from headers)
                # In real system: m.headers.get("X-Signature"), m.headers.get("X-Public-Key")
                sig: str = m.headers.get("signature", "")
                key: str = m.headers.get("sender_key", "")

                sigs_bytes.append(sig.encode("utf-8"))  # Should be raw bytes in real app
                keys_bytes.append(key.encode("utf-8"))  # Should be raw bytes in real app

            # Call Rust
            res_dict = await self._rp.process_bulk(msgs_bytes, sigs_bytes, keys_bytes)

            # Parse results
            import json

            validities: list[bool] = json.loads(res_dict["results"])

            results: list[ValidationResult] = []
            for is_valid in validities:
                if is_valid:
                    self._record_success()
                    results.append(ValidationResult(is_valid=True))
                else:
                    results.append(
                        ValidationResult(is_valid=False, errors=["Bulk validation failed"])
                    )

            return results

        except _PROCESSING_STRATEGY_ERRORS as e:
            self._record_failure()
            logger.error(f"Rust bulk execution failed: {e}")
            # Fallback to serial on failure
            error_results: list[ValidationResult] = []
            for m in messages:
                error_results.append(await self.process(m, {}))
            return error_results

    def _to_rust(self, msg: AgentMessage):
        if self._rb is None:
            raise RuntimeError("Rust bus bindings are not initialized")
        r = self._rb.AgentMessage()
        r.message_id = msg.message_id
        r.content = {k: str(v) for k, v in msg.content.items()}
        r.from_agent, r.to_agent = msg.from_agent, msg.to_agent
        if hasattr(self._rb, "MessageType"):
            r.message_type = getattr(
                self._rb.MessageType, msg.message_type.name.replace("_", ""), None
            )
        if hasattr(self._rb, "Priority"):
            r.priority = getattr(self._rb.Priority, msg.priority.name.capitalize(), None)
        elif hasattr(self._rb, "MessagePriority"):
            r.priority = getattr(self._rb.MessagePriority, msg.priority.name.capitalize(), None)
        if hasattr(self._rb, "MessageStatus"):
            r.status = getattr(self._rb.MessageStatus, msg.status.name.capitalize(), None)
        return r

    def _record_failure(self) -> None:
        with self._circuit_breaker_lock:
            self._failure_count += 1
            self._success_count = 0
            if self._failure_count >= 3:
                self._breaker_tripped = True

    def _record_success(self) -> None:
        with self._circuit_breaker_lock:
            self._success_count += 1
            if self._success_count >= 5:
                self._failure_count = 0
                self._breaker_tripped = False

    def is_available(self) -> bool:
        """Check if the Rust processing strategy is available for use.

        The strategy is unavailable if the Rust processor is None, the circuit
        breaker is tripped, or the processor lacks required validation methods.

        Returns:
            True if the Rust processor is available and circuit breaker is not
            tripped, False otherwise.
        """
        if self._rp is None or self._breaker_tripped:
            return False
        # Check if processor has required methods
        return hasattr(self._rp, "validate") or hasattr(self._rp, "validate_message")

    def get_name(self) -> str:
        """Get the canonical name of this processing strategy.

        Returns:
            The string "rust" identifying this strategy type.
        """
        return "rust"


class CompositeProcessingStrategy:
    """Composite strategy that chains multiple processing strategies.

    Attempts each strategy in order until one succeeds or returns an explicit
    validation failure. Implements fail-fast semantics: processing stops
    immediately on validation failures, but continues to the next strategy
    on exceptions.

    This enables patterns like Rust-with-Python-fallback where the high-performance
    Rust strategy is tried first, falling back to Python if Rust is unavailable.

    Attributes:
        _constitutional_hash: The constitutional hash for integrity verification.
        _strategies: Ordered list of processing strategies to attempt.
    """

    def __init__(self, strategies: list[_StrategyLike]) -> None:
        """Initialize the composite processing strategy.

        Args:
            strategies: Ordered list of processing strategies to attempt.
                Strategies are tried in order; the first available strategy
                that succeeds or explicitly fails is used.
        """
        self._constitutional_hash: str = CONSTITUTIONAL_HASH
        self._strategies: list[_StrategyLike] = strategies

    async def process(
        self,
        msg: AgentMessage,
        handlers: dict[object, list[Callable[[AgentMessage], object]]],
    ) -> ValidationResult:
        """Process a message through the strategy chain.

        Iterates through strategies in order, attempting processing with each
        available strategy. Returns immediately on success or explicit validation
        failure. Continues to next strategy on exceptions.

        Args:
            msg: The agent message to process.
            handlers: Dictionary mapping message types to handler callables.

        Returns:
            ValidationResult from the first strategy that completes (success or
            explicit failure). If all strategies fail with exceptions, returns
            a failure result containing all error messages.

        Raises:
            No exceptions are raised; all errors are captured in the
            ValidationResult.errors list.
        """
        errors: list[str] = []
        for strat in self._strategies:
            if not strat.is_available():
                continue
            try:
                res: ValidationResult = await strat.process(msg, handlers)
                if not res.is_valid:
                    return res  # FAIL FAST on invalidity
                return res  # Success
            except _PROCESSING_STRATEGY_ERRORS as e:
                err_str: str = f"{type(e).__name__}: {e!s}"
                errors.append(err_str)
                if hasattr(strat, "_record_failure"):
                    strat._record_failure()
        return ValidationResult(
            is_valid=False, errors=[f"All processing strategies failed: {errors}"]
        )

    def is_available(self) -> bool:
        """Check if any strategy in the composite is available.

        Returns:
            True if at least one contained strategy is available, False if all
            strategies are unavailable.
        """
        return any(s.is_available() for s in self._strategies)

    def get_name(self) -> str:
        """Get the canonical name of this composite strategy.

        Returns:
            A string in the format "composite(strategy1+strategy2+...)" showing
            all contained strategy names joined with '+'.
        """
        return f"composite({'+'.join(s.get_name() for s in self._strategies)})"


class DynamicPolicyProcessingStrategy(PythonProcessingStrategy):
    """Processing strategy with dynamic policy-based validation.

    Extends PythonProcessingStrategy to validate messages against dynamically
    loaded policies via a policy client. Useful for environments where validation
    rules need to be updated at runtime without code changes.

    Attributes:
        _policy_client: The policy client for dynamic policy evaluation.
    """

    def __init__(
        self,
        policy_client=None,
        validation_strategy=None,
        metrics_enabled: bool = False,
    ) -> None:
        """Initialize the dynamic policy processing strategy.

        Args:
            policy_client: Client for fetching and evaluating dynamic policies.
                If None, the strategy will report as unavailable.
            validation_strategy: The validation strategy to use. If None,
                defaults to DynamicPolicyValidationStrategy wrapping the
                policy_client.
            metrics_enabled: Whether to enable metrics collection. Defaults to False.
        """
        super().__init__(
            validation_strategy or DynamicPolicyValidationStrategy(policy_client), metrics_enabled
        )
        self._policy_client = policy_client

    async def process(
        self,
        msg: AgentMessage,
        handlers: dict[object, list[Callable[[AgentMessage], object]]],
    ) -> ValidationResult:
        """Process a message with dynamic policy validation.

        Delegates to the parent PythonProcessingStrategy but wraps any
        exceptions in a policy-specific error format.

        Args:
            msg: The agent message to process.
            handlers: Dictionary mapping message types to handler callables.

        Returns:
            ValidationResult indicating success or failure. Policy validation
            errors are prefixed with "Policy validation error:".

        Raises:
            No exceptions are raised; all errors are captured in the
            ValidationResult.errors list.
        """
        try:
            return await super().process(msg, handlers)
        except _PROCESSING_STRATEGY_ERRORS as e:
            msg.status = MessageStatus.FAILED
            return ValidationResult(is_valid=False, errors=[f"Policy validation error: {e!s}"])

    def is_available(self) -> bool:
        """Check if the dynamic policy strategy is available.

        Returns:
            True if the policy client is configured, False otherwise.
        """
        return self._policy_client is not None

    def get_name(self) -> str:
        """Get the canonical name of this processing strategy.

        Returns:
            The string "dynamic_policy" identifying this strategy type.
        """
        return "dynamic_policy"


class OPAProcessingStrategy(PythonProcessingStrategy):
    """Processing strategy using Open Policy Agent (OPA) for validation.

    Extends PythonProcessingStrategy to validate messages against OPA policies.
    OPA provides a declarative policy language (Rego) for expressing complex
    validation rules that can be managed independently of application code.

    Attributes:
        _opa_client: The OPA client for policy evaluation.
    """

    def __init__(
        self,
        opa_client=None,
        validation_strategy=None,
        metrics_enabled: bool = False,
    ) -> None:
        """Initialize the OPA processing strategy.

        Args:
            opa_client: Client for communicating with the OPA server or
                evaluating OPA policies locally. If None, the strategy will
                report as unavailable.
            validation_strategy: The validation strategy to use. If None,
                defaults to OPAValidationStrategy wrapping the opa_client.
            metrics_enabled: Whether to enable metrics collection. Defaults to False.
        """
        super().__init__(validation_strategy or OPAValidationStrategy(opa_client), metrics_enabled)
        self._opa_client = opa_client

    async def process(
        self,
        msg: AgentMessage,
        handlers: dict[object, list[Callable[[AgentMessage], object]]],
    ) -> ValidationResult:
        """Process a message with OPA policy validation.

        Delegates to the parent PythonProcessingStrategy but wraps any
        exceptions in an OPA-specific error format.

        Args:
            msg: The agent message to process.
            handlers: Dictionary mapping message types to handler callables.

        Returns:
            ValidationResult indicating success or failure. OPA validation
            errors are prefixed with "OPA validation error:".

        Raises:
            No exceptions are raised; all errors are captured in the
            ValidationResult.errors list.
        """
        try:
            return await super().process(msg, handlers)
        except _PROCESSING_STRATEGY_ERRORS as e:
            msg.status = MessageStatus.FAILED
            return ValidationResult(is_valid=False, errors=[f"OPA validation error: {e!s}"])

    def is_available(self) -> bool:
        """Check if the OPA strategy is available.

        Returns:
            True if the OPA client is configured, False otherwise.
        """
        return self._opa_client is not None

    def get_name(self) -> str:
        """Get the canonical name of this processing strategy.

        Returns:
            The string "opa" identifying this strategy type.
        """
        return "opa"


class MACIProcessingStrategy:
    """MACI (Multi-Agent Constitutional Integrity) enforcement wrapper strategy.

    Wraps an inner processing strategy with MACI role-based access control
    validation. MACI enforces constitutional constraints on agent interactions,
    ensuring messages comply with defined role permissions and capabilities.

    In strict mode (default), MACI violations block message processing.
    In non-strict mode, violations are logged but processing continues.

    Attributes:
        _constitutional_hash: The constitutional hash for integrity verification.
        _inner: The wrapped inner processing strategy.
        _registry: The MACI role registry for role definitions.
        _enforcer: The MACI enforcer for role validation.
        _strict: Whether strict mode is enabled.
        _maci_available: Whether MACI components are properly initialized.
        _maci_strategy: Reference to the MACI enforcer for validation.
    """

    def __init__(
        self,
        inner_strategy,
        maci_registry=None,
        maci_enforcer=None,
        strict_mode: bool = True,
    ) -> None:
        """Initialize the MACI processing strategy.

        Args:
            inner_strategy: The underlying processing strategy to wrap. This
                strategy handles actual message processing after MACI validation.
            maci_registry: The MACI role registry containing role definitions.
                If None, attempts to create a default MACIRoleRegistry.
            maci_enforcer: The MACI enforcer for validating role permissions.
                If None and maci_registry is available, creates a default
                MACIEnforcer with the provided strict_mode.
            strict_mode: If True, MACI violations fail processing immediately.
                If False, violations are logged but processing continues.
                Defaults to True.

        Note:
            VULN-001: MACI components are auto-initialized if not provided to
            prevent security bypass through misconfiguration.
        """
        self._constitutional_hash: str = CONSTITUTIONAL_HASH
        self._inner: _StrategyLike = inner_strategy

        # Initialize MACI components if not provided (VULN-001)
        if maci_registry is None and available("maci_enforcement"):
            try:
                maci_registry = import_module(require("maci_enforcement")).MACIRoleRegistry()
            except ValueError:
                pass

        if maci_enforcer is None and maci_registry is not None and available("maci_enforcement"):
            try:
                maci_enforcer = import_module(require("maci_enforcement")).MACIEnforcer(
                    registry=maci_registry, strict_mode=strict_mode
                )
            except ValueError:
                pass

        self._registry = maci_registry
        self._enforcer = maci_enforcer
        self._strict: bool = strict_mode
        self._maci_available: bool = maci_registry is not None and maci_enforcer is not None
        self._maci_strategy = self._build_maci_validator(maci_enforcer)

    @staticmethod
    def _build_maci_validator(maci_enforcer: object | None) -> object | None:
        """Normalize MACI enforcement onto a validator-style interface.

        Accepts either a validation strategy exposing ``validate(msg)`` or a raw
        enforcer exposing ``validate_action(...)``. Raw enforcers are wrapped in
        ``MACIValidationStrategy`` so the processing path always consumes one
        validation contract.
        """
        if maci_enforcer is None:
            return None

        validator = getattr(maci_enforcer, "validate", None)
        if callable(validator):
            return maci_enforcer

        validate_action = getattr(maci_enforcer, "validate_action", None)
        if callable(validate_action):
            try:
                if available("maci_strategy"):
                    return import_module(require("maci_strategy")).MACIValidationStrategy(
                        maci_enforcer
                    )
            except ValueError:
                return maci_enforcer

        return maci_enforcer

    async def _validate_message(self, msg: AgentMessage) -> tuple[bool, str | None]:
        """Run MACI validation and normalize the result."""
        if self._maci_strategy is None:
            raise RuntimeError("MACI validator unavailable")

        validator = getattr(self._maci_strategy, "validate", None)
        if callable(validator):
            maybe_result = validator(msg)
            if asyncio.iscoroutine(maybe_result):
                maybe_result = await cast(Awaitable[object], maybe_result)
            return self._coerce_validation_result(maybe_result)

        raise RuntimeError("MACI validator does not expose validate(msg)")

    @staticmethod
    def _coerce_validation_result(result: object) -> tuple[bool, str | None]:
        """Coerce supported MACI result shapes into ``(is_valid, error)``."""
        if isinstance(result, tuple) and len(result) == 2:
            valid = bool(result[0])
            error = result[1] if isinstance(result[1], str) else None
            return valid, error

        if hasattr(result, "is_valid"):
            valid = bool(result.is_valid)
            error_message = getattr(result, "error_message", None)
            violation_type = getattr(result, "violation_type", None)
            error = error_message or violation_type
            return valid, error if isinstance(error, str) else None

        raise TypeError("Unsupported MACI validation result contract")

    @property
    def registry(self):
        """Get the MACI role registry.

        Returns:
            The MACIRoleRegistry instance, or None if not configured.
        """
        return self._registry

    @property
    def enforcer(self):
        """Get the MACI enforcer.

        Returns:
            The MACIEnforcer instance, or None if not configured.
        """
        return self._enforcer

    async def process(
        self,
        msg: AgentMessage,
        handlers: dict[object, list[Callable[[AgentMessage], object]]],
    ) -> ValidationResult:
        """Process a message with MACI enforcement.

        First validates the message against MACI role permissions. If validation
        passes (or fails in non-strict mode), delegates to the inner strategy
        for actual processing.

        Args:
            msg: The agent message to process.
            handlers: Dictionary mapping message types to handler callables.

        Returns:
            ValidationResult indicating success or failure. MACI violations
            in strict mode return errors prefixed with "MACIRoleViolationError:".

        Raises:
            No exceptions are raised; all errors are captured in the
            ValidationResult.errors list.
        """
        if self._maci_available and self._maci_strategy:
            return await self._process_with_maci_validation(msg, handlers)

        return await self._inner.process(msg, handlers)

    @fail_closed(
        lambda self, msg, handlers, *, error: self._handle_maci_validation_error(error),
        exceptions=(Exception,),
    )
    async def _process_with_maci_validation(
        self,
        msg: AgentMessage,
        handlers: dict[object, list[Callable[[AgentMessage], object]]],
    ) -> ValidationResult:
        valid, error = await self._validate_message(msg)
        if not valid and self._strict:
            return ValidationResult(
                is_valid=False,
                errors=(
                    [f"MACIRoleViolationError: {error}"]
                    if error
                    else ["MACIRoleViolationError: MACI violation"]
                ),
            )
        return await self._inner.process(msg, handlers)

    def _handle_maci_validation_error(self, error: BaseException) -> ValidationResult:
        if self._strict:
            return ValidationResult(is_valid=False, errors=[f"{type(error).__name__}: {error!s}"])
        return ValidationResult(is_valid=True)

    def is_available(self) -> bool:
        """Check if the MACI strategy is available.

        The strategy is available if the inner strategy is available AND either
        strict mode is disabled OR MACI components are properly configured.

        Returns:
            True if the strategy can process messages, False otherwise.
        """
        return self._inner.is_available() and (not self._strict or self._maci_available)

    def get_name(self) -> str:
        """Get the canonical name of this processing strategy.

        Returns:
            A string in the format "maci(inner_strategy_name)" showing the
            MACI wrapper and its inner strategy.
        """
        return f"maci({self._inner.get_name()})"
