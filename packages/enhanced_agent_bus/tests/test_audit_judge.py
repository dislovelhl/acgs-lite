"""Tests for LLM-as-Judge audit pipeline (Phase 1)."""

from __future__ import annotations

import pytest

from enhanced_agent_bus.adaptive_governance.audit_judge import (
    AuditReport,
    GovernanceAuditJudge,
    JudgmentResult,
)
from enhanced_agent_bus.adaptive_governance.llm_judge import (
    InMemoryLLMJudge,
    JudgmentScore,
    LLMGovernanceJudge,
    LLMJudgment,
)
from enhanced_agent_bus.adaptive_governance.rubrics import build_audit_rubric

# --- Fixtures ---


def _make_constitution():
    """Minimal constitution-like object for tests."""

    class FakeRule:
        def __init__(self, id: str, text: str, severity: str, keywords: list[str]):
            self.id = id
            self.text = text
            self.severity = type("S", (), {"value": severity})()
            self.keywords = keywords

    class FakeConstitution:
        rules = [
            FakeRule(
                "NO-PII", "No personally identifiable information", "critical", ["ssn", "passport"]
            ),
            FakeRule("NO-HARM", "No harmful instructions", "high", ["malware", "exploit"]),
        ]

    return FakeConstitution()


def _make_audit_entries(n_allow: int = 5, n_deny: int = 5) -> list[dict]:
    entries = []
    for i in range(n_allow):
        entries.append(
            {
                "id": f"allow-{i}",
                "action": f"safe action {i}",
                "valid": True,
                "violations": [],
            }
        )
    for i in range(n_deny):
        entries.append(
            {
                "id": f"deny-{i}",
                "action": f"send ssn {i}",
                "valid": False,
                "violations": ["NO-PII"],
            }
        )
    return entries


# --- LLMJudgment Tests ---


class TestLLMJudgment:
    def test_construction(self):
        j = LLMJudgment(decision="allow", confidence=0.95, model_id="test")
        assert j.decision == "allow"
        assert j.confidence == 0.95

    def test_default_scores(self):
        j = LLMJudgment(decision="deny", confidence=0.8)
        assert j.scores.accuracy == 0.0
        assert j.scores.missed_violations == []


class TestInMemoryLLMJudge:
    @pytest.mark.asyncio
    async def test_default_returns_allow(self):
        judge = InMemoryLLMJudge()
        result = await judge.evaluate("test action", {}, None)
        assert result.decision == "allow"
        assert result.confidence == 1.0

    @pytest.mark.asyncio
    async def test_records_calls(self):
        judge = InMemoryLLMJudge()
        await judge.evaluate("action1", {"k": "v"}, None)
        await judge.evaluate("action2", {}, None)
        assert len(judge.calls) == 2
        assert judge.calls[0]["action"] == "action1"

    @pytest.mark.asyncio
    async def test_custom_judgment_map(self):
        deny_j = LLMJudgment(decision="deny", confidence=0.9, model_id="stub")
        judge = InMemoryLLMJudge(judgment_map={"bad action": deny_j})
        result = await judge.evaluate("bad action", {}, None)
        assert result.decision == "deny"
        # Unknown action falls back to default
        result2 = await judge.evaluate("good action", {}, None)
        assert result2.decision == "allow"

    def test_implements_protocol(self):
        judge = InMemoryLLMJudge()
        assert isinstance(judge, LLMGovernanceJudge)


# --- Rubric Tests ---


