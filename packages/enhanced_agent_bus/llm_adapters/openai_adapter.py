"""
ACGS-2 Enhanced Agent Bus - OpenAI LLM Adapter
Constitutional Hash: 608508a9bd224290

OpenAI adapter supporting GPT-4, GPT-3.5, and future models with streaming
and function calling capabilities.
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
from .config import OpenAIAdapterConfig
from .models import MessageConverter, ResponseConverter

# Logger
logger = get_logger(__name__)
_OPENAI_ADAPTER_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
)


class _TokenEncoderProtocol(Protocol):
    def encode(self, text: str) -> list[int]: ...


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


class OpenAIAdapter(BaseLLMAdapter):
    """OpenAI LLM adapter for GPT models.

    Constitutional Hash: 608508a9bd224290

    Supports:
    - GPT-4 (all variants: turbo, vision, etc.)
    - GPT-3.5-turbo
    - Future GPT models
    - Streaming responses
    - Function/tool calling
    - Token counting with tiktoken
    - Cost estimation
    - Rate limit compliance
    """

    config: OpenAIAdapterConfig  # type: ignore[assignment]

    # Model pricing per 1M tokens (USD)
    # Updated as of March 2026
    MODEL_PRICING: ClassVar[dict] = {
        # Current generation (GPT-5.x)
        "gpt-5.4": {"prompt": 2.00, "completion": 16.00},
        "gpt-5.3": {"prompt": 1.75, "completion": 14.00},
        "gpt-5.2": {"prompt": 1.75, "completion": 14.00},
        "gpt-5.1": {"prompt": 1.25, "completion": 10.00},
        "gpt-5": {"prompt": 1.25, "completion": 10.00},
        "gpt-5-mini": {"prompt": 0.25, "completion": 2.00},
        "gpt-5-nano": {"prompt": 0.05, "completion": 0.40},
        # Previous generation (GPT-4.x) — deprecated Feb 13 2026
        "gpt-4o": {"prompt": 2.50, "completion": 10.00},
        "gpt-4o-mini": {"prompt": 0.15, "completion": 0.60},
        "gpt-4.1": {"prompt": 2.00, "completion": 8.00},
        "gpt-4.1-mini": {"prompt": 0.40, "completion": 1.60},
        "gpt-4.1-nano": {"prompt": 0.10, "completion": 0.40},
        # Legacy (kept for backward compatibility)
        "gpt-4-turbo": {"prompt": 10.00, "completion": 30.00},
        "gpt-4": {"prompt": 30.00, "completion": 60.00},
        "gpt-3.5-turbo": {"prompt": 0.50, "completion": 1.50},
        # Moonshot AI (Kimi) models - OpenAI-compatible API
        "kimi-k2.5-free": {"prompt": 0.0, "completion": 0.0},
        "kimi-k2.5": {"prompt": 1.00, "completion": 3.00},
    }

    def __init__(
        self,
        config: OpenAIAdapterConfig | None = None,
        model: str | None = None,
        api_key: str | None = None,
        retry_config: RetryConfig | None = None,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
        **kwargs: object,
    ) -> None:
        """Initialize OpenAI adapter.

        Args:
            config: OpenAI adapter configuration
            model: Model identifier (if config not provided)
            api_key: API key (if config not provided)
            retry_config: Retry configuration
            constitutional_hash: Constitutional hash for compliance
            **kwargs: Additional configuration options
        """
        # Create default config if not provided
        if config is None:
            if model is None:
                model = "gpt-5.4"
            config = OpenAIAdapterConfig.from_environment(model=model, **kwargs)

        # Initialize base adapter
        super().__init__(
            model=config.model,
            api_key=api_key or config.get_api_key("OPENAI_API_KEY"),
            retry_config=retry_config,
            constitutional_hash=constitutional_hash,
            **kwargs,
        )

        self.config = config
        self._client: _OpenAIClientProtocol | None = None
        self._async_client: _AsyncOpenAIClientProtocol | None = None
        self._tiktoken_encoder: _TokenEncoderProtocol | None = None

    def validate_constitutional_compliance(self, **kwargs: object) -> None:
        """Validate constitutional compliance for OpenAI adapter."""
        if not self.constitutional_hash:
            raise ValueError("Constitutional hash is required for OpenAI adapter compliance.")
        if self.constitutional_hash != CONSTITUTIONAL_HASH:
            logger.warning(
                "OpenAI adapter using non-standard constitutional hash: %s",
                self.constitutional_hash,
            )
        if not self.model:
            raise ValueError("OpenAI adapter constitutional compliance requires a model.")

    def _get_client(self) -> _OpenAIClientProtocol:
        """Get or create synchronous OpenAI client.

        Returns:
            OpenAI client instance

        Raises:
            ImportError: If openai package is not installed
            ValueError: If API key is not configured
        """
        if self._client is None:
            try:
                import openai
            except ImportError:
                raise ImportError(
                    "openai package is required for OpenAI adapter. "
                    "Install with: pip install openai>=1.0.0"
                ) from None

            if not self.api_key:
                raise ValueError(
                    "OpenAI API key is required. Set OPENAI_API_KEY environment "
                    "variable or provide api_key parameter."
                )

            self._client = cast(
                _OpenAIClientProtocol,
                cast(
                    object,
                    openai.OpenAI(
                        api_key=self.api_key,
                        base_url=self.config.api_base,
                        organization=self.config.organization,
                        timeout=self.config.timeout_seconds,
                    ),
                ),
            )

        return self._client

    def _get_async_client(self) -> _AsyncOpenAIClientProtocol:
        """Get or create asynchronous OpenAI client.

        Returns:
            AsyncOpenAI client instance

        Raises:
            ImportError: If openai package is not installed
            ValueError: If API key is not configured
        """
        if self._async_client is None:
            try:
                import openai
            except ImportError:
                raise ImportError(
                    "openai package is required for OpenAI adapter. "
                    "Install with: pip install openai>=1.0.0"
                ) from None

            if not self.api_key:
                raise ValueError(
                    "OpenAI API key is required. Set OPENAI_API_KEY environment "
                    "variable or provide api_key parameter."
                )

            self._async_client = cast(
                _AsyncOpenAIClientProtocol,
                cast(
                    object,
                    openai.AsyncOpenAI(
                        api_key=self.api_key,
                        base_url=self.config.api_base,
                        organization=self.config.organization,
                        timeout=self.config.timeout_seconds,
                    ),
                ),
            )

        return self._async_client

    def _get_tiktoken_encoder(self) -> _TokenEncoderProtocol:
        """Get or create tiktoken encoder for token counting.

        Returns:
            Tiktoken encoder instance

        Raises:
            ImportError: If tiktoken package is not installed
        """
        if self._tiktoken_encoder is None:
            try:
                import tiktoken
            except ImportError:
                raise ImportError(
                    "tiktoken package is required for token counting. "
                    "Install with: pip install tiktoken"
                ) from None

            # Get encoding for model
            try:
                self._tiktoken_encoder = cast(
                    _TokenEncoderProtocol,
                    tiktoken.encoding_for_model(self.model),
                )
            except KeyError:
                # Fall back to cl100k_base for newer models
                logger.warning(
                    f"Model {self.model} not found in tiktoken, using cl100k_base encoding"
                )
                self._tiktoken_encoder = cast(
                    _TokenEncoderProtocol,
                    tiktoken.get_encoding("cl100k_base"),
                )

        return self._tiktoken_encoder

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
            **kwargs: Additional OpenAI-specific parameters

        Returns:
            LLMResponse with generated content and metadata

        Raises:
            Exception: On API or validation errors
        """
        # Validate messages
        self.validate_messages(messages)
        self.validate_constitutional_compliance()

        # Prepare request
        openai_messages = MessageConverter.to_openai_format(messages)

        request_params: dict[str, object] = {
            "model": self.model,
            "messages": openai_messages,
            "temperature": temperature,
            "top_p": top_p,
        }

        if max_tokens:
            request_params["max_tokens"] = max_tokens
        if stop:
            request_params["stop"] = stop

        # Add optional parameters
        if kwargs.get("tools"):
            request_params["tools"] = kwargs["tools"]
        if kwargs.get("tool_choice"):
            request_params["tool_choice"] = kwargs["tool_choice"]
        if kwargs.get("response_format"):
            request_params["response_format"] = kwargs["response_format"]
        if kwargs.get("frequency_penalty"):
            request_params["frequency_penalty"] = kwargs["frequency_penalty"]
        if kwargs.get("presence_penalty"):
            request_params["presence_penalty"] = kwargs["presence_penalty"]

        # Execute request with retry logic
        start_time = time.time()
        client = self._get_client()

        try:
            response = cast(
                _CompletionResponseProtocol,
                client.chat.completions.create(**cast(dict[str, object], request_params)),
            )
            latency_ms = (time.time() - start_time) * 1000

            # Convert to standard response
            response_dict = response.model_dump()
            llm_response = ResponseConverter.from_openai_response(response_dict, provider="openai")

            # Update metadata
            llm_response.metadata.latency_ms = latency_ms

            # Estimate cost
            llm_response.cost = self.estimate_cost(
                llm_response.usage.prompt_tokens,
                llm_response.usage.completion_tokens,
            )

            return llm_response

        except _OPENAI_ADAPTER_OPERATION_ERRORS as e:
            logger.error(f"OpenAI completion error: {e}")
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
        """Generate a completion asynchronously.

        Args:
            messages: List of conversation messages
            temperature: Sampling temperature (0.0 to 2.0)
            max_tokens: Maximum tokens to generate
            top_p: Nucleus sampling parameter
            stop: Stop sequences
            **kwargs: Additional OpenAI-specific parameters

        Returns:
            LLMResponse with generated content and metadata

        Raises:
            Exception: On API or validation errors
        """
        # Validate messages
        self.validate_messages(messages)
        self.validate_constitutional_compliance()

        # Prepare request
        openai_messages = MessageConverter.to_openai_format(messages)

        request_params: dict[str, object] = {
            "model": self.model,
            "messages": openai_messages,
            "temperature": temperature,
            "top_p": top_p,
        }

        if max_tokens:
            request_params["max_tokens"] = max_tokens
        if stop:
            request_params["stop"] = stop

        # Add optional parameters
        if kwargs.get("tools"):
            request_params["tools"] = kwargs["tools"]
        if kwargs.get("tool_choice"):
            request_params["tool_choice"] = kwargs["tool_choice"]
        if kwargs.get("response_format"):
            request_params["response_format"] = kwargs["response_format"]
        if kwargs.get("frequency_penalty"):
            request_params["frequency_penalty"] = kwargs["frequency_penalty"]
        if kwargs.get("presence_penalty"):
            request_params["presence_penalty"] = kwargs["presence_penalty"]

        # Execute request with retry logic
        start_time = time.time()
        client = self._get_async_client()

        try:
            response = cast(
                _CompletionResponseProtocol,
                await client.chat.completions.create(**cast(dict[str, object], request_params)),
            )
            latency_ms = (time.time() - start_time) * 1000

            # Convert to standard response
            response_dict = response.model_dump()
            llm_response = ResponseConverter.from_openai_response(response_dict, provider="openai")

            # Update metadata
            llm_response.metadata.latency_ms = latency_ms

            # Estimate cost
            llm_response.cost = self.estimate_cost(
                llm_response.usage.prompt_tokens,
                llm_response.usage.completion_tokens,
            )

            return llm_response

        except _OPENAI_ADAPTER_OPERATION_ERRORS as e:
            logger.error(f"OpenAI async completion error: {e}")
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
            temperature: Sampling temperature (0.0 to 2.0)
            max_tokens: Maximum tokens to generate
            top_p: Nucleus sampling parameter
            stop: Stop sequences
            **kwargs: Additional OpenAI-specific parameters

        Yields:
            Generated text chunks

        Raises:
            Exception: On API or validation errors
        """
        # Validate messages
        self.validate_messages(messages)
        self.validate_constitutional_compliance()

        # Prepare request parameters
        request_params = self._build_streaming_params(
            messages, temperature, max_tokens, top_p, stop, **kwargs
        )

        # Execute streaming request
        client = self._get_client()

        try:
            stream = cast(
                Iterator[_ChunkProtocol],
                client.chat.completions.create(**cast(dict[str, object], request_params)),
            )

            yield from self._process_stream_chunks(stream)

        except _OPENAI_ADAPTER_OPERATION_ERRORS as e:
            logger.error(f"OpenAI streaming error: {e}")
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
            temperature: Sampling temperature (0.0 to 2.0)
            max_tokens: Maximum tokens to generate
            top_p: Nucleus sampling parameter
            stop: Stop sequences
            **kwargs: Additional OpenAI-specific parameters

        Yields:
            Generated text chunks

        Raises:
            Exception: On API or validation errors
        """
        # Validate messages
        self.validate_messages(messages)
        self.validate_constitutional_compliance()

        # Prepare request parameters
        request_params = self._build_streaming_params(
            messages, temperature, max_tokens, top_p, stop, **kwargs
        )

        # Execute streaming request
        client = self._get_async_client()

        try:
            stream = cast(
                AsyncIterator[_ChunkProtocol],
                await client.chat.completions.create(**cast(dict[str, object], request_params)),
            )

            async for chunk in stream:
                content = self._extract_chunk_content(chunk)
                if content:
                    yield content

        except _OPENAI_ADAPTER_OPERATION_ERRORS as e:
            logger.error(f"OpenAI async streaming error: {e}")
            raise

    def count_tokens(self, messages: list[LLMMessage]) -> int:
        """Count tokens in messages for the current model.

        Args:
            messages: List of messages to count tokens for

        Returns:
            Total token count

        Raises:
            ImportError: If tiktoken is not installed
        """
        encoder = self._get_tiktoken_encoder()

        # Count tokens per message
        total_tokens = 0

        for message in messages:
            # Every message follows <im_start>{role/name}\n{content}<im_end>\n
            total_tokens += 4  # Message formatting tokens

            # Role tokens
            total_tokens += len(encoder.encode(message.role))

            # Content tokens
            if message.content:
                total_tokens += len(encoder.encode(message.content))

            # Name tokens (if present)
            if message.name:
                total_tokens += len(encoder.encode(message.name))
                total_tokens += -1  # Role is omitted if name is present

        # Every reply is primed with <im_start>assistant
        total_tokens += 2

        return total_tokens

    def estimate_cost(
        self,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> CostEstimate:
        """Estimate cost for a completion request.

        Args:
            prompt_tokens: Number of tokens in the prompt
            completion_tokens: Number of completion tokens

        Returns:
            CostEstimate with pricing breakdown
        """
        # Find pricing for model (check exact match first, then prefix match)
        pricing = None
        for model_key, model_pricing in self.MODEL_PRICING.items():
            if self.model == model_key or self.model.startswith(model_key):
                pricing = model_pricing
                break

        # Default to GPT-5.2 pricing if model not found
        if pricing is None:
            logger.warning(f"Pricing not found for model {self.model}, using GPT-5.4 pricing")
            pricing = self.MODEL_PRICING["gpt-5.4"]

        # Calculate costs (pricing is per 1K tokens)
        prompt_cost = (prompt_tokens / 1000.0) * pricing["prompt"]
        completion_cost = (completion_tokens / 1000.0) * pricing["completion"]
        total_cost = prompt_cost + completion_cost

        return CostEstimate(
            prompt_cost_usd=prompt_cost,
            completion_cost_usd=completion_cost,
            total_cost_usd=total_cost,
            currency="USD",
            pricing_model=self.model,
            constitutional_hash=self.constitutional_hash,
        )

    async def health_check(self) -> HealthCheckResult:
        """Check adapter health and connectivity.

        Returns:
            HealthCheckResult with status and diagnostics

        Raises:
            Exception: On health check failures
        """
        start_time = time.time()

        try:
            # Simple health check: list models
            client = self._get_async_client()
            await client.models.list()

            latency_ms = (time.time() - start_time) * 1000

            return HealthCheckResult(
                status=AdapterStatus.HEALTHY,
                latency_ms=latency_ms,
                message="OpenAI API is accessible",
                details={
                    "model": self.model,
                    "provider": "openai",
                    "api_base": self.config.api_base or "https://api.openai.com/v1",
                },
                constitutional_hash=self.constitutional_hash,
            )

        except _OPENAI_ADAPTER_OPERATION_ERRORS as e:
            latency_ms = (time.time() - start_time) * 1000
            logger.error(f"OpenAI health check failed: {e}")

            return HealthCheckResult(
                status=AdapterStatus.UNHEALTHY,
                latency_ms=latency_ms,
                message=f"Health check failed: {e!s}",
                details={
                    "model": self.model,
                    "provider": "openai",
                    "error": str(e),
                },
                constitutional_hash=self.constitutional_hash,
            )

    def get_streaming_mode(self) -> StreamingMode:
        """Get streaming support level for this adapter.

        Returns:
            StreamingMode.SUPPORTED (OpenAI supports streaming)
        """
        return StreamingMode.SUPPORTED

    def get_provider_name(self) -> str:
        """Get the provider name for this adapter.

        Returns:
            Provider identifier "openai"
        """
        return "openai"

    def _build_streaming_params(
        self,
        messages: list[LLMMessage],
        temperature: float,
        max_tokens: int | None,
        top_p: float,
        stop: list[str] | None,
        **kwargs: object,
    ) -> dict[str, object]:
        """Build request parameters for streaming requests."""
        openai_messages = MessageConverter.to_openai_format(messages)

        request_params: dict[str, object] = {
            "model": self.model,
            "messages": openai_messages,
            "temperature": temperature,
            "top_p": top_p,
            "stream": True,
        }

        # Add standard optional parameters
        if max_tokens:
            request_params["max_tokens"] = max_tokens
        if stop:
            request_params["stop"] = stop

        # Add additional optional parameters
        self._add_optional_params(request_params, **kwargs)

        return request_params

    def _add_optional_params(self, request_params: dict[str, object], **kwargs: object) -> None:
        """Add optional parameters to request."""
        optional_param_keys = ["tools", "tool_choice", "frequency_penalty", "presence_penalty"]

        for key in optional_param_keys:
            if kwargs.get(key):
                request_params[key] = kwargs[key]

    def _extract_chunk_content(self, chunk: _ChunkProtocol) -> str | None:
        """Extract content from a streaming chunk."""
        if chunk.choices and len(chunk.choices) > 0:
            delta = chunk.choices[0].delta
            if delta.content:
                return delta.content
        return None

    def _process_stream_chunks(self, stream: Iterator[_ChunkProtocol]) -> Iterator[str]:
        """Process streaming chunks synchronously."""
        for chunk in stream:
            content = self._extract_chunk_content(chunk)
            if content:
                yield content


__all__ = ["OpenAIAdapter"]
