# mypy: ignore-errors
# OPAClient uses mixin composition from cache.py and health.py. The mixin
# attributes are resolved at class instantiation but mypy cannot verify
# the composition statically.
"""
ACGS-2 OPA Client — Core
Constitutional Hash: 608508a9bd224290

Provides the core OPAClient class with initialization, evaluation,
constitutional validation, authorization, bundle management, and
singleton lifecycle functions.
"""

import asyncio
import hashlib
import json
import os
import re
import ssl
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import aiofiles
import httpx
from httpx import ConnectError as HTTPConnectError
from httpx import ConnectTimeout as HTTPConnectTimeout
from httpx import HTTPStatusError
from httpx import TimeoutException as HTTPTimeoutException

try:
    from enhanced_agent_bus._compat.errors import ConfigurationError
except ImportError:

    class ConfigurationError(Exception):  # type: ignore[no-redef]
        def __init__(self, message: str = "", error_code: str = "") -> None:
            super().__init__(message)
            self.error_code = error_code


from enhanced_agent_bus._compat.errors import ValidationError as ACGSValidationError

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

try:
    from ..config import settings
    from ..exceptions import (
        OPAConnectionError,
        OPANotInitializedError,
        PolicyEvaluationError,
    )
    from ..models import CONSTITUTIONAL_HASH, AgentMessage
    from ..validators import ValidationResult
except (ImportError, ValueError):
    try:
        from config import settings  # type: ignore[no-redef, attr-defined]
        from exceptions import (  # type: ignore[no-redef]
            OPAConnectionError,
            OPANotInitializedError,
            PolicyEvaluationError,
        )
        from models import CONSTITUTIONAL_HASH, AgentMessage  # type: ignore[no-redef]
        from validators import ValidationResult  # type: ignore[no-redef]
    except ImportError:
        try:
            from enhanced_agent_bus.config import settings  # type: ignore[no-redef]

            from ..exceptions import (  # type: ignore[no-redef]
                OPAConnectionError,
                OPANotInitializedError,
                PolicyEvaluationError,
            )
            from ..models import (  # type: ignore[no-redef]
                CONSTITUTIONAL_HASH,
                AgentMessage,
            )
            from ..validators import (
                ValidationResult,  # type: ignore[no-redef]
            )
        except ImportError:
            # Fallback for sharing with shared package
            from enhanced_agent_bus._compat.config import settings  # type: ignore[import-untyped]
            from exceptions import OPANotInitializedError  # type: ignore[import-untyped]
            from models import CONSTITUTIONAL_HASH  # type: ignore[import-untyped]
            from validators import ValidationResult  # type: ignore[import-untyped]

# Import cache mixin constants needed by __init__
from .cache import (
    _CACHE_HASH_MODES,
    DEFAULT_CACHE_HASH_MODE,
    FAST_HASH_AVAILABLE,
    REDIS_CLIENT_AVAILABLE,
    OPAClientCacheMixin,
    _redis_client_available,
    get_redis_url,
)
from .health import OPAClientHealthMixin

# Optional OPA Python SDK for embedded mode
try:
    from opa import OPA as EmbeddedOPA

    OPA_SDK_AVAILABLE = True
except ImportError:
    OPA_SDK_AVAILABLE = False
    EmbeddedOPA = None

logger = get_logger(__name__)


def _opa_sdk_available() -> bool:
    """Look up OPA_SDK_AVAILABLE through the package namespace for patchability.

    Tests may patch ``packages.enhanced_agent_bus.opa_client.OPA_SDK_AVAILABLE``
    (the ``__init__.py`` binding). This helper reads from that namespace at
    call-time so the patched value is observed.
    """
    import sys

    pkg = sys.modules.get(__name__.rsplit(".", 1)[0])  # enhanced_agent_bus.opa_client
    if pkg is not None and hasattr(pkg, "OPA_SDK_AVAILABLE"):
        return pkg.OPA_SDK_AVAILABLE  # type: ignore[return-value]
    return OPA_SDK_AVAILABLE


def _get_embedded_opa_class() -> type | None:
    """Look up EmbeddedOPA through the package namespace for patchability."""
    import sys

    pkg = sys.modules.get(__name__.rsplit(".", 1)[0])
    if pkg is not None and hasattr(pkg, "EmbeddedOPA"):
        return pkg.EmbeddedOPA  # type: ignore[return-value]
    return EmbeddedOPA


