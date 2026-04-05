"""
ACGS-2 OpenAI Model Adapter
Constitutional Hash: 608508a9bd224290

Adapter for OpenAI GPT models (GPT-4, GPT-3.5, etc.)
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
# Role mapping for OpenAI
OPENAI_ROLE_MAP = {
    MessageRole.SYSTEM: "system",
    MessageRole.USER: "user",
    MessageRole.ASSISTANT: "assistant",
    MessageRole.TOOL: "tool",
    MessageRole.FUNCTION: "function",
}


class OpenAIAdapter(ModelAdapter):
    """Adapter for OpenAI GPT models.

    Supports:
    - GPT-4, GPT-4 Turbo, GPT-4o
    - GPT-3.5 Turbo
    - Function calling and tools
    - Streaming responses

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.openai.com/v1",
        default_model: str = "gpt-4o",
        timeout_seconds: int = 60,
        organization: str | None = None,
    ) -> None:
        """Initialize OpenAI adapter.

        Args:
            api_key: OpenAI API key (or use OPENAI_API_KEY env var)
            base_url: API base URL
            default_model: Default model to use
            timeout_seconds: Request timeout
            organization: Optional organization ID
        """
        super().__init__(
            provider=ModelProvider.OPENAI,
            api_key=api_key,
            base_url=base_url,
            default_model=default_model,
            timeout_seconds=timeout_seconds,
        )
        self.organization = organization
        self._client: object | None = None

    async def _ensure_client(self) -> object:
        """Ensure OpenAI client is initialized."""
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
                organization=self.organization,
            )
        return self._client

    def translate_request(self, request: ModelRequest) -> JSONDict:
        """Translate to OpenAI format."""
        messages = []
        for msg in request.messages:
            openai_msg: JSONDict = {
                "role": OPENAI_ROLE_MAP.get(msg.role, "user"),
                "content": msg.content,
            }
            if msg.name:
                openai_msg["name"] = msg.name
            if msg.tool_call_id:
                openai_msg["tool_call_id"] = msg.tool_call_id
            if msg.tool_calls:
                openai_msg["tool_calls"] = msg.tool_calls
            messages.append(openai_msg)

        payload: JSONDict = {
            "model": request.model or self.default_model,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "top_p": request.top_p,
            "stream": request.stream,
        }

        if request.stop:
            payload["stop"] = request.stop
        if request.tools:
            payload["tools"] = request.tools
        if request.tool_choice:
            payload["tool_choice"] = request.tool_choice

        return payload

    def translate_response(self, response: JSONDict) -> ModelResponse:
        """Translate from OpenAI format."""
        choice = response.get("choices", [{}])[0]
        message = choice.get("message", {})
        usage = response.get("usage", {})

        return ModelResponse(
            content=message.get("content", ""),
            model=response.get("model", ""),
            provider=ModelProvider.OPENAI,
            finish_reason=choice.get("finish_reason", "stop"),
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
            tool_calls=message.get("tool_calls"),
            response_id=response.get("id", ""),
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

    async def complete(self, request: ModelRequest) -> ModelResponse:
        """Execute completion request."""
        errors = self.validate_request(request)
        if errors:
            raise ValueError(f"Invalid request: {', '.join(errors)}")

        client = await self._ensure_client()
        payload = self.translate_request(request)

        response = await client.chat.completions.create(**payload)
        return self.translate_response(response.model_dump())

    async def stream(self, request: ModelRequest) -> AsyncIterator[StreamChunk]:
        """Execute streaming request."""
        errors = self.validate_request(request)
        if errors:
            raise ValueError(f"Invalid request: {', '.join(errors)}")

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
                    tool_calls=delta.tool_calls,
                    is_final=chunk.choices[0].finish_reason is not None,
                )

    def get_capabilities(self) -> JSONDict:
        """Get OpenAI-specific capabilities."""
        caps = super().get_capabilities()
        caps.update(
            {
                "vision": True,  # GPT-4V supports vision
                "json_mode": True,
                "seed_support": True,
                "max_context_tokens": 128000,  # GPT-4 Turbo
            }
        )
        return caps


__all__ = ["OpenAIAdapter"]
