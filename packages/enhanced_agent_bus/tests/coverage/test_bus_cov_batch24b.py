"""Coverage tests for:
1. packages/acgs-lite/src/acgs_lite/engine/core.py
2. packages/enhanced_agent_bus/opa_client/core.py

Targets uncovered lines: engine/core.py (176 missing), opa_client/core.py (89 missing).
"""

from __future__ import annotations

import gc
import os
import sys
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from acgs_lite.audit import AuditEntry, AuditLog

# ============================================================================
# Part 1: acgs_lite engine/core.py tests
# ============================================================================
from acgs_lite.constitution import Constitution, Rule, Severity
from acgs_lite.engine.core import (
    _ANON,
    GovernanceEngine,
    ValidationResult,
    Violation,
    _dedup_violations,
    _FastAuditLog,
    _NoopRecorder,
)
from acgs_lite.errors import ConstitutionalViolationError


def _make_rule(
    rule_id: str = "R1",
    text: str = "No harmful actions",
    severity: Severity = Severity.MEDIUM,
    keywords: list[str] | None = None,
    patterns: list[str] | None = None,
    category: str = "safety",
    enabled: bool = True,
) -> Rule:
    """Helper to create a Rule with defaults."""
    return Rule(
        id=rule_id,
        text=text,
        severity=severity,
        keywords=keywords or ["harmful"],
        patterns=patterns or [],
        category=category,
        enabled=enabled,
    )


def _make_constitution(rules: list[Rule] | None = None) -> Constitution:
    """Helper to create a Constitution with default rules."""
    if rules is None:
        rules = [_make_rule()]
    return Constitution(name="test", version="1.0.0", rules=rules)


def _make_engine(
    rules: list[Rule] | None = None,
    audit_log: AuditLog | None = None,
    strict: bool = True,
    custom_validators: list | None = None,
) -> GovernanceEngine:
    """Create a GovernanceEngine with GC freeze/disable disabled for test safety."""
    constitution = _make_constitution(rules)
    # Re-enable GC after engine init (engine freezes + may disable GC)
    gc_was_enabled = gc.isenabled()
    try:
        engine = GovernanceEngine(
            constitution,
            audit_log=audit_log,
            custom_validators=custom_validators,
            strict=strict,
        )
    finally:
        if gc_was_enabled:
            gc.enable()
    return engine


# ---------------------------------------------------------------------------
# Violation NamedTuple
# ---------------------------------------------------------------------------


class TestViolation:
    def test_creation(self):
        v = Violation("R1", "rule text", Severity.HIGH, "matched", "safety")
        assert v.rule_id == "R1"
        assert v.rule_text == "rule text"
        assert v.severity == Severity.HIGH
        assert v.matched_content == "matched"
        assert v.category == "safety"

    def test_namedtuple_immutable(self):
        v = Violation("R1", "text", Severity.LOW, "m", "c")
        with pytest.raises(AttributeError):
            v.rule_id = "R2"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ValidationResult dataclass
# ---------------------------------------------------------------------------


class TestValidationResult:
    def test_blocking_violations(self):
        v_crit = Violation("R1", "t", Severity.CRITICAL, "m", "c")
        v_high = Violation("R2", "t", Severity.HIGH, "m", "c")
        v_med = Violation("R3", "t", Severity.MEDIUM, "m", "c")
        v_low = Violation("R4", "t", Severity.LOW, "m", "c")

        result = ValidationResult(
            valid=False,
            constitutional_hash="abc",
            violations=[v_crit, v_high, v_med, v_low],
        )
        blocking = result.blocking_violations
        assert len(blocking) == 2
        assert v_crit in blocking
        assert v_high in blocking

    def test_warnings(self):
        v_med = Violation("R3", "t", Severity.MEDIUM, "m", "c")
        v_low = Violation("R4", "t", Severity.LOW, "m", "c")
        v_crit = Violation("R1", "t", Severity.CRITICAL, "m", "c")

        result = ValidationResult(
            valid=False,
            constitutional_hash="abc",
            violations=[v_crit],
            warnings=[v_med, v_low],
        )
        warnings = result.warnings
        assert len(warnings) == 2
        assert v_med in warnings
        assert v_low in warnings

    def test_to_dict(self):
        v = Violation("R1", "rule text", Severity.MEDIUM, "matched", "safety")
        result = ValidationResult(
            valid=True,
            constitutional_hash="hash123",
            violations=[v],
            rules_checked=5,
            latency_ms=1.23,
            request_id="req-1",
            action="test action",
            agent_id="agent-1",
        )
        d = result.to_dict()
        assert d["valid"] is True
        assert d["constitutional_hash"] == "hash123"
        assert d["rules_checked"] == 5
        assert d["latency_ms"] == 1.23
        assert d["request_id"] == "req-1"
        assert d["action"] == "test action"
        assert d["agent_id"] == "agent-1"
        assert len(d["violations"]) == 1
        assert d["violations"][0]["rule_id"] == "R1"
        assert d["violations"][0]["severity"] == "medium"

    def test_to_dict_no_violations(self):
        result = ValidationResult(valid=True, constitutional_hash="h")
        d = result.to_dict()
        assert d["violations"] == []
        assert d["valid"] is True


# ---------------------------------------------------------------------------
# _dedup_violations
# ---------------------------------------------------------------------------


class TestDedupViolations:
    def test_no_duplicates(self):
        v1 = Violation("R1", "t", Severity.LOW, "m", "c")
        v2 = Violation("R2", "t", Severity.LOW, "m", "c")
        result = _dedup_violations([v1, v2])
        assert len(result) == 2

    def test_with_duplicates(self):
        v1 = Violation("R1", "t1", Severity.LOW, "m1", "c1")
        v2 = Violation("R1", "t2", Severity.HIGH, "m2", "c2")
        v3 = Violation("R2", "t3", Severity.MEDIUM, "m3", "c3")
        result = _dedup_violations([v1, v2, v3])
        assert len(result) == 2
        assert result[0].rule_id == "R1"
        assert result[1].rule_id == "R2"

    def test_all_same(self):
        v = Violation("R1", "t", Severity.LOW, "m", "c")
        result = _dedup_violations([v, v, v])
        assert len(result) == 1


# ---------------------------------------------------------------------------
# _NoopRecorder
# ---------------------------------------------------------------------------


class TestNoopRecorder:
    def test_append_and_len(self):
        rec = _NoopRecorder()
        assert len(rec) == 0
        rec.append("anything")
        assert len(rec) == 1
        rec.append(None)
        assert len(rec) == 2


# ---------------------------------------------------------------------------
# _FastAuditLog
# ---------------------------------------------------------------------------


