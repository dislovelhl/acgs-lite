# Constitutional Hash: 608508a9bd224290
"""
Comprehensive test coverage for policy_copilot/api.py.

Targets ≥90% coverage of the API routes, dependency providers,
helper models, and error handling paths.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus._compat.errors import ValidationError
from enhanced_agent_bus._compat.security.auth import UserClaims, get_current_user
from enhanced_agent_bus.policy_copilot.api import (
    FeedbackRequest,
    FeedbackResponse,
    HealthResponse,
    TemplateListResponse,
    get_nlp_engine,
    get_policy_validator,
    get_rego_generator,
    router,
)
from enhanced_agent_bus.policy_copilot.models import (
    PolicyEntity,
    PolicyEntityType,
    PolicyResult,
    PolicyTemplate,
    PolicyTemplateCategory,
    TestResult,
    ValidationResult,
)

# ---------------------------------------------------------------------------
# App fixture
# ---------------------------------------------------------------------------


class SyncASGIClient:
    """Synchronous wrapper around httpx ASGI transport for deterministic tests."""

    def __init__(self, app, raise_server_exceptions: bool = True) -> None:
        self._app = app
        self._raise = raise_server_exceptions

    def request(self, method: str, url: str, **kwargs):
        async def _call():
            transport = httpx.ASGITransport(
                app=self._app,
                raise_app_exceptions=self._raise,
            )
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
                return await c.request(method, url, **kwargs)

        return asyncio.run(_call())

    def get(self, url: str, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs):
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs):
        return self.request("PUT", url, **kwargs)

    def delete(self, url: str, **kwargs):
        return self.request("DELETE", url, **kwargs)


def _mock_user(tenant_id: str = "tenant-test") -> UserClaims:
    return UserClaims(
        sub="user-123",
        tenant_id=tenant_id,
        roles=["agent"],
        permissions=["read", "write"],
        exp=9999999999,
        iat=1000000000,
        iss="acgs2",
        constitutional_hash=CONSTITUTIONAL_HASH,  # pragma: allowlist secret
    )


def _async_override(value):
    async def _dependency():
        return value

    return _dependency


@pytest.fixture()
def app() -> FastAPI:
    """Create a minimal FastAPI app with the copilot router."""
    application = FastAPI()
    application.include_router(router)

    # Use async dependency overrides to avoid threadpool deadlocks in ASGI transport tests.
    default_nlp = MagicMock(name="default_nlp_engine")
    default_nlp.extract_entities.return_value = []
    default_nlp.detect_policy_type.return_value = "role_based"

    default_rego_generator = MagicMock(name="default_rego_generator")
    default_rego_generator.TEMPLATES = {}
    default_rego_generator.get_templates.return_value = []

    default_policy_validator = MagicMock(name="default_policy_validator")

    application.dependency_overrides[get_current_user] = _async_override(_mock_user())
    application.dependency_overrides[get_nlp_engine] = _async_override(default_nlp)
    application.dependency_overrides[get_rego_generator] = _async_override(default_rego_generator)
    application.dependency_overrides[get_policy_validator] = _async_override(
        default_policy_validator
    )
    return application


@pytest.fixture()
def client(app: FastAPI):
    return SyncASGIClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Shared mock helpers
# ---------------------------------------------------------------------------


def _make_policy_result(confidence: float = 0.9, rego_code: str | None = None) -> PolicyResult:
    """Build a minimal PolicyResult for mocking."""
    code = rego_code or "package authz\ndefault allow = false\nallow { true }"
    entity = PolicyEntity(type=PolicyEntityType.ROLE, value="admin", confidence=0.9)
    return PolicyResult(
        rego_code=code,
        explanation="Test explanation",
        test_cases=[],
        confidence=confidence,
        entities=[entity],
    )


def _make_template(tid: str = "ownership") -> PolicyTemplate:
    return PolicyTemplate(
        id=tid,
        name="Test Template",
        description="A test policy template",
        category=PolicyTemplateCategory.ACCESS_CONTROL,
        rego_template="package authz\ndefault allow = false",
        placeholders=[],
        example_usage="test usage",
        tags=["test"],
    )


# ---------------------------------------------------------------------------
# Dependency provider tests
# ---------------------------------------------------------------------------


class TestDependencyProviders:
    """Test the get_* singleton factory functions."""

    def test_get_nlp_engine_creates_instance(self) -> None:
        import enhanced_agent_bus.policy_copilot.api as api_mod

        original = api_mod._nlp_engine
        try:
            api_mod._nlp_engine = None
            engine = get_nlp_engine()
            assert engine is not None
            # Second call returns the same instance
            engine2 = get_nlp_engine()
            assert engine2 is engine
        finally:
            api_mod._nlp_engine = original

    def test_get_rego_generator_creates_instance(self) -> None:
        import enhanced_agent_bus.policy_copilot.api as api_mod

        original = api_mod._rego_generator
        try:
            api_mod._rego_generator = None
            gen = get_rego_generator()
            assert gen is not None
            gen2 = get_rego_generator()
            assert gen2 is gen
        finally:
            api_mod._rego_generator = original

    def test_get_policy_validator_creates_instance(self) -> None:
        import enhanced_agent_bus.policy_copilot.api as api_mod

        original = api_mod._policy_validator
        try:
            api_mod._policy_validator = None
            val = get_policy_validator()
            assert val is not None
            val2 = get_policy_validator()
            assert val2 is val
        finally:
            api_mod._policy_validator = original

    def test_get_nlp_engine_returns_existing(self) -> None:
        import enhanced_agent_bus.policy_copilot.api as api_mod

        mock_engine = MagicMock()
        original = api_mod._nlp_engine
        try:
            api_mod._nlp_engine = mock_engine
            result = get_nlp_engine()
            assert result is mock_engine
        finally:
            api_mod._nlp_engine = original


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


class TestHealthCheck:
    def test_health_check_returns_200(self, client) -> None:
        response = client.get("/api/v1/policy-copilot/health")
        assert response.status_code == 200

    def test_health_check_body(self, client) -> None:
        response = client.get("/api/v1/policy-copilot/health")
        data = response.json()
        assert data["status"] == "healthy"
        assert data["version"] == "1.0.0"
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert "nlp_engine" in data["components"]
        assert "rego_generator" in data["components"]
        assert "policy_validator" in data["components"]

    def test_health_response_components_are_true(self, client) -> None:
        response = client.get("/api/v1/policy-copilot/health")
        data = response.json()
        for key, val in data["components"].items():
            assert val is True, f"Component {key} should be True"


# ---------------------------------------------------------------------------
# Generate policy
# ---------------------------------------------------------------------------


class TestGeneratePolicy:
    def _mock_deps(self, result: PolicyResult) -> tuple[MagicMock, MagicMock]:
        mock_nlp = MagicMock()
        mock_nlp.extract_entities.return_value = result.entities
        mock_nlp.detect_policy_type.return_value = "role_based"

        mock_gen = MagicMock()
        mock_gen.TEMPLATES = {}
        mock_gen.generate.return_value = result
        return mock_nlp, mock_gen

    def test_generate_success(self, app: FastAPI) -> None:
        result = _make_policy_result(confidence=0.9)
        mock_nlp, mock_gen = self._mock_deps(result)

        app.dependency_overrides[get_nlp_engine] = _async_override(mock_nlp)
        app.dependency_overrides[get_rego_generator] = _async_override(mock_gen)
        try:
            client = SyncASGIClient(app, raise_server_exceptions=False)
            response = client.post(
                "/api/v1/policy-copilot/generate",
                json={"description": "Only admins can delete resources"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["constitutional_hash"] == CONSTITUTIONAL_HASH
            assert "policy" in data
            assert "confidence" in data
        finally:
            app.dependency_overrides.clear()

    def test_generate_low_confidence_adds_suggestion(self, app: FastAPI) -> None:
        result = _make_policy_result(confidence=0.5)
        mock_nlp, mock_gen = self._mock_deps(result)

        app.dependency_overrides[get_nlp_engine] = _async_override(mock_nlp)
        app.dependency_overrides[get_rego_generator] = _async_override(mock_gen)
        try:
            client = SyncASGIClient(app, raise_server_exceptions=False)
            response = client.post(
                "/api/v1/policy-copilot/generate",
                json={"description": "Some policy description here"},
            )
            assert response.status_code == 200
            data = response.json()
            assert any("confidence" in s.lower() for s in data["suggestions"])
        finally:
            app.dependency_overrides.clear()

    def test_generate_default_allow_adds_risk(self, app: FastAPI) -> None:
        result = _make_policy_result(
            confidence=0.9,
            rego_code="package authz\ndefault allow = true\nallow { true }",
        )
        mock_nlp, mock_gen = self._mock_deps(result)

        app.dependency_overrides[get_nlp_engine] = _async_override(mock_nlp)
        app.dependency_overrides[get_rego_generator] = _async_override(mock_gen)
        try:
            client = SyncASGIClient(app, raise_server_exceptions=False)
            response = client.post(
                "/api/v1/policy-copilot/generate",
                json={"description": "Default allow test policy here"},
            )
            assert response.status_code == 200
            data = response.json()
            assert len(data["risks"]) > 0
            assert any("default allow" in r.lower() for r in data["risks"])
        finally:
            app.dependency_overrides.clear()

    def test_generate_with_template_id_found(self, app: FastAPI) -> None:
        template = _make_template("ownership")
        result = _make_policy_result()
        mock_nlp, mock_gen = self._mock_deps(result)
        mock_gen.TEMPLATES = {"ownership": template}

        app.dependency_overrides[get_nlp_engine] = _async_override(mock_nlp)
        app.dependency_overrides[get_rego_generator] = _async_override(mock_gen)
        try:
            client = SyncASGIClient(app, raise_server_exceptions=False)
            response = client.post(
                "/api/v1/policy-copilot/generate",
                json={
                    "description": "Only admins can delete resources",
                    "template_id": "ownership",
                },
            )
            assert response.status_code == 200
            mock_gen.generate.assert_called_once()
            call_kwargs = mock_gen.generate.call_args
            assert call_kwargs.kwargs.get("policy_type") == "ownership"
        finally:
            app.dependency_overrides.clear()

    def test_generate_with_template_id_not_found(self, app: FastAPI) -> None:
        result = _make_policy_result()
        mock_nlp, mock_gen = self._mock_deps(result)
        mock_gen.TEMPLATES = {}

        app.dependency_overrides[get_nlp_engine] = _async_override(mock_nlp)
        app.dependency_overrides[get_rego_generator] = _async_override(mock_gen)
        try:
            client = SyncASGIClient(app, raise_server_exceptions=False)
            response = client.post(
                "/api/v1/policy-copilot/generate",
                json={
                    "description": "Only admins can delete resources",
                    "template_id": "nonexistent",
                },
            )
            assert response.status_code == 200
        finally:
            app.dependency_overrides.clear()

    def test_generate_validation_error_raises_400(self, app: FastAPI) -> None:
        mock_nlp = MagicMock()
        mock_nlp.extract_entities.side_effect = ValidationError("bad input")
        mock_gen = MagicMock()
        mock_gen.TEMPLATES = {}

        app.dependency_overrides[get_nlp_engine] = _async_override(mock_nlp)
        app.dependency_overrides[get_rego_generator] = _async_override(mock_gen)
        try:
            client = SyncASGIClient(app, raise_server_exceptions=False)
            response = client.post(
                "/api/v1/policy-copilot/generate",
                json={"description": "Only admins can delete"},
            )
            assert response.status_code == 400
        finally:
            app.dependency_overrides.clear()

    def test_generate_runtime_error_raises_500(self, app: FastAPI) -> None:
        mock_nlp = MagicMock()
        mock_nlp.extract_entities.side_effect = RuntimeError("boom")
        mock_gen = MagicMock()
        mock_gen.TEMPLATES = {}

        app.dependency_overrides[get_nlp_engine] = _async_override(mock_nlp)
        app.dependency_overrides[get_rego_generator] = _async_override(mock_gen)
        try:
            client = SyncASGIClient(app, raise_server_exceptions=False)
            response = client.post(
                "/api/v1/policy-copilot/generate",
                json={"description": "Only admins can delete"},
            )
            assert response.status_code == 500
            assert response.json()["detail"]  # sanitized error detail present
        finally:
            app.dependency_overrides.clear()

    def test_generate_with_tenant_and_context(self, app: FastAPI) -> None:
        result = _make_policy_result()
        mock_nlp, mock_gen = self._mock_deps(result)

        app.dependency_overrides[get_nlp_engine] = _async_override(mock_nlp)
        app.dependency_overrides[get_rego_generator] = _async_override(mock_gen)
        app.dependency_overrides[get_current_user] = _async_override(
            _mock_user(tenant_id="tenant-123")
        )
        try:
            client = SyncASGIClient(app, raise_server_exceptions=False)
            response = client.post(
                "/api/v1/policy-copilot/generate",
                json={
                    "description": "Only admins can view reports",
                    "context": "enterprise",
                    "tenant_id": "tenant-123",
                },
            )
            assert response.status_code == 200
        finally:
            app.dependency_overrides.clear()

    def test_generate_cross_tenant_returns_403(self, app: FastAPI) -> None:
        result = _make_policy_result()
        mock_nlp, mock_gen = self._mock_deps(result)

        app.dependency_overrides[get_nlp_engine] = _async_override(mock_nlp)
        app.dependency_overrides[get_rego_generator] = _async_override(mock_gen)
        app.dependency_overrides[get_current_user] = _async_override(
            _mock_user(tenant_id="tenant-123")
        )
        try:
            client = SyncASGIClient(app, raise_server_exceptions=False)
            response = client.post(
                "/api/v1/policy-copilot/generate",
                json={
                    "description": "Only admins can view reports",
                    "tenant_id": "tenant-456",
                },
            )
            assert response.status_code == 403
        finally:
            app.dependency_overrides.clear()

    def test_generate_invalid_body_returns_422(self, app: FastAPI) -> None:
        client = SyncASGIClient(app, raise_server_exceptions=False)
        response = client.post("/api/v1/policy-copilot/generate", json={})
        assert response.status_code == 422

    def test_generate_description_too_short_returns_422(self, app: FastAPI) -> None:
        client = SyncASGIClient(app, raise_server_exceptions=False)
        response = client.post("/api/v1/policy-copilot/generate", json={"description": "   "})
        assert response.status_code == 422

    @pytest.mark.parametrize(
        "error_type",
        [AttributeError, KeyError, OSError, TypeError, ValueError],
    )
    def test_generate_api_errors_return_500(
        self, app: FastAPI, error_type: type[Exception]
    ) -> None:
        mock_nlp = MagicMock()
        mock_nlp.extract_entities.side_effect = error_type("err")
        mock_gen = MagicMock()
        mock_gen.TEMPLATES = {}

        app.dependency_overrides[get_nlp_engine] = _async_override(mock_nlp)
        app.dependency_overrides[get_rego_generator] = _async_override(mock_gen)
        try:
            client = SyncASGIClient(app, raise_server_exceptions=False)
            response = client.post(
                "/api/v1/policy-copilot/generate",
                json={"description": "Only admins can delete"},
            )
            assert response.status_code == 500
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Explain policy
# ---------------------------------------------------------------------------


class TestExplainPolicy:
    def _explanation_data(self) -> dict:
        return {
            "explanation": "This is a secure policy.",
            "risks": [
                {
                    "severity": "high",
                    "category": "security",
                    "description": "Default allow",
                    "mitigation": "Change to deny",
                }
            ],
            "suggestions": ["Add MFA"],
            "complexity_score": 0.3,
        }

    def test_explain_success(self, app: FastAPI) -> None:
        mock_gen = MagicMock()
        mock_gen.explain.return_value = self._explanation_data()

        app.dependency_overrides[get_rego_generator] = _async_override(mock_gen)
        try:
            client = SyncASGIClient(app, raise_server_exceptions=False)
            response = client.post(
                "/api/v1/policy-copilot/explain",
                json={"policy": "package authz\ndefault allow = false"},
            )
            assert response.status_code == 200
            data = response.json()
            assert "explanation" in data
            assert "risks" in data
        finally:
            app.dependency_overrides.clear()

    def test_explain_with_risk_conversion(self, app: FastAPI) -> None:
        mock_gen = MagicMock()
        mock_gen.explain.return_value = self._explanation_data()

        app.dependency_overrides[get_rego_generator] = _async_override(mock_gen)
        try:
            client = SyncASGIClient(app, raise_server_exceptions=False)
            response = client.post(
                "/api/v1/policy-copilot/explain",
                json={"policy": "package authz\ndefault allow = true", "detail_level": "simple"},
            )
            assert response.status_code == 200
            data = response.json()
            assert len(data["risks"]) == 1
            assert data["risks"][0]["severity"] == "high"
        finally:
            app.dependency_overrides.clear()

    def test_explain_runtime_error_returns_500(self, app: FastAPI) -> None:
        mock_gen = MagicMock()
        mock_gen.explain.side_effect = RuntimeError("kaboom")

        app.dependency_overrides[get_rego_generator] = _async_override(mock_gen)
        try:
            client = SyncASGIClient(app, raise_server_exceptions=False)
            response = client.post(
                "/api/v1/policy-copilot/explain",
                json={"policy": "package authz"},
            )
            assert response.status_code == 500
            assert response.json()["detail"]  # sanitized error detail present
        finally:
            app.dependency_overrides.clear()

    def test_explain_empty_risks(self, app: FastAPI) -> None:
        mock_gen = MagicMock()
        mock_gen.explain.return_value = {
            "explanation": "OK",
            "risks": [],
            "suggestions": [],
            "complexity_score": 0.1,
        }

        app.dependency_overrides[get_rego_generator] = _async_override(mock_gen)
        try:
            client = SyncASGIClient(app, raise_server_exceptions=False)
            response = client.post(
                "/api/v1/policy-copilot/explain",
                json={"policy": "package authz\ndefault allow = false"},
            )
            assert response.status_code == 200
            assert response.json()["risks"] == []
        finally:
            app.dependency_overrides.clear()

    def test_explain_missing_risk_fields_use_defaults(self, app: FastAPI) -> None:
        """Risk dicts with missing keys fall back to defaults."""
        mock_gen = MagicMock()
        mock_gen.explain.return_value = {
            "explanation": "OK",
            "risks": [{}],  # all keys missing
            "suggestions": [],
            "complexity_score": 0.0,
        }

        app.dependency_overrides[get_rego_generator] = _async_override(mock_gen)
        try:
            client = SyncASGIClient(app, raise_server_exceptions=False)
            response = client.post(
                "/api/v1/policy-copilot/explain",
                json={"policy": "package authz"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["risks"][0]["severity"] == "low"
            assert data["risks"][0]["category"] == "general"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.parametrize("error_type", [AttributeError, KeyError, OSError, TypeError])
    def test_explain_api_errors_return_500(self, app: FastAPI, error_type: type[Exception]) -> None:
        mock_gen = MagicMock()
        mock_gen.explain.side_effect = error_type("err")

        app.dependency_overrides[get_rego_generator] = _async_override(mock_gen)
        try:
            client = SyncASGIClient(app, raise_server_exceptions=False)
            response = client.post(
                "/api/v1/policy-copilot/explain",
                json={"policy": "package authz"},
            )
            assert response.status_code == 500
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Improve policy
# ---------------------------------------------------------------------------


class TestImprovePolicy:
    def test_improve_success(self, app: FastAPI) -> None:
        mock_gen = MagicMock()
        mock_gen.improve.return_value = (
            "package authz\ndefault allow = false\nallow { input.user.mfa }",
            ["Added MFA requirement"],
        )

        app.dependency_overrides[get_rego_generator] = _async_override(mock_gen)
        try:
            client = SyncASGIClient(app, raise_server_exceptions=False)
            response = client.post(
                "/api/v1/policy-copilot/improve",
                json={
                    "policy": "package authz\ndefault allow = false",
                    "feedback": "Add MFA requirement",
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert "improved_policy" in data
            assert "changes_made" in data
            assert "explanation" in data
            assert "1 changes" in data["explanation"]
        finally:
            app.dependency_overrides.clear()

    def test_improve_no_changes(self, app: FastAPI) -> None:
        mock_gen = MagicMock()
        mock_gen.improve.return_value = ("package authz", [])

        app.dependency_overrides[get_rego_generator] = _async_override(mock_gen)
        try:
            client = SyncASGIClient(app, raise_server_exceptions=False)
            response = client.post(
                "/api/v1/policy-copilot/improve",
                json={
                    "policy": "package authz\ndefault allow = false",
                    "feedback": "looks good",
                    "instruction": "stricter",
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert "0 changes" in data["explanation"]
        finally:
            app.dependency_overrides.clear()

    def test_improve_runtime_error_returns_500(self, app: FastAPI) -> None:
        mock_gen = MagicMock()
        mock_gen.improve.side_effect = RuntimeError("fail")

        app.dependency_overrides[get_rego_generator] = _async_override(mock_gen)
        try:
            client = SyncASGIClient(app, raise_server_exceptions=False)
            response = client.post(
                "/api/v1/policy-copilot/improve",
                json={"policy": "package authz", "feedback": "improve this"},
            )
            assert response.status_code == 500
            assert response.json()["detail"]  # sanitized error detail present
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.parametrize("error_type", [AttributeError, KeyError, OSError, TypeError])
    def test_improve_api_errors_return_500(self, app: FastAPI, error_type: type[Exception]) -> None:
        mock_gen = MagicMock()
        mock_gen.improve.side_effect = error_type("err")

        app.dependency_overrides[get_rego_generator] = _async_override(mock_gen)
        try:
            client = SyncASGIClient(app, raise_server_exceptions=False)
            response = client.post(
                "/api/v1/policy-copilot/improve",
                json={"policy": "package authz", "feedback": "improve this"},
            )
            assert response.status_code == 500
        finally:
            app.dependency_overrides.clear()

    def test_improve_missing_fields_returns_422(self, app: FastAPI) -> None:
        client = SyncASGIClient(app, raise_server_exceptions=False)
        response = client.post("/api/v1/policy-copilot/improve", json={"policy": "package authz"})
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Validate policy
# ---------------------------------------------------------------------------


class TestValidatePolicy:
    def test_validate_success_valid(self, app: FastAPI) -> None:
        mock_val = MagicMock()
        mock_val.validate_syntax.return_value = ValidationResult(
            valid=True, errors=[], syntax_check=True
        )

        app.dependency_overrides[get_policy_validator] = _async_override(mock_val)
        try:
            client = SyncASGIClient(app, raise_server_exceptions=False)
            response = client.post(
                "/api/v1/policy-copilot/validate",
                json={"policy": "package authz\ndefault allow = false"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["valid"] is True
        finally:
            app.dependency_overrides.clear()

    def test_validate_success_invalid(self, app: FastAPI) -> None:
        mock_val = MagicMock()
        mock_val.validate_syntax.return_value = ValidationResult(
            valid=False, errors=["Missing package"], syntax_check=False
        )

        app.dependency_overrides[get_policy_validator] = _async_override(mock_val)
        try:
            client = SyncASGIClient(app, raise_server_exceptions=False)
            response = client.post(
                "/api/v1/policy-copilot/validate",
                json={"policy": "allow { true }"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["valid"] is False
            assert len(data["errors"]) > 0
        finally:
            app.dependency_overrides.clear()

    def test_validate_runtime_error_returns_500(self, app: FastAPI) -> None:
        mock_val = MagicMock()
        mock_val.validate_syntax.side_effect = RuntimeError("fail")

        app.dependency_overrides[get_policy_validator] = _async_override(mock_val)
        try:
            client = SyncASGIClient(app, raise_server_exceptions=False)
            response = client.post(
                "/api/v1/policy-copilot/validate",
                json={"policy": "package authz"},
            )
            assert response.status_code == 500
            assert response.json()["detail"]  # sanitized error detail present
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.parametrize("error_type", [AttributeError, KeyError, OSError, TypeError])
    def test_validate_api_errors_return_500(
        self, app: FastAPI, error_type: type[Exception]
    ) -> None:
        mock_val = MagicMock()
        mock_val.validate_syntax.side_effect = error_type("err")

        app.dependency_overrides[get_policy_validator] = _async_override(mock_val)
        try:
            client = SyncASGIClient(app, raise_server_exceptions=False)
            response = client.post(
                "/api/v1/policy-copilot/validate",
                json={"policy": "package authz"},
            )
            assert response.status_code == 500
        finally:
            app.dependency_overrides.clear()

    def test_validate_missing_policy_field_returns_422(self, app: FastAPI) -> None:
        client = SyncASGIClient(app, raise_server_exceptions=False)
        response = client.post("/api/v1/policy-copilot/validate", json={})
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Test policy
# ---------------------------------------------------------------------------


class TestTestPolicy:
    def _mock_result(self) -> TestResult:
        return TestResult(
            allowed=True,
            decision_path=["allow_rule_0"],
            trace={"simulated": True},
            errors=[],
            execution_time_ms=1.5,
        )

    def test_test_policy_success(self, app: FastAPI) -> None:
        mock_val = MagicMock()
        mock_val.test_policy.return_value = self._mock_result()

        app.dependency_overrides[get_policy_validator] = _async_override(mock_val)
        try:
            client = SyncASGIClient(app, raise_server_exceptions=False)
            response = client.post(
                "/api/v1/policy-copilot/test",
                json={
                    "policy": "package authz\ndefault allow = false",
                    "test_input": {"user": {"role": "admin"}, "action": "read"},
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["allowed"] is True
        finally:
            app.dependency_overrides.clear()

    def test_test_policy_denied(self, app: FastAPI) -> None:
        mock_val = MagicMock()
        mock_val.test_policy.return_value = TestResult(
            allowed=False,
            decision_path=[],
            trace={},
            errors=[],
            execution_time_ms=0.5,
        )

        app.dependency_overrides[get_policy_validator] = _async_override(mock_val)
        try:
            client = SyncASGIClient(app, raise_server_exceptions=False)
            response = client.post(
                "/api/v1/policy-copilot/test",
                json={
                    "policy": "package authz\ndefault allow = false",
                    "test_input": {"user": {"role": "guest"}, "action": "delete"},
                },
            )
            assert response.status_code == 200
            assert response.json()["allowed"] is False
        finally:
            app.dependency_overrides.clear()

    def test_test_policy_runtime_error_returns_500(self, app: FastAPI) -> None:
        mock_val = MagicMock()
        mock_val.test_policy.side_effect = RuntimeError("eval fail")

        app.dependency_overrides[get_policy_validator] = _async_override(mock_val)
        try:
            client = SyncASGIClient(app, raise_server_exceptions=False)
            response = client.post(
                "/api/v1/policy-copilot/test",
                json={
                    "policy": "package authz",
                    "test_input": {"user": {}},
                },
            )
            assert response.status_code == 500
            assert response.json()["detail"]  # sanitized error detail present
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.parametrize("error_type", [AttributeError, KeyError, OSError, TypeError])
    def test_test_api_errors_return_500(self, app: FastAPI, error_type: type[Exception]) -> None:
        mock_val = MagicMock()
        mock_val.test_policy.side_effect = error_type("err")

        app.dependency_overrides[get_policy_validator] = _async_override(mock_val)
        try:
            client = SyncASGIClient(app, raise_server_exceptions=False)
            response = client.post(
                "/api/v1/policy-copilot/test",
                json={"policy": "package authz", "test_input": {}},
            )
            assert response.status_code == 500
        finally:
            app.dependency_overrides.clear()

    def test_test_policy_missing_fields_returns_422(self, app: FastAPI) -> None:
        client = SyncASGIClient(app, raise_server_exceptions=False)
        response = client.post("/api/v1/policy-copilot/test", json={"policy": "package authz"})
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Get templates
# ---------------------------------------------------------------------------


class TestGetTemplates:
    def test_get_templates_no_filter(self, app: FastAPI) -> None:
        templates = [_make_template("ownership"), _make_template("role_based")]
        mock_gen = MagicMock()
        mock_gen.get_templates.return_value = templates

        app.dependency_overrides[get_rego_generator] = _async_override(mock_gen)
        try:
            client = SyncASGIClient(app, raise_server_exceptions=False)
            response = client.get("/api/v1/policy-copilot/templates")
            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 2
            assert len(data["templates"]) == 2
        finally:
            app.dependency_overrides.clear()

    def test_get_templates_with_category_filter(self, app: FastAPI) -> None:
        mock_gen = MagicMock()
        mock_gen.get_templates.return_value = [_make_template("ownership")]

        app.dependency_overrides[get_rego_generator] = _async_override(mock_gen)
        try:
            client = SyncASGIClient(app, raise_server_exceptions=False)
            response = client.get("/api/v1/policy-copilot/templates?category=access_control")
            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 1
            mock_gen.get_templates.assert_called_once_with(PolicyTemplateCategory.ACCESS_CONTROL)
        finally:
            app.dependency_overrides.clear()

    def test_get_templates_empty(self, app: FastAPI) -> None:
        mock_gen = MagicMock()
        mock_gen.get_templates.return_value = []

        app.dependency_overrides[get_rego_generator] = _async_override(mock_gen)
        try:
            client = SyncASGIClient(app, raise_server_exceptions=False)
            response = client.get("/api/v1/policy-copilot/templates")
            assert response.status_code == 200
            assert response.json()["total"] == 0
        finally:
            app.dependency_overrides.clear()

    def test_get_templates_runtime_error_returns_500(self, app: FastAPI) -> None:
        mock_gen = MagicMock()
        mock_gen.get_templates.side_effect = RuntimeError("fail")

        app.dependency_overrides[get_rego_generator] = _async_override(mock_gen)
        try:
            client = SyncASGIClient(app, raise_server_exceptions=False)
            response = client.get("/api/v1/policy-copilot/templates")
            assert response.status_code == 500
            assert response.json()["detail"]  # sanitized error detail present
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.parametrize("error_type", [AttributeError, KeyError, OSError, TypeError])
    def test_get_templates_api_errors_return_500(
        self, app: FastAPI, error_type: type[Exception]
    ) -> None:
        mock_gen = MagicMock()
        mock_gen.get_templates.side_effect = error_type("err")

        app.dependency_overrides[get_rego_generator] = _async_override(mock_gen)
        try:
            client = SyncASGIClient(app, raise_server_exceptions=False)
            response = client.get("/api/v1/policy-copilot/templates")
            assert response.status_code == 500
        finally:
            app.dependency_overrides.clear()

    def test_get_templates_invalid_category_returns_422(self, app: FastAPI) -> None:
        client = SyncASGIClient(app, raise_server_exceptions=False)
        response = client.get("/api/v1/policy-copilot/templates?category=invalid_category")
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Get specific template
# ---------------------------------------------------------------------------


class TestGetTemplate:
    def test_get_template_found(self, app: FastAPI) -> None:
        template = _make_template("ownership")
        mock_gen = MagicMock()
        mock_gen.TEMPLATES = {"ownership": template}

        app.dependency_overrides[get_rego_generator] = _async_override(mock_gen)
        try:
            client = SyncASGIClient(app, raise_server_exceptions=False)
            response = client.get("/api/v1/policy-copilot/templates/ownership")
            assert response.status_code == 200
            data = response.json()
            assert data["id"] == "ownership"
        finally:
            app.dependency_overrides.clear()

    def test_get_template_not_found_returns_404(self, app: FastAPI) -> None:
        mock_gen = MagicMock()
        mock_gen.TEMPLATES = {}

        app.dependency_overrides[get_rego_generator] = _async_override(mock_gen)
        try:
            client = SyncASGIClient(app, raise_server_exceptions=False)
            response = client.get("/api/v1/policy-copilot/templates/nonexistent")
            assert response.status_code == 404
            assert "nonexistent" in response.json()["detail"]
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Submit feedback
# ---------------------------------------------------------------------------


class TestSubmitFeedback:
    def test_feedback_thumbs_up(self, client) -> None:
        response = client.post(
            "/api/v1/policy-copilot/feedback",
            json={"policy_id": "policy-abc", "feedback": "thumbs_up"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["received"] is True
        assert data["policy_id"] == "policy-abc"

    def test_feedback_thumbs_down(self, client) -> None:
        response = client.post(
            "/api/v1/policy-copilot/feedback",
            json={
                "policy_id": "policy-xyz",
                "feedback": "thumbs_down",
                "comment": "Not accurate enough",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["received"] is True
        assert data["policy_id"] == "policy-xyz"

    def test_feedback_without_comment(self, client) -> None:
        response = client.post(
            "/api/v1/policy-copilot/feedback",
            json={"policy_id": "pol-001", "feedback": "thumbs_up"},
        )
        assert response.status_code == 200

    def test_feedback_invalid_type_returns_422(self, client) -> None:
        response = client.post(
            "/api/v1/policy-copilot/feedback",
            json={"policy_id": "pol-001", "feedback": "meh"},
        )
        assert response.status_code == 422

    def test_feedback_missing_policy_id_returns_422(self, client) -> None:
        response = client.post(
            "/api/v1/policy-copilot/feedback",
            json={"feedback": "thumbs_up"},
        )
        assert response.status_code == 422

    def test_feedback_missing_feedback_field_returns_422(self, client) -> None:
        response = client.post(
            "/api/v1/policy-copilot/feedback",
            json={"policy_id": "pol-001"},
        )
        assert response.status_code == 422

    def test_feedback_error_path(self, app: FastAPI) -> None:
        """Test the except block by patching logger.info to raise."""
        with patch("enhanced_agent_bus.policy_copilot.api.logger") as mock_logger:
            mock_logger.info.side_effect = RuntimeError("log failed")
            client = SyncASGIClient(app, raise_server_exceptions=False)
            response = client.post(
                "/api/v1/policy-copilot/feedback",
                json={"policy_id": "pol-001", "feedback": "thumbs_up"},
            )
            # RuntimeError is in API_ERRORS, so returns 500
            assert response.status_code == 500


# ---------------------------------------------------------------------------
# Pydantic model unit tests
# ---------------------------------------------------------------------------


class TestPydanticModels:
    def test_health_response_model(self) -> None:
        h = HealthResponse(
            status="healthy",
            version="1.0.0",
            constitutional_hash=CONSTITUTIONAL_HASH,
            components={"a": True},
        )
        assert h.status == "healthy"
        assert h.constitutional_hash == CONSTITUTIONAL_HASH

    def test_template_list_response_model(self) -> None:
        t = _make_template()
        resp = TemplateListResponse(templates=[t], total=1)
        assert resp.total == 1
        assert len(resp.templates) == 1

    def test_feedback_request_model(self) -> None:
        req = FeedbackRequest(policy_id="p1", feedback="thumbs_up")
        assert req.comment is None

    def test_feedback_response_model(self) -> None:
        resp = FeedbackResponse(received=True, policy_id="p1")
        assert resp.received is True
