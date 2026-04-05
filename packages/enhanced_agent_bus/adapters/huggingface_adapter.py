"""
ACGS-2 HuggingFace Model Adapter
Constitutional Hash: 608508a9bd224290

Adapter for HuggingFace Inference API and local models.
Supports Llama, Mistral, and other open source models.
"""

from collections.abc import AsyncIterator

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from .base import (
    CONSTITUTIONAL_HASH,
    MessageRole,
    ModelAdapter,
    ModelProvider,
    ModelRequest,
    ModelResponse,
    StreamChunk,
)

logger = get_logger(__name__)


class HuggingFaceAdapter(ModelAdapter):
    """Adapter for HuggingFace models.

    Supports:
    - HuggingFace Inference API
    - Llama models
    - Mistral models
    - Open source models

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api-inference.huggingface.co/models",
        default_model: str = "meta-llama/Llama-3.1-8B-Instruct",
        timeout_seconds: int = 120,
    ) -> None:
        """Initialize HuggingFace adapter."""
        super().__init__(
            provider=ModelProvider.HUGGINGFACE,
            api_key=api_key,
            base_url=base_url,
            default_model=default_model,
            timeout_seconds=timeout_seconds,
        )
        self._client: object | None = None

    async def _ensure_client(self) -> object:
        """Ensure client is initialized."""
        if self._client is None:
            try:
                from huggingface_hub import AsyncInferenceClient
            except ImportError:
                raise ImportError(
                    "HuggingFace Hub not installed. Install with: pip install huggingface_hub"
                ) from None
            self._client = AsyncInferenceClient(
                token=self.api_key,
                timeout=self.timeout_seconds,
            )
        return self._client

    def translate_request(self, request: ModelRequest) -> JSONDict:
        """Translate to HuggingFace format."""
        # Build conversation format
        messages = [
            {
                "role": "system" if msg.role == MessageRole.SYSTEM else msg.role.value,
                "content": msg.content,
            }
            for msg in request.messages
        ]

        return {
            "model": request.model or self.default_model,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "top_p": request.top_p,
            "stream": request.stream,
        }

    def translate_response(self, response: JSONDict) -> ModelResponse:
        """Translate from HuggingFace format."""
        # Handle different response formats
        content = ""
        if isinstance(response, str):
            content = response
        elif isinstance(response, dict):
            if "generated_text" in response:
                content = response["generated_text"]
            elif "choices" in response:
                content = response["choices"][0].get("message", {}).get("content", "")

        return ModelResponse(
            content=content,
            model=self.default_model,
            provider=ModelProvider.HUGGINGFACE,
            finish_reason="stop",
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

    async def complete(self, request: ModelRequest) -> ModelResponse:
        """Execute completion request."""
        client = await self._ensure_client()
        payload = self.translate_request(request)

        # Use chat_completion for instruction-tuned models
        response = await client.chat_completion(
            model=payload["model"],
            messages=payload["messages"],
            max_tokens=payload["max_tokens"],
            temperature=payload["temperature"],
            top_p=payload["top_p"],
        )

        return ModelResponse(
            content=response.choices[0].message.content,
            model=payload["model"],
            provider=ModelProvider.HUGGINGFACE,
            finish_reason=response.choices[0].finish_reason or "stop",
            prompt_tokens=response.usage.prompt_tokens if response.usage else 0,
            completion_tokens=response.usage.completion_tokens if response.usage else 0,
            total_tokens=response.usage.total_tokens if response.usage else 0,
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

    async def stream(self, request: ModelRequest) -> AsyncIterator[StreamChunk]:
        """Execute streaming request."""
        client = await self._ensure_client()
        payload = self.translate_request(request)

        async for chunk in await client.chat_completion(
            model=payload["model"],
            messages=payload["messages"],
            max_tokens=payload["max_tokens"],
            temperature=payload["temperature"],
            stream=True,
        ):
            if chunk.choices:
                delta = chunk.choices[0].delta
                yield StreamChunk(
                    content=delta.content or "",
                    finish_reason=chunk.choices[0].finish_reason,
                    is_final=chunk.choices[0].finish_reason is not None,
                )


__all__ = ["HuggingFaceAdapter"]
