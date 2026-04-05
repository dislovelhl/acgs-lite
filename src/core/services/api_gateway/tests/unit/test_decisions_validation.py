from __future__ import annotations

from src.core.services.api_gateway.main import app
from src.core.shared.security.auth import UserClaims, get_current_user

_TEST_USER = UserClaims(
    sub="decision-tester",
    tenant_id="tenant-1",
    roles=["admin"],
    permissions=[],
    exp=9_999_999_999,
    iat=1_000_000_000,
)


class TestDecisionExplanationValidation:
    def test_generate_explanation_rejects_invalid_verdict(self, client) -> None:
        app.dependency_overrides[get_current_user] = lambda: _TEST_USER
        try:
            response = client.post(
                "/api/v1/decisions/explain",
                json={"message": {"action": "review"}, "verdict": "DROP TABLE"},
            )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 422
        assert "verdict must be one of" in response.text
