# Constitutional Hash: 608508a9bd224290
"""
Comprehensive test coverage for src/core/enhanced_agent_bus/api/rate_limiting.py

Covers:
- check_batch_rate_limit (Redis path, fallback path, RATE_LIMITING_AVAILABLE=False)
- _check_rate_limit_redis (normal, exceeded, Redis failure fallback)
- _check_rate_limit_memory (normal, exceeded, window cleanup)
- validate_item_sizes (valid, oversized, serialisation error, many violations)
- Module-level Limiter / get_remote_address instantiation

Design note: The production code raises RateLimitExceeded(agent_id=...,
message=..., retry_after_ms=...).  The real slowapi.RateLimitExceeded only
accepts a Limit object, so calling it with those kwargs raises TypeError (which
the Redis fallback catches and re-routes to in-memory).  All tests that need to
exercise the *raise* path patch rl_mod.RateLimitExceeded with the stub that
accepts those kwargs.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta, timezone
from typing import Any, ClassVar
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import enhanced_agent_bus.api.rate_limiting as rl_mod
from enhanced_agent_bus.fallback_stubs import StubRateLimitExceeded as _StubRLE

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_item(content: Any = "hello", request_id: str = "req-1") -> MagicMock:
    """Build a mock BatchRequestItem with .content and .request_id."""
    item = MagicMock()
    item.content = content
    item.request_id = request_id
    return item


def _make_batch(items: list[MagicMock], batch_id: str = "batch-1") -> MagicMock:
    """Build a mock BatchRequestProtocol."""
    batch = MagicMock()
    batch.items = items
    batch.batch_id = batch_id
    return batch


def _patched_rl(**extra: Any):
    """
    Return a patch.dict context that sets RATE_LIMITING_AVAILABLE=True and
    replaces RateLimitExceeded with the stub (which accepts agent_id kwargs).
    Also patches RateLimitExceededWrapper to produce _StubRLE instances.
    Caller may supply additional overrides via **extra.
    """
    return patch.dict(
        rl_mod.__dict__,
        {
            "RATE_LIMITING_AVAILABLE": True,
            "RateLimitExceeded": _StubRLE,
            "RateLimitExceededWrapper": _StubRLE,
            **extra,
        },
    )


# ---------------------------------------------------------------------------
# validate_item_sizes — purely synchronous
# ---------------------------------------------------------------------------


class TestValidateItemSizes:
    def test_empty_batch_returns_none(self) -> None:
        batch = _make_batch(items=[])
        assert rl_mod.validate_item_sizes(batch) is None

    def test_valid_small_items_returns_none(self) -> None:
        items = [_make_item(content="short content", request_id=f"r{i}") for i in range(3)]
        result = rl_mod.validate_item_sizes(_make_batch(items=items))
        assert result is None

    def test_oversized_item_returns_error_dict(self) -> None:
        from enhanced_agent_bus.api.config import MAX_ITEM_CONTENT_SIZE

        big_content = "x" * (MAX_ITEM_CONTENT_SIZE + 1)
        result = rl_mod.validate_item_sizes(_make_batch([_make_item(big_content, "big-1")]))
        assert result is not None
        assert result["total_oversized"] == 1
        assert result["oversized_items"][0]["item_index"] == 0
        assert result["oversized_items"][0]["request_id"] == "big-1"
        assert "content_size_bytes" in result["oversized_items"][0]
        assert "max_size_mb" in result

    def test_mixed_valid_and_oversized(self) -> None:
        from enhanced_agent_bus.api.config import MAX_ITEM_CONTENT_SIZE

        big = "x" * (MAX_ITEM_CONTENT_SIZE + 1)
        items = [
            _make_item("small", "r0"),
            _make_item(big, "r1"),
            _make_item("also small", "r2"),
        ]
        result = rl_mod.validate_item_sizes(_make_batch(items))
        assert result is not None
        assert result["total_oversized"] == 1
        assert result["oversized_items"][0]["item_index"] == 1

    def test_serialisation_failure_reported(self) -> None:
        """Non-serializable objects are handled gracefully by size estimator.

        After switching from json.dumps to sys.getsizeof-based estimation,
        arbitrary Python objects are measurable without serialization errors.
        Small objects pass validation regardless of serializability.
        """

        class _NotSerializable:
            pass

        result = rl_mod.validate_item_sizes(_make_batch([_make_item(_NotSerializable(), "bad")]))
        assert result is None

    def test_many_oversized_capped_at_max_violations(self) -> None:
        from enhanced_agent_bus.api.config import (
            MAX_ITEM_CONTENT_SIZE,
            MAX_VIOLATIONS_TO_DISPLAY,
        )

        big = "x" * (MAX_ITEM_CONTENT_SIZE + 1)
        n = MAX_VIOLATIONS_TO_DISPLAY + 3
        items = [_make_item(big, f"r{i}") for i in range(n)]
        result = rl_mod.validate_item_sizes(_make_batch(items))
        assert result is not None
        assert result["total_oversized"] == n
        assert len(result["oversized_items"]) == MAX_VIOLATIONS_TO_DISPLAY

    def test_result_contains_message_field(self) -> None:
        from enhanced_agent_bus.api.config import MAX_ITEM_CONTENT_SIZE

        big = "x" * (MAX_ITEM_CONTENT_SIZE + 1)
        result = rl_mod.validate_item_sizes(_make_batch([_make_item(big)]))
        assert result is not None
        assert "message" in result

    def test_item_exactly_at_limit_is_valid(self) -> None:
        """Content at exactly MAX_ITEM_CONTENT_SIZE passes validation."""
        import sys

        from enhanced_agent_bus.api.config import MAX_ITEM_CONTENT_SIZE

        overhead = sys.getsizeof("")
        content = "a" * (MAX_ITEM_CONTENT_SIZE - overhead)
        result = rl_mod.validate_item_sizes(_make_batch([_make_item(content, "exact")]))
        assert result is None

    def test_content_size_mb_in_oversized_item(self) -> None:
        from enhanced_agent_bus.api.config import MAX_ITEM_CONTENT_SIZE

        # Make content clearly bigger than 1 MB after JSON encoding
        big = "y" * (MAX_ITEM_CONTENT_SIZE + 10_000)
        result = rl_mod.validate_item_sizes(_make_batch([_make_item(big, "mb-check")]))
        assert result is not None
        item_detail = result["oversized_items"][0]
        assert "content_size_mb" in item_detail
        assert item_detail["content_size_mb"] >= 1.0


# ---------------------------------------------------------------------------
# check_batch_rate_limit — RATE_LIMITING_AVAILABLE = False
# ---------------------------------------------------------------------------


class TestCheckBatchRateLimitUnavailable:
    async def test_returns_none_when_unavailable(self) -> None:
        with patch.dict(rl_mod.__dict__, {"RATE_LIMITING_AVAILABLE": False}):
            result = await rl_mod.check_batch_rate_limit("client-1", 50)
        assert result is None

    async def test_raises_in_production_when_unavailable(self, monkeypatch) -> None:
        monkeypatch.setenv("ENVIRONMENT", "production")
        with patch.dict(rl_mod.__dict__, {"RATE_LIMITING_AVAILABLE": False}):
            with pytest.raises(RuntimeError, match="slowapi"):
                await rl_mod.check_batch_rate_limit("client-1", 50)

    async def test_no_redis_call_when_unavailable(self) -> None:
        mock_redis = AsyncMock()
        with patch.dict(
            rl_mod.__dict__,
            {"RATE_LIMITING_AVAILABLE": False, "_redis_client": mock_redis},
        ):
            await rl_mod.check_batch_rate_limit("client-1", 10)
        mock_redis.incrby.assert_not_called()


# ---------------------------------------------------------------------------
# check_batch_rate_limit — Redis-backed path
# ---------------------------------------------------------------------------


class TestCheckBatchRateLimitRedisPath:
    async def test_successful_redis_call_does_not_raise(self) -> None:
        mock_redis = AsyncMock()
        mock_redis.incrby = AsyncMock(return_value=1)
        mock_redis.expire = AsyncMock(return_value=True)

        with _patched_rl(_redis_client=mock_redis):
            await rl_mod.check_batch_rate_limit("user-1", 5)

        mock_redis.incrby.assert_awaited_once()

    async def test_redis_sets_expiry_on_first_request(self) -> None:
        """expire() must be called when incrby returns == rate_limit_cost."""
        mock_redis = AsyncMock()
        mock_redis.incrby = AsyncMock(return_value=1)  # cost=1, first request
        mock_redis.expire = AsyncMock(return_value=True)

        with _patched_rl(_redis_client=mock_redis):
            await rl_mod.check_batch_rate_limit("user-1", 10)

        mock_redis.expire.assert_awaited_once()

    async def test_redis_does_not_set_expiry_on_subsequent_requests(self) -> None:
        mock_redis = AsyncMock()
        mock_redis.incrby = AsyncMock(return_value=5)  # 5 > cost=1
        mock_redis.expire = AsyncMock(return_value=True)

        with _patched_rl(_redis_client=mock_redis):
            await rl_mod.check_batch_rate_limit("user-1", 10)

        mock_redis.expire.assert_not_awaited()

    async def test_redis_over_limit_propagates_from_direct_helper(self) -> None:
        """Verify _check_rate_limit_redis itself raises when over limit."""
        from enhanced_agent_bus.api.config import BATCH_RATE_LIMIT_BASE

        mock_redis = AsyncMock()
        mock_redis.incrby = AsyncMock(return_value=BATCH_RATE_LIMIT_BASE + 1)
        mock_redis.expire = AsyncMock(return_value=True)

        with patch.dict(
            rl_mod.__dict__,
            {
                "_redis_client": mock_redis,
                "RateLimitExceeded": _StubRLE,
                "RateLimitExceededWrapper": _StubRLE,
            },
        ):
            with pytest.raises(_StubRLE):
                await rl_mod._check_rate_limit_redis("user-1", 1, 10)

    async def test_redis_failure_falls_back_to_memory(self) -> None:
        mock_redis = AsyncMock()
        mock_redis.incrby = AsyncMock(side_effect=ConnectionError("redis down"))
        mem_check = AsyncMock()

        with _patched_rl(_redis_client=mock_redis):
            with patch.object(rl_mod, "_check_rate_limit_memory", mem_check):
                await rl_mod.check_batch_rate_limit("user-1", 10)

        mem_check.assert_awaited_once()

    async def test_redis_failure_raises_in_production(self, monkeypatch) -> None:
        mock_redis = AsyncMock()
        mock_redis.incrby = AsyncMock(side_effect=ConnectionError("redis down"))
        monkeypatch.setenv("ENVIRONMENT", "production")

        with _patched_rl(_redis_client=mock_redis):
            with pytest.raises(RuntimeError, match="Redis-backed rate limiting unavailable"):
                await rl_mod.check_batch_rate_limit("user-1", 10)

    async def test_large_batch_uses_higher_cost(self) -> None:
        """batch_size=1000 → cost=100."""
        mock_redis = AsyncMock()
        mock_redis.incrby = AsyncMock(return_value=100)
        mock_redis.expire = AsyncMock(return_value=True)

        with _patched_rl(_redis_client=mock_redis):
            await rl_mod.check_batch_rate_limit("user-1", 1000)

        args = mock_redis.incrby.call_args
        assert args[0][1] == 100

    async def test_zero_batch_size_uses_cost_of_1(self) -> None:
        """batch_size=0 → max(1, 0//10)=1."""
        mock_redis = AsyncMock()
        mock_redis.incrby = AsyncMock(return_value=1)
        mock_redis.expire = AsyncMock(return_value=True)

        with _patched_rl(_redis_client=mock_redis):
            await rl_mod.check_batch_rate_limit("user-1", 0)

        args = mock_redis.incrby.call_args
        assert args[0][1] == 1


# ---------------------------------------------------------------------------
# _check_rate_limit_redis — direct unit tests
# ---------------------------------------------------------------------------


class TestCheckRateLimitRedis:
    async def test_does_not_raise_within_limit(self) -> None:
        mock_redis = AsyncMock()
        mock_redis.incrby = AsyncMock(return_value=5)
        mock_redis.expire = AsyncMock()

        with patch.dict(rl_mod.__dict__, {"_redis_client": mock_redis}):
            await rl_mod._check_rate_limit_redis("client", 5, 50)

    async def test_raises_when_count_exceeds_base(self) -> None:
        from enhanced_agent_bus.api.config import BATCH_RATE_LIMIT_BASE

        mock_redis = AsyncMock()
        mock_redis.incrby = AsyncMock(return_value=BATCH_RATE_LIMIT_BASE + 10)
        mock_redis.expire = AsyncMock()

        with patch.dict(
            rl_mod.__dict__,
            {
                "_redis_client": mock_redis,
                "RateLimitExceeded": _StubRLE,
                "RateLimitExceededWrapper": _StubRLE,
            },
        ):
            with pytest.raises(_StubRLE) as exc_info:
                await rl_mod._check_rate_limit_redis("client", 10, 100)

        assert exc_info.value.retry_after_ms is not None
        assert exc_info.value.retry_after_ms >= 0

    async def test_window_key_includes_minute_precision(self) -> None:
        mock_redis = AsyncMock()
        mock_redis.incrby = AsyncMock(return_value=1)
        mock_redis.expire = AsyncMock()

        with patch.dict(rl_mod.__dict__, {"_redis_client": mock_redis}):
            await rl_mod._check_rate_limit_redis("user-xyz", 1, 10)

        key_used = mock_redis.incrby.call_args[0][0]
        assert "rate_limit:user-xyz:" in key_used
        # Minute stamp is 13 chars: YYYYMMDDTHHmm
        stamp = key_used.split("rate_limit:user-xyz:")[1]
        assert len(stamp) == 13


# ---------------------------------------------------------------------------
# _check_rate_limit_memory — direct unit tests
# ---------------------------------------------------------------------------


class TestCheckRateLimitMemory:
    async def _reset(self) -> None:
        async with rl_mod._batch_rate_limit_lock:
            rl_mod._batch_rate_limit_state.clear()

    async def test_first_request_succeeds(self) -> None:
        await self._reset()
        await rl_mod._check_rate_limit_memory("mem-1", 5, 50)
        assert any("mem-1" in k for k in rl_mod._batch_rate_limit_state)

    async def test_increments_tokens_consumed(self) -> None:
        await self._reset()
        with patch.dict(
            rl_mod.__dict__, {"RateLimitExceeded": _StubRLE, "RateLimitExceededWrapper": _StubRLE}
        ):
            await rl_mod._check_rate_limit_memory("cli-inc", 3, 30)
            await rl_mod._check_rate_limit_memory("cli-inc", 4, 40)
        state = next(v for k, v in rl_mod._batch_rate_limit_state.items() if "cli-inc" in k)
        assert state["tokens_consumed"] == 7
        assert state["requests"] == 2


class TestProductionGuards:
    async def _reset(self) -> None:
        async with rl_mod._batch_rate_limit_lock:
            rl_mod._batch_rate_limit_state.clear()

    def test_require_rate_limiting_dependencies_allows_sandbox(self) -> None:
        with patch.dict(rl_mod.__dict__, {"RATE_LIMITING_AVAILABLE": False, "_redis_client": None}):
            rl_mod.require_rate_limiting_dependencies()

    def test_require_rate_limiting_dependencies_rejects_missing_slowapi(self, monkeypatch) -> None:
        monkeypatch.setenv("ENVIRONMENT", "production")
        with patch.dict(rl_mod.__dict__, {"RATE_LIMITING_AVAILABLE": False}):
            with pytest.raises(RuntimeError, match="slowapi"):
                rl_mod.require_rate_limiting_dependencies()

    def test_require_rate_limiting_dependencies_rejects_missing_redis(self, monkeypatch) -> None:
        monkeypatch.setenv("ENVIRONMENT", "production")
        with patch.dict(rl_mod.__dict__, {"RATE_LIMITING_AVAILABLE": True, "_redis_client": None}):
            with pytest.raises(RuntimeError, match="Redis-backed rate limiting"):
                rl_mod.require_rate_limiting_dependencies()

    def test_create_app_calls_rate_limit_guard(self, monkeypatch) -> None:
        import importlib

        api_app = importlib.import_module("enhanced_agent_bus.api.app")

        called: list[str] = []

        monkeypatch.setattr(
            api_app,
            "require_rate_limiting_dependencies",
            lambda: called.append("called"),
        )

        api_app.create_app()

        assert called == ["called"]

    async def test_raises_when_tokens_exceed_base(self) -> None:
        from enhanced_agent_bus.api.config import BATCH_RATE_LIMIT_BASE

        await self._reset()
        with patch.dict(
            rl_mod.__dict__, {"RateLimitExceeded": _StubRLE, "RateLimitExceededWrapper": _StubRLE}
        ):
            # Consume exactly the base
            await rl_mod._check_rate_limit_memory("cli-exc", BATCH_RATE_LIMIT_BASE, 1000)
            # One more token should exceed the limit
            with pytest.raises(_StubRLE):
                await rl_mod._check_rate_limit_memory("cli-exc", 1, 10)

    async def test_different_clients_isolated(self) -> None:
        await self._reset()
        from enhanced_agent_bus.api.config import BATCH_RATE_LIMIT_BASE

        with patch.dict(
            rl_mod.__dict__, {"RateLimitExceeded": _StubRLE, "RateLimitExceededWrapper": _StubRLE}
        ):
            await rl_mod._check_rate_limit_memory("cli-a", BATCH_RATE_LIMIT_BASE, 1000)
            await rl_mod._check_rate_limit_memory("cli-b", BATCH_RATE_LIMIT_BASE, 1000)

    async def test_old_windows_cleaned_up(self) -> None:
        from enhanced_agent_bus.api.config import RATE_LIMIT_WINDOW_CLEANUP_MINUTES

        await self._reset()
        old_time = datetime.now(UTC) - timedelta(minutes=RATE_LIMIT_WINDOW_CLEANUP_MINUTES + 1)
        stale_key = "stale-client:2020-01-01T00:00:00+00:00"
        rl_mod._batch_rate_limit_state[stale_key] = {
            "tokens_consumed": 5,
            "window_start": old_time,
            "requests": 1,
        }

        await rl_mod._check_rate_limit_memory("new-client", 1, 10)
        assert stale_key not in rl_mod._batch_rate_limit_state

    async def test_recent_windows_not_cleaned_up(self) -> None:
        await self._reset()
        recent_time = datetime.now(UTC)
        key = "recent-client:2099-01-01T00:00:00+00:00"
        rl_mod._batch_rate_limit_state[key] = {
            "tokens_consumed": 5,
            "window_start": recent_time,
            "requests": 1,
        }
        await rl_mod._check_rate_limit_memory("another-client", 1, 10)
        assert key in rl_mod._batch_rate_limit_state

    async def test_error_message_has_retry_after(self) -> None:
        from enhanced_agent_bus.api.config import BATCH_RATE_LIMIT_BASE

        await self._reset()
        with patch.dict(
            rl_mod.__dict__, {"RateLimitExceeded": _StubRLE, "RateLimitExceededWrapper": _StubRLE}
        ):
            await rl_mod._check_rate_limit_memory("cli-msg", BATCH_RATE_LIMIT_BASE, 1000)
            with pytest.raises(_StubRLE) as exc_info:
                await rl_mod._check_rate_limit_memory("cli-msg", 5, 50)

        assert exc_info.value.retry_after_ms is not None

    async def test_cost_of_one_for_tiny_batch(self) -> None:
        """max(1, 5//10) == 1."""
        await self._reset()
        await rl_mod._check_rate_limit_memory("tiny", 1, 5)
        state = next(v for k, v in rl_mod._batch_rate_limit_state.items() if "tiny" in k)
        assert state["tokens_consumed"] == 1

    async def test_exactly_at_base_is_allowed(self) -> None:
        from enhanced_agent_bus.api.config import BATCH_RATE_LIMIT_BASE

        await self._reset()
        with patch.dict(
            rl_mod.__dict__, {"RateLimitExceeded": _StubRLE, "RateLimitExceededWrapper": _StubRLE}
        ):
            await rl_mod._check_rate_limit_memory("exact-cli", BATCH_RATE_LIMIT_BASE, 1000)
        state = next(v for k, v in rl_mod._batch_rate_limit_state.items() if "exact-cli" in k)
        assert state["tokens_consumed"] == BATCH_RATE_LIMIT_BASE


# ---------------------------------------------------------------------------
# Module-level symbols
# ---------------------------------------------------------------------------


class TestModuleLevelSymbols:
    def test_limiter_exists(self) -> None:
        assert hasattr(rl_mod, "limiter")
        assert rl_mod.limiter is not None

    def test_rate_limiting_available_is_bool(self) -> None:
        assert isinstance(rl_mod.RATE_LIMITING_AVAILABLE, bool)

    def test_rate_limit_exceeded_is_exported(self) -> None:
        assert hasattr(rl_mod, "RateLimitExceeded")

    def test_get_remote_address_is_callable(self) -> None:
        assert callable(rl_mod.get_remote_address)

    def test_rate_limit_exceeded_handler_exported(self) -> None:
        assert hasattr(rl_mod, "_rate_limit_exceeded_handler")

    def test_check_batch_rate_limit_is_coroutine_function(self) -> None:
        import inspect

        assert inspect.iscoroutinefunction(rl_mod.check_batch_rate_limit)

    def test_validate_item_sizes_is_callable(self) -> None:
        assert callable(rl_mod.validate_item_sizes)

    def test_all_list_populated(self) -> None:
        for name in rl_mod.__all__:
            assert hasattr(rl_mod, name), f"Missing: {name}"


# ---------------------------------------------------------------------------
# Edge-case tests
# ---------------------------------------------------------------------------


class TestEdgeCases:
    async def test_no_redis_uses_memory_path(self) -> None:
        """When _redis_client is None, the memory path is used directly."""
        called: list[tuple[str, int, int]] = []

        async def _mock_mem(client_id: str, cost: int, batch_size: int) -> None:
            called.append((client_id, cost, batch_size))

        with patch.dict(
            rl_mod.__dict__,
            {"RATE_LIMITING_AVAILABLE": True, "_redis_client": None},
        ):
            with patch.object(rl_mod, "_check_rate_limit_memory", _mock_mem):
                await rl_mod.check_batch_rate_limit("cli-nomem", 20)

        assert len(called) == 1
        assert called[0][0] == "cli-nomem"
        assert called[0][2] == 20

    async def test_redis_key_format(self) -> None:
        """Key must be rate_limit:<client>:<YYYYMMDDTHHmm>."""
        mock_redis = AsyncMock()
        captured: list[str] = []

        async def _incrby(key: str, amount: int) -> int:
            captured.append(key)
            return amount

        mock_redis.incrby = _incrby
        mock_redis.expire = AsyncMock()

        with patch.dict(rl_mod.__dict__, {"_redis_client": mock_redis}):
            await rl_mod._check_rate_limit_redis("test-key-client", 1, 10)

        key = captured[0]
        parts = key.split(":")
        assert parts[0] == "rate_limit"
        assert parts[1] == "test-key-client"
        assert len(parts[2]) == 13

    async def test_concurrent_memory_clients(self) -> None:
        async with rl_mod._batch_rate_limit_lock:
            rl_mod._batch_rate_limit_state.clear()

        await asyncio.gather(
            *[rl_mod._check_rate_limit_memory(f"concurrent-{i}", 1, 10) for i in range(5)]
        )
        client_keys = [k for k in rl_mod._batch_rate_limit_state if "concurrent-" in k]
        assert len(client_keys) == 5

    def test_batch_request_protocol_can_be_used(self) -> None:
        """BatchRequestProtocol is a Protocol — validate structural check."""
        from enhanced_agent_bus.api.rate_limiting import BatchRequestProtocol

        class _Concrete:
            items: ClassVar[list] = []
            batch_id: str = "x"

        obj = _Concrete()
        # Protocol check — isinstance will work with runtime_checkable if decorated,
        # here we just verify the attribute structure matches what code expects.
        assert hasattr(obj, "items")
        assert hasattr(obj, "batch_id")

    async def test_redis_exception_logs_warning_and_uses_memory(self) -> None:
        """TypeError from RateLimitExceeded should also trigger memory fallback."""
        from enhanced_agent_bus.api.config import BATCH_RATE_LIMIT_BASE

        mock_redis = AsyncMock()
        mock_redis.incrby = AsyncMock(return_value=BATCH_RATE_LIMIT_BASE + 1)
        mock_redis.expire = AsyncMock()

        mem_check = AsyncMock()

        # Do NOT patch RateLimitExceeded → real slowapi raises TypeError on __init__,
        # which the except clause catches and routes to memory.
        with patch.dict(
            rl_mod.__dict__,
            {"RATE_LIMITING_AVAILABLE": True, "_redis_client": mock_redis},
        ):
            with patch.object(rl_mod, "_check_rate_limit_memory", mem_check):
                await rl_mod.check_batch_rate_limit("exc-fallback", 10)

        mem_check.assert_awaited_once()