class TestFastAuditLog:
    def test_record_fast_full_tuple(self):
        log = _FastAuditLog("hash123")
        log.record_fast("req1", "agent1", "do_thing", True, [], "hash123", 1.0, "2025-01-01")
        assert len(log) == 1
        entries = log.entries
        assert len(entries) == 1
        e = entries[0]
        assert e.id == "req1"
        assert e.agent_id == "agent1"
        assert e.action == "do_thing"
        assert e.valid is True

    def test_record_compat_shim(self):
        log = _FastAuditLog("hash")
        entry = AuditEntry(
            id="r1",
            type="validation",
            agent_id="a1",
            action="act",
            valid=True,
            violations=[],
            constitutional_hash="hash",
            latency_ms=0.5,
            timestamp="2025-01-01",
        )
        result = log.record(entry)
        assert result == ""
        assert len(log) == 1

    def test_entries_compact_record(self):
        log = _FastAuditLog("hash")
        # Simulate a compact 2-tuple record
        log._records.append(("req1", "action1"))
        entries = log.entries
        assert len(entries) == 1
        e = entries[0]
        assert e.id == "req1"
        assert e.agent_id == _ANON
        assert e.action == "action1"
        assert e.valid is True

    def test_entries_mixed_records(self):
        log = _FastAuditLog("hash")
        log._records.append(("req1", "action1"))  # compact
        log.record_fast("req2", "agent2", "action2", False, ["R1"], "hash", 2.0, "ts")
        entries = log.entries
        assert len(entries) == 2
        assert entries[0].id == "req1"
        assert entries[1].id == "req2"
        assert entries[1].valid is False


# ---------------------------------------------------------------------------
# GovernanceEngine — initialization and basic validation
# ---------------------------------------------------------------------------


class TestGovernanceEngineInit:
    def test_default_init_with_no_rules(self):
        engine = _make_engine(rules=[])
        assert engine._rules_count == 0
        assert engine._const_hash == engine.constitution.hash

    def test_init_with_multiple_rules(self):
        rules = [
            _make_rule("R1", "No harm", Severity.CRITICAL, keywords=["harm"]),
            _make_rule("R2", "No leak", Severity.HIGH, keywords=["leak"]),
            _make_rule("R3", "Be nice", Severity.LOW, keywords=["rude"]),
        ]
        engine = _make_engine(rules=rules)
        assert engine._rules_count == 3
        assert len(engine._rule_data) == 3

    def test_init_with_custom_audit_log(self):
        audit = AuditLog()
        engine = _make_engine(audit_log=audit)
        assert engine.audit_log is audit
        assert engine._fast_records is None

    def test_init_with_disabled_rules(self):
        rules = [
            _make_rule("R1", "Active", Severity.MEDIUM, enabled=True),
            _make_rule("R2", "Disabled", Severity.MEDIUM, enabled=False),
        ]
        engine = _make_engine(rules=rules)
        # Only active rules should be in _active_rules
        assert engine._rules_count == 1

    def test_has_high_rules_false(self):
        rules = [
            _make_rule("R1", "Critical only", Severity.CRITICAL, keywords=["bad"]),
            _make_rule("R2", "Medium only", Severity.MEDIUM, keywords=["meh"]),
        ]
        engine = _make_engine(rules=rules)
        assert engine._has_high_rules is False

    def test_has_high_rules_true(self):
        rules = [
            _make_rule("R1", "High rule", Severity.HIGH, keywords=["danger"]),
        ]
        engine = _make_engine(rules=rules)
        assert engine._has_high_rules is True

    def test_init_with_patterns(self):
        rules = [
            _make_rule(
                "R1",
                "No secret deploy",
                Severity.CRITICAL,
                keywords=["secret"],
                patterns=[r"\bsecret\b"],
            ),
        ]
        engine = _make_engine(rules=rules)
        assert len(engine._pattern_rule_idxs) > 0


# ---------------------------------------------------------------------------
# GovernanceEngine.validate — allow path
# ---------------------------------------------------------------------------


class TestGovernanceEngineValidateAllow:
    def test_allow_safe_action(self):
        engine = _make_engine()
        result = engine.validate("run safety checks")
        assert result.valid is True

    def test_allow_returns_valid_result(self):
        engine = _make_engine()
        r1 = engine.validate("do something safe")
        r2 = engine.validate("do another safe thing")
        assert r1.valid is True
        assert r2.valid is True

    def test_allow_with_agent_id(self):
        audit = AuditLog()
        engine = _make_engine(audit_log=audit)
        result = engine.validate("safe action", agent_id="agent-42")
        assert result.valid is True
        assert result.agent_id == "agent-42"


# ---------------------------------------------------------------------------
# GovernanceEngine.validate — deny path
# ---------------------------------------------------------------------------


class TestGovernanceEngineValidateDeny:
    def test_critical_rule_raises(self):
        rules = [
            _make_rule("R1", "No harmful", Severity.CRITICAL, keywords=["harmful"]),
        ]
        engine = _make_engine(rules=rules, strict=True)
        with pytest.raises(ConstitutionalViolationError) as exc_info:
            engine.validate("do something harmful to people")
        assert exc_info.value.rule_id == "R1"

    def test_high_rule_raises_in_strict(self):
        rules = [
            _make_rule("R1", "No leaks allowed", Severity.HIGH, keywords=["leak"]),
        ]
        # Use audit_log to force slow path (fast path uses pooled result + NoopRecorder)
        audit = AuditLog()
        engine = _make_engine(rules=rules, strict=True, audit_log=audit)
        with pytest.raises(ConstitutionalViolationError):
            engine.validate("leak sensitive data")

    def test_medium_rule_no_raise(self):
        rules = [
            _make_rule("R1", "Be careful", Severity.MEDIUM, keywords=["risky"]),
        ]
        engine = _make_engine(rules=rules, strict=True)
        result = engine.validate("do risky thing")
        assert result.valid is True  # MEDIUM doesn't block
        # MEDIUM severity defaults to workflow_action=WARN, so violations land in warnings
        assert len(result.warnings) > 0

    def test_non_strict_high_no_raise(self):
        rules = [
            _make_rule("R1", "High rule", Severity.HIGH, keywords=["danger"]),
        ]
        engine = _make_engine(rules=rules, strict=False)
        result = engine.validate("danger ahead")
        assert result.valid is False
        assert len(result.violations) > 0


# ---------------------------------------------------------------------------
# GovernanceEngine.validate — context checking
# ---------------------------------------------------------------------------


class TestGovernanceEngineContext:
    def test_context_action_detail(self):
        rules = [
            _make_rule("R1", "No secret", Severity.MEDIUM, keywords=["secret"]),
        ]
        engine = _make_engine(rules=rules)
        # MEDIUM severity goes to warnings, not violations
        result = engine.validate(
            "this is secret info",
            context={"action_detail": "extra metadata"},
        )
        assert any(v.rule_id == "R1" for v in result.warnings)

    def test_context_action_description(self):
        rules = [
            _make_rule("R1", "No harmful", Severity.MEDIUM, keywords=["harmful"]),
        ]
        engine = _make_engine(rules=rules)
        result = engine.validate(
            "this is harmful content",
            context={"action_description": "extra metadata"},
        )
        assert any(v.rule_id == "R1" for v in result.warnings)

    def test_context_irrelevant_keys_ignored(self):
        rules = [
            _make_rule("R1", "No secret", Severity.MEDIUM, keywords=["secret"]),
        ]
        engine = _make_engine(rules=rules)
        result = engine.validate(
            "safe action",
            context={"source": "secret", "rule": "something"},
        )
        # "secret" in metadata-only context keys should NOT trigger violation
        assert result.valid is True

    def test_context_none(self):
        engine = _make_engine()
        result = engine.validate("safe action", context=None)
        assert result.valid is True

    def test_context_empty_dict(self):
        engine = _make_engine()
        result = engine.validate("safe action", context={})
        assert result.valid is True


