"""
ACGS-2 Enhanced Agent Bus - LLM Adapter Models
Constitutional Hash: cdd01ef066bc6cf2

Standardized request/response formats and conversion utilities for all LLM adapters.
Provides unified interface for multi-provider LLM integration with constitutional compliance.
"""

import json
from enum import Enum

from pydantic import BaseModel, Field, field_validator

# Import from base module
try:
    from src.core.shared.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from .base import (
    CONSTITUTIONAL_HASH,
    CompletionMetadata,
    CostEstimate,
    LLMMessage,
    LLMResponse,
    TokenUsage,
)

# Re-export base models for convenience
__all__ = [
    "CompletionMetadata",
    "CostEstimate",
    "FunctionDefinition",
    "FunctionParameters",
    # Re-exported from base
    "LLMMessage",
    # New models
    "LLMRequest",
    "LLMResponse",
    # Conversion utilities
    "MessageConverter",
    "RequestConverter",
    "ResponseConverter",
    "TokenUsage",
    "ToolCall",
    "ToolCallFunction",
    "ToolDefinition",
    "ToolType",
]


class ToolType(Enum):
    """Types of tools/functions that can be called.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    FUNCTION = "function"
    CODE_INTERPRETER = "code_interpreter"
    FILE_SEARCH = "file_search"  # For retrieval
    WEB_BROWSER = "web_browser"  # For web browsing


class FunctionParameters(BaseModel):
    """JSON Schema for function parameters.

    Constitutional Hash: cdd01ef066bc6cf2

    Follows JSON Schema specification for describing function parameters.
    Compatible with OpenAI, Anthropic, and other major providers.
    """

    type: str = Field(default="object", description="Parameter type (usually 'object')")
    properties: dict[str, JSONDict] = Field(
        default_factory=dict, description="Property definitions"
    )
    required: list[str] = Field(default_factory=list, description="Required parameter names")
    description: str | None = Field(default=None, description="Schema description")

    model_config = {"from_attributes": True}

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        result = {
            "type": self.type,
            "properties": self.properties,
        }
        if self.required:
            result["required"] = self.required
        if self.description:
            result["description"] = self.description
        return result


class FunctionDefinition(BaseModel):
    """Definition of a callable function/tool.

    Constitutional Hash: cdd01ef066bc6cf2

    Defines a function that the LLM can call, including its name,
    description, and parameter schema.
    """

    name: str = Field(..., description="Function name")
    description: str = Field(..., description="Function description for the LLM")
    parameters: FunctionParameters = Field(
        default_factory=FunctionParameters, description="Function parameter schema"
    )
    strict: bool | None = Field(
        default=None, description="Whether to enforce strict schema validation (OpenAI)"
    )

    model_config = {"from_attributes": True}

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate function name format."""
        if not v or not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError(f"Function name must be alphanumeric with underscores/hyphens: {v}")
        return v

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        result: JSONDict = {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters.to_dict(),
        }
        if self.strict is not None:
            result["strict"] = self.strict
        return result


class ToolDefinition(BaseModel):
    """Definition of a tool that can be used by the LLM.

    Constitutional Hash: cdd01ef066bc6cf2

    Wraps function definitions with tool type information.
    Compatible with OpenAI Tools API and Anthropic Tool Use.
    """

    type: ToolType = Field(default=ToolType.FUNCTION, description="Tool type")
    function: FunctionDefinition = Field(..., description="Function definition")

    model_config = {"from_attributes": True}

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "type": self.type.value,
            "function": self.function.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: JSONDict) -> "ToolDefinition":
        """Create from dictionary."""
        return cls(
            type=ToolType(data.get("type", "function")),
            function=FunctionDefinition(**data["function"]),
        )


