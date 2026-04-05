"""
Tests for REPL factory functions and high-level integration flows.
Constitutional Hash: 608508a9bd224290
"""

import asyncio
from unittest.mock import patch

from enhanced_agent_bus.tests.rlm_repl.conftest import _make_repl

REPL_MODULE = "enhanced_agent_bus.rlm_repl"


class TestFactoryFunctions:
    def test_create_rlm_repl_default_security_level(self):
        from enhanced_agent_bus.rlm_repl import REPLSecurityLevel, create_rlm_repl

        with patch(f"{REPL_MODULE}.is_repl_enabled", return_value=True):
            repl = create_rlm_repl()
            assert repl.config.security_level == REPLSecurityLevel.STANDARD

    def test_create_governance_repl_uses_strict_security(self):
        from enhanced_agent_bus.rlm_repl import REPLSecurityLevel, create_governance_repl

        with patch(f"{REPL_MODULE}.is_repl_enabled", return_value=True):
            repl = create_governance_repl()
            assert repl.config.security_level == REPLSecurityLevel.STRICT


class TestExecuteIntegration:
    async def test_search_helper_via_execute(self):
        repl = _make_repl()
        repl.set_context("doc", "hello world hello")
        with patch(f"{REPL_MODULE}.is_repl_enabled", return_value=True):
            result = await repl.execute("search('hello')")
        assert result["success"] is True
        assert len(result["result"]) == 2

    async def test_word_count_via_execute(self):
        repl = _make_repl()
        repl.set_context("doc", "one two three four five")
        with patch(f"{REPL_MODULE}.is_repl_enabled", return_value=True):
            result = await repl.execute("word_count(doc)")
        assert result["success"] is True
        assert result["result"] == 5


class TestTimeoutCapping:
    async def test_timeout_capped_at_hard_limit(self):
        """max_execution_time_seconds > HARD_EXECUTION_TIMEOUT_SECONDS is capped."""
        from enhanced_agent_bus.rlm_repl import HARD_EXECUTION_TIMEOUT_SECONDS, REPLConfig

        config = REPLConfig(max_execution_time_seconds=999.0)
        repl = _make_repl(config)

        captured_timeout = []
        original_wait_for = asyncio.wait_for

        async def capturing_wait_for(coro, timeout):
            captured_timeout.append(timeout)
            return await original_wait_for(coro, timeout=timeout)

        with (
            patch(f"{REPL_MODULE}.is_repl_enabled", return_value=True),
            patch("asyncio.wait_for", side_effect=capturing_wait_for),
        ):
            await repl.execute("1+1")

        assert captured_timeout[0] == HARD_EXECUTION_TIMEOUT_SECONDS
