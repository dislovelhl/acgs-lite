"""
Tests for RLMREPLEnvironment initialization and namespace setup.
Constitutional Hash: 608508a9bd224290
"""

from unittest.mock import patch

import pytest

from enhanced_agent_bus.tests.rlm_repl.conftest import _make_repl

REPL_MODULE = "enhanced_agent_bus.rlm_repl"


class TestRLMREPLEnvironmentInit:
    def test_raises_when_repl_disabled(self):
        from enhanced_agent_bus.rlm_repl import REPLDisabledError, RLMREPLEnvironment

        with patch(f"{REPL_MODULE}.is_repl_enabled", return_value=False):
            with pytest.raises(REPLDisabledError):
                RLMREPLEnvironment()

    def test_init_default_config(self):
        from enhanced_agent_bus.rlm_repl import REPLConfig, RLMREPLEnvironment

        with patch(f"{REPL_MODULE}.is_repl_enabled", return_value=True):
            repl = RLMREPLEnvironment()
            assert isinstance(repl.config, REPLConfig)
            assert repl._operation_count == 0
            assert repl._audit_trail == []
            assert repl._contexts == {}
            assert repl._rate_limit_violations == 0

    def test_init_custom_config(self):
        from enhanced_agent_bus.rlm_repl import (
            REPLConfig,
            REPLSecurityLevel,
            RLMREPLEnvironment,
        )

        cfg = REPLConfig(security_level=REPLSecurityLevel.STRICT)
        with patch(f"{REPL_MODULE}.is_repl_enabled", return_value=True):
            repl = RLMREPLEnvironment(cfg)
            assert repl.config.security_level == REPLSecurityLevel.STRICT

    def test_namespace_contains_safe_builtins_and_helpers(self):
        repl = _make_repl()
        assert "__builtins__" in repl._namespace
        assert "re" in repl._namespace
        assert "json_loads" in repl._namespace
        assert "json_dumps" in repl._namespace
        assert "search" in repl._namespace
        assert "slice_context" in repl._namespace
        assert "word_count" in repl._namespace
        assert "line_count" in repl._namespace
        assert "find_all" in repl._namespace


class TestSetupSafeNamespace:
    def test_reset_clears_namespace(self):
        repl = _make_repl()
        repl._namespace["extra"] = 123
        repl._setup_safe_namespace()
        assert "extra" not in repl._namespace

    def test_safe_builtins_dict_in_namespace(self):
        repl = _make_repl()
        builtins = repl._namespace["__builtins__"]
        assert isinstance(builtins, dict)
        assert "len" in builtins
        assert "exec" not in builtins
        assert "open" not in builtins