class ToolCallFunction(BaseModel):
    """Function call details within a tool call.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    name: str = Field(..., description="Function name being called")
    arguments: str = Field(..., description="JSON string of function arguments")

    model_config = {"from_attributes": True}

    @field_validator("arguments")
    @classmethod
    def validate_arguments(cls, v: str) -> str:
        """Validate that arguments is valid JSON."""
        try:
            json.loads(v)
        except json.JSONDecodeError as e:
            raise ValueError(f"Arguments must be valid JSON: {e}") from e
        return v

    def get_arguments_dict(self) -> JSONDict:
        """Parse arguments as dictionary."""
        return json.loads(self.arguments)

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "arguments": self.arguments,
        }


class ToolCall(BaseModel):
    """A tool call made by the LLM.

    Constitutional Hash: cdd01ef066bc6cf2

    Represents a request from the LLM to call a specific tool/function.
    """

    id: str = Field(..., description="Unique identifier for this tool call")
    type: ToolType = Field(default=ToolType.FUNCTION, description="Tool type")
    function: ToolCallFunction = Field(..., description="Function call details")

    model_config = {"from_attributes": True}

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "type": self.type.value,
            "function": self.function.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: JSONDict) -> "ToolCall":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            type=ToolType(data.get("type", "function")),
            function=ToolCallFunction(**data["function"]),
        )


class LLMRequest(BaseModel):
    """Standardized LLM completion request.

    Constitutional Hash: cdd01ef066bc6cf2

    Unified request format for all LLM adapters. Adapters convert this
    to provider-specific formats using RequestConverter.
    """

    messages: list[LLMMessage] = Field(..., description="Conversation messages")
    model: str | None = Field(default=None, description="Model identifier (optional)")
    temperature: float = Field(default=0.7, description="Sampling temperature", ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, description="Maximum tokens to generate", ge=1)
    top_p: float = Field(default=1.0, description="Nucleus sampling parameter", ge=0.0, le=1.0)
    top_k: int | None = Field(default=None, description="Top-k sampling (provider-specific)")
    frequency_penalty: float | None = Field(
        default=None, description="Frequency penalty (OpenAI)", ge=-2.0, le=2.0
    )
    presence_penalty: float | None = Field(
        default=None, description="Presence penalty (OpenAI)", ge=-2.0, le=2.0
    )
    stop: list[str] | None = Field(default=None, description="Stop sequences")
    stream: bool = Field(default=False, description="Enable streaming responses")
    tools: list[ToolDefinition] | None = Field(
        default=None, description="Available tools for function calling"
    )
    tool_choice: str | JSONDict | None = Field(
        default=None, description="Tool choice strategy ('auto', 'none', or specific tool)"
    )
    response_format: JSONDict | None = Field(
        default=None, description="Response format specification (e.g., JSON mode)"
    )
    constitutional_hash: str = Field(
        default=CONSTITUTIONAL_HASH, description="Constitutional hash for compliance"
    )
    metadata: JSONDict = Field(default_factory=dict, description="Additional metadata for tracking")

    model_config = {"from_attributes": True}

    @field_validator("messages")
    @classmethod
    def validate_messages(cls, v: list[LLMMessage]) -> list[LLMMessage]:
        """Validate messages list is not empty."""
        if not v:
            raise ValueError("Messages list cannot be empty")
        return v

    def to_dict(self) -> JSONDict:
        """Convert to dictionary, excluding None values."""
        result = {
            "messages": [msg.model_dump() for msg in self.messages],
            "temperature": self.temperature,
            "top_p": self.top_p,
            "stream": self.stream,
            "constitutional_hash": self.constitutional_hash,
        }

        # Add optional fields if set
        if self.model:
            result["model"] = self.model
        if self.max_tokens:
            result["max_tokens"] = self.max_tokens
        if self.top_k is not None:
            result["top_k"] = self.top_k
        if self.frequency_penalty is not None:
            result["frequency_penalty"] = self.frequency_penalty
        if self.presence_penalty is not None:
            result["presence_penalty"] = self.presence_penalty
        if self.stop:
            result["stop"] = self.stop
        if self.tools:
            result["tools"] = [tool.to_dict() for tool in self.tools]
        if self.tool_choice is not None:
            result["tool_choice"] = self.tool_choice
        if self.response_format:
            result["response_format"] = self.response_format
        if self.metadata:
            result["metadata"] = self.metadata

        return result


class MessageConverter:
    """Utilities for converting messages between formats.

    Constitutional Hash: cdd01ef066bc6cf2

    Converts between our standard LLMMessage format and provider-specific
    message formats (OpenAI, Anthropic, Bedrock, etc.).
    """

    @staticmethod
    def to_openai_format(messages: list[LLMMessage]) -> list[JSONDict]:
        """Convert to OpenAI message format.

        Args:
            messages: Standard LLM messages

        Returns:
            list of OpenAI-formatted message dictionaries
        """
        result = []
        for msg in messages:
            openai_msg: JSONDict = {
                "role": msg.role,
                "content": msg.content,
            }
            if msg.name:
                openai_msg["name"] = msg.name
            if msg.tool_calls:
                openai_msg["tool_calls"] = msg.tool_calls
            if msg.tool_call_id:
                openai_msg["tool_call_id"] = msg.tool_call_id
            if msg.function_call:
                openai_msg["function_call"] = msg.function_call
            result.append(openai_msg)
        return result

    @staticmethod
    def to_anthropic_format(messages: list[LLMMessage]) -> list[JSONDict]:
        """Convert to Anthropic message format.

        Args:
            messages: Standard LLM messages

        Returns:
            list of Anthropic-formatted message dictionaries

        Note:
            Anthropic requires system messages to be passed separately.
            This method only converts user/assistant messages.
        """
        result = []
        for msg in messages:
            # Skip system messages (handled separately in Anthropic)
            if msg.role == "system":
                continue

            anthropic_msg: JSONDict = {
                "role": msg.role,
                "content": msg.content,
            }

            # Convert tool calls to Anthropic format
            if msg.tool_calls:
                anthropic_msg["content"] = [
                    {
                        "type": "tool_use",
                        "id": tc["id"],
                        "name": tc["function"]["name"],
                        "input": json.loads(tc["function"]["arguments"]),
                    }
                    for tc in msg.tool_calls
                ]

            result.append(anthropic_msg)
        return result

    @staticmethod
    def to_bedrock_format(messages: list[LLMMessage], provider: str = "anthropic") -> JSONDict:
        """Convert to AWS Bedrock message format.

        Args:
            messages: Standard LLM messages
            provider: Bedrock provider (anthropic, meta, cohere, etc.)

        Returns:
            Bedrock-formatted request body
        """
        if provider == "anthropic":
            # Bedrock uses Anthropic format for Claude models
            formatted_messages = MessageConverter.to_anthropic_format(messages)
            system_messages = [msg.content for msg in messages if msg.role == "system"]

            result: JSONDict = {
                "messages": formatted_messages,
            }
            if system_messages:
                result["system"] = " ".join(system_messages)
            return result
        else:
            # Generic format for other providers
            return {"messages": MessageConverter.to_openai_format(messages)}

    @staticmethod
    def from_openai_format(messages: list[JSONDict]) -> list[LLMMessage]:
        """Convert from OpenAI message format.

        Args:
            messages: OpenAI-formatted messages

        Returns:
            list of standard LLM messages
        """
        return [
            LLMMessage(
                role=msg["role"],
                content=msg.get("content", ""),
                name=msg.get("name"),
                tool_calls=msg.get("tool_calls"),
                tool_call_id=msg.get("tool_call_id"),
                function_call=msg.get("function_call"),
            )
            for msg in messages
        ]

    @staticmethod
    def from_anthropic_format(
        messages: list[JSONDict], system: str | None = None
    ) -> list[LLMMessage]:
        """Convert from Anthropic message format.

        Args:
            messages: Anthropic-formatted messages
            system: System message (passed separately in Anthropic)

        Returns:
            list of standard LLM messages
        """
        result = []

        # Add system message if provided
        if system:
            result.append(LLMMessage(role="system", content=system))

        # Convert messages
        for msg in messages:
            content = msg.get("content", "")
            tool_calls = None

            # Handle tool use in content
            if isinstance(content, list):
                tool_calls = [
                    {
                        "id": item["id"],
                        "type": "function",
                        "function": {
                            "name": item["name"],
                            "arguments": json.dumps(item["input"]),
                        },
                    }
                    for item in content
                    if item.get("type") == "tool_use"
                ]
                # Extract text content
                text_items = [
                    item.get("text", "") for item in content if item.get("type") == "text"
                ]
                content = " ".join(text_items) if text_items else ""

            result.append(
                LLMMessage(
                    role=msg["role"],
                    content=str(content),
                    tool_calls=tool_calls if tool_calls else None,
                )
            )

        return result


class RequestConverter:
    """Utilities for converting LLMRequest to provider-specific formats.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    @staticmethod
    def to_openai_request(request: LLMRequest) -> JSONDict:
        """Convert to OpenAI API request format.

        Args:
            request: Standard LLM request

        Returns:
            OpenAI API request parameters
        """
        result = {
            "messages": MessageConverter.to_openai_format(request.messages),
            "temperature": request.temperature,
            "top_p": request.top_p,
            "stream": request.stream,
        }

        if request.model:
            result["model"] = request.model
        if request.max_tokens:
            result["max_tokens"] = request.max_tokens
        if request.frequency_penalty is not None:
            result["frequency_penalty"] = request.frequency_penalty
        if request.presence_penalty is not None:
            result["presence_penalty"] = request.presence_penalty
        if request.stop:
            result["stop"] = request.stop
        if request.tools:
            result["tools"] = [tool.to_dict() for tool in request.tools]
        if request.tool_choice is not None:
            result["tool_choice"] = request.tool_choice
        if request.response_format:
            result["response_format"] = request.response_format

        return result

    @staticmethod
    def to_anthropic_request(request: LLMRequest) -> JSONDict:
        """Convert to Anthropic API request format.

        Args:
            request: Standard LLM request

        Returns:
            Anthropic API request parameters
        """
        # Extract system messages
        system_messages = [msg.content for msg in request.messages if msg.role == "system"]
        conversation_messages = [msg for msg in request.messages if msg.role != "system"]

        result = {
            "messages": MessageConverter.to_anthropic_format(conversation_messages),
            "temperature": request.temperature,
            "top_p": request.top_p,
        }

        if request.model:
            result["model"] = request.model
        if request.max_tokens:
            result["max_tokens"] = request.max_tokens
        if system_messages:
            result["system"] = " ".join(system_messages)
        if request.stop:
            result["stop_sequences"] = request.stop
        if request.tools:
            # Convert to Anthropic tool format
            result["tools"] = [
                {
                    "name": tool.function.name,
                    "description": tool.function.description,
                    "input_schema": tool.function.parameters.to_dict(),
                }
                for tool in request.tools
            ]
        if request.stream:
            result["stream"] = True

        return result

    @staticmethod
    def to_bedrock_request(
        request: LLMRequest, model_id: str, provider: str = "anthropic"
    ) -> JSONDict:
        """Convert to AWS Bedrock request format.

        Args:
            request: Standard LLM request
            model_id: Bedrock model identifier
            provider: Model provider (anthropic, meta, cohere, etc.)

        Returns:
            Bedrock InvokeModel request parameters
        """
        if provider == "anthropic":
            # Use Anthropic format for Claude models
            body = RequestConverter.to_anthropic_request(request)
        else:
            # Generic format for other providers
            body = RequestConverter.to_openai_request(request)

        return {
            "modelId": model_id,
            "body": json.dumps(body),
            "contentType": "application/json",
            "accept": "application/json",
        }