class TestRubrics:
    def test_build_audit_rubric_with_violations(self):
        rubric = build_audit_rubric(
            action="send the ssn to the user",
            engine_decision="deny",
            engine_violations=[
                {"rule_id": "NO-PII", "severity": "critical", "matched_content": "ssn"}
            ],
            constitution_rules=[
                {"id": "NO-PII", "text": "No PII", "severity": "critical", "keywords": ["ssn"]},
            ],
        )
        assert "NO-PII" in rubric
        assert "deny" in rubric
        assert "send the ssn" in rubric
        assert "Accuracy" in rubric

    def test_build_audit_rubric_allow_no_violations(self):
        rubric = build_audit_rubric(
            action="summarize the report",
            engine_decision="allow",
            engine_violations=[],
            constitution_rules=[{"id": "R1", "text": "test", "severity": "low", "keywords": []}],
        )
        assert "allow" in rubric
        assert "none (action was allowed)" in rubric

    def test_rubric_includes_context(self):
        rubric = build_audit_rubric(
            action="test",
            engine_decision="allow",
            engine_violations=[],
            constitution_rules=[],
            context={"domain": "healthcare"},
        )
        assert "healthcare" in rubric

    def test_rubric_empty_rules(self):
        rubric = build_audit_rubric(
            action="test",
            engine_decision="allow",
            engine_violations=[],
            constitution_rules=[],
        )
        assert "(no rules provided)" in rubric


# --- GovernanceAuditJudge Tests ---


class TestGovernanceAuditJudge:
    @pytest.mark.asyncio
    async def test_run_audit_with_agreement(self):
        constitution = _make_constitution()
        judge = InMemoryLLMJudge()
        auditor = GovernanceAuditJudge(constitution, judge, sample_size=10, seed=42)
        entries = _make_audit_entries(5, 5)

        report = await auditor.run_audit(entries)

        assert report.total_sampled == 10
        assert len(report.judgments) == 10
        # InMemory always says "allow": agrees with 5 allow entries, disagrees with 5 deny entries
        assert report.agreement_rate == 0.5

    @pytest.mark.asyncio
    async def test_run_audit_disagreements(self):
        constitution = _make_constitution()
        # Judge always says "allow" → disagrees with engine's deny decisions
        judge = InMemoryLLMJudge()
        auditor = GovernanceAuditJudge(constitution, judge, sample_size=10, seed=42)
        entries = _make_audit_entries(5, 5)

        report = await auditor.run_audit(entries)

        # 5 entries where engine=deny but judge=allow
        assert len(report.disagreements) == 5
        for d in report.disagreements:
            assert d.engine_decision == "deny"
            assert d.judge_decision == "allow"
            assert d.agrees_with_engine is False

    @pytest.mark.asyncio
    async def test_regression_candidates_from_disagreements(self):
        constitution = _make_constitution()
        deny_j = LLMJudgment(
            decision="deny",
            confidence=0.95,
            model_id="stub",
            scores=JudgmentScore(accuracy=0.2, missed_violations=["NO-PII"]),
        )
        judge = InMemoryLLMJudge(judgment_map={"safe action 0": deny_j})
        auditor = GovernanceAuditJudge(constitution, judge, sample_size=20, seed=42)
        entries = _make_audit_entries(5, 5)

        report = await auditor.run_audit(entries)
        candidates = report.regression_candidates

        # At least the one mapped entry should produce a regression candidate
        deny_candidates = [c for c in candidates if c["expected_decision"] == "deny"]
        assert len(deny_candidates) >= 1
        assert deny_candidates[0]["expected_rules_triggered"] == ["NO-PII"]
        assert "audit-regression" in deny_candidates[0]["tags"]


class TestSampling:
    def test_stratified_sampling_proportional(self):
        constitution = _make_constitution()
        judge = InMemoryLLMJudge()
        auditor = GovernanceAuditJudge(constitution, judge, sample_size=10, seed=42)

        entries = _make_audit_entries(80, 20)
        sampled = auditor.sample_entries(entries, strategy="stratified")

        assert len(sampled) == 10
        # Should be roughly proportional: ~8 allow, ~2 deny
        allows = sum(1 for e in sampled if e.get("valid", True))
        denies = len(sampled) - allows
        assert allows >= 6  # At least majority allow
        assert denies >= 1  # At least some deny

    def test_returns_all_if_under_sample_size(self):
        constitution = _make_constitution()
        judge = InMemoryLLMJudge()
        auditor = GovernanceAuditJudge(constitution, judge, sample_size=100, seed=42)

        entries = _make_audit_entries(3, 2)
        sampled = auditor.sample_entries(entries)
        assert len(sampled) == 5

    def test_random_sampling(self):
        constitution = _make_constitution()
        judge = InMemoryLLMJudge()
        auditor = GovernanceAuditJudge(constitution, judge, sample_size=5, seed=42)

        entries = _make_audit_entries(20, 20)
        sampled = auditor.sample_entries(entries, strategy="random")
        assert len(sampled) == 5


