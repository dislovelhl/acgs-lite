"""
Tests for module-level constants, configuration, and basic REPL types.
Constitutional Hash: 608508a9bd224290
"""

import logging
from unittest.mock import patch

from enhanced_agent_bus.observability.structured_logging import get_logger

REPL_MODULE = "enhanced_agent_bus.rlm_repl"


class TestModuleLevelConstants:
    """Verify module-level constants are defined correctly."""

    def test_safe_builtins_is_set(self):
        from enhanced_agent_bus.rlm_repl import SAFE_BUILTINS

        assert isinstance(SAFE_BUILTINS, set)
        assert "len" in SAFE_BUILTINS
        assert "str" in SAFE_BUILTINS

    def test_blocked_patterns_is_list(self):
        from enhanced_agent_bus.rlm_repl import BLOCKED_PATTERNS

        assert isinstance(BLOCKED_PATTERNS, list)
        assert len(BLOCKED_PATTERNS) > 0
        assert any("import" in p for p in BLOCKED_PATTERNS)
        assert any("exec" in p for p in BLOCKED_PATTERNS)

    def test_hard_timeout_constant(self):
        from enhanced_agent_bus.rlm_repl import HARD_EXECUTION_TIMEOUT_SECONDS

        assert HARD_EXECUTION_TIMEOUT_SECONDS == 5.0

    def test_repl_execution_errors_tuple(self):
        from enhanced_agent_bus.rlm_repl import REPL_EXECUTION_ERRORS

        assert RuntimeError in REPL_EXECUTION_ERRORS
        assert ValueError in REPL_EXECUTION_ERRORS
        assert TypeError in REPL_EXECUTION_ERRORS
        assert KeyError in REPL_EXECUTION_ERRORS
        assert AttributeError in REPL_EXECUTION_ERRORS
        assert OSError in REPL_EXECUTION_ERRORS


class TestIsReplEnabled:
    def test_returns_false_in_production_even_when_flag_set(self):
        with (
            patch(f"{REPL_MODULE}.IS_PRODUCTION", True),
            patch(f"{REPL_MODULE}.ENABLE_RLM_REPL", True),
        ):
            from enhanced_agent_bus.rlm_repl import is_repl_enabled

            assert is_repl_enabled() is False

    def test_returns_false_in_production_no_flag(self):
        with (
            patch(f"{REPL_MODULE}.IS_PRODUCTION", True),
            patch(f"{REPL_MODULE}.ENABLE_RLM_REPL", False),
        ):
            from enhanced_agent_bus.rlm_repl import is_repl_enabled

            assert is_repl_enabled() is False

    def test_production_warning_logged_when_flag_set(self, caplog):
        with (
            patch(f"{REPL_MODULE}.IS_PRODUCTION", True),
            patch(f"{REPL_MODULE}.ENABLE_RLM_REPL", True),
            caplog.at_level(logging.WARNING, logger=REPL_MODULE),
        ):
            from enhanced_agent_bus.rlm_repl import is_repl_enabled

            result = is_repl_enabled()
            assert result is False
            assert any("BLOCKED" in r.message or "production" in r.message for r in caplog.records)

    def test_returns_enable_flag_when_not_production(self):
        with (
            patch(f"{REPL_MODULE}.IS_PRODUCTION", False),
            patch(f"{REPL_MODULE}.ENABLE_RLM_REPL", True),
        ):
            from enhanced_agent_bus.rlm_repl import is_repl_enabled

            assert is_repl_enabled() is True

    def test_returns_false_when_flag_false_not_production(self):
        with (
            patch(f"{REPL_MODULE}.IS_PRODUCTION", False),
            patch(f"{REPL_MODULE}.ENABLE_RLM_REPL", False),
        ):
            from enhanced_agent_bus.rlm_repl import is_repl_enabled

            assert is_repl_enabled() is False


class TestREPLDisabledError:
    def test_error_attributes(self):
        from enhanced_agent_bus.rlm_repl import REPLDisabledError

        err = REPLDisabledError("disabled")
        assert err.http_status_code == 403
        assert err.error_code == "REPL_DISABLED"
        assert "disabled" in str(err)

    def test_is_acgs_base_error(self):
        from enhanced_agent_bus._compat.errors import ACGSBaseError
        from enhanced_agent_bus.rlm_repl import REPLDisabledError

        assert issubclass(REPLDisabledError, ACGSBaseError)


class TestREPLSecurityLevel:
    def test_enum_values(self):
        from enhanced_agent_bus.rlm_repl import REPLSecurityLevel

        assert REPLSecurityLevel.STRICT.value == "strict"
        assert REPLSecurityLevel.STANDARD.value == "standard"
        assert REPLSecurityLevel.PERMISSIVE.value == "permissive"

    def test_is_str_subclass(self):
        from enhanced_agent_bus.rlm_repl import REPLSecurityLevel

        assert isinstance(REPLSecurityLevel.STRICT, str)


class TestREPLConfig:
    def test_default_values(self):
        from enhanced_agent_bus.rlm_repl import REPLConfig, REPLSecurityLevel

        cfg = REPLConfig()
        assert cfg.security_level == REPLSecurityLevel.STANDARD
        assert cfg.max_execution_time_seconds == 30.0
        assert cfg.max_memory_mb == 512
        assert cfg.max_output_length == 100_000
        assert cfg.allow_imports is False
        assert cfg.allow_file_access is False
        assert cfg.allow_network is False
        assert cfg.allow_subprocess is False
        assert cfg.max_context_size_mb == 100
        assert cfg.max_variables == 100
        assert cfg.enable_audit_trail is True
        assert cfg.audit_all_operations is True
        assert cfg.enable_rate_limiting is True
        assert cfg.max_operations_per_minute == 60
        assert cfg.max_operations_per_hour == 500

    def test_constitutional_hash_default(self):
        from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
        from enhanced_agent_bus.rlm_repl import REPLConfig

        cfg = REPLConfig()
        assert cfg.constitutional_hash == CONSTITUTIONAL_HASH

    def test_custom_values(self):
        from enhanced_agent_bus.rlm_repl import REPLConfig, REPLSecurityLevel

        cfg = REPLConfig(
            security_level=REPLSecurityLevel.STRICT,
            max_execution_time_seconds=10.0,
            max_memory_mb=256,
            allow_imports=True,
        )
        assert cfg.security_level == REPLSecurityLevel.STRICT
        assert cfg.max_execution_time_seconds == 10.0
        assert cfg.max_memory_mb == 256
        assert cfg.allow_imports is True