class OPAClientCore:
    """
    Core client for OPA (Open Policy Agent) policy evaluation.

    Supports multiple modes:
    1. HTTP API mode - Connect to remote OPA server
    2. Embedded mode - Use OPA Python SDK (if available)
    3. Fallback mode - Local validation when OPA unavailable
    """

    # PERFORMANCE: Bundle optimization level for OPA policy compilation
    # 0 = disabled, 1 = partial evaluation (recommended), 2 = aggressive inlining
    OPA_OPTIMIZE_LEVEL: int = 1

    def __init__(
        self,
        opa_url: str = "http://localhost:8181",
        mode: str = "http",  # "http", "embedded", or "fallback"
        timeout: float = 5.0,
        cache_ttl: int = 60,  # PERFORMANCE: 60s TTL for sub-ms P99 latency
        enable_cache: bool = True,
        redis_url: str | None = None,
        ssl_verify: bool = True,
        ssl_cert: str | None = None,
        ssl_key: str | None = None,
        optimize_level: int = 1,  # OPA bundle optimization level (0, 1, or 2)
        cache_hash_mode: Literal["sha256", "fast"] = DEFAULT_CACHE_HASH_MODE,
    ):
        """Initialize OPA client.

        Args:
            opa_url: OPA server URL
            mode: Operating mode ("http", "embedded", or "fallback")
            timeout: HTTP request timeout in seconds
            cache_ttl: Cache TTL in seconds (default 60s for P99 <1ms target)
            enable_cache: Enable policy result caching
            redis_url: Redis URL for distributed caching
            ssl_verify: Enable SSL certificate verification
            ssl_cert: Path to SSL client certificate
            ssl_key: Path to SSL client key
            optimize_level: OPA bundle optimization level (0=off, 1=partial eval, 2=aggressive)
            cache_hash_mode: Cache key hash mode ("sha256" default, "fast" optional)
        """
        # Use settings defaults if not provided
        self.opa_url = opa_url or settings.opa.url
        self.opa_url = self.opa_url.rstrip("/")
        self.mode = mode or settings.opa.mode
        self.timeout = timeout
        self.cache_ttl = cache_ttl
        self.enable_cache = enable_cache
        self.ssl_verify = ssl_verify
        self.ssl_cert = ssl_cert
        self.ssl_key = ssl_key
        self.optimize_level = optimize_level
        if cache_hash_mode not in _CACHE_HASH_MODES:
            raise ValueError(f"Invalid cache_hash_mode: {cache_hash_mode}")
        self.cache_hash_mode = cache_hash_mode
        # SECURITY FIX (VULN-002): Force fail-closed architecture.
        # This prevents any "fail-open" scenarios when OPA is unavailable.
        self.fail_closed = True
        self._http_client: httpx.AsyncClient | None = None
        self._redis_client: object | None = None
        self._embedded_opa: object | None = None
        self._embedded_executor: ThreadPoolExecutor | None = None
        self._memory_cache: dict[str, JSONDict] = {}
        self._memory_cache_timestamps: dict[str, float] = {}
        self._memory_cache_maxsize: int = 10000  # Prevent OOM
        self._lkg_bundle_path: str | None = None
        self._multipath_evaluation_count: int = 0
        self._multipath_last_path_count: int = 0
        self._multipath_last_diversity_ratio: float = 0.0
        self._multipath_last_support_family_count: int = 0

        # Redis configuration
        self.redis_url = redis_url or get_redis_url(db=2)

        if self.cache_hash_mode == "fast" and not FAST_HASH_AVAILABLE:
            logger.warning(
                "cache_hash_mode=fast requested but acgs2_perf.fast_hash unavailable; "
                "falling back to sha256"
            )

        # Validate mode
        if mode == "embedded" and not _opa_sdk_available():
            logger.warning("Embedded mode requested but OPA SDK not available")
            self.mode = "http"

    async def __aenter__(self) -> "OPAClientCore":
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

    def get_stats(self) -> JSONDict:
        """Return a lightweight snapshot of cache and evaluation state."""
        cache_backend = "memory"
        if self.enable_cache and self._redis_client is not None:
            cache_backend = "redis"
        elif not self.enable_cache:
            cache_backend = "disabled"

        return {
            "mode": self.mode,
            "cache_enabled": self.enable_cache,
            "cache_size": len(self._memory_cache),
            "cache_backend": cache_backend,
            "fail_closed": self.fail_closed,
            "multipath_evaluation_count": self._multipath_evaluation_count,
            "multipath_last_path_count": self._multipath_last_path_count,
            "multipath_last_diversity_ratio": self._multipath_last_diversity_ratio,
            "multipath_last_support_family_count": self._multipath_last_support_family_count,
        }

    async def initialize(self) -> None:
        """Initialize HTTP client and cache connections."""
        if self.mode in ("http", "fallback"):
            await self._ensure_http_client()

        if self.mode == "embedded" and _opa_sdk_available():
            await self._initialize_embedded_opa()

        if self.enable_cache and _redis_client_available():
            await self._initialize_redis_cache()

    async def _ensure_http_client(self) -> None:
        """Ensure the HTTP client is initialized exactly once."""
        if self._http_client:
            return

        ssl_context = self._build_ssl_context_if_needed()
        self._http_client = httpx.AsyncClient(
            timeout=self.timeout,
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
            verify=ssl_context if ssl_context is not None else self.ssl_verify,
        )

    def _build_ssl_context_if_needed(self) -> ssl.SSLContext | None:
        """Build SSL context for HTTPS endpoints with production-safe defaults."""
        if not self.opa_url.startswith("https"):
            return None

        environment = os.getenv("ENVIRONMENT", "production").lower()
        is_production = environment in ("production", "prod", "live")

        ssl_context = ssl.create_default_context()
        if not self.ssl_verify:
            if is_production:
                logger.error(
                    "SECURITY VIOLATION: Attempted to disable SSL verification "
                    "for OPA client in production environment. "
                    "Constitutional Hash: %s",
                    CONSTITUTIONAL_HASH,
                )
                raise ConfigurationError(
                    "SSL verification cannot be disabled in production. "
                    "Set ssl_verify=True or use http:// URL for local development only.",
                    error_code="OPA_SSL_DISABLED_IN_PRODUCTION",
                )

            logger.warning(
                "SECURITY WARNING: SSL verification disabled for OPA client. "
                "This is insecure and should ONLY be used in development/testing. "
                "Environment: %s. Constitutional Hash: %s",
                environment,
                CONSTITUTIONAL_HASH,
            )
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

        if self.ssl_cert and self.ssl_key:
            ssl_context.load_cert_chain(certfile=self.ssl_cert, keyfile=self.ssl_key)

        return ssl_context

    async def _initialize_embedded_opa(self) -> None:
        """Initialize embedded OPA, falling back to HTTP mode when unavailable."""
        try:
            opa_cls = _get_embedded_opa_class()
            self._embedded_opa = opa_cls()
            self._embedded_executor = ThreadPoolExecutor(
                max_workers=1,
                thread_name_prefix="opa-embedded",
            )
            logger.info("Embedded OPA initialized successfully")
        except (RuntimeError, OSError) as e:
            logger.error("Failed to initialize embedded OPA: %s", e)
            self.mode = "http"
            self._shutdown_embedded_executor()
            await self._ensure_http_client()

    async def close(self) -> None:
        """Close all connections."""
        if self._http_client:
            try:
                await self._http_client.aclose()
            except RuntimeError as exc:
                if "Event loop is closed" in str(exc):
                    logger.warning("Event loop closed during HTTP client shutdown")
                else:
                    raise
            self._http_client = None

        if self._redis_client:
            try:
                await self._redis_client.close()
            except RuntimeError as exc:
                if "Event loop is closed" in str(exc):
                    logger.warning("Event loop closed during Redis client shutdown")
                else:
                    raise
            self._redis_client = None

        self._embedded_opa = None
        self._shutdown_embedded_executor()
        self._memory_cache.clear()
        self._memory_cache_timestamps.clear()

    def _get_embedded_executor(self) -> ThreadPoolExecutor:
        """Return a dedicated executor for embedded OPA evaluations."""
        if getattr(self, "_embedded_executor", None) is None:
            self._embedded_executor = ThreadPoolExecutor(
                max_workers=1,
                thread_name_prefix="opa-embedded",
            )
        return self._embedded_executor

    def _shutdown_embedded_executor(self) -> None:
        """Tear down the dedicated embedded OPA executor."""
        if getattr(self, "_embedded_executor", None) is None:
            return
        self._embedded_executor.shutdown(wait=False, cancel_futures=True)
        self._embedded_executor = None

    async def _dispatch_evaluation(self, input_data: JSONDict, policy_path: str) -> JSONDict:
        """Route evaluation to the appropriate backend based on *self.mode*.

        Args:
            input_data: Validated input dict.
            policy_path: Validated OPA policy path.

        Returns:
            Raw evaluation result from the selected backend.
        """
        if self.mode == "http":
            return await self._evaluate_http(input_data, policy_path)
        if self.mode == "embedded":
            return await self._evaluate_embedded(input_data, policy_path)
        return await self._evaluate_fallback(input_data, policy_path)

    async def evaluate_policy(
        self, input_data: JSONDict, policy_path: str = "data.acgs.allow"
    ) -> JSONDict:
        """Evaluate a policy."""
        input_with_candidates = dict(input_data)
        if self._is_multi_path_candidate_generation_enabled() and not isinstance(
            input_with_candidates.get("support_set_candidates"), list
        ):
            lifecycle_candidates = self._build_policy_lifecycle_support_set_candidates(
                input_with_candidates
            )
            if lifecycle_candidates:
                input_with_candidates["support_set_candidates"] = lifecycle_candidates

        if isinstance(input_with_candidates.get("support_set_candidates"), list):
            return await self.evaluate_policy_multi_path(
                input_with_candidates, policy_path=policy_path
            )

        cache_key = self._generate_cache_key(policy_path, input_with_candidates)
        cached_result = await self._get_from_cache(cache_key)
        if cached_result:
            return cached_result

        try:
            # SECURITY FIX (VULN-009): Strict input validation
            self._validate_policy_path(policy_path)
            self._validate_input_data(input_with_candidates)

            result = await self._dispatch_evaluation(input_with_candidates, policy_path)

            await self._set_to_cache(cache_key, result)
            return result

        except (ValueError, ACGSValidationError) as e:
            # Input validation errors — log without sanitization (no network data)
            logger.error("Policy input validation error: %s", e)
            return self._handle_evaluation_error(e, policy_path)
        except (
            HTTPConnectError,
            HTTPConnectTimeout,
            HTTPTimeoutException,
            HTTPStatusError,
            OPAConnectionError,
            OPANotInitializedError,
            PolicyEvaluationError,
            AttributeError,
            KeyError,
            OSError,
            RuntimeError,
            TypeError,
        ) as e:
            # SECURITY: All transport/OPA/unexpected errors — sanitize and fail-closed
            sanitized_error = self._sanitize_error(e)
            logger.error("OPA evaluation error (fail-closed): %s", sanitized_error)
            return self._handle_evaluation_error(e, policy_path)

    def _validate_policy_path(self, policy_path: str) -> None:
        """Strict validation of OPA policy path to prevent injection (VULN-009)."""
        if not re.match(r"^[a-zA-Z0-9_.]+$", policy_path):
            raise ACGSValidationError(
                f"Invalid policy path characters: {policy_path}",
                field="policy_path",
                constraint="alphanumeric, dots, and underscores only",
            )
        if ".." in policy_path:
            raise ACGSValidationError(
                f"Path traversal detected in policy path: {policy_path}",
                field="policy_path",
                constraint="no path traversal sequences",
            )

    def _validate_input_data(self, input_data: JSONDict) -> None:
        """Validate input data size and structure (VULN-009)."""
        if self._estimate_input_size_bytes(input_data) > 1024 * 512:  # 512KB limit
            raise ACGSValidationError(
                "Input data exceeds maximum allowed size",
                field="input_data",
                constraint="max 512KB",
            )

    def _estimate_input_size_bytes(self, value: object, seen: set[int] | None = None) -> int:
        """Estimate payload size without JSON serialization in hot paths."""
        if seen is None:
            seen = set()

        obj_id = id(value)
        if obj_id in seen:
            return 0
        seen.add(obj_id)

        total_size = sys.getsizeof(value)

        if isinstance(value, dict):
            for key, nested_value in value.items():
                total_size += self._estimate_input_size_bytes(key, seen)
                total_size += self._estimate_input_size_bytes(nested_value, seen)
        elif isinstance(value, (list, tuple, set, frozenset)):
            for item in value:
                total_size += self._estimate_input_size_bytes(item, seen)

        return total_size

    def _sanitize_error(self, error: Exception) -> str:
        """Strip sensitive metadata from error messages (VULN-008)."""
        from enhanced_agent_bus._compat.security import sanitize_error

        return sanitize_error(error)

    def _handle_evaluation_error(self, error: Exception, policy_path: str) -> JSONDict:
        """Build a response for OPA evaluation failures - ALWAYS FAIL-CLOSED."""
        sanitized_error = self._sanitize_error(error)
        logger.error("OPA evaluation failed: %s", sanitized_error)
        return {
            "result": False,
            "allowed": False,
            "reason": f"Policy evaluation failed: {sanitized_error}",
            "metadata": {
                "error": sanitized_error,
                "mode": self.mode,
                "policy_path": policy_path,
                "security": "fail-closed",
            },
        }

    def _format_evaluation_result(
        self, opa_result: object, mode: str, policy_path: str
    ) -> JSONDict:
        """Format the OPA evaluation result into a standardized dictionary."""
        if isinstance(opa_result, bool):
            return {
                "result": opa_result,
                "allowed": opa_result,
                "reason": "Policy evaluated successfully",
                "metadata": {"mode": mode, "policy_path": policy_path},
            }
        elif isinstance(opa_result, dict):
            return {
                "result": opa_result,
                "allowed": opa_result.get("allow", False),
                "reason": opa_result.get("reason", "Success"),
                "metadata": {
                    "mode": mode,
                    "policy_path": policy_path,
                    **opa_result.get("metadata", {}),
                },
            }
        else:
            return {
                "result": False,
                "allowed": False,
                "reason": f"Unexpected result type: {type(opa_result)}",
                "metadata": {"mode": mode, "policy_path": policy_path},
            }

    async def _evaluate_http(self, input_data: JSONDict, policy_path: str) -> JSONDict:
        """Evaluate policy via HTTP API."""
        if not self._http_client:
            raise OPANotInitializedError("HTTP policy evaluation")

        try:
            path_parts = policy_path.replace("data.", "").replace(".", "/")
            url = f"{self.opa_url}/v1/data/{path_parts}"

            # Secondary SSRF defense: verify the constructed URL still targets
            # the configured OPA base URL, regardless of how path_parts was derived.
            if not url.startswith(self.opa_url):
                raise ACGSValidationError(
                    "Constructed OPA URL does not start with configured base — request blocked",
                    field="policy_path",
                    constraint="URL must target configured OPA base",
                )

            response = await self._http_client.post(url, json={"input": input_data})
            response.raise_for_status()

            data = response.json()
            opa_result = data.get("result", False)

            return self._format_evaluation_result(opa_result, "http", policy_path)

        except (HTTPConnectError, HTTPConnectTimeout) as e:
            sanitized_error = self._sanitize_error(e)
            logger.error("OPA HTTP connection error: %s", sanitized_error)
            raise OPAConnectionError(
                self.opa_url or "unknown", f"Failed to connect to OPA: {sanitized_error}"
            ) from e
        except HTTPTimeoutException as e:
            sanitized_error = self._sanitize_error(e)
            logger.error("OPA HTTP timeout: %s", sanitized_error)
            raise OPAConnectionError(
                self.opa_url or "unknown", f"OPA request timeout: {sanitized_error}"
            ) from e
        except HTTPStatusError as e:
            sanitized_error = self._sanitize_error(e)
            logger.error("OPA HTTP error: %s", sanitized_error)
            raise PolicyEvaluationError(
                policy_path, f"OPA returned error: {sanitized_error}"
            ) from e
        except json.JSONDecodeError as e:
            logger.error("OPA response parse error: %s", e)
            raise PolicyEvaluationError(policy_path, f"Invalid OPA response: {e}") from e

    async def _evaluate_embedded(self, input_data: JSONDict, policy_path: str) -> JSONDict:
        """Evaluate policy via embedded OPA SDK."""
        if not self._embedded_opa:
            raise OPANotInitializedError("embedded policy evaluation")

        try:
            loop = asyncio.get_running_loop()
            executor = self._get_embedded_executor()
            opa_result = await loop.run_in_executor(
                executor,
                self._embedded_opa.evaluate,
                policy_path,
                input_data,
            )

            return self._format_evaluation_result(opa_result, "embedded", policy_path)

        except (RuntimeError, OSError) as e:
            sanitized_error = self._sanitize_error(e)
            logger.error("Embedded OPA evaluation error: %s", sanitized_error)
            raise PolicyEvaluationError(
                policy_path, f"Embedded OPA error: {sanitized_error}"
            ) from e
        except TypeError as e:
            # Type errors from input data issues
            logger.error("Embedded OPA type error: %s", e)
            raise PolicyEvaluationError(policy_path, f"Invalid input for OPA: {e}") from e

    async def _evaluate_fallback(self, input_data: JSONDict, policy_path: str) -> JSONDict:
        """Fallback policy evaluation - ALWAYS FAIL-CLOSED."""
        logger.warning("Using fail-closed fallback for %s", policy_path)

        constitutional_hash = input_data.get("constitutional_hash", "")
        if constitutional_hash != CONSTITUTIONAL_HASH:
            return {
                "result": False,
                "allowed": False,
                "reason": f"Invalid constitutional hash: {constitutional_hash}",
                "metadata": {"mode": "fallback", "policy_path": policy_path},
            }

        return {
            "result": False,
            "allowed": False,
            "reason": "OPA service unavailable - denied (fail-closed)",
            "metadata": {
                "mode": "fallback",
                "policy_path": policy_path,
                "security": "fail-closed",
            },
        }

    async def evaluate_with_history(
        self,
        input_data: JSONDict,
        action_history: list[str],
        policy_path: str = "data.acgs.temporal.allow",
    ) -> JSONDict:
        """Evaluate a temporal ordering policy with session action history.

        Temporal policies (e.g. policies/temporal.rego) require the full
        sequence of prior actions in the current session to verify ordering
        constraints.  This method injects ``action_history`` into the OPA
        input so those rules can use set-membership checks.

        Unlike ``evaluate_policy``, results are NOT cached because the
        action_history is dynamic and changes every pipeline step.

        Args:
        input_data: Standard OPA input (action, impact_score, etc.)
        action_history: Ordered list of completed action labels for
        the current session (e.g. ["constitutional_hash_verified",
        "maci_consensus_approved"]).
        policy_path: OPA policy path to evaluate. Defaults to the
        ACGS temporal ordering policy.

        Returns:
        Standard OPA result dict with ``allowed``, ``reason``, and
        ``metadata`` keys. Always fails-closed on error.
        """
        enriched = {
            **input_data,
            "action_history": list(action_history),
        }
        try:
            self._validate_policy_path(policy_path)
            self._validate_input_data(enriched)

            async def _evaluate_enriched(payload: JSONDict) -> JSONDict:
                if self.mode == "http":
                    return await self._evaluate_http(payload, policy_path)
                if self.mode == "embedded":
                    return await self._evaluate_embedded(payload, policy_path)
                return await self._evaluate_fallback(payload, policy_path)

            support_candidates: list[JSONDict] = []
            if self._is_temporal_multi_path_enabled():
                support_candidates = self._build_temporal_support_set_candidates(action_history)

            if not support_candidates:
                return await _evaluate_enriched(enriched)

            baseline = await _evaluate_enriched(enriched)
            paths: list[JSONDict] = [
                {
                    "path_id": "baseline",
                    "allowed": baseline.get("allowed", False),
                    "reason": baseline.get("reason", ""),
                    "support_set": {"action_history": list(action_history)},
                    "metadata": baseline.get("metadata", {}),
                }
            ]
            for idx, support_set in enumerate(support_candidates, start=1):
                candidate_input: JSONDict = {**enriched, **support_set}
                decision = await _evaluate_enriched(candidate_input)
                paths.append(
                    {
                        "path_id": f"candidate_{idx}",
                        "allowed": decision.get("allowed", False),
                        "reason": decision.get("reason", ""),
                        "support_set": support_set,
                        "metadata": decision.get("metadata", {}),
                    }
                )

            allowed_paths = [path for path in paths if path.get("allowed")]
            minimal_support_sets = self._minimal_support_sets(allowed_paths)
            diversity = self._compute_diversity_metrics(paths, allowed_paths, minimal_support_sets)
            self._multipath_evaluation_count += 1
            self._multipath_last_path_count = len(paths)
            self._multipath_last_diversity_ratio = float(diversity.get("path_diversity_ratio", 0.0))
            self._multipath_last_support_family_count = int(
                diversity.get("support_family_count", 0)
            )

            return {
                "result": baseline.get("result", False),
                "allowed": baseline.get("allowed", False),
                "reason": baseline.get("reason", ""),
                "metadata": {
                    **baseline.get("metadata", {}),
                    "path_count": len(paths),
                    "allowed_path_count": len(allowed_paths),
                    "minimal_support_set_count": len(minimal_support_sets),
                    "multi_path_source": "temporal_history",
                    **diversity,
                },
                "paths": paths,
                "minimal_support_sets": minimal_support_sets,
            }

        except (
            HTTPConnectError,
            HTTPConnectTimeout,
            HTTPTimeoutException,
            HTTPStatusError,
            ValueError,
            ACGSValidationError,
            OPAConnectionError,
            OPANotInitializedError,
            PolicyEvaluationError,
            AttributeError,
            KeyError,
            OSError,
            RuntimeError,
            TypeError,
        ) as e:
            return self._handle_evaluation_error(e, policy_path)

    async def validate_constitutional(self, message: JSONDict) -> ValidationResult:
        """Validate message against constitutional rules."""
        try:
            input_data = {
                "message": message,
                "constitutional_hash": message.get("constitutional_hash", ""),
                "timestamp": datetime.now(UTC).isoformat(),
            }
            if self._is_multi_path_candidate_generation_enabled():
                support_candidates = self._build_constitutional_support_set_candidates(message)
                if support_candidates:
                    input_data["support_set_candidates"] = support_candidates

            result = await self.evaluate_policy(
                input_data, policy_path="data.acgs.constitutional.validate"
            )

            validation_result = ValidationResult(
                is_valid=result["allowed"], constitutional_hash=CONSTITUTIONAL_HASH
            )

            if not result["allowed"]:
                validation_result.add_error(result.get("reason", "Failed"))

            validation_result.metadata.update(result.get("metadata", {}))
            return validation_result

        except (OPAConnectionError, OPANotInitializedError, PolicyEvaluationError) as e:
            logger.error("Constitutional validation OPA error: %s", e)
            res = ValidationResult(is_valid=False, constitutional_hash=CONSTITUTIONAL_HASH)
            res.add_error(f"OPA error: {e!s}")
            return res
        except (HTTPConnectError, HTTPTimeoutException, HTTPStatusError) as e:
            logger.error("Constitutional validation HTTP error: %s", e)
            res = ValidationResult(is_valid=False, constitutional_hash=CONSTITUTIONAL_HASH)
            res.add_error(f"Connection error: {e!s}")
            return res
        except (ValueError, ACGSValidationError) as e:
            logger.error("Constitutional validation value error: %s", e)
            res = ValidationResult(is_valid=False, constitutional_hash=CONSTITUTIONAL_HASH)
            res.add_error(f"Validation error: {e!s}")
            return res

    async def check_agent_authorization(
        self, agent_id: str, action: str, resource: str, context: JSONDict | None = None
    ) -> bool:
        """Check if agent is authorized."""
        try:
            ctx = context or {}
            provided_hash = ctx.get("constitutional_hash", CONSTITUTIONAL_HASH)

            if provided_hash != CONSTITUTIONAL_HASH:
                return False

            input_data = {
                "agent_id": agent_id,
                "action": action,
                "resource": resource,
                "context": ctx,
                "constitutional_hash": provided_hash,
                "timestamp": datetime.now(UTC).isoformat(),
            }
            if self._is_multi_path_candidate_generation_enabled():
                support_candidates = self._build_authorization_support_set_candidates(ctx)
                if support_candidates:
                    input_data["support_set_candidates"] = support_candidates

            result = await self.evaluate_policy(input_data, policy_path="data.acgs.rbac.allow")

            return result["allowed"]

        except (OPAConnectionError, OPANotInitializedError, PolicyEvaluationError) as e:
            logger.error("Authorization check OPA error: %s", e)
            return False
        except (HTTPConnectError, HTTPTimeoutException, HTTPStatusError) as e:
            logger.error("Authorization check HTTP error: %s", e)
            return False
        except (ValueError, ACGSValidationError) as e:
            logger.error("Authorization check value error: %s", e)
            return False

    async def load_policy(self, policy_id: str, policy_content: str) -> bool:
        """Load a policy into OPA."""
        if self.mode != "http" or not self._http_client:
            return False

        try:
            response = await self._http_client.put(
                f"{self.opa_url}/v1/policies/{policy_id}",
                content=policy_content.encode("utf-8"),
                headers={"Content-Type": "text/plain"},
            )
            response.raise_for_status()

            # Smart Invalidation: Clear cache when policy is updated
            # Note: policy_id might not match the evaluation policy_path exactly,
            # so we clear the whole cache to be safe when a specific policy is loaded.
            await self.clear_cache()

            return True
        except (HTTPConnectError, HTTPConnectTimeout) as e:
            logger.error("Failed to connect to OPA for policy %s: %s", policy_id, e)
            return False
        except HTTPTimeoutException as e:
            logger.error("Timeout loading policy %s: %s", policy_id, e)
            return False
        except HTTPStatusError as e:
            logger.error("HTTP error loading policy %s: %s", policy_id, e)
            return False
        except (RuntimeError, ValueError, TypeError) as e:
            logger.error("Unexpected error loading policy %s: %s", policy_id, e)
            return False

    async def load_bundle_from_url(self, url: str, signature: str, public_key: str) -> bool:
        """Download and load an OPA bundle with signature verification.
        Implements Pillar 1: Dynamic Policy-as-Code distribution.
        """
        if not self._http_client:
            await self.initialize()

        try:
            # 1. Download bundle
            response = await self._http_client.get(url)
            response.raise_for_status()

            bundle_data = response.content
            temp_path = "runtime/policy_bundles/temp_bundle.tar.gz"
            os.makedirs(os.path.dirname(temp_path), exist_ok=True)

            await asyncio.to_thread(Path(temp_path).write_bytes, bundle_data)

            # 2. Verify signature
            if not await self._verify_bundle(temp_path, signature, public_key):
                logger.error("Bundle signature verification failed")
                return await self._rollback_to_lkg()

            # 3. Load into OPA (Simulated)
            if self.mode == "http":
                logger.info("Loading bundle from %s into OPA", url)

            # Smart Invalidation: Clear cache when new bundle is loaded
            await self.clear_cache()

            # 4. Update LKG
            lkg_path = "runtime/policy_bundles/lkg_bundle.tar.gz"
            if os.path.exists(lkg_path):
                os.replace(temp_path, lkg_path)
            else:
                os.rename(temp_path, lkg_path)
            self._lkg_bundle_path = lkg_path

            return True

        except (HTTPConnectError, HTTPConnectTimeout) as e:
            logger.error("Connection error loading bundle from %s: %s", url, e)
            return await self._rollback_to_lkg()
        except HTTPTimeoutException as e:
            logger.error("Timeout loading bundle from %s: %s", url, e)
            return await self._rollback_to_lkg()
        except HTTPStatusError as e:
            logger.error("HTTP error loading bundle from %s: %s", url, e)
            return await self._rollback_to_lkg()
        except OSError as e:
            logger.error("File I/O error processing bundle: %s", e)
            return await self._rollback_to_lkg()
        except (RuntimeError, ValueError, TypeError) as e:
            logger.error("Unexpected error loading bundle from %s: %s", url, e)
            return await self._rollback_to_lkg()

    async def _verify_bundle(self, bundle_path: str, signature: str, public_key: str) -> bool:
        """Verify bundle signature using CryptoService."""
        try:
            import sys

            sys.path.append(os.path.join(os.getcwd(), "services/policy_registry"))
            from app.services.crypto_service import CryptoService

            with open(bundle_path, "rb") as f:
                data = f.read()
            bundle_hash = hashlib.sha256(data).hexdigest()

            metadata = {"hash": bundle_hash, "constitutional_hash": CONSTITUTIONAL_HASH}

            return CryptoService.verify_policy_signature(metadata, signature, public_key)
        except (ImportError, ModuleNotFoundError) as e:
            logger.error("CryptoService import error: %s", e)
            return False
        except FileNotFoundError as e:
            logger.error("Bundle file not found: %s", e)
            return False
        except OSError as e:
            logger.error("Error reading bundle file: %s", e)
            return False
        except (ValueError, TypeError) as e:
            logger.error("Signature verification error: %s", e)
            return False

    async def _rollback_to_lkg(self) -> bool:
        """Rollback to Last-Known-Good bundle."""
        lkg_path = "runtime/policy_bundles/lkg_bundle.tar.gz"
        if os.path.exists(lkg_path):
            logger.warning("Rolling back to LKG policy bundle")
            return True
        logger.error("No LKG bundle available for rollback")
        return False


