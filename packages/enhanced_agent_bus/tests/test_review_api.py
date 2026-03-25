"""
Tests for constitutional review API endpoints.
Constitutional Hash: 608508a9bd224290
"""

from contextlib import contextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from enhanced_agent_bus.constitutional.amendment_model import (
    AmendmentProposal,
    AmendmentStatus,
)
from enhanced_agent_bus.constitutional.review_api import (
    AmendmentDetailResponse,
    AmendmentListQuery,
    AmendmentListResponse,
    ApprovalRequest,
    ApprovalResponse,
    RejectionRequest,
    RollbackRequest,
    RollbackResponse,
    approve_amendment,
    get_amendment,
    health_check,
    list_amendments,
    reject_amendment,
    router,
)
from enhanced_agent_bus.maci.models import MACIValidationResult


def _make_amendment(**kwargs):
    """Create a minimal valid AmendmentProposal for tests."""
    defaults = {
        "proposed_changes": {"section": "content"},
        "justification": "Test justification for this amendment proposal",
        "proposer_agent_id": "agent-test",
        "target_version": "1.0.0",
    }
    defaults.update(kwargs)
    return AmendmentProposal(**defaults)


_MISSING = object()


@contextmanager
def _review_api_patch(name: str, value=_MISSING):
    globals_dict = list_amendments.__globals__
    had_original = name in globals_dict
    original = globals_dict.get(name)
    replacement = MagicMock(name=name) if value is _MISSING else value
    globals_dict[name] = replacement
    try:
        yield replacement
    finally:
        if had_original:
            globals_dict[name] = original
        else:
            globals_dict.pop(name, None)


# ---------------------------------------------------------------------------
# Pydantic model unit tests
# ---------------------------------------------------------------------------


class TestAmendmentListQuery:
    """Tests for AmendmentListQuery model."""

    def test_defaults(self):
        q = AmendmentListQuery()
        assert q.status is None
        assert q.proposer_agent_id is None
        assert q.limit == 50
        assert q.offset == 0
        assert q.order_by == "created_at"
        assert q.order == "desc"

    def test_custom_values(self):
        q = AmendmentListQuery(limit=10, offset=5, order_by="impact_score", order="asc")
        assert q.limit == 10
        assert q.offset == 5
        assert q.order_by == "impact_score"
        assert q.order == "asc"

    def test_limit_bounds(self):
        q = AmendmentListQuery(limit=1)
        assert q.limit == 1
        q = AmendmentListQuery(limit=250)
        assert q.limit == 250


class TestApprovalRequest:
    """Tests for ApprovalRequest model."""

    def test_required_fields(self):
        req = ApprovalRequest(approver_agent_id="agent-1")
        assert req.approver_agent_id == "agent-1"
        assert req.comments is None
        assert req.metadata == {}

    def test_with_optional_fields(self):
        req = ApprovalRequest(
            approver_agent_id="agent-1",
            comments="Looks good",
            metadata={"key": "value"},
        )
        assert req.comments == "Looks good"
        assert req.metadata == {"key": "value"}


class TestRejectionRequest:
    """Tests for RejectionRequest model."""

    def test_required_fields(self):
        req = RejectionRequest(
            rejector_agent_id="agent-2",
            reason="This violates principle X and must be revised",
        )
        assert req.rejector_agent_id == "agent-2"
        assert "violates" in req.reason


class TestApprovalResponse:
    """Tests for ApprovalResponse model."""

    def test_construction(self):
        amendment = _make_amendment()
        resp = ApprovalResponse(
            success=True,
            amendment=amendment,
            message="Approved",
            next_steps=["Step 1"],
        )
        assert resp.success is True
        assert resp.message == "Approved"
        assert len(resp.next_steps) == 1


class TestRollbackRequest:
    """Tests for RollbackRequest model."""

    def test_required_fields(self):
        req = RollbackRequest(
            requester_agent_id="agent-3",
            justification="Emergency rollback due to critical governance failure detected",
        )
        assert req.requester_agent_id == "agent-3"
        assert len(req.justification) >= 20


class TestRollbackResponse:
    """Tests for RollbackResponse model."""

    def test_construction(self):
        resp = RollbackResponse(
            success=True,
            rollback_id="rb-123",
            previous_version="1.0.0",
            restored_version="0.9.0",
            message="Rolled back",
            justification="Governance failure detected with critical metrics",
        )
        assert resp.success is True
        assert resp.rollback_id == "rb-123"
        assert resp.degradation_detected is False


class TestAmendmentListResponse:
    """Tests for AmendmentListResponse model."""

    def test_construction(self):
        resp = AmendmentListResponse(
            amendments=[],
            total=0,
            limit=50,
            offset=0,
        )
        assert resp.total == 0
        assert resp.limit == 50
        assert resp.constitutional_hash is not None
        assert resp.timestamp is not None


class TestAmendmentDetailResponse:
    """Tests for AmendmentDetailResponse model."""

    def test_construction(self):
        amendment = _make_amendment()
        resp = AmendmentDetailResponse(
            amendment=amendment,
        )
        assert resp.diff is None
        assert resp.target_version is None
        assert resp.governance_metrics_delta == {}
        assert resp.approval_status == {}


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_check():
    result = await health_check()
    assert result["status"] == "healthy"
    assert result["service"] == "constitutional-review-api"
    assert "constitutional_hash" in result
    assert "timestamp" in result


