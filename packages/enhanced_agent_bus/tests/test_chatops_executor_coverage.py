"""
Tests for agents/chatops_executor.py
Constitutional Hash: 608508a9bd224290
"""

import sys
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

from enhanced_agent_bus.core_models import AgentMessage, MessageType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_msg(
    to_agent: str = "chatops_executor",
    message_type: MessageType = MessageType.COMMAND,
    content: object = None,
) -> AgentMessage:
    """Build a minimal AgentMessage for testing."""
    if content is None:
        content = {
            "command_body": "/acgs-build-fix",
            "author": "tester",
            "issue_number": 42,
        }
    return AgentMessage(
        from_agent="github_app",
        to_agent=to_agent,
        message_type=message_type,
        content=content,
    )


def _make_context_result(success: bool = True, data: object = None) -> MagicMock:
    """Build a mock context result returned by mcp_client.call_tool."""
    result = MagicMock()
    result.success = success
    result.data = data or {"context": "some open-aware context"}
    return result


# ---------------------------------------------------------------------------
# Routing guard tests (wrong to_agent / wrong message_type)
# ---------------------------------------------------------------------------


class TestRoutingGuards:
    """Tests for the early-return guards at the top of handle_chatops_command."""

    async def test_wrong_to_agent_returns_none(self) -> None:
        """Messages addressed to a different agent must be ignored."""
        from enhanced_agent_bus.agents.chatops_executor import (
            handle_chatops_command,
        )

        msg = _make_msg(to_agent="some_other_agent")
        result = await handle_chatops_command(msg)
        assert result is None

    async def test_wrong_message_type_returns_none(self) -> None:
        """Non-COMMAND messages must be ignored even when to_agent matches."""
        from enhanced_agent_bus.agents.chatops_executor import (
            handle_chatops_command,
        )

        msg = _make_msg(message_type=MessageType.QUERY)
        result = await handle_chatops_command(msg)
        assert result is None

    async def test_wrong_to_agent_and_wrong_type_returns_none(self) -> None:
        """Both guards failing still produces None."""
        from enhanced_agent_bus.agents.chatops_executor import (
            handle_chatops_command,
        )

        msg = _make_msg(to_agent="other", message_type=MessageType.EVENT)
        result = await handle_chatops_command(msg)
        assert result is None

    async def test_event_type_returns_none(self) -> None:
        """MessageType.EVENT routed to chatops_executor must be ignored."""
        from enhanced_agent_bus.agents.chatops_executor import (
            handle_chatops_command,
        )

        msg = _make_msg(message_type=MessageType.EVENT)
        result = await handle_chatops_command(msg)
        assert result is None

    async def test_notification_type_returns_none(self) -> None:
        """MessageType.NOTIFICATION must be ignored."""
        from enhanced_agent_bus.agents.chatops_executor import (
            handle_chatops_command,
        )

        msg = _make_msg(message_type=MessageType.NOTIFICATION)
        result = await handle_chatops_command(msg)
        assert result is None


# ---------------------------------------------------------------------------
# Content type guard tests
# ---------------------------------------------------------------------------


class TestContentTypeGuard:
    """Tests for the non-dict content guard."""

    async def test_string_content_returns_none(self) -> None:
        from enhanced_agent_bus.agents.chatops_executor import (
            handle_chatops_command,
        )

        msg = _make_msg(content="not a dict")
        result = await handle_chatops_command(msg)
        assert result is None

    async def test_list_content_returns_none(self) -> None:
        from enhanced_agent_bus.agents.chatops_executor import (
            handle_chatops_command,
        )

        msg = _make_msg(content=["/acgs-build-fix"])
        result = await handle_chatops_command(msg)
        assert result is None

    async def test_none_content_returns_none(self) -> None:
        from enhanced_agent_bus.agents.chatops_executor import (
            handle_chatops_command,
        )

        msg = _make_msg(content=None)
        # AgentMessage.content defaults to {}, so override the field after creation
        msg.content = None  # type: ignore[assignment]
        result = await handle_chatops_command(msg)
        assert result is None

    async def test_integer_content_returns_none(self) -> None:
        from enhanced_agent_bus.agents.chatops_executor import (
            handle_chatops_command,
        )

        msg = _make_msg(content=123)
        result = await handle_chatops_command(msg)
        assert result is None

    async def test_empty_dict_content_falls_through(self) -> None:
        """An empty dict is valid content (no command_body → unrecognized branch)."""
        from enhanced_agent_bus.agents.chatops_executor import (
            handle_chatops_command,
        )

        msg = _make_msg(content={})
        result = await handle_chatops_command(msg)
        # empty command_body → unrecognized → returns msg
        assert result is msg


