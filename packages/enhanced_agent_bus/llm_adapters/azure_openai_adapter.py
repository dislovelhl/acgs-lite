"""
ACGS-2 Enhanced Agent Bus - Azure OpenAI LLM Adapter
Constitutional Hash: cdd01ef066bc6cf2

Azure OpenAI adapter supporting enterprise features including managed identity,
private endpoints, deployment-based model selection, and content filtering.
"""

import asyncio
import time
from collections.abc import AsyncIterator, Callable, Iterator
from importlib import import_module
from typing import ClassVar, Protocol, cast

from enhanced_agent_bus.observability.structured_logging import get_logger

JSONDict = dict[str, object]

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
from .config import AzureOpenAIAdapterConfig
from .models import MessageConverter, ResponseConverter

# Logger
logger = get_logger(__name__)


class _CompletionsAPI(Protocol):
    def create(self, **kwargs: object) -> object: ...


class _ChatAPI(Protocol):
    completions: _CompletionsAPI


class _AzureOpenAIClientProtocol(Protocol):
    chat: _ChatAPI


class _EncoderProtocol(Protocol):
    def encode(self, text: str) -> list[int]: ...


_AZURE_OPENAI_ADAPTER_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
)


class AzureOpenAIAdapter(BaseLLMAdapter):
    """Azure OpenAI LLM adapter with enterprise features.

    Constitutional Hash: cdd01ef066bc6cf2

    Supports:
    - GPT-4 (all variants via Azure deployments)
    - GPT-3.5-turbo (via Azure deployments)
    - Managed Identity authentication (Azure AD)
    - Private endpoint connectivity
    - Deployment-based model selection
    - Content filtering integration
    - Azure-specific rate limiting
    - Streaming responses
    - Function/tool calling
    - Token counting with tiktoken
    - Cost estimation
    """

    # Type annotation for config - overrides base class dict config
    config: AzureOpenAIAdapterConfig  # type: ignore[assignment]

    # Model pricing per 1M tokens (USD) - same as OpenAI
    MODEL_PRICING: ClassVar[dict] = {
        "gpt-5.4": {"prompt": 2.00, "completion": 16.00},
        "gpt-5.3": {"prompt": 1.75, "completion": 14.00},
        "gpt-5.2": {"prompt": 1.75, "completion": 14.00},
        "gpt-5.1": {"prompt": 1.25, "completion": 10.00},
        "gpt-5": {"prompt": 1.25, "completion": 10.00},
        "gpt-5-mini": {"prompt": 0.25, "completion": 2.00},
        "gpt-5-nano": {"prompt": 0.05, "completion": 0.40},
        "gpt-4o": {"prompt": 2.50, "completion": 10.00},
        "gpt-4o-mini": {"prompt": 0.15, "completion": 0.60},
        "gpt-4.1": {"prompt": 2.00, "completion": 8.00},
        "gpt-4.1-mini": {"prompt": 0.40, "completion": 1.60},
        "gpt-4-turbo": {"prompt": 10.00, "completion": 30.00},
        "gpt-4": {"prompt": 30.00, "completion": 60.00},
        "gpt-3.5-turbo": {"prompt": 0.50, "completion": 1.50},
    }

    def __init__(
        self,
        config: AzureOpenAIAdapterConfig | None = None,
        deployment_name: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        retry_config: RetryConfig | None = None,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
        **kwargs: object,
    ) -> None:
        """Initialize Azure OpenAI adapter.

        Args:
            config: Azure OpenAI adapter configuration
            deployment_name: Azure deployment name (if config not provided)
            model: Model identifier (if config not provided)
            api_key: API key (if config not provided and not using managed identity)
            retry_config: Retry configuration
            constitutional_hash: Constitutional hash for compliance
            **kwargs: Additional configuration options
        """
        # Create default config if not provided
        if config is None:
            if deployment_name is None:
                raise ValueError("deployment_name is required when config is not provided")
            if model is None:
                model = "gpt-5.4"
            config = AzureOpenAIAdapterConfig.from_environment(
                deployment_name=deployment_name,
                model=model,
                **kwargs,
            )

        # Initialize base adapter
        super().__init__(
            model=config.model,
            api_key=api_key or config.get_api_key("AZURE_OPENAI_API_KEY"),
            retry_config=retry_config,
            constitutional_hash=constitutional_hash,
            **kwargs,
        )

        self.config = config
        self.deployment_name = config.deployment_name
        self._client: _AzureOpenAIClientProtocol | None = None
        self._async_client: _AzureOpenAIClientProtocol | None = None
        self._tiktoken_encoder: _EncoderProtocol | None = None
        self._credential: object | None = None

    def _get_credential(self) -> object | None:
        """Get Azure credential for managed identity authentication.

        Returns:
            Azure credential instance or None if not using managed identity

        Raises:
            ImportError: If azure-identity package is not installed
        """
        if not self.config.use_managed_identity:
            return None

        if self._credential is None:
            try:
                azure_identity = import_module("azure.identity")
                default_credential_cls = azure_identity.DefaultAzureCredential
            except ImportError:
                raise ImportError(
                    "azure-identity package is required for managed identity authentication. "
                    "Install with: pip install azure-identity>=1.15.0"
                ) from None

            self._credential = default_credential_cls()
            logger.info("Using Azure Managed Identity for authentication")

        return self._credential

    def _get_client(self) -> _AzureOpenAIClientProtocol:
        """Get or create synchronous Azure OpenAI client.

        Returns:
            AzureOpenAI client instance

        Raises:
            ImportError: If openai package is not installed
            ValueError: If configuration is invalid
        """
        if self._client is None:
            try:
                from openai import AzureOpenAI
            except ImportError:
                raise ImportError(
                    "openai package is required for Azure OpenAI adapter. "
                    "Install with: pip install openai>=1.0.0"
                ) from None

            # Validate configuration
            if not self.config.api_base and not self.config.azure_endpoint:
                raise ValueError(
                    "Azure OpenAI endpoint is required. Set AZURE_OPENAI_ENDPOINT "
                    "environment variable or provide azure_endpoint parameter."
                )

            client_kwargs: JSONDict = {
                "api_version": self.config.api_version,
                "azure_endpoint": self.config.azure_endpoint or self.config.api_base,
            }

            # Authentication: Managed Identity or API Key
            if self.config.use_managed_identity:
                credential = self._get_credential()
                client_kwargs["azure_ad_token_provider"] = credential
            else:
                if not self.api_key:
                    raise ValueError(
                        "Azure OpenAI API key is required when not using managed identity. "
                        "Set AZURE_OPENAI_API_KEY environment variable or provide api_key parameter."
                    )
                client_kwargs["api_key"] = self.api_key

            if self.config.timeout_seconds:
                client_kwargs["timeout"] = self.config.timeout_seconds

            self._client = cast(
                _AzureOpenAIClientProtocol,
                cast(object, cast(Callable[..., object], AzureOpenAI)(**client_kwargs)),
            )

        return self._client

    def _get_async_client(self) -> _AzureOpenAIClientProtocol:
        """Get or create asynchronous Azure OpenAI client.

        Returns:
            AsyncAzureOpenAI client instance

        Raises:
            ImportError: If openai package is not installed
            ValueError: If configuration is invalid
        """
        if self._async_client is None:
            try:
                from openai import AsyncAzureOpenAI
            except ImportError:
                raise ImportError(
                    "openai package is required for Azure OpenAI adapter. "
                    "Install with: pip install openai>=1.0.0"
                ) from None

            # Validate configuration
            if not self.config.api_base and not self.config.azure_endpoint:
                raise ValueError(
                    "Azure OpenAI endpoint is required. Set AZURE_OPENAI_ENDPOINT "
                    "environment variable or provide azure_endpoint parameter."
                )

            client_kwargs: JSONDict = {
                "api_version": self.config.api_version,
                "azure_endpoint": self.config.azure_endpoint or self.config.api_base,
            }

            # Authentication: Managed Identity or API Key
            if self.config.use_managed_identity:
                credential = self._get_credential()
                client_kwargs["azure_ad_token_provider"] = credential
            else:
                if not self.api_key:
                    raise ValueError(
                        "Azure OpenAI API key is required when not using managed identity. "
                        "Set AZURE_OPENAI_API_KEY environment variable or provide api_key parameter."
                    )
                client_kwargs["api_key"] = self.api_key

            if self.config.timeout_seconds:
                client_kwargs["timeout"] = self.config.timeout_seconds

            self._async_client = cast(
                _AzureOpenAIClientProtocol,
                cast(object, cast(Callable[..., object], AsyncAzureOpenAI)(**client_kwargs)),
            )

        return self._async_client

    def _get_tiktoken_encoder(self) -> _EncoderProtocol:
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
                    _EncoderProtocol, tiktoken.encoding_for_model(self.model)
                )
            except KeyError:
                # Fall back to cl100k_base for newer models
                logger.warning(
                    f"Model {self.model} not found in tiktoken, using cl100k_base encoding"
                )
                self._tiktoken_encoder = cast(
                    _EncoderProtocol, tiktoken.get_encoding("cl100k_base")
                )

        return self._tiktoken_encoder

    def _prepare_request_params(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        top_p: float = 1.0,
        stop: list[str] | None = None,
        stream: bool = False,
    ) -> JSONDict:
        """Prepare base request parameters for OpenAI API.

        Args:
            messages: List of conversation messages
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            top_p: Nucleus sampling parameter
            stop: Stop sequences
            stream: Whether to enable streaming

        Returns:
            Dictionary of request parameters
        """
        openai_messages = MessageConverter.to_openai_format(messages)

        request_params: JSONDict = {
            "model": self.deployment_name,
            "messages": openai_messages,
            "temperature": temperature,
            "top_p": top_p,
        }

        if max_tokens:
            request_params["max_tokens"] = max_tokens
        if stop:
            request_params["stop"] = stop
        if stream:
            request_params["stream"] = True

        return request_params

    def _add_optional_parameters(self, request_params: JSONDict, **kwargs: object) -> None:
        """Add optional parameters to request if present in kwargs.

        Args:
            request_params: Base request parameters to modify
            **kwargs: Optional parameters
        """
        optional_params = [
            "tools",
            "tool_choice",
            "response_format",
            "frequency_penalty",
            "presence_penalty",
        ]

        for param in optional_params:
            if kwargs.get(param):
                request_params[param] = kwargs[param]

    def _extract_content_filter_results(self, response: object, llm_response: LLMResponse) -> None:
        """Extract Azure-specific content filtering results.

        Args:
            response: Raw OpenAI response object
            llm_response: LLM response to update
        """
        prompt_filter_results = getattr(response, "prompt_filter_results", None)
        if prompt_filter_results is not None:
            llm_response.metadata.extra["prompt_filter_results"] = prompt_filter_results

        response_choices = getattr(response, "choices", None)
        if isinstance(response_choices, list) and response_choices:
            content_filter_results = getattr(response_choices[0], "content_filter_results", None)
            if content_filter_results is not None:
                llm_response.metadata.extra["content_filter_results"] = content_filter_results

    def _process_completion_response(self, response: object, start_time: float) -> LLMResponse:
        """Process completion response into LLMResponse.

        Args:
            response: Raw OpenAI response
            start_time: Request start time

        Returns:
            Processed LLM response
        """
        latency_ms = (time.time() - start_time) * 1000

        # Convert to standard response
        model_dump = getattr(response, "model_dump", None)
        response_dict = model_dump() if callable(model_dump) else {}
        llm_response = ResponseConverter.from_openai_response(
            response_dict, provider="azure_openai"
        )

        # Update metadata
        llm_response.metadata.latency_ms = latency_ms

        # Estimate cost
        llm_response.cost = self.estimate_cost(
            llm_response.usage.prompt_tokens,
            llm_response.usage.completion_tokens,
        )

        # Extract content filtering results
        self._extract_content_filter_results(response, llm_response)

        return llm_response

    @staticmethod
    def _extract_stream_content(chunk: object) -> str | None:
        """Extract content from a streaming chunk.

        Args:
            chunk: Stream chunk object

        Returns:
            Content string if present, None otherwise
        """
        choices = getattr(chunk, "choices", None)
        if isinstance(choices, list) and choices:
            delta = getattr(choices[0], "delta", None)
            content = getattr(delta, "content", None)
            if isinstance(content, str) and content:
                return content
        return None

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
            **kwargs: Additional Azure OpenAI-specific parameters

        Returns:
            LLMResponse with generated content and metadata

        Raises:
            Exception: On API or validation errors
        """
        # Validate messages
        self.validate_messages(messages)
        self.validate_constitutional_compliance()

        # Prepare request
        request_params = self._prepare_request_params(
            messages, temperature, max_tokens, top_p, stop
        )
        self._add_optional_parameters(request_params, **kwargs)

        # Execute request with retry logic
        start_time = time.time()
        client = self._get_client()

        try:
            response = client.chat.completions.create(**request_params)
            return self._process_completion_response(response, start_time)

        except _AZURE_OPENAI_ADAPTER_OPERATION_ERRORS as e:
            logger.error(f"Azure OpenAI completion error: {e}")
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
            **kwargs: Additional Azure OpenAI-specific parameters

        Returns:
            LLMResponse with generated content and metadata

        Raises:
            Exception: On API or validation errors
        """
        # Validate messages
        self.validate_messages(messages)
        self.validate_constitutional_compliance()

        # Prepare request
        request_params = self._prepare_request_params(
            messages, temperature, max_tokens, top_p, stop
        )
        self._add_optional_parameters(request_params, **kwargs)

        # Execute request with retry logic
        start_time = time.time()
        client = self._get_async_client()

        try:
            response_raw = client.chat.completions.create(**request_params)
            response = await response_raw if asyncio.iscoroutine(response_raw) else response_raw
            return self._process_completion_response(response, start_time)

        except _AZURE_OPENAI_ADAPTER_OPERATION_ERRORS as e:
            logger.error(f"Azure OpenAI async completion error: {e}")
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
            **kwargs: Additional Azure OpenAI-specific parameters

        Yields:
            Generated text chunks

        Raises:
            Exception: On API or validation errors
        """
        # Validate messages
        self.validate_messages(messages)
        self.validate_constitutional_compliance()

        # Prepare request
        request_params = self._prepare_request_params(
            messages, temperature, max_tokens, top_p, stop, stream=True
        )
        self._add_optional_parameters(request_params, **kwargs)

        # Execute streaming request
        client = self._get_client()

        try:
            stream_raw = client.chat.completions.create(**request_params)
            stream = (
                cast(Iterator[object], stream_raw) if hasattr(stream_raw, "__iter__") else iter(())
            )

            for chunk in stream:
                content = self._extract_stream_content(chunk)
                if content:
                    yield content

        except _AZURE_OPENAI_ADAPTER_OPERATION_ERRORS as e:
            logger.error(f"Azure OpenAI streaming error: {e}")
            raise

    async def _process_async_stream(self, stream_candidate: object) -> AsyncIterator[str]:
        """Process async stream and yield content.

        Args:
            stream_candidate: Stream object from OpenAI client

        Yields:
            Generated text chunks
        """
        if hasattr(stream_candidate, "__aiter__"):
            async for chunk in cast(AsyncIterator[object], stream_candidate):
                content = self._extract_stream_content(chunk)
                if content:
                    yield content
        elif hasattr(stream_candidate, "__iter__"):
            for chunk in cast(Iterator[object], stream_candidate):
                content = self._extract_stream_content(chunk)
                if content:
                    yield content

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
            **kwargs: Additional Azure OpenAI-specific parameters

        Yields:
            Generated text chunks

        Raises:
            Exception: On API or validation errors
        """
        # Validate messages
        self.validate_messages(messages)
        self.validate_constitutional_compliance()

        # Prepare request
        request_params = self._prepare_request_params(
            messages, temperature, max_tokens, top_p, stop, stream=True
        )
        self._add_optional_parameters(request_params, **kwargs)

        # Execute streaming request
        client = self._get_async_client()

        try:
            stream_raw = client.chat.completions.create(**request_params)
            stream_candidate = await stream_raw if asyncio.iscoroutine(stream_raw) else stream_raw

            async for content in self._process_async_stream(stream_candidate):
                yield content

        except _AZURE_OPENAI_ADAPTER_OPERATION_ERRORS as e:
            logger.error(f"Azure OpenAI async streaming error: {e}")
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
            logger.warning(f"Pricing not found for model {self.model}, using GPT-5.2 pricing")
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
            # Simple health check: try to access the deployment
            # Note: Azure OpenAI doesn't have a models.list() endpoint
            # We'll attempt a minimal completion request instead
            client = self._get_async_client()

            test_messages = [{"role": "user", "content": "test"}]

            health_check_raw = client.chat.completions.create(
                model=self.deployment_name,
                messages=test_messages,
                max_tokens=1,
            )
            if asyncio.iscoroutine(health_check_raw):
                await health_check_raw

            latency_ms = (time.time() - start_time) * 1000

            return HealthCheckResult(
                status=AdapterStatus.HEALTHY,
                latency_ms=latency_ms,
                message="Azure OpenAI deployment is accessible",
                details={
                    "model": self.model,
                    "deployment": self.deployment_name,
                    "provider": "azure_openai",
                    "endpoint": self.config.azure_endpoint or self.config.api_base,
                    "api_version": self.config.api_version,
                    "auth_type": (
                        "managed_identity" if self.config.use_managed_identity else "api_key"
                    ),
                },
                constitutional_hash=self.constitutional_hash,
            )

        except _AZURE_OPENAI_ADAPTER_OPERATION_ERRORS as e:
            latency_ms = (time.time() - start_time) * 1000
            logger.error(f"Azure OpenAI health check failed: {e}")

            return HealthCheckResult(
                status=AdapterStatus.UNHEALTHY,
                latency_ms=latency_ms,
                message=f"Health check failed: {e!s}",
                details={
                    "model": self.model,
                    "deployment": self.deployment_name,
                    "provider": "azure_openai",
                    "error": str(e),
                },
                constitutional_hash=self.constitutional_hash,
            )

    def get_streaming_mode(self) -> StreamingMode:
        """Get streaming support level for this adapter.

        Returns:
            StreamingMode.SUPPORTED (Azure OpenAI supports streaming)
        """
        return StreamingMode.SUPPORTED

    def get_provider_name(self) -> str:
        """Get the provider name for this adapter.

        Returns:
            Provider identifier "azure_openai"
        """
        return "azure_openai"


__all__ = ["AzureOpenAIAdapter"]
