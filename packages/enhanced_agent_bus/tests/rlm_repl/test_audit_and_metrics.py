"""
Tests for REPL audit trail, operation records, and metrics.
Constitutional Hash: 608508a9bd224290
"""

from datetime import UTC, datetime, timezone

from enhanced_agent_bus.tests.rlm_repl.conftest import _make_repl


class TestREPLOperation:
    def test_to_dict_short_code(self):
        from enhanced_agent_bus.rlm_repl import REPLOperation

        op = REPLOperation(
            operation_id="op_0",
            timestamp=datetime.now(UTC),
            code="len(x)",
            result_preview="42",
            execution_time_ms=1.5,
            success=True,
        )
        d = op.to_dict()
        assert d["operation_id"] == "op_0"
        assert d["code"] == "len(x)"
        assert d["success"] is True

    def test_to_dict_long_code_truncated(self):
        from enhanced_agent_bus.rlm_repl import REPLOperation

        long_code = "x" * 300
        op = REPLOperation(
            operation_id="op_1",
            timestamp=datetime.now(UTC),
            code=long_code,
            result_preview="result",
            execution_time_ms=2.0,
            success=False,
            error="some error",
        )
        d = op.to_dict()
        assert d["code"].endswith("...")
        assert len(d["code"]) == 203


class TestRecordOperation:
    def test_records_operation_when_audit_enabled(self):
        from enhanced_agent_bus.rlm_repl import REPLConfig

        config = REPLConfig(enable_audit_trail=True)
        repl = _make_repl(config)
        repl._record_operation("op_0", "len(x)", "42", 1.5, True)
        assert len(repl._audit_trail) == 1

    def test_does_not_record_when_audit_disabled(self):
        from enhanced_agent_bus.rlm_repl import REPLConfig

        config = REPLConfig(enable_audit_trail=False)
        repl = _make_repl(config)
        repl._record_operation("op_0", "len(x)", "42", 1.5, True)
        assert len(repl._audit_trail) == 0


class TestAuditTrail:
    def test_get_audit_trail_empty(self):
        repl = _make_repl()
        trail = repl.get_audit_trail()
        assert trail == []

    def test_get_audit_trail_limit(self):
        repl = _make_repl()
        for i in range(10):
            repl._record_operation(f"op_{i}", "code", "r", 1.0, True)
        trail = repl.get_audit_trail(limit=3)
        assert len(trail) == 3

    def test_clear_audit_trail(self):
        repl = _make_repl()
        repl._record_operation("op_0", "code", "r", 1.0, True)
        repl.clear_audit_trail()
        assert repl._audit_trail == []


class TestGetMetrics:
    def test_initial_metrics(self):
        repl = _make_repl()
        m = repl.get_metrics()
        assert m["contexts_loaded"] == 0
        assert m["operations_executed"] == 0

    def test_metrics_after_context_loaded(self):
        repl = _make_repl()
        repl.set_context("doc", "hello world")
        m = repl.get_metrics()
        assert m["contexts_loaded"] == 1
        assert m["total_context_size"] == len("hello world")


class TestReset:
    def test_reset_clears_contexts_and_count(self):
        repl = _make_repl()
        repl.set_context("a", "data")
        repl._operation_count = 5
        repl.reset()
        assert repl._contexts == {}
        assert repl._operation_count == 0


class TestConstitutionalHashInAudit:
    def test_audit_record_has_correct_hash(self):
        from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

        repl = _make_repl()
        repl._record_operation("op_0", "code", "result", 1.0, True)
        trail = repl.get_audit_trail()
        assert trail[0]["constitutional_hash"] == CONSTITUTIONAL_HASH
