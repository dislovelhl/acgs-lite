"""
ACGS-2 Enhanced Agent Bus - LLM Adapter Base Interface
Constitutional Hash: cdd01ef066bc6cf2

Abstract base class defining standard interface for all LLM adapters.
Provides methods for completion, streaming, token counting, error handling,
and constitutional validation.
"""

import asyncio
import inspect
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field
from src.core.shared.resilience.retry import RetryConfig as SharedRetryConfig
from src.core.shared.resilience.retry import retry
from src.core.shared.types import JSONDict

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)

# Import centralized constitutional hash from shared module
try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH
except ImportError:
    # Fallback for standalone usage
    from src.core.shared.constants import CONSTITUTIONAL_HASH

RETRY_EXECUTION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    ConnectionError,
    OSError,
    asyncio.TimeoutError,
)

LEGACY_TIMEOUT_ERRORS: tuple[type[BaseException], ...] = (
    TimeoutError,
    asyncio.TimeoutError,
)

LEGACY_RATE_LIMIT_ERRORS: tuple[type[BaseException], ...] = (RuntimeError,)

LEGACY_SERVER_ERRORS: tuple[type[BaseException], ...] = (
    ConnectionError,
    OSError,
)


class StreamingMode(Enum):
    """Streaming support modes for LLM adapters."""

    NONE = "none"  # No streaming support
    SUPPORTED = "supported"  # Streaming available
    REQUIRED = "required"  # Only supports streaming


class AdapterStatus(Enum):
    """Status of an LLM adapter."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNAVAILABLE = "unavailable"


@dataclass
class TokenUsage:
    """Token usage statistics for a completion request.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    constitutional_hash: str = CONSTITUTIONAL_HASH

    @property
    def tokens(self) -> int:
        """Alias for total_tokens for backward compatibility."""
        return self.total_tokens

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "constitutional_hash": self.constitutional_hash,
        }


@dataclass
class CostEstimate:
    """Cost estimation for LLM API calls.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    prompt_cost_usd: float = 0.0
    completion_cost_usd: float = 0.0
    total_cost_usd: float = 0.0
    currency: str = "USD"
    pricing_model: str = "unknown"
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "prompt_cost_usd": self.prompt_cost_usd,
            "completion_cost_usd": self.completion_cost_usd,
            "total_cost_usd": self.total_cost_usd,
            "currency": self.currency,
            "pricing_model": self.pricing_model,
            "constitutional_hash": self.constitutional_hash,
        }


@dataclass
class CompletionMetadata:
    """Metadata for completion requests and responses.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    model: str
    provider: str
    request_id: str = ""
    latency_ms: float = 0.0
    finish_reason: str = "stop"
    constitutional_hash: str = CONSTITUTIONAL_HASH
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    extra: JSONDict = field(default_factory=dict)

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "model": self.model,
            "provider": self.provider,
            "request_id": self.request_id,
            "latency_ms": self.latency_ms,
            "finish_reason": self.finish_reason,
            "constitutional_hash": self.constitutional_hash,
            "timestamp": self.timestamp.isoformat(),
            "extra": self.extra,
        }


class LLMMessage(BaseModel):
    """Standardized message format for LLM requests.

    Compatible with OpenAI, Anthropic, and other major providers.
    Constitutional Hash: cdd01ef066bc6cf2
    """

    role: str = Field(..., description="Message role: 'system', 'user', or 'assistant'")
    content: str = Field(..., description="Message content text")
    name: str | None = Field(default=None, description="Optional name for the message author")
    function_call: JSONDict | None = Field(
        default=None, description="Function call data (deprecated, use tool_calls)"
    )
    tool_calls: list[JSONDict] | None = Field(
        default=None, description="Tool/function calls requested by the assistant"
    )
    tool_call_id: str | None = Field(
        default=None, description="ID of the tool call this message is responding to"
    )

    model_config = {"from_attributes": True}


