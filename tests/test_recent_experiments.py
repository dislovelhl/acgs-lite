"""Tests for recent governance quality experiments (exp231-234).

Covers: CausalChainTracker, SessionContractTracker, ObligationPredictor,
RefusalReasoningEngine, and the declarative registry + domain classification.
"""

from __future__ import annotations

import pytest

from acgs_lite.constitution import (
    Constitution,
    Rule,
    Severity,
    modules_by_domain,
)


class TestDeclarativeRegistry:
    """P1/P2: Declarative lazy-load registry and domain classification."""

    def test_all_symbols_accessible(self) -> None:
        import acgs_lite.constitution as c

        errors = []
        for name in c.__all__:
            try:
                getattr(c, name)
            except Exception as exc:
                errors.append(f"{name}: {exc}")
        assert not errors, f"{len(errors)} symbols broken: {errors[:5]}"

    def test_unknown_symbol_raises_attribute_error(self) -> None:
        import acgs_lite.constitution as c

        with pytest.raises(AttributeError):
            c.__getattr__("NonExistentSymbol99999")

    def test_modules_by_domain_returns_all_domains(self) -> None:
        domains = modules_by_domain()
        assert "lifecycle" in domains
        assert "enforcement" in domains
        assert "monitoring" in domains
        assert "analysis" in domains

    def test_modules_by_domain_filter(self) -> None:
        lifecycle = modules_by_domain("lifecycle")
        assert "lifecycle" in lifecycle
        assert len(lifecycle) == 1
        assert "amendments" in lifecycle["lifecycle"]

    def test_module_cache_reuses_imports(self) -> None:
        from acgs_lite.constitution import CausalChainTracker, ChainPattern

        assert CausalChainTracker is not None
        assert ChainPattern is not None


class TestCausalChainTracker:
    """exp231: Causal action chain detection."""

    def setup_method(self) -> None:
        from acgs_lite.constitution import CausalChainTracker

        self.tracker = CausalChainTracker.with_builtin_patterns()

    def test_data_exfiltration_chain(self) -> None:
        r1 = self.tracker.record_and_check("agent-1", "read customer database")
        assert not r1.completed
        r2 = self.tracker.record_and_check("agent-1", "export data to external API")
        assert r2.completed
        assert r2.completed[0].pattern_id == "CHAIN-001"
        assert r2.completed[0].severity == "high"

    def test_audit_evasion_chain(self) -> None:
        self.tracker.record_and_check("a2", "suppress logging system")
        r2 = self.tracker.record_and_check("a2", "run sensitive operation")
        assert r2.alerts
        r3 = self.tracker.record_and_check("a2", "resume logging system")
        assert r3.completed
        assert r3.completed[0].pattern_id == "CHAIN-002"
        assert r3.completed[0].severity == "critical"

    def test_gap_exceeded_no_match(self) -> None:
        self.tracker.record_and_check("a3", "read sensitive file")
        for i in range(6):
            self.tracker.record_and_check("a3", f"unrelated action {i}")
        r = self.tracker.record_and_check("a3", "send file via email")
        assert not r.completed

    def test_gap_within_limit_matches(self) -> None:
        self.tracker.record_and_check("a4", "read sensitive file")
        self.tracker.record_and_check("a4", "check permissions")
        self.tracker.record_and_check("a4", "validate input")
        r = self.tracker.record_and_check("a4", "send file via email")
        assert r.completed

    def test_custom_pattern(self) -> None:
        from acgs_lite.constitution import CausalChainTracker, ChainPattern, ChainStep

        custom = ChainPattern(
            id="CUSTOM-001",
            name="Test",
            steps=(
                ChainStep(frozenset({"alpha"}), "a"),
                ChainStep(frozenset({"beta"}), "b"),
            ),
            severity="low",
            description="test",
            max_gap=2,
        )
        t = CausalChainTracker([custom])
        t.record_and_check("x", "do alpha thing")
        r = t.record_and_check("x", "do beta thing")
        assert r.completed
        assert r.completed[0].pattern_id == "CUSTOM-001"

    def test_builtin_patterns_count(self) -> None:
        from acgs_lite.constitution import builtin_patterns

        assert len(builtin_patterns()) == 8

    def test_reset_clears_state(self) -> None:
        self.tracker.record_and_check("a5", "read secret credentials")
        assert self.tracker.active_chains("a5")
        self.tracker.reset_agent("a5")
        assert not self.tracker.active_chains("a5")

    def test_summary(self) -> None:
        self.tracker.record_and_check("a6", "read data")
        self.tracker.record_and_check("a6", "export data")
        s = self.tracker.summary()
        assert s["total_completed"] >= 1

    def test_to_dict(self) -> None:
        self.tracker.record_and_check("a7", "read data")
        r = self.tracker.record_and_check("a7", "export data")
        d = r.to_dict()
        assert "completed" in d
        assert "alerts" in d


