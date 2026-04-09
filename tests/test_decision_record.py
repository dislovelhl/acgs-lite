"""Tests for GovernanceDecisionRecord and conversion methods."""

from __future__ import annotations

from acgs_lite.constitution import Severity
from acgs_lite.engine.decision_record import GovernanceDecisionRecord, TriggeredRule
from acgs_lite.engine.models import ValidationResult, Violation


class TestGovernanceDecisionRecord:
    def test_basic_construction(self):
        record = GovernanceDecisionRecord(decision="allow", constitutional_hash="abc123")
        assert record.decision == "allow"
        assert record.triggered_rules == []
        assert record.confidence == 1.0
        assert record.model_id == "deterministic"

    def test_dict_protocol_decision(self):
        record = GovernanceDecisionRecord(decision="deny")
        assert record["decision"] == "deny"

    def test_dict_protocol_triggered_rules(self):
        record = GovernanceDecisionRecord(
            decision="deny",
            triggered_rules=[
                TriggeredRule(id="R1", text="No harm", severity="high", category="safety")
            ],
        )
        rules = record["triggered_rules"]
        assert len(rules) == 1
        assert rules[0]["id"] == "R1"
        assert rules[0]["severity"] == "high"

    def test_get_method(self):
        record = GovernanceDecisionRecord(decision="allow")
        assert record.get("decision") == "allow"
        assert record.get("nonexistent", "default") == "default"

    def test_to_dict(self):
        record = GovernanceDecisionRecord(
            decision="deny",
            triggered_rules=[TriggeredRule(id="R1")],
            confidence=0.95,
            model_id="llm-haiku",
            latency_ms=12.5,
        )
        d = record.to_dict()
        assert d["decision"] == "deny"
        assert len(d["triggered_rules"]) == 1
        assert d["confidence"] == 0.95
        assert d["model_id"] == "llm-haiku"


class TestValidationResultConversion:
    def test_allow_result(self):
        vr = ValidationResult(valid=True, constitutional_hash="608508a9bd224290", rules_checked=10)
        record = vr.to_decision_record()
        assert record.decision == "allow"
        assert record.triggered_rules == []
        assert record.violations == []
        assert record.confidence == 1.0
        assert record.model_id == "deterministic"
        assert record.constitutional_hash == "608508a9bd224290"
        assert record.rules_checked == 10

    def test_deny_result_with_violations(self):
        violations = [
            Violation(
                rule_id="NO-PII",
                rule_text="No PII",
                severity=Severity.CRITICAL,
                matched_content="ssn 123",
                category="privacy",
            ),
            Violation(
                rule_id="NO-HARM",
                rule_text="No harm",
                severity=Severity.HIGH,
                matched_content="malware",
                category="safety",
            ),
        ]
        vr = ValidationResult(
            valid=False,
            constitutional_hash="608508a9bd224290",
            violations=violations,
            rules_checked=15,
            latency_ms=0.42,
            request_id="req-001",
            action="send ssn",
            agent_id="agent-1",
        )
        record = vr.to_decision_record()
        assert record.decision == "deny"
        assert len(record.triggered_rules) == 2
        assert record.triggered_rules[0].id == "NO-PII"
        assert record.triggered_rules[0].severity == "critical"
        assert record.triggered_rules[1].id == "NO-HARM"
        assert len(record.violations) == 2
        assert record.violations[0]["rule_id"] == "NO-PII"
        assert record.latency_ms == 0.42
        assert record.audit_entry_id == "req-001"
        assert record.action == "send ssn"
        assert record.agent_id == "agent-1"

    def test_roundtrip_to_dict(self):
        vr = ValidationResult(
            valid=False,
            constitutional_hash="abc",
            violations=[
                Violation("R1", "text", Severity.HIGH, "match", "cat"),
            ],
        )
        d = vr.to_decision_record().to_dict()
        assert d["decision"] == "deny"
        assert d["triggered_rules"][0]["id"] == "R1"


class TestGovernanceTestSuiteCompat:
    """Verify the record works with GovernanceTestSuite's expected protocol."""

    def test_decision_attribute_access(self):
        record = GovernanceDecisionRecord(decision="allow")
        # Test suite checks .decision or ["decision"]
        assert record.decision == "allow"
        assert record["decision"] == "allow"

    def test_triggered_rules_attribute_access(self):
        record = GovernanceDecisionRecord(
            decision="deny",
            triggered_rules=[TriggeredRule(id="R1"), TriggeredRule(id="R2")],
        )
        # Test suite checks .triggered_rules or ["triggered_rules"]
        assert len(record.triggered_rules) == 2
        rules_via_dict = record["triggered_rules"]
        assert len(rules_via_dict) == 2
        assert rules_via_dict[0]["id"] == "R1"
