"""Tests for constitution/contracts.py — GovernanceContract, ContractRegistry."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from acgs_lite.constitution.contracts import (
    BreachRecord,
    BreachSeverity,
    ContractRegistry,
    ContractStatus,
    ContractTerm,
    DisputeResolution,
    GovernanceContract,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_terms() -> list[ContractTerm]:
    return [
        ContractTerm(term_id="T1", description="No PII sharing", category="data_protection", severity="critical"),
        ContractTerm(term_id="T2", description="Latency < 500ms", category="sla", severity="medium", measurable=True, threshold=500.0, unit="ms"),
    ]


def _make_contract(**overrides) -> GovernanceContract:
    defaults = {
        "contract_id": "c1",
        "party_a": "alpha",
        "party_b": "beta",
        "terms": _make_terms(),
        "created_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    return GovernanceContract(**defaults)


# ---------------------------------------------------------------------------
# ContractTerm
# ---------------------------------------------------------------------------
class TestContractTerm:
    def test_to_dict_basic(self):
        t = ContractTerm(term_id="T1", description="desc", category="cat")
        d = t.to_dict()
        assert d["term_id"] == "T1"
        assert "measurable" not in d

    def test_to_dict_measurable(self):
        t = ContractTerm(term_id="T1", description="d", category="c", measurable=True, threshold=10.0, unit="ms")
        d = t.to_dict()
        assert d["measurable"] is True
        assert d["threshold"] == 10.0
        assert d["unit"] == "ms"


# ---------------------------------------------------------------------------
# BreachRecord
# ---------------------------------------------------------------------------
class TestBreachRecord:
    def test_to_dict_unresolved(self):
        b = BreachRecord(
            breach_id="b1", contract_id="c1", term_id="T1",
            reported_by="alpha", evidence="proof",
            severity=BreachSeverity.MAJOR, timestamp=datetime.now(timezone.utc),
        )
        d = b.to_dict()
        assert d["resolved"] is False
        assert "resolution" not in d

    def test_to_dict_resolved(self):
        b = BreachRecord(
            breach_id="b1", contract_id="c1", term_id="T1",
            reported_by="alpha", evidence="proof",
            severity=BreachSeverity.MINOR, timestamp=datetime.now(timezone.utc),
            resolved=True, resolution=DisputeResolution.WARNING,
            resolved_by="admin", resolved_at=datetime.now(timezone.utc),
            resolution_notes="noted",
        )
        d = b.to_dict()
        assert d["resolved"] is True
        assert d["resolution"] == "warning"
        assert d["resolved_by"] == "admin"


# ---------------------------------------------------------------------------
# GovernanceContract — lifecycle
# ---------------------------------------------------------------------------
class TestGovernanceContractLifecycle:
    def test_initial_status_is_draft(self):
        c = _make_contract()
        assert c.status == ContractStatus.DRAFT

    def test_propose(self):
        c = _make_contract()
        c.propose(proposed_by="alpha")
        assert c.status == ContractStatus.PROPOSED

    def test_propose_non_party_raises(self):
        c = _make_contract()
        with pytest.raises(ValueError, match="Only contract parties"):
            c.propose(proposed_by="outsider")

    def test_propose_from_non_draft_raises(self):
        c = _make_contract(status=ContractStatus.ACTIVE)
        with pytest.raises(ValueError, match="Can only propose from DRAFT"):
            c.propose(proposed_by="alpha")

    def test_accept(self):
        c = _make_contract()
        c.propose(proposed_by="alpha")
        c.accept(accepted_by="beta")
        assert c.status == ContractStatus.ACTIVE

    def test_accept_own_proposal_raises(self):
        c = _make_contract()
        c.propose(proposed_by="alpha")
        with pytest.raises(ValueError, match="Cannot accept your own proposal"):
            c.accept(accepted_by="alpha")

    def test_accept_non_party_raises(self):
        c = _make_contract()
        c.propose(proposed_by="alpha")
        with pytest.raises(ValueError, match="Only contract parties"):
            c.accept(accepted_by="outsider")

    def test_accept_from_non_proposed_raises(self):
        c = _make_contract()
        with pytest.raises(ValueError, match="Can only accept from PROPOSED"):
            c.accept(accepted_by="beta")

    def test_is_active(self):
        c = _make_contract(status=ContractStatus.ACTIVE)
        assert c.is_active() is True

    def test_is_active_expired(self):
        past = datetime.now(timezone.utc) - timedelta(days=1)
        c = _make_contract(status=ContractStatus.ACTIVE, expires_at=past)
        assert c.is_active() is False

    def test_is_active_not_active_status(self):
        c = _make_contract(status=ContractStatus.DRAFT)
        assert c.is_active() is False

    def test_check_expiry_expires_contract(self):
        past = datetime.now(timezone.utc) - timedelta(seconds=1)
        c = _make_contract(status=ContractStatus.ACTIVE, expires_at=past)
        assert c.check_expiry() is True
        assert c.status == ContractStatus.EXPIRED

    def test_check_expiry_not_expired(self):
        future = datetime.now(timezone.utc) + timedelta(days=30)
        c = _make_contract(status=ContractStatus.ACTIVE, expires_at=future)
        assert c.check_expiry() is False
        assert c.status == ContractStatus.ACTIVE

    def test_terminate(self):
        c = _make_contract(status=ContractStatus.ACTIVE)
        c.terminate(terminated_by="alpha", reason="done")
        assert c.status == ContractStatus.TERMINATED

    def test_terminate_already_terminated_raises(self):
        c = _make_contract(status=ContractStatus.TERMINATED)
        with pytest.raises(ValueError, match="already terminated"):
            c.terminate(terminated_by="alpha")

    def test_suspend(self):
        c = _make_contract(status=ContractStatus.ACTIVE)
        c.suspend(suspended_by="admin")
        assert c.status == ContractStatus.SUSPENDED

    def test_suspend_non_active_raises(self):
        c = _make_contract(status=ContractStatus.DRAFT)
        with pytest.raises(ValueError, match="Can only suspend ACTIVE"):
            c.suspend(suspended_by="admin")

    def test_reinstate(self):
        c = _make_contract(status=ContractStatus.SUSPENDED)
        c.reinstate(reinstated_by="admin")
        assert c.status == ContractStatus.ACTIVE

    def test_reinstate_non_suspended_raises(self):
        c = _make_contract(status=ContractStatus.ACTIVE)
        with pytest.raises(ValueError, match="Can only reinstate SUSPENDED"):
            c.reinstate(reinstated_by="admin")


# ---------------------------------------------------------------------------
# GovernanceContract — breaches and disputes
# ---------------------------------------------------------------------------
class TestBreachesAndDisputes:
    def test_report_breach(self):
        c = _make_contract(status=ContractStatus.ACTIVE)
        breach = c.report_breach("T1", reported_by="beta", evidence="PII found")
        assert isinstance(breach, BreachRecord)
        assert c.status == ContractStatus.DISPUTED
        assert len(c.breaches) == 1

    def test_report_breach_infers_severity(self):
        c = _make_contract(status=ContractStatus.ACTIVE)
        breach = c.report_breach("T1", reported_by="beta", evidence="PII found")
        assert breach.severity == BreachSeverity.CRITICAL  # T1 severity is "critical"

    def test_report_breach_explicit_severity(self):
        c = _make_contract(status=ContractStatus.ACTIVE)
        breach = c.report_breach("T1", reported_by="beta", evidence="e", severity=BreachSeverity.MINOR)
        assert breach.severity == BreachSeverity.MINOR

    def test_report_breach_unknown_term_raises(self):
        c = _make_contract(status=ContractStatus.ACTIVE)
        with pytest.raises(ValueError, match="Unknown term"):
            c.report_breach("T99", reported_by="beta", evidence="e")

    def test_report_breach_non_party_raises(self):
        c = _make_contract(status=ContractStatus.ACTIVE)
        with pytest.raises(ValueError, match="Only contract parties"):
            c.report_breach("T1", reported_by="outsider", evidence="e")

    def test_report_breach_non_active_raises(self):
        c = _make_contract(status=ContractStatus.DRAFT)
        with pytest.raises(ValueError, match="Can only report breaches on ACTIVE"):
            c.report_breach("T1", reported_by="beta", evidence="e")

    def test_resolve_dispute_warning(self):
        c = _make_contract(status=ContractStatus.ACTIVE)
        breach = c.report_breach("T1", reported_by="beta", evidence="e")
        c.resolve_dispute(breach.breach_id, resolution="warning", resolved_by="admin")
        assert breach.resolved is True
        assert breach.resolution == DisputeResolution.WARNING
        assert c.status == ContractStatus.ACTIVE  # no unresolved breaches

    def test_resolve_dispute_contract_suspended(self):
        c = _make_contract(status=ContractStatus.ACTIVE)
        breach = c.report_breach("T1", reported_by="beta", evidence="e")
        c.resolve_dispute(breach.breach_id, resolution="contract_suspended", resolved_by="admin")
        assert c.status == ContractStatus.SUSPENDED

    def test_resolve_dispute_contract_terminated(self):
        c = _make_contract(status=ContractStatus.ACTIVE)
        breach = c.report_breach("T1", reported_by="beta", evidence="e")
        c.resolve_dispute(breach.breach_id, resolution="contract_terminated", resolved_by="admin")
        assert c.status == ContractStatus.TERMINATED

    def test_resolve_unknown_breach_raises(self):
        c = _make_contract(status=ContractStatus.ACTIVE)
        c.report_breach("T1", reported_by="beta", evidence="e")
        with pytest.raises(ValueError, match="Unknown breach"):
            c.resolve_dispute("nonexistent", resolution="warning", resolved_by="admin")

    def test_resolve_already_resolved_raises(self):
        c = _make_contract(status=ContractStatus.ACTIVE)
        breach = c.report_breach("T1", reported_by="beta", evidence="e")
        c.resolve_dispute(breach.breach_id, resolution="warning", resolved_by="admin")
        with pytest.raises(ValueError, match="already resolved"):
            c.resolve_dispute(breach.breach_id, resolution="warning", resolved_by="admin")

    def test_stays_disputed_with_unresolved_breaches(self):
        c = _make_contract(status=ContractStatus.ACTIVE)
        b1 = c.report_breach("T1", reported_by="beta", evidence="e1")
        _b2 = c.report_breach("T2", reported_by="beta", evidence="e2")
        c.resolve_dispute(b1.breach_id, resolution="warning", resolved_by="admin")
        # Still one unresolved breach
        assert c.status == ContractStatus.DISPUTED


# ---------------------------------------------------------------------------
# GovernanceContract — compliance and integrity
# ---------------------------------------------------------------------------
class TestComplianceAndIntegrity:
    def test_compliance_score_full(self):
        c = _make_contract(status=ContractStatus.ACTIVE)
        assert c.compliance_score() == 1.0

    def test_compliance_score_with_breach(self):
        c = _make_contract(status=ContractStatus.ACTIVE)
        c.report_breach("T1", reported_by="beta", evidence="e")
        # 1 of 2 terms breached -> 0.5
        assert c.compliance_score() == 0.5

    def test_compliance_score_no_terms(self):
        c = _make_contract(terms=[])
        assert c.compliance_score() == 1.0

    def test_integrity_hash_deterministic(self):
        c = _make_contract()
        h1 = c.integrity_hash()
        h2 = c.integrity_hash()
        assert h1 == h2
        assert len(h1) == 16

    def test_integrity_hash_changes_with_terms(self):
        c1 = _make_contract()
        c2 = _make_contract(terms=[ContractTerm(term_id="X", description="x", category="x")])
        assert c1.integrity_hash() != c2.integrity_hash()

    def test_history_records_events(self):
        c = _make_contract()
        c.propose(proposed_by="alpha")
        c.accept(accepted_by="beta")
        history = c.history()
        assert len(history) >= 2
        events = [e["event"] for e in history]
        assert "proposed" in events
        assert "accepted" in events

    def test_to_dict(self):
        c = _make_contract(status=ContractStatus.ACTIVE)
        d = c.to_dict()
        assert d["contract_id"] == "c1"
        assert d["status"] == "active"
        assert len(d["terms"]) == 2
        assert "compliance_score" in d
        assert "integrity_hash" in d


# ---------------------------------------------------------------------------
# ContractRegistry
# ---------------------------------------------------------------------------
class TestContractRegistry:
    @pytest.fixture()
    def registry(self) -> ContractRegistry:
        return ContractRegistry()

    def test_create_contract(self, registry):
        c = registry.create_contract("alpha", "beta", _make_terms())
        assert c.status == ContractStatus.DRAFT
        assert len(registry) == 1

    def test_create_contract_same_party_raises(self, registry):
        with pytest.raises(ValueError, match="must be different"):
            registry.create_contract("alpha", "alpha", _make_terms())

    def test_get_contract(self, registry):
        c = registry.create_contract("alpha", "beta", _make_terms())
        fetched = registry.get_contract(c.contract_id)
        assert fetched is c

    def test_get_contract_missing(self, registry):
        assert registry.get_contract("nonexistent") is None

    def test_contracts_for_agent(self, registry):
        registry.create_contract("alpha", "beta", _make_terms())
        registry.create_contract("alpha", "gamma", _make_terms())
        assert len(registry.contracts_for_agent("alpha")) == 2
        assert len(registry.contracts_for_agent("beta")) == 1
        assert len(registry.contracts_for_agent("delta")) == 0

    def test_contracts_for_agent_filtered_by_status(self, registry):
        c = registry.create_contract("alpha", "beta", _make_terms())
        c.propose(proposed_by="alpha")
        c.accept(accepted_by="beta")
        registry.create_contract("alpha", "gamma", _make_terms())  # stays DRAFT

        active = registry.contracts_for_agent("alpha", status=ContractStatus.ACTIVE)
        assert len(active) == 1

    def test_active_contracts_between(self, registry):
        c = registry.create_contract("alpha", "beta", _make_terms())
        c.propose(proposed_by="alpha")
        c.accept(accepted_by="beta")

        active = registry.active_contracts_between("alpha", "beta")
        assert len(active) == 1

        active_reversed = registry.active_contracts_between("beta", "alpha")
        assert len(active_reversed) == 1

    def test_active_contracts_between_no_match(self, registry):
        registry.create_contract("alpha", "beta", _make_terms())  # DRAFT, not active
        assert len(registry.active_contracts_between("alpha", "beta")) == 0

    def test_check_all_expiry(self, registry):
        past = datetime.now(timezone.utc) - timedelta(seconds=1)
        c = registry.create_contract("alpha", "beta", _make_terms(), expires_at=past)
        c.propose(proposed_by="alpha")
        c.accept(accepted_by="beta")

        expired = registry.check_all_expiry()
        assert len(expired) == 1
        assert c.status == ContractStatus.EXPIRED

    def test_compliance_report(self, registry):
        c = registry.create_contract("alpha", "beta", _make_terms())
        c.propose(proposed_by="alpha")
        c.accept(accepted_by="beta")

        report = registry.compliance_report()
        assert report["total_contracts"] == 1
        assert report["active"] == 1
        assert report["disputed"] == 0
        assert report["avg_compliance_score"] == 1.0

    def test_compliance_report_empty(self, registry):
        report = registry.compliance_report()
        assert report["total_contracts"] == 0
        assert report["avg_compliance_score"] == 1.0

    def test_len(self, registry):
        assert len(registry) == 0
        registry.create_contract("a", "b", _make_terms())
        assert len(registry) == 1
