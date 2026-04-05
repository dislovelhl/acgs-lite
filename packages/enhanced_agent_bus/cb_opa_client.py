"""
ACGS-2 Enhanced Agent Bus - Circuit Breaker OPA Client
Constitutional Hash: 608508a9bd224290

OPA Client with circuit breaker protection implementing FAIL-CLOSED strategy.
When the circuit is open, all policy evaluations are DENIED.
Split from circuit_breaker_clients.py for improved maintainability.
"""

import hashlib
import json
import sys
import time
from datetime import UTC, datetime
from typing import Literal

# Import centralized constitutional hash
try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger
from enhanced_agent_bus.shared.fail_closed import fail_closed

# Import circuit breaker components
from .circuit_breaker import (
    ServiceCircuitBreaker,
    get_service_circuit_breaker,
)

logger = get_logger(__name__)
DEFAULT_CACHE_HASH_MODE = "sha256"
_CACHE_HASH_MODES = {"sha256", "fast"}
OPA_OPERATION_ERRORS = (
    AttributeError,
    ConnectionError,
    OSError,
    RuntimeError,
    TimeoutError,
    TypeError,
    ValueError,
)

try:
    from acgs2_perf import fast_hash

    FAST_HASH_AVAILABLE = True
except ImportError:
    FAST_HASH_AVAILABLE = False

_module = sys.modules[__name__]
sys.modules.setdefault("enhanced_agent_bus.cb_opa_client", _module)
sys.modules.setdefault("packages.enhanced_agent_bus.cb_opa_client", _module)


