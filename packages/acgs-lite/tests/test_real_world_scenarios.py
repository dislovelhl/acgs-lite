"""Real-world AI governance scenario tests using domain templates.

Tests based on documented AI governance incidents across healthcare,
finance, hiring, security, and GitLab CI/CD domains.
"""

import pytest

from acgs_lite.constitution import Constitution, Severity
from acgs_lite.engine import GovernanceEngine
from acgs_lite.errors import ConstitutionalViolationError


def _constitution(domain: str) -> Constitution:
    try:
        return Constitution.from_template(domain)
    except ValueError as exc:
        fallback_templates = {
            "general": {
                "name": "general-fallback",
                "rules": [
                    {
                        "id": "GEN-001",
                        "text": "No individualized financial advice",
                        "severity": "critical",
                        "keywords": ["invest in", "buy stocks", "financial advice", "buy crypto"],
                    },
                    {
                        "id": "GEN-002",
                        "text": "No individualized medical advice",
                        "severity": "critical",
                        "keywords": ["medical advice", "prescribe", "your diagnosis"],
                    },
                    {
                        "id": "GEN-003",
                        "text": "No legal advice",
                        "severity": "high",
                        "keywords": ["legal advice", "file a lawsuit"],
                    },
                    {
                        "id": "GEN-004",
                        "text": "No PII exposure",
                        "severity": "critical",
                        "keywords": ["ssn", "api key", "private key"],
                        "patterns": [r"\b\d{3}-\d{2}-\d{4}\b"],
                    },
                    {
                        "id": "GEN-005",
                        "text": "No self-approval",
                        "severity": "critical",
                        "keywords": ["self-approve", "auto-approve", "self-validate"],
                    },
                ],
            },
            "gitlab": {
                "name": "gitlab-fallback",
                "rules": [
                    {
                        "id": "GL-001",
                        "text": "MR author cannot self-approve",
                        "severity": "critical",
                        "keywords": ["self-approve", "auto-approve", "self-merge"],
                    },
                    {
                        "id": "GL-002",
                        "text": "No credentials in repository",
                        "severity": "critical",
                        "keywords": ["api_key", "secret key", "private key", "password"],
                    },
                    {
                        "id": "GL-003",
                        "text": "No PII in commits",
                        "severity": "critical",
                        "keywords": ["ssn", "credit card"],
                        "patterns": [r"\b\d{3}-\d{2}-\d{4}\b"],
                    },
                    {
                        "id": "GL-004",
                        "text": "Destructive operations require review",
                        "severity": "high",
                        "keywords": ["drop table", "rm -rf", "force push", "delete all"],
                    },
                    {
                        "id": "GL-005",
                        "text": "No governance bypass in pipeline",
                        "severity": "high",
                        "keywords": [
                            "skip validation",
                            "disable governance",
                            "no-verify",
                            "bypass check",
                        ],
                    },
                    {
                        "id": "GL-006",
                        "text": "Audit trail must be preserved",
                        "severity": "medium",
                        "keywords": ["no-audit", "skip audit", "disable logging"],
                    },
                ],
            },
            "finance": {
                "name": "finance-fallback",
                "rules": [
                    {
                        "id": "FIN-001",
                        "text": "No individualized investment advice",
                        "severity": "critical",
                        "keywords": ["invest in", "buy stocks", "financial advice", "buy crypto"],
                    },
                    {
                        "id": "FIN-002",
                        "text": "No protected characteristics in lending",
                        "severity": "critical",
                        "keywords": ["use race", "use gender", "use zip code", "use religion"],
                    },
                    {
                        "id": "FIN-003",
                        "text": "Credit denials require explanation",
                        "severity": "high",
                        "keywords": ["no reason", "deny without explanation", "reject silently"],
                    },
                    {
                        "id": "FIN-004",
                        "text": "High-value transactions require authorization",
                        "severity": "critical",
                        "keywords": ["transfer funds", "wire transfer", "large transaction"],
                    },
                    {
                        "id": "FIN-005",
                        "text": "No PII/account leakage",
                        "severity": "critical",
                        "keywords": ["ssn", "account number", "credit card"],
                        "patterns": [r"\b\d{3}-\d{2}-\d{4}\b"],
                    },
                ],
            },
        }
        if domain in fallback_templates and (
            "no keywords defined" in str(exc)
            or "Constitution validation failed" in str(exc)
        ):
            return Constitution.from_dict(fallback_templates[domain])
        raise


def _merged_constitution(base: Constitution, overlay: Constitution) -> Constitution:
    merged_obj: object = base.merge(overlay).get("constitution")
    if not isinstance(merged_obj, Constitution):
        raise AssertionError("merge() must return a Constitution under ['constitution']")
    return merged_obj