# ---------------------------------------------------------------------------
# /acgs-build-fix branch
# ---------------------------------------------------------------------------


class TestBuildFixCommand:
    """Tests for the /acgs-build-fix dispatch branch."""

    async def test_build_fix_returns_original_message(self) -> None:
        """Build-fix routes to build_fix_swarm; returns a new routed AgentMessage."""
        from enhanced_agent_bus.agents.chatops_executor import (
            handle_chatops_command,
        )

        msg = _make_msg(content={"command_body": "/acgs-build-fix", "author": "dev"})
        result = await handle_chatops_command(msg)
        assert result is not None
        assert result.to_agent == "build_fix_swarm"
        assert result.content["action"] == "execute_build_fix"

    async def test_build_fix_with_args_returns_original_message(self) -> None:
        """Verify /acgs-build-fix with extra args still routes correctly."""
        from enhanced_agent_bus.agents.chatops_executor import (
            handle_chatops_command,
        )

        msg = _make_msg(
            content={
                "command_body": "/acgs-build-fix --verbose",
                "author": "ci-bot",
                "issue_number": 99,
            }
        )
        result = await handle_chatops_command(msg)
        assert result is not None
        assert result.to_agent == "build_fix_swarm"
        assert result.content["issue_number"] == 99

    async def test_build_fix_logs_dispatch(self) -> None:
        """Logger.info must be called when dispatching to build-fix swarm."""
        from enhanced_agent_bus.agents import chatops_executor

        msg = _make_msg(content={"command_body": "/acgs-build-fix"})
        with patch.object(chatops_executor.logger, "info") as mock_info:
            await chatops_executor.handle_chatops_command(msg)
        # at minimum: "Executing ChatOps command" and "Dispatching to Build Fix agent swarm"
        assert mock_info.call_count >= 2

    async def test_build_fix_command_body_prefix_match(self) -> None:
        """/acgs-build-fix must match even when extra text follows."""
        from enhanced_agent_bus.agents.chatops_executor import (
            handle_chatops_command,
        )

        msg = _make_msg(content={"command_body": "/acgs-build-fix #42 please fix"})
        result = await handle_chatops_command(msg)
        assert result is not None
        assert result.to_agent == "build_fix_swarm"

    async def test_build_fix_missing_author_uses_default(self) -> None:
        """author defaults to 'unknown' when absent; function routes to build_fix_swarm."""
        from enhanced_agent_bus.agents.chatops_executor import (
            handle_chatops_command,
        )

        msg = _make_msg(content={"command_body": "/acgs-build-fix"})
        result = await handle_chatops_command(msg)
        assert result is not None
        assert result.content["author"] == "unknown"


# ---------------------------------------------------------------------------
# /acgs-review branch — success path
# ---------------------------------------------------------------------------


