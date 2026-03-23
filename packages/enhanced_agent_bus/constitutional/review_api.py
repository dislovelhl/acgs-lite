"""
ACGS-2 Enhanced Agent Bus - Constitutional Amendment Review API
Constitutional Hash: cdd01ef066bc6cf2

API endpoints for reviewing, approving, and rejecting constitutional amendments
with MACI enforcement, governance metrics comparison, and HITL integration.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timezone
import sys

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi import status as http_status
from pydantic import BaseModel, Field

# Import centralized constitutional hash
try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH  # noqa: E402
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
from src.core.shared.security.error_sanitizer import safe_error_detail

try:
    from src.core.shared.types import JSONDict  # noqa: E402
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from .amendment_model import AmendmentProposal, AmendmentStatus
from .diff_engine import ConstitutionalDiffEngine, SemanticDiff
from .hitl_integration import ConstitutionalHITLIntegration
from .storage import ConstitutionalStorageService  # type: ignore[attr-defined]
from .version_model import ConstitutionalVersion

_MODULE = sys.modules[__name__]
sys.modules.setdefault("enhanced_agent_bus.constitutional.review_api", _MODULE)
sys.modules.setdefault("packages.enhanced_agent_bus.constitutional.review_api", _MODULE)

# Import rollback engine and related components
try:
    from .degradation_detector import (
        DegradationDetector,
        DegradationThresholds,
        TimeWindow,
    )
    from .metrics_collector import GovernanceMetricsCollector
    from .rollback_engine import (
        RollbackReason,
        RollbackSagaActivities,
        rollback_amendment,
    )

    ROLLBACK_AVAILABLE = True
except ImportError:
    # Fallback for standalone usage
    ROLLBACK_AVAILABLE = False  # type: ignore[no-redef]
    RollbackReason = None  # type: ignore[no-redef, misc]
    rollback_amendment = None  # type: ignore[no-redef, misc]

# Import MACI enforcement
try:
    from ..maci_enforcement import MACIAction, MACIEnforcer, MACIRole
except ImportError:

    def _raise_missing_maci_dependency() -> RuntimeError:
        return RuntimeError(
            "MACI enforcement unavailable: cannot review constitutional amendments without "
            "maci_enforcement"
        )

    class MACIRole:  # type: ignore[no-redef]
        LEGISLATIVE = "legislative"
        JUDICIAL = "judicial"

    class MACIAction:  # type: ignore[no-redef]
        APPROVE: str = "approve"
        REJECT: str = "reject"
        VALIDATE: str = "validate"

    class MACIEnforcer:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            raise _raise_missing_maci_dependency()

        async def validate_action(self, *args, **kwargs):
            raise _raise_missing_maci_dependency()


# Import audit client
try:
    from ..audit_client import AuditClient, AuditClientConfig
except ImportError:
    # Create mock class for standalone usage
    class AuditClientConfig:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            pass

    class AuditClient:  # type: ignore[no-redef]
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        async def log_event(  # type: ignore[no-untyped-def]
            self, *args: object, **kwargs: object
        ) -> None:
            pass


logger = get_logger(__name__)
_REVIEW_API_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
)

# Create router for constitutional amendment review endpoints
router = APIRouter(
    prefix="/api/v1/constitutional",
    tags=["constitutional-amendments"],
    responses={
        404: {"description": "Amendment not found"},
        403: {"description": "MACI authorization failed"},
        500: {"description": "Internal server error"},
    },
)


def _maci_allowed(result: object) -> bool:
    """Normalize MACI validation results from typed and legacy callers."""
    if hasattr(result, "is_valid"):
        return bool(getattr(result, "is_valid"))
    if isinstance(result, dict):
        return bool(result.get("allowed", False) or result.get("is_valid", False))
    raise TypeError("Unsupported MACI validation result contract")


def _review_maci_action(action_name: str) -> object:
    """Resolve review operations onto the available MACI action surface."""
    explicit_action = getattr(MACIAction, action_name.upper(), None)
    if explicit_action is not None:
        return explicit_action
    return MACIAction.VALIDATE


@dataclass(slots=True)
class _ReviewDependencies:
    storage: ConstitutionalStorageService
    audit_client: AuditClient
    hitl: ConstitutionalHITLIntegration | None = None


@dataclass(slots=True)
class _PreparedReviewAction:
    agent_id: str
    amendment: AmendmentProposal
    dependencies: _ReviewDependencies


async def _authorize_judicial_action(
    *,
    agent_id: str,
    action_name: str,
    target_output_id: str,
    failure_detail: str,
) -> None:
    maci_enforcer = MACIEnforcer()
    maci_result = await maci_enforcer.validate_action(
        agent_id=agent_id,
        action=_review_maci_action(action_name),
        target_output_id=target_output_id,
    )
    if not _maci_allowed(maci_result):
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail=failure_detail,
        )


async def _create_review_dependencies(*, include_hitl: bool = False) -> _ReviewDependencies:
    storage = ConstitutionalStorageService()
    await storage.connect()
    audit_client = AuditClient(config=AuditClientConfig())
    hitl = ConstitutionalHITLIntegration(storage=storage) if include_hitl else None
    return _ReviewDependencies(storage=storage, audit_client=audit_client, hitl=hitl)


async def _close_review_dependencies(dependencies: _ReviewDependencies | None) -> None:
    if dependencies is None:
        return
    await dependencies.storage.disconnect()


async def _get_amendment_or_404(
    storage: ConstitutionalStorageService,
    amendment_id: str,
) -> AmendmentProposal:
    amendment = await storage.get_amendment(amendment_id)
    if not amendment:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Amendment not found: {amendment_id}",
        )
    return amendment


def _validate_amendment_review_status(
    amendment: AmendmentProposal,
    *,
    operation: str,
) -> None:
    if amendment.status not in [AmendmentStatus.UNDER_REVIEW, AmendmentStatus.PROPOSED]:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Cannot {operation} amendment in status: {amendment.status}. "
                "Must be PROPOSED or UNDER_REVIEW."
            ),
        )


async def _prepare_review_action(
    *,
    amendment_id: str,
    actor_id: str,
    header_agent_id: str | None,
    action_name: str,
    failure_detail: str,
    include_hitl: bool = False,
) -> _PreparedReviewAction:
    agent_id = header_agent_id or actor_id
    await _authorize_judicial_action(
        agent_id=agent_id,
        action_name=action_name,
        target_output_id=amendment_id,
        failure_detail=failure_detail,
    )
    dependencies = await _create_review_dependencies(include_hitl=include_hitl)
    amendment = await _get_amendment_or_404(dependencies.storage, amendment_id)
    _validate_amendment_review_status(amendment, operation=action_name)
    return _PreparedReviewAction(
        agent_id=agent_id,
        amendment=amendment,
        dependencies=dependencies,
    )

# =============================================================================
# Request/Response Models
# =============================================================================


class AmendmentListQuery(BaseModel):
    """Query parameters for listing amendments."""

    status: AmendmentStatus | None = Field(None, description="Filter by amendment status")
    proposer_agent_id: str | None = Field(None, description="Filter by proposer agent ID")
    limit: int = Field(default=50, ge=1, le=250, description="Maximum results to return")
    offset: int = Field(default=0, ge=0, description="Number of results to skip")
    order_by: str = Field(
        default="created_at", description="Field to order by (created_at, impact_score)"
    )
    order: str = Field(default="desc", description="Sort order (asc or desc)")


class AmendmentListResponse(BaseModel):
    """Response model for listing amendments."""

    amendments: list[AmendmentProposal] = Field(..., description="list of amendment proposals")
    total: int = Field(..., description="Total number of amendments matching filter")
    limit: int = Field(..., description="Limit applied to results")
    offset: int = Field(..., description="Offset applied to results")
    constitutional_hash: str = Field(
        default=CONSTITUTIONAL_HASH, description="Current constitutional hash"
    )
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class AmendmentDetailResponse(BaseModel):
    """Response model for amendment details with diff and metrics."""

    amendment: AmendmentProposal = Field(..., description="Amendment proposal details")
    diff: SemanticDiff | None = Field(None, description="Semantic diff preview of proposed changes")
    target_version: ConstitutionalVersion | None = Field(
        None, description="Target constitutional version being amended"
    )
    governance_metrics_delta: dict[str, float] = Field(
        default_factory=dict, description="Delta between before/after governance metrics"
    )
    approval_status: JSONDict = Field(
        default_factory=dict, description="Current HITL approval status and chain progress"
    )
    constitutional_hash: str = Field(
        default=CONSTITUTIONAL_HASH, description="Current constitutional hash"
    )
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class ApprovalRequest(BaseModel):
    """Request model for approving an amendment."""

    approver_agent_id: str = Field(..., description="ID of the approving agent/user")
    comments: str | None = Field(None, max_length=1000, description="Optional approval comments")
    metadata: JSONDict = Field(default_factory=dict, description="Additional approval metadata")


class RejectionRequest(BaseModel):
    """Request model for rejecting an amendment."""

    rejector_agent_id: str = Field(..., description="ID of the rejecting agent/user")
    reason: str = Field(..., min_length=10, max_length=1000, description="Reason for rejection")
    metadata: JSONDict = Field(default_factory=dict, description="Additional rejection metadata")


class ApprovalResponse(BaseModel):
    """Response model for approval/rejection actions."""

    success: bool = Field(..., description="Whether the action succeeded")
    amendment: AmendmentProposal = Field(..., description="Updated amendment proposal")
    message: str = Field(..., description="Human-readable result message")
    next_steps: list[str] = Field(default_factory=list, description="Next steps in the workflow")
    constitutional_hash: str = Field(
        default=CONSTITUTIONAL_HASH, description="Current constitutional hash"
    )
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class RollbackRequest(BaseModel):
    """Request model for manual constitutional rollback."""

    requester_agent_id: str = Field(..., description="ID of the agent requesting rollback")
    justification: str = Field(
        ..., min_length=20, max_length=2000, description="Justification for manual rollback"
    )
    metadata: JSONDict = Field(default_factory=dict, description="Additional rollback metadata")


class RollbackResponse(BaseModel):
    """Response model for rollback actions."""

    success: bool = Field(..., description="Whether the rollback succeeded")
    rollback_id: str = Field(..., description="Unique rollback operation ID")
    previous_version: str = Field(..., description="Version that was rolled back from")
    restored_version: str = Field(..., description="Version that was restored")
    diff: SemanticDiff | None = Field(None, description="Diff showing changes that were reverted")
    message: str = Field(..., description="Human-readable result message")
    justification: str = Field(..., description="Justification for the rollback")
    degradation_detected: bool = Field(
        default=False, description="Whether degradation was detected"
    )
    constitutional_hash: str = Field(
        default=CONSTITUTIONAL_HASH, description="Current constitutional hash"
    )
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


# =============================================================================
# API Endpoints
# =============================================================================


@router.get(
    "/amendments",
    response_model=AmendmentListResponse,
    summary="list constitutional amendments",
    description="list all constitutional amendment proposals with optional filtering",
)
async def list_amendments(
    status: str | None = Query(None, description="Filter by status"),
    proposer_agent_id: str | None = Query(None, description="Filter by proposer"),
    limit: int = Query(50, ge=1, le=250, description="Max results"),
    offset: int = Query(0, ge=0, description="Results offset"),
    order_by: str = Query("created_at", description="Order by field"),
    order: str = Query("desc", description="Sort order (asc/desc)"),
) -> AmendmentListResponse:
    """
    list all constitutional amendment proposals.

    This endpoint supports filtering by status and proposer, pagination,
    and sorting. All amendments are returned with basic metadata.

    Constitutional Hash: cdd01ef066bc6cf2

    Args:
        status: Optional status filter (proposed, under_review, approved, etc.)
        proposer_agent_id: Optional filter by proposer agent ID
        limit: Maximum number of results to return (1-250, default 50)
        offset: Number of results to skip for pagination (default 0)
        order_by: Field to sort by (created_at, impact_score, default created_at)
        order: Sort order - asc or desc (default desc)

    Returns:
        AmendmentListResponse with list of amendments and pagination metadata

    Raises:
        HTTPException: 500 if storage service fails
    """
    try:
        # Initialize storage service
        storage = ConstitutionalStorageService()
        await storage.connect()

        # Convert string status to enum if provided
        status_filter = None
        if status:
            try:
                status_filter = AmendmentStatus(status.lower())
            except ValueError:
                raise HTTPException(
                    status_code=http_status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid status: {status}. Must be one of: {[s.value for s in AmendmentStatus]}",  # noqa: E501
                ) from None

        # Validate order_by field
        valid_order_fields = ["created_at", "impact_score", "status"]
        if order_by not in valid_order_fields:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid order_by: {order_by}. Must be one of: {valid_order_fields}",
            )

        # Validate order direction
        if order not in ["asc", "desc"]:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid order: {order}. Must be 'asc' or 'desc'",
            )

        # Fetch amendments from storage using database-level filtering and pagination
        paginated_amendments, total = await storage.list_amendments(
            limit=limit,
            offset=offset,
            status=status_filter.value if status_filter else None,
            proposer_agent_id=proposer_agent_id,
            order_by=order_by,
            order=order,
        )

        await storage.disconnect()

        return AmendmentListResponse(
            amendments=paginated_amendments,
            total=total,
            limit=limit,
            offset=offset,
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

    except HTTPException:
        raise
    except _REVIEW_API_OPERATION_ERRORS as e:
        logger.error(f"Failed to list amendments: {e}", exc_info=True)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "list amendments"),
        ) from e


@router.get(
    "/amendments/{amendment_id}",
    response_model=AmendmentDetailResponse,
    summary="Get amendment details",
    description="Get detailed information about a constitutional amendment including diff preview and governance metrics",  # noqa: E501
)
async def get_amendment(
    amendment_id: str,
    include_diff: bool = Query(True, description="Include diff preview"),
    include_target_version: bool = Query(True, description="Include target version details"),
) -> AmendmentDetailResponse:
    """
    Get detailed information about a constitutional amendment.

    This endpoint returns the full amendment proposal along with:
    - Semantic diff preview of the proposed changes
    - Target constitutional version being amended
    - Governance metrics delta (before vs after)
    - Current HITL approval status

    Constitutional Hash: cdd01ef066bc6cf2

    Args:
        amendment_id: Unique identifier of the amendment proposal
        include_diff: Whether to include diff preview (default True)
        include_target_version: Whether to include target version details (default True)

    Returns:
        AmendmentDetailResponse with comprehensive amendment details

    Raises:
        HTTPException: 404 if amendment not found, 500 if service fails
    """
    try:
        # Initialize services
        storage = ConstitutionalStorageService()
        await storage.connect()

        # Fetch amendment proposal
        amendment = await storage.get_amendment(amendment_id)
        if not amendment:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Amendment not found: {amendment_id}",
            )

        # Fetch target version if requested
        target_version = None
        if include_target_version:
            target_version = await storage.get_version(amendment.target_version)

        # Generate diff preview if requested
        diff = None
        if include_diff and target_version:
            diff_engine = ConstitutionalDiffEngine(storage=storage)
            if isinstance(amendment.proposed_changes, dict) and amendment.proposed_changes:
                diff = await diff_engine.compute_diff_from_content(
                    from_version_id=amendment.target_version,
                    proposed_content=amendment.proposed_changes,
                )
            elif isinstance(amendment.proposed_changes, str) and amendment.proposed_changes:
                diff = await diff_engine.compute_diff(
                    from_version_id=amendment.target_version,
                    to_version_id=amendment.proposed_changes,
                )

        # Calculate governance metrics delta
        governance_metrics_delta = {}
        if amendment.governance_metrics_before and amendment.governance_metrics_after:
            for metric_name in amendment.governance_metrics_before.keys():
                before_value = amendment.governance_metrics_before.get(metric_name, 0.0)
                after_value = amendment.governance_metrics_after.get(metric_name, 0.0)
                governance_metrics_delta[metric_name] = after_value - before_value

        # Get HITL approval status
        approval_status = {
            "approval_chain": amendment.approval_chain,
            "total_approvers": len(amendment.approval_chain),
            "requires_deliberation": amendment.requires_deliberation,
        }

        await storage.disconnect()

        return AmendmentDetailResponse(
            amendment=amendment,
            diff=diff,
            target_version=target_version,
            governance_metrics_delta=governance_metrics_delta,
            approval_status=approval_status,
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

    except HTTPException:
        raise
    except _REVIEW_API_OPERATION_ERRORS as e:
        logger.error(f"Failed to get amendment {amendment_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "get amendment"),
        ) from e


@router.post(
    "/amendments/{amendment_id}/approve",
    response_model=ApprovalResponse,
    summary="Approve amendment",
    description="Approve a constitutional amendment (requires JUDICIAL MACI role)",
)
async def approve_amendment(
    amendment_id: str,
    approval_request: ApprovalRequest,
    x_agent_id: str | None = Header(None, description="Agent ID for MACI validation"),
) -> ApprovalResponse:
    """
    Approve a constitutional amendment.

    This endpoint approves an amendment proposal and advances it through
    the HITL approval workflow. MACI enforcement ensures only agents with
    the JUDICIAL role can approve amendments.

    Constitutional Hash: cdd01ef066bc6cf2

    Flow:
    1. Validate MACI permissions (JUDICIAL role required)
    2. Load amendment proposal
    3. Validate amendment is in UNDER_REVIEW status
    4. Record approval in approval chain
    5. Process approval through HITL service
    6. Update amendment status if all approvals received
    7. Audit log the approval action

    Args:
        amendment_id: Unique identifier of the amendment to approve
        approval_request: Approval request with approver ID and comments
        x_agent_id: Agent ID from request header for MACI validation

    Returns:
        ApprovalResponse with updated amendment and next steps

    Raises:
        HTTPException: 403 if MACI validation fails, 404 if amendment not found,
                      400 if amendment in wrong status, 500 if service fails
    """
    dependencies: _ReviewDependencies | None = None
    try:
        prepared = await _prepare_review_action(
            amendment_id=amendment_id,
            actor_id=approval_request.approver_agent_id,
            header_agent_id=x_agent_id,
            action_name="approve",
            failure_detail=(
                "MACI authorization failed: Only JUDICIAL role can approve amendments. "
                f"Agent {(x_agent_id or approval_request.approver_agent_id)} lacks required permissions."
            ),
            include_hitl=True,
        )
        dependencies = prepared.dependencies
        amendment = prepared.amendment

        # Record approval in approval chain
        approval_record = {
            "approver_id": approval_request.approver_agent_id,
            "action": "approve",
            "comments": approval_request.comments,
            "timestamp": datetime.now(UTC).isoformat(),
            "metadata": approval_request.metadata,
        }
        amendment.approval_chain.append(approval_record)

        # Determine required approvals from HITL chain config based on impact score
        chain_config = dependencies.hitl._determine_approval_chain(amendment)
        required_approvals = chain_config.required_approvals
        approvals_received = len(amendment.approval_chain)
        approval_status: JSONDict = {
            "status": "approved" if approvals_received >= required_approvals else "pending",
            "required_approvals": required_approvals,
            "approvals_received": approvals_received,
        }

        # Update amendment status based on HITL approval status
        next_steps = []
        if approval_status.get("status") == "approved":
            amendment.status = AmendmentStatus.APPROVED
            amendment.reviewed_at = datetime.now(UTC)
            next_steps.append("Amendment fully approved - ready for activation")
            next_steps.append(
                "Use POST /api/v1/constitutional/amendments/{id}/activate to activate"
            )
        elif approval_status.get("status") == "pending":
            amendment.status = AmendmentStatus.UNDER_REVIEW
            required = approval_status.get("required_approvals", 0)
            received = approval_status.get("approvals_received", 0)
            next_steps.append(
                f"Approval recorded - waiting for additional approvals ({received}/{required})"
            )

        # Save updated amendment
        await dependencies.storage.save_amendment(amendment)

        # Audit log the approval
        await dependencies.audit_client.log_event(  # type: ignore[attr-defined]
            event_type="constitutional_amendment_approved",
            agent_id=approval_request.approver_agent_id,
            data={
                "amendment_id": amendment_id,
                "approver_id": approval_request.approver_agent_id,
                "comments": approval_request.comments,
                "approval_status": approval_status,
                "constitutional_hash": CONSTITUTIONAL_HASH,
            },
        )

        return ApprovalResponse(
            success=True,
            amendment=amendment,
            message=f"Amendment {amendment_id} approved by {approval_request.approver_agent_id}",
            next_steps=next_steps,
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

    except HTTPException:
        raise
    except _REVIEW_API_OPERATION_ERRORS as e:
        logger.error(f"Failed to approve amendment {amendment_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "approve amendment"),
        ) from e
    finally:
        await _close_review_dependencies(dependencies)


@router.post(
    "/amendments/{amendment_id}/reject",
    response_model=ApprovalResponse,
    summary="Reject amendment",
    description="Reject a constitutional amendment (requires JUDICIAL MACI role)",
)
async def reject_amendment(
    amendment_id: str,
    rejection_request: RejectionRequest,
    x_agent_id: str | None = Header(None, description="Agent ID for MACI validation"),
) -> ApprovalResponse:
    """
    Reject a constitutional amendment.

    This endpoint rejects an amendment proposal and terminates the
    approval workflow. MACI enforcement ensures only agents with
    the JUDICIAL role can reject amendments.

    Constitutional Hash: cdd01ef066bc6cf2

    Flow:
    1. Validate MACI permissions (JUDICIAL role required)
    2. Load amendment proposal
    3. Validate amendment is in UNDER_REVIEW or PROPOSED status
    4. Record rejection in approval chain
    5. Update amendment status to REJECTED
    6. Process rejection through HITL service
    7. Audit log the rejection action

    Args:
        amendment_id: Unique identifier of the amendment to reject
        rejection_request: Rejection request with rejector ID and reason
        x_agent_id: Agent ID from request header for MACI validation

    Returns:
        ApprovalResponse with updated amendment and next steps

    Raises:
        HTTPException: 403 if MACI validation fails, 404 if amendment not found,
                      400 if amendment in wrong status, 500 if service fails
    """
    dependencies: _ReviewDependencies | None = None
    try:
        prepared = await _prepare_review_action(
            amendment_id=amendment_id,
            actor_id=rejection_request.rejector_agent_id,
            header_agent_id=x_agent_id,
            action_name="reject",
            failure_detail=(
                "MACI authorization failed: Only JUDICIAL role can reject amendments. "
                f"Agent {(x_agent_id or rejection_request.rejector_agent_id)} lacks required permissions."
            ),
            include_hitl=False,
        )
        dependencies = prepared.dependencies
        amendment = prepared.amendment

        # Record rejection in approval chain
        rejection_record = {
            "rejector_id": rejection_request.rejector_agent_id,
            "action": "reject",
            "reason": rejection_request.reason,
            "timestamp": datetime.now(UTC).isoformat(),
            "metadata": rejection_request.metadata,
        }
        amendment.approval_chain.append(rejection_record)

        # Update amendment status
        amendment.status = AmendmentStatus.REJECTED
        amendment.rejection_reason = rejection_request.reason
        amendment.reviewed_at = datetime.now(UTC)

        # Note: Rejection is handled directly without HITL polling
        # The amendment status update above handles the rejection state

        # Save updated amendment
        await dependencies.storage.save_amendment(amendment)

        # Audit log the rejection
        await dependencies.audit_client.log_event(  # type: ignore[attr-defined]
            event_type="constitutional_amendment_rejected",
            agent_id=rejection_request.rejector_agent_id,
            data={
                "amendment_id": amendment_id,
                "rejector_id": rejection_request.rejector_agent_id,
                "reason": rejection_request.reason,
                "constitutional_hash": CONSTITUTIONAL_HASH,
            },
        )

        next_steps = [
            "Amendment rejected - proposal terminated",
            "Proposer may submit a new amended proposal addressing the rejection reason",
        ]

        return ApprovalResponse(
            success=True,
            amendment=amendment,
            message=f"Amendment {amendment_id} rejected by {rejection_request.rejector_agent_id}: {rejection_request.reason}",  # noqa: E501
            next_steps=next_steps,
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

    except HTTPException:
        raise
    except _REVIEW_API_OPERATION_ERRORS as e:
        logger.error(f"Failed to reject amendment {amendment_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "reject amendment"),
        ) from e
    finally:
        await _close_review_dependencies(dependencies)


@router.post(
    "/versions/{version_id}/rollback",
    response_model=RollbackResponse,
    summary="Manual constitutional rollback",
    description="Manually rollback to a specific constitutional version (requires JUDICIAL MACI role)",  # noqa: E501
)
async def rollback_to_version(
    version_id: str,
    rollback_request: RollbackRequest,
    x_agent_id: str | None = Header(None, description="Agent ID for MACI validation"),
) -> RollbackResponse:
    """
    Manually rollback to a specific constitutional version.

    This endpoint allows authorized agents (JUDICIAL role) to manually
    rollback the constitutional version to a previous version. This is
    useful for emergency situations or when automatic rollback is not
    triggered but governance issues are detected.

    Constitutional Hash: cdd01ef066bc6cf2

    Flow:
    1. Validate MACI permissions (JUDICIAL role required)
    2. Load target version and current active version
    3. Compute diff showing changes that will be reverted
    4. Execute rollback saga workflow
    5. Audit log the manual rollback action
    6. Return rollback details with diff preview

    Args:
        version_id: ID of the version to rollback to
        rollback_request: Rollback request with requester ID and justification
        x_agent_id: Agent ID from request header for MACI validation

    Returns:
        RollbackResponse with rollback details and diff preview

    Raises:
        HTTPException: 403 if MACI validation fails, 404 if version not found,
                      400 if rollback prerequisites not met, 500 if service fails
    """
    if not ROLLBACK_AVAILABLE:
        raise HTTPException(
            status_code=http_status.HTTP_501_NOT_IMPLEMENTED,
            detail="Rollback functionality not available. Missing required dependencies.",
        )

    dependencies: _ReviewDependencies | None = None
    try:
        agent_id = x_agent_id or rollback_request.requester_agent_id
        await _authorize_judicial_action(
            agent_id=agent_id,
            action_name="rollback",
            target_output_id=version_id,
            failure_detail=(
                "MACI authorization failed: Only JUDICIAL role can trigger manual rollback. "
                f"Agent {agent_id} lacks required permissions."
            ),
        )

        # Validate justification length
        if len(rollback_request.justification) < 20:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="Justification must be at least 20 characters",
            )

        dependencies = await _create_review_dependencies()
        storage = dependencies.storage

        # Fetch target version (version to rollback to)
        target_version = await storage.get_version(version_id)
        if not target_version:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Target version not found: {version_id}",
            )

        # Fetch current active version
        current_version = await storage.get_active_version()
        if not current_version:
            raise HTTPException(
                status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="No active constitutional version found",
            )

        # Validate we're not rolling back to the current version
        if current_version.version_id == target_version.version_id:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=f"Target version {version_id} is already the active version",
            )

        # Compute diff showing what will be reverted
        diff_engine = ConstitutionalDiffEngine(storage=storage)
        revert_diff = await diff_engine.compute_diff(
            from_version_id=current_version.version_id, to_version_id=target_version.version_id
        )

        logger.info(
            f"[{CONSTITUTIONAL_HASH}] Manual rollback initiated by {agent_id}: "
            f"{current_version.version} -> {target_version.version}"
        )

        # Initialize metrics collector and degradation detector for rollback saga
        metrics_collector = GovernanceMetricsCollector()
        await metrics_collector.connect()

        degradation_detector = DegradationDetector(
            metrics_collector=metrics_collector,
            thresholds=DegradationThresholds(
                violations_rate_threshold=0.01,
                latency_p99_threshold_ms=2.0,
                latency_p99_percent_threshold=0.5,
                deliberation_success_rate_threshold=0.05,
                maci_violations_threshold=1,
                error_rate_threshold=0.1,
                health_score_threshold=0.15,
                min_sample_size=30,
                significance_level=0.05,
            ),
        )

        # Execute rollback saga
        # Note: For manual rollback, we override the current version's predecessor
        # to point to the target version, then execute rollback
        from uuid import uuid4

        rollback_id = f"manual-rollback-{str(uuid4())[:8]}"

        try:
            # Temporarily update current version's predecessor to enable rollback
            original_predecessor = current_version.predecessor_version
            current_version.predecessor_version = target_version.version_id
            await storage.update_version(current_version)

            # Execute rollback using rollback_amendment function
            saga_result = await rollback_amendment(
                current_version_id=current_version.version_id,
                storage=storage,
                metrics_collector=metrics_collector,
                degradation_detector=degradation_detector,
                rollback_reason=RollbackReason.MANUAL_REQUEST,
                amendment_id=None,  # Manual rollback, no specific amendment
                time_window=TimeWindow.ONE_HOUR,
            )

            # Check if rollback succeeded
            rollback_succeeded = (
                saga_result.status.value == "completed" if hasattr(saga_result, "status") else False
            )

            if not rollback_succeeded:
                # Restore original predecessor on failure
                current_version.predecessor_version = original_predecessor
                await storage.update_version(current_version)

                error_msg = f"Rollback saga failed: {saga_result.errors if hasattr(saga_result, 'errors') else 'Unknown error'}"  # noqa: E501
                logger.error(f"[{CONSTITUTIONAL_HASH}] {error_msg}")
                raise HTTPException(
                    status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail=error_msg
                )

        finally:
            await metrics_collector.disconnect()

        # Audit log the manual rollback
        await dependencies.audit_client.log_event(  # type: ignore[attr-defined]
            event_type="constitutional_manual_rollback",
            agent_id=rollback_request.requester_agent_id,
            data={
                "rollback_id": rollback_id,
                "requester_id": rollback_request.requester_agent_id,
                "justification": rollback_request.justification,
                "previous_version": current_version.version,
                "previous_version_id": current_version.version_id,
                "restored_version": target_version.version,
                "restored_version_id": target_version.version_id,
                "revert_diff": revert_diff.model_dump() if revert_diff else None,
                "constitutional_hash": CONSTITUTIONAL_HASH,
                "metadata": rollback_request.metadata,
            },
        )

        logger.warning(
            f"CONSTITUTIONAL_MANUAL_ROLLBACK: {current_version.version} -> {target_version.version} "  # noqa: E501
            f"by {agent_id} (justification: {rollback_request.justification[:100]}...)"
        )

        return RollbackResponse(
            success=True,
            rollback_id=rollback_id,
            previous_version=current_version.version,
            restored_version=target_version.version,
            diff=revert_diff,
            message=f"Successfully rolled back from {current_version.version} to {target_version.version}",  # noqa: E501
            justification=rollback_request.justification,
            degradation_detected=False,  # Manual rollback, not triggered by degradation
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

    except HTTPException:
        raise
    except _REVIEW_API_OPERATION_ERRORS as e:
        logger.error(f"Failed to execute manual rollback to {version_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "execute rollback"),
        ) from e
    finally:
        await _close_review_dependencies(dependencies)


# Health check for constitutional review API
@router.get(
    "/health", summary="Health check", description="Health check for constitutional review API"
)
async def health_check() -> JSONDict:
    """
    Health check endpoint for constitutional review API.

    Returns:
        Health status with service information
    """
    return {
        "status": "healthy",
        "service": "constitutional-review-api",
        "constitutional_hash": CONSTITUTIONAL_HASH,
        "timestamp": datetime.now(UTC).isoformat(),
    }
