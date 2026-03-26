"""
ACGS-2 Model-Agnostic Adapter Framework
Constitutional Hash: 608508a9bd224290

Provides unified interface for AI model integration across providers.
Enables governance across any AI model without code changes.
"""

from .anthropic_adapter import AnthropicAdapter
from .base import (
    CONSTITUTIONAL_HASH,
    AdapterRegistry,
    MessageRole,
    ModelAdapter,
    ModelMessage,
    ModelProvider,
    ModelRequest,
    ModelResponse,
    StreamChunk,
    get_adapter_registry,
)
from .deepseek_adapter import DeepSeekAdapter
from .huggingface_adapter import HuggingFaceAdapter
from .openai_adapter import OpenAIAdapter

__all__ = [
    # Constants
    "CONSTITUTIONAL_HASH",
    # Registry
    "AdapterRegistry",
    "AnthropicAdapter",
    "DeepSeekAdapter",
    "HuggingFaceAdapter",
    "MessageRole",
    # Base class
    "ModelAdapter",
    "ModelMessage",
    # Base types
    "ModelProvider",
    "ModelRequest",
    "ModelResponse",
    # Concrete adapters
    "OpenAIAdapter",
    "StreamChunk",
    "get_adapter_registry",
]


def create_adapter(
    provider: ModelProvider,
    api_key: str | None = None,
    **kwargs,
) -> ModelAdapter:
    """Factory function to create an adapter for a provider.

    Args:
        provider: Model provider type
        api_key: API key for the provider
        **kwargs: Additional provider-specific arguments

    Returns:
        Configured adapter instance

    Raises:
        ValueError: If provider is not supported
    """
    adapter_map = {
        ModelProvider.OPENAI: OpenAIAdapter,
        ModelProvider.ANTHROPIC: AnthropicAdapter,
        ModelProvider.DEEPSEEK: DeepSeekAdapter,
        ModelProvider.HUGGINGFACE: HuggingFaceAdapter,
        ModelProvider.META: HuggingFaceAdapter,
        ModelProvider.XAI: OpenAIAdapter,  # xAI uses OpenAI-compatible API
        ModelProvider.MOONSHOT: OpenAIAdapter,  # Moonshot uses OpenAI-compatible API
    }

    adapter_class = adapter_map.get(provider)
    if adapter_class is None:
        raise ValueError(f"No adapter available for provider: {provider}")

    return adapter_class(api_key=api_key, **kwargs)  # type: ignore[no-any-return]
