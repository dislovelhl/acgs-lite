"""
ACGS-2 DeepSeek Model Adapter
Constitutional Hash: 608508a9bd224290

Adapter for DeepSeek models (DeepSeek-Coder, DeepSeek-Chat, etc.)
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


class DeepSeekAdapter(ModelAdapter):
    """Adapter for DeepSeek models.

    DeepSeek uses an OpenAI-compatible API, so we extend
    the same translation logic with DeepSeek-specific defaults.

    Supports:
    - DeepSeek-Coder
    - DeepSeek-Chat
    - DeepSeek-V2

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.deepseek.com/v1",
        default_model: str = "deepseek-chat",
        timeout_seconds: int = 60,
    ) -> None:
        """Initialize DeepSeek adapter."""
        super().__init__(
            provider=ModelProvider.DEEPSEEK,
            api_key=api_key,
            base_url=base_url,
            default_model=default_model,
            timeout_seconds=timeout_seconds,
        )
        self._client: object | None = None

    async def _ensure_client(self) -> object:
        """Ensure client is initialized (uses OpenAI client)."""
        if self._client is None:
            try:
                from openai import AsyncOpenAI
            except ImportError:
                raise ImportError(
                    "OpenAI package not installed. Install with: pip install openai"
                ) from None
            self._client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout_seconds,
            )
        return self._client

    def translate_request(self, request: ModelRequest) -> JSONDict:
        """Translate to DeepSeek format (OpenAI-compatible)."""
        role_map = {
            MessageRole.SYSTEM: "system",
            MessageRole.USER: "user",
            MessageRole.ASSISTANT: "assistant",
        }

        messages = [
            {
                "role": role_map.get(msg.role, "user"),
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
        """Translate from DeepSeek format."""
        choice = response.get("choices", [{}])[0]
        message = choice.get("message", {})
        usage = response.get("usage", {})

        return ModelResponse(
            content=message.get("content", ""),
            model=response.get("model", ""),
            provider=ModelProvider.DEEPSEEK,
            finish_reason=choice.get("finish_reason", "stop"),
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
            response_id=response.get("id", ""),
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

    async def complete(self, request: ModelRequest) -> ModelResponse:
        """Execute completion request."""
        client = await self._ensure_client()
        payload = self.translate_request(request)
        response = await client.chat.completions.create(**payload)
        return self.translate_response(response.model_dump())

    async def stream(self, request: ModelRequest) -> AsyncIterator[StreamChunk]:
        """Execute streaming request."""
        client = await self._ensure_client()
        request.stream = True
        payload = self.translate_request(request)

        response = await client.chat.completions.create(**payload)
        async for chunk in response:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta:
                yield StreamChunk(
                    content=delta.content or "",
                    finish_reason=chunk.choices[0].finish_reason,
                    is_final=chunk.choices[0].finish_reason is not None,
                )


__all__ = ["DeepSeekAdapter"]
