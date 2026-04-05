"""
ACGS-2 ML Governance Client
Constitutional Hash: 608508a9bd224290

Provides integration with the Adaptive Learning Engine for reporting governance
decision outcomes. Enables real-time model training through outcome feedback.
"""

import asyncio
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

import httpx

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

# Import configuration - try relative first, then absolute
try:
    from enhanced_agent_bus.exceptions import AgentBusError

    from ..config import BusConfiguration
except (ImportError, ValueError):
    try:
        from config import BusConfiguration  # type: ignore[import-untyped]
        from exceptions import AgentBusError  # type: ignore[import-untyped]
    except ImportError:
        try:
            from enhanced_agent_bus.config import BusConfiguration
            from enhanced_agent_bus.exceptions import AgentBusError
        except ImportError:
            # Fallback for standalone usage
            BusConfiguration = None  # type: ignore[assignment]
            AgentBusError = Exception  # type: ignore[assignment]

# Import constitutional hash
try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = os.environ.get("CONSTITUTIONAL_HASH", CONSTITUTIONAL_HASH)

logger = get_logger(__name__)
# =============================================================================
# Enums and Status Types
# =============================================================================


from ..circuit_breaker.enums import CircuitState


class OutcomeReportStatus(str, Enum):
    """Status of outcome report submission."""

    SUCCESS = "success"
    QUEUED = "queued"
    FAILED = "failed"
    CIRCUIT_OPEN = "circuit_open"
    TIMEOUT = "timeout"
    SERVICE_UNAVAILABLE = "service_unavailable"


# =============================================================================
# Exceptions
# =============================================================================


class MLGovernanceError(AgentBusError):
    """Base exception for ML Governance client errors."""

    def __init__(
        self,
        message: str,
        details: JSONDict | None = None,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
    ) -> None:
        if isinstance(AgentBusError, type) and AgentBusError is not Exception:
            super().__init__(message, details, constitutional_hash)
        else:
            super().__init__(message)
            self.message = message
            self.details = details or {}
            self.constitutional_hash = constitutional_hash


class MLGovernanceConnectionError(MLGovernanceError):
    """Raised when connection to Adaptive Learning Engine fails."""

    def __init__(self, url: str, reason: str) -> None:
        self.url = url
        self.reason = reason
        super().__init__(
            message=f"Failed to connect to Adaptive Learning Engine at '{url}': {reason}",
            details={"url": url, "reason": reason},
        )


class MLGovernanceTimeoutError(MLGovernanceError):
    """Raised when request to Adaptive Learning Engine times out."""

    def __init__(self, operation: str, timeout_seconds: float) -> None:
        self.operation = operation
        self.timeout_seconds = timeout_seconds
        super().__init__(
            message=f"Timeout during {operation} after {timeout_seconds}s",
            details={"operation": operation, "timeout_seconds": timeout_seconds},
        )


# =============================================================================
# Configuration
# =============================================================================


