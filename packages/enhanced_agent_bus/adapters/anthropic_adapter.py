"""
ACGS-2 Anthropic Model Adapter
Constitutional Hash: 608508a9bd224290

Adapter for Anthropic Claude models (Claude 3, Claude 2, etc.)
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


class AnthropicAdapter(ModelAdapter):
    """Adapter for Anthropic Claude models.

    Supports:
    - Claude 3 (Opus, Sonnet, Haiku)
    - Claude 3.5 Sonnet
    - Tool use
    - Streaming responses

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.anthropic.com",
        default_model: str = "claude-sonnet-4-6",
        timeout_seconds: int = 60,
    ) -> None:
        """Initialize Anthropic adapter.

        Args:
            api_key: Anthropic API key
            base_url: API base URL
            default_model: Default model to use
            timeout_seconds: Request timeout
        """
        super().__init__(
            provider=ModelProvider.ANTHROPIC,
            api_key=api_key,
            base_url=base_url,
            default_model=default_model,
            timeout_seconds=timeout_seconds,
        )
        self._client = None

    async def _ensure_client(self) -> object:
        """Ensure Anthropic client is initialized."""
        if self._client is None:
            try:
                from anthropic import AsyncAnthropic
            except ImportError:
                raise ImportError(
                    "Anthropic package not installed. Install with: pip install anthropic"
                ) from None
            self._client = AsyncAnthropic(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout_seconds,
            )
        return self._client

    def translate_request(self, request: ModelRequest) -> JSONDict:
        """Translate to Anthropic format.

        Anthropic uses a different message format than OpenAI:
        - System message is a separate parameter
        - Messages are user/assistant alternating
        """
        system_content = None
        messages = []

        for msg in request.messages:
            if msg.role == MessageRole.SYSTEM:
                system_content = msg.content
            else:
                # Map roles to Anthropic format
                role = "user" if msg.role == MessageRole.USER else "assistant"
                messages.append(
                    {
                        "role": role,
                        "content": msg.content,
                    }
                )

        payload: JSONDict = {
            "model": request.model or self.default_model,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "top_p": request.top_p,
        }

        if system_content:
            payload["system"] = system_content

        if request.stop:
            payload["stop_sequences"] = request.stop

        if request.tools:
            # Convert OpenAI tool format to Anthropic format
            anthropic_tools = []
            for tool in request.tools:
                if tool.get("type") == "function":
                    fn = tool.get("function", {})
                    anthropic_tools.append(
                        {
                            "name": fn.get("name"),
                            "description": fn.get("description"),
                            "input_schema": fn.get("parameters", {}),
                        }
                    )
            if anthropic_tools:
                payload["tools"] = anthropic_tools

        return payload

    def translate_response(self, response: JSONDict) -> ModelResponse:
        """Translate from Anthropic format."""
        content_blocks = response.get("content", [])
        text_content = ""
        tool_calls = []

        for block in content_blocks:
            if block.get("type") == "text":
                text_content += block.get("text", "")
            elif block.get("type") == "tool_use":
                tool_calls.append(
                    {
                        "id": block.get("id"),
                        "type": "function",
                        "function": {
                            "name": block.get("name"),
                            "arguments": block.get("input", {}),
                        },
                    }
                )

        usage = response.get("usage", {})

        return ModelResponse(
            content=text_content,
            model=response.get("model", ""),
            provider=ModelProvider.ANTHROPIC,
            finish_reason=response.get("stop_reason", "end_turn"),
            prompt_tokens=usage.get("input_tokens", 0),
            completion_tokens=usage.get("output_tokens", 0),
            total_tokens=usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
            tool_calls=tool_calls if tool_calls else None,
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

        response = await client.messages.create(**payload)
        return self.translate_response(response.model_dump())

    async def stream(self, request: ModelRequest) -> AsyncIterator[StreamChunk]:
        """Execute streaming request."""
        errors = self.validate_request(request)
        if errors:
            raise ValueError(f"Invalid request: {', '.join(errors)}")

        client = await self._ensure_client()
        payload = self.translate_request(request)
        payload["stream"] = True

        async with client.messages.stream(**payload) as stream:
            async for event in stream:
                if hasattr(event, "delta"):
                    delta = event.delta
                    if hasattr(delta, "text"):
                        yield StreamChunk(
                            content=delta.text or "",
                            is_final=False,
                        )
                elif hasattr(event, "message"):
                    # Final message
                    yield StreamChunk(
                        content="",
                        finish_reason=event.message.stop_reason,
                        is_final=True,
                    )

    def get_capabilities(self) -> JSONDict:
        """Get Anthropic-specific capabilities."""
        caps = super().get_capabilities()
        caps.update(
            {
                "vision": True,  # Claude 3 supports vision
                "max_context_tokens": 200000,  # Claude 3 context
                "extended_thinking": False,  # Future feature
            }
        )
        return caps


__all__ = ["AnthropicAdapter"]