class TestReviewCommandSuccess:
    """Tests for the /acgs-review branch when MCP calls succeed."""

    def _mock_mcp_client(self, context_result: MagicMock | None = None) -> MagicMock:
        if context_result is None:
            context_result = _make_context_result(success=True)
        client = MagicMock()
        client.connect = AsyncMock()
        client.call_tool = AsyncMock(return_value=context_result)
        client.disconnect = AsyncMock()
        return client

    async def test_review_returns_task_request_message(self) -> None:
        """Success path must return a new TASK_REQUEST AgentMessage."""
        from enhanced_agent_bus.agents.chatops_executor import (
            handle_chatops_command,
        )

        mock_client = self._mock_mcp_client()
        mock_cls = MagicMock(return_value=mock_client)

        with patch.dict(
            sys.modules,
            {
                "src.core.integrations.nemo_agent_toolkit.mcp_bridge": MagicMock(
                    ACGS2MCPClient=mock_cls
                )
            },
        ):
            msg = _make_msg(
                content={"command_body": "/acgs-review", "author": "reviewer", "issue_number": 5}
            )
            result = await handle_chatops_command(msg)

        assert result is not None
        assert result.message_type == MessageType.TASK_REQUEST
        assert result.to_agent == "review_swarm"
        assert result.from_agent == "chatops_executor"

    async def test_review_content_has_action_field(self) -> None:
        """The review task content must contain 'action'."""
        from enhanced_agent_bus.agents.chatops_executor import (
            handle_chatops_command,
        )

        mock_client = self._mock_mcp_client()
        mock_cls = MagicMock(return_value=mock_client)

        with patch.dict(
            sys.modules,
            {
                "src.core.integrations.nemo_agent_toolkit.mcp_bridge": MagicMock(
                    ACGS2MCPClient=mock_cls
                )
            },
        ):
            msg = _make_msg(content={"command_body": "/acgs-review", "issue_number": 7})
            result = await handle_chatops_command(msg)

        assert result is not None
        assert result.content.get("action") == "execute_code_review"

    async def test_review_content_has_issue_number(self) -> None:
        """The review task must forward the issue_number."""
        from enhanced_agent_bus.agents.chatops_executor import (
            handle_chatops_command,
        )

        mock_client = self._mock_mcp_client()
        mock_cls = MagicMock(return_value=mock_client)

        with patch.dict(
            sys.modules,
            {
                "src.core.integrations.nemo_agent_toolkit.mcp_bridge": MagicMock(
                    ACGS2MCPClient=mock_cls
                )
            },
        ):
            msg = _make_msg(content={"command_body": "/acgs-review", "issue_number": 77})
            result = await handle_chatops_command(msg)

        assert result is not None
        assert result.content.get("issue_number") == 77

    async def test_review_content_includes_open_aware_context_on_success(self) -> None:
        """When context_result.success=True, open_aware_context must be populated."""
        from enhanced_agent_bus.agents.chatops_executor import (
            handle_chatops_command,
        )

        ctx_data = {"key": "value", "lines": 10}
        context_result = _make_context_result(success=True, data=ctx_data)
        mock_client = self._mock_mcp_client(context_result)
        mock_cls = MagicMock(return_value=mock_client)

        with patch.dict(
            sys.modules,
            {
                "src.core.integrations.nemo_agent_toolkit.mcp_bridge": MagicMock(
                    ACGS2MCPClient=mock_cls
                )
            },
        ):
            msg = _make_msg(content={"command_body": "/acgs-review", "issue_number": 3})
            result = await handle_chatops_command(msg)

        assert result is not None
        assert result.content.get("open_aware_context") == ctx_data

    async def test_review_content_open_aware_none_when_context_fails(self) -> None:
        """When context_result.success=False, open_aware_context must be None."""
        from enhanced_agent_bus.agents.chatops_executor import (
            handle_chatops_command,
        )

        context_result = _make_context_result(success=False, data=None)
        mock_client = self._mock_mcp_client(context_result)
        mock_cls = MagicMock(return_value=mock_client)

        with patch.dict(
            sys.modules,
            {
                "src.core.integrations.nemo_agent_toolkit.mcp_bridge": MagicMock(
                    ACGS2MCPClient=mock_cls
                )
            },
        ):
            msg = _make_msg(content={"command_body": "/acgs-review", "issue_number": 11})
            result = await handle_chatops_command(msg)

        assert result is not None
        assert result.content.get("open_aware_context") is None

    async def test_review_mcp_client_instantiated_with_correct_url(self) -> None:
        """ACGS2MCPClient must be called with the open-aware server URL."""
        from enhanced_agent_bus.agents.chatops_executor import (
            handle_chatops_command,
        )

        mock_client = self._mock_mcp_client()
        mock_cls = MagicMock(return_value=mock_client)

        with patch.dict(
            sys.modules,
            {
                "src.core.integrations.nemo_agent_toolkit.mcp_bridge": MagicMock(
                    ACGS2MCPClient=mock_cls
                )
            },
        ):
            msg = _make_msg(content={"command_body": "/acgs-review", "issue_number": 1})
            await handle_chatops_command(msg)

        mock_cls.assert_called_once_with(server_url="https://open-aware.qodo.ai/mcp")

    async def test_review_mcp_client_connect_called(self) -> None:
        """mcp_client.connect() must be awaited."""
        from enhanced_agent_bus.agents.chatops_executor import (
            handle_chatops_command,
        )

        mock_client = self._mock_mcp_client()
        mock_cls = MagicMock(return_value=mock_client)

        with patch.dict(
            sys.modules,
            {
                "src.core.integrations.nemo_agent_toolkit.mcp_bridge": MagicMock(
                    ACGS2MCPClient=mock_cls
                )
            },
        ):
            msg = _make_msg(content={"command_body": "/acgs-review", "issue_number": 2})
            await handle_chatops_command(msg)

        mock_client.connect.assert_awaited_once()

    async def test_review_mcp_client_disconnect_called(self) -> None:
        """mcp_client.disconnect() must be awaited after call_tool."""
        from enhanced_agent_bus.agents.chatops_executor import (
            handle_chatops_command,
        )

        mock_client = self._mock_mcp_client()
        mock_cls = MagicMock(return_value=mock_client)

        with patch.dict(
            sys.modules,
            {
                "src.core.integrations.nemo_agent_toolkit.mcp_bridge": MagicMock(
                    ACGS2MCPClient=mock_cls
                )
            },
        ):
            msg = _make_msg(content={"command_body": "/acgs-review", "issue_number": 2})
            await handle_chatops_command(msg)

        mock_client.disconnect.assert_awaited_once()

    async def test_review_call_tool_invoked_with_deep_research(self) -> None:
        """mcp_client.call_tool must be called with name='deep_research'."""
        from enhanced_agent_bus.agents.chatops_executor import (
            handle_chatops_command,
        )

        mock_client = self._mock_mcp_client()
        mock_cls = MagicMock(return_value=mock_client)

        with patch.dict(
            sys.modules,
            {
                "src.core.integrations.nemo_agent_toolkit.mcp_bridge": MagicMock(
                    ACGS2MCPClient=mock_cls
                )
            },
        ):
            msg = _make_msg(content={"command_body": "/acgs-review", "issue_number": 4})
            await handle_chatops_command(msg)

        call_kwargs = mock_client.call_tool.call_args
        assert call_kwargs.kwargs.get("name") == "deep_research" or (
            call_kwargs.args and call_kwargs.args[0] == "deep_research"
        )

    async def test_review_with_args_suffix_still_dispatches(self) -> None:
        """/acgs-review with trailing args must still enter the review branch."""
        from enhanced_agent_bus.agents.chatops_executor import (
            handle_chatops_command,
        )

        mock_client = self._mock_mcp_client()
        mock_cls = MagicMock(return_value=mock_client)

        with patch.dict(
            sys.modules,
            {
                "src.core.integrations.nemo_agent_toolkit.mcp_bridge": MagicMock(
                    ACGS2MCPClient=mock_cls
                )
            },
        ):
            msg = _make_msg(content={"command_body": "/acgs-review --deep", "issue_number": 6})
            result = await handle_chatops_command(msg)

        assert result is not None
        assert result.message_type == MessageType.TASK_REQUEST


