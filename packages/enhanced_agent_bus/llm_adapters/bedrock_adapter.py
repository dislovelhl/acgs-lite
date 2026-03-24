"""
ACGS-2 Enhanced Agent Bus - AWS Bedrock LLM Adapter
Constitutional Hash: cdd01ef066bc6cf2

AWS Bedrock adapter supporting multiple foundation models:
- Anthropic Claude (Opus, Sonnet, Haiku)
- Meta Llama (2, 3, 3.1, 3.2)
- Amazon Titan (Text, Embeddings)
- Cohere Command
- AI21 Jurassic

Includes IAM authentication, Guardrails integration, and streaming support.
"""

import asyncio
import json
import time
from collections.abc import AsyncIterator, Iterator
from typing import ClassVar

from enhanced_agent_bus.observability.structured_logging import get_logger

from .base import (
    CONSTITUTIONAL_HASH,
    AdapterStatus,
    BaseLLMAdapter,
    CompletionMetadata,
    CostEstimate,
    HealthCheckResult,
    LLMMessage,
    LLMResponse,
    RetryConfig,
    StreamingMode,
    TokenUsage,
)
from .config import AWSBedrockAdapterConfig
from .models import MessageConverter

# Logger
logger = get_logger(__name__)
BEDROCK_HEALTHCHECK_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    ConnectionError,
    OSError,
)

_BEDROCK_ADAPTER_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
)