class TestSessionContractTracker:
    """exp232: Behavioral session contracts."""

    def setup_method(self) -> None:
        from acgs_lite.constitution import BehaviorContract, SessionContractTracker

        self.contract = BehaviorContract(
            allowed_actions=frozenset({"read", "summarise", "list"}),
            resource_scopes=frozenset({"documents", "calendar"}),
            max_actions=10,
            time_limit_seconds=3600,
        )
        self.tracker = SessionContractTracker()

    def test_contract_hash_auto_computed(self) -> None:
        assert self.contract.contract_hash
        assert len(self.contract.contract_hash) == 64

    def test_contract_integrity_verification(self) -> None:
        assert self.contract.verify_integrity()

    def test_compliant_action(self) -> None:
        self.tracker.bind("a1", self.contract)
        r = self.tracker.check_action("a1", "read quarterly report")
        assert r.is_compliant

    def test_unauthorized_action_detected(self) -> None:
        from acgs_lite.constitution import DivergenceType

        self.tracker.bind("a1", self.contract)
        r = self.tracker.check_action("a1", "write email to external contact")
        assert not r.is_compliant
        assert r.divergences[0].divergence_type == DivergenceType.UNAUTHORIZED_ACTION

    def test_volume_limit(self) -> None:
        self.tracker.bind("a1", self.contract)
        for _ in range(10):
            self.tracker.check_action("a1", "read document")
        r = self.tracker.check_action("a1", "list remaining")
        vol = [d for d in r.divergences if d.divergence_type.value == "volume_exceeded"]
        assert vol

    def test_divergence_score(self) -> None:
        self.tracker.bind("a1", self.contract)
        self.tracker.check_action("a1", "read doc")
        self.tracker.check_action("a1", "write email")
        assert self.tracker.divergence_score("a1") == pytest.approx(0.5)

    def test_unbind_returns_report(self) -> None:
        self.tracker.bind("a1", self.contract)
        self.tracker.check_action("a1", "read doc")
        report = self.tracker.unbind("a1")
        assert report is not None
        assert report.total_actions == 1
        assert not self.tracker.is_bound("a1")

    def test_duplicate_bind_raises(self) -> None:
        self.tracker.bind("a1", self.contract)
        with pytest.raises(ValueError):
            self.tracker.bind("a1", self.contract)