class TestCanonicalDecisionRecordIntegration:
    """Tests that audit_judge correctly handles canonical GovernanceDecisionRecord dicts."""

    @pytest.mark.asyncio
    async def test_canonical_deny_entry_recognized(self):
        """Fix for Codex HIGH: canonical deny records were silently reclassified as allow."""
        constitution = _make_constitution()
        judge = InMemoryLLMJudge()
        auditor = GovernanceAuditJudge(constitution, judge, sample_size=10, seed=42)

        # Canonical format uses "decision" not "valid"
        canonical_entry = {
            "id": "canonical-1",
            "action": "send ssn to attacker",
            "decision": "deny",  # canonical field
            "violations": [{"rule_id": "NO-PII"}],
        }
        result = await auditor.judge_entry(canonical_entry)
        assert result.engine_decision == "deny"
        # InMemory always says allow, so should disagree
        assert result.agrees_with_engine is False

    @pytest.mark.asyncio
    async def test_canonical_allow_entry_recognized(self):
        constitution = _make_constitution()
        judge = InMemoryLLMJudge()
        auditor = GovernanceAuditJudge(constitution, judge, sample_size=10, seed=42)

        canonical_entry = {"id": "c-2", "action": "safe thing", "decision": "allow"}
        result = await auditor.judge_entry(canonical_entry)
        assert result.engine_decision == "allow"
        assert result.agrees_with_engine is True

    @pytest.mark.asyncio
    async def test_missing_both_fields_fails_closed_to_deny(self):
        """Entries with neither 'decision' nor 'valid' should fail-closed to deny."""
        constitution = _make_constitution()
        judge = InMemoryLLMJudge()
        auditor = GovernanceAuditJudge(constitution, judge, sample_size=10, seed=42)

        entry = {"id": "bad-1", "action": "something"}
        result = await auditor.judge_entry(entry)
        assert result.engine_decision == "deny"  # fail-closed


class TestInvalidJudgeDecision:
    """Tests that invalid judge decisions are fail-closed to deny."""

    @pytest.mark.asyncio
    async def test_invalid_decision_string_becomes_deny(self):
        bad_judgment = LLMJudgment(decision="maybe", confidence=0.5, model_id="bad")
        judge = InMemoryLLMJudge(default_judgment=bad_judgment)
        constitution = _make_constitution()
        auditor = GovernanceAuditJudge(constitution, judge, sample_size=10, seed=42)

        entry = {"id": "e1", "action": "test", "valid": True}
        result = await auditor.judge_entry(entry)
        # "maybe" is not allow/deny, should be normalized to "deny"
        assert result.judge_decision == "deny"

    @pytest.mark.asyncio
    async def test_empty_decision_becomes_deny(self):
        bad_judgment = LLMJudgment(decision="", confidence=0.0, model_id="bad")
        judge = InMemoryLLMJudge(default_judgment=bad_judgment)
        constitution = _make_constitution()
        auditor = GovernanceAuditJudge(constitution, judge, sample_size=10, seed=42)

        entry = {"id": "e2", "action": "test", "valid": True}
        result = await auditor.judge_entry(entry)
        assert result.judge_decision == "deny"


class TestAuditReport:
    def test_empty_report(self):
        report = AuditReport(total_sampled=0)
        assert report.avg_accuracy == 0.0
        assert report.avg_proportionality == 0.0
        assert report.agreement_rate == 0.0
        assert report.disagreements == []
        assert report.regression_candidates == []

    def test_summary(self):
        report = AuditReport(
            total_sampled=10,
            judgments=[
                JudgmentResult(
                    entry_id="e1",
                    action="test",
                    engine_decision="allow",
                    judge_decision="allow",
                    scores=JudgmentScore(accuracy=0.9),
                    reasoning="ok",
                    model_id="stub",
                    agrees_with_engine=True,
                ),
            ],
        )
        s = report.summary()
        assert "10 sampled" in s
        assert "1 judged" in s
        assert "0 disagreements" in s