@pytest.mark.asyncio
async def test_list_amendments_invalid_status():
    with _review_api_patch("ConstitutionalStorageService", MagicMock(return_value=AsyncMock())):
        with pytest.raises(HTTPException) as exc_info:
            await list_amendments(status="invalid_status_xyz")
    assert exc_info.value.status_code == 400
    assert "Invalid status" in exc_info.value.detail


@pytest.mark.asyncio
async def test_list_amendments_invalid_order_by():
    with _review_api_patch("ConstitutionalStorageService", MagicMock(return_value=AsyncMock())):
        with pytest.raises(HTTPException) as exc_info:
            await list_amendments(
                status=None,
                proposer_agent_id=None,
                limit=50,
                offset=0,
                order_by="nonexistent_field",
                order="desc",
            )
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_list_amendments_invalid_order():
    with _review_api_patch("ConstitutionalStorageService", MagicMock(return_value=AsyncMock())):
        with pytest.raises(HTTPException) as exc_info:
            await list_amendments(
                status=None,
                proposer_agent_id=None,
                limit=50,
                offset=0,
                order_by="created_at",
                order="sideways",
            )
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_list_amendments_success():
    mock_storage = AsyncMock()
    mock_storage.list_amendments.return_value = ([], 0)
    with _review_api_patch("ConstitutionalStorageService", MagicMock(return_value=mock_storage)):
        result = await list_amendments(
            status=None,
            proposer_agent_id=None,
            limit=50,
            offset=0,
            order_by="created_at",
            order="desc",
        )
    assert isinstance(result, AmendmentListResponse)
    assert result.total == 0
    assert result.amendments == []
    mock_storage.connect.assert_awaited_once()
    mock_storage.disconnect.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_amendments_storage_failure():
    mock_storage = AsyncMock()
    mock_storage.connect.side_effect = RuntimeError("DB down")
    with _review_api_patch("ConstitutionalStorageService", MagicMock(return_value=mock_storage)):
        with pytest.raises(HTTPException) as exc_info:
            await list_amendments()
    assert exc_info.value.status_code == 500


@pytest.mark.asyncio
async def test_get_amendment_not_found():
    mock_storage = AsyncMock()
    mock_storage.get_amendment.return_value = None
    with _review_api_patch("ConstitutionalStorageService", MagicMock(return_value=mock_storage)):
        with pytest.raises(HTTPException) as exc_info:
            await get_amendment("nonexistent-id")
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_amendment_success():
    amendment = _make_amendment(
        governance_metrics_before={"health": 0.9},
        governance_metrics_after={"health": 0.85},
    )

    mock_storage = AsyncMock()
    mock_storage.get_amendment.return_value = amendment
    mock_storage.get_version.return_value = None  # skip diff to avoid Pydantic issues
    with (
        _review_api_patch("ConstitutionalStorageService", MagicMock(return_value=mock_storage)),
        _review_api_patch("ConstitutionalDiffEngine", MagicMock()),
    ):
        result = await get_amendment("amend-1", include_diff=False, include_target_version=False)
    assert isinstance(result, AmendmentDetailResponse)
    assert result.governance_metrics_delta["health"] == pytest.approx(-0.05)


@pytest.mark.asyncio
async def test_get_amendment_storage_failure():
    mock_storage = AsyncMock()
    mock_storage.connect.side_effect = RuntimeError("fail")
    with _review_api_patch("ConstitutionalStorageService", MagicMock(return_value=mock_storage)):
        with pytest.raises(HTTPException) as exc_info:
            await get_amendment("amend-1")
    assert exc_info.value.status_code == 500


def test_router_prefix():
    assert router.prefix == "/api/v1/constitutional"
    assert "constitutional-amendments" in router.tags


@pytest.mark.asyncio
async def test_approve_amendment_accepts_typed_maci_result():
    amendment = _make_amendment(status=AmendmentStatus.PROPOSED, approval_chain=[])
    mock_maci = AsyncMock()
    mock_maci.validate_action = AsyncMock(return_value=MACIValidationResult(is_valid=True))
    mock_maci_cls = MagicMock(return_value=mock_maci)

    mock_storage = AsyncMock()
    mock_storage.get_amendment.return_value = amendment
    mock_storage_cls = MagicMock(return_value=mock_storage)

    mock_hitl = MagicMock()
    mock_hitl._determine_approval_chain.return_value = MagicMock(required_approvals=1)
    mock_hitl_cls = MagicMock(return_value=mock_hitl)

    with (
        _review_api_patch("MACIEnforcer", mock_maci_cls),
        _review_api_patch("ConstitutionalStorageService", mock_storage_cls),
        _review_api_patch("ConstitutionalHITLIntegration", mock_hitl_cls),
        _review_api_patch("AuditClient", MagicMock(return_value=AsyncMock())),
    ):
        result = await approve_amendment(
            "amend-1",
            ApprovalRequest(approver_agent_id="judge-1", comments="approved"),
            x_agent_id="judge-1",
        )

    assert result.success is True
    assert result.amendment.status == AmendmentStatus.APPROVED


@pytest.mark.asyncio
async def test_reject_amendment_denies_typed_maci_result():
    mock_maci = AsyncMock()
    mock_maci.validate_action = AsyncMock(return_value=MACIValidationResult(is_valid=False))
    with _review_api_patch("MACIEnforcer", MagicMock(return_value=mock_maci)):
        with pytest.raises(HTTPException) as exc_info:
            await reject_amendment(
                "amend-1",
                RejectionRequest(
                    rejector_agent_id="exec-1",
                    reason="This violates principle X and must be revised",
                ),
                x_agent_id="exec-1",
            )

    assert exc_info.value.status_code == 403