class BedrockAdapter(BaseLLMAdapter):
    """AWS Bedrock LLM adapter for multiple foundation models.

    Constitutional Hash: cdd01ef066bc6cf2

    Supports:
    - Anthropic Claude models (via Bedrock)
    - Meta Llama models
    - Amazon Titan models
    - Cohere Command models
    - AI21 Jurassic models
    - Streaming responses (InvokeModelWithResponseStream)
    - IAM authentication (access keys or IAM roles)
    - Bedrock Guardrails integration
    - Region-aware configuration
    - Token counting and cost estimation
    """

    # Type annotation for config - overrides base class untyped dict config
    config: AWSBedrockAdapterConfig  # type: ignore[assignment]

    # Model pricing per 1M tokens (USD) - Bedrock pricing as of February 2026
    # Prices vary by region, these are us-east-1 base prices
    MODEL_PRICING: ClassVar[dict] = {
        # Anthropic Claude 4.x models (current generation)
        "anthropic.claude-opus-4-6-v1": {"prompt": 5.00, "completion": 25.00},
        "anthropic.claude-sonnet-4-6-v1:0": {"prompt": 3.00, "completion": 15.00},
        "anthropic.claude-haiku-4-5-20251001-v1:0": {"prompt": 1.00, "completion": 5.00},
        "anthropic.claude-opus-4-5-20251101-v1:0": {"prompt": 5.00, "completion": 25.00},
        "anthropic.claude-opus-4-20250514-v1:0": {"prompt": 15.00, "completion": 75.00},
        "anthropic.claude-sonnet-4-20250514-v1:0": {"prompt": 3.00, "completion": 15.00},
        # Anthropic Claude 3.x models (legacy)
        "anthropic.claude-3-7-sonnet-20250219-v1:0": {"prompt": 3.00, "completion": 15.00},
        "anthropic.claude-3-5-sonnet-20240620-v1:0": {"prompt": 3.00, "completion": 15.00},
        "anthropic.claude-3-5-sonnet-20241022-v2:0": {"prompt": 3.00, "completion": 15.00},
        "anthropic.claude-3-opus-20240229-v1:0": {"prompt": 15.00, "completion": 75.00},
        "anthropic.claude-3-sonnet-20240229-v1:0": {"prompt": 3.00, "completion": 15.00},
        "anthropic.claude-3-haiku-20240307-v1:0": {"prompt": 0.25, "completion": 1.25},
        # Meta Llama models
        "meta.llama3-2-1b-instruct-v1:0": {"prompt": 0.10, "completion": 0.10},
        "meta.llama3-2-3b-instruct-v1:0": {"prompt": 0.15, "completion": 0.15},
        "meta.llama3-2-11b-instruct-v1:0": {"prompt": 0.35, "completion": 0.35},
        "meta.llama3-2-90b-instruct-v1:0": {"prompt": 2.65, "completion": 2.65},
        "meta.llama3-1-8b-instruct-v1:0": {"prompt": 0.22, "completion": 0.22},
        "meta.llama3-1-70b-instruct-v1:0": {"prompt": 0.99, "completion": 0.99},
        "meta.llama3-70b-instruct-v1:0": {"prompt": 2.65, "completion": 3.50},
        "meta.llama3-8b-instruct-v1:0": {"prompt": 0.40, "completion": 0.60},
        # Amazon Titan models
        "amazon.titan-text-premier-v1:0": {"prompt": 0.50, "completion": 1.50},
        "amazon.titan-text-express-v1": {"prompt": 0.20, "completion": 0.60},
        "amazon.titan-text-lite-v1": {"prompt": 0.15, "completion": 0.20},
        # Cohere models
        "cohere.command-r-plus-v1:0": {"prompt": 3.00, "completion": 15.00},
        "cohere.command-r-v1:0": {"prompt": 0.50, "completion": 1.50},
        "cohere.command-text-v14": {"prompt": 1.50, "completion": 2.00},
        "cohere.command-light-text-v14": {"prompt": 0.30, "completion": 0.60},
        # AI21 models
        "ai21.jamba-instruct-v1:0": {"prompt": 0.50, "completion": 0.70},
        "ai21.j2-ultra-v1": {"prompt": 15.00, "completion": 15.00},
        "ai21.j2-mid-v1": {"prompt": 10.00, "completion": 10.00},
    }

    # Model provider mapping (inferred from model ID)
    PROVIDER_MAP: ClassVar[dict] = {
        "anthropic": "anthropic",
        "meta": "meta",
        "amazon": "amazon",
        "cohere": "cohere",
        "ai21": "ai21",
    }

    def __init__(
        self,
        config: AWSBedrockAdapterConfig | None = None,
        model: str | None = None,
        region: str | None = None,
        retry_config: RetryConfig | None = None,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
        **kwargs: object,
    ) -> None:
        """Initialize AWS Bedrock adapter.

        Args:
            config: Bedrock adapter configuration
            model: Model identifier (if config not provided)
            region: AWS region (if config not provided)
            retry_config: Retry configuration
            constitutional_hash: Constitutional hash for compliance
            **kwargs: Additional configuration options
        """
        # Create default config if not provided
        if config is None:
            if model is None:
                model = "anthropic.claude-sonnet-4-6-v1:0"
            config = AWSBedrockAdapterConfig.from_environment(
                model=model,
                region=region,
                **kwargs,
            )

        # Initialize base adapter
        # For Bedrock, we don't use traditional API keys
        super().__init__(
            model=config.model,
            api_key=None,  # Bedrock uses IAM authentication
            retry_config=retry_config,
            constitutional_hash=constitutional_hash,
            **kwargs,
        )

        self.config = config
        self._client: object | None = None
        self._async_client: object | None = None
        self._provider: str | None = None

    def _get_provider(self) -> str:
        """Get the provider name from model ID.

        Returns:
            Provider name (anthropic, meta, amazon, cohere, ai21)
        """
        if self._provider is None:
            # Extract provider from model ID (e.g., "anthropic.claude-3-opus...")
            for prefix, provider in self.PROVIDER_MAP.items():
                if self.model.startswith(prefix):
                    self._provider = provider
                    break

            if self._provider is None:
                logger.warning(
                    f"Unknown provider for model {self.model}, defaulting to 'anthropic'"
                )
                self._provider = "anthropic"

        return self._provider

    def _get_client(self) -> object:
        """Get or create synchronous Bedrock client.

        Returns:
            Boto3 Bedrock Runtime client instance

        Raises:
            ImportError: If boto3 package is not installed
            Exception: On AWS authentication errors
        """
        if self._client is None:
            try:
                import boto3
            except ImportError:
                raise ImportError(
                    "boto3 package is required for AWS Bedrock adapter. "
                    "Install with: pip install boto3>=1.34.0"
                ) from None

            # Prepare credentials
            client_kwargs = {
                "service_name": "bedrock-runtime",
                "region_name": self.config.region,
            }

            # Add explicit credentials if provided
            if self.config.aws_access_key_id:
                client_kwargs["aws_access_key_id"] = (
                    self.config.aws_access_key_id.get_secret_value()
                )
            if self.config.aws_secret_access_key:
                client_kwargs["aws_secret_access_key"] = (
                    self.config.aws_secret_access_key.get_secret_value()
                )
            if self.config.aws_session_token:
                client_kwargs["aws_session_token"] = (
                    self.config.aws_session_token.get_secret_value()
                )

            self._client = boto3.client(**client_kwargs)

        return self._client

    def _get_async_client(self) -> object | None:
        """Get or create asynchronous Bedrock client.

        Returns:
            Aioboto3 Bedrock Runtime client instance

        Raises:
            ImportError: If aioboto3 package is not installed
            Exception: On AWS authentication errors
        """
        if self._async_client is None:
            try:
                import aioboto3
            except ImportError:
                # Fallback to sync client wrapped in asyncio
                logger.warning(
                    "aioboto3 not installed, using sync client with asyncio.to_thread(). "
                    "Install aioboto3 for better async performance: pip install aioboto3"
                )
                return None

            # Prepare credentials
            session_kwargs = {}
            if self.config.aws_access_key_id:
                session_kwargs["aws_access_key_id"] = (
                    self.config.aws_access_key_id.get_secret_value()
                )
            if self.config.aws_secret_access_key:
                session_kwargs["aws_secret_access_key"] = (
                    self.config.aws_secret_access_key.get_secret_value()
                )
            if self.config.aws_session_token:
                session_kwargs["aws_session_token"] = (
                    self.config.aws_session_token.get_secret_value()
                )

            self._async_client = aioboto3.Session(**session_kwargs)

        return self._async_client

    def _build_request_body(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        top_p: float = 1.0,
        stop: list[str] | None = None,
        **kwargs: object,
    ) -> str:
        """Build request body for Bedrock InvokeModel.

        Args:
            messages: List of conversation messages
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            top_p: Nucleus sampling parameter
            stop: Stop sequences
            **kwargs: Additional provider-specific parameters

        Returns:
            JSON string of request body
        """
        provider = self._get_provider()
        max_tokens = max_tokens or 4096

        # Provider-specific body builders lookup table
        body_builders = {
            "anthropic": self._build_anthropic_body,
            "meta": self._build_meta_body,
            "amazon": self._build_amazon_body,
            "cohere": self._build_cohere_body,
            "ai21": self._build_ai21_body,
        }

        builder = body_builders.get(provider, self._build_generic_body)
        body = builder(messages, temperature, max_tokens, top_p, stop, **kwargs)
        return json.dumps(body)

    def _build_anthropic_body(
        self,
        messages: list[LLMMessage],
        temperature: float,
        max_tokens: int,
        top_p: float,
        stop: list[str] | None,
        **kwargs: object,
    ) -> dict:
        """Build Anthropic Claude request body."""
        system_messages = [msg.content for msg in messages if msg.role == "system"]
        conversation_messages = [msg for msg in messages if msg.role != "system"]

        body = {
            "messages": MessageConverter.to_anthropic_format(conversation_messages),
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "anthropic_version": "bedrock-2023-05-31",
        }

        if system_messages:
            body["system"] = " ".join(system_messages)
        if stop:
            body["stop_sequences"] = stop
        if kwargs.get("top_k"):
            body["top_k"] = kwargs["top_k"]

        return body

    def _build_meta_body(
        self,
        messages: list[LLMMessage],
        temperature: float,
        max_tokens: int,
        top_p: float,
        stop: list[str] | None,
        **kwargs: object,
    ) -> dict:
        """Build Meta Llama request body."""
        return {
            "prompt": self._format_generic_prompt(
                messages,
                system_prefix="<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n",
                system_suffix="<|eot_id|>",
                user_prefix="<|start_header_id|>user<|end_header_id|>\n",
                user_suffix="<|eot_id|>",
                assistant_prefix="<|start_header_id|>assistant<|end_header_id|>\n",
                assistant_suffix="<|eot_id|>",
                final_suffix="<|start_header_id|>assistant<|end_header_id|>",
            ),
            "max_gen_len": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
        }

    def _build_amazon_body(
        self,
        messages: list[LLMMessage],
        temperature: float,
        max_tokens: int,
        top_p: float,
        stop: list[str] | None,
        **kwargs: object,
    ) -> dict:
        """Build Amazon Titan request body."""
        body = {
            "inputText": self._format_generic_prompt(
                messages,
                system_prefix="Instructions: ",
                user_prefix="User: ",
                assistant_prefix="Assistant: ",
                final_suffix="Assistant:",
            ),
            "textGenerationConfig": {
                "maxTokenCount": max_tokens,
                "temperature": temperature,
                "topP": top_p,
            },
        }

        if stop:
            body["textGenerationConfig"]["stopSequences"] = stop

        return body

    def _build_cohere_body(
        self,
        messages: list[LLMMessage],
        temperature: float,
        max_tokens: int,
        top_p: float,
        stop: list[str] | None,
        **kwargs: object,
    ) -> dict:
        """Build Cohere request body."""
        body = {
            "message": messages[-1].content if messages else "",
            "max_tokens": max_tokens,
            "temperature": temperature,
            "p": top_p,
        }

        # Add chat history if available
        if len(messages) > 1:
            chat_history = [
                {
                    "role": "USER" if msg.role == "user" else "CHATBOT",
                    "message": msg.content,
                }
                for msg in messages[:-1]
            ]
            body["chat_history"] = chat_history

        return body

    def _build_ai21_body(
        self,
        messages: list[LLMMessage],
        temperature: float,
        max_tokens: int,
        top_p: float,
        stop: list[str] | None,
        **kwargs: object,
    ) -> dict:
        """Build AI21 request body."""
        body = {
            "prompt": self._format_generic_prompt(
                messages,
                user_prefix="Human: ",
                assistant_prefix="Assistant: ",
                final_suffix="Assistant:",
            ),
            "maxTokens": max_tokens,
            "temperature": temperature,
            "topP": top_p,
        }

        if stop:
            body["stopSequences"] = stop

        return body

    def _build_generic_body(
        self,
        messages: list[LLMMessage],
        temperature: float,
        max_tokens: int,
        top_p: float,
        stop: list[str] | None,
        **kwargs: object,
    ) -> dict:
        """Build generic fallback request body."""
        return {
            "prompt": "\n".join([f"{msg.role}: {msg.content}" for msg in messages]),
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
        }

    def _format_generic_prompt(
        self,
        messages: list[LLMMessage],
        system_prefix: str = "",
        system_suffix: str = "\n\n",
        user_prefix: str = "",
        user_suffix: str = "\n\n",
        assistant_prefix: str = "",
        assistant_suffix: str = "\n\n",
        final_suffix: str = "",
    ) -> str:
        """Generic formatter for provider-specific prompts."""
        prompt_parts = []
        for msg in messages:
            if msg.role == "system":
                prompt_parts.append(f"{system_prefix}{msg.content}{system_suffix}")
            elif msg.role == "user":
                prompt_parts.append(f"{user_prefix}{msg.content}{user_suffix}")
            elif msg.role == "assistant":
                prompt_parts.append(f"{assistant_prefix}{msg.content}{assistant_suffix}")
        prompt_parts.append(final_suffix)
        return "".join(prompt_parts)

    def _parse_response_body(self, body: str) -> tuple[str, TokenUsage]:
        """Parse response body from Bedrock.

        Args:
            body: JSON response body string

        Returns:
            Tuple of (content, token_usage)
        """
        provider = self._get_provider()
        response_data = json.loads(body)

        if provider == "anthropic":
            # Anthropic Claude response
            content = ""
            for block in response_data.get("content", []):
                if block.get("type") == "text":
                    content += block.get("text", "")

            usage = response_data.get("usage", {})
            token_usage = TokenUsage(
                prompt_tokens=usage.get("input_tokens", 0),
                completion_tokens=usage.get("output_tokens", 0),
                total_tokens=usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
            )

        elif provider == "meta":
            # Meta Llama response
            content = response_data.get("generation", "")
            token_usage = TokenUsage(
                prompt_tokens=response_data.get("prompt_token_count", 0),
                completion_tokens=response_data.get("generation_token_count", 0),
                total_tokens=(
                    response_data.get("prompt_token_count", 0)
                    + response_data.get("generation_token_count", 0)
                ),
            )

        elif provider == "amazon":
            # Amazon Titan response
            results = response_data.get("results", [{}])
            content = results[0].get("outputText", "") if results else ""
            token_usage = TokenUsage(
                prompt_tokens=response_data.get("inputTextTokenCount", 0),
                completion_tokens=results[0].get("tokenCount", 0) if results else 0,
                total_tokens=(
                    response_data.get("inputTextTokenCount", 0)
                    + (results[0].get("tokenCount", 0) if results else 0)
                ),
            )

        elif provider == "cohere":
            # Cohere response
            content = response_data.get("text", "")
            token_usage = TokenUsage(
                prompt_tokens=0,  # Cohere doesn't provide token counts in response
                completion_tokens=0,
                total_tokens=0,
            )

        elif provider == "ai21":
            # AI21 response
            completions = response_data.get("completions", [{}])
            content = completions[0].get("data", {}).get("text", "") if completions else ""
            token_usage = TokenUsage(
                prompt_tokens=0,  # AI21 doesn't provide token counts in response
                completion_tokens=0,
                total_tokens=0,
            )

        else:
            # Generic fallback
            content = response_data.get("completion", response_data.get("text", ""))
            token_usage = TokenUsage()

        return content, token_usage

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
            temperature: Sampling temperature (0.0 to 1.0)
            max_tokens: Maximum tokens to generate
            top_p: Nucleus sampling parameter
            stop: Stop sequences
            **kwargs: Additional Bedrock-specific parameters

        Returns:
            LLMResponse with generated content and metadata

        Raises:
            Exception: On API or validation errors
        """
        # Validate messages
        self.validate_messages(messages)
        self.validate_constitutional_compliance()

        # Build request body
        body = self._build_request_body(messages, temperature, max_tokens, top_p, stop, **kwargs)

        # Prepare InvokeModel request
        invoke_params = {
            "modelId": self.model,
            "body": body,
            "contentType": "application/json",
            "accept": "application/json",
        }

        # Add Guardrails if configured
        if self.config.guardrails_id:
            invoke_params["guardrailIdentifier"] = self.config.guardrails_id
            if self.config.guardrails_version:
                invoke_params["guardrailVersion"] = self.config.guardrails_version

        # Execute request
        start_time = time.time()
        client = self._get_client()

        try:
            response = client.invoke_model(**invoke_params)
            latency_ms = (time.time() - start_time) * 1000

            # Parse response
            response_body = response["body"].read().decode("utf-8")
            content, token_usage = self._parse_response_body(response_body)

            # Build metadata
            metadata = CompletionMetadata(
                model=self.model,
                provider=f"bedrock-{self._get_provider()}",
                request_id=response.get("ResponseMetadata", {}).get("RequestId", ""),
                latency_ms=latency_ms,
                finish_reason="stop",
                constitutional_hash=self.constitutional_hash,
            )

            # Estimate cost
            cost = self.estimate_cost(
                token_usage.prompt_tokens,
                token_usage.completion_tokens,
            )

            return LLMResponse(
                content=content,
                messages=[LLMMessage(role="assistant", content=content)],
                usage=token_usage,
                cost=cost,
                metadata=metadata,
                constitutional_hash=self.constitutional_hash,
                raw_response=json.loads(response_body),
            )

        except _BEDROCK_ADAPTER_OPERATION_ERRORS as e:
            logger.error(f"Bedrock completion error: {e}")
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
            temperature: Sampling temperature (0.0 to 1.0)
            max_tokens: Maximum tokens to generate
            top_p: Nucleus sampling parameter
            stop: Stop sequences
            **kwargs: Additional Bedrock-specific parameters

        Returns:
            LLMResponse with generated content and metadata

        Raises:
            Exception: On API or validation errors
        """
        # Validate messages
        self.validate_messages(messages)
        self.validate_constitutional_compliance()

        # Build request body
        body = self._build_request_body(messages, temperature, max_tokens, top_p, stop, **kwargs)

        # Prepare InvokeModel request
        invoke_params = {
            "modelId": self.model,
            "body": body,
            "contentType": "application/json",
            "accept": "application/json",
        }

        # Add Guardrails if configured
        if self.config.guardrails_id:
            invoke_params["guardrailIdentifier"] = self.config.guardrails_id
            if self.config.guardrails_version:
                invoke_params["guardrailVersion"] = self.config.guardrails_version

        # Execute request
        start_time = time.time()
        async_client = self._get_async_client()

        try:
            if async_client is not None:
                # Use aioboto3 for true async
                async with async_client.client(
                    "bedrock-runtime",
                    region_name=self.config.region,
                ) as client:
                    response = await client.invoke_model(**invoke_params)
                    latency_ms = (time.time() - start_time) * 1000

                    # Parse response
                    response_body = await response["body"].read()
                    response_body_str = response_body.decode("utf-8")
            else:
                # Fallback to sync client with asyncio
                sync_client = self._get_client()
                response = await asyncio.to_thread(sync_client.invoke_model, **invoke_params)
                latency_ms = (time.time() - start_time) * 1000

                # Parse response
                response_body_str = response["body"].read().decode("utf-8")

            content, token_usage = self._parse_response_body(response_body_str)

            # Build metadata
            metadata = CompletionMetadata(
                model=self.model,
                provider=f"bedrock-{self._get_provider()}",
                request_id=response.get("ResponseMetadata", {}).get("RequestId", ""),
                latency_ms=latency_ms,
                finish_reason="stop",
                constitutional_hash=self.constitutional_hash,
            )

            # Estimate cost
            cost = self.estimate_cost(
                token_usage.prompt_tokens,
                token_usage.completion_tokens,
            )

            return LLMResponse(
                content=content,
                messages=[LLMMessage(role="assistant", content=content)],
                usage=token_usage,
                cost=cost,
                metadata=metadata,
                constitutional_hash=self.constitutional_hash,
                raw_response=json.loads(response_body_str),
            )

        except _BEDROCK_ADAPTER_OPERATION_ERRORS as e:
            logger.error(f"Bedrock async completion error: {e}")
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
            temperature: Sampling temperature (0.0 to 1.0)
            max_tokens: Maximum tokens to generate
            top_p: Nucleus sampling parameter
            stop: Stop sequences
            **kwargs: Additional Bedrock-specific parameters

        Yields:
            Generated text chunks

        Raises:
            Exception: On API or validation errors
        """
        self.validate_messages(messages)
        self.validate_constitutional_compliance()

        invoke_params = self._build_streaming_params(
            messages, temperature, max_tokens, top_p, stop, **kwargs
        )
        client = self._get_client()

        try:
            response = client.invoke_model_with_response_stream(**invoke_params)
            stream = response.get("body")

            for event in stream:
                text = self._extract_stream_text(event)
                if text:
                    yield text

        except _BEDROCK_ADAPTER_OPERATION_ERRORS as e:
            logger.error(f"Bedrock streaming error: {e}")
            raise

    def _build_streaming_params(
        self,
        messages: list[LLMMessage],
        temperature: float,
        max_tokens: int | None,
        top_p: float,
        stop: list[str] | None,
        **kwargs: object,
    ) -> dict:
        """Build parameters for streaming request."""
        body = self._build_request_body(messages, temperature, max_tokens, top_p, stop, **kwargs)

        invoke_params = {
            "modelId": self.model,
            "body": body,
            "contentType": "application/json",
            "accept": "application/json",
        }

        if self.config.guardrails_id:
            invoke_params["guardrailIdentifier"] = self.config.guardrails_id
            if self.config.guardrails_version:
                invoke_params["guardrailVersion"] = self.config.guardrails_version

        return invoke_params

    def _extract_stream_text(self, event: dict) -> str | None:
        """Extract text from streaming event based on provider."""
        chunk = event.get("chunk")
        if not chunk:
            return None

        chunk_data = json.loads(chunk.get("bytes").decode("utf-8"))
        provider = self._get_provider()

        # Provider-specific chunk processors lookup table
        chunk_processors = {
            "anthropic": self._extract_anthropic_chunk_text,
            "meta": self._extract_meta_chunk_text,
            "amazon": self._extract_amazon_chunk_text,
        }

        processor = chunk_processors.get(provider, self._extract_generic_chunk_text)
        return processor(chunk_data)

    @staticmethod
    def _extract_anthropic_chunk_text(chunk_data: dict) -> str | None:
        """Extract text from Anthropic chunk."""
        delta = chunk_data.get("delta", {})
        if delta.get("type") == "content_block_delta":
            return delta.get("delta", {}).get("text", "")  # type: ignore[no-any-return]
        return None

    @staticmethod
    def _extract_meta_chunk_text(chunk_data: dict) -> str | None:
        """Extract text from Meta chunk."""
        return chunk_data.get("generation", "")  # type: ignore[no-any-return]

    @staticmethod
    def _extract_amazon_chunk_text(chunk_data: dict) -> str | None:
        """Extract text from Amazon chunk."""
        return chunk_data.get("outputText", "")  # type: ignore[no-any-return]

    @staticmethod
    def _extract_generic_chunk_text(chunk_data: dict) -> str | None:
        """Extract text from generic chunk."""
        return chunk_data.get("text", chunk_data.get("completion", ""))  # type: ignore[no-any-return]

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
            temperature: Sampling temperature (0.0 to 1.0)
            max_tokens: Maximum tokens to generate
            top_p: Nucleus sampling parameter
            stop: Stop sequences
            **kwargs: Additional Bedrock-specific parameters

        Yields:
            Generated text chunks

        Raises:
            Exception: On API or validation errors
        """
        self.validate_messages(messages)
        self.validate_constitutional_compliance()

        invoke_params = self._build_streaming_params(
            messages, temperature, max_tokens, top_p, stop, **kwargs
        )
        async_client = self._get_async_client()

        try:
            if async_client is not None:
                async for text in self._async_stream_with_client(async_client, invoke_params):
                    if text:
                        yield text
            else:
                logger.warning(
                    "Using sync client for async streaming - install aioboto3 for better performance"
                )
                async for text in self._async_stream_fallback(
                    messages, temperature, max_tokens, top_p, stop, **kwargs
                ):
                    yield text

        except _BEDROCK_ADAPTER_OPERATION_ERRORS as e:
            logger.error(f"Bedrock async streaming error: {e}")
            raise

    async def _async_stream_with_client(
        self, async_client: object, invoke_params: dict
    ) -> AsyncIterator[str]:
        """Handle async streaming with aioboto3 client."""
        async with async_client.client(
            "bedrock-runtime",
            region_name=self.config.region,
        ) as client:
            response = await client.invoke_model_with_response_stream(**invoke_params)
            stream = response.get("body")

            async for event in stream:
                text = self._extract_stream_text(event)
                if text:
                    yield text

    async def _async_stream_fallback(
        self,
        messages: list[LLMMessage],
        temperature: float,
        max_tokens: int | None,
        top_p: float,
        stop: list[str] | None,
        **kwargs: object,
    ) -> AsyncIterator[str]:
        """Fallback async streaming using sync client."""
        for chunk in self.stream(messages, temperature, max_tokens, top_p, stop, **kwargs):
            yield chunk

    def count_tokens(self, messages: list[LLMMessage]) -> int:
        """Count tokens in messages for the current model.

        Args:
            messages: List of messages to count tokens for

        Returns:
            Total token count

        Note:
            This is an estimation as Bedrock doesn't provide a direct token counting API.
            For Anthropic models, we use a rough estimation based on character count.
            For more accurate counting, consider using the model provider's tokenizer directly.
        """
        provider = self._get_provider()

        if provider == "anthropic":
            # Rough estimation: 4 characters ≈ 1 token for Claude
            total_chars = sum(len(msg.role) + len(msg.content) for msg in messages)
            return total_chars // 4
        elif provider == "meta":
            # Llama tokenization is roughly similar to GPT
            total_chars = sum(len(msg.role) + len(msg.content) for msg in messages)
            return total_chars // 4
        else:
            # Generic estimation
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
        # Find pricing for model
        pricing = None
        for model_key, model_pricing in self.MODEL_PRICING.items():
            if self.model == model_key or self.model.startswith(model_key):
                pricing = model_pricing
                break

        # Default to Claude 3.5 Sonnet pricing if model not found
        if pricing is None:
            logger.warning(
                f"Pricing not found for model {self.model}, using Claude 3.5 Sonnet pricing"
            )
            pricing = self.MODEL_PRICING["anthropic.claude-sonnet-4-6-v1:0"]

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
            test_messages = [LLMMessage(role="user", content="Hi")]

            # Use minimal tokens for health check
            await self.acomplete(
                test_messages,
                max_tokens=10,
                temperature=0.0,
            )

            latency_ms = (time.time() - start_time) * 1000

            return HealthCheckResult(
                status=AdapterStatus.HEALTHY,
                latency_ms=latency_ms,
                message="AWS Bedrock is accessible",
                details={
                    "model": self.model,
                    "provider": f"bedrock-{self._get_provider()}",
                    "region": self.config.region,
                    "guardrails_enabled": self.config.guardrails_id is not None,
                },
                constitutional_hash=self.constitutional_hash,
            )

        except BEDROCK_HEALTHCHECK_ERRORS as e:
            latency_ms = (time.time() - start_time) * 1000
            logger.error(f"Bedrock health check failed: {e}")

            return HealthCheckResult(
                status=AdapterStatus.UNHEALTHY,
                latency_ms=latency_ms,
                message=f"Health check failed: {e!s}",
                details={
                    "model": self.model,
                    "provider": f"bedrock-{self._get_provider()}",
                    "region": self.config.region,
                    "error": str(e),
                },
                constitutional_hash=self.constitutional_hash,
            )

    def get_streaming_mode(self) -> StreamingMode:
        """Get streaming support level for this adapter.

        Returns:
            StreamingMode.SUPPORTED (Bedrock supports streaming)
        """
        return StreamingMode.SUPPORTED

    def get_provider_name(self) -> str:
        """Get the provider name for this adapter.

        Returns:
            Provider identifier "bedrock-{provider}"
        """
        return f"bedrock-{self._get_provider()}"


__all__ = ["BedrockAdapter"]