class ResponseConverter:
    """Utilities for converting provider responses to standard format.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    @staticmethod
    def from_openai_response(response: JSONDict, provider: str = "openai") -> LLMResponse:
        """Convert from OpenAI API response format.

        Args:
            response: OpenAI API response
            provider: Provider name for metadata

        Returns:
            Standard LLM response
        """
        choice = response["choices"][0]
        message = choice["message"]

        usage = response.get("usage", {})
        token_usage = TokenUsage(
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
        )

        metadata = CompletionMetadata(
            model=response.get("model", "unknown"),
            provider=provider,
            request_id=response.get("id", ""),
            finish_reason=choice.get("finish_reason", "stop"),
        )

        return LLMResponse(
            content=message.get("content", ""),
            messages=[LLMMessage(**message)],
            usage=token_usage,
            metadata=metadata,
            tool_calls=message.get("tool_calls"),
            raw_response=response,
        )

    @staticmethod
    def from_anthropic_response(response: JSONDict) -> LLMResponse:
        """Convert from Anthropic API response format.

        Args:
            response: Anthropic API response

        Returns:
            Standard LLM response
        """
        content = response.get("content", [])
        text_content = ""
        tool_calls = []

        # Extract text and tool calls from content blocks
        for block in content:
            if block.get("type") == "text":
                text_content += block.get("text", "")
            elif block.get("type") == "tool_use":
                tool_calls.append(
                    {
                        "id": block["id"],
                        "type": "function",
                        "function": {
                            "name": block["name"],
                            "arguments": json.dumps(block["input"]),
                        },
                    }
                )

        usage_data = response.get("usage", {})
        token_usage = TokenUsage(
            prompt_tokens=usage_data.get("input_tokens", 0),
            completion_tokens=usage_data.get("output_tokens", 0),
            total_tokens=usage_data.get("input_tokens", 0) + usage_data.get("output_tokens", 0),
        )

        metadata = CompletionMetadata(
            model=response.get("model", "unknown"),
            provider="anthropic",
            request_id=response.get("id", ""),
            finish_reason=response.get("stop_reason", "end_turn"),
        )

        return LLMResponse(
            content=text_content,
            messages=[
                LLMMessage(
                    role="assistant",
                    content=text_content,
                    tool_calls=tool_calls if tool_calls else None,
                )
            ],
            usage=token_usage,
            metadata=metadata,
            tool_calls=tool_calls if tool_calls else None,
            raw_response=response,
        )

    @staticmethod
    def from_bedrock_response(response: JSONDict, provider: str = "anthropic") -> LLMResponse:
        """Convert from AWS Bedrock response format.

        Args:
            response: Bedrock InvokeModel response
            provider: Model provider (anthropic, meta, cohere, etc.)

        Returns:
            Standard LLM response
        """
        # Parse body from Bedrock response
        body = json.loads(response.get("body", "{}"))

        if provider == "anthropic":
            return ResponseConverter.from_anthropic_response(body)
        else:
            # Assume OpenAI-compatible format
            return ResponseConverter.from_openai_response(body, provider=provider)
