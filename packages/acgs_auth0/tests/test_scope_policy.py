"""Unit tests for MACIScopePolicy — constitutional scope validation.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import pytest

from acgs_auth0.exceptions import ConstitutionalScopeViolation, MACIRoleNotPermittedError
from acgs_auth0.scope_policy import (
    ConnectionScopeRule,
    MACIScopePolicy,
    ScopeRiskLevel,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def policy() -> MACIScopePolicy:
    """Minimal policy for tests."""
    rules = [
        # EXECUTIVE: read GitHub, no write
        ConnectionScopeRule(
            connection="github",
            role="EXECUTIVE",
            permitted_scopes=["read:user", "repo:read"],
            high_risk_scopes=[],
        ),
        # IMPLEMENTER: read + write GitHub (write requires step-up)
        ConnectionScopeRule(
            connection="github",
            role="IMPLEMENTER",
            permitted_scopes=["read:user", "repo:read", "repo:write"],
            high_risk_scopes=["repo:write"],
        ),
        # EXECUTIVE: Google Calendar read-only
        ConnectionScopeRule(
            connection="google-oauth2",
            role="EXECUTIVE",
            permitted_scopes=[
                "openid",
                "https://www.googleapis.com/auth/calendar.freebusy",
            ],
            high_risk_scopes=[],
        ),
        # IMPLEMENTER: Google Calendar full access (write requires step-up)
        ConnectionScopeRule(
            connection="google-oauth2",
            role="IMPLEMENTER",
            permitted_scopes=[
                "openid",
                "https://www.googleapis.com/auth/calendar",
            ],
            high_risk_scopes=["https://www.googleapis.com/auth/calendar"],
        ),
    ]
    return MACIScopePolicy(rules=rules)


# ---------------------------------------------------------------------------
# ConnectionScopeRule
# ---------------------------------------------------------------------------


class TestConnectionScopeRule:
    def test_is_permitted_positive(self) -> None:
        rule = ConnectionScopeRule(
            connection="github",
            role="EXECUTIVE",
            permitted_scopes=["read:user", "repo:read"],
        )
        assert rule.is_permitted("read:user")
        assert rule.is_permitted("repo:read")

    def test_is_permitted_negative(self) -> None:
        rule = ConnectionScopeRule(
            connection="github",
            role="EXECUTIVE",
            permitted_scopes=["read:user"],
        )
        assert not rule.is_permitted("repo:write")

    def test_requires_step_up(self) -> None:
        rule = ConnectionScopeRule(
            connection="github",
            role="IMPLEMENTER",
            permitted_scopes=["repo:read", "repo:write"],
            high_risk_scopes=["repo:write"],
        )
        assert rule.requires_step_up("repo:write")
        assert not rule.requires_step_up("repo:read")

    def test_denied_scopes(self) -> None:
        rule = ConnectionScopeRule(
            connection="github",
            role="EXECUTIVE",
            permitted_scopes=["read:user", "repo:read"],
        )
        denied = rule.denied_scopes(["read:user", "repo:write"])
        assert denied == ["repo:write"]

    def test_step_up_scopes(self) -> None:
        rule = ConnectionScopeRule(
            connection="github",
            role="IMPLEMENTER",
            permitted_scopes=["repo:read", "repo:write"],
            high_risk_scopes=["repo:write"],
        )
        assert rule.step_up_scopes(["repo:read", "repo:write"]) == ["repo:write"]
        assert rule.step_up_scopes(["repo:read"]) == []


# ---------------------------------------------------------------------------
# MACIScopePolicy — construction
# ---------------------------------------------------------------------------


class TestMACIScopePolicyConstruction:
    def test_get_rule_found(self, policy: MACIScopePolicy) -> None:
        rule = policy.get_rule(connection="github", role="EXECUTIVE")
        assert rule is not None
        assert rule.role == "EXECUTIVE"

    def test_get_rule_not_found(self, policy: MACIScopePolicy) -> None:
        rule = policy.get_rule(connection="github", role="JUDICIAL")
        assert rule is None

    def test_is_connection_permitted_true(self, policy: MACIScopePolicy) -> None:
        assert policy.is_connection_permitted(connection="github", role="EXECUTIVE")

    def test_is_connection_permitted_false(self, policy: MACIScopePolicy) -> None:
        assert not policy.is_connection_permitted(connection="slack", role="EXECUTIVE")

    def test_permissive_policy_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging

        with caplog.at_level(logging.WARNING, logger="acgs_auth0.scope_policy"):
            p = MACIScopePolicy.permissive()
        assert "permissive" in caplog.text.lower() or "PERMISSIVE" in p.constitutional_hash


# ---------------------------------------------------------------------------
# MACIScopePolicy.validate()
# ---------------------------------------------------------------------------


class TestMACIScopePolicyValidate:
    def test_permitted_read_scopes(self, policy: MACIScopePolicy) -> None:
        result = policy.validate(
            agent_id="planner",
            role="EXECUTIVE",
            connection="github",
            requested_scopes=["read:user", "repo:read"],
        )
        assert result.permitted is True
        assert result.denied_scopes == []
        assert result.step_up_required == []
        assert result.error is None

    def test_denied_write_scope_for_executive(self, policy: MACIScopePolicy) -> None:
        result = policy.validate(
            agent_id="planner",
            role="EXECUTIVE",
            connection="github",
            requested_scopes=["repo:write"],
        )
        assert result.permitted is False
        assert "repo:write" in result.denied_scopes
        assert isinstance(result.error, ConstitutionalScopeViolation)

    def test_role_not_permitted_for_connection(self, policy: MACIScopePolicy) -> None:
        result = policy.validate(
            agent_id="validator",
            role="JUDICIAL",
            connection="github",
            requested_scopes=["read:user"],
        )
        assert result.permitted is False
        assert isinstance(result.error, MACIRoleNotPermittedError)
        assert result.error.role == "JUDICIAL"
        assert result.error.connection == "github"

    def test_step_up_required_for_high_risk_scope(self, policy: MACIScopePolicy) -> None:
        result = policy.validate(
            agent_id="executor",
            role="IMPLEMENTER",
            connection="github",
            requested_scopes=["repo:read", "repo:write"],
        )
        assert result.permitted is True
        assert result.step_up_required == ["repo:write"]

    def test_mixed_permitted_and_denied_returns_denied(
        self, policy: MACIScopePolicy
    ) -> None:
        result = policy.validate(
            agent_id="planner",
            role="EXECUTIVE",
            connection="github",
            requested_scopes=["read:user", "repo:write"],
        )
        assert result.permitted is False
        assert "repo:write" in result.denied_scopes

    def test_google_calendar_read_permitted(self, policy: MACIScopePolicy) -> None:
        result = policy.validate(
            agent_id="planner",
            role="EXECUTIVE",
            connection="google-oauth2",
            requested_scopes=[
                "openid",
                "https://www.googleapis.com/auth/calendar.freebusy",
            ],
        )
        assert result.permitted is True

    def test_google_calendar_write_triggers_step_up(
        self, policy: MACIScopePolicy
    ) -> None:
        result = policy.validate(
            agent_id="executor",
            role="IMPLEMENTER",
            connection="google-oauth2",
            requested_scopes=["https://www.googleapis.com/auth/calendar"],
        )
        assert result.permitted is True
        assert "https://www.googleapis.com/auth/calendar" in result.step_up_required


# ---------------------------------------------------------------------------
# ScopeRiskLevel classification
# ---------------------------------------------------------------------------


class TestScopeRiskClassification:
    def test_known_low_risk(self, policy: MACIScopePolicy) -> None:
        assert policy.classify_risk("repo:read") == ScopeRiskLevel.LOW
        assert policy.classify_risk("openid") == ScopeRiskLevel.LOW

    def test_known_high_risk(self, policy: MACIScopePolicy) -> None:
        assert policy.classify_risk("repo:write") == ScopeRiskLevel.HIGH
        assert policy.classify_risk("https://www.googleapis.com/auth/calendar") == ScopeRiskLevel.HIGH

    def test_known_critical(self, policy: MACIScopePolicy) -> None:
        assert policy.classify_risk("delete_repo") == ScopeRiskLevel.CRITICAL

    def test_unknown_scope_defaults_to_medium(self, policy: MACIScopePolicy) -> None:
        assert policy.classify_risk("totally:unknown:scope") == ScopeRiskLevel.MEDIUM

    def test_register_custom_risk(self, policy: MACIScopePolicy) -> None:
        policy.register_scope_risk("custom:dangerous", ScopeRiskLevel.CRITICAL)
        assert policy.classify_risk("custom:dangerous") == ScopeRiskLevel.CRITICAL


# ---------------------------------------------------------------------------
# YAML loading
# ---------------------------------------------------------------------------


class TestMACIScopePolicyFromYAML:
    def test_load_from_yaml(self, tmp_path: pytest.TempPathFactory) -> None:
        yaml_content = """
token_vault:
  constitutional_hash: "608508a9bd224290"
  connections:
    github:
      EXECUTIVE:
        permitted_scopes: ["read:user", "repo:read"]
        high_risk_scopes: []
      IMPLEMENTER:
        permitted_scopes: ["read:user", "repo:read", "repo:write"]
        high_risk_scopes: ["repo:write"]
"""
        yaml_file = tmp_path / "constitution.yaml"
        yaml_file.write_text(yaml_content)

        policy = MACIScopePolicy.from_yaml(yaml_file)
        assert policy.constitutional_hash == "608508a9bd224290"
        rule = policy.get_rule(connection="github", role="EXECUTIVE")
        assert rule is not None
        assert "repo:read" in rule.permitted_scopes

    def test_load_from_yaml_without_pyyaml(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import acgs_auth0.scope_policy as sp

        monkeypatch.setattr(sp, "YAML_AVAILABLE", False)
        with pytest.raises(ImportError, match="PyYAML"):
            MACIScopePolicy.from_yaml("anything.yaml")