# ---------------------------------------------------------------------------
# /acgs-review branch — exception path
# ---------------------------------------------------------------------------


class TestReviewCommandException:
    """Tests for the /acgs-review branch when exceptions are raised."""

    async def test_connect_raises_returns_none(self) -> None:
        """If mcp_client.connect() raises, the function must return None."""
        from enhanced_agent_bus.agents.chatops_executor import (
            handle_chatops_command,
        )

        mock_client = MagicMock()
        mock_client.connect = AsyncMock(side_effect=ConnectionError("network failure"))
        mock_client.call_tool = AsyncMock()
        mock_client.disconnect = AsyncMock()
        mock_cls = MagicMock(return_value=mock_client)

        with patch.dict(
            sys.modules,
            {
                "src.core.integrations.nemo_agent_toolkit.mcp_bridge": MagicMock(
                    ACGS2MCPClient=mock_cls
                )
            },
        ):
            msg = _make_msg(content={"command_body": "/acgs-review", "issue_number": 10})
            result = await handle_chatops_command(msg)

        assert result is None

    async def test_call_tool_raises_returns_none(self) -> None:
        """If mcp_client.call_tool() raises, the function must return None."""
        from enhanced_agent_bus.agents.chatops_executor import (
            handle_chatops_command,
        )

        mock_client = MagicMock()
        mock_client.connect = AsyncMock()
        mock_client.call_tool = AsyncMock(side_effect=RuntimeError("tool error"))
        mock_client.disconnect = AsyncMock()
        mock_cls = MagicMock(return_value=mock_client)

        with patch.dict(
            sys.modules,
            {
                "src.core.integrations.nemo_agent_toolkit.mcp_bridge": MagicMock(
                    ACGS2MCPClient=mock_cls
                )
            },
        ):
            msg = _make_msg(content={"command_body": "/acgs-review", "issue_number": 12})
            result = await handle_chatops_command(msg)

        assert result is None

    async def test_disconnect_raises_returns_none(self) -> None:
        """If mcp_client.disconnect() raises, the function must return None."""
        from enhanced_agent_bus.agents.chatops_executor import (
            handle_chatops_command,
        )

        context_result = _make_context_result(success=True)
        mock_client = MagicMock()
        mock_client.connect = AsyncMock()
        mock_client.call_tool = AsyncMock(return_value=context_result)
        mock_client.disconnect = AsyncMock(side_effect=OSError("disconnect error"))
        mock_cls = MagicMock(return_value=mock_client)

        with patch.dict(
            sys.modules,
            {
                "src.core.integrations.nemo_agent_toolkit.mcp_bridge": MagicMock(
                    ACGS2MCPClient=mock_cls
                )
            },
        ):
            msg = _make_msg(content={"command_body": "/acgs-review", "issue_number": 13})
            result = await handle_chatops_command(msg)

        assert result is None

    async def test_import_error_returns_none(self) -> None:
        """If importing ACGS2MCPClient raises ImportError, the function must return None."""
        from enhanced_agent_bus.agents import chatops_executor

        # Remove the cached module to force re-import inside the function.
        sys.modules.pop("src.core.integrations.nemo_agent_toolkit.mcp_bridge", None)

        # Make the import raise
        with patch.dict(
            sys.modules,
            {"src.core.integrations.nemo_agent_toolkit.mcp_bridge": None},  # type: ignore[dict-item]
        ):
            msg = _make_msg(content={"command_body": "/acgs-review", "issue_number": 14})
            result = await chatops_executor.handle_chatops_command(msg)

        assert result is None

    async def test_exception_logs_error(self) -> None:
        """Logger.error must be called when an exception occurs in review branch."""
        from enhanced_agent_bus.agents import chatops_executor

        mock_client = MagicMock()
        mock_client.connect = AsyncMock(side_effect=Exception("boom"))
        mock_cls = MagicMock(return_value=mock_client)

        with patch.dict(
            sys.modules,
            {
                "src.core.integrations.nemo_agent_toolkit.mcp_bridge": MagicMock(
                    ACGS2MCPClient=mock_cls
                )
            },
        ):
            with patch.object(chatops_executor.logger, "error") as mock_error:
                msg = _make_msg(content={"command_body": "/acgs-review", "issue_number": 15})
                await chatops_executor.handle_chatops_command(msg)

        mock_error.assert_called_once()
        call_args = mock_error.call_args
        assert "Failed to retrieve open-aware context" in call_args[0][0]

    async def test_exception_error_extra_contains_error_key(self) -> None:
        """The error log extra dict must contain the 'error' key."""
        from enhanced_agent_bus.agents import chatops_executor

        error_msg = "something went wrong"
        mock_client = MagicMock()
        mock_client.connect = AsyncMock(side_effect=ValueError(error_msg))
        mock_cls = MagicMock(return_value=mock_client)

        with patch.dict(
            sys.modules,
            {
                "src.core.integrations.nemo_agent_toolkit.mcp_bridge": MagicMock(
                    ACGS2MCPClient=mock_cls
                )
            },
        ):
            with patch.object(chatops_executor.logger, "error") as mock_error:
                msg = _make_msg(content={"command_body": "/acgs-review", "issue_number": 16})
                await chatops_executor.handle_chatops_command(msg)

        extra = mock_error.call_args.kwargs.get("extra", {})
        assert "error" in extra
        assert error_msg in extra["error"]