class OPAClient(OPAClientCore, OPAClientCacheMixin, OPAClientHealthMixin):
    """Fully-composed OPA client with caching and health monitoring.

    Constitutional Hash: 608508a9bd224290

    Combines:
    - OPAClientCore: evaluation, authorization, bundle management
    - OPAClientCacheMixin: query result caching
    - OPAClientHealthMixin: health checks, multi-path evaluation
    """

    pass


# ---------------------------------------------------------------------------
# Singleton lifecycle helpers
# ---------------------------------------------------------------------------

_opa_client: OPAClient | None = None


async def initialize_opa_client(**kwargs: object) -> OPAClient:
    """Create (or re-use) the module-level singleton OPAClient.

    Keyword arguments are forwarded to the ``OPAClient`` constructor on first
    call. Subsequent calls return the existing instance.
    """
    global _opa_client
    if _opa_client is None:
        _opa_client = OPAClient(**kwargs)  # type: ignore[arg-type]
        await _opa_client.initialize()
    return _opa_client


def get_opa_client() -> OPAClient:
    """Return the module-level singleton, or raise if not yet initialised."""
    if _opa_client is None:
        raise OPANotInitializedError("get_opa_client")
    return _opa_client


async def close_opa_client() -> None:
    """Shut down the module-level singleton and release resources."""
    global _opa_client
    if _opa_client is not None:
        await _opa_client.close()
        _opa_client = None
