# Constitutional Hash: 608508a9bd224290
# Sprint 56 — sdpc/pacar_manager.py coverage
"""
Comprehensive tests for sdpc/pacar_manager.py targeting ≥95% coverage.
"""

import pytest

pytest.importorskip("enhanced_agent_bus.sdpc")


import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.sdpc.conversation import (
    ConversationMessage,
    ConversationState,
    MessageRole,
)
from enhanced_agent_bus.sdpc.pacar_manager import (
    _PACAR_OPERATION_ERRORS,
    PACARManager,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(redis_url: str = "redis://localhost:6379") -> MagicMock:
    cfg = MagicMock()
    cfg.redis_url = redis_url
    return cfg


def _make_state(session_id: str = "sess-1") -> ConversationState:
    return ConversationState(session_id=session_id)


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


class TestPACARManagerInit:
    def test_init_with_explicit_config(self):
        cfg = _make_config()
        mgr = PACARManager(config=cfg)
        assert mgr.config is cfg
        assert mgr._redis is None
        assert mgr._local_history == {}

    def test_init_without_config_calls_from_environment(self):
        mock_cfg = _make_config()
        with patch("enhanced_agent_bus.sdpc.pacar_manager.BusConfiguration") as mock_cls:
            mock_cls.from_environment.return_value = mock_cfg
            mgr = PACARManager()
        mock_cls.from_environment.assert_called_once()
        assert mgr.config is mock_cfg


# ---------------------------------------------------------------------------
# _get_redis
# ---------------------------------------------------------------------------


class TestGetRedis:
    async def test_creates_redis_connection_on_first_call(self):
        cfg = _make_config("redis://localhost:6379")
        mgr = PACARManager(config=cfg)

        mock_redis = AsyncMock()
        with patch(
            "enhanced_agent_bus.sdpc.pacar_manager.redis.from_url",
            return_value=mock_redis,
        ) as mock_from_url:
            result = await mgr._get_redis()

        mock_from_url.assert_called_once_with("redis://localhost:6379", decode_responses=True)
        assert result is mock_redis
        assert mgr._redis is mock_redis

    async def test_returns_cached_connection_on_second_call(self):
        cfg = _make_config()
        mgr = PACARManager(config=cfg)

        mock_redis = AsyncMock()
        with patch(
            "enhanced_agent_bus.sdpc.pacar_manager.redis.from_url",
            return_value=mock_redis,
        ) as mock_from_url:
            r1 = await mgr._get_redis()
            r2 = await mgr._get_redis()

        # from_url called exactly once — second call reuses cached instance
        mock_from_url.assert_called_once()
        assert r1 is r2

    async def test_pre_assigned_redis_is_returned_directly(self):
        cfg = _make_config()
        mgr = PACARManager(config=cfg)
        existing = AsyncMock()
        mgr._redis = existing

        with patch(
            "enhanced_agent_bus.sdpc.pacar_manager.redis.from_url"
        ) as mock_from_url:
            result = await mgr._get_redis()

        mock_from_url.assert_not_called()
        assert result is existing


# ---------------------------------------------------------------------------
# get_state
# ---------------------------------------------------------------------------


class TestGetState:
    async def test_returns_from_local_cache_when_present(self):
        mgr = PACARManager(config=_make_config())
        state = _make_state("cached-sess")
        mgr._local_history["cached-sess"] = state

        result = await mgr.get_state("cached-sess")
        assert result is state

    async def test_fetches_from_redis_when_not_in_local_cache(self):
        mgr = PACARManager(config=_make_config())

        redis_state = ConversationState(session_id="redis-sess")
        json_data = redis_state.model_dump_json()

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json_data)

        with patch.object(mgr, "_get_redis", return_value=mock_redis):
            result = await mgr.get_state("redis-sess")

        assert result.session_id == "redis-sess"
        assert "redis-sess" in mgr._local_history

    async def test_caches_redis_result_in_local_history(self):
        mgr = PACARManager(config=_make_config())

        redis_state = ConversationState(session_id="cache-test")
        json_data = redis_state.model_dump_json()

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json_data)

        with patch.object(mgr, "_get_redis", return_value=mock_redis):
            await mgr.get_state("cache-test")

        assert mgr._local_history["cache-test"].session_id == "cache-test"

    async def test_creates_new_state_when_redis_returns_none(self):
        mgr = PACARManager(config=_make_config())

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)

        with patch.object(mgr, "_get_redis", return_value=mock_redis):
            result = await mgr.get_state("new-sess")

        assert result.session_id == "new-sess"
        assert result.messages == []
        assert "new-sess" in mgr._local_history

    async def test_creates_new_state_when_redis_returns_empty_string(self):
        mgr = PACARManager(config=_make_config())

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value="")

        with patch.object(mgr, "_get_redis", return_value=mock_redis):
            result = await mgr.get_state("empty-sess")

        assert result.session_id == "empty-sess"

    async def test_handles_redis_error_and_creates_new_state(self):
        """All errors in _PACAR_OPERATION_ERRORS must be caught."""
        for exc_cls in _PACAR_OPERATION_ERRORS:
            mgr = PACARManager(config=_make_config())
            mock_redis = AsyncMock()
            mock_redis.get = AsyncMock(side_effect=exc_cls("boom"))

            with patch.object(mgr, "_get_redis", return_value=mock_redis):
                result = await mgr.get_state(f"err-sess-{exc_cls.__name__}")

            assert result.session_id == f"err-sess-{exc_cls.__name__}"

    async def test_logs_error_on_redis_failure(self):
        mgr = PACARManager(config=_make_config())
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(side_effect=RuntimeError("conn refused"))

        with patch.object(mgr, "_get_redis", return_value=mock_redis):
            with patch("enhanced_agent_bus.sdpc.pacar_manager.logger") as mock_log:
                await mgr.get_state("log-sess")

        mock_log.error.assert_called_once()
        call_args = mock_log.error.call_args[0][0]
        assert "log-sess" in call_args

    async def test_get_redis_error_also_caught(self):
        """If _get_redis itself raises, the exception is caught and new state returned."""
        mgr = PACARManager(config=_make_config())

        async def _failing_get_redis():
            raise ConnectionError("no redis")

        with patch.object(mgr, "_get_redis", side_effect=ConnectionError("no redis")):
            result = await mgr.get_state("conn-err-sess")

        assert result.session_id == "conn-err-sess"


