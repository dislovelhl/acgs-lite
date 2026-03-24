"""
ACGS-2 Enhanced Agent Bus - OpenClaw LLM Adapter
Constitutional Hash: cdd01ef066bc6cf2

OpenClaw adapter for routing LLM requests through a local agent runtime
gateway. Uses an OpenAI-compatible HTTP API for chat completions and
falls back to the WebSocket gateway for agent-mode interactions.

Models use the format 'provider/model-name' (e.g., 'anthropic/claude-opus-4-6').
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Iterator
from typing import ClassVar, Protocol, cast

from enhanced_agent_bus.observability.structured_logging import get_logger

from .base import (
    CONSTITUTIONAL_HASH,
    AdapterStatus,
    BaseLLMAdapter,
    CostEstimate,
    HealthCheckResult,
    LLMMessage,
    LLMResponse,
    RetryConfig,
    StreamingMode,
)
from .config import OpenClawAdapterConfig
from .models import ResponseConverter

logger = get_logger(__name__)
_OPENCLAW_ADAPTER_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
)


class _CompletionResponseProtocol(Protocol):
    def model_dump(self) -> dict[str, object]: ...


class _DeltaProtocol(Protocol):
    content: str | None


class _ChoiceProtocol(Protocol):
    delta: _DeltaProtocol


class _ChunkProtocol(Protocol):
    choices: list[_ChoiceProtocol]


class _ChatCompletionsProtocol(Protocol):
    def create(self, **kwargs: object) -> object: ...


class _AsyncChatCompletionsProtocol(Protocol):
    async def create(self, **kwargs: object) -> object: ...


class _ChatProtocol(Protocol):
    completions: _ChatCompletionsProtocol


class _AsyncChatProtocol(Protocol):
    completions: _AsyncChatCompletionsProtocol


class _ModelsProtocol(Protocol):
    async def list(self) -> object: ...


class _OpenAIClientProtocol(Protocol):
    chat: _ChatProtocol


class _AsyncOpenAIClientProtocol(Protocol):
    chat: _AsyncChatProtocol
    models: _ModelsProtocol


class OpenClawAdapter(BaseLLMAdapter):
    """OpenClaw LLM adapter for gateway-routed models.

    Constitutional Hash: cdd01ef066bc6cf2

    Routes requests through the OpenClaw agent runtime gateway using an
    OpenAI-compatible HTTP API. Supports any model available through
    the gateway (Anthropic, OpenAI, Gemini, etc.).

    Supports:
    - All models routed through OpenClaw gateway
    - Streaming responses
    - Function/tool calling (provider-dependent)
    - Token counting (approximate, uses tiktoken fallback)
    - Cost estimation (based on underlying model pricing)
    """

    config: OpenClawAdapterConfig  # type: ignore[assignment]

    # Approximate pricing per 1M tokens (USD) for models routed through OpenClaw.
    # Actual cost depends on the underlying provider.
    MODEL_PRICING: ClassVar[dict] = {
        # Anthropic models via OpenClaw
        "anthropic/claude-opus-4-6": {"prompt": 5.00, "completion": 25.00},
        "anthropic/claude-sonnet-4-6": {"prompt": 3.00, "completion": 15.00},
        "anthropic/claude-haiku-4-5-20251001": {"prompt": 1.00, "completion": 5.00},
        # OpenAI models via OpenClaw
        "openai/gpt-5.4": {"prompt": 2.00, "completion": 16.00},
        "openai/gpt-5.3": {"prompt": 1.75, "completion": 14.00},
        "openai/gpt-5.2": {"prompt": 1.75, "completion": 14.00},
        "openai/gpt-5.1": {"prompt": 1.25, "completion": 10.00},
        "openai/gpt-5-mini": {"prompt": 0.25, "completion": 2.00},
        # xAI models via OpenClaw
        "xai/grok-4-1-fast": {"prompt": 0.20, "completion": 0.50},
        "xai/grok-4.20": {"prompt": 2.00, "completion": 6.00},
        "xai/grok-4": {"prompt": 3.00, "completion": 15.00},
        # Google models via OpenClaw
        "google/gemini-2.0-flash": {"prompt": 0.0, "completion": 0.0},
    }

    def __init__(
        self,
        config: OpenClawAdapterConfig | None = None,
        model: str | None = None,
        api_key: str | None = None,
        retry_config: RetryConfig | None = None,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
        **kwargs: object,
    ) -> None:
        """Initialize OpenClaw adapter.

        Args:
            config: OpenClaw adapter configuration
            model: Model identifier (if config not provided)
            api_key: API key (if config not provided)
            retry_config: Retry configuration
            constitutional_hash: Constitutional hash for compliance
            **kwargs: Additional configuration options
        """
        if config is None:
            if model is None:
                model = "anthropic/claude-opus-4-6"
            config = OpenClawAdapterConfig.from_environment(model=model, **kwargs)

        super().__init__(
            model=config.model,
            api_key=api_key or config.get_api_key("OPENCLAW_API_KEY"),
            retry_config=retry_config,
            constitutional_hash=constitutional_hash,
            **kwargs,
        )

        self.config = config
        self._client: _OpenAIClientProtocol | None = None
        self._async_client: _AsyncOpenAIClientProtocol | None = None

    def validate_constitutional_compliance(self, **kwargs: object) -> None:
        """Validate constitutional compliance for OpenClaw adapter."""
        if not self.constitutional_hash:
            raise ValueError("Constitutional hash is required for OpenClaw adapter compliance.")
        if self.constitutional_hash != CONSTITUTIONAL_HASH:
            logger.warning(
                "OpenClaw adapter using non-standard constitutional hash: %s",
                self.constitutional_hash,
            )
        if not self.model:
            raise ValueError("OpenClaw adapter constitutional compliance requires a model.")

    def _get_client(self) -> _OpenAIClientProtocol:
        """Get or create synchronous OpenAI-compatible client.

        Returns:
            OpenAI client instance pointed at OpenClaw API

        Raises:
            ImportError: If openai package is not installed
        """
        if self._client is None:
            try:
                import openai
            except ImportError:
                raise ImportError(
                    "openai package is required for OpenClaw adapter. "
                    "Install with: pip install openai>=1.0.0"
                ) from None

            client_kwargs: dict[str, object] = {
                "base_url": self.config.api_base or "http://127.0.0.1:18790",
                "timeout": float(self.config.timeout_seconds),
            }
            if self.api_key:
                client_kwargs["api_key"] = self.api_key
            else:
                # OpenClaw gateway may not require an API key for local use
                client_kwargs["api_key"] = "openclaw-local"

            self._client = cast(
                _OpenAIClientProtocol,
                openai.OpenAI(**client_kwargs),
            )

        return self._client

    async def _get_async_client(self) -> _AsyncOpenAIClientProtocol:
        """Get or create async OpenAI-compatible client.

        Returns:
            Async OpenAI client instance pointed at OpenClaw API

        Raises:
            ImportError: If openai package is not installed
        """
        if self._async_client is None:
            try:
                import openai
            except ImportError:
                raise ImportError(
                    "openai package is required for OpenClaw adapter. "
                    "Install with: pip install openai>=1.0.0"
                ) from None

            client_kwargs: dict[str, object] = {
                "base_url": self.config.api_base or "http://127.0.0.1:18790",
                "timeout": float(self.config.timeout_seconds),
            }
            if self.api_key:
                client_kwargs["api_key"] = self.api_key
            else:
                client_kwargs["api_key"] = "openclaw-local"

            self._async_client = cast(
                _AsyncOpenAIClientProtocol,
                openai.AsyncOpenAI(**client_kwargs),
            )

        return self._async_client

    def _prepare_messages(
        self,
        messages: list[LLMMessage],
    ) -> list[dict[str, str]]:
        """Convert LLMMessage list to OpenAI-compatible format.

        Args:
            messages: List of LLM messages

        Returns:
            List of message dicts
        """
        result = []
        for msg in messages:
            entry: dict[str, str] = {
                "role": msg.role,
                "content": msg.content,
            }
            if msg.name:
                entry["name"] = msg.name
            result.append(entry)
        return result

    def complete(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        top_p: float = 1.0,
        stop: list[str] | None = None,
        **kwargs: object,
    ) -> LLMResponse:
        """Generate a completion synchronously via OpenClaw gateway.

        Args:
            messages: List of conversation messages
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            top_p: Nucleus sampling parameter
            stop: Stop sequences
            **kwargs: Additional parameters

        Returns:
            LLMResponse with generated content and metadata
        """
        client = self._get_client()
        start_time = time.monotonic()

        request_kwargs: dict[str, object] = {
            "model": self.model,
            "messages": self._prepare_messages(messages),
            "temperature": temperature,
            "top_p": top_p,
        }
        if max_tokens is not None:
            request_kwargs["max_tokens"] = max_tokens
        if stop:
            request_kwargs["stop"] = stop

        try:
            response = cast(
                _CompletionResponseProtocol,
                client.chat.completions.create(**request_kwargs),
            )
            raw = response.model_dump()
            latency_ms = (time.monotonic() - start_time) * 1000

            return ResponseConverter.from_openai_response(
                raw,
                model=self.model,
                provider="openclaw",
                latency_ms=latency_ms,
            )
        except _OPENCLAW_ADAPTER_OPERATION_ERRORS:
            raise

    async def acomplete(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        top_p: float = 1.0,
        stop: list[str] | None = None,
        **kwargs: object,
    ) -> LLMResponse:
        """Generate a completion asynchronously via OpenClaw gateway.

        Args:
            messages: List of conversation messages
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            top_p: Nucleus sampling parameter
            stop: Stop sequences
            **kwargs: Additional parameters

        Returns:
            LLMResponse with generated content and metadata
        """
        client = await self._get_async_client()
        start_time = time.monotonic()

        request_kwargs: dict[str, object] = {
            "model": self.model,
            "messages": self._prepare_messages(messages),
            "temperature": temperature,
            "top_p": top_p,
        }
        if max_tokens is not None:
            request_kwargs["max_tokens"] = max_tokens
        if stop:
            request_kwargs["stop"] = stop

        try:
            response = cast(
                _CompletionResponseProtocol,
                await client.chat.completions.create(**request_kwargs),
            )
            raw = response.model_dump()
            latency_ms = (time.monotonic() - start_time) * 1000

            return ResponseConverter.from_openai_response(
                raw,
                model=self.model,
                provider="openclaw",
                latency_ms=latency_ms,
            )
        except _OPENCLAW_ADAPTER_OPERATION_ERRORS:
            raise

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
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            top_p: Nucleus sampling parameter
            stop: Stop sequences
            **kwargs: Additional parameters

        Yields:
            Generated text chunks
        """
        client = self._get_client()

        request_kwargs: dict[str, object] = {
            "model": self.model,
            "messages": self._prepare_messages(messages),
            "temperature": temperature,
            "top_p": top_p,
            "stream": True,
        }
        if max_tokens is not None:
            request_kwargs["max_tokens"] = max_tokens
        if stop:
            request_kwargs["stop"] = stop

        try:
            response = client.chat.completions.create(**request_kwargs)
            for chunk in cast(Iterator[_ChunkProtocol], response):
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except _OPENCLAW_ADAPTER_OPERATION_ERRORS:
            raise

    async def astream(
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
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            top_p: Nucleus sampling parameter
            stop: Stop sequences
            **kwargs: Additional parameters

        Yields:
            Generated text chunks
        """
        client = await self._get_async_client()

        request_kwargs: dict[str, object] = {
            "model": self.model,
            "messages": self._prepare_messages(messages),
            "temperature": temperature,
            "top_p": top_p,
            "stream": True,
        }
        if max_tokens is not None:
            request_kwargs["max_tokens"] = max_tokens
        if stop:
            request_kwargs["stop"] = stop

        try:
            response = await client.chat.completions.create(**request_kwargs)
            async for chunk in cast(AsyncIterator[_ChunkProtocol], response):
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except _OPENCLAW_ADAPTER_OPERATION_ERRORS:
            raise

    def count_tokens(self, messages: list[LLMMessage]) -> int:
        """Count tokens in messages (approximate).

        Uses tiktoken with cl100k_base encoding as a reasonable approximation
        for most models routed through OpenClaw.

        Args:
            messages: List of messages to count tokens for

        Returns:
            Approximate total token count
        """
        try:
            import tiktoken

            encoding = tiktoken.get_encoding("cl100k_base")
        except ImportError:
            # Rough estimate: ~4 chars per token
            return sum(len(msg.content) // 4 for msg in messages)

        total = 0
        for msg in messages:
            total += len(encoding.encode(msg.content))
            total += 4  # overhead per message (role, separators)
        total += 2  # reply priming
        return total

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
        pricing = self.MODEL_PRICING.get(
            self.model,
            {"prompt": 0.0, "completion": 0.0},
        )

        prompt_cost = (prompt_tokens / 1_000_000) * pricing["prompt"]
        completion_cost = (completion_tokens / 1_000_000) * pricing["completion"]

        return CostEstimate(
            prompt_cost_usd=prompt_cost,
            completion_cost_usd=completion_cost,
            total_cost_usd=prompt_cost + completion_cost,
            currency="USD",
            pricing_model=f"openclaw/{self.model}",
            constitutional_hash=self.constitutional_hash,
        )

    async def health_check(self) -> HealthCheckResult:
        """Check adapter health by pinging the OpenClaw gateway.

        Returns:
            HealthCheckResult with status and latency
        """
        start_time = time.monotonic()

        try:
            client = await self._get_async_client()
            await client.models.list()
            latency_ms = (time.monotonic() - start_time) * 1000

            return HealthCheckResult(
                status=AdapterStatus.HEALTHY,
                latency_ms=latency_ms,
                message="OpenClaw gateway is reachable",
                details={"gateway_url": self.config.gateway_url, "model": self.model},
                constitutional_hash=self.constitutional_hash,
            )
        except _OPENCLAW_ADAPTER_OPERATION_ERRORS as e:
            latency_ms = (time.monotonic() - start_time) * 1000
            return HealthCheckResult(
                status=AdapterStatus.UNHEALTHY,
                latency_ms=latency_ms,
                message=f"OpenClaw gateway unreachable: {e}",
                details={"gateway_url": self.config.gateway_url, "error": str(e)},
                constitutional_hash=self.constitutional_hash,
            )

    @property
    def streaming_mode(self) -> StreamingMode:
        """OpenClaw supports streaming via the OpenAI-compatible API."""
        return StreamingMode.SUPPORTED

    @property
    def provider_name(self) -> str:
        """Return the provider name."""
        return "openclaw"

    @property
    def supports_function_calling(self) -> bool:
        """Function calling support depends on the underlying model."""
        return True