class LLMResponse(BaseModel):
    """Standardized response format from LLM adapters.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    content: str = Field(..., description="Generated text content")
    messages: list[LLMMessage] = Field(
        default_factory=list, description="Full conversation history including response"
    )
    usage: TokenUsage = Field(default_factory=TokenUsage, description="Token usage statistics")
    cost: CostEstimate = Field(default_factory=CostEstimate, description="Cost estimation")
    metadata: CompletionMetadata = Field(..., description="Request/response metadata")
    constitutional_hash: str = Field(
        default=CONSTITUTIONAL_HASH, description="Constitutional hash for compliance"
    )
    tool_calls: list[JSONDict] | None = Field(
        default=None, description="Tool/function calls in the response"
    )
    raw_response: JSONDict | None = Field(
        default=None, description="Raw provider-specific response for debugging"
    )

    model_config = {"from_attributes": True}

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "content": self.content,
            "messages": [msg.model_dump() for msg in self.messages],
            "usage": self.usage.to_dict(),
            "cost": self.cost.to_dict(),
            "metadata": self.metadata.to_dict(),
            "constitutional_hash": self.constitutional_hash,
            "tool_calls": self.tool_calls,
        }


@dataclass
class LLMRetryConfig:
    """Legacy-compatible LLM retry config mapped to shared RetryConfig."""

    max_retries: int = 3
    initial_delay_ms: float = 1000.0
    max_delay_ms: float = 60000.0
    exponential_base: float = 2.0
    jitter: bool = True
    retry_on_timeout: bool = True
    retry_on_rate_limit: bool = True
    retry_on_server_error: bool = True
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_shared_retry_config(self) -> SharedRetryConfig:
        """Convert legacy retry config to canonical shared retry config."""
        retryable_errors: list[type[BaseException]] = [
            RuntimeError,
            ValueError,
            TypeError,
            KeyError,
            AttributeError,
        ]

        if self.retry_on_timeout:
            retryable_errors.extend(LEGACY_TIMEOUT_ERRORS)
        if self.retry_on_rate_limit:
            retryable_errors.extend(LEGACY_RATE_LIMIT_ERRORS)
        if self.retry_on_server_error:
            retryable_errors.extend(LEGACY_SERVER_ERRORS)

        deduplicated_retryable_errors = tuple(dict.fromkeys(retryable_errors))

        return SharedRetryConfig(
            max_retries=self.max_retries,
            base_delay=self.initial_delay_ms / 1000.0,
            max_delay=self.max_delay_ms / 1000.0,
            multiplier=self.exponential_base,
            jitter=self.jitter,
            jitter_factor=0.5,
            retryable_exceptions=deduplicated_retryable_errors,
            raise_on_exhausted=False,
        )


# Backward-compatible export name used by concrete adapters.
RetryConfig = LLMRetryConfig


@dataclass
class HealthCheckResult:
    """Result of adapter health check.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    status: AdapterStatus
    latency_ms: float = 0.0
    message: str = ""
    details: JSONDict = field(default_factory=dict)
    constitutional_hash: str = CONSTITUTIONAL_HASH
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "status": self.status.value,
            "latency_ms": self.latency_ms,
            "message": self.message,
            "details": self.details,
            "constitutional_hash": self.constitutional_hash,
            "timestamp": self.timestamp.isoformat(),
        }


