"""Tests for healthcare-specific custom validators.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from acgs_lite.constitution import Severity
from clinicalguard.skills.healthcare_validators import (
    adverse_event_logger,
    clinical_decision_auditor,
    phi_detector,
    register_all,
)

CTX: dict = {}


# ---------------------------------------------------------------------------
# PHI Detector Tests
# ---------------------------------------------------------------------------

class TestPHIDetector:
    """Detect HIPAA Safe Harbor identifiers in clinical text."""

    def test_ssn_detected(self) -> None:
        violations = phi_detector("Patient SSN: 123-45-6789", CTX)
        assert any(v.rule_id == "PHI-SSN" for v in violations)
        assert all(v.severity == Severity.CRITICAL for v in violations)

    def test_mrn_detected(self) -> None:
        violations = phi_detector("MRN: 12345678", CTX)
        assert any(v.rule_id == "PHI-MRN" for v in violations)

    def test_mrn_medical_record_format(self) -> None:
        violations = phi_detector("Medical Record #98765", CTX)
        assert any(v.rule_id == "PHI-MRN" for v in violations)

    def test_dob_detected(self) -> None:
        violations = phi_detector("DOB: 03/15/1985", CTX)
        assert any(v.rule_id == "PHI-DOB" for v in violations)

    def test_dob_born_format(self) -> None:
        violations = phi_detector("born 1/1/90", CTX)
        assert any(v.rule_id == "PHI-DOB" for v in violations)

    def test_phone_detected(self) -> None:
        violations = phi_detector("Contact: (555) 123-4567", CTX)
        assert any(v.rule_id == "PHI-PHONE" for v in violations)

    def test_email_detected(self) -> None:
        violations = phi_detector("Email: patient@hospital.org", CTX)
        assert any(v.rule_id == "PHI-EMAIL" for v in violations)

    def test_insurance_id_detected(self) -> None:
        violations = phi_detector("Insurance ID: ABC12345678", CTX)
        assert any(v.rule_id == "PHI-INSURANCE" for v in violations)

    def test_device_udi_detected(self) -> None:
        violations = phi_detector("UDI: ABC-12345-DEF", CTX)
        assert any(v.rule_id == "PHI-DEVICE" for v in violations)

    def test_license_number_detected(self) -> None:
        violations = phi_detector("DEA number: AB1234567", CTX)
        assert any(v.rule_id == "PHI-LICENSE" for v in violations)

    def test_safe_text_no_violations(self) -> None:
        violations = phi_detector(
            "Patient SYNTH-001 presented with mild hypertension. "
            "BP 140/90. Recommend lifestyle modifications.",
            CTX,
        )
        # Should not trigger PHI patterns on synthetic IDs
        phi_ids = {v.rule_id for v in violations if v.rule_id.startswith("PHI-")}
        # SYNTH-001 should not match SSN, MRN, etc.
        assert "PHI-SSN" not in phi_ids

    def test_multiple_phi_in_one_text(self) -> None:
        text = "Patient SSN 123-45-6789, DOB: 01/15/1990, email: john@example.com"
        violations = phi_detector(text, CTX)
        rule_ids = {v.rule_id for v in violations}
        assert "PHI-SSN" in rule_ids
        assert "PHI-DOB" in rule_ids
        assert "PHI-EMAIL" in rule_ids

    def test_all_violations_are_critical(self) -> None:
        text = "MRN: 99999 phone (555) 111-2222"
        violations = phi_detector(text, CTX)
        for v in violations:
            assert v.severity == Severity.CRITICAL
            assert v.category == "phi_protection"


# ---------------------------------------------------------------------------
# Clinical Decision Auditor Tests
# ---------------------------------------------------------------------------

class TestClinicalDecisionAuditor:
    """Flag unsafe clinical claims and recommendations."""

    def test_no_evidence_flagged(self) -> None:
        violations = clinical_decision_auditor("This treatment has no evidence of efficacy", CTX)
        assert any(v.rule_id == "CLIN-NOEVIDENCE" for v in violations)

    def test_certainty_flagged(self) -> None:
        violations = clinical_decision_auditor(
            "This medication is guaranteed to cure your condition", CTX
        )
        assert any(v.rule_id == "CLIN-CERTAINTY" for v in violations)

    def test_self_diagnosis_flagged(self) -> None:
        violations = clinical_decision_auditor("You have type 2 diabetes", CTX)
        assert any(v.rule_id == "CLIN-SELFDIAGNOSE" for v in violations)

    def test_skip_monitoring_flagged(self) -> None:
        violations = clinical_decision_auditor(
            "No need to monitor blood levels after starting", CTX
        )
        assert any(v.rule_id == "CLIN-NOMONITOR" for v in violations)

    def test_stop_medication_critical(self) -> None:
        violations = clinical_decision_auditor("Stop taking your medication immediately", CTX)
        stop_v = [v for v in violations if v.rule_id == "CLIN-STOPMED"]
        assert len(stop_v) == 1
        assert stop_v[0].severity == Severity.CRITICAL

    def test_safe_clinical_text(self) -> None:
        violations = clinical_decision_auditor(
            "Based on current guidelines (AHA 2024), recommend initiating "
            "low-dose aspirin 81mg daily. Follow-up in 4 weeks for reassessment.",
            CTX,
        )
        assert len(violations) == 0

    def test_appropriate_uncertainty(self) -> None:
        violations = clinical_decision_auditor(
            "The findings may suggest early-stage hypertension. "
            "Recommend consultation with a cardiologist for further evaluation.",
            CTX,
        )
        assert len(violations) == 0


# ---------------------------------------------------------------------------
# Adverse Event Logger Tests
# ---------------------------------------------------------------------------

class TestAdverseEventLogger:
    """Detect signals requiring MedWatch or incident reporting."""

    def test_patient_death_detected(self) -> None:
        violations = adverse_event_logger("Patient died after administration", CTX)
        assert any(v.rule_id == "AE-DEATH" for v in violations)
        assert violations[0].severity == Severity.CRITICAL

    def test_hospitalization_detected(self) -> None:
        violations = adverse_event_logger("Patient was hospitalized for 3 days", CTX)
        assert any(v.rule_id == "AE-HOSPITALIZE" for v in violations)

    def test_er_visit_detected(self) -> None:
        violations = adverse_event_logger("Required emergency visit", CTX)
        assert any(v.rule_id == "AE-HOSPITALIZE" for v in violations)

    def test_disability_detected(self) -> None:
        violations = adverse_event_logger("Resulted in permanent disability", CTX)
        assert any(v.rule_id == "AE-DISABILITY" for v in violations)

    def test_overdose_detected(self) -> None:
        violations = adverse_event_logger("Patient presented with overdose symptoms", CTX)
        assert any(v.rule_id == "AE-OVERDOSE" for v in violations)

    def test_serotonin_syndrome_detected(self) -> None:
        violations = adverse_event_logger("Suspected serotonin syndrome", CTX)
        assert any(v.rule_id == "AE-OVERDOSE" for v in violations)

    def test_anaphylaxis_detected(self) -> None:
        violations = adverse_event_logger("Patient experienced anaphylaxis", CTX)
        assert any(v.rule_id == "AE-ALLERGY" for v in violations)

    def test_stevens_johnson_detected(self) -> None:
        violations = adverse_event_logger("Diagnosed with Stevens-Johnson syndrome", CTX)
        assert any(v.rule_id == "AE-ALLERGY" for v in violations)

    def test_fall_risk_medium_severity(self) -> None:
        violations = adverse_event_logger("Patient is a fall risk", CTX)
        fall_v = [v for v in violations if v.rule_id == "AE-FALLRISK"]
        assert len(fall_v) == 1
        assert fall_v[0].severity == Severity.MEDIUM

    def test_routine_clinical_no_adverse_events(self) -> None:
        violations = adverse_event_logger(
            "Patient tolerating medication well. Vitals stable. "
            "Blood pressure 120/80. Continue current regimen.",
            CTX,
        )
        assert len(violations) == 0


# ---------------------------------------------------------------------------
# Integration: register_all
# ---------------------------------------------------------------------------

class TestRegisterAll:
    """Verify all validators can be registered on a GovernanceEngine."""

    def test_register_all_on_engine(self) -> None:
        from acgs_lite import Constitution, GovernanceEngine

        constitution = Constitution.default()
        engine = GovernanceEngine(constitution, strict=False)
        register_all(engine)
        assert len(engine.custom_validators) == 3

    def test_engine_with_validators_detects_phi(self) -> None:
        from acgs_lite import Constitution, GovernanceEngine, Rule
        from acgs_lite import Severity as Sev

        # Use minimal constitution so no CRITICAL rules short-circuit custom validators
        constitution = Constitution.from_rules(
            [Rule(id="TEST-001", text="placeholder", severity=Sev.LOW, keywords=["zzz_nevermatches"])],
            name="test-minimal",
        )
        engine = GovernanceEngine(constitution, strict=False)
        register_all(engine)

        result = engine.validate("Patient SSN 123-45-6789")
        phi_violations = [v for v in result.violations if v.rule_id.startswith("PHI-")]
        assert len(phi_violations) >= 1

    def test_engine_with_validators_detects_adverse_event(self) -> None:
        from acgs_lite import Constitution, GovernanceEngine

        constitution = Constitution.default()
        engine = GovernanceEngine(constitution, strict=False)
        register_all(engine)

        result = engine.validate("Patient was hospitalized after adverse reaction")
        ae_violations = [v for v in result.violations if v.rule_id.startswith("AE-")]
        assert len(ae_violations) >= 1