# ---------------------------------------------------------------------------
# Unrecognized command branch
# ---------------------------------------------------------------------------


class TestUnrecognizedCommand:
    """Tests for the else/warning branch when command is not recognized."""

    async def test_unrecognized_command_returns_original_message(self) -> None:
        """Unrecognized commands must return the original message unchanged."""
        from enhanced_agent_bus.agents.chatops_executor import (
            handle_chatops_command,
        )

        msg = _make_msg(content={"command_body": "/unknown-command"})
        result = await handle_chatops_command(msg)
        assert result is msg

    async def test_empty_command_body_returns_original_message(self) -> None:
        """An empty command_body string is not recognized; returns original message."""
        from enhanced_agent_bus.agents.chatops_executor import (
            handle_chatops_command,
        )

        msg = _make_msg(content={"command_body": ""})
        result = await handle_chatops_command(msg)
        assert result is msg

    async def test_unrecognized_command_logs_warning(self) -> None:
        """A warning must be logged for unrecognized commands."""
        from enhanced_agent_bus.agents import chatops_executor

        msg = _make_msg(content={"command_body": "/something-else"})
        with patch.object(chatops_executor.logger, "warning") as mock_warn:
            await chatops_executor.handle_chatops_command(msg)

        mock_warn.assert_called_once()
        warning_msg = mock_warn.call_args[0][0]
        assert "/something-else" in warning_msg

    async def test_partial_command_not_matching_build_fix(self) -> None:
        """/acgs-build is not a recognized command prefix."""
        from enhanced_agent_bus.agents.chatops_executor import (
            handle_chatops_command,
        )

        msg = _make_msg(content={"command_body": "/acgs-build"})
        result = await handle_chatops_command(msg)
        assert result is msg

    async def test_partial_command_not_matching_review(self) -> None:
        """/acgs-rev is not a recognized command prefix."""
        from enhanced_agent_bus.agents.chatops_executor import (
            handle_chatops_command,
        )

        msg = _make_msg(content={"command_body": "/acgs-rev"})
        result = await handle_chatops_command(msg)
        assert result is msg

    async def test_plain_text_command_body_returns_original(self) -> None:
        """Plain text without a slash prefix is unrecognized; returns original message."""
        from enhanced_agent_bus.agents.chatops_executor import (
            handle_chatops_command,
        )

        msg = _make_msg(content={"command_body": "just some text"})
        result = await handle_chatops_command(msg)
        assert result is msg


