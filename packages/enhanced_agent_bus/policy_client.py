"""Constitutional Hash: 608508a9bd224290
Policy Registry Client for dynamic constitutional validation
"""

import time
from collections import OrderedDict

import httpx

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

try:
    from .models import AgentMessage
    from .validators import ValidationResult
except (ImportError, ValueError):
    from models import AgentMessage  # type: ignore[no-redef]
    from validators import ValidationResult  # type: ignore[no-redef]

try:
    from enhanced_agent_bus._compat.config import settings
except ImportError:
    from enhanced_agent_bus._compat.config import settings  # type: ignore[no-redef]

logger = get_logger(__name__)
# Default maximum cache size to prevent unbounded memory growth
DEFAULT_MAX_CACHE_SIZE = 1000

# Optimized cache TTL settings based on content volatility
# These values balance freshness with hit rate optimization
CACHE_TTL_POLICIES = {
    # Dynamic policies that may change frequently (e.g., A/B tests, active updates)
    "dynamic": 60,  # 1 minute - quick refresh for frequently changing content
    # Standard policies that change occasionally (default)
    "standard": 300,  # 5 minutes - balance between freshness and hit rate
    # Stable policies that rarely change (constitutional, core governance)
    "stable": 900,  # 15 minutes - higher TTL for stable content
    # Immutable policies (versioned, locked)
    "immutable": 3600,  # 1 hour - can cache longer since they don't change
}

# Policy ID patterns to TTL tier mapping
POLICY_TTL_PATTERNS = {
    "constitutional": "stable",
    "governance": "stable",
    "core": "stable",
    "ab_test": "dynamic",
    "experiment": "dynamic",
    "feature_flag": "dynamic",
}


def get_optimal_cache_ttl(policy_id: str, default_ttl: int = 300) -> int:
    """
    Get optimal cache TTL based on policy ID pattern matching.

    Args:
        policy_id: The policy identifier
        default_ttl: Default TTL if no pattern matches

    Returns:
        Optimal TTL in seconds
    """
    policy_id_lower = policy_id.lower()
    for pattern, tier in POLICY_TTL_PATTERNS.items():
        if pattern in policy_id_lower:
            return CACHE_TTL_POLICIES.get(tier, default_ttl)
    return default_ttl