# ---------------------------------------------------------------------------
# save_state
# ---------------------------------------------------------------------------


class TestSaveState:
    async def test_saves_to_local_history(self):
        mgr = PACARManager(config=_make_config())
        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock()

        with patch.object(mgr, "_get_redis", return_value=mock_redis):
            state = _make_state("save-sess")
            await mgr.save_state(state)

        assert mgr._local_history["save-sess"] is state

    async def test_calls_redis_setex_with_correct_args(self):
        mgr = PACARManager(config=_make_config())
        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock()

        state = _make_state("setex-sess")
        with patch.object(mgr, "_get_redis", return_value=mock_redis):
            await mgr.save_state(state)

        mock_redis.setex.assert_called_once_with(
            "pacar:session:setex-sess",
            3600,
            state.model_dump_json(),
        )

    async def test_handles_redis_error_on_save(self):
        for exc_cls in _PACAR_OPERATION_ERRORS:
            mgr = PACARManager(config=_make_config())
            mock_redis = AsyncMock()
            mock_redis.setex = AsyncMock(side_effect=exc_cls("write fail"))

            state = _make_state(f"save-err-{exc_cls.__name__}")
            with patch.object(mgr, "_get_redis", return_value=mock_redis):
                # Should not raise
                await mgr.save_state(state)

            # Local history still updated despite Redis error
            assert f"save-err-{exc_cls.__name__}" in mgr._local_history

    async def test_logs_error_on_save_failure(self):
        mgr = PACARManager(config=_make_config())
        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock(side_effect=OSError("disk full"))

        state = _make_state("log-save-sess")
        with patch.object(mgr, "_get_redis", return_value=mock_redis):
            with patch("enhanced_agent_bus.sdpc.pacar_manager.logger") as mock_log:
                await mgr.save_state(state)

        mock_log.error.assert_called_once()
        call_args = mock_log.error.call_args[0][0]
        assert "log-save-sess" in call_args


# ---------------------------------------------------------------------------
# add_message
# ---------------------------------------------------------------------------