# ---------------------------------------------------------------------------
# Metadata extraction tests
# ---------------------------------------------------------------------------


class TestMetadataExtraction:
    """Tests verifying that command_data fields are extracted correctly."""

    async def test_author_is_extracted_from_content(self) -> None:
        """The author field from content must be forwarded in the routed message."""
        from enhanced_agent_bus.agents import chatops_executor

        msg = _make_msg(
            content={"command_body": "/acgs-build-fix", "author": "alice", "issue_number": 100}
        )
        result = await chatops_executor.handle_chatops_command(msg)
        assert result is not None
        assert result.content["author"] == "alice"

    async def test_issue_number_none_when_absent(self) -> None:
        """Absence of issue_number is handled gracefully."""
        from enhanced_agent_bus.agents.chatops_executor import (
            handle_chatops_command,
        )

        msg = _make_msg(content={"command_body": "/acgs-build-fix"})
        result = await handle_chatops_command(msg)
        assert result is not None
        assert result.content["issue_number"] is None

    async def test_extra_fields_in_content_are_ignored(self) -> None:
        """Extra unexpected fields in content do not break the function."""
        from enhanced_agent_bus.agents.chatops_executor import (
            handle_chatops_command,
        )

        msg = _make_msg(
            content={
                "command_body": "/acgs-build-fix",
                "unexpected_key": "unexpected_value",
                "another": 123,
            }
        )
        result = await handle_chatops_command(msg)
        assert result is not None
        assert result.to_agent == "build_fix_swarm"

    async def test_info_log_called_on_valid_command(self) -> None:
        """Logger.info must be called with 'Executing ChatOps command'."""
        from enhanced_agent_bus.agents import chatops_executor

        msg = _make_msg(
            content={"command_body": "/acgs-build-fix", "author": "ci", "issue_number": 55}
        )
        with patch.object(chatops_executor.logger, "info") as mock_info:
            await chatops_executor.handle_chatops_command(msg)

        first_call_msg = mock_info.call_args_list[0][0][0]
        assert "Executing ChatOps command" in first_call_msg


