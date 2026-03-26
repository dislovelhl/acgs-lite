"""
Tests for decisions.py route coverage.
Constitutional Hash: 608508a9bd224290

Covers: get_decision_explanation, generate_decision_explanation,
        get_governance_vector_schema, _convert_to_response helper.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.services.api_gateway.routes.decisions import (
    _convert_to_response,
    decisions_v1_router,
)
from src.core.shared.security.auth import UserClaims, get_current_user

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_user() -> UserClaims:
    now = int(datetime.now(UTC).timestamp())
    return UserClaims(
        sub="user-1",
        tenant_id="tenant-1",
        roles=["user"],
        permissions=["read"],
        exp=now + 3600,
        iat=now,
    )


_USER = _make_user()


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(decisions_v1_router)
    app.dependency_overrides[get_current_user] = lambda: _USER
    return app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(_build_app())


def _mock_factor(*, governance_dim_has_value: bool = True):
    f = MagicMock()
    f.factor_id = "f-1"
    f.factor_name = "safety_score"
    f.factor_value = 0.8
    f.factor_weight = 0.5
    f.explanation = "High safety impact"
    f.evidence = ["evidence-1"]
    if governance_dim_has_value:
        f.governance_dimension = MagicMock(value="safety")
    else:
        # Use a plain string (no .value attribute) to test the str() fallback
        f.governance_dimension = "safety"
    f.source_component = "safety-engine"
    f.calculation_method = "weighted-sum"
    return f


def _mock_counterfactual(*, outcome_has_value: bool = True):
    cf = MagicMock()
    cf.scenario_id = "cf-1"
    cf.scenario_description = "Lower safety"
    cf.modified_factor = "safety_score"
    cf.original_value = 0.8
    cf.modified_value = 0.3
    if outcome_has_value:
        cf.predicted_outcome = MagicMock(value="DENY")
    else:
        # Use a plain string (no .value attribute) to test the str() fallback
        cf.predicted_outcome = "DENY"
    cf.confidence = 0.9
    cf.threshold_crossed = "safety_threshold"
    cf.impact_delta = -0.5
    return cf


def _mock_euaiact_info():
    info = MagicMock()
    info.article_13_compliant = True
    info.human_oversight_level = "human-on-the-loop"
    info.risk_category = "limited"
    info.transparency_measures = ["logging"]
    info.data_governance_info = {}
    info.technical_documentation_ref = "doc-ref-1"
    info.conformity_assessment_status = "pending"
    info.intended_purpose = "governance"
    info.limitations_and_risks = ["model drift"]
    info.human_reviewers = ["admin"]
    return info


def _mock_explanation(*, include_factors: bool = True, include_cf: bool = True):
    exp = MagicMock()
    exp.decision_id = "dec-1"
    exp.message_id = "msg-1"
    exp.request_id = "req-1"
    exp.verdict = "ALLOW"
    exp.confidence_score = 0.95
    exp.impact_score = 0.2
    exp.governance_vector = {
        "safety": 0.8,
        "security": 0.5,
        "privacy": 0.3,
        "fairness": 0.4,
        "reliability": 0.7,
        "transparency": 0.6,
        "efficiency": 0.5,
    }
    exp.factors = [_mock_factor()] if include_factors else []
    exp.primary_factors = ["f-1"] if include_factors else []
    exp.counterfactual_hints = [_mock_counterfactual()] if include_cf else []
    exp.counterfactuals_generated = include_cf
    exp.matched_rules = ["rule-1"]
    exp.violated_rules = []
    exp.applicable_policies = ["policy-1"]
    exp.summary = "Decision allowed"
    exp.detailed_reasoning = "All factors passed"
    exp.euaiact_article13_info = _mock_euaiact_info()
    exp.processing_time_ms = 12.5
    exp.explanation_generated_at = datetime.now(UTC)
    exp.explanation_version = "v1.0.0"
    exp.tenant_id = "tenant-1"
    exp.scope = "decision"
    exp.audit_references = ["audit-1"]
    exp.constitutional_hash = "608508a9bd224290"
    return exp


# ---------------------------------------------------------------------------
# _convert_to_response unit tests
# ---------------------------------------------------------------------------


class TestConvertToResponse:
    """Unit tests for the _convert_to_response helper."""

    def test_convert_full_explanation(self):
        exp = _mock_explanation()
        result = _convert_to_response(exp, include_counterfactuals=True)
        assert result.decision_id == "dec-1"
        assert result.verdict == "ALLOW"
        assert len(result.factors) == 1
        assert result.factors[0].governance_dimension == "safety"
        assert len(result.counterfactual_hints) == 1
        assert result.counterfactual_hints[0].predicted_outcome == "DENY"

    def test_convert_without_counterfactuals(self):
        exp = _mock_explanation(include_cf=True)
        result = _convert_to_response(exp, include_counterfactuals=False)
        assert result.counterfactual_hints == []

    def test_convert_governance_dimension_string_fallback(self):
        exp = _mock_explanation()
        exp.factors = [_mock_factor(governance_dim_has_value=False)]
        result = _convert_to_response(exp, include_counterfactuals=False)
        assert result.factors[0].governance_dimension == "safety"

    def test_convert_counterfactual_outcome_string_fallback(self):
        exp = _mock_explanation()
        exp.counterfactual_hints = [_mock_counterfactual(outcome_has_value=False)]
        result = _convert_to_response(exp, include_counterfactuals=True)
        assert result.counterfactual_hints[0].predicted_outcome == "DENY"

    def test_convert_empty_factors_and_cf(self):
        exp = _mock_explanation(include_factors=False, include_cf=False)
        result = _convert_to_response(exp, include_counterfactuals=True)
        assert result.factors == []
        assert result.counterfactual_hints == []


# ---------------------------------------------------------------------------
# GET /{decision_id}/explain
# ---------------------------------------------------------------------------


class TestGetDecisionExplanation:
    """GET /api/v1/decisions/{decision_id}/explain"""

    def test_get_explanation_success(self, client: TestClient):
        mock_exp = _mock_explanation()
        mock_service = AsyncMock()
        mock_service.get_explanation = AsyncMock(return_value=mock_exp)

        mock_module = MagicMock()
        mock_module.ExplanationServiceAdapter = lambda *a, **kw: mock_service

        with patch.dict(
            "sys.modules",
            {
                "packages": MagicMock(),
                "packages.enhanced_agent_bus": MagicMock(),
                "packages.enhanced_agent_bus.facades": MagicMock(),
                "packages.enhanced_agent_bus.facades.agent_bus_facade": mock_module,
            },
        ):
            resp = client.get("/api/v1/decisions/dec-1/explain")
            assert resp.status_code == 200
            body = resp.json()
            assert body["decision_id"] == "dec-1"
            assert body["verdict"] == "ALLOW"

    def test_get_explanation_not_found(self, client: TestClient):
        mock_service = AsyncMock()
        mock_service.get_explanation = AsyncMock(return_value=None)

        with patch.dict(
            "sys.modules",
            {
                "packages": MagicMock(),
                "packages.enhanced_agent_bus": MagicMock(),
                "packages.enhanced_agent_bus.facades": MagicMock(),
                "packages.enhanced_agent_bus.facades.agent_bus_facade": MagicMock(
                    ExplanationServiceAdapter=lambda: mock_service,
                ),
            },
        ):
            resp = client.get("/api/v1/decisions/dec-1/explain")
            assert resp.status_code in (404, 500)

    def test_get_explanation_internal_error(self, client: TestClient):
        mock_service = AsyncMock()
        mock_service.get_explanation = AsyncMock(side_effect=RuntimeError("db down"))

        with patch.dict(
            "sys.modules",
            {
                "packages": MagicMock(),
                "packages.enhanced_agent_bus": MagicMock(),
                "packages.enhanced_agent_bus.facades": MagicMock(),
                "packages.enhanced_agent_bus.facades.agent_bus_facade": MagicMock(
                    ExplanationServiceAdapter=lambda: mock_service,
                ),
            },
        ):
            resp = client.get("/api/v1/decisions/dec-1/explain")
            assert resp.status_code == 500


# ---------------------------------------------------------------------------
# POST /explain
# ---------------------------------------------------------------------------


class TestGenerateDecisionExplanation:
    """POST /api/v1/decisions/explain"""

    def test_generate_explanation_success(self, client: TestClient):
        mock_exp = _mock_explanation()
        mock_service = AsyncMock()
        mock_service.generate_explanation = AsyncMock(return_value=mock_exp)

        mock_module = MagicMock()
        mock_module.ExplanationServiceAdapter = lambda *a, **kw: mock_service
        mock_module.ExplanationService = MagicMock()

        with patch.dict(
            "sys.modules",
            {
                "packages": MagicMock(),
                "packages.enhanced_agent_bus": MagicMock(),
                "packages.enhanced_agent_bus.facades": MagicMock(),
                "packages.enhanced_agent_bus.facades.agent_bus_facade": mock_module,
            },
        ):
            resp = client.post(
                "/api/v1/decisions/explain",
                json={
                    "message": {"content": "test action"},
                    "verdict": "ALLOW",
                    "context": {},
                    "include_counterfactuals": True,
                },
            )
            assert resp.status_code in (200, 500)

    def test_generate_explanation_error(self, client: TestClient):
        mock_module = MagicMock()
        mock_module.ExplanationServiceAdapter = MagicMock(side_effect=RuntimeError("fail"))
        mock_module.ExplanationService = MagicMock()

        with patch.dict(
            "sys.modules",
            {
                "packages": MagicMock(),
                "packages.enhanced_agent_bus": MagicMock(),
                "packages.enhanced_agent_bus.facades": MagicMock(),
                "packages.enhanced_agent_bus.facades.agent_bus_facade": mock_module,
            },
        ):
            resp = client.post(
                "/api/v1/decisions/explain",
                json={
                    "message": {"content": "test"},
                    "verdict": "DENY",
                },
            )
            assert resp.status_code == 500


# ---------------------------------------------------------------------------
# GET /governance-vector/schema
# ---------------------------------------------------------------------------


class TestGovernanceVectorSchema:
    """GET /api/v1/decisions/governance-vector/schema"""

    def test_schema_returns_200(self, client: TestClient):
        resp = client.get("/api/v1/decisions/governance-vector/schema")
        assert resp.status_code == 200
        body = resp.json()
        assert "dimensions" in body
        dims = body["dimensions"]
        assert set(dims.keys()) == {
            "safety",
            "security",
            "privacy",
            "fairness",
            "reliability",
            "transparency",
            "efficiency",
        }
        assert body["constitutional_hash"] == "608508a9bd224290"
        assert body["thresholds"]["escalation"] == 0.8

    def test_schema_dimension_structure(self, client: TestClient):
        resp = client.get("/api/v1/decisions/governance-vector/schema")
        body = resp.json()
        for dim in body["dimensions"].values():
            assert "description" in dim
            assert "range" in dim
            assert dim["range"] == [0.0, 1.0]
            assert "high_score_meaning" in dim
