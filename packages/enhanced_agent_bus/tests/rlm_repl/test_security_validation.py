"""
Tests for REPL security validation and AST checks.
Constitutional Hash: 608508a9bd224290
"""

import ast
import logging

import pytest

from enhanced_agent_bus.observability.structured_logging import get_logger
from enhanced_agent_bus.tests.rlm_repl.conftest import _make_repl

REPL_MODULE = "enhanced_agent_bus.rlm_repl"


class TestValidateCode:
    def test_safe_code_returns_empty_issues(self):
        repl = _make_repl()
        issues = repl._validate_code("len('hello')")
        assert issues == []

    def test_blocked_pattern_detected(self):
        repl = _make_repl()
        issues = repl._validate_code("__import__('os')")
        assert len(issues) > 0
        assert any("Blocked pattern" in issue for issue in issues)

    def test_exec_blocked(self):
        repl = _make_repl()
        issues = repl._validate_code("exec('print(1)')")
        assert len(issues) > 0

    def test_open_blocked(self):
        repl = _make_repl()
        issues = repl._validate_code("open('/etc/passwd')")
        assert len(issues) > 0

    def test_import_statement_blocked_by_default(self):
        repl = _make_repl()
        issues = repl._validate_code("import os")
        assert len(issues) > 0

    def test_import_allowed_when_flag_set(self):
        from enhanced_agent_bus.rlm_repl import REPLConfig

        config = REPLConfig(allow_imports=True)
        repl = _make_repl(config)
        issues = repl._validate_code("import json")
        ast_import_issues = [i for i in issues if "Import statements not allowed" in i]
        assert ast_import_issues == []

    def test_dunder_attribute_access_blocked(self):
        repl = _make_repl()
        issues = repl._validate_code("x.__class__")
        assert any("not allowed" in issue for issue in issues)

    def test_syntax_error_returns_issue(self):
        repl = _make_repl()
        issues = repl._validate_code("def ()")
        assert any("Syntax error" in issue for issue in issues)


class TestValidateAstSecurity:
    def test_safe_ast_no_error(self):
        repl = _make_repl()
        tree = ast.parse("x + y", mode="eval")
        repl._validate_ast_security(tree)

    def test_dangerous_name_raises(self):
        repl = _make_repl()
        tree = ast.parse("open('x')", mode="eval")
        with pytest.raises(ValueError, match="SECURITY"):
            repl._validate_ast_security(tree)

    def test_dunder_attribute_raises(self):
        repl = _make_repl()
        tree = ast.parse("x.__class__", mode="eval")
        with pytest.raises(ValueError, match="SECURITY"):
            repl._validate_ast_security(tree)

    def test_allowed_underscore_internal_vars(self):
        repl = _make_repl()
        tree = ast.parse("_output", mode="eval")
        repl._validate_ast_security(tree)

    def test_suspicious_string_logs_warning(self, caplog):
        repl = _make_repl()
        tree = ast.parse("'__import__'", mode="eval")
        with caplog.at_level(logging.WARNING):
            repl._validate_ast_security(tree)

    def test_sys_name_raises(self):
        repl = _make_repl()
        tree = ast.parse("sys", mode="eval")
        with pytest.raises(ValueError, match="SECURITY"):
            repl._validate_ast_security(tree)

    def test_globals_name_raises(self):
        repl = _make_repl()
        tree = ast.parse("globals()", mode="eval")
        with pytest.raises(ValueError, match="SECURITY"):
            repl._validate_ast_security(tree)

    def test_import_node_raises(self):
        repl = _make_repl()
        tree = ast.parse("import os", mode="exec")
        with pytest.raises(ValueError, match="SECURITY"):
            repl._validate_ast_security(tree)

    def test_dunder_name_raises(self):
        repl = _make_repl()
        tree = ast.parse("__builtins__", mode="eval")
        with pytest.raises(ValueError, match="SECURITY"):
            repl._validate_ast_security(tree)

    def test_underscore_bare_allowed(self):
        repl = _make_repl()
        tree = ast.parse("_", mode="eval")
        repl._validate_ast_security(tree)

    def test_output_attribute_access_allowed(self):
        repl = _make_repl()
        tree = ast.parse("dummy._output", mode="eval")
        repl._validate_ast_security(tree)


class TestGetSafeGlobals:
    def test_returns_dict_with_builtins(self):
        repl = _make_repl()
        safe = repl._get_safe_globals()
        assert "__builtins__" in safe
        assert "len" in safe["__builtins__"]

    def test_does_not_contain_open(self):
        repl = _make_repl()
        safe = repl._get_safe_globals()
        assert "open" not in safe["__builtins__"]

    def test_builtins_mapping_is_frozen(self):
        repl = _make_repl()
        safe = repl._get_safe_globals()
        with pytest.raises(TypeError):
            safe["__builtins__"]["open"] = open