# ---------------------------------------------------------------------------
# Return value identity tests
# ---------------------------------------------------------------------------


class TestReturnValueIdentity:
    """Tests that verify the exact return value identity in each branch."""

    async def test_build_fix_returns_same_object(self) -> None:
        from enhanced_agent_bus.agents.chatops_executor import (
            handle_chatops_command,
        )

        msg = _make_msg(content={"command_body": "/acgs-build-fix"})
        result = await handle_chatops_command(msg)
        assert result is not None
        assert result is not msg  # new routed message, not the original
        assert result.to_agent == "build_fix_swarm"

    async def test_unrecognized_returns_same_object(self) -> None:
        from enhanced_agent_bus.agents.chatops_executor import (
            handle_chatops_command,
        )

        msg = _make_msg(content={"command_body": "/noop"})
        result = await handle_chatops_command(msg)
        assert result is msg

    async def test_review_success_returns_different_object(self) -> None:
        """Review success path creates a *new* AgentMessage, not the input."""
        from enhanced_agent_bus.agents.chatops_executor import (
            handle_chatops_command,
        )

        context_result = _make_context_result(success=True)
        mock_client = MagicMock()
        mock_client.connect = AsyncMock()
        mock_client.call_tool = AsyncMock(return_value=context_result)
        mock_client.disconnect = AsyncMock()
        mock_cls = MagicMock(return_value=mock_client)

        with patch.dict(
            sys.modules,
            {
                "src.core.integrations.nemo_agent_toolkit.mcp_bridge": MagicMock(
                    ACGS2MCPClient=mock_cls
                )
            },
        ):
            msg = _make_msg(content={"command_body": "/acgs-review", "issue_number": 50})
            result = await handle_chatops_command(msg)

        assert result is not msg
        assert isinstance(result, AgentMessage)
