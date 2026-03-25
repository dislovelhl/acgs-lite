"""
ACGS-2 Enhanced Agent Bus - PQC Enforcement Models Coverage Tests
Constitutional Hash: 608508a9bd224290

Covers: enhanced_agent_bus/pqc_enforcement_models.py (26 stmts, 0% -> target 100%)
Tests Pydantic models for PQC enforcement mode administration.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

pytestmark = [pytest.mark.governance, pytest.mark.constitutional]


class TestEnforcementModeRequest:
    def test_strict_mode(self) -> None:
        from enhanced_agent_bus.pqc_enforcement_models import EnforcementModeRequest

        req = EnforcementModeRequest(mode="strict")
        assert req.mode == "strict"
        assert req.scope == "global"

    def test_permissive_mode_with_scope(self) -> None:
        from enhanced_agent_bus.pqc_enforcement_models import EnforcementModeRequest

        req = EnforcementModeRequest(mode="permissive", scope="tenant-123")
        assert req.mode == "permissive"
        assert req.scope == "tenant-123"

    def test_invalid_mode_rejected(self) -> None:
        from pydantic import ValidationError

        from enhanced_agent_bus.pqc_enforcement_models import EnforcementModeRequest

        with pytest.raises(ValidationError):
            EnforcementModeRequest(mode="invalid")  # type: ignore[arg-type]


class TestEnforcementModeResponse:
    def test_construction(self) -> None:
        from enhanced_agent_bus.pqc_enforcement_models import EnforcementModeResponse

        now = datetime.now(UTC)
        resp = EnforcementModeResponse(
            mode="strict",
            activated_at=now,
            activated_by="admin@acgs",
            scope="global",
            propagation_deadline_seconds=300,
        )
        assert resp.mode == "strict"
        assert resp.activated_by == "admin@acgs"
        assert resp.propagation_deadline_seconds == 300


class TestPQCRejectionError:
    def test_construction(self) -> None:
        from enhanced_agent_bus.pqc_enforcement_models import PQCRejectionError

        err = PQCRejectionError(
            error_code="PQC_REQUIRED",
            message="Classical key rejected in strict mode",
            supported_algorithms=["ML-KEM-768", "ML-DSA-65"],
            docs_url="https://docs.acgs/pqc",
        )
        assert err.error_code == "PQC_REQUIRED"
        assert len(err.supported_algorithms) == 2

    def test_optional_fields(self) -> None:
        from enhanced_agent_bus.pqc_enforcement_models import PQCRejectionError

        err = PQCRejectionError(
            error_code="PQC_REQUIRED",
            message="Classical key rejected",
        )
        assert err.supported_algorithms == []
        assert err.docs_url is None


class TestPQCAdoptionWindow:
    def test_construction(self) -> None:
        from enhanced_agent_bus.pqc_enforcement_models import PQCAdoptionWindow

        window = PQCAdoptionWindow(
            window="1h",
            pqc_verified_count=100,
            classical_verified_count=20,
            pqc_adoption_rate=0.83,
        )
        assert window.window == "1h"
        assert window.pqc_adoption_rate == 0.83


class TestPQCAdoptionMetricsResponse:
    def test_construction(self) -> None:
        from enhanced_agent_bus.pqc_enforcement_models import (
            PQCAdoptionMetricsResponse,
            PQCAdoptionWindow,
        )

        now = datetime.now(UTC)
        resp = PQCAdoptionMetricsResponse(
            windows=[
                PQCAdoptionWindow(
                    window="1h",
                    pqc_verified_count=50,
                    classical_verified_count=10,
                    pqc_adoption_rate=0.83,
                ),
                PQCAdoptionWindow(
                    window="24h",
                    pqc_verified_count=500,
                    classical_verified_count=100,
                    pqc_adoption_rate=0.83,
                ),
            ],
            generated_at=now,
        )
        assert len(resp.windows) == 2
        assert resp.generated_at == now
