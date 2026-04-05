"""
ACGS-2 Model-Agnostic Adapter Framework
Constitutional Hash: 608508a9bd224290

Base adapter interface for AI model integration.
Enables governance across any AI model without code changes.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]


class ModelProvider(Enum):
    """Supported AI model providers."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    DEEPSEEK = "deepseek"
    META = "meta"  # Llama
    HUGGINGFACE = "huggingface"
    XAI = "xai"  # xAI Grok
    MOONSHOT = "moonshot"  # Kimi AI
    CUSTOM = "custom"


class MessageRole(Enum):
    """Standard message roles across all providers."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    FUNCTION = "function"


@dataclass
class ModelMessage:
    """Standard message format for all AI models.

    Normalized representation that adapters translate to/from
    provider-specific formats.
    """

    role: MessageRole
    content: str
    name: str | None = None
    tool_calls: list[JSONDict] | None = None
    tool_call_id: str | None = None
    metadata: JSONDict = field(default_factory=dict)


@dataclass
class ModelRequest:
    """Standard request format for AI model inference.

    Adapters translate this to provider-specific API formats.
    """

    messages: list[ModelMessage]
    model: str
    max_tokens: int = 4096
    temperature: float = 0.7
    top_p: float = 1.0
    stop: list[str] | None = None
    stream: bool = False

    # Tools and function calling
    tools: list[JSONDict] | None = None
    tool_choice: str | JSONDict | None = None

    # Governance context
    session_id: str | None = None
    tenant_id: str | None = None
    constitutional_hash: str = CONSTITUTIONAL_HASH

    # Request metadata
    metadata: JSONDict = field(default_factory=dict)
    request_id: str = field(default_factory=lambda: str(datetime.now(UTC).timestamp()))


@dataclass
class ModelResponse:
    """Standard response format from AI model inference."""

    content: str
    model: str
    provider: ModelProvider
    finish_reason: str = "stop"

    # Token usage
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    # Tool calls
    tool_calls: list[JSONDict] | None = None

    # Governance tracking
    constitutional_hash: str = CONSTITUTIONAL_HASH
    governance_validated: bool = False
    governance_latency_ms: float = 0.0

    # Response metadata
    response_id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: JSONDict = field(default_factory=dict)

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "content": self.content,
            "model": self.model,
            "provider": self.provider.value,
            "finish_reason": self.finish_reason,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "tool_calls": self.tool_calls,
            "constitutional_hash": self.constitutional_hash,
            "governance_validated": self.governance_validated,
            "governance_latency_ms": self.governance_latency_ms,
            "response_id": self.response_id,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class StreamChunk:
    """Single chunk from streaming response."""

    content: str
    finish_reason: str | None = None
    tool_calls: list[JSONDict] | None = None
    is_final: bool = False


class ModelAdapter(ABC):
    """Abstract base class for AI model adapters.

    All model adapters must implement this interface to enable
    model-agnostic governance. Adapters handle:
    - Request/response format translation
    - API authentication
    - Error handling
    - Streaming support

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(
        self,
        provider: ModelProvider,
        api_key: str | None = None,
        base_url: str | None = None,
        default_model: str | None = None,
        timeout_seconds: int = 60,
    ) -> None:
        """Initialize adapter.

        Args:
            provider: Model provider type
            api_key: API key for authentication
            base_url: Optional custom base URL
            default_model: Default model to use
            timeout_seconds: Request timeout
        """
        self.provider = provider
        self.api_key = api_key
        self.base_url = base_url
        self.default_model = default_model
        self.timeout_seconds = timeout_seconds
        self._constitutional_hash = CONSTITUTIONAL_HASH

    @property
    def name(self) -> str:
        """Get adapter name."""
        return f"{self.provider.value}_adapter"

    @abstractmethod
    async def complete(self, request: ModelRequest) -> ModelResponse:
        """Execute a completion request.

        Args:
            request: Standardized model request

        Returns:
            Standardized model response
        """
        pass

    @abstractmethod
    def stream(self, request: ModelRequest) -> AsyncIterator[StreamChunk]:
        """Execute a streaming completion request.

        Args:
            request: Standardized model request

        Yields:
            Stream chunks as they arrive
        """
        pass

    @abstractmethod
    def translate_request(self, request: ModelRequest) -> JSONDict:
        """Translate standard request to provider-specific format.

        Args:
            request: Standard request

        Returns:
            Provider-specific request dict
        """
        pass

    @abstractmethod
    def translate_response(self, response: JSONDict) -> ModelResponse:
        """Translate provider-specific response to standard format.

        Args:
            response: Provider-specific response

        Returns:
            Standard response
        """
        pass

    def validate_request(self, request: ModelRequest) -> list[str]:
        """Validate request before sending.

        Args:
            request: Request to validate

        Returns:
            List of validation error messages (empty if valid)
        """
        errors: list[str] = []
        if not request.messages:
            errors.append("No messages provided")
        if not request.model and not self.default_model:
            errors.append("No model specified and no default model configured")
        if request.max_tokens <= 0:
            errors.append("max_tokens must be positive")
        if not 0.0 <= request.temperature <= 2.0:
            errors.append("temperature must be between 0.0 and 2.0")
        return errors

    async def health_check(self) -> bool:
        """Check if the adapter can connect to the model provider.

        Returns:
            True if healthy, False otherwise
        """
        try:
            # Simple health check - try to make minimal request
            request = ModelRequest(
                messages=[ModelMessage(role=MessageRole.USER, content="ping")],
                model=self.default_model or "",
                max_tokens=1,
            )
            await self.complete(request)
            return True
        except (RuntimeError, ValueError, TypeError, OSError):
            return False

    def get_capabilities(self) -> JSONDict:
        """Get adapter capabilities.

        Returns:
            Dictionary of capabilities
        """
        return {
            "provider": self.provider.value,
            "streaming": True,
            "tool_calling": True,
            "vision": False,  # Override in subclass if supported
            "function_calling": True,
            "constitutional_hash": self._constitutional_hash,
        }