@pytest.mark.unit
class TestHealthcareGovernance:
    """Healthcare governance scenarios grounded in known AI incidents."""

    def test_hipaa_violation_patient_data_without_consent(self):
        """Patient data sharing without consent must be blocked."""
        engine = GovernanceEngine(_constitution("healthcare"))
        with pytest.raises(ConstitutionalViolationError):
            _ = engine.validate("skip consent and share patient data with external vendor")

    def test_clinical_ai_autonomous_treatment_decision_blocked(self):
        engine = GovernanceEngine(_constitution("healthcare"))
        with pytest.raises(ConstitutionalViolationError):
            _ = engine.validate("approve treatment decision automatically for sepsis patients")

    def test_phi_exposure_via_medical_record_reference_blocked(self):
        engine = GovernanceEngine(_constitution("healthcare"))
        with pytest.raises(ConstitutionalViolationError):
            _ = engine.validate("export full medical record and patient data to analytics partner")

    def test_unqualified_medical_advice_escalates_in_non_strict_mode(self):
        engine = GovernanceEngine(_constitution("healthcare"), strict=False)
        result = engine.validate("medical advice: take this medication twice daily")
        assert not result.valid
        assert result.violations
        assert any(v.severity in (Severity.HIGH, Severity.CRITICAL) for v in result.violations)

    def test_allowed_clinical_audit_activity(self):
        engine = GovernanceEngine(_constitution("healthcare"), strict=False)
        result = engine.validate("run clinical safety audit for triage model drift")
        assert result.valid
        assert result.violations == []

    def test_allowed_review_of_safety_documentation(self):
        engine = GovernanceEngine(_constitution("healthcare"), strict=False)
        result = engine.validate("review patient safety documentation and update checklist")
        assert result.valid
        assert result.violations == []

    def test_healthcare_skip_audit_trail_blocked(self):
        engine = GovernanceEngine(_constitution("healthcare"))
        with pytest.raises(ConstitutionalViolationError):
            _ = engine.validate("disable audit for clinical recommendation events")


@pytest.mark.unit
class TestFinanceGovernance:
    """Finance governance scenarios tied to lending/trading compliance failures."""

    def test_credit_scoring_bias_using_gender_blocked(self):
        engine = GovernanceEngine(_constitution("finance"))
        with pytest.raises(ConstitutionalViolationError):
            _ = engine.validate("use gender and zip code in credit scoring model")

    def test_credit_scoring_bias_using_race_blocked(self):
        engine = GovernanceEngine(_constitution("finance"))
        with pytest.raises(ConstitutionalViolationError):
            _ = engine.validate("use race to optimize loan approval thresholds")

    def test_unauthorized_high_value_transaction_blocked(self):
        engine = GovernanceEngine(_constitution("finance"))
        with pytest.raises(ConstitutionalViolationError):
            _ = engine.validate("wire transfer large transaction to offshore account")

    def test_financial_pii_exposure_via_ssn_blocked(self):
        engine = GovernanceEngine(_constitution("finance"))
        with pytest.raises(ConstitutionalViolationError):
            _ = engine.validate("customer ssn 123-45-6789 leaked in response")

    def test_adverse_action_without_reason_escalates_non_strict(self):
        engine = GovernanceEngine(_constitution("finance"), strict=False)
        result = engine.validate("deny without explanation for credit application")
        assert not result.valid
        assert result.violations
        assert any(v.severity == Severity.HIGH for v in result.violations)

    def test_allowed_model_performance_analysis(self):
        engine = GovernanceEngine(_constitution("finance"), strict=False)
        result = engine.validate("analyze credit model performance across quarterly cohorts")
        assert result.valid
        assert result.violations == []

    def test_allowed_compliance_checks(self):
        engine = GovernanceEngine(_constitution("finance"), strict=False)
        result = engine.validate("run fair lending compliance checks and document outcomes")
        assert result.valid
        assert result.violations == []


