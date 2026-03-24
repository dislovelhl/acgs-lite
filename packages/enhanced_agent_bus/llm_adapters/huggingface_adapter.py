"""
ACGS-2 Enhanced Agent Bus - Hugging Face LLM Adapter
Constitutional Hash: cdd01ef066bc6cf2

Hugging Face adapter supporting open-source models like Llama, DeepSeek, Mistral
via Inference API, Inference Endpoints, or local transformers.
"""

import asyncio
import os
import time
from collections.abc import AsyncIterator, Iterator
from typing import ClassVar, Protocol, cast

try:
    from src.core.shared.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

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
    TokenUsage,
)
from .config import HuggingFaceAdapterConfig

# Logger
logger = get_logger(__name__)


class _HFInferenceClient(Protocol):
    def text_generation(self, prompt: str, **kwargs: object) -> object: ...


class _HFAsyncInferenceClient(Protocol):
    def text_generation(self, prompt: str, **kwargs: object) -> object: ...


class _HFTokenizer(Protocol):
    def encode(self, text: str) -> list[int]: ...


class _GeneratedTextResponse(Protocol):
    generated_text: object


class _TokenChunk(Protocol):
    token: object


class _TokenWithText(Protocol):
    text: object


class HuggingFaceAdapter(BaseLLMAdapter):
    """Hugging Face LLM adapter for open-source models.

    Constitutional Hash: cdd01ef066bc6cf2

    Supports:
    - Inference API (cloud-hosted models)
    - Inference Endpoints (custom deployments)
    - Local models via transformers (optional)
    - Model architectures: Llama, DeepSeek, Mistral, Falcon, etc.
    - Streaming responses (where available)
    - Model-specific tokenization
    - GPU memory management for local models
    """

    # Type annotation for config - overrides base class dict config
    config: HuggingFaceAdapterConfig  # type: ignore[assignment]

    # Model pricing estimates per 1M tokens (USD)
    # Note: Inference API is free with rate limits, these are for reference/endpoints
    MODEL_PRICING: ClassVar[dict] = {
        # Meta Llama models (Inference Endpoints pricing)
        "meta-llama/Llama-2-7b-chat-hf": {"prompt": 0.20, "completion": 0.20},
        "meta-llama/Llama-2-13b-chat-hf": {"prompt": 0.40, "completion": 0.40},
        "meta-llama/Llama-2-70b-chat-hf": {"prompt": 1.00, "completion": 1.00},
        "meta-llama/Meta-Llama-3-8B-Instruct": {"prompt": 0.20, "completion": 0.20},
        "meta-llama/Meta-Llama-3-70B-Instruct": {"prompt": 1.00, "completion": 1.00},
        "meta-llama/Meta-Llama-3.1-8B-Instruct": {"prompt": 0.20, "completion": 0.20},
        "meta-llama/Meta-Llama-3.1-70B-Instruct": {"prompt": 1.00, "completion": 1.00},
        # DeepSeek models
        "deepseek-ai/deepseek-coder-6.7b-instruct": {"prompt": 0.15, "completion": 0.15},
        "deepseek-ai/deepseek-coder-33b-instruct": {"prompt": 0.80, "completion": 0.80},
        "deepseek-ai/DeepSeek-V2-Chat": {"prompt": 0.60, "completion": 0.60},
        # Mistral models
        "mistralai/Mistral-7B-Instruct-v0.1": {"prompt": 0.20, "completion": 0.20},
        "mistralai/Mistral-7B-Instruct-v0.2": {"prompt": 0.20, "completion": 0.20},
        "mistralai/Mixtral-8x7B-Instruct-v0.1": {"prompt": 0.70, "completion": 0.70},
        "mistralai/Mixtral-8x22B-Instruct-v0.1": {"prompt": 1.20, "completion": 1.20},
        # Other popular models
        "tiiuae/falcon-7b-instruct": {"prompt": 0.15, "completion": 0.15},
        "tiiuae/falcon-40b-instruct": {"prompt": 0.90, "completion": 0.90},
        "HuggingFaceH4/zephyr-7b-beta": {"prompt": 0.20, "completion": 0.20},
        "01-ai/Yi-34B-Chat": {"prompt": 0.80, "completion": 0.80},
        # LocoOperator-4B (local inference — zero cost)
        "LocoreMind/LocoOperator-4B-GGUF": {"prompt": 0.00, "completion": 0.00},
        # Default fallback for unknown models
        "default": {"prompt": 0.50, "completion": 0.50},
    }

    # Chat templates for different model families
    CHAT_TEMPLATES: ClassVar[dict] = {
        "llama2": "<s>[INST] {system}\n\n{user} [/INST] {assistant}</s>",
        "llama3": (
            "<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n"
            "{system}<|eot_id|><|start_header_id|>user<|end_header_id|>\n\n"
            "{user}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n"
            "{assistant}<|eot_id|>"
        ),
        "mistral": "<s>[INST] {system}\n{user} [/INST] {assistant}</s>",
        "deepseek": "User: {system}\n{user}\n\nAssistant: {assistant}",
        "zephyr": "<|system|>\n{system}</s>\n<|user|>\n{user}</s>\n<|assistant|>\n{assistant}</s>",
        # LocoOperator-4B uses ChatML format (Qwen2.5-compatible architecture)
        "locooperator": (
            "<|im_start|>system\n{system}<|im_end|>\n"
            "<|im_start|>user\n{user}<|im_end|>\n"
            "<|im_start|>assistant\n{assistant}<|im_end|>\n"
        ),
        "default": "{system}\n\nUser: {user}\n\nAssistant: {assistant}",
    }

    def __init__(
        self,
        config: HuggingFaceAdapterConfig | None = None,
        model: str | None = None,
        api_key: str | None = None,
        retry_config: RetryConfig | None = None,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
        **kwargs: object,
    ) -> None:
        """Initialize Hugging Face adapter.

        Args:
            config: Hugging Face adapter configuration
            model: Model identifier (if config not provided)
            api_key: API key (if config not provided)
            retry_config: Retry configuration
            constitutional_hash: Constitutional hash for compliance
            **kwargs: Additional configuration options
        """
        # Create default config if not provided
        if config is None:
            if model is None:
                model = "meta-llama/Meta-Llama-3.1-8B-Instruct"
            config = HuggingFaceAdapterConfig.from_environment(model=model)

        # Initialize base adapter
        super().__init__(
            model=config.model,
            api_key=api_key or config.get_api_key("HUGGINGFACE_API_KEY"),
            retry_config=retry_config,
            constitutional_hash=constitutional_hash,
            **kwargs,
        )

        self.config = config
        self._client: _HFInferenceClient | None = None
        self._async_client: _HFAsyncInferenceClient | None = None
        self._tokenizer: _HFTokenizer | None = None
        self._local_model: object | None = None
        self._local_pipeline: object | None = None

    def validate_constitutional_compliance(self, **kwargs: object) -> None:
        """Validate constitutional compliance for HuggingFace adapter."""
        if not self.constitutional_hash:
            raise ValueError("Constitutional hash is required for HuggingFace adapter compliance.")
        if self.constitutional_hash != CONSTITUTIONAL_HASH:
            logger.warning(
                "HuggingFace adapter using non-standard constitutional hash: %s",
                self.constitutional_hash,
            )
        if not self.model:
            raise ValueError("HuggingFace adapter constitutional compliance requires a model.")

    def _get_client(self) -> _HFInferenceClient:
        """Get or create synchronous Hugging Face Inference client.

        Returns:
            InferenceClient instance

        Raises:
            ImportError: If huggingface_hub package is not installed
            ValueError: If using Inference API without API key
        """
        if self._client is None:
            try:
                from huggingface_hub import InferenceClient
            except ImportError:
                raise ImportError(
                    "huggingface_hub package is required for Hugging Face adapter. "
                    "Install with: pip install huggingface_hub>=0.20.0"
                ) from None

            if self.config.use_inference_api and not self.api_key:
                logger.warning(
                    "No Hugging Face API key provided. Rate limits will be restricted. "
                    "Set HUGGINGFACE_API_KEY environment variable for higher limits."
                )

            self._client = cast(
                _HFInferenceClient,
                cast(
                    object,
                    InferenceClient(
                        model=None if self.config.inference_endpoint else self.model,
                        token=self.api_key,
                        timeout=self.config.timeout_seconds,
                        base_url=self.config.inference_endpoint,
                    ),
                ),
            )

        return self._client

    def _get_async_client(self) -> _HFAsyncInferenceClient:
        """Get or create asynchronous Hugging Face Inference client.

        Returns:
            AsyncInferenceClient instance

        Raises:
            ImportError: If huggingface_hub package is not installed
        """
        if self._async_client is None:
            try:
                from huggingface_hub import AsyncInferenceClient
            except ImportError:
                raise ImportError(
                    "huggingface_hub package is required for Hugging Face adapter. "
                    "Install with: pip install huggingface_hub>=0.20.0"
                ) from None

            if self.config.use_inference_api and not self.api_key:
                logger.warning("No Hugging Face API key provided. Rate limits will be restricted.")

            self._async_client = cast(
                _HFAsyncInferenceClient,
                cast(
                    object,
                    AsyncInferenceClient(
                        model=None if self.config.inference_endpoint else self.model,
                        token=self.api_key,
                        timeout=self.config.timeout_seconds,
                        base_url=self.config.inference_endpoint,
                    ),
                ),
            )

        return self._async_client

    def _get_tokenizer(self) -> _HFTokenizer | None:
        """Get or create tokenizer for the model.

        Returns:
            Tokenizer instance

        Raises:
            ImportError: If transformers package is not installed
        """
        if self._tokenizer is None:
            try:
                from transformers import AutoTokenizer
            except ImportError:
                logger.warning(
                    "transformers package not installed. Token counting will use estimation. "
                    "Install with: pip install transformers"
                )
                return None

            try:
                _trust_remote = os.getenv("ACGS_HF_TRUST_REMOTE_CODE", "false").lower() == "true"
                if _trust_remote:
                    logger.warning(
                        "ACGS_HF_TRUST_REMOTE_CODE enabled — executing remote model code",
                        extra={
                            "security_event": "trust_remote_code_enabled",
                            "model": self.model,
                        },
                    )
                self._tokenizer = cast(
                    _HFTokenizer,
                    AutoTokenizer.from_pretrained(  # nosec B615 - model source is controlled by deployment config
                        self.model,
                        token=self.api_key,
                        trust_remote_code=_trust_remote,
                    ),
                )
            except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as e:
                logger.warning(f"Failed to load tokenizer for {self.model}: {e}")
                return None

        return self._tokenizer

    def _detect_model_family(self) -> str:
        """Detect model family from model ID for chat template selection.

        Returns:
            Model family identifier
        """
        model_lower = self.model.lower()

        if "llama-3" in model_lower or "llama-3.1" in model_lower:
            return "llama3"
        elif "llama-2" in model_lower or "llama2" in model_lower:
            return "llama2"
        elif "mistral" in model_lower or "mixtral" in model_lower:
            return "mistral"
        elif "deepseek" in model_lower:
            return "deepseek"
        elif "zephyr" in model_lower:
            return "zephyr"
        elif "locooperator" in model_lower or "locoremin" in model_lower:
            return "locooperator"
        else:
            return "default"

    def _extract_message_parts(
        self, messages: list[LLMMessage]
    ) -> tuple[str, list[tuple[str, str]]]:
        """Extract system content and conversation parts from messages.

        Args:
            messages: Standard LLM messages

        Returns:
            Tuple of (system_content, conversation_parts)
        """
        system_content = ""
        conversation_parts = []

        for msg in messages:
            if msg.role == "system":
                system_content = msg.content
            elif msg.role == "user":
                conversation_parts.append(("user", msg.content))
            elif msg.role == "assistant":
                conversation_parts.append(("assistant", msg.content))

        return system_content, conversation_parts

    def _format_with_template(
        self, template: str, system_content: str, conversation_parts: list[tuple[str, str]]
    ) -> list[str]:
        """Format conversation using template with system message support.

        Args:
            template: Chat template string
            system_content: System message content
            conversation_parts: List of (role, content) tuples

        Returns:
            List of formatted prompt parts
        """
        prompt_parts = []

        if system_content and "{system}" in template:
            # Template supports system message
            user_content = conversation_parts[0][1] if conversation_parts else ""
            assistant_content = ""

            formatted = template.format(
                system=system_content, user=user_content, assistant=assistant_content
            )
            prompt_parts.append(formatted.split("{assistant}")[0])  # Only use up to assistant

            # Add remaining conversation
            for _i, (role, content) in enumerate(conversation_parts[1:], 1):
                if role == "user":
                    prompt_parts.append(f"User: {content}\n")
                elif role == "assistant":
                    prompt_parts.append(f"Assistant: {content}\n")

        return prompt_parts

    def _format_simple(self, conversation_parts: list[tuple[str, str]]) -> list[str]:
        """Format conversation using simple role prefixes.

        Args:
            conversation_parts: List of (role, content) tuples

        Returns:
            List of formatted prompt parts
        """
        prompt_parts = []
        for role, content in conversation_parts:
            if role == "user":
                prompt_parts.append(f"User: {content}\n")
            elif role == "assistant":
                prompt_parts.append(f"Assistant: {content}\n")
        return prompt_parts

    def _merge_system_to_first_user(
        self, system_content: str, conversation_parts: list[tuple[str, str]]
    ) -> None:
        """Merge system content into first user message if template doesn't support system.

        Args:
            system_content: System message content to merge
            conversation_parts: List of (role, content) tuples to modify in-place
        """
        if conversation_parts:
            first_role, first_content = conversation_parts[0]
            if first_role == "user":
                conversation_parts[0] = ("user", f"{system_content}\n\n{first_content}")

    def _ensure_assistant_prompt(self, prompt: str) -> str:
        """Ensure prompt ends with assistant prompt.

        Args:
            prompt: Current prompt string

        Returns:
            Prompt with assistant prompt suffix
        """
        if not prompt.rstrip().endswith("Assistant:"):
            prompt += "\nAssistant: "
        return prompt

    def _format_messages_for_inference(self, messages: list[LLMMessage]) -> str:
        """Format messages for text generation inference.

        Args:
            messages: Standard LLM messages

        Returns:
            Formatted prompt string
        """
        # Extract message components
        system_content, conversation_parts = self._extract_message_parts(messages)

        # Get appropriate chat template
        model_family = self._detect_model_family()
        template = self.CHAT_TEMPLATES.get(model_family, self.CHAT_TEMPLATES["default"])

        # Try template-based formatting first
        prompt_parts = self._format_with_template(template, system_content, conversation_parts)

        # Handle system message for templates that don't support it
        if system_content and not prompt_parts:
            self._merge_system_to_first_user(system_content, conversation_parts)

        # Use simple formatting if template didn't work or no system message
        if not prompt_parts:
            prompt_parts = self._format_simple(conversation_parts)

        # Build final prompt with assistant prompt
        prompt = "".join(prompt_parts)
        return self._ensure_assistant_prompt(prompt)

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
            **kwargs: Additional Hugging Face-specific parameters

        Returns:
            LLMResponse with generated content and metadata

        Raises:
            Exception: On API or validation errors
        """
        # Validate messages
        self.validate_messages(messages)
        self.validate_constitutional_compliance()

        # Prepare prompt
        prompt = self._format_messages_for_inference(messages)

        # Set default max_tokens if not provided
        if max_tokens is None:
            max_tokens = 1024

        # Prepare request parameters
        request_params: JSONDict = {
            "temperature": temperature,
            "max_new_tokens": max_tokens,
            "top_p": top_p,
            "return_full_text": False,
        }

        if stop:
            request_params["stop_sequences"] = stop

        # Add optional parameters
        if isinstance(kwargs.get("top_k"), int):
            request_params["top_k"] = kwargs["top_k"]

        if isinstance(kwargs.get("repetition_penalty"), int | float):
            request_params["repetition_penalty"] = kwargs["repetition_penalty"]

        if isinstance(kwargs.get("do_sample"), bool):
            request_params["do_sample"] = kwargs["do_sample"]

        # Execute request
        start_time = time.time()
        client = self._get_client()

        try:
            response = client.text_generation(
                prompt,
                **request_params,
            )
            latency_ms = (time.time() - start_time) * 1000

            # Extract generated text
            if isinstance(response, str):
                generated_text = response
            elif hasattr(response, "generated_text"):
                generated_text = str(cast(_GeneratedTextResponse, response).generated_text)
            else:
                generated_text = str(response)

            # Count tokens
            prompt_tokens = self.count_tokens(messages)
            completion_tokens = len(generated_text.split()) * 1.3  # Rough estimate
            completion_tokens = int(completion_tokens)

            # Create response
            usage = TokenUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
                constitutional_hash=self.constitutional_hash,
            )

            metadata = CompletionMetadata(
                model=self.model,
                provider="huggingface",
                latency_ms=latency_ms,
                finish_reason="stop",
                constitutional_hash=self.constitutional_hash,
            )

            # Estimate cost
            cost = self.estimate_cost(prompt_tokens, completion_tokens)

            # Build response
            response_messages = messages + [LLMMessage(role="assistant", content=generated_text)]

            return LLMResponse(
                content=generated_text,
                messages=response_messages,
                usage=usage,
                cost=cost,
                metadata=metadata,
                constitutional_hash=self.constitutional_hash,
            )

        except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as e:
            logger.error(f"Hugging Face completion error: {e}")
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
            **kwargs: Additional Hugging Face-specific parameters

        Returns:
            LLMResponse with generated content and metadata

        Raises:
            Exception: On API or validation errors
        """
        # Validate messages
        self.validate_messages(messages)
        self.validate_constitutional_compliance()

        # Prepare prompt
        prompt = self._format_messages_for_inference(messages)

        # Set default max_tokens if not provided
        if max_tokens is None:
            max_tokens = 1024

        # Prepare request parameters
        request_params: JSONDict = {
            "temperature": temperature,
            "max_new_tokens": max_tokens,
            "top_p": top_p,
            "return_full_text": False,
        }

        if stop:
            request_params["stop_sequences"] = stop

        # Add optional parameters
        if isinstance(kwargs.get("top_k"), int):
            request_params["top_k"] = kwargs["top_k"]

        if isinstance(kwargs.get("repetition_penalty"), int | float):
            request_params["repetition_penalty"] = kwargs["repetition_penalty"]

        # Execute request
        start_time = time.time()
        client = self._get_async_client()

        try:
            response_raw = client.text_generation(
                prompt,
                **request_params,
            )
            response = await response_raw if asyncio.iscoroutine(response_raw) else response_raw
            latency_ms = (time.time() - start_time) * 1000

            # Extract generated text
            if isinstance(response, str):
                generated_text = response
            elif hasattr(response, "generated_text"):
                generated_text = str(cast(_GeneratedTextResponse, response).generated_text)
            else:
                generated_text = str(response)

            # Count tokens
            prompt_tokens = self.count_tokens(messages)
            completion_tokens = len(generated_text.split()) * 1.3  # Rough estimate
            completion_tokens = int(completion_tokens)

            # Create response
            usage = TokenUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
                constitutional_hash=self.constitutional_hash,
            )

            metadata = CompletionMetadata(
                model=self.model,
                provider="huggingface",
                latency_ms=latency_ms,
                finish_reason="stop",
                constitutional_hash=self.constitutional_hash,
            )

            # Estimate cost
            cost = self.estimate_cost(prompt_tokens, completion_tokens)

            # Build response
            response_messages = messages + [LLMMessage(role="assistant", content=generated_text)]

            return LLMResponse(
                content=generated_text,
                messages=response_messages,
                usage=usage,
                cost=cost,
                metadata=metadata,
                constitutional_hash=self.constitutional_hash,
            )

        except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as e:
            logger.error(f"Hugging Face async completion error: {e}")
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
            **kwargs: Additional Hugging Face-specific parameters

        Yields:
            Generated text chunks

        Raises:
            Exception: On API or validation errors
        """
        # Validate messages
        self.validate_messages(messages)
        self.validate_constitutional_compliance()

        # Prepare prompt
        prompt = self._format_messages_for_inference(messages)

        # Set default max_tokens if not provided
        if max_tokens is None:
            max_tokens = 1024

        # Prepare request parameters
        request_params: JSONDict = {
            "temperature": temperature,
            "max_new_tokens": max_tokens,
            "top_p": top_p,
            "return_full_text": False,
            "stream": True,
        }

        if stop:
            request_params["stop_sequences"] = stop

        if isinstance(kwargs.get("top_k"), int):
            request_params["top_k"] = kwargs["top_k"]

        # Execute streaming request
        client = self._get_client()

        try:
            stream_raw = client.text_generation(prompt, **request_params)
            stream_iter: Iterator[object] = (
                cast(Iterator[object], stream_raw) if hasattr(stream_raw, "__iter__") else iter(())
            )
            for chunk in stream_iter:
                if isinstance(chunk, str):
                    yield chunk
                elif hasattr(chunk, "token"):
                    token = cast(_TokenChunk, chunk).token
                    yield str(cast(_TokenWithText, token).text) if hasattr(token, "text") else ""
                else:
                    yield str(chunk)

        except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as e:
            logger.error(f"Hugging Face streaming error: {e}")
            raise

    def _prepare_streaming_params(
        self,
        temperature: float,
        max_tokens: int | None,
        top_p: float,
        stop: list[str] | None,
        **kwargs: object,
    ) -> JSONDict:
        """Prepare parameters for streaming requests.

        Args:
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            top_p: Nucleus sampling parameter
            stop: Stop sequences
            **kwargs: Additional parameters

        Returns:
            Dictionary of request parameters
        """
        # Set default max_tokens if not provided
        if max_tokens is None:
            max_tokens = 1024

        # Base parameters
        request_params: JSONDict = {
            "temperature": temperature,
            "max_new_tokens": max_tokens,
            "top_p": top_p,
            "return_full_text": False,
            "stream": True,
        }

        # Optional parameters
        if stop:
            request_params["stop_sequences"] = stop

        if isinstance(kwargs.get("top_k"), int):
            request_params["top_k"] = kwargs["top_k"]

        return request_params

    def _process_stream_chunk(self, chunk: object) -> str:
        """Process individual stream chunk and extract text.

        Args:
            chunk: Stream chunk from API

        Returns:
            Text content from chunk
        """
        if isinstance(chunk, str):
            return chunk
        elif hasattr(chunk, "token"):
            token = cast(_TokenChunk, chunk).token
            return str(cast(_TokenWithText, token).text) if hasattr(token, "text") else ""
        else:
            return str(chunk)

    async def _process_async_stream(self, stream_raw: object) -> AsyncIterator[str]:
        """Process async stream response and yield chunks.

        Args:
            stream_raw: Raw stream response from client

        Yields:
            Text chunks from stream
        """
        if hasattr(stream_raw, "__aiter__"):
            async for chunk in cast(AsyncIterator[object], stream_raw):
                yield self._process_stream_chunk(chunk)
        elif hasattr(stream_raw, "__iter__"):
            for chunk in cast(Iterator[object], stream_raw):
                yield self._process_stream_chunk(chunk)

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
            **kwargs: Additional Hugging Face-specific parameters

        Yields:
            Generated text chunks

        Raises:
            Exception: On API or validation errors
        """
        # Validate messages
        self.validate_messages(messages)
        self.validate_constitutional_compliance()

        # Prepare prompt and parameters
        prompt = self._format_messages_for_inference(messages)
        request_params = self._prepare_streaming_params(
            temperature, max_tokens, top_p, stop, **kwargs
        )

        # Execute streaming request
        client = self._get_async_client()

        try:
            stream_raw = client.text_generation(prompt, **request_params)
            async for chunk in self._process_async_stream(stream_raw):
                yield chunk

        except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as e:
            logger.error(f"Hugging Face async streaming error: {e}")
            raise

    def count_tokens(self, messages: list[LLMMessage]) -> int:
        """Count tokens in messages for the current model.

        Args:
            messages: List of messages to count tokens for

        Returns:
            Total token count
        """
        # Try to use actual tokenizer
        tokenizer = self._get_tokenizer()

        if tokenizer is not None:
            try:
                # Convert messages to text
                text = self._format_messages_for_inference(messages)
                tokens = tokenizer.encode(text)
                return len(tokens)
            except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as e:
                logger.warning(f"Tokenizer count failed: {e}, using estimation")

        # Fallback to estimation (roughly 4 chars per token)
        total_text = " ".join(msg.content for msg in messages)
        return len(total_text) // 4

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
        # Get pricing for model (or default)
        pricing = self.MODEL_PRICING.get(self.model, self.MODEL_PRICING["default"])

        # Calculate costs (pricing is per 1M tokens)
        prompt_cost = (prompt_tokens / 1_000_000) * pricing["prompt"]
        completion_cost = (completion_tokens / 1_000_000) * pricing["completion"]
        total_cost = prompt_cost + completion_cost

        return CostEstimate(
            prompt_cost_usd=prompt_cost,
            completion_cost_usd=completion_cost,
            total_cost_usd=total_cost,
            currency="USD",
            pricing_model=f"huggingface-{self.model}",
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
            # Try a minimal inference request to check connectivity
            if self.config.use_inference_api:
                # NOTE: Client is instantiated to verify configuration is valid
                _ = self._get_async_client()

                # Simple health check - just verify we can connect
                try:
                    # Try to get model info
                    from huggingface_hub import model_info

                    info = model_info(
                        self.model,
                        token=self.api_key,
                        timeout=5.0,
                    )

                    latency_ms = (time.time() - start_time) * 1000

                    return HealthCheckResult(
                        status=AdapterStatus.HEALTHY,
                        latency_ms=latency_ms,
                        message=f"Connected to Hugging Face Inference API for {self.model}",
                        details={
                            "model": self.model,
                            "model_type": getattr(info, "pipeline_tag", "unknown"),
                            "using_inference_api": self.config.use_inference_api,
                        },
                        constitutional_hash=self.constitutional_hash,
                    )
                except (
                    ImportError,
                    AttributeError,
                    OSError,
                    RuntimeError,
                    TypeError,
                    ValueError,
                ) as e:
                    logger.warning(f"Model info check failed: {e}, trying simple completion")

                    # Fallback to simple completion test
                    test_messages = [LLMMessage(role="user", content="Hi")]

                    # Verify connectivity by attempting a minimal completion
                    _ = await self.acomplete(
                        test_messages,
                        max_tokens=5,
                        temperature=0.1,
                    )

                    latency_ms = (time.time() - start_time) * 1000

                    return HealthCheckResult(
                        status=AdapterStatus.HEALTHY,
                        latency_ms=latency_ms,
                        message=f"Health check passed for {self.model}",
                        details={
                            "model": self.model,
                            "using_inference_api": self.config.use_inference_api,
                        },
                        constitutional_hash=self.constitutional_hash,
                    )
            else:
                # For local models or custom endpoints, just verify client creation
                latency_ms = (time.time() - start_time) * 1000

                return HealthCheckResult(
                    status=AdapterStatus.HEALTHY,
                    latency_ms=latency_ms,
                    message=f"Adapter initialized for {self.model}",
                    details={
                        "model": self.model,
                        "using_inference_api": self.config.use_inference_api,
                        "inference_endpoint": self.config.inference_endpoint,
                    },
                    constitutional_hash=self.constitutional_hash,
                )

        except (ImportError, AttributeError, OSError, RuntimeError, TypeError, ValueError) as e:
            latency_ms = (time.time() - start_time) * 1000

            return HealthCheckResult(
                status=AdapterStatus.UNHEALTHY,
                latency_ms=latency_ms,
                message=f"Health check failed: {e!s}",
                details={
                    "model": self.model,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
                constitutional_hash=self.constitutional_hash,
            )


__all__ = [
    "HuggingFaceAdapter",
]