# ---------------------------------------------------------------------------
# GovernanceEngine — custom validators
# ---------------------------------------------------------------------------


class TestCustomValidators:
    def test_custom_validator_adds_violations(self):
        def my_validator(action: str, ctx: dict) -> list[Violation]:
            if "banned" in action:
                return [
                    Violation("CUSTOM-1", "Banned word", Severity.MEDIUM, action[:200], "custom")
                ]
            return []

        # Use audit_log to force slow path so custom validators run
        audit = AuditLog()
        engine = _make_engine(custom_validators=[my_validator], audit_log=audit)
        result = engine.validate("banned word usage")
        # CUSTOM-1 has Severity.MEDIUM → workflow_action=WARN → result.warnings
        assert any(v.rule_id == "CUSTOM-1" for v in result.warnings)

    def test_custom_validator_exception_creates_error_violation(self):
        def bad_validator(action: str, ctx: dict) -> list[Violation]:
            raise RuntimeError("validator crashed")

        # CUSTOM-ERROR uses Severity.MEDIUM (infrastructure error: warn, not block).
        audit = AuditLog()
        engine = _make_engine(custom_validators=[bad_validator], audit_log=audit)
        result = engine.validate("any action")
        assert any(v.rule_id == "CUSTOM-ERROR" for v in result.warnings)
        assert any("validator crashed" in v.rule_text for v in result.warnings)

    def test_add_validator(self):
        engine = _make_engine()
        assert len(engine.custom_validators) == 0

        def noop_validator(action: str, ctx: dict) -> list[Violation]:
            return []

        engine.add_validator(noop_validator)
        assert len(engine.custom_validators) == 1


# ---------------------------------------------------------------------------
# GovernanceEngine.stats
# ---------------------------------------------------------------------------


class TestGovernanceEngineStats:
    def test_stats_with_noop_recorder(self):
        engine = _make_engine()
        engine.validate("safe action")
        stats = engine.stats
        assert "total_validations" in stats
        assert stats["total_validations"] == 1
        assert "compliance_rate" in stats
        # Fast mode returns None for compliance_rate (no per-entry tracking)
        assert stats["compliance_rate"] is None or stats["compliance_rate"] == 1.0
        assert "rules_count" in stats
        assert "constitutional_hash" in stats
        assert "avg_latency_ms" in stats

    def test_stats_with_audit_log(self):
        audit = AuditLog()
        engine = _make_engine(audit_log=audit)
        engine.validate("safe action")
        stats = engine.stats
        assert stats["total_validations"] == 1
        assert stats["compliance_rate"] == 1.0

    def test_stats_with_violations(self):
        audit = AuditLog()
        rules = [
            _make_rule("R1", "No bad", Severity.MEDIUM, keywords=["bad"]),
        ]
        engine = _make_engine(rules=rules, audit_log=audit)
        engine.validate("safe action")
        engine.validate("bad action")
        stats = engine.stats
        assert stats["total_validations"] == 2

    def test_stats_empty_audit_log(self):
        audit = AuditLog()
        engine = _make_engine(audit_log=audit)
        stats = engine.stats
        assert stats["total_validations"] == 0
        assert stats["compliance_rate"] == 1.0
        assert stats["avg_latency_ms"] == 0.0


# ---------------------------------------------------------------------------
# GovernanceEngine — audit log recording (slow path)
# ---------------------------------------------------------------------------


class TestGovernanceEngineAuditLog:
    def test_audit_entry_recorded_on_allow(self):
        audit = AuditLog()
        engine = _make_engine(audit_log=audit)
        engine.validate("safe action", agent_id="myagent")
        assert len(audit.entries) == 1
        entry = audit.entries[0]
        assert entry.valid is True
        assert entry.agent_id == "myagent"

    def test_audit_entry_recorded_on_violation(self):
        audit = AuditLog()
        rules = [
            _make_rule("R1", "No bad", Severity.MEDIUM, keywords=["bad"]),
        ]
        engine = _make_engine(rules=rules, audit_log=audit)
        result = engine.validate("bad thing happened")
        # MEDIUM → WARN → valid=True, violation in result.warnings
        assert result.valid is True
        assert len(result.warnings) > 0
        assert len(audit.entries) >= 1

    def test_audit_includes_rule_evaluations(self):
        audit = AuditLog()
        rules = [
            _make_rule("R1", "No harm", Severity.MEDIUM, keywords=["harm"]),
        ]
        engine = _make_engine(rules=rules, audit_log=audit)
        engine.validate("safe action")
        entry = audit.entries[0]
        assert entry.metadata is not None
        assert "rule_evaluations" in entry.metadata

    def test_violation_audit_includes_matched_rules(self):
        audit = AuditLog()
        rules = [
            _make_rule("R1", "No harm", Severity.MEDIUM, keywords=["harm"]),
            _make_rule("R2", "No leak", Severity.MEDIUM, keywords=["leak"]),
        ]
        engine = _make_engine(rules=rules, audit_log=audit)
        engine.validate("harm and leak data")
        entry = audit.entries[0]
        assert entry.metadata is not None
        evals = entry.metadata.get("rule_evaluations", [])
        matched = [e for e in evals if e.get("matched")]
        assert len(matched) == 2


# ---------------------------------------------------------------------------
# GovernanceEngine — deduplication edge cases
# ---------------------------------------------------------------------------


class TestDeduplication:
    def test_single_violation_no_dedup(self):
        rules = [
            _make_rule("R1", "No bad", Severity.MEDIUM, keywords=["bad"]),
        ]
        engine = _make_engine(rules=rules)
        result = engine.validate("bad action")
        # MEDIUM → WARN → appears in result.warnings, not result.violations
        assert len(result.warnings) == 1

    def test_multiple_keywords_same_rule(self):
        rules = [
            _make_rule("R1", "No bad stuff", Severity.MEDIUM, keywords=["bad", "stuff"]),
        ]
        engine = _make_engine(rules=rules)
        result = engine.validate("bad stuff everywhere")
        # Should deduplicate — same rule_id
        assert all(v.rule_id == "R1" for v in result.violations)


# ---------------------------------------------------------------------------
# GovernanceEngine — pattern matching
# ---------------------------------------------------------------------------


class TestPatternMatching:
    def test_pattern_match_triggers_violation(self):
        rules = [
            _make_rule(
                "R1",
                "No deploy without review",
                Severity.MEDIUM,
                keywords=[],
                patterns=[r"\bdeploy\s+without\s+review\b"],
            ),
        ]
        engine = _make_engine(rules=rules)
        result = engine.validate("deploy without review to production")
        # MEDIUM → WARN → appears in result.warnings, not result.violations
        assert any(v.rule_id == "R1" for v in result.warnings)

    def test_pattern_no_match(self):
        rules = [
            _make_rule(
                "R1",
                "No deploy without review",
                Severity.MEDIUM,
                keywords=[],
                patterns=[r"\bdeploy\s+without\s+review\b"],
            ),
        ]
        engine = _make_engine(rules=rules)
        result = engine.validate("deploy with full review completed")
        assert result.valid is True


# ---------------------------------------------------------------------------
# GovernanceEngine — strict vs non-strict blocking with HIGH
# ---------------------------------------------------------------------------