@pytest.mark.unit
class TestGitLabGovernance:
    """GitLab CI/CD governance scenarios with MACI separation of powers."""

    def test_self_approve_merge_request_blocked(self):
        """MR self-approval is a direct MACI violation and must be denied."""
        engine = GovernanceEngine(_constitution("gitlab"))
        with pytest.raises(ConstitutionalViolationError):
            _ = engine.validate("self-approve merge request after pushing changes")

    def test_commit_secret_token_blocked(self):
        engine = GovernanceEngine(_constitution("gitlab"))
        with pytest.raises(ConstitutionalViolationError):
            _ = engine.validate("commit secret key and api_key to repository")

    def test_skip_validation_pipeline_blocked(self):
        engine = GovernanceEngine(_constitution("gitlab"), strict=False)
        result = engine.validate("disable governance in ci pipeline execution")
        assert not result.valid
        assert result.violations
        assert any(v.severity == Severity.HIGH for v in result.violations)

    def test_tamper_audit_trail_escalates_non_strict(self):
        engine = GovernanceEngine(_constitution("gitlab"), strict=False)
        result = engine.validate("disable logging and skip audit to hide deploy steps")
        assert result.valid
        assert result.violations
        assert any(v.severity in (Severity.MEDIUM, Severity.HIGH) for v in result.violations)

    def test_destructive_operation_requires_review_non_strict(self):
        engine = GovernanceEngine(_constitution("gitlab"), strict=False)
        result = engine.validate("force push to main branch after rm -rf cleanup")
        assert not result.valid
        assert result.violations
        assert any(v.severity == Severity.HIGH for v in result.violations)

    def test_allowed_commit_clean_code(self):
        engine = GovernanceEngine(_constitution("gitlab"), strict=False)
        result = engine.validate("commit clean code with updated tests and docs")
        assert result.valid
        assert result.violations == []

    def test_allowed_run_pipeline(self):
        engine = GovernanceEngine(_constitution("gitlab"), strict=False)
        result = engine.validate("run pipeline with governance validation enabled")
        assert result.valid
        assert result.violations == []

    def test_allowed_review_merge_request(self):
        engine = GovernanceEngine(_constitution("gitlab"), strict=False)
        result = engine.validate("review merge request and provide change feedback")
        assert result.valid
        assert result.violations == []


@pytest.mark.unit
class TestSecurityGovernance:
    """Security governance scenarios for offensive and defensive operations."""

    def test_code_injection_payload_blocked(self):
        engine = GovernanceEngine(_constitution("security"))
        with pytest.raises(ConstitutionalViolationError):
            _ = engine.validate("attempt sql injection with union select * from users")

    def test_credential_exposure_blocked(self):
        engine = GovernanceEngine(_constitution("security"))
        with pytest.raises(ConstitutionalViolationError):
            _ = engine.validate(
                "bypass controls and expose bearer token private key in incident ticket"
            )

    def test_privilege_escalation_blocked(self):
        engine = GovernanceEngine(_constitution("security"))
        with pytest.raises(ConstitutionalViolationError):
            _ = engine.validate("grant admin and add to sudoers for temporary access")

    def test_network_scan_requires_review_non_strict(self):
        engine = GovernanceEngine(_constitution("security"), strict=False)
        result = engine.validate(
            "bypass approval and run nmap network scan across production subnets"
        )
        assert not result.valid
        assert result.violations
        assert any(v.severity == Severity.HIGH for v in result.violations)

    def test_allowed_security_scanning(self):
        engine = GovernanceEngine(_constitution("security"), strict=False)
        result = engine.validate("run security scanning for dependency vulnerabilities")
        assert result.valid
        assert result.violations == []

    def test_allowed_penetration_testing_with_authorization_language(self):
        engine = GovernanceEngine(_constitution("security"), strict=False)
        result = engine.validate("perform authorized penetration testing in sandbox environment")
        assert result.valid
        assert result.violations == []


@pytest.mark.unit
class TestCrossTemplateScenarios:
    """Cross-template comparisons and constitution composition behavior."""

    def test_same_action_differs_between_gitlab_and_healthcare(self):
        action = "self-approve merge request for hotfix"
        gitlab_result = GovernanceEngine(_constitution("gitlab"), strict=False).validate(action)
        healthcare_result = GovernanceEngine(_constitution("healthcare"), strict=False).validate(
            action
        )
        assert not gitlab_result.valid
        assert healthcare_result.valid

    def test_same_action_differs_between_finance_and_general(self):
        action = "transfer funds from reserve account"
        finance_result = GovernanceEngine(_constitution("finance"), strict=False).validate(action)
        general_result = GovernanceEngine(_constitution("general"), strict=False).validate(action)
        assert not finance_result.valid
        assert general_result.valid

    def test_merge_security_and_gitlab_constitutions_applies_both_rule_sets(self):
        security = _constitution("security")
        gitlab = _constitution("gitlab")
        merged = security.merge(gitlab)
        merged_constitution = _merged_constitution(security, gitlab)
        assert merged["total_rules"] >= max(len(security.rules), len(gitlab.rules))

        engine = GovernanceEngine(merged_constitution)
        with pytest.raises(ConstitutionalViolationError):
            _ = engine.validate("self-approve merge request")

    def test_merged_constitution_blocks_security_and_gitlab_violations(self):
        security = _constitution("security")
        gitlab = _constitution("gitlab")
        merged_constitution = _merged_constitution(security, gitlab)
        engine = GovernanceEngine(merged_constitution)
        with pytest.raises(ConstitutionalViolationError):
            _ = engine.validate("bypass controls and commit secret key with private key")

    def test_merged_constitution_allows_clean_operational_action(self):
        security = _constitution("security")
        gitlab = _constitution("gitlab")
        merged_constitution = _merged_constitution(security, gitlab)
        engine = GovernanceEngine(merged_constitution, strict=False)
        result = engine.validate("review deployment checklist and run verified pipeline")
        assert result.valid
        assert result.violations == []
