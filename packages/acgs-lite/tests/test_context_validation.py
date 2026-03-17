"""Tests for context-dependent governance validation.

Exercises the engine's ability to evaluate actions using context
metadata (action_detail, action_description, env, risk).
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
                        "keywords": ["invest in", "buy stocks", "financial advice"],
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
                        "text": "No validation bypass",
                        "severity": "high",
                        "keywords": ["skip validation", "disable governance", "bypass check"],
                    },
                    {
                        "id": "GL-006",
                        "text": "Audit trail required",
                        "severity": "medium",
                        "keywords": ["no-audit", "skip audit", "disable logging"],
                    },
                ],
            },
            "finance": {
                "name": "finance-fallback",
                "rules": [
                    {
                        "id": "FIN-002",
                        "text": "No protected characteristics",
                        "severity": "critical",
                        "keywords": ["use race", "use gender", "use zip code"],
                    },
                    {
                        "id": "FIN-003",
                        "text": "Credit denials require reasons",
                        "severity": "high",
                        "keywords": ["deny without explanation", "reject silently", "no reason"],
                    },
                ],
            },
        }
        if domain in fallback_templates and "no keywords defined" in str(exc):
            return Constitution.from_dict(fallback_templates[domain])
        raise


@pytest.mark.unit
class TestContextDetectsViolation:
    """Context fields should trigger violations even with clean action text."""

    def test_clean_action_with_violating_action_detail_is_denied(self):
        """Violating context must block even when action text is clean."""
        engine = GovernanceEngine(_constitution("security"))
        with pytest.raises(ConstitutionalViolationError):
            _ = engine.validate(
                "review weekly security report",
                context={"action_detail": "execute sql injection payload against endpoint"},
            )

    def test_clean_action_with_violating_action_description_is_denied(self):
        engine = GovernanceEngine(_constitution("gitlab"))
        with pytest.raises(ConstitutionalViolationError):
            _ = engine.validate(
                "review merge request",
                context={"action_description": "self-approve merge request after review"},
            )

    def test_context_description_credential_exposure_is_denied(self):
        engine = GovernanceEngine(_constitution("security"))
        with pytest.raises(ConstitutionalViolationError):
            _ = engine.validate(
                "assess secrets policy",
                context={
                    "action_description": "bypass controls and expose private key in release notes"
                },
            )

    def test_context_action_detail_credit_bias_is_denied(self):
        engine = GovernanceEngine(_constitution("finance"))
        with pytest.raises(ConstitutionalViolationError):
            _ = engine.validate(
                "evaluate lending controls",
                context={"action_detail": "use race and gender for approval ranking"},
            )

    def test_context_action_description_phi_without_consent_is_denied(self):
        engine = GovernanceEngine(_constitution("healthcare"))
        with pytest.raises(ConstitutionalViolationError):
            _ = engine.validate(
                "review clinical quality metrics",
                context={"action_description": "share patient data without consent"},
            )


@pytest.mark.unit
class TestContextAllowsAction:
    """Constructive context metadata should keep safe actions allowed."""

    def test_context_constructive_action_detail_allows_action(self):
        engine = GovernanceEngine(_constitution("security"), strict=False)
        result = engine.validate(
            "run monitoring review",
            context={"action_detail": "run authorized security scan in sandbox"},
        )
        assert result.valid
        assert result.violations == []

    def test_context_constructive_action_description_allows_action(self):
        engine = GovernanceEngine(_constitution("gitlab"), strict=False)
        result = engine.validate(
            "review merge request",
            context={"action_description": "run governance validation and review pipeline logs"},
        )
        assert result.valid
        assert result.violations == []

    def test_context_with_env_staging_and_risk_low_allows(self):
        engine = GovernanceEngine(_constitution("general"), strict=False)
        result = engine.validate(
            "update governance dashboard",
            context={"env": "staging", "risk": "low", "ticket": "GOV-123"},
        )
        assert result.valid
        assert result.violations == []

    def test_context_with_metadata_plus_safe_action_detail_allows(self):
        engine = GovernanceEngine(_constitution("finance"), strict=False)
        result = engine.validate(
            "review compliance posture",
            context={
                "action_detail": "analyze model performance metrics for bias monitoring",
                "env": "staging",
                "risk": "low",
                "owner": "risk-team",
            },
        )
        assert result.valid
        assert result.violations == []

    def test_context_with_safe_action_description_and_trace_metadata_allows(self):
        engine = GovernanceEngine(_constitution("healthcare"), strict=False)
        result = engine.validate(
            "prepare governance summary",
            context={
                "action_description": "review safety docs and audit workflow conformance",
                "trace_id": "abc-123",
                "env": "staging",
            },
        )
        assert result.valid
        assert result.violations == []


@pytest.mark.unit
class TestContextEdgeCases:
    """Edge conditions for context payload handling and default behavior."""

    def test_empty_context_matches_baseline_behavior(self):
        engine = GovernanceEngine(_constitution("general"), strict=False)
        baseline = engine.validate("review governance changelog")
        with_empty_context = engine.validate("review governance changelog", context={})
        assert baseline.valid == with_empty_context.valid
        assert baseline.violations == with_empty_context.violations

    def test_non_string_context_values_are_ignored(self):
        engine = GovernanceEngine(_constitution("security"), strict=False)
        result = engine.validate(
            "review security posture",
            context={"action_detail": {"nested": "exec(payload)"}, "risk": 0.1},
        )
        assert result.valid
        assert result.violations == []

    def test_context_only_metadata_fields_scans_only_action(self):
        engine = GovernanceEngine(_constitution("gitlab"), strict=False)
        result = engine.validate(
            "review merge request checklist",
            context={"env": "production", "risk": "high", "phase": "deploy"},
        )
        assert result.valid
        assert result.violations == []

    def test_context_action_detail_non_string_does_not_trigger(self):
        engine = GovernanceEngine(_constitution("finance"), strict=False)
        result = engine.validate(
            "assess controls",
            context={"action_detail": ["use race for approvals"], "env": "prod"},
        )
        assert result.valid
        assert result.violations == []

    def test_context_action_description_empty_string_keeps_action_baseline(self):
        engine = GovernanceEngine(_constitution("healthcare"), strict=False)
        result = engine.validate(
            "review patient safety workflow",
            context={"action_description": "", "env": "staging", "risk": "low"},
        )
        assert result.valid
        assert result.violations == []