class TestStrictBlocking:
    def test_strict_high_raises(self):
        rules = [
            _make_rule("R1", "Blocked action", Severity.HIGH, keywords=["blocked"]),
        ]
        audit = AuditLog()
        engine = _make_engine(rules=rules, strict=True, audit_log=audit)
        with pytest.raises(ConstitutionalViolationError):
            engine.validate("blocked action")

    def test_non_strict_high_returns_invalid(self):
        rules = [
            _make_rule("R1", "Blocked", Severity.HIGH, keywords=["blocked"]),
        ]
        engine = _make_engine(rules=rules, strict=False)
        result = engine.validate("blocked action")
        assert result.valid is False
        assert len(result.violations) > 0


# ============================================================================
# Part 2: enhanced_agent_bus opa_client/core.py tests
# ============================================================================


class TestOPAClientCoreInit:
    def test_default_init(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        assert client.opa_url == "http://localhost:8181"
        assert client.mode == "http"
        assert client.timeout == 5.0
        assert client.cache_ttl == 60
        assert client.enable_cache is True
        assert client.fail_closed is True
        assert client._http_client is None

    def test_url_trailing_slash_stripped(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(opa_url="http://localhost:8181/")
        assert client.opa_url == "http://localhost:8181"

    def test_invalid_cache_hash_mode(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        with pytest.raises(ValueError, match="Invalid cache_hash_mode"):
            OPAClientCore(cache_hash_mode="invalid")  # type: ignore[arg-type]

    def test_embedded_mode_falls_back_when_sdk_unavailable(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        with patch("enhanced_agent_bus.opa_client.core._opa_sdk_available", return_value=False):
            client = OPAClientCore(mode="embedded")
            assert client.mode == "http"

    def test_embedded_mode_stays_when_sdk_available(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        with patch("enhanced_agent_bus.opa_client.core._opa_sdk_available", return_value=True):
            client = OPAClientCore(mode="embedded")
            assert client.mode == "embedded"

    def test_fast_hash_mode_warns_when_unavailable(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        with patch("enhanced_agent_bus.opa_client.core.FAST_HASH_AVAILABLE", False):
            # Should not raise, just warn
            client = OPAClientCore(cache_hash_mode="fast")
            assert client.cache_hash_mode == "fast"


class TestOPAClientCoreGetStats:
    def test_stats_default(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        stats = client.get_stats()
        assert stats["mode"] == "http"
        assert stats["cache_enabled"] is True
        assert stats["cache_size"] == 0
        assert stats["cache_backend"] == "memory"
        assert stats["fail_closed"] is True

    def test_stats_cache_disabled(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(enable_cache=False)
        stats = client.get_stats()
        assert stats["cache_backend"] == "disabled"

    def test_stats_redis_backend(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        client._redis_client = MagicMock()
        stats = client.get_stats()
        assert stats["cache_backend"] == "redis"


class TestOPAClientCoreContextManager:
    async def test_aenter_aexit(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        with (
            patch.object(client, "initialize", new_callable=AsyncMock) as mock_init,
            patch.object(client, "close", new_callable=AsyncMock) as mock_close,
        ):
            async with client as c:
                assert c is client
                mock_init.assert_awaited_once()
            mock_close.assert_awaited_once()


class TestOPAClientCoreInitialize:
    async def test_initialize_http_mode(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(mode="http", enable_cache=False)
        with patch.object(client, "_ensure_http_client", new_callable=AsyncMock) as mock:
            await client.initialize()
            mock.assert_awaited_once()

    async def test_initialize_fallback_mode(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(mode="fallback", enable_cache=False)
        with patch.object(client, "_ensure_http_client", new_callable=AsyncMock) as mock:
            await client.initialize()
            mock.assert_awaited_once()

    async def test_initialize_embedded_mode(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore.__new__(OPAClientCore)
        client.mode = "embedded"
        client.opa_url = "http://localhost:8181"
        client.enable_cache = False
        client._http_client = None
        with (
            patch("enhanced_agent_bus.opa_client.core._opa_sdk_available", return_value=True),
            patch.object(client, "_initialize_embedded_opa", new_callable=AsyncMock) as mock,
        ):
            await client.initialize()
            mock.assert_awaited_once()

    async def test_initialize_with_redis(self):
        from enhanced_agent_bus.opa_client.core import OPAClient

        client = OPAClient(mode="http", enable_cache=True)
        with (
            patch.object(client, "_ensure_http_client", new_callable=AsyncMock),
            patch(
                "enhanced_agent_bus.opa_client.core._redis_client_available",
                return_value=True,
            ),
            patch.object(client, "_initialize_redis_cache", new_callable=AsyncMock) as mock_redis,
        ):
            await client.initialize()
            mock_redis.assert_awaited_once()


class TestOPAClientCoreSSL:
    def test_no_ssl_for_http(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(opa_url="http://localhost:8181")
        result = client._build_ssl_context_if_needed()
        assert result is None

    def test_ssl_context_for_https(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(opa_url="https://opa.example.com")
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            ctx = client._build_ssl_context_if_needed()
            assert ctx is not None

    def test_ssl_verify_disabled_in_production_raises(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(opa_url="https://opa.example.com", ssl_verify=False)
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
            with pytest.raises(Exception, match="SSL verification cannot be disabled"):
                client._build_ssl_context_if_needed()

    def test_ssl_verify_disabled_in_dev(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(opa_url="https://opa.example.com", ssl_verify=False)
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            ctx = client._build_ssl_context_if_needed()
            assert ctx is not None

    def test_ssl_with_cert_and_key(self):
        import ssl
        import tempfile

        from enhanced_agent_bus.opa_client.core import OPAClientCore

        # Create temp cert/key files
        with (
            tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as cert_f,
            tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as key_f,
        ):
            cert_path = cert_f.name
            key_path = key_f.name

        try:
            client = OPAClientCore(
                opa_url="https://opa.example.com",
                ssl_cert=cert_path,
                ssl_key=key_path,
            )
            with (
                patch.dict(os.environ, {"ENVIRONMENT": "development"}),
                patch.object(ssl.SSLContext, "load_cert_chain"),
            ):
                ctx = client._build_ssl_context_if_needed()
                assert ctx is not None
        finally:
            os.unlink(cert_path)
            os.unlink(key_path)


class TestOPAClientCoreClose:
    async def test_close_http_client(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        mock_http = AsyncMock()
        client._http_client = mock_http
        await client.close()
        mock_http.aclose.assert_awaited_once()
        assert client._http_client is None

    async def test_close_redis_client(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        mock_redis = AsyncMock()
        client._redis_client = mock_redis
        await client.close()
        mock_redis.close.assert_awaited_once()
        assert client._redis_client is None

    async def test_close_clears_caches(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        client._memory_cache["key"] = {"val": 1}
        client._memory_cache_timestamps["key"] = 123.0
        client._embedded_opa = MagicMock()
        await client.close()
        assert len(client._memory_cache) == 0
        assert len(client._memory_cache_timestamps) == 0
        assert client._embedded_opa is None

    async def test_close_http_event_loop_closed(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        mock_http = AsyncMock()
        mock_http.aclose.side_effect = RuntimeError("Event loop is closed")
        client._http_client = mock_http
        await client.close()
        assert client._http_client is None

    async def test_close_http_other_runtime_error(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        mock_http = AsyncMock()
        mock_http.aclose.side_effect = RuntimeError("Something else")
        client._http_client = mock_http
        with pytest.raises(RuntimeError, match="Something else"):
            await client.close()

    async def test_close_redis_event_loop_closed(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        mock_redis = AsyncMock()
        mock_redis.close.side_effect = RuntimeError("Event loop is closed")
        client._redis_client = mock_redis
        await client.close()
        assert client._redis_client is None

    async def test_close_redis_other_runtime_error(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        mock_redis = AsyncMock()
        mock_redis.close.side_effect = RuntimeError("Other error")
        client._redis_client = mock_redis
        with pytest.raises(RuntimeError, match="Other error"):
            await client.close()


class TestOPAClientCoreValidatePolicyPath:
    def test_valid_path(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        # Should not raise
        client._validate_policy_path("data.acgs.allow")

    def test_invalid_characters(self):
        from enhanced_agent_bus._compat.errors import ValidationError as ACGSValidationError
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        with pytest.raises(ACGSValidationError, match="Invalid policy path"):
            client._validate_policy_path("data/../etc/passwd")

    def test_path_traversal(self):
        from enhanced_agent_bus._compat.errors import ValidationError as ACGSValidationError
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        with pytest.raises(ACGSValidationError, match="Path traversal"):
            client._validate_policy_path("data..acgs..allow")

    def test_special_chars_rejected(self):
        from enhanced_agent_bus._compat.errors import ValidationError as ACGSValidationError
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        with pytest.raises(ACGSValidationError):
            client._validate_policy_path("data/acgs/allow")


class TestOPAClientCoreValidateInputData:
    def test_normal_input(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        # Should not raise
        client._validate_input_data({"key": "value"})

    def test_oversized_input(self):
        from enhanced_agent_bus._compat.errors import ValidationError as ACGSValidationError
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        # Create input that exceeds 512KB
        big_input = {"data": "x" * (1024 * 600)}
        with pytest.raises(ACGSValidationError, match="exceeds maximum"):
            client._validate_input_data(big_input)


class TestEstimateInputSize:
    def test_simple_dict(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        size = client._estimate_input_size_bytes({"key": "value"})
        assert size > 0

    def test_nested_dict(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        data = {"a": {"b": {"c": "deep"}}}
        size = client._estimate_input_size_bytes(data)
        assert size > 0

    def test_list_input(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        size = client._estimate_input_size_bytes([1, 2, 3])
        assert size > 0

    def test_circular_reference(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        d: dict[str, Any] = {}
        d["self"] = d
        # Should handle without infinite recursion
        size = client._estimate_input_size_bytes(d)
        assert size > 0

    def test_tuple_and_set(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        size = client._estimate_input_size_bytes((1, 2, frozenset([3, 4])))
        assert size > 0


class TestOPAClientCoreDispatchEvaluation:
    async def test_dispatch_http(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore(mode="http")
        with patch.object(
            client, "_evaluate_http", new_callable=AsyncMock, return_value={"result": True}
        ) as mock:
            result = await client._dispatch_evaluation({"input": "data"}, "data.acgs.allow")
            mock.assert_awaited_once()
            assert result == {"result": True}

    async def test_dispatch_embedded(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore.__new__(OPAClientCore)
        client.mode = "embedded"
        with patch.object(
            client, "_evaluate_embedded", new_callable=AsyncMock, return_value={"result": True}
        ) as mock:
            result = await client._dispatch_evaluation({}, "data.acgs.allow")
            mock.assert_awaited_once()

    async def test_dispatch_fallback(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore.__new__(OPAClientCore)
        client.mode = "fallback"
        with patch.object(
            client, "_evaluate_fallback", new_callable=AsyncMock, return_value={"result": False}
        ) as mock:
            result = await client._dispatch_evaluation({}, "data.acgs.allow")
            mock.assert_awaited_once()


class TestOPAClientCoreFormatResult:
    def test_bool_true(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        result = client._format_evaluation_result(True, "http", "data.acgs.allow")
        assert result["result"] is True
        assert result["allowed"] is True
        assert result["metadata"]["mode"] == "http"

    def test_bool_false(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        result = client._format_evaluation_result(False, "http", "data.acgs.allow")
        assert result["result"] is False
        assert result["allowed"] is False

    def test_dict_result_with_allow(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        opa_result = {"allow": True, "reason": "Permitted", "metadata": {"extra": "info"}}
        result = client._format_evaluation_result(opa_result, "embedded", "data.acgs.allow")
        assert result["allowed"] is True
        assert result["reason"] == "Permitted"
        assert result["metadata"]["extra"] == "info"

    def test_dict_result_without_allow(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        opa_result = {"some_key": "val"}
        result = client._format_evaluation_result(opa_result, "http", "path")
        assert result["allowed"] is False

    def test_unexpected_type(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        result = client._format_evaluation_result(42, "http", "data.acgs.allow")
        assert result["result"] is False
        assert result["allowed"] is False
        assert "Unexpected result type" in result["reason"]


class TestOPAClientCoreHandleError:
    def test_handle_evaluation_error(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        with patch.object(client, "_sanitize_error", return_value="sanitized msg"):
            result = client._handle_evaluation_error(RuntimeError("test"), "data.acgs.allow")
            assert result["result"] is False
            assert result["allowed"] is False
            assert result["metadata"]["security"] == "fail-closed"
            assert result["metadata"]["policy_path"] == "data.acgs.allow"


class TestOPAClientCoreEvaluatePolicy:
    async def test_evaluate_policy_cached(self):
        from enhanced_agent_bus.opa_client.core import OPAClient

        client = OPAClient()
        cached = {"result": True, "allowed": True, "reason": "cached"}
        with (
            patch.object(client, "_generate_cache_key", return_value="key"),
            patch.object(client, "_get_from_cache", new_callable=AsyncMock, return_value=cached),
            patch.object(
                client,
                "_is_multi_path_candidate_generation_enabled",
                return_value=False,
            ),
        ):
            result = await client.evaluate_policy({"input": "data"})
            assert result == cached

    async def test_evaluate_policy_cache_miss(self):
        from enhanced_agent_bus.opa_client.core import OPAClient

        client = OPAClient()
        eval_result = {"result": True, "allowed": True, "reason": "ok"}
        with (
            patch.object(client, "_generate_cache_key", return_value="key"),
            patch.object(client, "_get_from_cache", new_callable=AsyncMock, return_value=None),
            patch.object(client, "_validate_policy_path"),
            patch.object(client, "_validate_input_data"),
            patch.object(
                client, "_dispatch_evaluation", new_callable=AsyncMock, return_value=eval_result
            ),
            patch.object(client, "_set_to_cache", new_callable=AsyncMock),
            patch.object(
                client,
                "_is_multi_path_candidate_generation_enabled",
                return_value=False,
            ),
        ):
            result = await client.evaluate_policy({"input": "data"})
            assert result["allowed"] is True

    async def test_evaluate_policy_validation_error(self):
        from enhanced_agent_bus._compat.errors import ValidationError as ACGSValidationError
        from enhanced_agent_bus.opa_client.core import OPAClient

        client = OPAClient()
        with (
            patch.object(client, "_generate_cache_key", return_value="key"),
            patch.object(client, "_get_from_cache", new_callable=AsyncMock, return_value=None),
            patch.object(
                client,
                "_validate_policy_path",
                side_effect=ACGSValidationError("bad path", field="f"),
            ),
            patch.object(client, "_sanitize_error", return_value="err"),
            patch.object(
                client,
                "_is_multi_path_candidate_generation_enabled",
                return_value=False,
            ),
        ):
            result = await client.evaluate_policy({"input": "data"})
            assert result["allowed"] is False
            assert result["metadata"]["security"] == "fail-closed"

    async def test_evaluate_policy_connection_error(self):
        from httpx import ConnectError as HTTPConnectError

        from enhanced_agent_bus.opa_client.core import OPAClient

        client = OPAClient()
        with (
            patch.object(client, "_generate_cache_key", return_value="key"),
            patch.object(client, "_get_from_cache", new_callable=AsyncMock, return_value=None),
            patch.object(client, "_validate_policy_path"),
            patch.object(client, "_validate_input_data"),
            patch.object(
                client,
                "_dispatch_evaluation",
                new_callable=AsyncMock,
                side_effect=HTTPConnectError("conn failed"),
            ),
            patch.object(client, "_sanitize_error", return_value="err"),
            patch.object(
                client,
                "_is_multi_path_candidate_generation_enabled",
                return_value=False,
            ),
        ):
            result = await client.evaluate_policy({"input": "data"})
            assert result["allowed"] is False

    async def test_evaluate_policy_with_support_set_candidates(self):
        from enhanced_agent_bus.opa_client.core import OPAClient

        client = OPAClient()
        multi_result = {"result": True, "allowed": True, "reason": "multi"}
        with (
            patch.object(
                client,
                "_is_multi_path_candidate_generation_enabled",
                return_value=False,
            ),
            patch.object(client, "_generate_cache_key", return_value="key"),
            patch.object(client, "_get_from_cache", new_callable=AsyncMock, return_value=None),
            patch.object(client, "_validate_policy_path"),
            patch.object(client, "_validate_input_data"),
            patch.object(
                client,
                "evaluate_policy_multi_path",
                new_callable=AsyncMock,
                return_value=multi_result,
            ),
            patch.object(client, "_set_to_cache", new_callable=AsyncMock),
        ):
            input_data = {"input": "data", "support_set_candidates": [{"a": 1}]}
            result = await client.evaluate_policy(input_data)
            assert result == multi_result


class TestOPAClientCoreEvaluateHTTP:
    async def test_evaluate_http_success(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        mock_response = MagicMock()
        mock_response.json.return_value = {"result": True}
        mock_response.raise_for_status = MagicMock()
        mock_http = AsyncMock()
        mock_http.post.return_value = mock_response
        client._http_client = mock_http

        result = await client._evaluate_http({"key": "val"}, "data.acgs.allow")
        assert result["allowed"] is True

    async def test_evaluate_http_not_initialized(self):
        from enhanced_agent_bus.exceptions import OPANotInitializedError
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        client._http_client = None
        with pytest.raises(OPANotInitializedError, match="HTTP policy evaluation"):
            await client._evaluate_http({}, "data.acgs.allow")

    async def test_evaluate_http_connect_error(self):
        from httpx import ConnectError as HTTPConnectError

        from enhanced_agent_bus.exceptions import OPAConnectionError
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        mock_http = AsyncMock()
        mock_http.post.side_effect = HTTPConnectError("refused")
        client._http_client = mock_http
        with patch.object(client, "_sanitize_error", return_value="err"):
            with pytest.raises(OPAConnectionError):
                await client._evaluate_http({}, "data.acgs.allow")

    async def test_evaluate_http_timeout(self):
        from httpx import TimeoutException as HTTPTimeoutException

        from enhanced_agent_bus.exceptions import OPAConnectionError
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        mock_http = AsyncMock()
        mock_http.post.side_effect = HTTPTimeoutException("timeout")
        client._http_client = mock_http
        with patch.object(client, "_sanitize_error", return_value="err"):
            with pytest.raises(OPAConnectionError):
                await client._evaluate_http({}, "data.acgs.allow")

    async def test_evaluate_http_status_error(self):
        import httpx

        from enhanced_agent_bus.exceptions import PolicyEvaluationError
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        mock_http = AsyncMock()
        mock_request = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_http.post.side_effect = httpx.HTTPStatusError(
            "error", request=mock_request, response=mock_response
        )
        client._http_client = mock_http
        with patch.object(client, "_sanitize_error", return_value="err"):
            with pytest.raises(PolicyEvaluationError):
                await client._evaluate_http({}, "data.acgs.allow")

    async def test_evaluate_http_json_decode_error(self):
        import json

        from enhanced_agent_bus.exceptions import PolicyEvaluationError
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.side_effect = json.JSONDecodeError("err", "", 0)
        mock_http = AsyncMock()
        mock_http.post.return_value = mock_response
        client._http_client = mock_http
        with pytest.raises(PolicyEvaluationError):
            await client._evaluate_http({}, "data.acgs.allow")


class TestOPAClientCoreEvaluateEmbedded:
    async def test_not_initialized(self):
        from enhanced_agent_bus.exceptions import OPANotInitializedError
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore.__new__(OPAClientCore)
        client._embedded_opa = None
        with pytest.raises(OPANotInitializedError, match="embedded policy evaluation"):
            await client._evaluate_embedded({}, "data.acgs.allow")

    async def test_success(self):
        from enhanced_agent_bus.exceptions import PolicyEvaluationError
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore.__new__(OPAClientCore)
        client.opa_url = "http://localhost:8181"
        mock_opa = MagicMock()
        mock_opa.evaluate.return_value = True
        client._embedded_opa = mock_opa

        result = await client._evaluate_embedded({"key": "val"}, "data.acgs.allow")
        assert result["allowed"] is True

    async def test_runtime_error(self):
        from enhanced_agent_bus.exceptions import PolicyEvaluationError
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore.__new__(OPAClientCore)
        client.opa_url = "http://localhost:8181"
        mock_opa = MagicMock()
        mock_opa.evaluate.side_effect = RuntimeError("crash")
        client._embedded_opa = mock_opa
        with patch.object(client, "_sanitize_error", return_value="err"):
            with pytest.raises(PolicyEvaluationError):
                await client._evaluate_embedded({}, "data.acgs.allow")

    async def test_type_error(self):
        from enhanced_agent_bus.exceptions import PolicyEvaluationError
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore.__new__(OPAClientCore)
        client.opa_url = "http://localhost:8181"
        mock_opa = MagicMock()
        mock_opa.evaluate.side_effect = TypeError("bad type")
        client._embedded_opa = mock_opa
        with pytest.raises(PolicyEvaluationError):
            await client._evaluate_embedded({}, "data.acgs.allow")


class TestOPAClientCoreEvaluateFallback:
    async def test_invalid_hash(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        result = await client._evaluate_fallback(
            {"constitutional_hash": "wrong_hash"}, "data.acgs.allow"
        )
        assert result["allowed"] is False
        assert "Invalid constitutional hash" in result["reason"]

    async def test_valid_hash_still_denied(self):
        from enhanced_agent_bus.opa_client.core import CONSTITUTIONAL_HASH, OPAClientCore

        client = OPAClientCore()
        result = await client._evaluate_fallback(
            {"constitutional_hash": CONSTITUTIONAL_HASH}, "data.acgs.allow"
        )
        assert result["allowed"] is False
        assert "fail-closed" in result["reason"]
        assert result["metadata"]["security"] == "fail-closed"


class TestOPAClientCoreValidateConstitutional:
    async def test_success_allowed(self):
        from enhanced_agent_bus.opa_client.core import OPAClient

        client = OPAClient()
        eval_result = {
            "allowed": True,
            "reason": "ok",
            "metadata": {"mode": "http"},
        }
        with (
            patch.object(
                client, "evaluate_policy", new_callable=AsyncMock, return_value=eval_result
            ),
            patch.object(
                client,
                "_is_multi_path_candidate_generation_enabled",
                return_value=False,
            ),
        ):
            result = await client.validate_constitutional({"content": "test"})
            assert result.is_valid is True

    async def test_denied(self):
        from enhanced_agent_bus.opa_client.core import OPAClient

        client = OPAClient()
        eval_result = {
            "allowed": False,
            "reason": "Denied by policy",
            "metadata": {},
        }
        with (
            patch.object(
                client, "evaluate_policy", new_callable=AsyncMock, return_value=eval_result
            ),
            patch.object(
                client,
                "_is_multi_path_candidate_generation_enabled",
                return_value=False,
            ),
        ):
            result = await client.validate_constitutional({"content": "bad"})
            assert result.is_valid is False

    async def test_opa_connection_error(self):
        from enhanced_agent_bus.exceptions import OPAConnectionError
        from enhanced_agent_bus.opa_client.core import OPAClient

        client = OPAClient()
        with (
            patch.object(
                client,
                "evaluate_policy",
                new_callable=AsyncMock,
                side_effect=OPAConnectionError("host", "msg"),
            ),
            patch.object(
                client,
                "_is_multi_path_candidate_generation_enabled",
                return_value=False,
            ),
        ):
            result = await client.validate_constitutional({"content": "test"})
            assert result.is_valid is False

    async def test_http_error(self):
        from httpx import ConnectError as HTTPConnectError

        from enhanced_agent_bus.opa_client.core import OPAClient

        client = OPAClient()
        with (
            patch.object(
                client,
                "evaluate_policy",
                new_callable=AsyncMock,
                side_effect=HTTPConnectError("conn failed"),
            ),
            patch.object(
                client,
                "_is_multi_path_candidate_generation_enabled",
                return_value=False,
            ),
        ):
            result = await client.validate_constitutional({"content": "test"})
            assert result.is_valid is False

    async def test_value_error(self):
        from enhanced_agent_bus.opa_client.core import OPAClient

        client = OPAClient()
        with (
            patch.object(
                client,
                "evaluate_policy",
                new_callable=AsyncMock,
                side_effect=ValueError("bad value"),
            ),
            patch.object(
                client,
                "_is_multi_path_candidate_generation_enabled",
                return_value=False,
            ),
        ):
            result = await client.validate_constitutional({"content": "test"})
            assert result.is_valid is False


class TestOPAClientCoreCheckAuthorization:
    async def test_authorized(self):
        from enhanced_agent_bus.opa_client.core import CONSTITUTIONAL_HASH, OPAClient

        client = OPAClient()
        eval_result = {"allowed": True, "reason": "ok", "metadata": {}}
        with (
            patch.object(
                client, "evaluate_policy", new_callable=AsyncMock, return_value=eval_result
            ),
            patch.object(
                client,
                "_is_multi_path_candidate_generation_enabled",
                return_value=False,
            ),
        ):
            result = await client.check_agent_authorization(
                "agent1",
                "read",
                "resource1",
                context={"constitutional_hash": CONSTITUTIONAL_HASH},
            )
            assert result is True

    async def test_wrong_hash(self):
        from enhanced_agent_bus.opa_client.core import OPAClient

        client = OPAClient()
        result = await client.check_agent_authorization(
            "agent1",
            "read",
            "resource1",
            context={"constitutional_hash": "wrong_hash"},
        )
        assert result is False

    async def test_no_context(self):
        from enhanced_agent_bus.opa_client.core import OPAClient

        client = OPAClient()
        eval_result = {"allowed": True, "reason": "ok", "metadata": {}}
        with (
            patch.object(
                client, "evaluate_policy", new_callable=AsyncMock, return_value=eval_result
            ),
            patch.object(
                client,
                "_is_multi_path_candidate_generation_enabled",
                return_value=False,
            ),
        ):
            result = await client.check_agent_authorization("agent1", "read", "resource1")
            assert result is True

    async def test_opa_error_returns_false(self):
        from enhanced_agent_bus.exceptions import OPAConnectionError
        from enhanced_agent_bus.opa_client.core import OPAClient

        client = OPAClient()
        with (
            patch.object(
                client,
                "evaluate_policy",
                new_callable=AsyncMock,
                side_effect=OPAConnectionError("host", "msg"),
            ),
            patch.object(
                client,
                "_is_multi_path_candidate_generation_enabled",
                return_value=False,
            ),
        ):
            result = await client.check_agent_authorization("agent1", "read", "resource1")
            assert result is False

    async def test_value_error_returns_false(self):
        from enhanced_agent_bus.opa_client.core import OPAClient

        client = OPAClient()
        with (
            patch.object(
                client,
                "evaluate_policy",
                new_callable=AsyncMock,
                side_effect=ValueError("bad"),
            ),
            patch.object(
                client,
                "_is_multi_path_candidate_generation_enabled",
                return_value=False,
            ),
        ):
            result = await client.check_agent_authorization("agent1", "read", "resource1")
            assert result is False


class TestOPAClientCoreLoadPolicy:
    async def test_load_policy_success(self):
        from enhanced_agent_bus.opa_client.core import OPAClient

        client = OPAClient(mode="http")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_http = AsyncMock()
        mock_http.put.return_value = mock_response
        client._http_client = mock_http
        with patch.object(client, "clear_cache", new_callable=AsyncMock):
            result = await client.load_policy("policy1", "package test")
            assert result is True

    async def test_load_policy_not_http_mode(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore.__new__(OPAClientCore)
        client.mode = "embedded"
        client._http_client = None
        result = await client.load_policy("policy1", "package test")
        assert result is False

    async def test_load_policy_no_client(self):
        from enhanced_agent_bus.opa_client.core import OPAClient

        client = OPAClient(mode="http")
        client._http_client = None
        result = await client.load_policy("policy1", "package test")
        assert result is False

    async def test_load_policy_connect_error(self):
        from httpx import ConnectError as HTTPConnectError

        from enhanced_agent_bus.opa_client.core import OPAClient

        client = OPAClient(mode="http")
        mock_http = AsyncMock()
        mock_http.put.side_effect = HTTPConnectError("refused")
        client._http_client = mock_http
        result = await client.load_policy("policy1", "package test")
        assert result is False

    async def test_load_policy_timeout(self):
        from httpx import TimeoutException as HTTPTimeoutException

        from enhanced_agent_bus.opa_client.core import OPAClient

        client = OPAClient(mode="http")
        mock_http = AsyncMock()
        mock_http.put.side_effect = HTTPTimeoutException("timeout")
        client._http_client = mock_http
        result = await client.load_policy("policy1", "package test")
        assert result is False

    async def test_load_policy_runtime_error(self):
        from enhanced_agent_bus.opa_client.core import OPAClient

        client = OPAClient(mode="http")
        mock_http = AsyncMock()
        mock_http.put.side_effect = RuntimeError("unexpected")
        client._http_client = mock_http
        result = await client.load_policy("policy1", "package test")
        assert result is False


class TestOPAClientCoreEvaluateWithHistory:
    async def test_basic_evaluate_with_history(self):
        from enhanced_agent_bus.opa_client.core import OPAClient

        client = OPAClient(mode="http")
        eval_result = {"allowed": True, "result": True, "reason": "ok", "metadata": {}}
        with (
            patch.object(client, "_validate_policy_path"),
            patch.object(client, "_validate_input_data"),
            patch.object(
                client, "_evaluate_http", new_callable=AsyncMock, return_value=eval_result
            ),
            patch.object(client, "_is_temporal_multi_path_enabled", return_value=False),
        ):
            result = await client.evaluate_with_history({"action": "test"}, ["step1", "step2"])
            assert result["allowed"] is True

    async def test_evaluate_with_history_error(self):
        from httpx import ConnectError as HTTPConnectError

        from enhanced_agent_bus.opa_client.core import OPAClient

        client = OPAClient(mode="http")
        with (
            patch.object(client, "_validate_policy_path"),
            patch.object(client, "_validate_input_data"),
            patch.object(
                client,
                "_evaluate_http",
                new_callable=AsyncMock,
                side_effect=HTTPConnectError("fail"),
            ),
            patch.object(client, "_sanitize_error", return_value="err"),
            patch.object(client, "_is_temporal_multi_path_enabled", return_value=False),
        ):
            result = await client.evaluate_with_history({"action": "test"}, ["step1"])
            assert result["allowed"] is False


class TestOPAClientCoreInitializeEmbedded:
    async def test_initialize_embedded_success(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore.__new__(OPAClientCore)
        client.opa_url = "http://localhost:8181"
        client.mode = "embedded"
        client._http_client = None
        client._embedded_opa = None

        mock_cls = MagicMock()
        with patch(
            "enhanced_agent_bus.opa_client.core._get_embedded_opa_class",
            return_value=mock_cls,
        ):
            await client._initialize_embedded_opa()
            assert client._embedded_opa is not None

    async def test_initialize_embedded_failure(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore.__new__(OPAClientCore)
        client.opa_url = "http://localhost:8181"
        client.mode = "embedded"
        client._http_client = None
        client._embedded_opa = None
        client.ssl_verify = True
        client.ssl_cert = None
        client.ssl_key = None
        client.timeout = 5.0

        mock_cls = MagicMock(side_effect=RuntimeError("OPA init failed"))
        with patch(
            "enhanced_agent_bus.opa_client.core._get_embedded_opa_class",
            return_value=mock_cls,
        ):
            await client._initialize_embedded_opa()
            assert client.mode == "http"


class TestOPAClientCoreRollback:
    async def test_rollback_with_lkg(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        with patch("os.path.exists", return_value=True):
            result = await client._rollback_to_lkg()
            assert result is True

    async def test_rollback_no_lkg(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        with patch("os.path.exists", return_value=False):
            result = await client._rollback_to_lkg()
            assert result is False


class TestOPAClientCoreVerifyBundle:
    async def test_verify_bundle_import_error(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        with patch.dict(sys.modules, {"app.services.crypto_service": None}):
            result = await client._verify_bundle("fake/path", "sig", "key")
            assert result is False

    async def test_verify_bundle_file_not_found(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        result = await client._verify_bundle("/nonexistent/bundle.tar.gz", "sig", "key")
        assert result is False


class TestOPAClientCoreLoadBundle:
    async def test_load_bundle_connect_error(self):
        from httpx import ConnectError as HTTPConnectError

        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        mock_http = AsyncMock()
        mock_http.get.side_effect = HTTPConnectError("refused")
        client._http_client = mock_http
        with patch.object(client, "_rollback_to_lkg", new_callable=AsyncMock, return_value=False):
            result = await client.load_bundle_from_url(
                "http://example.com/bundle.tar.gz", "sig", "key"
            )
            assert result is False

    async def test_load_bundle_os_error(self):
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        client = OPAClientCore()
        mock_http = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = b"bundle data"
        mock_response.raise_for_status = MagicMock()
        mock_http.get.return_value = mock_response
        client._http_client = mock_http
        with (
            patch("os.makedirs", side_effect=OSError("disk full")),
            patch.object(client, "_rollback_to_lkg", new_callable=AsyncMock, return_value=False),
        ):
            result = await client.load_bundle_from_url(
                "http://example.com/bundle.tar.gz", "sig", "key"
            )
            assert result is False


# ---------------------------------------------------------------------------
# Singleton lifecycle helpers
# ---------------------------------------------------------------------------


class TestSingletonLifecycle:
    async def test_initialize_get_close(self):
        import enhanced_agent_bus.opa_client.core as opa_core

        original = opa_core._opa_client
        try:
            opa_core._opa_client = None
            with patch.object(opa_core.OPAClient, "initialize", new_callable=AsyncMock):
                client = await opa_core.initialize_opa_client()
                assert client is not None
                assert opa_core.get_opa_client() is client

                # Second call returns same instance
                client2 = await opa_core.initialize_opa_client()
                assert client2 is client

                with patch.object(client, "close", new_callable=AsyncMock):
                    await opa_core.close_opa_client()
                assert opa_core._opa_client is None
        finally:
            opa_core._opa_client = original

    async def test_get_opa_client_not_initialized(self):
        import enhanced_agent_bus.opa_client.core as opa_core

        original = opa_core._opa_client
        try:
            opa_core._opa_client = None
            with pytest.raises(Exception, match="get_opa_client"):
                opa_core.get_opa_client()
        finally:
            opa_core._opa_client = original

    async def test_close_when_none(self):
        import enhanced_agent_bus.opa_client.core as opa_core

        original = opa_core._opa_client
        try:
            opa_core._opa_client = None
            await opa_core.close_opa_client()  # Should not raise
            assert opa_core._opa_client is None
        finally:
            opa_core._opa_client = original


# ---------------------------------------------------------------------------
# Helper functions at module level
# ---------------------------------------------------------------------------


class TestModuleLevelHelpers:
    def test_opa_sdk_available_from_package(self):
        from enhanced_agent_bus.opa_client.core import _opa_sdk_available

        result = _opa_sdk_available()
        assert isinstance(result, bool)

    def test_get_embedded_opa_class(self):
        from enhanced_agent_bus.opa_client.core import _get_embedded_opa_class

        result = _get_embedded_opa_class()
        # Either None (no SDK) or a class
        assert result is None or isinstance(result, type)


class TestOPAClientComposed:
    def test_opa_client_is_composed(self):
        from enhanced_agent_bus.opa_client.cache import OPAClientCacheMixin
        from enhanced_agent_bus.opa_client.core import OPAClient, OPAClientCore
        from enhanced_agent_bus.opa_client.health import OPAClientHealthMixin

        assert issubclass(OPAClient, OPAClientCore)
        assert issubclass(OPAClient, OPAClientCacheMixin)
        assert issubclass(OPAClient, OPAClientHealthMixin)

    def test_opa_client_instantiation(self):
        from enhanced_agent_bus.opa_client.core import OPAClient

        client = OPAClient()
        assert client.opa_url == "http://localhost:8181"
        assert client.fail_closed is True
