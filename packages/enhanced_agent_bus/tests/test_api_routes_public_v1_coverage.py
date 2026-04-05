# Constitutional Hash: 608508a9bd224290
"""Comprehensive coverage tests for api/routes/public_v1.py.

Targets ≥95% line coverage of
src/core/enhanced_agent_bus/api/routes/public_v1.py (58 statements).

Covers:
- Module-level constants and Pydantic models
- Helper functions: _build_request_id, _validation_score_and_violations, _record_validation
- _otel_span context manager (with and without tracer)
- GET /v1/health endpoint
- POST /v1/validate endpoint (success, auth failure, rate-limit path)
"""

from __future__ import annotations

import asyncio
import importlib
import sys
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI

from enhanced_agent_bus.api.routes import public_v1 as _mod

pytestmark = [pytest.mark.unit]


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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MOD_PATH = "enhanced_agent_bus.api.routes.public_v1"


def _async_override(value):
    async def _dependency():
        return value

    return _dependency


def _fresh_module() -> object:
    """Return the already-imported module (coverage is already tracking it)."""
    return sys.modules.get(_MOD_PATH) or importlib.import_module(_MOD_PATH)


def _make_app(*, override_api_key: bool = True) -> FastAPI:
    """Create a minimal FastAPI app with the public_v1 router.

    When *override_api_key* is True, the `require_api_key` dependency is
    replaced with a passthrough so tests don't need real API-key logic.
    """
    from enhanced_agent_bus.api.routes.public_v1 import router

    app = FastAPI()
    if override_api_key:
        from enhanced_agent_bus.api.api_key_auth import require_api_key

        app.dependency_overrides[require_api_key] = _async_override("test-key")

    # Attach limiter state expected by slowapi
    from enhanced_agent_bus.api.rate_limiting import limiter

    app.state.limiter = limiter
    app.include_router(router)
    return app


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------


class TestModuleConstants:
    def test_public_api_version(self):
        assert _mod.PUBLIC_API_VERSION == "1.0.0"

    def test_hash_validation_failure_message(self):
        assert "constitutional" in _mod.HASH_VALIDATION_FAILURE.lower()

    def test_validation_ok_score(self):
        assert _mod.VALIDATION_OK_SCORE == 1.0

    def test_validation_failed_score(self):
        assert _mod.VALIDATION_FAILED_SCORE == 0.0

    def test_router_prefix(self):
        assert _mod.router.prefix == "/v1"


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class TestValidateRequest:
    def test_basic_construction(self):
        req = _mod.ValidateRequest(agent_id="a1", action="read")
        assert req.agent_id == "a1"
        assert req.action == "read"
        assert req.context == {}
        assert req.policies == []

    def test_with_context_and_policies(self):
        req = _mod.ValidateRequest(
            agent_id="a2",
            action="write",
            context={"env": "prod"},
            policies=["p1", "p2"],
        )
        assert req.context == {"env": "prod"}
        assert req.policies == ["p1", "p2"]

    def test_missing_required_fields_raises(self):
        with pytest.raises((TypeError, ValueError)):
            _mod.ValidateRequest()  # type: ignore[call-arg]

    def test_context_default_is_empty_dict(self):
        req1 = _mod.ValidateRequest(agent_id="x", action="y")
        req2 = _mod.ValidateRequest(agent_id="x", action="y")
        # Mutable default — each instance gets its own dict
        req1.context["key"] = "val"
        assert req2.context == {}

    def test_policies_default_is_empty_list(self):
        req1 = _mod.ValidateRequest(agent_id="x", action="y")
        req2 = _mod.ValidateRequest(agent_id="x", action="y")
        req1.policies.append("p")
        assert req2.policies == []


class TestValidateResponse:
    def test_defaults(self):
        resp = _mod.ValidateResponse(compliant=True, constitutional_hash="abc")
        assert resp.score == 1.0
        assert resp.violations == []
        assert resp.latency_ms == 0.0
        assert resp.request_id == ""

    def test_non_compliant(self):
        resp = _mod.ValidateResponse(
            compliant=False,
            constitutional_hash="abc",
            score=0.0,
            violations=["v1"],
        )
        assert not resp.compliant
        assert resp.violations == ["v1"]

    def test_all_fields(self):
        resp = _mod.ValidateResponse(
            compliant=True,
            constitutional_hash="hash123",
            score=0.9,
            violations=[],
            latency_ms=3.14,
            request_id="agent:action",
        )
        assert resp.latency_ms == 3.14
        assert resp.request_id == "agent:action"


