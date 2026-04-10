"""Tests for Phase 2: Runtime Compliance Enforcement.

Covers:
- ObligationType enum values and severity mapping
- RuntimeObligation model (to_dict, satisfy, is_blocking)
- make_obligation factory
- obligation_mappings static map + register_obligation extension
- get_obligations_for_refs lookup
- RuntimeComplianceChecker.check() for EU AI Act, HIPAA, GDPR, SOC2
- Blocking obligations when unsatisfied
- Satisfaction via human_approval signal
- CDP assembler: runtime_obligations field populated
- CDPRecordV1: runtime_obligations in to_dict and hash payload
"""

from __future__ import annotations

from acgs_lite.cdp.assembler import assemble_cdp_record
from acgs_lite.cdp.record import CDPRecordV1
from acgs_lite.compliance.obligation_mappings import (
    _OBLIGATION_MAP,
    get_all_article_refs,
    get_obligations_for_refs,
    register_obligation,
)
from acgs_lite.compliance.runtime_checker import RuntimeComplianceChecker
from acgs_lite.compliance.runtime_obligations import (
    _OBLIGATION_SEVERITY,
    ObligationSeverity,
    ObligationType,
    RuntimeObligation,
    make_obligation,
)

_CONST_HASH = "608508a9bd224290"
_FIXED_TS = "2026-04-10T00:00:00+00:00"


# ──────────────────────────────────────────────────────────────────────────────
# ObligationType and severity
# ──────────────────────────────────────────────────────────────────────────────


class TestObligationType:
    def test_blocking_types(self) -> None:
        blocking = {
            ObligationType.HITL_REQUIRED,
            ObligationType.PHI_GUARD,
            ObligationType.CONSENT_CHECK,
        }
        for ob_type in blocking:
            assert _OBLIGATION_SEVERITY[ob_type] == ObligationSeverity.BLOCKING

    def test_advisory_types(self) -> None:
        advisory = {
            ObligationType.EXPLAINABILITY,
            ObligationType.AUDIT_REQUIRED,
            ObligationType.BIAS_CHECK,
            ObligationType.COOL_OFF,
            ObligationType.SPEND_LIMIT,
        }
        for ob_type in advisory:
            assert _OBLIGATION_SEVERITY[ob_type] == ObligationSeverity.ADVISORY

    def test_all_types_covered(self) -> None:
        for ob_type in ObligationType:
            assert ob_type in _OBLIGATION_SEVERITY, f"{ob_type} missing from severity map"


# ──────────────────────────────────────────────────────────────────────────────
# RuntimeObligation model
# ──────────────────────────────────────────────────────────────────────────────


class TestRuntimeObligation:
    def _make(self, ob_type: ObligationType = ObligationType.HITL_REQUIRED) -> RuntimeObligation:
        return make_obligation(
            ob_type,
            "eu_ai_act",
            "EU-AIA Art.14(1)",
            "Human-in-the-loop required for high-risk AI decisions.",
        )

    def test_is_blocking_hitl(self) -> None:
        ob = self._make(ObligationType.HITL_REQUIRED)
        assert ob.is_blocking is True
        assert ob.satisfied is False

    def test_is_not_blocking_advisory(self) -> None:
        ob = make_obligation(ObligationType.EXPLAINABILITY, "eu_ai_act", "Art.13", "Explain.")
        assert ob.is_blocking is False

    def test_satisfy_returns_new_instance(self) -> None:
        ob = self._make()
        satisfied = ob.satisfy(evidence="human clicked approve")
        # Original unchanged (frozen dataclass)
        assert ob.satisfied is False
        assert satisfied.satisfied is True
        assert satisfied.metadata.get("satisfied_evidence") == "human clicked approve"

    def test_to_dict_keys(self) -> None:
        ob = self._make()
        d = ob.to_dict()
        assert set(d.keys()) == {
            "obligation_type",
            "framework_id",
            "article_ref",
            "description",
            "satisfied",
            "severity",
            "metadata",
        }

    def test_to_dict_values(self) -> None:
        ob = self._make()
        d = ob.to_dict()
        assert d["obligation_type"] == "hitl_required"
        assert d["severity"] == "blocking"
        assert d["satisfied"] is False


# ──────────────────────────────────────────────────────────────────────────────
# obligation_mappings
# ──────────────────────────────────────────────────────────────────────────────