@dataclass
class MLGovernanceConfig:
    """Configuration for ML Governance client.

    Attributes:
        base_url: Base URL of the Adaptive Learning Engine
        timeout: Request timeout in seconds
        max_retries: Maximum number of retry attempts
        retry_delay: Initial delay between retries (exponential backoff)
        circuit_breaker_threshold: Failures before opening circuit
        circuit_breaker_reset: Seconds before trying again after circuit opens
        enable_async_queue: Whether to queue failed requests for retry
        max_queue_size: Maximum number of queued requests
        graceful_degradation: Whether to silently fail when service unavailable
    """

    base_url: str = field(
        default_factory=lambda: os.environ.get(
            "ADAPTIVE_LEARNING_URL", "http://adaptive-learning-engine:8001"
        )
    )
    timeout: float = 5.0
    max_retries: int = 3
    retry_delay: float = 0.5  # seconds, with exponential backoff
    circuit_breaker_threshold: int = 5
    circuit_breaker_reset: float = 30.0  # seconds
    enable_async_queue: bool = True
    max_queue_size: int = 1000
    graceful_degradation: bool = True
    constitutional_hash: str = field(default=CONSTITUTIONAL_HASH)

    @classmethod
    def from_environment(cls) -> "MLGovernanceConfig":
        """Create configuration from environment variables."""

        def _parse_float(value: str | None, default: float) -> float:
            if value is None:
                return default
            try:
                return float(value)
            except ValueError:
                return default

        def _parse_int(value: str | None, default: int) -> int:
            if value is None:
                return default
            try:
                return int(value)
            except ValueError:
                return default

        def _parse_bool(value: str | None, default: bool) -> bool:
            if value is None:
                return default
            return value.lower() in ("true", "1", "yes", "on")

        return cls(
            base_url=os.environ.get(
                "ADAPTIVE_LEARNING_URL", "http://adaptive-learning-engine:8001"
            ),
            timeout=_parse_float(os.environ.get("ML_GOVERNANCE_TIMEOUT"), 5.0),
            max_retries=_parse_int(os.environ.get("ML_GOVERNANCE_MAX_RETRIES"), 3),
            retry_delay=_parse_float(os.environ.get("ML_GOVERNANCE_RETRY_DELAY"), 0.5),
            circuit_breaker_threshold=_parse_int(
                os.environ.get("ML_GOVERNANCE_CIRCUIT_THRESHOLD"), 5
            ),
            circuit_breaker_reset=_parse_float(os.environ.get("ML_GOVERNANCE_CIRCUIT_RESET"), 30.0),
            enable_async_queue=_parse_bool(os.environ.get("ML_GOVERNANCE_ENABLE_QUEUE"), True),
            max_queue_size=_parse_int(os.environ.get("ML_GOVERNANCE_MAX_QUEUE_SIZE"), 1000),
            graceful_degradation=_parse_bool(
                os.environ.get("ML_GOVERNANCE_GRACEFUL_DEGRADATION"), True
            ),
            constitutional_hash=os.environ.get("CONSTITUTIONAL_HASH", CONSTITUTIONAL_HASH),
        )

    @classmethod
    def for_testing(cls) -> "MLGovernanceConfig":
        """Create configuration for unit testing."""
        return cls(
            base_url="http://localhost:8001",
            timeout=1.0,
            max_retries=1,
            retry_delay=0.1,
            circuit_breaker_threshold=2,
            circuit_breaker_reset=1.0,
            enable_async_queue=False,
            max_queue_size=10,
            graceful_degradation=True,
        )

    def to_dict(self) -> JSONDict:
        """Convert configuration to dictionary for logging."""
        return {
            "base_url": self.base_url,
            "timeout": self.timeout,
            "max_retries": self.max_retries,
            "retry_delay": self.retry_delay,
            "circuit_breaker_threshold": self.circuit_breaker_threshold,
            "circuit_breaker_reset": self.circuit_breaker_reset,
            "enable_async_queue": self.enable_async_queue,
            "max_queue_size": self.max_queue_size,
            "graceful_degradation": self.graceful_degradation,
        }


# =============================================================================
# Data Types
# =============================================================================


@dataclass
class OutcomeReport:
    """Represents a governance outcome report for training."""

    features: dict[str, float]
    label: int  # 0 or 1 for binary classification
    weight: float | None = None
    tenant_id: str | None = None
    prediction_id: str | None = None
    timestamp: float | None = None
    metadata: JSONDict = field(default_factory=dict)

    def to_request_dict(self) -> JSONDict:
        """Convert to request dictionary for API."""
        result: JSONDict = {
            "features": self.features,
            "label": self.label,
        }
        if self.weight is not None:
            result["sample_weight"] = self.weight
        if self.tenant_id:
            result["tenant_id"] = self.tenant_id
        if self.prediction_id:
            result["prediction_id"] = self.prediction_id
        if self.timestamp:
            result["timestamp"] = self.timestamp
        return result


@dataclass
class OutcomeResult:
    """Result of submitting an outcome report."""

    status: OutcomeReportStatus
    success: bool
    sample_count: int = 0
    current_accuracy: float = 0.0
    message: str = ""
    training_id: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    details: JSONDict = field(default_factory=dict)

    def to_dict(self) -> JSONDict:
        """Convert to dictionary for serialization."""
        return {
            "status": self.status.value,
            "success": self.success,
            "sample_count": self.sample_count,
            "current_accuracy": self.current_accuracy,
            "message": self.message,
            "training_id": self.training_id,
            "timestamp": self.timestamp,
            "details": self.details,
        }


# =============================================================================
# ML Governance Client
# =============================================================================


