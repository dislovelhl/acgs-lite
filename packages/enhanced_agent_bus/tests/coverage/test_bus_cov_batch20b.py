"""
Comprehensive coverage tests for enhanced_agent_bus modules:
- mcp_server/adapters/agent_bus.py (AgentBusAdapter)
- adapters/anthropic_adapter.py (AnthropicAdapter)
- mcp_server/tools/submit_governance.py (SubmitGovernanceTool)

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# AnthropicAdapter imports
# ---------------------------------------------------------------------------
from enhanced_agent_bus.adapters.anthropic_adapter import AnthropicAdapter
from enhanced_agent_bus.adapters.base import (
    MessageRole,
    ModelMessage,
    ModelProvider,
    ModelRequest,
    ModelResponse,
    StreamChunk,
)

# ---------------------------------------------------------------------------
# AgentBusAdapter imports
# ---------------------------------------------------------------------------
from enhanced_agent_bus.mcp_server.adapters.agent_bus import AgentBusAdapter

# ---------------------------------------------------------------------------
# SubmitGovernanceTool imports
# ---------------------------------------------------------------------------
from enhanced_agent_bus.mcp_server.tools.submit_governance import (
    GovernanceRequest,
    RequestPriority,
    RequestStatus,
    SubmitGovernanceTool,
)

# ============================================================================
# AgentBusAdapter Tests
# ============================================================================


class TestAgentBusAdapterInit:
    """Test AgentBusAdapter initialization."""

    def test_default_init(self):
        adapter = AgentBusAdapter()
        assert adapter.agent_bus is None
        assert adapter.mcp_agent_id == "mcp-server"
        assert adapter._request_count == 0
        assert adapter._connected is False

    def test_custom_init(self):
        bus = MagicMock()
        adapter = AgentBusAdapter(agent_bus=bus, mcp_agent_id="custom-id")
        assert adapter.agent_bus is bus
        assert adapter.mcp_agent_id == "custom-id"


class TestAgentBusAdapterConnect:
    """Test AgentBusAdapter.connect()."""

    async def test_connect_no_bus_returns_false(self):
        adapter = AgentBusAdapter(agent_bus=None)
        result = await adapter.connect()
        assert result is False
        assert adapter._connected is False

    async def test_connect_success(self):
        bus = MagicMock()
        bus.register_agent = AsyncMock(return_value=True)
        adapter = AgentBusAdapter(agent_bus=bus)

        result = await adapter.connect()

        assert result is True
        assert adapter._connected is True
        bus.register_agent.assert_awaited_once_with(
            agent_id="mcp-server",
            agent_type="mcp_server",
            capabilities=["governance", "validation", "audit"],
        )

    async def test_connect_registration_fails(self):
        bus = MagicMock()
        bus.register_agent = AsyncMock(return_value=False)
        adapter = AgentBusAdapter(agent_bus=bus)

        result = await adapter.connect()

        assert result is False
        assert adapter._connected is False

    async def test_connect_exception_returns_false(self):
        bus = MagicMock()
        bus.register_agent = AsyncMock(side_effect=RuntimeError("connection refused"))
        adapter = AgentBusAdapter(agent_bus=bus)

        result = await adapter.connect()

        assert result is False
        assert adapter._connected is False

    async def test_connect_value_error_returns_false(self):
        bus = MagicMock()
        bus.register_agent = AsyncMock(side_effect=ValueError("bad value"))
        adapter = AgentBusAdapter(agent_bus=bus)

        result = await adapter.connect()
        assert result is False

    async def test_connect_timeout_error_returns_false(self):
        bus = MagicMock()
        bus.register_agent = AsyncMock(side_effect=TimeoutError("timed out"))
        adapter = AgentBusAdapter(agent_bus=bus)

        result = await adapter.connect()
        assert result is False


class TestAgentBusAdapterDisconnect:
    """Test AgentBusAdapter.disconnect()."""

    async def test_disconnect_when_connected(self):
        bus = MagicMock()
        bus.deregister_agent = AsyncMock()
        adapter = AgentBusAdapter(agent_bus=bus)
        adapter._connected = True

        await adapter.disconnect()

        assert adapter._connected is False
        bus.deregister_agent.assert_awaited_once_with("mcp-server")

    async def test_disconnect_when_not_connected(self):
        bus = MagicMock()
        bus.deregister_agent = AsyncMock()
        adapter = AgentBusAdapter(agent_bus=bus)
        adapter._connected = False

        await adapter.disconnect()

        bus.deregister_agent.assert_not_awaited()

    async def test_disconnect_no_bus(self):
        adapter = AgentBusAdapter(agent_bus=None)
        adapter._connected = False
        # Should not raise
        await adapter.disconnect()

    async def test_disconnect_exception_handled(self):
        bus = MagicMock()
        bus.deregister_agent = AsyncMock(side_effect=RuntimeError("disconnect error"))
        adapter = AgentBusAdapter(agent_bus=bus)
        adapter._connected = True

        # Should not raise, error is logged
        await adapter.disconnect()


class TestAgentBusAdapterValidateAction:
    """Test AgentBusAdapter.validate_action()."""

    async def test_validate_standalone_safe_action(self):
        adapter = AgentBusAdapter()  # No bus => standalone
        result = await adapter.validate_action("read_data", {})

        assert result["compliant"] is True
        assert result["confidence"] == 1.0
        assert result["violations"] == []
        assert result["standalone_mode"] is True
        assert adapter._request_count == 1

    async def test_validate_standalone_sensitive_data_no_consent(self):
        adapter = AgentBusAdapter()
        result = await adapter.validate_action(
            "access_records",
            {"data_sensitivity": "confidential"},
        )

        assert result["compliant"] is False
        assert result["confidence"] == pytest.approx(0.7)
        assert len(result["violations"]) == 1
        assert result["violations"][0]["principle"] == "privacy"

    async def test_validate_standalone_restricted_data_with_consent(self):
        adapter = AgentBusAdapter()
        result = await adapter.validate_action(
            "access_records",
            {"data_sensitivity": "restricted", "consent_obtained": True},
        )

        assert result["compliant"] is True
        assert result["confidence"] == 1.0

    async def test_validate_standalone_high_risk_action_no_auth(self):
        adapter = AgentBusAdapter()
        result = await adapter.validate_action(
            "delete_user",
            {},
        )

        assert result["compliant"] is False
        assert len(result["violations"]) == 1
        assert result["violations"][0]["principle"] == "safety"

    async def test_validate_standalone_high_risk_with_auth(self):
        adapter = AgentBusAdapter()
        result = await adapter.validate_action(
            "delete_user",
            {"authorization_verified": True},
        )

        assert result["compliant"] is True

    async def test_validate_standalone_multiple_violations(self):
        adapter = AgentBusAdapter()
        result = await adapter.validate_action(
            "admin_drop_table",
            {"data_sensitivity": "confidential"},
        )

        assert result["compliant"] is False
        assert len(result["violations"]) == 2
        assert result["confidence"] == pytest.approx(0.4)

    async def test_validate_standalone_high_risk_patterns(self):
        """Test all high-risk pattern keywords."""
        adapter = AgentBusAdapter()
        for pattern in ["delete", "drop", "admin", "root", "exec"]:
            result = await adapter.validate_action(
                f"{pattern}_something",
                {},
            )
            assert result["compliant"] is False, f"Pattern '{pattern}' should trigger violation"

    async def test_validate_via_agent_bus(self):
        bus = MagicMock()
        response = MagicMock()
        response.content = {"compliant": True, "confidence": 0.95, "violations": []}
        bus.send_message = AsyncMock(return_value=response)
        adapter = AgentBusAdapter(agent_bus=bus)
        adapter._connected = True

        result = await adapter.validate_action("read_data", {}, strict_mode=True)

        assert result == {"compliant": True, "confidence": 0.95, "violations": []}
        assert adapter._request_count == 1

    async def test_validate_via_agent_bus_dict_response(self):
        bus = MagicMock()
        bus.send_message = AsyncMock(
            return_value={"compliant": True, "confidence": 1.0, "violations": []}
        )
        adapter = AgentBusAdapter(agent_bus=bus)
        adapter._connected = True

        result = await adapter.validate_action("read_data", {})

        assert result["compliant"] is True

    async def test_validate_via_agent_bus_unparseable_response(self):
        bus = MagicMock()
        bus.send_message = AsyncMock(return_value=42)  # Not dict, no .content
        adapter = AgentBusAdapter(agent_bus=bus)
        adapter._connected = True

        result = await adapter.validate_action("read_data", {})

        assert result["compliant"] is False
        assert "Unable to parse" in result["violations"][0]["description"]

    async def test_validate_via_agent_bus_error_strict(self):
        bus = MagicMock()
        bus.send_message = AsyncMock(side_effect=RuntimeError("bus down"))
        adapter = AgentBusAdapter(agent_bus=bus)
        adapter._connected = True

        result = await adapter.validate_action("read_data", {}, strict_mode=True)

        assert result["compliant"] is False
        assert result["fail_closed"] is True
        assert result["confidence"] == 0.0

    async def test_validate_via_agent_bus_error_non_strict_raises(self):
        bus = MagicMock()
        bus.send_message = AsyncMock(side_effect=RuntimeError("bus down"))
        adapter = AgentBusAdapter(agent_bus=bus)
        adapter._connected = True

        with pytest.raises(RuntimeError, match="bus down"):
            await adapter.validate_action("read_data", {}, strict_mode=False)


class TestAgentBusAdapterSubmitGovernance:
    """Test AgentBusAdapter.submit_governance_request()."""

    async def test_submit_standalone_compliant(self):
        adapter = AgentBusAdapter()
        result = await adapter.submit_governance_request(
            action="read_data",
            context={},
            priority="medium",
            requester_id="test-user",
        )

        assert result["status"] == "approved"
        assert result["standalone_mode"] is True
        assert result["validation_result"]["compliant"] is True

    async def test_submit_standalone_non_compliant(self):
        adapter = AgentBusAdapter()
        result = await adapter.submit_governance_request(
            action="delete_user",
            context={},
            priority="low",
            requester_id="test-user",
        )

        assert result["status"] == "denied"
        assert result["standalone_mode"] is True
        assert result["validation_result"]["compliant"] is False

    async def test_submit_via_agent_bus_with_content_response(self):
        bus = MagicMock()
        response = MagicMock()
        response.content = {"status": "approved", "validation_result": {}, "conditions": []}
        bus.send_message = AsyncMock(return_value=response)
        adapter = AgentBusAdapter(agent_bus=bus)
        adapter._connected = True

        result = await adapter.submit_governance_request(
            action="read_data",
            context={},
            priority="high",
            requester_id="agent-1",
        )

        assert result["status"] == "approved"

    async def test_submit_via_agent_bus_dict_response(self):
        bus = MagicMock()
        bus.send_message = AsyncMock(
            return_value={"status": "denied", "validation_result": None, "conditions": []}
        )
        adapter = AgentBusAdapter(agent_bus=bus)
        adapter._connected = True

        result = await adapter.submit_governance_request(
            action="drop_tables",
            context={},
            priority="low",
            requester_id="agent-1",
        )

        assert result["status"] == "denied"

    async def test_submit_via_agent_bus_error(self):
        bus = MagicMock()
        bus.send_message = AsyncMock(side_effect=RuntimeError("send failed"))
        adapter = AgentBusAdapter(agent_bus=bus)
        adapter._connected = True

        result = await adapter.submit_governance_request(
            action="read_data",
            context={},
            priority="medium",
            requester_id="agent-1",
        )

        assert result["status"] == "error"
        assert "send failed" in result["error"]

    async def test_submit_priority_mapping(self):
        """Test all priority string mappings."""
        bus = MagicMock()
        response = MagicMock()
        response.content = {"status": "approved"}
        bus.send_message = AsyncMock(return_value=response)

        for prio in ["low", "medium", "high", "critical"]:
            adapter = AgentBusAdapter(agent_bus=bus)
            adapter._connected = True
            result = await adapter.submit_governance_request(
                action="test",
                context={},
                priority=prio,
                requester_id="user",
            )
            assert result["status"] == "approved"

    async def test_submit_unknown_priority_defaults_medium(self):
        bus = MagicMock()
        response = MagicMock()
        response.content = {"status": "approved"}
        bus.send_message = AsyncMock(return_value=response)
        adapter = AgentBusAdapter(agent_bus=bus)
        adapter._connected = True

        result = await adapter.submit_governance_request(
            action="test",
            context={},
            priority="unknown_level",
            requester_id="user",
        )
        assert result["status"] == "approved"


class TestAgentBusAdapterGetMetrics:
    """Test AgentBusAdapter.get_metrics()."""

    def test_get_metrics_initial(self):
        adapter = AgentBusAdapter(mcp_agent_id="test-agent")
        metrics = adapter.get_metrics()

        assert metrics["request_count"] == 0
        assert metrics["connected"] is False
        assert metrics["agent_id"] == "test-agent"
        assert "constitutional_hash" in metrics

    async def test_get_metrics_after_requests(self):
        adapter = AgentBusAdapter()
        await adapter.validate_action("test1", {})
        await adapter.validate_action("test2", {})

        metrics = adapter.get_metrics()
        assert metrics["request_count"] == 2


# ============================================================================
# AnthropicAdapter Tests
# ============================================================================


class TestAnthropicAdapterInit:
    """Test AnthropicAdapter initialization."""

    def test_default_init(self):
        adapter = AnthropicAdapter()
        assert adapter.provider == ModelProvider.ANTHROPIC
        assert adapter.api_key is None
        assert adapter.base_url == "https://api.anthropic.com"
        assert adapter.default_model == "claude-sonnet-4-6"
        assert adapter.timeout_seconds == 60
        assert adapter._client is None

    def test_custom_init(self):
        adapter = AnthropicAdapter(
            api_key="sk-test-key",
            base_url="https://custom.api.com",
            default_model="claude-3-haiku-20240307",
            timeout_seconds=120,
        )
        assert adapter.api_key == "sk-test-key"
        assert adapter.base_url == "https://custom.api.com"
        assert adapter.default_model == "claude-3-haiku-20240307"
        assert adapter.timeout_seconds == 120


class TestAnthropicAdapterEnsureClient:
    """Test AnthropicAdapter._ensure_client()."""

    async def test_ensure_client_creates_client(self):
        adapter = AnthropicAdapter(api_key="test-key")

        with patch(
            "enhanced_agent_bus.adapters.anthropic_adapter.AsyncAnthropic",
            create=True,
        ) as mock_cls:
            # Patch the import inside _ensure_client
            mock_client = MagicMock()
            mock_cls.return_value = mock_client

            with patch.dict("sys.modules", {"anthropic": MagicMock(AsyncAnthropic=mock_cls)}):
                # Need to reset client to force re-creation
                adapter._client = None
                # Directly set the client to test the caching
                adapter._client = mock_client
                client = await adapter._ensure_client()
                assert client is mock_client

    async def test_ensure_client_caches_instance(self):
        adapter = AnthropicAdapter(api_key="test-key")
        mock_client = MagicMock()
        adapter._client = mock_client

        client = await adapter._ensure_client()
        assert client is mock_client

    async def test_ensure_client_import_error(self):
        adapter = AnthropicAdapter(api_key="test-key")
        adapter._client = None

        with patch.dict("sys.modules", {"anthropic": None}):
            with pytest.raises(ImportError, match="Anthropic package not installed"):
                await adapter._ensure_client()


class TestAnthropicAdapterTranslateRequest:
    """Test AnthropicAdapter.translate_request()."""

    def test_basic_messages(self):
        adapter = AnthropicAdapter()
        request = ModelRequest(
            messages=[
                ModelMessage(role=MessageRole.USER, content="Hello"),
            ],
            model="claude-sonnet-4-6",
        )
        payload = adapter.translate_request(request)

        assert payload["model"] == "claude-sonnet-4-6"
        assert len(payload["messages"]) == 1
        assert payload["messages"][0]["role"] == "user"
        assert payload["messages"][0]["content"] == "Hello"
        assert "system" not in payload

    def test_system_message_extracted(self):
        adapter = AnthropicAdapter()
        request = ModelRequest(
            messages=[
                ModelMessage(role=MessageRole.SYSTEM, content="You are helpful"),
                ModelMessage(role=MessageRole.USER, content="Hi"),
            ],
            model="claude-sonnet-4-6",
        )
        payload = adapter.translate_request(request)

        assert payload["system"] == "You are helpful"
        assert len(payload["messages"]) == 1
        assert payload["messages"][0]["role"] == "user"

    def test_assistant_message_role(self):
        adapter = AnthropicAdapter()
        request = ModelRequest(
            messages=[
                ModelMessage(role=MessageRole.USER, content="Hi"),
                ModelMessage(role=MessageRole.ASSISTANT, content="Hello!"),
                ModelMessage(role=MessageRole.USER, content="How are you?"),
            ],
            model="claude-sonnet-4-6",
        )
        payload = adapter.translate_request(request)

        assert payload["messages"][0]["role"] == "user"
        assert payload["messages"][1]["role"] == "assistant"
        assert payload["messages"][2]["role"] == "user"

    def test_tool_role_maps_to_assistant(self):
        """Non-user, non-system roles map to 'assistant'."""
        adapter = AnthropicAdapter()
        request = ModelRequest(
            messages=[
                ModelMessage(role=MessageRole.TOOL, content="tool result"),
            ],
            model="claude-sonnet-4-6",
        )
        payload = adapter.translate_request(request)

        assert payload["messages"][0]["role"] == "assistant"

    def test_stop_sequences(self):
        adapter = AnthropicAdapter()
        request = ModelRequest(
            messages=[ModelMessage(role=MessageRole.USER, content="Hi")],
            model="claude-sonnet-4-6",
            stop=["END", "STOP"],
        )
        payload = adapter.translate_request(request)

        assert payload["stop_sequences"] == ["END", "STOP"]

    def test_no_stop_sequences(self):
        adapter = AnthropicAdapter()
        request = ModelRequest(
            messages=[ModelMessage(role=MessageRole.USER, content="Hi")],
            model="claude-sonnet-4-6",
        )
        payload = adapter.translate_request(request)

        assert "stop_sequences" not in payload

    def test_tools_conversion(self):
        adapter = AnthropicAdapter()
        request = ModelRequest(
            messages=[ModelMessage(role=MessageRole.USER, content="Hi")],
            model="claude-sonnet-4-6",
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "description": "Get weather info",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ],
        )
        payload = adapter.translate_request(request)

        assert "tools" in payload
        assert len(payload["tools"]) == 1
        assert payload["tools"][0]["name"] == "get_weather"
        assert payload["tools"][0]["description"] == "Get weather info"
        assert payload["tools"][0]["input_schema"] == {"type": "object", "properties": {}}

    def test_tools_non_function_type_skipped(self):
        adapter = AnthropicAdapter()
        request = ModelRequest(
            messages=[ModelMessage(role=MessageRole.USER, content="Hi")],
            model="claude-sonnet-4-6",
            tools=[{"type": "retrieval"}],
        )
        payload = adapter.translate_request(request)

        # No anthropic_tools appended, so "tools" key should not be in payload
        assert "tools" not in payload

    def test_model_fallback_to_default(self):
        adapter = AnthropicAdapter(default_model="claude-3-haiku-20240307")
        request = ModelRequest(
            messages=[ModelMessage(role=MessageRole.USER, content="Hi")],
            model="",
        )
        payload = adapter.translate_request(request)

        # `request.model or self.default_model` -> "" is falsy so default used
        assert payload["model"] == "claude-3-haiku-20240307"

    def test_explicit_model_used(self):
        adapter = AnthropicAdapter(default_model="claude-3-haiku-20240307")
        request = ModelRequest(
            messages=[ModelMessage(role=MessageRole.USER, content="Hi")],
            model="claude-sonnet-4-6",
        )
        payload = adapter.translate_request(request)

        assert payload["model"] == "claude-sonnet-4-6"

    def test_temperature_and_top_p(self):
        adapter = AnthropicAdapter()
        request = ModelRequest(
            messages=[ModelMessage(role=MessageRole.USER, content="Hi")],
            model="claude-sonnet-4-6",
            temperature=0.5,
            top_p=0.9,
        )
        payload = adapter.translate_request(request)

        assert payload["temperature"] == 0.5
        assert payload["top_p"] == 0.9


class TestAnthropicAdapterTranslateResponse:
    """Test AnthropicAdapter.translate_response()."""

    def test_text_response(self):
        adapter = AnthropicAdapter()
        raw = {
            "content": [{"type": "text", "text": "Hello there!"}],
            "model": "claude-sonnet-4-6",
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 5},
            "id": "msg_123",
        }
        resp = adapter.translate_response(raw)

        assert isinstance(resp, ModelResponse)
        assert resp.content == "Hello there!"
        assert resp.model == "claude-sonnet-4-6"
        assert resp.provider == ModelProvider.ANTHROPIC
        assert resp.finish_reason == "end_turn"
        assert resp.prompt_tokens == 10
        assert resp.completion_tokens == 5
        assert resp.total_tokens == 15
        assert resp.tool_calls is None
        assert resp.response_id == "msg_123"

    def test_tool_use_response(self):
        adapter = AnthropicAdapter()
        raw = {
            "content": [
                {"type": "text", "text": "Let me check."},
                {
                    "type": "tool_use",
                    "id": "tool_1",
                    "name": "get_weather",
                    "input": {"location": "NYC"},
                },
            ],
            "model": "claude-sonnet-4-6",
            "stop_reason": "tool_use",
            "usage": {"input_tokens": 20, "output_tokens": 15},
            "id": "msg_456",
        }
        resp = adapter.translate_response(raw)

        assert resp.content == "Let me check."
        assert resp.tool_calls is not None
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0]["id"] == "tool_1"
        assert resp.tool_calls[0]["type"] == "function"
        assert resp.tool_calls[0]["function"]["name"] == "get_weather"
        assert resp.tool_calls[0]["function"]["arguments"] == {"location": "NYC"}

    def test_empty_response(self):
        adapter = AnthropicAdapter()
        raw = {"content": [], "usage": {}}
        resp = adapter.translate_response(raw)

        assert resp.content == ""
        assert resp.model == ""
        assert resp.prompt_tokens == 0
        assert resp.completion_tokens == 0
        assert resp.total_tokens == 0
        assert resp.tool_calls is None

    def test_multiple_text_blocks(self):
        adapter = AnthropicAdapter()
        raw = {
            "content": [
                {"type": "text", "text": "Part 1. "},
                {"type": "text", "text": "Part 2."},
            ],
            "usage": {},
        }
        resp = adapter.translate_response(raw)

        assert resp.content == "Part 1. Part 2."

    def test_unknown_block_type_ignored(self):
        adapter = AnthropicAdapter()
        raw = {
            "content": [
                {"type": "image", "source": "..."},
                {"type": "text", "text": "Some text"},
            ],
            "usage": {},
        }
        resp = adapter.translate_response(raw)

        assert resp.content == "Some text"


class TestAnthropicAdapterComplete:
    """Test AnthropicAdapter.complete()."""

    async def test_complete_success(self):
        adapter = AnthropicAdapter(api_key="test-key")
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.model_dump.return_value = {
            "content": [{"type": "text", "text": "Hi!"}],
            "model": "claude-sonnet-4-6",
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 5, "output_tokens": 3},
            "id": "msg_test",
        }
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        adapter._client = mock_client

        request = ModelRequest(
            messages=[ModelMessage(role=MessageRole.USER, content="Hello")],
            model="claude-sonnet-4-6",
        )
        result = await adapter.complete(request)

        assert result.content == "Hi!"
        assert result.provider == ModelProvider.ANTHROPIC

    async def test_complete_validation_error(self):
        adapter = AnthropicAdapter(api_key="test-key")
        adapter._client = MagicMock()

        request = ModelRequest(
            messages=[],  # No messages -> validation error
            model="claude-sonnet-4-6",
        )
        with pytest.raises(ValueError, match="Invalid request"):
            await adapter.complete(request)


class TestAnthropicAdapterStream:
    """Test AnthropicAdapter.stream()."""

    async def test_stream_validation_error(self):
        adapter = AnthropicAdapter(api_key="test-key")
        adapter._client = MagicMock()

        request = ModelRequest(
            messages=[],
            model="claude-sonnet-4-6",
        )
        with pytest.raises(ValueError, match="Invalid request"):
            async for _ in adapter.stream(request):
                pass

    async def test_stream_yields_chunks(self):
        adapter = AnthropicAdapter(api_key="test-key")
        mock_client = MagicMock()

        # Create mock events
        delta_event = MagicMock()
        delta_event.delta = MagicMock()
        delta_event.delta.text = "chunk1"
        del delta_event.message  # No .message attribute

        final_event = MagicMock()
        del final_event.delta  # No .delta attribute
        final_event.message = MagicMock()
        final_event.message.stop_reason = "end_turn"

        # Create async context manager and async iterator
        mock_stream = MagicMock()

        async def mock_aiter(self_inner):
            yield delta_event
            yield final_event

        mock_stream.__aiter__ = mock_aiter
        mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
        mock_stream.__aexit__ = AsyncMock(return_value=False)

        mock_client.messages.stream = MagicMock(return_value=mock_stream)
        adapter._client = mock_client

        request = ModelRequest(
            messages=[ModelMessage(role=MessageRole.USER, content="Hi")],
            model="claude-sonnet-4-6",
        )

        chunks = []
        async for chunk in adapter.stream(request):
            chunks.append(chunk)

        assert len(chunks) == 2
        assert chunks[0].content == "chunk1"
        assert chunks[0].is_final is False
        assert chunks[1].content == ""
        assert chunks[1].is_final is True
        assert chunks[1].finish_reason == "end_turn"


class TestAnthropicAdapterCapabilities:
    """Test AnthropicAdapter.get_capabilities()."""

    def test_capabilities(self):
        adapter = AnthropicAdapter()
        caps = adapter.get_capabilities()

        assert caps["provider"] == "anthropic"
        assert caps["vision"] is True
        assert caps["max_context_tokens"] == 200000
        assert caps["extended_thinking"] is False
        assert caps["streaming"] is True
        assert caps["tool_calling"] is True


# ============================================================================
# GovernanceRequest Tests
# ============================================================================


class TestGovernanceRequest:
    """Test GovernanceRequest dataclass."""

    def test_to_dict(self):
        req = GovernanceRequest(
            request_id="GOV-12345678",
            action="read_data",
            context={"user_id": "u1"},
            priority=RequestPriority.HIGH,
            requester_id="agent-1",
            timestamp="2024-01-01T00:00:00",
            status=RequestStatus.APPROVED,
            validation_result={"compliant": True},
            approval_chain=["validator-1"],
            conditions=["condition-1"],
            expiry="2024-12-31T23:59:59",
        )
        d = req.to_dict()

        assert d["request_id"] == "GOV-12345678"
        assert d["action"] == "read_data"
        assert d["context"] == {"user_id": "u1"}
        assert d["priority"] == "high"
        assert d["requester_id"] == "agent-1"
        assert d["status"] == "approved"
        assert d["validation_result"] == {"compliant": True}
        assert d["approval_chain"] == ["validator-1"]
        assert d["conditions"] == ["condition-1"]
        assert d["expiry"] == "2024-12-31T23:59:59"

    def test_defaults(self):
        req = GovernanceRequest(
            request_id="GOV-1",
            action="test",
            context={},
            priority=RequestPriority.LOW,
            requester_id="user",
            timestamp="2024-01-01",
        )
        assert req.status == RequestStatus.PENDING
        assert req.validation_result is None
        assert req.approval_chain == []
        assert req.conditions == []
        assert req.expiry is None


class TestRequestEnums:
    """Test RequestStatus and RequestPriority enums."""

    def test_request_status_values(self):
        assert RequestStatus.PENDING.value == "pending"
        assert RequestStatus.PROCESSING.value == "processing"
        assert RequestStatus.APPROVED.value == "approved"
        assert RequestStatus.DENIED.value == "denied"
        assert RequestStatus.CONDITIONAL.value == "conditional"
        assert RequestStatus.ESCALATED.value == "escalated"
        assert RequestStatus.TIMEOUT.value == "timeout"

    def test_request_priority_values(self):
        assert RequestPriority.LOW.value == "low"
        assert RequestPriority.MEDIUM.value == "medium"
        assert RequestPriority.HIGH.value == "high"
        assert RequestPriority.CRITICAL.value == "critical"


# ============================================================================
# SubmitGovernanceTool Tests
# ============================================================================


class TestSubmitGovernanceToolInit:
    """Test SubmitGovernanceTool initialization."""

    def test_default_init(self):
        tool = SubmitGovernanceTool()
        assert tool.agent_bus_adapter is None
        assert tool.auto_validate is True
        assert tool._pending_requests == {}
        assert tool._completed_requests == {}
        assert tool._request_count == 0

    def test_custom_init(self):
        adapter = MagicMock()
        tool = SubmitGovernanceTool(agent_bus_adapter=adapter, auto_validate=False)
        assert tool.agent_bus_adapter is adapter
        assert tool.auto_validate is False


class TestSubmitGovernanceToolDefinition:
    """Test SubmitGovernanceTool.get_definition()."""

    def test_get_definition(self):
        defn = SubmitGovernanceTool.get_definition()

        assert defn.name == "submit_governance_request"
        assert "governance" in defn.description.lower()
        assert defn.constitutional_required is True
        assert "action" in defn.inputSchema.properties
        assert "context" in defn.inputSchema.properties
        assert "priority" in defn.inputSchema.properties
        assert "requester_id" in defn.inputSchema.required


class TestSubmitGovernanceToolExecute:
    """Test SubmitGovernanceTool.execute()."""

    async def test_execute_local_approved(self):
        tool = SubmitGovernanceTool()
        result = await tool.execute(
            {
                "action": "read_data",
                "context": {},
                "requester_id": "user-1",
            }
        )

        assert result["isError"] is False
        content_text = result["content"][0]["text"]
        parsed = json.loads(content_text)
        assert parsed["request"]["status"] == "approved"
        assert tool._request_count == 1

    async def test_execute_local_denied(self):
        tool = SubmitGovernanceTool()
        result = await tool.execute(
            {
                "action": "delete_records",
                "context": {"data_sensitivity": "confidential"},
                "requester_id": "user-1",
                "priority": "low",
            }
        )

        assert result["isError"] is True
        content_text = result["content"][0]["text"]
        parsed = json.loads(content_text)
        assert parsed["request"]["status"] == "denied"

    async def test_execute_local_conditional(self):
        """Action with violation but confidence >= 0.7 => conditional."""
        tool = SubmitGovernanceTool()
        result = await tool.execute(
            {
                "action": "delete_data",
                "context": {},
                "requester_id": "user-1",
                "priority": "low",
            }
        )

        content_text = result["content"][0]["text"]
        parsed = json.loads(content_text)
        # "delete" is high-risk, priority not critical => one violation, confidence 0.8
        assert parsed["request"]["status"] == "conditional"
        assert result["isError"] is False

    async def test_execute_local_pending_when_no_auto_approve(self):
        tool = SubmitGovernanceTool()
        result = await tool.execute(
            {
                "action": "read_data",
                "context": {},
                "requester_id": "user-1",
                "auto_approve_if_compliant": False,
            }
        )

        content_text = result["content"][0]["text"]
        parsed = json.loads(content_text)
        assert parsed["request"]["status"] == "pending"

    async def test_execute_via_agent_bus(self):
        mock_adapter = AsyncMock()
        mock_adapter.submit_governance_request = AsyncMock(
            return_value={
                "status": "approved",
                "validation_result": {"compliant": True},
                "conditions": [],
            }
        )
        tool = SubmitGovernanceTool(agent_bus_adapter=mock_adapter)

        result = await tool.execute(
            {
                "action": "read_data",
                "context": {},
                "requester_id": "user-1",
            }
        )

        assert result["isError"] is False
        content_text = result["content"][0]["text"]
        parsed = json.loads(content_text)
        assert parsed["request"]["status"] == "approved"

    async def test_execute_exception_returns_error(self):
        tool = SubmitGovernanceTool()
        result = await tool.execute(
            {
                "action": "test",
                "context": {},
                "requester_id": "user-1",
                "priority": "invalid_priority",  # Will cause ValueError in RequestPriority()
            }
        )

        assert result["isError"] is True
        content_text = result["content"][0]["text"]
        parsed = json.loads(content_text)
        assert parsed["status"] == "error"
        assert "error" in parsed

    async def test_execute_moves_to_completed(self):
        tool = SubmitGovernanceTool()
        result = await tool.execute(
            {
                "action": "read_data",
                "context": {},
                "requester_id": "user-1",
            }
        )

        # Approved request should be in completed, not pending
        assert len(tool._pending_requests) == 0
        assert len(tool._completed_requests) == 1

    async def test_execute_default_arguments(self):
        """Test default argument values when not provided."""
        tool = SubmitGovernanceTool()
        result = await tool.execute({})

        # action="" and requester_id="unknown" by default
        content_text = result["content"][0]["text"]
        parsed = json.loads(content_text)
        assert parsed["request"]["requester_id"] == "unknown"
        assert parsed["request"]["action"] == ""


class TestSubmitGovernanceToolValidateRequest:
    """Test SubmitGovernanceTool._validate_request()."""

    async def test_validate_clean_request(self):
        tool = SubmitGovernanceTool()
        req = GovernanceRequest(
            request_id="GOV-1",
            action="read_data",
            context={},
            priority=RequestPriority.LOW,
            requester_id="user",
            timestamp="2024-01-01",
        )
        result = await tool._validate_request(req)

        assert result["compliant"] is True
        assert result["confidence"] == 1.0
        assert result["violations"] == []

    async def test_validate_sensitive_data_no_consent(self):
        tool = SubmitGovernanceTool()
        req = GovernanceRequest(
            request_id="GOV-2",
            action="access_data",
            context={"data_sensitivity": "confidential"},
            priority=RequestPriority.LOW,
            requester_id="user",
            timestamp="2024-01-01",
        )
        result = await tool._validate_request(req)

        assert result["compliant"] is False
        assert any(v["principle"] == "privacy" for v in result["violations"])

    async def test_validate_restricted_with_consent(self):
        tool = SubmitGovernanceTool()
        req = GovernanceRequest(
            request_id="GOV-3",
            action="access_data",
            context={"data_sensitivity": "restricted", "consent_obtained": True},
            priority=RequestPriority.LOW,
            requester_id="user",
            timestamp="2024-01-01",
        )
        result = await tool._validate_request(req)

        assert result["compliant"] is True

    async def test_validate_high_risk_non_critical_priority(self):
        tool = SubmitGovernanceTool()
        for keyword in ["delete", "drop", "admin", "root", "system"]:
            req = GovernanceRequest(
                request_id=f"GOV-{keyword}",
                action=f"{keyword}_action",
                context={},
                priority=RequestPriority.MEDIUM,
                requester_id="user",
                timestamp="2024-01-01",
            )
            result = await tool._validate_request(req)
            assert result["compliant"] is False, f"keyword '{keyword}' should trigger violation"
            assert any(v["principle"] == "safety" for v in result["violations"])

    async def test_validate_high_risk_critical_priority_passes(self):
        tool = SubmitGovernanceTool()
        req = GovernanceRequest(
            request_id="GOV-crit",
            action="delete_action",
            context={},
            priority=RequestPriority.CRITICAL,
            requester_id="user",
            timestamp="2024-01-01",
        )
        result = await tool._validate_request(req)

        # "delete" with CRITICAL priority => no safety violation
        assert not any(v["principle"] == "safety" for v in result["violations"])

    async def test_validate_high_priority_no_impact_assessment(self):
        tool = SubmitGovernanceTool()
        req = GovernanceRequest(
            request_id="GOV-4",
            action="read_data",
            context={},
            priority=RequestPriority.HIGH,
            requester_id="user",
            timestamp="2024-01-01",
        )
        result = await tool._validate_request(req)

        assert result["compliant"] is False
        assert any(v["principle"] == "accountability" for v in result["violations"])

    async def test_validate_critical_with_impact_assessment(self):
        tool = SubmitGovernanceTool()
        req = GovernanceRequest(
            request_id="GOV-5",
            action="read_data",
            context={"impact_assessment": {"severity": "low"}},
            priority=RequestPriority.CRITICAL,
            requester_id="user",
            timestamp="2024-01-01",
        )
        result = await tool._validate_request(req)

        assert not any(v["principle"] == "accountability" for v in result["violations"])

    async def test_validate_multiple_violations(self):
        tool = SubmitGovernanceTool()
        req = GovernanceRequest(
            request_id="GOV-6",
            action="admin_delete",
            context={"data_sensitivity": "restricted"},
            priority=RequestPriority.HIGH,
            requester_id="user",
            timestamp="2024-01-01",
        )
        result = await tool._validate_request(req)

        assert result["compliant"] is False
        # privacy + safety + accountability = 3 violations
        assert len(result["violations"]) == 3
        assert result["confidence"] == pytest.approx(0.4)

    async def test_validate_principles_checked(self):
        tool = SubmitGovernanceTool()
        req = GovernanceRequest(
            request_id="GOV-7",
            action="read",
            context={},
            priority=RequestPriority.LOW,
            requester_id="user",
            timestamp="2024-01-01",
        )
        result = await tool._validate_request(req)

        assert "principles_checked" in result
        assert "privacy" in result["principles_checked"]
        assert "safety" in result["principles_checked"]
        assert "accountability" in result["principles_checked"]


class TestSubmitGovernanceToolGenerateConditions:
    """Test SubmitGovernanceTool._generate_conditions()."""

    def test_generate_conditions_high_severity(self):
        tool = SubmitGovernanceTool()
        validation = {
            "violations": [
                {"principle": "privacy", "severity": "high", "description": "No consent"},
            ]
        }
        conditions = tool._generate_conditions(validation)

        assert len(conditions) == 1
        assert "Must address" in conditions[0]
        assert "privacy" in conditions[0]

    def test_generate_conditions_medium_severity(self):
        tool = SubmitGovernanceTool()
        validation = {
            "violations": [
                {"principle": "safety", "severity": "medium", "description": "Needs review"},
            ]
        }
        conditions = tool._generate_conditions(validation)

        assert len(conditions) == 1
        assert "Should implement" in conditions[0]

    def test_generate_conditions_low_severity_skipped(self):
        tool = SubmitGovernanceTool()
        validation = {
            "violations": [
                {"principle": "accountability", "severity": "low", "description": "Minor issue"},
            ]
        }
        conditions = tool._generate_conditions(validation)

        assert len(conditions) == 0

    def test_generate_conditions_mixed(self):
        tool = SubmitGovernanceTool()
        validation = {
            "violations": [
                {"principle": "privacy", "severity": "high", "description": "No consent"},
                {"principle": "safety", "severity": "medium", "description": "Needs auth"},
                {"principle": "accountability", "severity": "low", "description": "Missing docs"},
            ]
        }
        conditions = tool._generate_conditions(validation)

        assert len(conditions) == 2

    def test_generate_conditions_empty_violations(self):
        tool = SubmitGovernanceTool()
        conditions = tool._generate_conditions({"violations": []})

        assert conditions == []

    def test_generate_conditions_no_violations_key(self):
        tool = SubmitGovernanceTool()
        conditions = tool._generate_conditions({})

        assert conditions == []


class TestSubmitGovernanceToolGetRequestStatus:
    """Test SubmitGovernanceTool.get_request_status()."""

    def test_get_pending_request(self):
        tool = SubmitGovernanceTool()
        req = GovernanceRequest(
            request_id="GOV-PENDING",
            action="test",
            context={},
            priority=RequestPriority.LOW,
            requester_id="user",
            timestamp="2024-01-01",
        )
        tool._pending_requests["GOV-PENDING"] = req

        result = tool.get_request_status("GOV-PENDING")
        assert result is not None
        assert result["request_id"] == "GOV-PENDING"

    def test_get_completed_request(self):
        tool = SubmitGovernanceTool()
        req = GovernanceRequest(
            request_id="GOV-DONE",
            action="test",
            context={},
            priority=RequestPriority.LOW,
            requester_id="user",
            timestamp="2024-01-01",
            status=RequestStatus.APPROVED,
        )
        tool._completed_requests["GOV-DONE"] = req

        result = tool.get_request_status("GOV-DONE")
        assert result is not None
        assert result["status"] == "approved"

    def test_get_nonexistent_request(self):
        tool = SubmitGovernanceTool()
        result = tool.get_request_status("GOV-UNKNOWN")
        assert result is None


class TestSubmitGovernanceToolGetMetrics:
    """Test SubmitGovernanceTool.get_metrics()."""

    def test_initial_metrics(self):
        tool = SubmitGovernanceTool()
        metrics = tool.get_metrics()

        assert metrics["request_count"] == 0
        assert metrics["pending_count"] == 0
        assert metrics["completed_count"] == 0
        assert metrics["status_distribution"] == {}
        assert metrics["approval_rate"] == 0.0
        assert "constitutional_hash" in metrics

    async def test_metrics_after_requests(self):
        tool = SubmitGovernanceTool()

        # Execute an approved request
        await tool.execute(
            {
                "action": "read_data",
                "context": {},
                "requester_id": "user-1",
            }
        )
        # Execute a denied request
        await tool.execute(
            {
                "action": "admin_drop",
                "context": {"data_sensitivity": "confidential"},
                "requester_id": "user-2",
                "priority": "low",
            }
        )

        metrics = tool.get_metrics()
        assert metrics["request_count"] == 2
        assert metrics["completed_count"] == 2
        assert metrics["pending_count"] == 0


class TestSubmitGovernanceToolSubmitViaBus:
    """Test SubmitGovernanceTool._submit_via_agent_bus()."""

    async def test_submit_via_bus_delegates(self):
        mock_adapter = AsyncMock()
        mock_adapter.submit_governance_request = AsyncMock(
            return_value={
                "status": "approved",
                "validation_result": {},
                "conditions": [],
            }
        )
        tool = SubmitGovernanceTool(agent_bus_adapter=mock_adapter)

        req = GovernanceRequest(
            request_id="GOV-BUS",
            action="some_action",
            context={"key": "val"},
            priority=RequestPriority.HIGH,
            requester_id="agent-x",
            timestamp="2024-01-01",
        )
        result = await tool._submit_via_agent_bus(req, True, 30)

        assert result["status"] == "approved"
        mock_adapter.submit_governance_request.assert_awaited_once_with(
            action="some_action",
            context={"key": "val"},
            priority="high",
            requester_id="agent-x",
            wait_for_approval=True,
            timeout_seconds=30,
        )