class TestObligationMappings:
    def test_static_map_has_key_refs(self) -> None:
        assert "EU-AIA Art.14(1)" in _OBLIGATION_MAP
        assert "HIPAA §164.502" in _OBLIGATION_MAP
        assert "GDPR Art.22(1)" in _OBLIGATION_MAP
        assert "SOC2 CC7.1" in _OBLIGATION_MAP

    def test_get_obligations_for_known_refs(self) -> None:
        obs = get_obligations_for_refs(["EU-AIA Art.14(1)", "HIPAA §164.502"])
        types = {o.obligation_type for o in obs}
        assert ObligationType.HITL_REQUIRED in types
        assert ObligationType.PHI_GUARD in types

    def test_get_obligations_skips_unknown(self) -> None:
        obs = get_obligations_for_refs(["NOT-A-REAL-REF-XYZ"])
        assert obs == []

    def test_get_obligations_deduplicates(self) -> None:
        obs = get_obligations_for_refs(["EU-AIA Art.14(1)", "EU-AIA Art.14(1)"])
        assert len(obs) == 1

    def test_register_obligation_extends_map(self) -> None:
        custom = make_obligation(
            ObligationType.COOL_OFF,
            "igaming",
            "UKGC SR-S1.2",
            "Self-exclusion cool-off period must be enforced.",
        )
        register_obligation("UKGC SR-S1.2", custom)
        obs = get_obligations_for_refs(["UKGC SR-S1.2"])
        assert len(obs) == 1
        assert obs[0].obligation_type == ObligationType.COOL_OFF
        assert obs[0].framework_id == "igaming"

    def test_get_all_article_refs_includes_static(self) -> None:
        refs = get_all_article_refs()
        assert "EU-AIA Art.14(1)" in refs
        assert "HIPAA §164.502" in refs


# ──────────────────────────────────────────────────────────────────────────────
# RuntimeComplianceChecker
# ──────────────────────────────────────────────────────────────────────────────


class TestRuntimeComplianceChecker:
    def setup_method(self) -> None:
        self.checker = RuntimeComplianceChecker()

    def test_eu_ai_act_high_risk_triggers_hitl(self) -> None:
        obs = self.checker.check(
            {
                "compliance_frameworks": ["eu_ai_act"],
                "risk_score": 0.85,
                "matched_rules": ["EU-AIA Art.14(1)"],
            }
        )
        types = {o.obligation_type for o in obs}
        assert ObligationType.HITL_REQUIRED in types

    def test_hipaa_triggers_phi_guard(self) -> None:
        obs = self.checker.check(
            {
                "compliance_frameworks": ["hipaa_ai"],
                "matched_rules": ["HIPAA §164.502"],
            }
        )
        types = {o.obligation_type for o in obs}
        assert ObligationType.PHI_GUARD in types

    def test_gdpr_triggers_hitl_and_consent(self) -> None:
        obs = self.checker.check(
            {
                "compliance_frameworks": ["gdpr"],
                "matched_rules": ["GDPR Art.22(1)", "GDPR Art.6(1)"],
            }
        )
        types = {o.obligation_type for o in obs}
        assert ObligationType.HITL_REQUIRED in types
        assert ObligationType.CONSENT_CHECK in types

    def test_soc2_triggers_audit_required(self) -> None:
        obs = self.checker.check(
            {
                "compliance_frameworks": ["soc2_ai"],
            }
        )
        types = {o.obligation_type for o in obs}
        assert ObligationType.AUDIT_REQUIRED in types

    def test_hitl_satisfied_by_human_approval(self) -> None:
        obs = self.checker.check(
            {
                "compliance_frameworks": ["eu_ai_act"],
                "matched_rules": ["EU-AIA Art.14(1)"],
                "human_approval": True,
            }
        )
        hitl_obs = [o for o in obs if o.obligation_type == ObligationType.HITL_REQUIRED]
        assert len(hitl_obs) >= 1
        assert all(o.satisfied for o in hitl_obs)

    def test_hitl_not_satisfied_without_approval(self) -> None:
        obs = self.checker.check(
            {
                "compliance_frameworks": ["eu_ai_act"],
                "matched_rules": ["EU-AIA Art.14(1)"],
                "human_approval": False,
            }
        )
        hitl_obs = [o for o in obs if o.obligation_type == ObligationType.HITL_REQUIRED]
        assert any(not o.satisfied for o in hitl_obs)

    def test_empty_context_returns_empty(self) -> None:
        obs = self.checker.check({})
        assert obs == []

    def test_blocking_unsatisfied_identified(self) -> None:
        obs = self.checker.check(
            {
                "compliance_frameworks": ["eu_ai_act"],
                "matched_rules": ["EU-AIA Art.14(1)"],
                "human_approval": None,
            }
        )
        blocking_unsatisfied = [o for o in obs if o.is_blocking and not o.satisfied]
        assert len(blocking_unsatisfied) >= 1

    def test_domain_healthcare_infers_phi_guard(self) -> None:
        obs = self.checker.check(
            {
                "domain": "healthcare",
                "compliance_frameworks": [],
            }
        )
        types = {o.obligation_type for o in obs}
        assert ObligationType.PHI_GUARD in types

    def test_low_risk_eu_ai_act_no_hitl_inferred(self) -> None:
        """Low risk_score should not auto-infer HITL from eu_ai_act framework alone."""
        obs = self.checker.check(
            {
                "compliance_frameworks": ["eu_ai_act"],
                "risk_score": 0.2,
                "matched_rules": [],
            }
        )
        # HITL should only come from explicit refs or high risk — low risk + no refs → no HITL
        hitl_obs = [o for o in obs if o.obligation_type == ObligationType.HITL_REQUIRED]
        assert len(hitl_obs) == 0

    def test_multiple_frameworks_combined(self) -> None:
        obs = self.checker.check(
            {
                "compliance_frameworks": ["eu_ai_act", "hipaa_ai", "soc2_ai"],
                "risk_score": 0.8,
                "matched_rules": ["EU-AIA Art.14(1)", "HIPAA §164.502"],
            }
        )
        types = {o.obligation_type for o in obs}
        assert ObligationType.HITL_REQUIRED in types
        assert ObligationType.PHI_GUARD in types
        assert ObligationType.AUDIT_REQUIRED in types


