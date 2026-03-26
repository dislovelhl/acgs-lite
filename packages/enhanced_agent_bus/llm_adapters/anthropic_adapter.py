"""
ACGS-2 Enhanced Agent Bus - Anthropic LLM Adapter
Constitutional Hash: 608508a9bd224290

Anthropic adapter supporting Claude 3 models (Opus, Sonnet, Haiku) with
constitutional AI features, streaming, and tool use capabilities.
"""

import time
from collections.abc import AsyncIterator, Iterator
from typing import ClassVar

try:
    from src.core.shared.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

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
from .config import AnthropicAdapterConfig
from .models import MessageConverter, ResponseConverter

# Logger
logger = get_logger(__name__)
_ANTHROPIC_ADAPTER_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
)


class AnthropicAdapter(BaseLLMAdapter):
    """Anthropic LLM adapter for Claude models.

    Constitutional Hash: 608508a9bd224290

    Supports:
    - Claude 3 Opus (most capable)
    - Claude 3.5 Sonnet (best performance/cost balance)
    - Claude 3 Sonnet
    - Claude 3 Haiku (fastest, most affordable)
    - Streaming responses
    - Tool use (function calling)
    - Token counting with Anthropic tokenizer
    - Cost estimation
    - Constitutional AI features
    """

    # Type annotation for config - overrides base class untyped dict config
    config: AnthropicAdapterConfig  # type: ignore[assignment]

    # Model pricing per 1M tokens (USD)
    # Updated as of February 2026
    MODEL_PRICING: ClassVar[dict] = {
        # Current generation
        "claude-opus-4-6": {"prompt": 5.00, "completion": 25.00},
        "claude-sonnet-4-6": {"prompt": 3.00, "completion": 15.00},
        "claude-haiku-4-5-20251001": {"prompt": 1.00, "completion": 5.00},
        # Previous generation (legacy)
        "claude-opus-4-5-20251101": {"prompt": 5.00, "completion": 25.00},
        "claude-opus-4-20250514": {"prompt": 15.00, "completion": 75.00},
        "claude-sonnet-4-20250514": {"prompt": 3.00, "completion": 15.00},
        "claude-3-7-sonnet-20250219": {"prompt": 3.00, "completion": 15.00},
        "claude-3-5-sonnet-20241022": {"prompt": 3.00, "completion": 15.00},
        "claude-3-5-sonnet-20240620": {"prompt": 3.00, "completion": 15.00},
        "claude-3-opus-20240229": {"prompt": 15.00, "completion": 75.00},
        "claude-3-sonnet-20240229": {"prompt": 3.00, "completion": 15.00},
        "claude-3-haiku-20240307": {"prompt": 0.25, "completion": 1.25},
    }

    def __init__(
        self,
        config: AnthropicAdapterConfig | None = None,
        model: str | None = None,
        api_key: str | None = None,
        retry_config: RetryConfig | None = None,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
        **kwargs: object,
    ) -> None:
        """Initialize Anthropic adapter.

        Args:
            config: Anthropic adapter configuration
            model: Model identifier (if config not provided)
            api_key: API key (if config not provided)
            retry_config: Retry configuration
            constitutional_hash: Constitutional hash for compliance
            **kwargs: Additional configuration options
        """
        # Create default config if not provided
        if config is None:
            if model is None:
                model = "claude-sonnet-4-6"
            config = AnthropicAdapterConfig.from_environment(model=model, **kwargs)

        # Initialize base adapter
        super().__init__(
            model=config.model,
            api_key=api_key or config.get_api_key("ANTHROPIC_API_KEY"),
            retry_config=retry_config,
            constitutional_hash=constitutional_hash,
            **kwargs,
        )

        self.config = config
        self._client: object | None = None
        self._async_client: object | None = None

    def validate_constitutional_compliance(self, **kwargs: object) -> None:
        """Validate constitutional compliance for Anthropic adapter.

        Checks that:
        - The constitutional hash is correctly set
        - The adapter config has a valid model and API key source

        Raises:
            ValueError: If constitutional compliance requirements are not met.
        """
        if not self.constitutional_hash:
            raise ValueError("Constitutional hash is required for Anthropic adapter compliance.")
        if self.constitutional_hash != CONSTITUTIONAL_HASH:
            logger.warning(
                "Anthropic adapter using non-standard constitutional hash: %s",
                self.constitutional_hash,
            )
        if not self.config.model:
            raise ValueError(
                "Anthropic adapter constitutional compliance requires a model to be configured."
            )

    def _get_client(self) -> object:
        """Get or create synchronous Anthropic client.

        Returns:
            Anthropic client instance

        Raises:
            ImportError: If anthropic package is not installed
            ValueError: If API key is not configured
        """
        if self._client is None:
            try:
                import anthropic
            except ImportError:
                raise ImportError(
                    "anthropic package is required for Anthropic adapter. "
                    "Install with: pip install anthropic>=0.18.0"
                ) from None

            if not self.api_key:
                raise ValueError(
                    "Anthropic API key is required. Set ANTHROPIC_API_KEY environment "
                    "variable or provide api_key parameter."
                )

            client_kwargs: JSONDict = {
                "api_key": self.api_key,
            }

            if self.config.api_base:
                client_kwargs["base_url"] = self.config.api_base

            if self.config.timeout_seconds:
                client_kwargs["timeout"] = self.config.timeout_seconds

            self._client = anthropic.Anthropic(**client_kwargs)

        return self._client

    def _get_async_client(self) -> object:
        """Get or create asynchronous Anthropic client.

        Returns:
            AsyncAnthropic client instance

        Raises:
            ImportError: If anthropic package is not installed
            ValueError: If API key is not configured
        """
        if self._async_client is None:
            try:
                import anthropic
            except ImportError:
                raise ImportError(
                    "anthropic package is required for Anthropic adapter. "
                    "Install with: pip install anthropic>=0.18.0"
                ) from None

            if not self.api_key:
                raise ValueError(
                    "Anthropic API key is required. Set ANTHROPIC_API_KEY environment "
                    "variable or provide api_key parameter."
                )

            client_kwargs: JSONDict = {
                "api_key": self.api_key,
            }

            if self.config.api_base:
                client_kwargs["base_url"] = self.config.api_base

            if self.config.timeout_seconds:
                client_kwargs["timeout"] = self.config.timeout_seconds

            self._async_client = anthropic.AsyncAnthropic(**client_kwargs)

        return self._async_client

    def _prepare_messages(self, messages: list[LLMMessage]) -> tuple[str | None, list[JSONDict]]:
        """Prepare messages for Anthropic API format.

        Args:
            messages: Standard LLM messages

        Returns:
            Tuple of (system_prompt, conversation_messages)
        """
        # Extract system messages (Anthropic requires separate system parameter)
        system_messages = [msg.content for msg in messages if msg.role == "system"]
        system_prompt = " ".join(system_messages) if system_messages else None

        # Convert conversation messages (excluding system)
        conversation_messages = [msg for msg in messages if msg.role != "system"]
        anthropic_messages = MessageConverter.to_anthropic_format(conversation_messages)

        return system_prompt, anthropic_messages

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
            temperature: Sampling temperature (0.0 to 1.0 for Claude)
            max_tokens: Maximum tokens to generate (required for Anthropic)
            top_p: Nucleus sampling parameter
            stop: Stop sequences
            **kwargs: Additional Anthropic-specific parameters

        Returns:
            LLMResponse with generated content and metadata

        Raises:
            Exception: On API or validation errors
        """
        # Validate messages
        self.validate_messages(messages)
        self.validate_constitutional_compliance()

        # Prepare request
        system_prompt, anthropic_messages = self._prepare_messages(messages)

        # Anthropic requires max_tokens
        if max_tokens is None:
            max_tokens = 4096  # Default reasonable value

        request_params = {
            "model": self.model,
            "messages": anthropic_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
        }

        if system_prompt:
            request_params["system"] = system_prompt

        if stop:
            request_params["stop_sequences"] = stop

        # Add optional parameters
        if kwargs.get("tools"):
            # Convert to Anthropic tool format
            request_params["tools"] = self._convert_tools_to_anthropic(kwargs["tools"])

        if kwargs.get("top_k"):
            request_params["top_k"] = kwargs["top_k"]

        # Execute request with retry logic
        start_time = time.time()
        client = self._get_client()

        try:
            response = client.messages.create(**request_params)
            latency_ms = (time.time() - start_time) * 1000

            # Convert to standard response
            response_dict = response.model_dump()
            llm_response = ResponseConverter.from_anthropic_response(response_dict)

            # Update metadata
            llm_response.metadata.latency_ms = latency_ms

            # Estimate cost
            llm_response.cost = self.estimate_cost(
                llm_response.usage.prompt_tokens,
                llm_response.usage.completion_tokens,
            )

            return llm_response

        except _ANTHROPIC_ADAPTER_OPERATION_ERRORS as e:
            logger.error(f"Anthropic completion error: {e}")
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
            temperature: Sampling temperature (0.0 to 1.0 for Claude)
            max_tokens: Maximum tokens to generate (required for Anthropic)
            top_p: Nucleus sampling parameter
            stop: Stop sequences
            **kwargs: Additional Anthropic-specific parameters

        Returns:
            LLMResponse with generated content and metadata

        Raises:
            Exception: On API or validation errors
        """
        # Validate messages
        self.validate_messages(messages)
        self.validate_constitutional_compliance()

        # Prepare request
        system_prompt, anthropic_messages = self._prepare_messages(messages)

        # Anthropic requires max_tokens
        if max_tokens is None:
            max_tokens = 4096  # Default reasonable value

        request_params = {
            "model": self.model,
            "messages": anthropic_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
        }

        if system_prompt:
            request_params["system"] = system_prompt

        if stop:
            request_params["stop_sequences"] = stop

        # Add optional parameters
        if kwargs.get("tools"):
            # Convert to Anthropic tool format
            request_params["tools"] = self._convert_tools_to_anthropic(kwargs["tools"])

        if kwargs.get("top_k"):
            request_params["top_k"] = kwargs["top_k"]

        # Execute request with retry logic
        start_time = time.time()
        client = self._get_async_client()

        try:
            response = await client.messages.create(**request_params)
            latency_ms = (time.time() - start_time) * 1000

            # Convert to standard response
            response_dict = response.model_dump()
            llm_response = ResponseConverter.from_anthropic_response(response_dict)

            # Update metadata
            llm_response.metadata.latency_ms = latency_ms

            # Estimate cost
            llm_response.cost = self.estimate_cost(
                llm_response.usage.prompt_tokens,
                llm_response.usage.completion_tokens,
            )

            return llm_response

        except _ANTHROPIC_ADAPTER_OPERATION_ERRORS as e:
            logger.error(f"Anthropic async completion error: {e}")
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
            temperature: Sampling temperature (0.0 to 1.0 for Claude)
            max_tokens: Maximum tokens to generate (required for Anthropic)
            top_p: Nucleus sampling parameter
            stop: Stop sequences
            **kwargs: Additional Anthropic-specific parameters

        Yields:
            Generated text chunks

        Raises:
            Exception: On API or validation errors
        """
        # Validate messages
        self.validate_messages(messages)
        self.validate_constitutional_compliance()

        # Prepare request
        system_prompt, anthropic_messages = self._prepare_messages(messages)

        # Anthropic requires max_tokens
        if max_tokens is None:
            max_tokens = 4096  # Default reasonable value

        request_params = {
            "model": self.model,
            "messages": anthropic_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
        }

        if system_prompt:
            request_params["system"] = system_prompt

        if stop:
            request_params["stop_sequences"] = stop

        # Add optional parameters
        if kwargs.get("tools"):
            request_params["tools"] = self._convert_tools_to_anthropic(kwargs["tools"])

        if kwargs.get("top_k"):
            request_params["top_k"] = kwargs["top_k"]

        # Execute streaming request
        client = self._get_client()

        try:
            with client.messages.stream(**request_params) as stream:
                for text in stream.text_stream:
                    yield text

        except _ANTHROPIC_ADAPTER_OPERATION_ERRORS as e:
            logger.error(f"Anthropic streaming error: {e}")
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
            temperature: Sampling temperature (0.0 to 1.0 for Claude)
            max_tokens: Maximum tokens to generate (required for Anthropic)
            top_p: Nucleus sampling parameter
            stop: Stop sequences
            **kwargs: Additional Anthropic-specific parameters

        Yields:
            Generated text chunks

        Raises:
            Exception: On API or validation errors
        """
        # Validate messages
        self.validate_messages(messages)
        self.validate_constitutional_compliance()

        # Prepare request
        system_prompt, anthropic_messages = self._prepare_messages(messages)

        # Anthropic requires max_tokens
        if max_tokens is None:
            max_tokens = 4096  # Default reasonable value

        request_params = {
            "model": self.model,
            "messages": anthropic_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
        }

        if system_prompt:
            request_params["system"] = system_prompt

        if stop:
            request_params["stop_sequences"] = stop

        # Add optional parameters
        if kwargs.get("tools"):
            request_params["tools"] = self._convert_tools_to_anthropic(kwargs["tools"])

        if kwargs.get("top_k"):
            request_params["top_k"] = kwargs["top_k"]

        # Execute streaming request
        client = self._get_async_client()

        try:
            async with client.messages.stream(**request_params) as stream:
                async for text in stream.text_stream:
                    yield text

        except _ANTHROPIC_ADAPTER_OPERATION_ERRORS as e:
            logger.error(f"Anthropic async streaming error: {e}")
            raise

    def count_tokens(self, messages: list[LLMMessage]) -> int:
        """Count tokens in messages for the current model.

        Args:
            messages: List of messages to count tokens for

        Returns:
            Total token count

        Note:
            Uses Anthropic's client.count_tokens() method for accurate counting.
            Falls back to rough estimation if count_tokens is not available.
        """
        try:
            client = self._get_client()

            # Prepare messages in Anthropic format
            system_prompt, anthropic_messages = self._prepare_messages(messages)

            # Use Anthropic's token counting if available
            if hasattr(client, "count_tokens"):
                count_params = {
                    "model": self.model,
                    "messages": anthropic_messages,
                }
                if system_prompt:
                    count_params["system"] = system_prompt

                result = client.count_tokens(**count_params)
                return result.input_tokens  # type: ignore[no-any-return]
            else:
                # Fallback: rough estimation (4 chars ≈ 1 token for English)
                total_chars = 0
                for msg in messages:
                    total_chars += len(msg.role) + len(msg.content)
                return total_chars // 4

        except _ANTHROPIC_ADAPTER_OPERATION_ERRORS as e:
            logger.warning(f"Token counting error, using fallback: {e}")
            # Fallback estimation
            total_chars = sum(len(msg.role) + len(msg.content) for msg in messages)
            return total_chars // 4

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

        # Default to Claude Sonnet 4.6 pricing if model not found
        if pricing is None:
            logger.warning(
                f"Pricing not found for model {self.model}, using Claude Sonnet 4.6 pricing"
            )
            pricing = self.MODEL_PRICING["claude-sonnet-4-6"]

        # Calculate costs (pricing is per 1M tokens)
        prompt_cost = (prompt_tokens / 1_000_000.0) * pricing["prompt"]
        completion_cost = (completion_tokens / 1_000_000.0) * pricing["completion"]
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
            # Simple health check: send minimal message
            client = self._get_async_client()

            # Use a minimal message for health check
            await client.messages.create(
                model=self.model,
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=10,
            )

            latency_ms = (time.time() - start_time) * 1000

            return HealthCheckResult(
                status=AdapterStatus.HEALTHY,
                latency_ms=latency_ms,
                message="Anthropic API is accessible",
                details={
                    "model": self.model,
                    "provider": "anthropic",
                    "api_base": self.config.api_base or "https://api.anthropic.com",
                    "api_version": self.config.api_version,
                },
                constitutional_hash=self.constitutional_hash,
            )

        except _ANTHROPIC_ADAPTER_OPERATION_ERRORS as e:
            latency_ms = (time.time() - start_time) * 1000
            logger.error(f"Anthropic health check failed: {e}")

            return HealthCheckResult(
                status=AdapterStatus.UNHEALTHY,
                latency_ms=latency_ms,
                message=f"Health check failed: {e!s}",
                details={
                    "model": self.model,
                    "provider": "anthropic",
                    "error": str(e),
                },
                constitutional_hash=self.constitutional_hash,
            )

    def get_streaming_mode(self) -> StreamingMode:
        """Get streaming support level for this adapter.

        Returns:
            StreamingMode.SUPPORTED (Anthropic supports streaming)
        """
        return StreamingMode.SUPPORTED

    def get_provider_name(self) -> str:
        """Get the provider name for this adapter.

        Returns:
            Provider identifier "anthropic"
        """
        return "anthropic"

    def _convert_tools_to_anthropic(self, tools: list[JSONDict]) -> list[JSONDict]:
        """Convert standard tool definitions to Anthropic format.

        Args:
            tools: Standard tool definitions

        Returns:
            Anthropic-formatted tool definitions
        """
        anthropic_tools = []
        for tool in tools:
            if tool.get("type") == "function" and "function" in tool:
                func = tool["function"]
                anthropic_tools.append(
                    {
                        "name": func["name"],
                        "description": func.get("description", ""),
                        "input_schema": func.get("parameters", {}),
                    }
                )
        return anthropic_tools


__all__ = ["AnthropicAdapter"]
