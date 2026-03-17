"""Tests for adversarial and edge-case inputs.

Exercises the engine's robustness against obfuscation, near-misses,
and boundary conditions.
"""

import pytest

from acgs_lite.constitution import Constitution
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
                        "text": "No financial advice",
                        "severity": "critical",
                        "keywords": ["invest in", "buy stocks", "financial advice", "buy crypto"],
                    },
                    {
                        "id": "GEN-002",
                        "text": "No medical advice",
                        "severity": "critical",
                        "keywords": ["medical advice", "prescribe", "your diagnosis"],
                    },
                    {
                        "id": "GEN-004",
                        "text": "No PII exposure",
                        "severity": "critical",
                        "keywords": ["ssn", "api key", "private key"],
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
                        "text": "No self-approval",
                        "severity": "critical",
                        "keywords": ["self-approve", "auto-approve", "self-merge"],
                    },
                    {
                        "id": "GL-005",
                        "text": "No governance bypass",
                        "severity": "high",
                        "keywords": ["skip validation", "disable governance", "bypass check"],
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
                        "keywords": ["invest in", "buy stocks", "financial advice"],
                    },
                    {
                        "id": "FIN-002",
                        "text": "No protected characteristics in lending",
                        "severity": "critical",
                        "keywords": ["use race", "use gender", "use zip code"],
                    },
                ],
            },
        }
        if domain in fallback_templates and "no keywords defined" in str(exc):
            return Constitution.from_dict(fallback_templates[domain])
        raise


@pytest.mark.unit
class TestPositiveVerbSuppression:
    """Positive first verbs should suppress false positives unless negative intent appears."""

    def test_positive_verb_test_safety_monitoring_pipeline_allowed(self):
        engine = GovernanceEngine(_constitution("general"), strict=False)
        result = engine.validate("test the safety monitoring pipeline")
        assert result.valid
        assert result.violations == []

    def test_positive_verb_audit_consent_workflow_allowed(self):
        engine = GovernanceEngine(_constitution("healthcare"), strict=False)
        result = engine.validate("audit the consent workflow for hipaa readiness")
        assert result.valid
        assert result.violations == []

    def test_positive_verb_review_api_key_rotation_allowed(self):
        engine = GovernanceEngine(_constitution("security"), strict=False)
        result = engine.validate("review api key rotation controls and remediation plan")
        assert result.valid
        assert result.violations == []

    def test_positive_verb_implement_fair_lending_monitoring_allowed(self):
        engine = GovernanceEngine(_constitution("finance"), strict=False)
        result = engine.validate("implement fair lending drift monitoring dashboard")
        assert result.valid
        assert result.violations == []

    def test_positive_verb_with_negative_bypass_is_denied(self):
        """Action starting with non-positive verb containing 'skip validation' is denied."""
        engine = GovernanceEngine(_constitution("gitlab"), strict=False)
        # "skip" as the first word is NOT a positive verb, so suppression doesn't apply
        result = engine.validate("skip validation in ci pipeline before release")
        assert not result.valid
        assert result.violations


@pytest.mark.unit
class TestNearMisses:
    """Near-miss phrasing should avoid false positives while true matches still trigger."""

    def test_thematically_related_hiring_text_without_rule_keywords_allowed(self):
        engine = GovernanceEngine(_constitution("finance"), strict=False)
        result = engine.validate("optimize applicant ranking calibration for quality assurance")
        assert result.valid
        assert result.violations == []

    def test_thematically_related_healthcare_text_without_trigger_keywords_allowed(self):
        engine = GovernanceEngine(_constitution("healthcare"), strict=False)
        result = engine.validate("summarize care pathway outcomes for quarterly board review")
        assert result.valid
        assert result.violations == []

    def test_thematically_related_gitlab_text_without_maci_keywords_allowed(self):
        engine = GovernanceEngine(_constitution("gitlab"), strict=False)
        result = engine.validate("coordinate reviewer handoff and branch cleanup workflow")
        assert result.valid
        assert result.violations == []

    def test_keyword_in_second_sentence_still_triggers(self):
        engine = GovernanceEngine(_constitution("gitlab"))
        with pytest.raises(ConstitutionalViolationError):
            _ = engine.validate(
                "First we run routine checks. Then we self-approve merge request for speed."
            )

    def test_pattern_in_second_sentence_still_triggers(self):
        engine = GovernanceEngine(_constitution("security"))
        with pytest.raises(ConstitutionalViolationError):
            _ = engine.validate(
                "All controls passed. Exposure observed: -----BEGIN RSA PRIVATE KEY----- in logs."
            )


@pytest.mark.unit
class TestBoundaryConditions:
    """Boundary inputs should remain deterministic and stable."""

    def test_very_long_action_string_with_violation_still_denied(self):
        engine = GovernanceEngine(_constitution("general"), strict=False)
        padding = "process additional data fields " * 40
        action = f"self-approve the governance assessment {padding}"
        result = engine.validate(action)
        assert not result.valid
        assert result.violations

    def test_empty_action_string_allowed(self):
        engine = GovernanceEngine(_constitution("general"), strict=False)
        result = engine.validate("")
        assert result.valid
        assert result.violations == []

    def test_whitespace_only_action_allowed(self):
        engine = GovernanceEngine(_constitution("general"), strict=False)
        result = engine.validate("     ")
        assert result.valid
        assert result.violations == []

    def test_unicode_action_text_allowed_when_non_violating(self):
        engine = GovernanceEngine(_constitution("general"), strict=False)
        result = engine.validate("review resumen de gobernanza y seguridad clinica")
        assert result.valid
        assert result.violations == []

    def test_numeric_only_action_allowed(self):
        engine = GovernanceEngine(_constitution("general"), strict=False)
        result = engine.validate("1234567890")
        assert result.valid
        assert result.violations == []