class TestHealthResponse:
    def test_construction(self):
        hr = _mod.HealthResponse(status="healthy", version="1.0.0", constitutional_hash="abc")
        assert hr.status == "healthy"
        assert hr.version == "1.0.0"
        assert hr.constitutional_hash == "abc"

    def test_serialisation_roundtrip(self):
        hr = _mod.HealthResponse(status="ok", version="2.0", constitutional_hash="xyz")
        d = hr.model_dump()
        assert d["status"] == "ok"
        assert d["constitutional_hash"] == "xyz"


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


class TestBuildRequestId:
    def test_format(self):
        req = _mod.ValidateRequest(agent_id="myagent", action="deploy")
        assert _mod._build_request_id(req) == "myagent:deploy"

    def test_different_inputs_different_ids(self):
        r1 = _mod.ValidateRequest(agent_id="a", action="b")
        r2 = _mod.ValidateRequest(agent_id="c", action="d")
        assert _mod._build_request_id(r1) != _mod._build_request_id(r2)

    def test_separator_is_colon(self):
        req = _mod.ValidateRequest(agent_id="X", action="Y")
        result = _mod._build_request_id(req)
        assert ":" in result
        parts = result.split(":")
        assert parts[0] == "X"
        assert parts[1] == "Y"


class TestValidationScoreAndViolations:
    def test_compliant_returns_ok_score(self):
        score, violations = _mod._validation_score_and_violations(True)
        assert score == _mod.VALIDATION_OK_SCORE
        assert violations == []

    def test_non_compliant_returns_failed_score(self):
        score, violations = _mod._validation_score_and_violations(False)
        assert score == _mod.VALIDATION_FAILED_SCORE
        assert len(violations) == 1
        assert _mod.HASH_VALIDATION_FAILURE in violations

    def test_compliant_violations_are_empty_list(self):
        _, violations = _mod._validation_score_and_violations(True)
        assert isinstance(violations, list)
        assert not violations

    def test_non_compliant_violations_contain_message(self):
        _, violations = _mod._validation_score_and_violations(False)
        assert violations[0] == _mod.HASH_VALIDATION_FAILURE


class TestRecordValidation:
    def test_calls_validation_store_record(self):
        mock_store = MagicMock()
        mock_entry_cls = MagicMock()

        req = _mod.ValidateRequest(agent_id="ag1", action="op1")
        with (
            patch.object(_mod, "get_validation_store", return_value=mock_store),
            patch.object(_mod, "ValidationEntry", mock_entry_cls),
        ):
            _mod._record_validation(req, True, 1.0, 5.0, "ag1:op1")

        mock_store.record.assert_called_once()

    def test_entry_fields_passed_correctly(self):
        recorded: list = []

        from enhanced_agent_bus.api.validation_store import ValidationEntry

        def fake_record(entry: ValidationEntry) -> None:  # type: ignore[override]
            recorded.append(entry)

        mock_store = MagicMock()
        mock_store.record.side_effect = fake_record

        req = _mod.ValidateRequest(agent_id="ag2", action="op2")
        with patch.object(_mod, "get_validation_store", return_value=mock_store):
            _mod._record_validation(req, False, 0.0, 12.5, "ag2:op2")

        assert mock_store.record.called
        call_args = mock_store.record.call_args[0][0]
        assert call_args.agent_id == "ag2"
        assert call_args.action == "op2"
        assert call_args.compliant is False
        assert call_args.score == 0.0
        assert call_args.latency_ms == 12.5
        assert call_args.request_id == "ag2:op2"


# ---------------------------------------------------------------------------
# _otel_span context manager
# ---------------------------------------------------------------------------


class TestOtelSpan:
    def test_no_op_when_tracer_is_none(self):
        """When _tracer is None the context manager should be a no-op."""
        original = _mod._tracer
        try:
            _mod._tracer = None
            with _mod._otel_span("test.op"):
                pass  # Should not raise
        finally:
            _mod._tracer = original

    def test_uses_tracer_when_available(self):
        fake_span = MagicMock()
        fake_span.__enter__ = MagicMock(return_value=fake_span)
        fake_span.__exit__ = MagicMock(return_value=False)

        fake_tracer = MagicMock()
        fake_tracer.start_as_current_span.return_value = fake_span

        with patch.object(_mod, "_tracer", fake_tracer):
            with _mod._otel_span("some.span", attributes={"k": "v"}):
                pass

        fake_tracer.start_as_current_span.assert_called_once_with(
            "some.span", attributes={"k": "v"}
        )

    def test_otel_span_no_attributes(self):
        fake_span = MagicMock()
        fake_span.__enter__ = MagicMock(return_value=fake_span)
        fake_span.__exit__ = MagicMock(return_value=False)

        fake_tracer = MagicMock()
        fake_tracer.start_as_current_span.return_value = fake_span

        with patch.object(_mod, "_tracer", fake_tracer):
            with _mod._otel_span("op.no.attr"):
                pass

        # attributes defaults to {}
        fake_tracer.start_as_current_span.assert_called_once_with("op.no.attr", attributes={})

    def test_tracer_none_with_attributes(self):
        original = _mod._tracer
        try:
            _mod._tracer = None
            with _mod._otel_span("op", attributes={"x": "y"}):
                pass  # no-op; no raise
        finally:
            _mod._tracer = original