class MLGovernanceClient:
    """
    Client for the Adaptive Learning Engine service.

    Provides outcome reporting for governance decisions to enable
    real-time model training through feedback loops.

    Features:
    - Circuit breaker pattern for resilience
    - Retry logic with exponential backoff
    - Graceful degradation when service unavailable
    - Async queue for failed requests
    - Comprehensive error handling and logging

    Usage:
        async with MLGovernanceClient() as client:
            result = await client.report_outcome(
                features={"action": "deploy", "resource": "production"},
                label=1,  # Approved
            )
    """

    def __init__(
        self,
        config: MLGovernanceConfig | None = None,
        base_url: str | None = None,
    ):
        """Initialize ML Governance client.

        Args:
            config: Configuration object (takes precedence)
            base_url: Base URL for adaptive learning engine (if no config)
        """
        self.config = config or MLGovernanceConfig.from_environment()
        if base_url:
            self.config.base_url = base_url

        # Ensure base URL doesn't have trailing slash
        self.config.base_url = self.config.base_url.rstrip("/")

        # HTTP client (initialized on first use or via initialize())
        self._http_client: httpx.AsyncClient | None = None

        # Circuit breaker state
        self._circuit_state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float | None = None

        # Async queue for failed requests
        self._queue: list[OutcomeReport] = []

        # Callbacks for events
        self._on_success_callbacks: list[Callable[[OutcomeResult], None]] = []
        self._on_failure_callbacks: list[Callable[[str], None]] = []
        self._on_circuit_open_callbacks: list[Callable[[], None]] = []

    async def __aenter__(self) -> "MLGovernanceClient":
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()

    async def initialize(self) -> None:
        """Initialize HTTP client."""
        if not self._http_client:
            self._http_client = httpx.AsyncClient(
                timeout=self.config.timeout,
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
            )
            logger.info(f"ML Governance client initialized: {self.config.base_url}")

    async def close(self) -> None:
        """Close HTTP client and process remaining queue."""
        # Try to flush queue before closing
        if self._queue and self._http_client:
            await self._flush_queue()

        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
            logger.info("ML Governance client closed")

    # -------------------------------------------------------------------------
    # Circuit Breaker Logic
    # -------------------------------------------------------------------------

    def _check_circuit(self) -> bool:
        """Check if circuit allows requests.

        Returns:
            True if requests are allowed, False otherwise.
        """
        if self._circuit_state == CircuitState.CLOSED:
            return True

        if self._circuit_state == CircuitState.OPEN:
            # Check if enough time has passed to try again
            if self._last_failure_time is not None:
                elapsed = datetime.now(UTC).timestamp() - self._last_failure_time
                if elapsed >= self.config.circuit_breaker_reset:
                    logger.info("Circuit breaker: transitioning to half-open")
                    self._circuit_state = CircuitState.HALF_OPEN
                    return True
            return False

        # HALF_OPEN - allow one request to test
        return True

    def _record_success(self) -> None:
        """Record successful request."""
        if self._circuit_state == CircuitState.HALF_OPEN:
            logger.info("Circuit breaker: closing circuit (success in half-open)")
        self._circuit_state = CircuitState.CLOSED
        self._failure_count = 0

    def _record_failure(self) -> None:
        """Record failed request."""
        self._failure_count += 1
        self._last_failure_time = datetime.now(UTC).timestamp()

        if self._failure_count >= self.config.circuit_breaker_threshold:
            if self._circuit_state != CircuitState.OPEN:
                logger.warning(
                    f"Circuit breaker: opening circuit after {self._failure_count} failures"
                )
                self._circuit_state = CircuitState.OPEN
                for callback in self._on_circuit_open_callbacks:
                    try:
                        callback()
                    except (RuntimeError, TypeError, ValueError) as e:
                        logger.error(f"Circuit open callback error: {e}")

    # -------------------------------------------------------------------------
    # Outcome Reporting
    # -------------------------------------------------------------------------

    async def report_outcome(
        self,
        features: dict[str, float],
        label: int,
        weight: float | None = None,
        tenant_id: str | None = None,
        prediction_id: str | None = None,
        timestamp: float | None = None,
        metadata: JSONDict | None = None,
    ) -> OutcomeResult:
        """Report a governance decision outcome for model training.

        This endpoint follows the progressive validation paradigm:
        predict first, then learn from the outcome.

        Args:
            features: Feature dictionary with numeric values
            label: Target label (0 or 1) for binary classification
            weight: Optional sample weight (time-weighted learning)
            tenant_id: Optional tenant identifier for multi-tenant isolation
            prediction_id: Optional ID linking to a previous prediction
            timestamp: Optional timestamp of the original event
            metadata: Optional additional metadata

        Returns:
            OutcomeResult with status of the submission

        Example:
            result = await client.report_outcome(
                features={"action": 0.5, "resource": 1.0},
                label=1,  # Decision was approved
                prediction_id="pred-123",
            )
        """
        report = OutcomeReport(
            features=features,
            label=label,
            weight=weight,
            tenant_id=tenant_id,
            prediction_id=prediction_id,
            timestamp=timestamp,
            metadata=metadata or {},
        )

        return await self._submit_report(report)

    async def _submit_report(self, report: OutcomeReport) -> OutcomeResult:
        """Submit outcome report with retry logic."""
        # Check circuit breaker
        if not self._check_circuit():
            if self.config.enable_async_queue:
                return self._queue_report(report)
            return OutcomeResult(
                status=OutcomeReportStatus.CIRCUIT_OPEN,
                success=False,
                message="Circuit breaker is open - service temporarily unavailable",
            )

        # Ensure client is initialized
        if not self._http_client:
            await self.initialize()

        # Retry loop with exponential backoff
        last_error: Exception | None = None
        for attempt in range(self.config.max_retries):
            try:
                return await self._send_request(report)
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                last_error = e
                self._record_failure()

                if attempt < self.config.max_retries - 1:
                    delay = self.config.retry_delay * (2**attempt)
                    logger.warning(f"Attempt {attempt + 1} failed, retrying in {delay}s: {e}")
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"All {self.config.max_retries} attempts failed: {e}")
            except (
                AttributeError,
                OSError,
                RuntimeError,
                TypeError,
                ValueError,
            ) as e:
                last_error = e
                self._record_failure()
                logger.error(f"Unexpected error reporting outcome: {e}")
                break

        # All retries failed - handle graceful degradation
        if self.config.graceful_degradation:
            if self.config.enable_async_queue:
                return self._queue_report(report)
            for callback in self._on_failure_callbacks:
                try:
                    callback(str(last_error))
                except (RuntimeError, TypeError, ValueError) as e:
                    logger.error(f"Failure callback error: {e}")
            return OutcomeResult(
                status=OutcomeReportStatus.SERVICE_UNAVAILABLE,
                success=False,
                message=f"Service unavailable: {self._sanitize_error(last_error)}",
            )

        # Not graceful - raise exception
        if isinstance(last_error, httpx.TimeoutException):
            raise MLGovernanceTimeoutError("report_outcome", self.config.timeout)
        raise MLGovernanceConnectionError(self.config.base_url, self._sanitize_error(last_error))

    async def _send_request(self, report: OutcomeReport) -> OutcomeResult:
        """Send the actual HTTP request."""
        if not self._http_client:
            raise MLGovernanceConnectionError(self.config.base_url, "Client not initialized")

        url = f"{self.config.base_url}/api/v1/train"
        payload = report.to_request_dict()

        response = await self._http_client.post(url, json=payload)

        # Handle response
        if response.status_code == 202:
            # Accepted - async processing
            data = response.json()
            self._record_success()
            result = OutcomeResult(
                status=OutcomeReportStatus.SUCCESS,
                success=True,
                sample_count=data.get("sample_count", 0),
                current_accuracy=data.get("current_accuracy", 0.0),
                message=data.get("message", "Training sample accepted"),
                training_id=data.get("training_id"),
                details=data,
            )
            for callback in self._on_success_callbacks:
                try:
                    callback(result)
                except (RuntimeError, TypeError, ValueError) as e:
                    logger.error(f"Success callback error: {e}")
            return result
        elif response.status_code == 200:
            # Synchronous success
            data = response.json()
            self._record_success()
            result = OutcomeResult(
                status=OutcomeReportStatus.SUCCESS,
                success=data.get("success", True),
                sample_count=data.get("sample_count", 0),
                current_accuracy=data.get("current_accuracy", 0.0),
                message=data.get("message", "Training complete"),
                training_id=data.get("training_id"),
                details=data,
            )
            for callback in self._on_success_callbacks:
                try:
                    callback(result)
                except (RuntimeError, TypeError, ValueError) as e:
                    logger.error(f"Success callback error: {e}")
            return result
        elif response.status_code == 503:
            # Service unavailable
            self._record_failure()
            return OutcomeResult(
                status=OutcomeReportStatus.SERVICE_UNAVAILABLE,
                success=False,
                message="Adaptive Learning Engine is unavailable",
            )
        else:
            # Other error
            self._record_failure()
            error_detail = "Unknown error"
            try:
                error_data = response.json()
                error_detail = error_data.get("detail", str(response.status_code))
            except (ValueError, TypeError, AttributeError):
                error_detail = response.text[:200] if response.text else str(response.status_code)
            return OutcomeResult(
                status=OutcomeReportStatus.FAILED,
                success=False,
                message=f"Request failed: {error_detail}",
                details={"status_code": response.status_code},
            )

    def _queue_report(self, report: OutcomeReport) -> OutcomeResult:
        """Add report to async queue for later retry."""
        if len(self._queue) >= self.config.max_queue_size:
            # Queue full - drop oldest
            self._queue.pop(0)
            logger.warning("Outcome queue full - dropping oldest report")

        self._queue.append(report)
        logger.info(f"Outcome queued for retry (queue size: {len(self._queue)})")

        return OutcomeResult(
            status=OutcomeReportStatus.QUEUED,
            success=False,
            message=f"Request queued for retry (queue size: {len(self._queue)})",
        )

    async def _flush_queue(self) -> int:
        """Attempt to flush queued reports.

        Returns:
            Number of successfully sent reports.
        """
        if not self._queue:
            return 0

        success_count = 0
        remaining: list[OutcomeReport] = []

        for report in self._queue:
            if not self._check_circuit():
                remaining.append(report)
                continue

            try:
                result = await self._send_request(report)
                if result.success:
                    success_count += 1
                else:
                    remaining.append(report)
            except (
                AttributeError,
                OSError,
                RuntimeError,
                TypeError,
                ValueError,
            ) as e:
                logger.error(f"Failed to send queued report: {e}")
                remaining.append(report)

        self._queue = remaining
        if success_count > 0:
            logger.info(f"Flushed {success_count} queued outcomes")
        return success_count

    # -------------------------------------------------------------------------
    # Batch Reporting
    # -------------------------------------------------------------------------

    async def report_outcomes_batch(
        self,
        reports: list[OutcomeReport],
        async_processing: bool = True,
    ) -> list[OutcomeResult]:
        """Report multiple outcomes in a batch.

        Args:
            reports: List of outcome reports
            async_processing: Whether to process asynchronously

        Returns:
            List of results for each report
        """
        if not self._check_circuit():
            return [
                OutcomeResult(
                    status=OutcomeReportStatus.CIRCUIT_OPEN,
                    success=False,
                    message="Circuit breaker is open",
                )
                for _ in reports
            ]

        if not self._http_client:
            await self.initialize()

        url = f"{self.config.base_url}/api/v1/train/batch"
        payload = {
            "samples": [r.to_request_dict() for r in reports],
            "async_processing": async_processing,
        }

        try:
            response = await self._http_client.post(url, json=payload)  # type: ignore[union-attr]

            if response.status_code in (200, 202):
                data = response.json()
                self._record_success()
                # Return single result for batch
                accepted = data.get("accepted", len(reports))
                return [
                    OutcomeResult(
                        status=OutcomeReportStatus.SUCCESS,
                        success=True,
                        sample_count=data.get("sample_count", 0),
                        current_accuracy=data.get("current_accuracy", 0.0),
                        message=data.get("message", f"Batch accepted: {accepted}/{len(reports)}"),
                    )
                ] * len(reports)
            else:
                self._record_failure()
                return [
                    OutcomeResult(
                        status=OutcomeReportStatus.FAILED,
                        success=False,
                        message=f"Batch request failed: {response.status_code}",
                    )
                ] * len(reports)
        except (
            httpx.HTTPError,
            AttributeError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as e:
            self._record_failure()
            logger.error(f"Batch reporting error: {e}")
            return [
                OutcomeResult(
                    status=OutcomeReportStatus.FAILED,
                    success=False,
                    message=str(e),
                )
                for _ in reports
            ]

    # -------------------------------------------------------------------------
    # Health and Status
    # -------------------------------------------------------------------------

    async def health_check(self) -> JSONDict:
        """Check Adaptive Learning Engine health.

        Returns:
            Dictionary with health status and details.
        """
        if not self._http_client:
            await self.initialize()

        try:
            response = await self._http_client.get(  # type: ignore[union-attr]
                f"{self.config.base_url}/health",
                timeout=2.0,
            )
            if response.status_code == 200:
                data = response.json()
                return {
                    "status": "healthy",
                    "service": data.get("service", "adaptive-learning-engine"),
                    "model_status": data.get("model_status"),
                    "circuit_state": self._circuit_state.value,
                }
            return {
                "status": "unhealthy",
                "reason": f"HTTP {response.status_code}",
                "circuit_state": self._circuit_state.value,
            }
        except (
            httpx.HTTPError,
            AttributeError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as e:
            return {
                "status": "unhealthy",
                "reason": str(e),
                "circuit_state": self._circuit_state.value,
            }

    def get_stats(self) -> JSONDict:
        """Get client statistics.

        Returns:
            Dictionary with client stats.
        """
        return {
            "base_url": self.config.base_url,
            "circuit_state": self._circuit_state.value,
            "failure_count": self._failure_count,
            "queue_size": len(self._queue),
            "max_queue_size": self.config.max_queue_size,
            "graceful_degradation": self.config.graceful_degradation,
            "initialized": self._http_client is not None,
        }

    # -------------------------------------------------------------------------
    # Callbacks
    # -------------------------------------------------------------------------

    def on_success(self, callback: Callable[[OutcomeResult], None]) -> None:
        """Register callback for successful submissions."""
        self._on_success_callbacks.append(callback)

    def on_failure(self, callback: Callable[[str], None]) -> None:
        """Register callback for failed submissions."""
        self._on_failure_callbacks.append(callback)

    def on_circuit_open(self, callback: Callable[[], None]) -> None:
        """Register callback for circuit breaker opening."""
        self._on_circuit_open_callbacks.append(callback)

    # -------------------------------------------------------------------------
    # Utilities
    # -------------------------------------------------------------------------

    def _sanitize_error(self, error: Exception | None) -> str:
        """Strip sensitive metadata from error messages."""
        from enhanced_agent_bus._compat.security.error_sanitizer import sanitize_error

        return sanitize_error(error)  # type: ignore[no-any-return]

        # =============================================================================
        # Global Client Instance
        # =============================================================================

        _ml_governance_client: MLGovernanceClient | None = None


def get_ml_governance_client() -> MLGovernanceClient:
    """Get global ML Governance client instance."""
    global _ml_governance_client
    if _ml_governance_client is None:
        _ml_governance_client = MLGovernanceClient()
    return _ml_governance_client


async def initialize_ml_governance_client(
    config: MLGovernanceConfig | None = None,
    base_url: str | None = None,
) -> MLGovernanceClient:
    """Initialize global ML Governance client."""
    global _ml_governance_client
    _ml_governance_client = MLGovernanceClient(config=config, base_url=base_url)
    await _ml_governance_client.initialize()
    return _ml_governance_client


async def close_ml_governance_client() -> None:
    """Close global ML Governance client."""
    global _ml_governance_client
    if _ml_governance_client:
        await _ml_governance_client.close()
        _ml_governance_client = None

        # =============================================================================
        # Convenience Function
        # =============================================================================


async def report_outcome(
    features: dict[str, float],
    label: int,
    weight: float | None = None,
    tenant_id: str | None = None,
    prediction_id: str | None = None,
) -> OutcomeResult:
    """Convenience function for reporting governance outcomes.

    Uses the global client instance for one-off reports.

    Args:
        features: Feature dictionary with numeric values
        label: Target label (0 or 1)
        weight: Optional sample weight
        tenant_id: Optional tenant identifier
        prediction_id: Optional ID linking to prediction

    Returns:
        OutcomeResult with submission status
    """
    client = get_ml_governance_client()
    if not client._http_client:
        await client.initialize()
    return await client.report_outcome(
        features=features,
        label=label,
        weight=weight,
        tenant_id=tenant_id,
        prediction_id=prediction_id,
    )


# =============================================================================
# Export
# =============================================================================

__all__ = [
    # Enums
    "CircuitState",
    # Client
    "MLGovernanceClient",
    "MLGovernanceConfig",
    "MLGovernanceConnectionError",
    # Exceptions
    "MLGovernanceError",
    "MLGovernanceTimeoutError",
    # Data types
    "OutcomeReport",
    "OutcomeReportStatus",
    "OutcomeResult",
    "close_ml_governance_client",
    # Global instance functions
    "get_ml_governance_client",
    "initialize_ml_governance_client",
    # Convenience function
    "report_outcome",
]
