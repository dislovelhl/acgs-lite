"""Tests for FastAPI governance microservice wrapper."""

from __future__ import annotations

from typing import Any, Callable, cast

import pytest
from fastapi.routing import APIRoute

from acgs_lite import Constitution, Rule, Severity
from acgs_lite.server import create_governance_app


@pytest.mark.unit
class TestGovernanceServer:
    @staticmethod
    def _route_endpoint(app: Any, path: str) -> Callable[..., dict[str, Any]]:
        for route in app.routes:
            if isinstance(route, APIRoute) and route.path == path:
                return cast(Callable[..., dict[str, Any]], route.endpoint)
        raise AssertionError(f"Route {path!r} not found")

    def test_validate_endpoint_allows_safe_action(self) -> None:
        app = create_governance_app(Constitution.default())
        validate = self._route_endpoint(app, "/validate")
        data = validate({"action": "deploy to staging"})
        assert data["valid"] is True
        assert data["rules_checked"] >= 1

    def test_validate_endpoint_reports_violation(self) -> None:
        constitution = Constitution.from_rules(
            [
                Rule(
                    id="S-001",
                    text="No self approval",
                    severity=Severity.CRITICAL,
                    keywords=["self-approve"],
                )
            ]
        )
        app = create_governance_app(constitution)
        validate = self._route_endpoint(app, "/validate")
        data = validate({"action": "self-approve merge"})
        assert data["valid"] is False
        assert any(v["rule_id"] == "S-001" for v in data["violations"])

    def test_stats_endpoint_reports_validation_count(self) -> None:
        app = create_governance_app(Constitution.default())
        validate = self._route_endpoint(app, "/validate")
        get_stats = self._route_endpoint(app, "/stats")

        validate({"action": "safe action one"})
        validate({"action": "safe action two"})

        stats = get_stats()
        assert stats["total_validations"] >= 2
        assert "constitutional_hash" in stats