# ---------------------------------------------------------------------------
# GET /v1/health
# ---------------------------------------------------------------------------


class TestV1Health:
    @pytest.fixture(autouse=True)
    def client(self):
        app = _make_app()
        self._client = SyncASGIClient(app, raise_server_exceptions=True)

    def test_status_200(self):
        resp = self._client.get("/v1/health")
        assert resp.status_code == 200

    def test_response_is_json(self):
        resp = self._client.get("/v1/health")
        data = resp.json()
        assert isinstance(data, dict)

    def test_status_field_healthy(self):
        resp = self._client.get("/v1/health")
        assert resp.json()["status"] == "healthy"

    def test_version_field(self):
        resp = self._client.get("/v1/health")
        assert resp.json()["version"] == _mod.PUBLIC_API_VERSION

    def test_constitutional_hash_field(self):
        from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

        resp = self._client.get("/v1/health")
        assert resp.json()["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_no_auth_required(self):
        """Health endpoint should work without API key."""
        app = FastAPI()
        from enhanced_agent_bus.api.rate_limiting import limiter
        from enhanced_agent_bus.api.routes.public_v1 import router

        app.state.limiter = limiter
        app.include_router(router)
        # No dependency overrides
        client = SyncASGIClient(app, raise_server_exceptions=True)
        resp = client.get("/v1/health")
        assert resp.status_code == 200

    def test_response_model_fields_present(self):
        resp = self._client.get("/v1/health")
        data = resp.json()
        assert "status" in data
        assert "version" in data
        assert "constitutional_hash" in data


# ---------------------------------------------------------------------------
# POST /v1/validate — success paths
# ---------------------------------------------------------------------------


class TestV1ValidateSuccess:
    @pytest.fixture(autouse=True)
    def client(self):
        self._app = _make_app()
        self._client = SyncASGIClient(self._app, raise_server_exceptions=True)

    def _post(self, payload: dict) -> object:
        return self._client.post("/v1/validate", json=payload)

    def test_status_200_compliant(self):
        mock_result = MagicMock()
        mock_result.valid = True
        with patch.object(_mod, "validate_constitutional_hash", return_value=mock_result):
            resp = self._post({"agent_id": "a1", "action": "read"})
        assert resp.status_code == 200

    def test_response_compliant_true(self):
        mock_result = MagicMock()
        mock_result.valid = True
        with patch.object(_mod, "validate_constitutional_hash", return_value=mock_result):
            resp = self._post({"agent_id": "a1", "action": "read"})
        assert resp.json()["compliant"] is True

    def test_response_violations_empty_when_compliant(self):
        mock_result = MagicMock()
        mock_result.valid = True
        with patch.object(_mod, "validate_constitutional_hash", return_value=mock_result):
            resp = self._post({"agent_id": "a1", "action": "read"})
        assert resp.json()["violations"] == []

    def test_response_score_1_when_compliant(self):
        mock_result = MagicMock()
        mock_result.valid = True
        with patch.object(_mod, "validate_constitutional_hash", return_value=mock_result):
            resp = self._post({"agent_id": "a1", "action": "read"})
        assert resp.json()["score"] == 1.0

    def test_response_compliant_false(self):
        mock_result = MagicMock()
        mock_result.valid = False
        with patch.object(_mod, "validate_constitutional_hash", return_value=mock_result):
            resp = self._post({"agent_id": "a2", "action": "write"})
        assert resp.json()["compliant"] is False

    def test_response_score_0_when_non_compliant(self):
        mock_result = MagicMock()
        mock_result.valid = False
        with patch.object(_mod, "validate_constitutional_hash", return_value=mock_result):
            resp = self._post({"agent_id": "a2", "action": "write"})
        assert resp.json()["score"] == 0.0

    def test_response_violations_when_non_compliant(self):
        mock_result = MagicMock()
        mock_result.valid = False
        with patch.object(_mod, "validate_constitutional_hash", return_value=mock_result):
            resp = self._post({"agent_id": "a2", "action": "write"})
        assert _mod.HASH_VALIDATION_FAILURE in resp.json()["violations"]

    def test_response_constitutional_hash_present(self):
        from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

        mock_result = MagicMock()
        mock_result.valid = True
        with patch.object(_mod, "validate_constitutional_hash", return_value=mock_result):
            resp = self._post({"agent_id": "a1", "action": "read"})
        assert resp.json()["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_response_latency_ms_is_float(self):
        mock_result = MagicMock()
        mock_result.valid = True
        with patch.object(_mod, "validate_constitutional_hash", return_value=mock_result):
            resp = self._post({"agent_id": "a1", "action": "read"})
        assert isinstance(resp.json()["latency_ms"], float)

    def test_response_request_id_format(self):
        mock_result = MagicMock()
        mock_result.valid = True
        with patch.object(_mod, "validate_constitutional_hash", return_value=mock_result):
            resp = self._post({"agent_id": "myagent", "action": "deploy"})
        assert resp.json()["request_id"] == "myagent:deploy"

    def test_validate_called_with_constitutional_hash(self):
        from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

        mock_result = MagicMock()
        mock_result.valid = True
        with patch.object(
            _mod, "validate_constitutional_hash", return_value=mock_result
        ) as mock_fn:
            self._post({"agent_id": "a", "action": "b"})
        mock_fn.assert_called_once_with(CONSTITUTIONAL_HASH)

    def test_record_validation_called(self):
        mock_result = MagicMock()
        mock_result.valid = True
        with (
            patch.object(_mod, "validate_constitutional_hash", return_value=mock_result),
            patch.object(_mod, "_record_validation") as mock_record,
        ):
            self._post({"agent_id": "a", "action": "b"})
        mock_record.assert_called_once()

    def test_record_validation_args(self):
        mock_result = MagicMock()
        mock_result.valid = True
        recorded_args = []

        def capture(*args, **kwargs):
            recorded_args.extend(args)

        with (
            patch.object(_mod, "validate_constitutional_hash", return_value=mock_result),
            patch.object(_mod, "_record_validation", side_effect=capture),
        ):
            self._post({"agent_id": "agt", "action": "act"})

        req_arg, compliant_arg, score_arg, _latency_arg, rid_arg = recorded_args
        assert req_arg.agent_id == "agt"
        assert req_arg.action == "act"
        assert compliant_arg is True
        assert score_arg == 1.0
        assert rid_arg == "agt:act"

    def test_with_context_and_policies(self):
        mock_result = MagicMock()
        mock_result.valid = True
        with patch.object(_mod, "validate_constitutional_hash", return_value=mock_result):
            resp = self._post(
                {
                    "agent_id": "a",
                    "action": "b",
                    "context": {"env": "prod"},
                    "policies": ["p1", "p2"],
                }
            )
        assert resp.status_code == 200

    def test_otel_span_invoked(self):
        """_otel_span should be called during validation."""
        mock_result = MagicMock()
        mock_result.valid = True
        span_calls = []

        original_otel_span = _mod._otel_span

        from contextlib import contextmanager

        @contextmanager
        def recording_span(name, attributes=None):
            span_calls.append((name, attributes))
            yield

        with (
            patch.object(_mod, "validate_constitutional_hash", return_value=mock_result),
            patch.object(_mod, "_otel_span", side_effect=recording_span),
        ):
            self._post({"agent_id": "a", "action": "b"})

        assert len(span_calls) == 1
        assert span_calls[0][0] == "v1.validate"
        assert span_calls[0][1]["agent_id"] == "a"
        assert span_calls[0][1]["action"] == "b"

    def test_response_fields_all_present(self):
        mock_result = MagicMock()
        mock_result.valid = True
        with patch.object(_mod, "validate_constitutional_hash", return_value=mock_result):
            resp = self._post({"agent_id": "a", "action": "b"})
        data = resp.json()
        for field in (
            "compliant",
            "constitutional_hash",
            "score",
            "violations",
            "latency_ms",
            "request_id",
        ):
            assert field in data, f"Missing field: {field}"


# ---------------------------------------------------------------------------
# POST /v1/validate — authentication failure
# ---------------------------------------------------------------------------


class TestV1ValidateAuthFailure:
    def test_missing_api_key_returns_401(self):
        """Without dependency override, missing key → 401."""
        from enhanced_agent_bus.api.rate_limiting import limiter
        from enhanced_agent_bus.api.routes.public_v1 import router

        app = FastAPI()
        app.state.limiter = limiter
        app.include_router(router)
        client = SyncASGIClient(app, raise_server_exceptions=False)

        resp = client.post(
            "/v1/validate",
            json={"agent_id": "x", "action": "y"},
            # No X-API-Key header
        )
        assert resp.status_code == 401

    def test_invalid_api_key_returns_401(self):
        from enhanced_agent_bus.api.rate_limiting import limiter
        from enhanced_agent_bus.api.routes.public_v1 import router

        app = FastAPI()
        app.state.limiter = limiter
        app.include_router(router)
        client = SyncASGIClient(app, raise_server_exceptions=False)

        resp = client.post(
            "/v1/validate",
            json={"agent_id": "x", "action": "y"},
            headers={"X-API-Key": "bad-key-12345"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /v1/validate — validation body errors
# ---------------------------------------------------------------------------


class TestV1ValidateBodyErrors:
    @pytest.fixture(autouse=True)
    def client(self):
        self._client = SyncASGIClient(_make_app(), raise_server_exceptions=False)

    def test_missing_agent_id_returns_422(self):
        resp = self._client.post("/v1/validate", json={"action": "read"})
        assert resp.status_code == 422

    def test_missing_action_returns_422(self):
        resp = self._client.post("/v1/validate", json={"agent_id": "a"})
        assert resp.status_code == 422

    def test_empty_body_returns_422(self):
        resp = self._client.post("/v1/validate", json={})
        assert resp.status_code == 422

    def test_null_agent_id_returns_422(self):
        resp = self._client.post("/v1/validate", json={"agent_id": None, "action": "x"})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Integration: validation store actually receives entries
# ---------------------------------------------------------------------------


class TestValidationStoreIntegration:
    def test_store_receives_entry_after_validate(self):
        from enhanced_agent_bus.api.validation_store import (
            ValidationStore,
            get_validation_store,
        )

        fresh_store = ValidationStore()

        app = _make_app()
        client = SyncASGIClient(app, raise_server_exceptions=True)

        mock_result = MagicMock()
        mock_result.valid = True

        with (
            patch.object(_mod, "validate_constitutional_hash", return_value=mock_result),
            patch.object(_mod, "get_validation_store", return_value=fresh_store),
        ):
            resp = client.post(
                "/v1/validate",
                json={"agent_id": "store_agent", "action": "store_action"},
            )

        assert resp.status_code == 200
        recent = fresh_store.get_recent()
        assert len(recent) == 1
        assert recent[0].agent_id == "store_agent"

    def test_multiple_requests_accumulate_in_store(self):
        from enhanced_agent_bus.api.validation_store import ValidationStore

        fresh_store = ValidationStore()
        app = _make_app()
        client = SyncASGIClient(app, raise_server_exceptions=True)

        mock_result = MagicMock()
        mock_result.valid = True

        with (
            patch.object(_mod, "validate_constitutional_hash", return_value=mock_result),
            patch.object(_mod, "get_validation_store", return_value=fresh_store),
        ):
            for i in range(3):
                client.post(
                    "/v1/validate",
                    json={"agent_id": f"agent{i}", "action": "op"},
                )

        assert len(fresh_store.get_recent()) == 3


# ---------------------------------------------------------------------------
# Validate endpoint — real constitutional hash (no mock)
# ---------------------------------------------------------------------------


class TestV1ValidateRealHash:
    @pytest.fixture(autouse=True)
    def client(self, monkeypatch):
        # Guarantee sandbox mode for this worker regardless of xdist worker state.
        # Other tests may clear ENVIRONMENT without proper cleanup; ensure it is
        # restored to "test" for the duration of each test in this class.
        monkeypatch.setenv("ENVIRONMENT", "test")
        self._client = SyncASGIClient(_make_app(), raise_server_exceptions=True)

    def test_real_hash_validates_as_compliant(self):
        """The real CONSTITUTIONAL_HASH should validate as compliant."""
        resp = self._client.post(
            "/v1/validate", json={"agent_id": "real_agent", "action": "real_action"}
        )
        assert resp.status_code == 200
        data = resp.json()
        # The canonical hash is valid so compliant should be True
        assert data["compliant"] is True
        assert data["score"] == 1.0
        assert data["violations"] == []

    def test_real_hash_in_response(self):
        from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

        resp = self._client.post("/v1/validate", json={"agent_id": "r", "action": "s"})
        assert resp.json()["constitutional_hash"] == CONSTITUTIONAL_HASH