# ──────────────────────────────────────────────────────────────────────────────
# CDP assembler — runtime_obligations field
# ──────────────────────────────────────────────────────────────────────────────


class TestCDPAssemblerObligations:
    def _base_kwargs(self) -> dict:
        return {
            "raw_input": "test input",
            "agent_id": "agent-obligations-test",
            "constitutional_hash": _CONST_HASH,
            "created_at": _FIXED_TS,
        }

    def test_no_obligations_by_default(self) -> None:
        record = assemble_cdp_record(**self._base_kwargs())
        assert record.runtime_obligations == []

    def test_obligations_stored_as_dicts(self) -> None:
        obs = [
            make_obligation(
                ObligationType.HITL_REQUIRED,
                "eu_ai_act",
                "EU-AIA Art.14(1)",
                "Human oversight required.",
            )
        ]
        record = assemble_cdp_record(**self._base_kwargs(), runtime_obligations=obs)
        assert len(record.runtime_obligations) == 1
        ob_dict = record.runtime_obligations[0]
        assert ob_dict["obligation_type"] == "hitl_required"
        assert ob_dict["framework_id"] == "eu_ai_act"

    def test_obligations_in_hash(self) -> None:
        """Records with different obligations must have different hashes."""
        base = assemble_cdp_record(**self._base_kwargs())
        with_ob = assemble_cdp_record(
            **self._base_kwargs(),
            runtime_obligations=[
                make_obligation(
                    ObligationType.PHI_GUARD, "hipaa_ai", "HIPAA §164.502", "PHI guard."
                )
            ],
        )
        assert base.cdp_hash != with_ob.cdp_hash

    def test_obligations_in_to_dict(self) -> None:
        obs = [make_obligation(ObligationType.AUDIT_REQUIRED, "soc2_ai", "SOC2 CC7.1", "Audit.")]
        record = assemble_cdp_record(**self._base_kwargs(), runtime_obligations=obs)
        d = record.to_dict()
        assert "runtime_obligations" in d
        assert len(d["runtime_obligations"]) == 1
        assert d["runtime_obligations"][0]["obligation_type"] == "audit_required"


# ──────────────────────────────────────────────────────────────────────────────
# CDPRecordV1 — runtime_obligations field
# ──────────────────────────────────────────────────────────────────────────────


class TestCDPRecordObligations:
    def test_default_empty(self) -> None:
        record = CDPRecordV1(cdp_id="cdp-test-1")
        assert record.runtime_obligations == []

    def test_accepts_plain_dicts(self) -> None:
        record = CDPRecordV1(
            cdp_id="cdp-test-2",
            runtime_obligations=[{"obligation_type": "hitl_required", "satisfied": False}],
        )
        assert record.runtime_obligations[0]["obligation_type"] == "hitl_required"

    def test_in_to_dict(self) -> None:
        record = CDPRecordV1(cdp_id="cdp-test-3", runtime_obligations=[{"x": 1}])
        d = record.to_dict()
        assert "runtime_obligations" in d
        assert d["runtime_obligations"] == [{"x": 1}]