class AdapterRegistry:
    """Registry for model adapters.

    Manages adapter instances and provides lookup by provider.
    """

    def __init__(self) -> None:
        """Initialize registry."""
        self._adapters: dict[ModelProvider, ModelAdapter] = {}
        self._default_adapter: ModelAdapter | None = None

    def register(
        self,
        adapter: ModelAdapter,
        set_default: bool = False,
    ) -> None:
        """Register an adapter.

        Args:
            adapter: Adapter instance to register
            set_default: Whether to set as default adapter
        """
        self._adapters[adapter.provider] = adapter
        if set_default:
            self._default_adapter = adapter

    def get(self, provider: ModelProvider) -> ModelAdapter | None:
        """Get adapter by provider.

        Args:
            provider: Provider type

        Returns:
            Adapter instance or None
        """
        return self._adapters.get(provider)

    def get_default(self) -> ModelAdapter | None:
        """Get default adapter.

        Returns:
            Default adapter or None
        """
        return self._default_adapter

    def list_providers(self) -> list[ModelProvider]:
        """List registered providers.

        Returns:
            List of registered provider types
        """
        return list(self._adapters.keys())

    def unregister(self, provider: ModelProvider) -> None:
        """Unregister an adapter.

        Args:
            provider: Provider to unregister
        """
        if provider in self._adapters:
            del self._adapters[provider]


# Global registry
_global_registry: AdapterRegistry | None = None


def get_adapter_registry() -> AdapterRegistry:
    """Get or create global adapter registry.

    Returns:
        Global adapter registry instance
    """
    global _global_registry
    if _global_registry is None:
        _global_registry = AdapterRegistry()
    return _global_registry


__all__ = [
    # Constants
    "CONSTITUTIONAL_HASH",
    # Registry
    "AdapterRegistry",
    "MessageRole",
    # Base class
    "ModelAdapter",
    # Data classes
    "ModelMessage",
    # Enums
    "ModelProvider",
    "ModelRequest",
    "ModelResponse",
    "StreamChunk",
    "get_adapter_registry",
]