class PolicyRegistryClient:
    """Client for communicating with Policy Registry Service"""

    def __init__(
        self,
        registry_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 5.0,
        cache_ttl: int = 300,  # 5 minutes
        fail_closed: bool = True,  # SECURITY: Default to fail-closed for safety
        max_cache_size: int = DEFAULT_MAX_CACHE_SIZE,
    ):
        self.registry_url = (registry_url or "http://localhost:8000").rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.cache_ttl = cache_ttl
        self.fail_closed = fail_closed
        self.max_cache_size = max_cache_size
        # OrderedDict maintains insertion order for LRU-style eviction
        self._cache: OrderedDict[str, JSONDict] = OrderedDict()
        self._http_client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "PolicyRegistryClient":
        """Async context manager entry"""
        await self.initialize()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Async context manager exit"""
        await self.close()

    async def initialize(self) -> None:
        """Initialize HTTP client"""
        if not self._http_client:
            headers = {}
            if self.api_key:
                headers["X-Internal-API-Key"] = self.api_key

            self._http_client = httpx.AsyncClient(
                timeout=self.timeout,
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
                headers=headers,
            )

    async def close(self) -> None:
        """Close HTTP client"""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    async def get_policy_content(
        self, policy_id: str, client_id: str | None = None
    ) -> JSONDict | None:
        """
        Get policy content from registry

        Args:
            policy_id: Policy identifier
            client_id: Client identifier for A/B testing

        Returns:
            Policy content dict or None
        """
        # Check cache first
        cache_key = f"{policy_id}:{client_id or 'default'}"
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            if time.monotonic() - cached["timestamp"] < self.cache_ttl:
                # Move to end for LRU behavior (most recently accessed)
                self._cache.move_to_end(cache_key)
                return cached["content"]
            else:
                # Expired, remove from cache
                del self._cache[cache_key]

        # Fetch from registry
        try:
            params = {"client_id": client_id} if client_id else {}
            response = await self._http_client.get(
                f"{self.registry_url}/api/v1/policies/{policy_id}/content", params=params
            )
            response.raise_for_status()
            content = response.json()

            # Evict oldest entries if cache is at capacity
            while len(self._cache) >= self.max_cache_size:
                # Remove oldest (first) item - FIFO eviction for LRU
                self._cache.popitem(last=False)

            # Cache the result
            self._cache[cache_key] = {"content": content, "timestamp": time.monotonic()}

            return content

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"Policy {policy_id} not found")
                return None
            else:
                logger.error(f"HTTP error fetching policy {policy_id}: {e}")
                raise
        except httpx.TimeoutException as e:
            logger.error(f"Timeout fetching policy {policy_id}: {e}")
            raise
        except httpx.ConnectError as e:
            logger.error(f"Connection error fetching policy {policy_id}: {e}")
            raise
        except (ValueError, KeyError) as e:
            logger.error(f"Data parsing error for policy {policy_id}: {e}")
            raise

    async def validate_message_signature(self, message: AgentMessage) -> ValidationResult:
        """
        Validate message against current constitutional policy

        Args:
            message: AgentMessage to validate

        Returns:
            ValidationResult
        """
        try:
            # Get current constitutional policy
            policy_content = await self.get_policy_content("constitutional_ai_safety")

            # Handle missing policy content
            if not policy_content:
                return self._handle_missing_policy()

            # Perform validation based on policy rules
            errors, warnings = self._validate_message_content(message, policy_content)

            return ValidationResult(is_valid=len(errors) == 0, errors=errors, warnings=warnings)

        except (httpx.TimeoutException, httpx.ConnectError) as e:
            return self._handle_network_error(e)
        except (ValueError, KeyError, TypeError) as e:
            return self._handle_data_error(e)

    def _handle_missing_policy(self) -> ValidationResult:
        """Handle case where policy content is not available."""
        if self.fail_closed:
            return ValidationResult(
                is_valid=False, errors=["Policy registry unavailable or policy not found"]
            )
        return ValidationResult(
            is_valid=True, warnings=["Policy registry unavailable, using basic validation"]
        )

    def _validate_message_content(
        self, message: AgentMessage, policy_content: JSONDict
    ) -> tuple[list[str], list[str]]:
        """Validate message content against policy rules."""
        errors: list[str] = []
        warnings: list[str] = []

        # Validate message length
        errors.extend(self._check_message_length(message, policy_content))

        # Validate allowed topics
        warnings.extend(self._check_allowed_topics(message, policy_content))

        # Check prohibited content
        errors.extend(self._check_prohibited_content(message, policy_content))

        return errors, warnings

    def _check_message_length(self, message: AgentMessage, policy_content: JSONDict) -> list[str]:
        """Check if message length exceeds policy limits."""
        max_length = policy_content.get("max_response_length", 10000)
        if len(str(message.content)) > max_length:
            return [f"Message exceeds maximum length of {max_length}"]
        return []

    def _check_allowed_topics(self, message: AgentMessage, policy_content: JSONDict) -> list[str]:
        """Check if message topics are allowed by policy."""
        allowed_topics = policy_content.get("allowed_topics", [])
        if allowed_topics:
            message_topics = message.content.get("topics", [])
            if not any(topic in allowed_topics for topic in message_topics):
                return ["Message topic not in allowed list"]
        return []

    def _check_prohibited_content(
        self, message: AgentMessage, policy_content: JSONDict
    ) -> list[str]:
        """Check if message contains prohibited content."""
        prohibited = policy_content.get("prohibited_content", [])
        message_text = str(message.content).lower()
        errors = []

        for prohibited_item in prohibited:
            if prohibited_item.lower() in message_text:
                errors.append(f"Message contains prohibited content: {prohibited_item}")

        return errors

    def _handle_network_error(self, error: Exception) -> ValidationResult:
        """Handle network-related validation errors."""
        logger.error(f"Network error validating message: {error}")
        if self.fail_closed:
            return ValidationResult(
                is_valid=False, errors=[f"Policy validation network error: {error!s}"]
            )
        return ValidationResult(
            is_valid=True, warnings=[f"Policy validation network error: {error!s}"]
        )

    def _handle_data_error(self, error: Exception) -> ValidationResult:
        """Handle data-related validation errors."""
        logger.error(f"Data error validating message: {error}")
        if self.fail_closed:
            return ValidationResult(
                is_valid=False, errors=[f"Policy validation data error: {error!s}"]
            )
        return ValidationResult(
            is_valid=True, warnings=[f"Policy validation data error: {error!s}"]
        )

    async def get_current_public_key(self) -> str | None:
        """Get current public key for signature verification"""
        try:
            response = await self._http_client.get(f"{self.registry_url}/api/v1/public-keys")
            response.raise_for_status()
            data = response.json()
            return data.get("current_public_key")  # type: ignore[no-any-return]
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching public key: {e}")
            return None
        except (httpx.TimeoutException, httpx.ConnectError) as e:
            logger.error(f"Network error fetching public key: {e}")
            return None
        except (ValueError, KeyError) as e:
            logger.error(f"Data error parsing public key response: {e}")
            return None

    async def health_check(self) -> JSONDict:
        """Check registry service health"""
        try:
            response = await self._http_client.get(f"{self.registry_url}/health/ready")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            return {"status": "unhealthy", "error": f"HTTP error: {e.response.status_code}"}
        except (httpx.TimeoutException, httpx.ConnectError) as e:
            return {"status": "unhealthy", "error": f"Network error: {type(e).__name__}"}
        except ValueError as e:
            return {"status": "unhealthy", "error": f"Response parsing error: {e}"}


# Global client instance
_policy_client: PolicyRegistryClient | None = None


def get_policy_client(fail_closed: bool | None = None) -> PolicyRegistryClient:
    """Get global policy client instance"""
    global _policy_client
    if _policy_client is None:
        # Use settings for default configuration
        api_key = (
            settings.security.api_key_internal.get_secret_value()
            if settings.security.api_key_internal
            else None
        )
        _policy_client = PolicyRegistryClient(
            registry_url=settings.services.policy_registry_url,
            api_key=api_key,
            fail_closed=(
                fail_closed if fail_closed is not None else True
            ),  # SECURITY: fail-closed default
        )
    elif fail_closed is not None:
        _policy_client.fail_closed = fail_closed
    return _policy_client


async def initialize_policy_client(
    registry_url: str = "http://localhost:8000",
    fail_closed: bool = True,  # SECURITY: Default to fail-closed for safety
) -> None:
    """Initialize global policy client"""
    global _policy_client
    _policy_client = PolicyRegistryClient(
        registry_url=registry_url,
        fail_closed=fail_closed,
    )
    await _policy_client.initialize()


async def close_policy_client() -> None:
    """Close global policy client"""
    global _policy_client
    if _policy_client:
        await _policy_client.close()
        _policy_client = None
