"""
Tests for data_subject.py route coverage.
Constitutional Hash: cdd01ef066bc6cf2

Covers: access, erasure (create/status/process/certificate), classify endpoints.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.services.api_gateway.routes.data_subject import data_subject_v1_router
from src.core.shared.security.auth import UserClaims, get_current_user


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_user(roles: list[str] | None = None) -> UserClaims:
    now = int(datetime.now(UTC).timestamp())
    return UserClaims(
        sub="user-1",
        tenant_id="tenant-1",
        roles=roles or ["user"],
        permissions=["read"],
        exp=now + 3600,
        iat=now,
    )


_USER = _make_user()


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(data_subject_v1_router)
    app.dependency_overrides[get_current_user] = lambda: _USER
    return app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(_build_app())


# ---------------------------------------------------------------------------
# /access endpoint
# ---------------------------------------------------------------------------


class TestDataSubjectAccess:
    """POST /api/v1/data-subject/access"""

    def test_access_returns_200_default_categories(self, client: TestClient):
        resp = client.post(
            "/api/v1/data-subject/access",
            json={"data_subject_id": "ds-1"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["data_subject_id"] == "ds-1"
        assert body["data_count"] == 42
        assert "personal_identifiers" in body["data_categories"]
        assert body["constitutional_hash"] == "cdd01ef066bc6cf2"

    def test_access_with_explicit_categories(self, client: TestClient):
        resp = client.post(
            "/api/v1/data-subject/access",
            json={"data_subject_id": "ds-2", "categories": ["email"]},
        )
        assert resp.status_code == 200
        assert resp.json()["data_categories"] == ["email"]

    def test_access_with_format(self, client: TestClient):
        resp = client.post(
            "/api/v1/data-subject/access",
            json={"data_subject_id": "ds-3", "format": "csv"},
        )
        assert resp.status_code == 200

    def test_access_missing_data_subject_id(self, client: TestClient):
        resp = client.post("/api/v1/data-subject/access", json={})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# /erasure endpoint (POST create)
# ---------------------------------------------------------------------------


class TestErasureCreate:
    """POST /api/v1/data-subject/erasure"""

    def test_erasure_503_when_service_unavailable(self, client: TestClient):
        with patch(
            "src.core.services.api_gateway.routes.data_subject.GDPR_ERASURE_AVAILABLE",
            False,
        ):
            resp = client.post(
                "/api/v1/data-subject/erasure",
                json={"data_subject_id": "ds-1"},
            )
            assert resp.status_code == 503
            assert resp.json()["detail"]["error"] == "gdpr_service_unavailable"

    def test_erasure_success(self, client: TestClient):
        mock_request = MagicMock()
        mock_request.request_id = str(uuid.uuid4())
        mock_request.data_subject_id = "ds-1"
        mock_request.status = MagicMock(value="pending")
        mock_request.deadline = datetime.now(UTC) + timedelta(days=30)
        mock_request.requested_at = datetime.now(UTC)

        mock_handler = AsyncMock()
        mock_handler.request_erasure = AsyncMock(return_value=mock_request)

        with (
            patch(
                "src.core.services.api_gateway.routes.data_subject.GDPR_ERASURE_AVAILABLE",
                True,
            ),
            patch(
                "src.core.shared.security.gdpr_erasure.get_gdpr_erasure_handler",
                return_value=mock_handler,
            ),
        ):
            resp = client.post(
                "/api/v1/data-subject/erasure",
                json={"data_subject_id": "ds-1", "scope": "all_data"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "pending"
            assert body["data_subject_id"] == "ds-1"

    def test_erasure_value_error_returns_400(self, client: TestClient):
        mock_handler = AsyncMock()
        mock_handler.request_erasure = AsyncMock(side_effect=ValueError("bad input"))

        with (
            patch(
                "src.core.services.api_gateway.routes.data_subject.GDPR_ERASURE_AVAILABLE",
                True,
            ),
            patch(
                "src.core.shared.security.gdpr_erasure.get_gdpr_erasure_handler",
                return_value=mock_handler,
            ),
        ):
            resp = client.post(
                "/api/v1/data-subject/erasure",
                json={"data_subject_id": "ds-1"},
            )
            assert resp.status_code == 400
            assert resp.json()["detail"]["error"] == "invalid_erasure_request"

    def test_erasure_runtime_error_returns_500(self, client: TestClient):
        mock_handler = AsyncMock()
        mock_handler.request_erasure = AsyncMock(side_effect=RuntimeError("db down"))

        with (
            patch(
                "src.core.services.api_gateway.routes.data_subject.GDPR_ERASURE_AVAILABLE",
                True,
            ),
            patch(
                "src.core.shared.security.gdpr_erasure.get_gdpr_erasure_handler",
                return_value=mock_handler,
            ),
        ):
            resp = client.post(
                "/api/v1/data-subject/erasure",
                json={"data_subject_id": "ds-1"},
            )
            assert resp.status_code == 500
            assert resp.json()["detail"]["error"] == "erasure_request_failed"

    def test_erasure_specific_categories_scope(self, client: TestClient):
        mock_request = MagicMock()
        mock_request.request_id = str(uuid.uuid4())
        mock_request.data_subject_id = "ds-1"
        mock_request.status = MagicMock(value="pending")
        mock_request.deadline = datetime.now(UTC) + timedelta(days=30)
        mock_request.requested_at = datetime.now(UTC)

        mock_handler = AsyncMock()
        mock_handler.request_erasure = AsyncMock(return_value=mock_request)

        with (
            patch(
                "src.core.services.api_gateway.routes.data_subject.GDPR_ERASURE_AVAILABLE",
                True,
            ),
            patch(
                "src.core.shared.security.gdpr_erasure.get_gdpr_erasure_handler",
                return_value=mock_handler,
            ),
        ):
            resp = client.post(
                "/api/v1/data-subject/erasure",
                json={
                    "data_subject_id": "ds-1",
                    "scope": "specific_categories",
                    "specific_categories": ["email"],
                },
            )
            assert resp.status_code == 200


# ---------------------------------------------------------------------------
# /erasure/{request_id} GET status
# ---------------------------------------------------------------------------


class TestErasureStatus:
    """GET /api/v1/data-subject/erasure/{request_id}"""

    def test_status_503_when_unavailable(self, client: TestClient):
        with patch(
            "src.core.services.api_gateway.routes.data_subject.GDPR_ERASURE_AVAILABLE",
            False,
        ):
            resp = client.get("/api/v1/data-subject/erasure/req-1")
            assert resp.status_code == 503

    def test_status_success(self, client: TestClient):
        mock_req = MagicMock()
        mock_req.request_id = "req-1"
        mock_req.data_subject_id = "ds-1"
        mock_req.status = MagicMock(value="in_progress")
        mock_req.system_results = [MagicMock(success=True), MagicMock(success=False)]
        mock_req.total_records_erased = 10
        mock_req.started_at = datetime.now(UTC)
        mock_req.completed_at = None

        mock_handler = AsyncMock()
        mock_handler.get_request = AsyncMock(return_value=mock_req)

        with (
            patch(
                "src.core.services.api_gateway.routes.data_subject.GDPR_ERASURE_AVAILABLE",
                True,
            ),
            patch(
                "src.core.shared.security.gdpr_erasure.get_gdpr_erasure_handler",
                return_value=mock_handler,
            ),
        ):
            resp = client.get("/api/v1/data-subject/erasure/req-1")
            assert resp.status_code == 200
            body = resp.json()
            assert body["systems_processed"] == 2
            assert body["systems_successful"] == 1
            assert body["total_records_erased"] == 10

    def test_status_completed_request(self, client: TestClient):
        mock_req = MagicMock()
        mock_req.request_id = "req-2"
        mock_req.data_subject_id = "ds-1"
        mock_req.status = MagicMock(value="completed")
        mock_req.system_results = [MagicMock(success=True)]
        mock_req.total_records_erased = 5
        mock_req.started_at = datetime.now(UTC)
        mock_req.completed_at = datetime.now(UTC)

        mock_handler = AsyncMock()
        mock_handler.get_request = AsyncMock(return_value=mock_req)

        with (
            patch(
                "src.core.services.api_gateway.routes.data_subject.GDPR_ERASURE_AVAILABLE",
                True,
            ),
            patch(
                "src.core.shared.security.gdpr_erasure.get_gdpr_erasure_handler",
                return_value=mock_handler,
            ),
        ):
            resp = client.get("/api/v1/data-subject/erasure/req-2")
            assert resp.status_code == 200
            assert resp.json()["status"] == "completed"

    def test_status_not_found(self, client: TestClient):
        mock_handler = AsyncMock()
        mock_handler.get_request = AsyncMock(return_value=None)

        with (
            patch(
                "src.core.services.api_gateway.routes.data_subject.GDPR_ERASURE_AVAILABLE",
                True,
            ),
            patch(
                "src.core.shared.security.gdpr_erasure.get_gdpr_erasure_handler",
                return_value=mock_handler,
            ),
        ):
            resp = client.get("/api/v1/data-subject/erasure/req-missing")
            assert resp.status_code == 404

    def test_status_value_error_returns_404(self, client: TestClient):
        mock_handler = AsyncMock()
        mock_handler.get_request = AsyncMock(side_effect=ValueError("not found"))

        with (
            patch(
                "src.core.services.api_gateway.routes.data_subject.GDPR_ERASURE_AVAILABLE",
                True,
            ),
            patch(
                "src.core.shared.security.gdpr_erasure.get_gdpr_erasure_handler",
                return_value=mock_handler,
            ),
        ):
            resp = client.get("/api/v1/data-subject/erasure/req-bad")
            assert resp.status_code == 404

    def test_status_runtime_error_returns_500(self, client: TestClient):
        mock_handler = AsyncMock()
        mock_handler.get_request = AsyncMock(side_effect=RuntimeError("db down"))

        with (
            patch(
                "src.core.services.api_gateway.routes.data_subject.GDPR_ERASURE_AVAILABLE",
                True,
            ),
            patch(
                "src.core.shared.security.gdpr_erasure.get_gdpr_erasure_handler",
                return_value=mock_handler,
            ),
        ):
            resp = client.get("/api/v1/data-subject/erasure/req-err")
            assert resp.status_code == 500


# ---------------------------------------------------------------------------
# /erasure/{request_id}/process
# ---------------------------------------------------------------------------


class TestErasureProcess:
    """POST /api/v1/data-subject/erasure/{request_id}/process"""

    def test_process_503_when_unavailable(self, client: TestClient):
        with patch(
            "src.core.services.api_gateway.routes.data_subject.GDPR_ERASURE_AVAILABLE",
            False,
        ):
            resp = client.post("/api/v1/data-subject/erasure/req-1/process")
            assert resp.status_code == 503

    def test_process_success(self, client: TestClient):
        mock_result = MagicMock()
        mock_result.request_id = "req-1"
        mock_result.data_subject_id = "ds-1"
        mock_result.status = MagicMock(value="completed")
        mock_result.system_results = [MagicMock(success=True)]
        mock_result.total_records_erased = 15
        mock_result.started_at = datetime.now(UTC)
        mock_result.completed_at = datetime.now(UTC)

        mock_handler = AsyncMock()
        mock_handler.validate_request = AsyncMock()
        mock_handler.check_exemptions = AsyncMock()
        mock_handler.discover_data_locations = AsyncMock()
        mock_handler.process_erasure = AsyncMock(return_value=mock_result)

        with (
            patch(
                "src.core.services.api_gateway.routes.data_subject.GDPR_ERASURE_AVAILABLE",
                True,
            ),
            patch(
                "src.core.shared.security.gdpr_erasure.get_gdpr_erasure_handler",
                return_value=mock_handler,
            ),
        ):
            resp = client.post("/api/v1/data-subject/erasure/req-1/process")
            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "completed"
            assert body["total_records_erased"] == 15

    def test_process_value_error_returns_404(self, client: TestClient):
        mock_handler = AsyncMock()
        mock_handler.validate_request = AsyncMock(side_effect=ValueError("not found"))

        with (
            patch(
                "src.core.services.api_gateway.routes.data_subject.GDPR_ERASURE_AVAILABLE",
                True,
            ),
            patch(
                "src.core.shared.security.gdpr_erasure.get_gdpr_erasure_handler",
                return_value=mock_handler,
            ),
        ):
            resp = client.post("/api/v1/data-subject/erasure/req-bad/process")
            assert resp.status_code == 404

    def test_process_runtime_error_returns_500(self, client: TestClient):
        mock_handler = AsyncMock()
        mock_handler.validate_request = AsyncMock(side_effect=RuntimeError("boom"))

        with (
            patch(
                "src.core.services.api_gateway.routes.data_subject.GDPR_ERASURE_AVAILABLE",
                True,
            ),
            patch(
                "src.core.shared.security.gdpr_erasure.get_gdpr_erasure_handler",
                return_value=mock_handler,
            ),
        ):
            resp = client.post("/api/v1/data-subject/erasure/req-err/process")
            assert resp.status_code == 500


# ---------------------------------------------------------------------------
# /erasure/{request_id}/certificate
# ---------------------------------------------------------------------------


class TestErasureCertificate:
    """GET /api/v1/data-subject/erasure/{request_id}/certificate"""

    def test_certificate_503_when_unavailable(self, client: TestClient):
        with patch(
            "src.core.services.api_gateway.routes.data_subject.GDPR_ERASURE_AVAILABLE",
            False,
        ):
            resp = client.get("/api/v1/data-subject/erasure/req-1/certificate")
            assert resp.status_code == 503

    def test_certificate_success(self, client: TestClient):
        mock_cert = MagicMock()
        mock_cert.certificate_id = "cert-1"
        mock_cert.request_id = "req-1"
        mock_cert.data_subject_id = "ds-1"
        mock_cert.systems_processed = 3
        mock_cert.systems_successful = 3
        mock_cert.total_records_erased = 42
        mock_cert.gdpr_article_17_compliant = True
        mock_cert.issued_at = datetime.now(UTC)
        mock_cert.valid_until = datetime.now(UTC) + timedelta(days=365)
        mock_cert.certificate_hash = "abc123"

        mock_handler = AsyncMock()
        mock_handler.generate_erasure_certificate = AsyncMock(return_value=mock_cert)

        with (
            patch(
                "src.core.services.api_gateway.routes.data_subject.GDPR_ERASURE_AVAILABLE",
                True,
            ),
            patch(
                "src.core.shared.security.gdpr_erasure.get_gdpr_erasure_handler",
                return_value=mock_handler,
            ),
        ):
            resp = client.get("/api/v1/data-subject/erasure/req-1/certificate")
            assert resp.status_code == 200
            body = resp.json()
            assert body["certificate_id"] == "cert-1"
            assert body["gdpr_article_17_compliant"] is True

    def test_certificate_not_found(self, client: TestClient):
        mock_handler = AsyncMock()
        mock_handler.generate_erasure_certificate = AsyncMock(
            side_effect=ValueError("Request not found")
        )

        with (
            patch(
                "src.core.services.api_gateway.routes.data_subject.GDPR_ERASURE_AVAILABLE",
                True,
            ),
            patch(
                "src.core.shared.security.gdpr_erasure.get_gdpr_erasure_handler",
                return_value=mock_handler,
            ),
        ):
            resp = client.get("/api/v1/data-subject/erasure/req-missing/certificate")
            assert resp.status_code == 404

    def test_certificate_bad_request(self, client: TestClient):
        mock_handler = AsyncMock()
        mock_handler.generate_erasure_certificate = AsyncMock(
            side_effect=ValueError("Request not completed yet")
        )

        with (
            patch(
                "src.core.services.api_gateway.routes.data_subject.GDPR_ERASURE_AVAILABLE",
                True,
            ),
            patch(
                "src.core.shared.security.gdpr_erasure.get_gdpr_erasure_handler",
                return_value=mock_handler,
            ),
        ):
            resp = client.get("/api/v1/data-subject/erasure/req-incomplete/certificate")
            assert resp.status_code == 400
            assert resp.json()["detail"]["error"] == "certificate_generation_failed"

    def test_certificate_runtime_error_returns_500(self, client: TestClient):
        mock_handler = AsyncMock()
        mock_handler.generate_erasure_certificate = AsyncMock(
            side_effect=RuntimeError("storage fail")
        )

        with (
            patch(
                "src.core.services.api_gateway.routes.data_subject.GDPR_ERASURE_AVAILABLE",
                True,
            ),
            patch(
                "src.core.shared.security.gdpr_erasure.get_gdpr_erasure_handler",
                return_value=mock_handler,
            ),
        ):
            resp = client.get("/api/v1/data-subject/erasure/req-err/certificate")
            assert resp.status_code == 500


# ---------------------------------------------------------------------------
# /classify endpoint
# ---------------------------------------------------------------------------


class TestClassifyData:
    """POST /api/v1/data-subject/classify"""

    def test_classify_503_when_unavailable(self, client: TestClient):
        with patch(
            "src.core.services.api_gateway.routes.data_subject.PII_DETECTOR_AVAILABLE",
            False,
        ):
            resp = client.post(
                "/api/v1/data-subject/classify",
                json={"data": {"name": "John"}},
            )
            assert resp.status_code == 503
            assert resp.json()["detail"]["error"] == "pii_detector_unavailable"

    def test_classify_success(self, client: TestClient):
        mock_result = MagicMock()
        mock_result.classification_id = "cls-1"
        mock_result.tier = MagicMock(value="high")
        mock_result.pii_categories = [MagicMock(value="name"), MagicMock(value="email")]
        mock_result.overall_confidence = 0.95
        mock_result.recommended_retention_days = 30
        mock_result.requires_encryption = True
        mock_result.requires_audit_logging = True
        mock_result.applicable_frameworks = [MagicMock(value="GDPR"), MagicMock(value="CCPA")]
        mock_result.classified_at = datetime.now(UTC)

        with (
            patch(
                "src.core.services.api_gateway.routes.data_subject.PII_DETECTOR_AVAILABLE",
                True,
            ),
            patch(
                "src.core.shared.security.pii_detector.classify_data",
                return_value=mock_result,
            ),
        ):
            resp = client.post(
                "/api/v1/data-subject/classify",
                json={"data": {"name": "John", "email": "john@example.com"}},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["classification_id"] == "cls-1"
            assert body["tier"] == "high"
            assert body["requires_encryption"] is True

    def test_classify_value_error_returns_400(self, client: TestClient):
        with (
            patch(
                "src.core.services.api_gateway.routes.data_subject.PII_DETECTOR_AVAILABLE",
                True,
            ),
            patch(
                "src.core.shared.security.pii_detector.classify_data",
                side_effect=ValueError("invalid input"),
            ),
        ):
            resp = client.post(
                "/api/v1/data-subject/classify",
                json={"data": {}},
            )
            assert resp.status_code == 400

    def test_classify_runtime_error_returns_500(self, client: TestClient):
        with (
            patch(
                "src.core.services.api_gateway.routes.data_subject.PII_DETECTOR_AVAILABLE",
                True,
            ),
            patch(
                "src.core.shared.security.pii_detector.classify_data",
                side_effect=RuntimeError("engine crash"),
            ),
        ):
            resp = client.post(
                "/api/v1/data-subject/classify",
                json={"data": {"x": 1}},
            )
            assert resp.status_code == 500