class TestObligationPredictor:
    """exp233: Markov chain breach prediction."""

    def setup_method(self) -> None:
        from acgs_lite.constitution import ObligationPredictor

        self.pred = ObligationPredictor(warn_threshold=0.1)
        for _ in range(70):
            self.pred.observe("pending", "fulfilled")
        for _ in range(15):
            self.pred.observe("pending", "breached")
        for _ in range(10):
            self.pred.observe("pending", "waived")
        for _ in range(5):
            self.pred.observe("pending", "expired")

    def test_observation_count(self) -> None:
        assert self.pred.observation_count() == 100

    def test_transition_matrix_row_stochastic(self) -> None:
        m = self.pred.matrix()
        for row in m:
            assert abs(sum(row) - 1.0) < 1e-9

    def test_breach_probability_reasonable(self) -> None:
        risk = self.pred.predict("pending", lookahead=10)
        assert 0.1 <= risk.breach_probability <= 0.2

    def test_absorbing_state_breached(self) -> None:
        risk = self.pred.predict("breached")
        assert risk.breach_probability == 1.0
        assert risk.should_warn

    def test_absorbing_state_fulfilled(self) -> None:
        risk = self.pred.predict("fulfilled")
        assert risk.breach_probability == 0.0
        assert risk.fulfilled_probability == 1.0

    def test_portfolio_scan(self) -> None:
        portfolio = self.pred.scan(["pending", "pending", "fulfilled", "breached"])
        assert portfolio.total_obligations == 4
        assert portfolio.pending_count == 2
        assert portfolio.warnings_count >= 1

    def test_uniform_prior_without_observations(self) -> None:
        from acgs_lite.constitution import ObligationPredictor

        fresh = ObligationPredictor()
        risk = fresh.predict("pending", lookahead=1)
        assert abs(risk.breach_probability - 0.2) < 0.01

    def test_reset(self) -> None:
        self.pred.reset()
        assert self.pred.observation_count() == 0


class TestRefusalReasoningEngine:
    """exp234: MOSAIC structured refusal with alternatives."""

    def setup_method(self) -> None:
        from acgs_lite.constitution import RefusalReasoningEngine

        self.constitution = Constitution(
            rules=[
                Rule(
                    id="SAFE-001",
                    text="No financial advice",
                    severity=Severity.CRITICAL,
                    keywords=["invest", "stocks"],
                ),
                Rule(
                    id="SAFE-002",
                    text="No destructive operations",
                    severity=Severity.HIGH,
                    keywords=["delete", "drop", "destroy"],
                ),
            ]
        )
        self.engine = RefusalReasoningEngine(self.constitution)

    def test_basic_refusal(self) -> None:
        d = self.engine.reason_refusal("invest in tech stocks", ["SAFE-001"])
        assert d.rule_count == 1
        assert d.refusal_severity == "critical"

    def test_matched_keywords(self) -> None:
        d = self.engine.reason_refusal("invest in tech stocks", ["SAFE-001"])
        assert (
            "invest" in d.reasons[0].matched_keywords or "stocks" in d.reasons[0].matched_keywords
        )

    def test_suggestions_generated(self) -> None:
        d = self.engine.reason_refusal("invest in tech stocks", ["SAFE-001"])
        assert d.can_retry
        assert len(d.suggestions) > 0

    def test_destructive_archive_suggestion(self) -> None:
        d = self.engine.reason_refusal("delete old records", ["SAFE-002"])
        has_archive = any("archive" in s.alternative_action.lower() for s in d.suggestions)
        assert has_archive

    def test_multi_rule_aggregate_severity(self) -> None:
        d = self.engine.reason_refusal("delete investment portfolio", ["SAFE-001", "SAFE-002"])
        assert d.rule_count == 2
        assert d.refusal_severity == "critical"

    def test_unknown_rule_handled(self) -> None:
        d = self.engine.reason_refusal("test", ["NONEXISTENT"])
        assert d.rule_count == 0

    def test_to_dict(self) -> None:
        d = self.engine.reason_refusal("invest now", ["SAFE-001"])
        dd = d.to_dict()
        assert "reasons" in dd
        assert "suggestions" in dd

    def test_max_suggestions_limit(self) -> None:
        from acgs_lite.constitution import RefusalReasoningEngine

        limited = RefusalReasoningEngine(self.constitution, max_suggestions=1)
        d = limited.reason_refusal("invest in stocks", ["SAFE-001"])
        assert len(d.suggestions) <= 1