class BaseLLMAdapter(ABC):
    """Abstract base class for all LLM adapters.

    This class defines the standard interface that all LLM adapter implementations
    must follow, ensuring consistent behavior across different providers.

    Constitutional Hash: cdd01ef066bc6cf2

    All adapters must implement:
    - Completion (sync and async)
    - Streaming (if supported)
    - Token counting
    - Cost estimation
    - Error handling with retry logic
    - Constitutional validation
    - Health checks
    """

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        retry_config: RetryConfig | SharedRetryConfig | None = None,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
        **kwargs: object,
    ) -> None:
        """Initialize the adapter.

        Args:
            model: Model identifier (e.g., "gpt-5.2", "claude-sonnet-4-6")
            api_key: API key for authentication (optional, can use env vars)
            retry_config: Configuration for retry logic
            constitutional_hash: Constitutional hash for compliance validation
            **kwargs: Provider-specific configuration
        """
        self.model = model
        self.api_key = api_key
        self.retry_config = self._to_shared_retry_config(retry_config)
        self.constitutional_hash = constitutional_hash
        self.config = kwargs
        self._validate_constitutional_hash()

    def _to_shared_retry_config(
        self,
        retry_config: RetryConfig | SharedRetryConfig | None,
    ) -> SharedRetryConfig:
        """Normalize retry config to canonical shared retry configuration."""
        if retry_config is None:
            return RetryConfig().to_shared_retry_config()
        if isinstance(retry_config, SharedRetryConfig):
            return retry_config
        if isinstance(retry_config, RetryConfig):
            return retry_config.to_shared_retry_config()
        raise TypeError(f"Unsupported retry config type: {type(retry_config).__name__}")

    def _validate_constitutional_hash(self) -> None:
        """Validate constitutional hash."""
        if self.constitutional_hash != CONSTITUTIONAL_HASH:
            # Allow custom hashes but log warning
            logger.warning(f"Using non-standard constitutional hash: {self.constitutional_hash}")

    # ==========================================================================
    # Abstract Methods - Must be implemented by all adapters
    # ==========================================================================

    @abstractmethod
    def complete(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        top_p: float = 1.0,
        stop: list[str] | None = None,
        **kwargs: object,
    ) -> LLMResponse:
        """Generate a completion synchronously.

        Args:
            messages: List of conversation messages
            temperature: Sampling temperature (0.0 to 2.0)
            max_tokens: Maximum tokens to generate
            top_p: Nucleus sampling parameter
            stop: Stop sequences
            **kwargs: Provider-specific parameters

        Returns:
            LLMResponse with generated content and metadata

        Raises:
            LLMAdapterError: On API or validation errors
            ConstitutionalError: On constitutional compliance failures
        """
        pass

    @abstractmethod
    async def acomplete(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        top_p: float = 1.0,
        stop: list[str] | None = None,
        **kwargs: object,
    ) -> LLMResponse:
        """Generate a completion asynchronously.

        Args:
            messages: List of conversation messages
            temperature: Sampling temperature (0.0 to 2.0)
            max_tokens: Maximum tokens to generate
            top_p: Nucleus sampling parameter
            stop: Stop sequences
            **kwargs: Provider-specific parameters

        Returns:
            LLMResponse with generated content and metadata

        Raises:
            LLMAdapterError: On API or validation errors
            ConstitutionalError: On constitutional compliance failures
        """
        pass

    @abstractmethod
    def stream(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        top_p: float = 1.0,
        stop: list[str] | None = None,
        **kwargs: object,
    ) -> Iterator[str]:
        """Stream completion tokens synchronously.

        Args:
            messages: List of conversation messages
            temperature: Sampling temperature (0.0 to 2.0)
            max_tokens: Maximum tokens to generate
            top_p: Nucleus sampling parameter
            stop: Stop sequences
            **kwargs: Provider-specific parameters

        Yields:
            Generated text chunks

        Raises:
            LLMAdapterError: On API or validation errors
            NotImplementedError: If streaming is not supported
        """
        pass

    @abstractmethod
    def astream(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        top_p: float = 1.0,
        stop: list[str] | None = None,
        **kwargs: object,
    ) -> AsyncIterator[str]:
        """Stream completion tokens asynchronously.

        Args:
            messages: List of conversation messages
            temperature: Sampling temperature (0.0 to 2.0)
            max_tokens: Maximum tokens to generate
            top_p: Nucleus sampling parameter
            stop: Stop sequences
            **kwargs: Provider-specific parameters

        Yields:
            Generated text chunks

        Raises:
            LLMAdapterError: On API or validation errors
            NotImplementedError: If streaming is not supported
        """
        pass

    @abstractmethod
    def count_tokens(self, messages: list[LLMMessage]) -> int:
        """Count tokens in messages for the current model.

        Args:
            messages: List of messages to count tokens for

        Returns:
            Total token count

        Raises:
            LLMAdapterError: On tokenization errors
        """
        pass

    @abstractmethod
    def estimate_cost(
        self,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> CostEstimate:
        """Estimate cost for a completion request.

        Args:
            prompt_tokens: Number of tokens in the prompt
            completion_tokens: Expected number of completion tokens

        Returns:
            CostEstimate with pricing breakdown
        """
        pass

    @abstractmethod
    async def health_check(self) -> HealthCheckResult:
        """Check adapter health and connectivity.

        Returns:
            HealthCheckResult with status and diagnostics

        Raises:
            LLMAdapterError: On health check failures
        """
        pass

    # ==========================================================================
    # Optional Methods - Default implementations provided
    # ==========================================================================

    def get_streaming_mode(self) -> StreamingMode:
        """Get streaming support level for this adapter.

        Returns:
            StreamingMode indicating streaming capability
        """
        return StreamingMode.SUPPORTED

    def get_provider_name(self) -> str:
        """Get the provider name for this adapter.

        Returns:
            Provider identifier (e.g., "openai", "anthropic")
        """
        return self.__class__.__name__.lower().replace("adapter", "")

    def validate_messages(self, messages: list[LLMMessage]) -> None:
        """Validate message format and constitutional compliance.

        Args:
            messages: Messages to validate

        Raises:
            ValueError: If messages are invalid
            ConstitutionalError: If constitutional validation fails
        """
        if not messages:
            raise ValueError("Messages list cannot be empty")

        # Validate message roles
        valid_roles = {"system", "user", "assistant", "function", "tool"}
        for msg in messages:
            if msg.role not in valid_roles:
                raise ValueError(f"Invalid role '{msg.role}'. Must be one of: {valid_roles}")

        # Ensure first message is not from assistant
        if messages[0].role == "assistant":
            raise ValueError("First message cannot be from assistant")

    def validate_constitutional_compliance(self, **kwargs: object) -> None:  # noqa: B027
        """Validate constitutional compliance for request parameters.

        Args:
            **kwargs: Request parameters to validate

        Raises:
            ConstitutionalError: If constitutional validation fails
        """
        # Base implementation - can be overridden by subclasses
        # for provider-specific constitutional checks
        pass

    async def retry_with_backoff(
        self,
        func: Callable[..., object | Awaitable[object]],
        *args: object,
        **kwargs: object,
    ) -> object:
        """Execute function with retry logic and exponential backoff.

        Args:
            func: Async function to execute
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func

        Returns:
            Result from successful function execution

        Raises:
            Exception: Last exception if all retries exhausted
        """
        if inspect.iscoroutinefunction(func):
            wrapped_func = retry(config=self.retry_config)(func)
            return await wrapped_func(*args, **kwargs)

        async def async_wrapper(*wrapper_args: object, **wrapper_kwargs: object) -> object:
            return func(*wrapper_args, **wrapper_kwargs)

        wrapped_func = retry(config=self.retry_config)(async_wrapper)
        return await wrapped_func(*args, **kwargs)

    def __repr__(self) -> str:
        """String representation of the adapter."""
        return (
            f"{self.__class__.__name__}("
            f"model='{self.model}', "
            f"provider='{self.get_provider_name()}', "
            f"constitutional_hash='{self.constitutional_hash[:8]}...')"
        )


__all__ = [
    "AdapterStatus",
    # Base class
    "BaseLLMAdapter",
    "CompletionMetadata",
    "CostEstimate",
    "HealthCheckResult",
    # Models
    "LLMMessage",
    "LLMResponse",
    "RetryConfig",
    # Enums
    "StreamingMode",
    # Data classes
    "TokenUsage",
]