class TestAddMessage:
    async def test_adds_user_message_to_new_session(self):
        mgr = PACARManager(config=_make_config())
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.setex = AsyncMock()

        with patch.object(mgr, "_get_redis", return_value=mock_redis):
            state = await mgr.add_message(
                session_id="msg-sess",
                role=MessageRole.USER,
                content="Hello",
            )

        assert len(state.messages) == 1
        assert state.messages[0].role == MessageRole.USER
        assert state.messages[0].content == "Hello"

    async def test_adds_assistant_message(self):
        mgr = PACARManager(config=_make_config())
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.setex = AsyncMock()

        with patch.object(mgr, "_get_redis", return_value=mock_redis):
            state = await mgr.add_message(
                session_id="asst-sess",
                role=MessageRole.ASSISTANT,
                content="Hi there",
            )

        assert state.messages[0].role == MessageRole.ASSISTANT

    async def test_adds_system_message(self):
        mgr = PACARManager(config=_make_config())
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.setex = AsyncMock()

        with patch.object(mgr, "_get_redis", return_value=mock_redis):
            state = await mgr.add_message(
                session_id="sys-sess",
                role=MessageRole.SYSTEM,
                content="You are helpful",
            )

        assert state.messages[0].role == MessageRole.SYSTEM

    async def test_metadata_defaults_to_empty_dict_when_none(self):
        mgr = PACARManager(config=_make_config())
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.setex = AsyncMock()

        with patch.object(mgr, "_get_redis", return_value=mock_redis):
            state = await mgr.add_message(
                session_id="meta-sess",
                role=MessageRole.USER,
                content="test",
                metadata=None,
            )

        assert state.messages[0].metadata == {}

    async def test_metadata_passed_through_when_provided(self):
        mgr = PACARManager(config=_make_config())
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.setex = AsyncMock()

        meta = {"key": "value", "num": 42}
        with patch.object(mgr, "_get_redis", return_value=mock_redis):
            state = await mgr.add_message(
                session_id="meta2-sess",
                role=MessageRole.USER,
                content="test",
                metadata=meta,
            )

        assert state.messages[0].metadata == meta

    async def test_appends_to_existing_session(self):
        mgr = PACARManager(config=_make_config())

        # Pre-seed local history with existing state
        existing = ConversationState(session_id="multi-sess")
        existing.messages.append(ConversationMessage(role=MessageRole.USER, content="First"))
        mgr._local_history["multi-sess"] = existing

        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock()

        with patch.object(mgr, "_get_redis", return_value=mock_redis):
            state = await mgr.add_message(
                session_id="multi-sess",
                role=MessageRole.ASSISTANT,
                content="Second",
            )

        assert len(state.messages) == 2
        assert state.messages[1].content == "Second"

    async def test_returns_updated_conversation_state(self):
        mgr = PACARManager(config=_make_config())
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.setex = AsyncMock()

        with patch.object(mgr, "_get_redis", return_value=mock_redis):
            result = await mgr.add_message(
                session_id="ret-sess",
                role=MessageRole.USER,
                content="Check return",
            )

        assert isinstance(result, ConversationState)
        assert result.session_id == "ret-sess"

    async def test_save_state_called_after_adding_message(self):
        mgr = PACARManager(config=_make_config())

        saved_states = []

        async def _mock_save(state):
            saved_states.append(state)

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.setex = AsyncMock()

        with patch.object(mgr, "_get_redis", return_value=mock_redis):
            with patch.object(mgr, "save_state", side_effect=_mock_save):
                await mgr.add_message(
                    session_id="save-check-sess",
                    role=MessageRole.USER,
                    content="save check",
                )

        assert len(saved_states) == 1


# ---------------------------------------------------------------------------
# clear_session
# ---------------------------------------------------------------------------