class CircuitBreakerOPAClient:
    """
    OPA Client with circuit breaker protection.

    Implements FAIL-CLOSED strategy for constitutional governance.
    When the circuit is open, all policy evaluations are DENIED.

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(
        self,
        opa_url: str = "http://localhost:8181",
        timeout: float = 5.0,
        cache_ttl: int = 300,
        enable_cache: bool = True,
        cache_hash_mode: Literal["sha256", "fast"] = DEFAULT_CACHE_HASH_MODE,
    ):
        if cache_hash_mode not in _CACHE_HASH_MODES:
            raise ValueError(f"Invalid cache_hash_mode: {cache_hash_mode}")
        self.opa_url = opa_url.rstrip("/")
        self.timeout = timeout
        self.cache_ttl = cache_ttl
        self.enable_cache = enable_cache
        self.cache_hash_mode = cache_hash_mode
        self.constitutional_hash = CONSTITUTIONAL_HASH

        self._http_client: object | None = None
        self._memory_cache: dict[str, JSONDict] = {}
        self._cache_timestamps: dict[str, float] = {}
        self._circuit_breaker: ServiceCircuitBreaker | None = None
        self._initialized = False
        if self.cache_hash_mode == "fast" and not FAST_HASH_AVAILABLE:
            logger.warning(
                "cache_hash_mode=fast requested but acgs2_perf.fast_hash unavailable; "
                "falling back to sha256"
            )

    async def initialize(self) -> None:
        """Initialize the OPA client with circuit breaker."""
        if self._initialized:
            return

        try:
            import httpx

            self._http_client = httpx.AsyncClient(
                timeout=self.timeout,
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
            )
        except ImportError:
            logger.error(f"[{CONSTITUTIONAL_HASH}] httpx not available for OPA client")
            raise

        # Get or create the circuit breaker for OPA
        self._circuit_breaker = await get_service_circuit_breaker("opa_evaluator")
        self._initialized = True

        logger.info(
            f"[{CONSTITUTIONAL_HASH}] Circuit-protected OPA client initialized "
            f"(url={self.opa_url}, fail_closed=True)"
        )

    async def close(self) -> None:
        """Close the OPA client."""
        if self._http_client:
            try:
                # Handle both real httpx clients and mocks
                close_coro = self._http_client.aclose()
                if hasattr(close_coro, "__await__"):
                    await close_coro
            except (TypeError, AttributeError):
                # Handle mocked clients that aren't awaitable
                pass
            finally:
                self._http_client = None
        self._initialized = False

    async def __aenter__(self) -> "CircuitBreakerOPAClient":
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Async context manager exit."""
        await self.close()

    def _get_cache_key(self, policy_path: str, input_data: JSONDict) -> str:
        """Generate cache key for policy evaluation."""
        input_str = json.dumps(input_data, sort_keys=True)
        if self.cache_hash_mode == "fast" and FAST_HASH_AVAILABLE:
            input_hash = f"{fast_hash(input_str):016x}"
        else:
            input_hash = hashlib.sha256(input_str.encode()).hexdigest()[:16]
        return f"opa_cb:{policy_path}:{input_hash}"

    def _get_from_cache(self, cache_key: str) -> JSONDict | None:
        """Get cached result if valid."""
        if not self.enable_cache or cache_key not in self._memory_cache:
            return None

        timestamp = self._cache_timestamps.get(cache_key, 0)
        if time.time() - timestamp > self.cache_ttl:
            del self._memory_cache[cache_key]
            del self._cache_timestamps[cache_key]
            return None

        return self._memory_cache[cache_key]

    def _set_cache(self, cache_key: str, result: JSONDict) -> None:
        """Cache a result."""
        if self.enable_cache:
            self._memory_cache[cache_key] = result
            self._cache_timestamps[cache_key] = time.time()

    async def evaluate_policy(
        self, input_data: JSONDict, policy_path: str = "data.acgs.allow"
    ) -> JSONDict:
        """
        Evaluate a policy with circuit breaker protection.

        FAIL-CLOSED: If circuit is open or evaluation fails, returns denied.

        Args:
            input_data: Input data for policy evaluation
            policy_path: OPA policy path to evaluate

        Returns:
            Policy evaluation result with allowed status
        """
        if not self._initialized:
            await self.initialize()

        # Check if circuit breaker allows execution
        if not await self._circuit_breaker.can_execute():
            # FAIL-CLOSED: Deny all requests when circuit is open
            await self._circuit_breaker.record_rejection()
            logger.warning(
                f"[{CONSTITUTIONAL_HASH}] OPA circuit breaker OPEN - DENYING request "
                f"(policy_path={policy_path})"
            )
            return {
                "result": False,
                "allowed": False,
                "reason": "OPA circuit breaker open - fail-closed mode",
                "metadata": {
                    "circuit_state": self._circuit_breaker.state.value,
                    "security": "fail-closed",
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                },
            }

        # Only consult cached policy decisions when the circuit is healthy enough
        # to execute. An open breaker must deny all requests, including cached allows.
        cache_key = self._get_cache_key(policy_path, input_data)
        cached = self._get_from_cache(cache_key)
        if cached is not None:
            return cached

        return await self._evaluate_policy_with_fail_closed(input_data, policy_path, cache_key)

    @fail_closed(
        lambda self, input_data, policy_path, cache_key, *, error: self._handle_evaluate_policy_error(error),
        exceptions=OPA_OPERATION_ERRORS,
    )
    async def _evaluate_policy_with_fail_closed(
        self, input_data: JSONDict, policy_path: str, cache_key: str
    ) -> JSONDict:
        result = await self._evaluate_http(input_data, policy_path)
        await self._circuit_breaker.record_success()
        self._set_cache(cache_key, result)
        return result

    async def _handle_evaluate_policy_error(self, error: BaseException) -> JSONDict:
        error_type = type(error).__name__
        await self._circuit_breaker.record_failure(error, error_type)
        logger.error(
            f"[{CONSTITUTIONAL_HASH}] OPA evaluation failed: {error} (error_type={error_type})"
        )
        return {
            "result": False,
            "allowed": False,
            "reason": f"OPA evaluation failed: {error}",
            "metadata": {
                "error_type": error_type,
                "security": "fail-closed",
                "constitutional_hash": CONSTITUTIONAL_HASH,
            },
        }

    async def _evaluate_http(self, input_data: JSONDict, policy_path: str) -> JSONDict:
        """Execute policy evaluation via HTTP."""

        path_parts = policy_path.replace("data.", "").replace(".", "/")
        url = f"{self.opa_url}/v1/data/{path_parts}"

        response = await self._http_client.post(url, json={"input": input_data})
        response.raise_for_status()

        data = response.json()
        opa_result = data.get("result", False)

        if isinstance(opa_result, bool):
            return {
                "result": opa_result,
                "allowed": opa_result,
                "reason": "Policy evaluated successfully",
                "metadata": {
                    "mode": "http",
                    "policy_path": policy_path,
                    "circuit_state": self._circuit_breaker.state.value,
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                },
            }
        elif isinstance(opa_result, dict):
            return {
                "result": opa_result,
                "allowed": opa_result.get("allow", False),
                "reason": opa_result.get("reason", "Success"),
                "metadata": {
                    "mode": "http",
                    "policy_path": policy_path,
                    "circuit_state": self._circuit_breaker.state.value,
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                    **opa_result.get("metadata", {}),
                },
            }
        else:
            return {
                "result": False,
                "allowed": False,
                "reason": f"Unexpected result type: {type(opa_result)}",
                "metadata": {
                    "mode": "http",
                    "policy_path": policy_path,
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                },
            }

    async def health_check(self) -> JSONDict:
        """Check OPA service health with circuit breaker status."""
        health = {
            "service": "opa_evaluator",
            "healthy": False,
            "circuit_state": "unknown",
            "fallback_strategy": "fail_closed",
            "constitutional_hash": CONSTITUTIONAL_HASH,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        if not self._initialized:
            health["error"] = "Client not initialized"
            return health

        if self._circuit_breaker:
            health["circuit_state"] = self._circuit_breaker.state.value
            health["circuit_metrics"] = self._circuit_breaker.metrics.__dict__

        return await self._populate_health(health)

    @fail_closed(
        lambda self, health, *, error: self._handle_health_check_error(health, error),
        exceptions=OPA_OPERATION_ERRORS,
    )
    async def _populate_health(self, health: JSONDict) -> JSONDict:
        response = await self._http_client.get(f"{self.opa_url}/health", timeout=2.0)
        response.raise_for_status()
        health["healthy"] = True
        health["opa_status"] = "healthy"
        return health

    def _handle_health_check_error(self, health: JSONDict, error: BaseException) -> JSONDict:
        health["error"] = str(error)
        health["opa_status"] = "unhealthy"
        return health

    def get_circuit_status(self) -> JSONDict:
        """Get circuit breaker status."""
        if not self._circuit_breaker:
            return {"error": "Circuit breaker not initialized"}
        return self._circuit_breaker.get_status()


__all__ = [
    "CircuitBreakerOPAClient",
]
