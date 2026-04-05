"""
Tests for RLMREPLEnvironment execution paths (eval/exec, timeout, errors, rate limiting).
Constitutional Hash: 608508a9bd224290
"""

import asyncio
import time
from contextlib import contextmanager
from unittest.mock import patch

import pytest

from enhanced_agent_bus.tests.rlm_repl.conftest import _make_repl

REPL_MODULE = "enhanced_agent_bus.rlm_repl"


class TestExecuteDisabledGuard:
    async def test_execute_raises_when_repl_disabled(self):
        from enhanced_agent_bus.rlm_repl import REPLDisabledError

        repl = _make_repl()
        with patch(f"{REPL_MODULE}.is_repl_enabled", return_value=False):
            with pytest.raises(REPLDisabledError):
                await repl.execute("len('x')")


class TestCheckRateLimit:
    def test_no_rate_limit_when_disabled(self):
        from enhanced_agent_bus.rlm_repl import REPLConfig

        config = REPLConfig(enable_rate_limiting=False)
        repl = _make_repl(config)
        result = repl._check_rate_limit()
        assert result is None

    def test_returns_none_within_limits(self):
        repl = _make_repl()
        result = repl._check_rate_limit()
        assert result is None

    def test_per_minute_rate_limit_exceeded(self):
        from enhanced_agent_bus.rlm_repl import REPLConfig

        config = REPLConfig(max_operations_per_minute=2)
        repl = _make_repl(config)
        now = time.time()
        repl._operation_timestamps = [now - 10, now - 5, now - 1]
        result = repl._check_rate_limit()
        assert result is not None
        assert "Rate limit exceeded" in result


class TestExecuteRateLimit:
    async def test_execute_returns_failure_when_rate_limited(self):
        from enhanced_agent_bus.rlm_repl import REPLConfig

        config = REPLConfig(max_operations_per_minute=1)
        repl = _make_repl(config)
        now = time.time()
        repl._operation_timestamps = [now - 30, now - 20]

        with patch(f"{REPL_MODULE}.is_repl_enabled", return_value=True):
            result = await repl.execute("1+1")

        assert result["success"] is False
        assert "Rate limit" in result["error"]


class TestExecuteSuccess:
    async def test_simple_expression_returns_value(self):
        repl = _make_repl()
        with patch(f"{REPL_MODULE}.is_repl_enabled", return_value=True):
            result = await repl.execute("1 + 2")
        assert result["success"] is True
        assert result["result"] == 3

    async def test_assignment_statement(self):
        repl = _make_repl()
        with patch(f"{REPL_MODULE}.is_repl_enabled", return_value=True):
            result = await repl.execute("x = 42")
        assert result["success"] is True

    async def test_exec_with_underscore_variable(self):
        repl = _make_repl()
        repl._namespace.pop("_", None)
        with patch(f"{REPL_MODULE}.is_repl_enabled", return_value=True):
            result = await repl.execute("_ = 'stored'")
        assert result["success"] is True
        assert result["result"] == "stored"


class TestExecuteTimeout:
    async def test_asyncio_timeout_returns_failure(self):
        repl = _make_repl()

        with (
            patch(f"{REPL_MODULE}.is_repl_enabled", return_value=True),
            patch("asyncio.wait_for", side_effect=TimeoutError()),
        ):
            result = await repl.execute("1+1")

        assert result["success"] is False
        assert "timed out" in result["error"]


class TestExecuteErrorHandling:
    async def test_runtime_error_in_executor_handled(self):
        repl = _make_repl()
        with (
            patch(f"{REPL_MODULE}.is_repl_enabled", return_value=True),
            patch.object(repl, "_execute_sync", side_effect=ValueError("bad input")),
        ):
            result = await repl.execute("1+1")

        assert result["success"] is False
        assert "bad input" in result["error"]


class TestExecuteSync:
    def test_eval_mode_returns_value(self):
        repl = _make_repl()
        result = repl._execute_sync("1 + 2")
        assert result == 3

    def test_eval_raises_governance_error_on_execution_timeout(self):
        from enhanced_agent_bus._compat.security.execution_time_limit import ExecutionTimeout

        repl = _make_repl()

        @contextmanager
        def raise_timeout(*args, **kwargs):
            raise ExecutionTimeout()
            yield

        with patch(f"{REPL_MODULE}.python_execution_time_limit", raise_timeout):
            with pytest.raises(Exception, match="exceeded"):
                repl._execute_sync("1 + 1")

    def test_execute_sync_output_buffer_returned(self):
        from io import StringIO

        repl = _make_repl()
        repl._namespace.pop("_", None)

        fake_buffer = StringIO()
        fake_buffer.write("captured output\n")

        with patch(f"{REPL_MODULE}.StringIO", return_value=fake_buffer):
            result = repl._execute_sync("x = 42")

        assert result == "captured output\n"