class TestClearSession:
    async def test_removes_session_from_local_history(self):
        mgr = PACARManager(config=_make_config())
        mgr._local_history["del-sess"] = _make_state("del-sess")

        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock()

        with patch.object(mgr, "_get_redis", return_value=mock_redis):
            await mgr.clear_session("del-sess")

        assert "del-sess" not in mgr._local_history

    async def test_calls_redis_delete_with_correct_key(self):
        mgr = PACARManager(config=_make_config())
        mgr._local_history["rdel-sess"] = _make_state("rdel-sess")

        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock()

        with patch.object(mgr, "_get_redis", return_value=mock_redis):
            await mgr.clear_session("rdel-sess")

        mock_redis.delete.assert_called_once_with("pacar:session:rdel-sess")

    async def test_clears_session_not_in_local_history(self):
        """Session absent from local cache — no KeyError, Redis delete still called."""
        mgr = PACARManager(config=_make_config())

        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock()

        with patch.object(mgr, "_get_redis", return_value=mock_redis):
            await mgr.clear_session("absent-sess")

        mock_redis.delete.assert_called_once_with("pacar:session:absent-sess")

    async def test_handles_redis_error_on_clear(self):
        for exc_cls in _PACAR_OPERATION_ERRORS:
            mgr = PACARManager(config=_make_config())
            sess_id = f"clear-err-{exc_cls.__name__}"
            mgr._local_history[sess_id] = _make_state(sess_id)

            mock_redis = AsyncMock()
            mock_redis.delete = AsyncMock(side_effect=exc_cls("del fail"))

            with patch.object(mgr, "_get_redis", return_value=mock_redis):
                # Should not raise
                await mgr.clear_session(sess_id)

            # Local history still cleaned up
            assert sess_id not in mgr._local_history

    async def test_logs_error_on_clear_failure(self):
        mgr = PACARManager(config=_make_config())
        sess_id = "log-clear-sess"
        mgr._local_history[sess_id] = _make_state(sess_id)

        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock(side_effect=TimeoutError("timeout"))

        with patch.object(mgr, "_get_redis", return_value=mock_redis):
            with patch("enhanced_agent_bus.sdpc.pacar_manager.logger") as mock_log:
                await mgr.clear_session(sess_id)

        mock_log.error.assert_called_once()
        call_args = mock_log.error.call_args[0][0]
        assert sess_id in call_args


# ---------------------------------------------------------------------------
# _PACAR_OPERATION_ERRORS tuple
# ---------------------------------------------------------------------------


class TestPacarOperationErrors:
    def test_contains_all_expected_error_types(self):
        expected = (
            RuntimeError,
            ValueError,
            TypeError,
            AttributeError,
            LookupError,
            OSError,
            TimeoutError,
            ConnectionError,
        )
        assert _PACAR_OPERATION_ERRORS == expected

    def test_is_a_tuple(self):
        assert isinstance(_PACAR_OPERATION_ERRORS, tuple)


# ---------------------------------------------------------------------------
# Integration-style: round-trip via Redis JSON
# ---------------------------------------------------------------------------


class TestRoundTrip:
    async def test_state_roundtrip_through_redis(self):
        """Simulate get_state reading back what save_state stored."""
        mgr = PACARManager(config=_make_config())

        session_id = "roundtrip-sess"
        state = ConversationState(session_id=session_id)
        state.messages.append(
            ConversationMessage(role=MessageRole.USER, content="round-trip message")
        )

        stored_json: list[str] = []

        async def _setex(key, ttl, data):
            stored_json.append(data)

        async def _get(key):
            return stored_json[0] if stored_json else None

        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock(side_effect=_setex)
        mock_redis.get = AsyncMock(side_effect=_get)

        with patch.object(mgr, "_get_redis", return_value=mock_redis):
            await mgr.save_state(state)

            # Remove from local cache to force Redis path
            del mgr._local_history[session_id]

            retrieved = await mgr.get_state(session_id)

        assert retrieved.session_id == session_id
        assert len(retrieved.messages) == 1
        assert retrieved.messages[0].content == "round-trip message"

    async def test_add_multiple_messages_accumulate(self):
        mgr = PACARManager(config=_make_config())

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.setex = AsyncMock()

        with patch.object(mgr, "_get_redis", return_value=mock_redis):
            for i, role in enumerate([MessageRole.USER, MessageRole.ASSISTANT, MessageRole.USER]):
                state = await mgr.add_message(
                    session_id="accum-sess",
                    role=role,
                    content=f"Message {i}",
                )

        assert len(state.messages) == 3
        assert state.messages[0].role == MessageRole.USER
        assert state.messages[1].role == MessageRole.ASSISTANT
        assert state.messages[2].role == MessageRole.USER

    async def test_clear_then_get_creates_fresh_state(self):
        mgr = PACARManager(config=_make_config())
        session_id = "clear-fresh-sess"

        # Pre-populate
        mgr._local_history[session_id] = ConversationState(session_id=session_id)
        mgr._local_history[session_id].messages.append(
            ConversationMessage(role=MessageRole.USER, content="old")
        )

        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)

        with patch.object(mgr, "_get_redis", return_value=mock_redis):
            await mgr.clear_session(session_id)
            fresh = await mgr.get_state(session_id)

        assert fresh.messages == []
        assert fresh.session_id == session_id
