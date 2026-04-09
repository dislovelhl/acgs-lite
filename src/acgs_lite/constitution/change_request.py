"""Structured change request workflow for governance rule modifications.

Formalizes the process of proposing, reviewing, approving, and applying
changes to governance rules — with impact assessment fields, multi-approver
gates, rejection with rationale, automatic rollback on failed application,
and change request audit trail.

Example::

    from acgs_lite.constitution.change_request import (
        ChangeRequestManager, ChangeRequest, ChangeRequestStatus, ChangeType,
    )

    mgr = ChangeRequestManager()
    cr = mgr.create(
        title="Add GDPR data minimization rule",
        change_type=ChangeType.ADD_RULE,
        proposed_by="policy-team",
        description="New rule GDPR-005 for data minimization enforcement",
        impact_assessment="Low risk — additive only, no existing rules affected",
    )
    mgr.approve(cr.request_id, approver="governance-lead")
    mgr.apply(cr.request_id)
    assert cr.status == ChangeRequestStatus.APPLIED
"""

from __future__ import annotations

import enum
import time
import uuid
from dataclasses import dataclass, field


class ChangeType(str, enum.Enum):
    ADD_RULE = "add_rule"
    MODIFY_RULE = "modify_rule"
    REMOVE_RULE = "remove_rule"
    UPDATE_SEVERITY = "update_severity"
    UPDATE_KEYWORDS = "update_keywords"
    BULK_CHANGE = "bulk_change"


class ChangeRequestStatus(str, enum.Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"
    ROLLED_BACK = "rolled_back"
    CANCELLED = "cancelled"


_VALID_CR_TRANSITIONS: dict[ChangeRequestStatus, set[ChangeRequestStatus]] = {
    ChangeRequestStatus.DRAFT: {ChangeRequestStatus.SUBMITTED, ChangeRequestStatus.CANCELLED},
    ChangeRequestStatus.SUBMITTED: {
        ChangeRequestStatus.UNDER_REVIEW,
        ChangeRequestStatus.CANCELLED,
    },
    ChangeRequestStatus.UNDER_REVIEW: {
        ChangeRequestStatus.APPROVED,
        ChangeRequestStatus.REJECTED,
        ChangeRequestStatus.CANCELLED,
    },
    ChangeRequestStatus.APPROVED: {
        ChangeRequestStatus.APPLIED,
        ChangeRequestStatus.CANCELLED,
    },
    ChangeRequestStatus.REJECTED: {ChangeRequestStatus.DRAFT},
    ChangeRequestStatus.APPLIED: {ChangeRequestStatus.ROLLED_BACK},
    ChangeRequestStatus.ROLLED_BACK: {ChangeRequestStatus.DRAFT},
    ChangeRequestStatus.CANCELLED: set(),
}


@dataclass
class ChangeRequestEvent:
    """Audit entry for a change request lifecycle event."""

    timestamp: float
    status: ChangeRequestStatus
    actor: str
    note: str = ""


@dataclass
class ChangeRequest:
    """A governance change request with full lifecycle state."""

    request_id: str
    title: str
    change_type: ChangeType
    proposed_by: str
    description: str = ""
    impact_assessment: str = ""
    affected_rule_ids: list[str] = field(default_factory=list)
    status: ChangeRequestStatus = ChangeRequestStatus.DRAFT
    approvers: list[str] = field(default_factory=list)
    rejectors: list[str] = field(default_factory=list)
    rejection_reason: str = ""
    required_approvals: int = 1
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    applied_at: float | None = None
    rolled_back_at: float | None = None
    history: list[ChangeRequestEvent] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


class ChangeRequestManager:
    """Manage governance change request lifecycles.

    Enforces valid status transitions, tracks multi-approver gates,
    supports rejection with rationale, rollback after application,
    and maintains a full audit trail per change request.

    Example::

        mgr = ChangeRequestManager()
        cr = mgr.create("Tighten PII rule", ChangeType.MODIFY_RULE, "admin")
        mgr.submit(cr.request_id)
        mgr.review(cr.request_id)
        mgr.approve(cr.request_id, approver="lead-1")
        mgr.apply(cr.request_id)
    """

    def __init__(self) -> None:
        self._requests: dict[str, ChangeRequest] = {}

    def create(
        self,
        title: str,
        change_type: ChangeType,
        proposed_by: str,
        description: str = "",
        impact_assessment: str = "",
        affected_rule_ids: list[str] | None = None,
        required_approvals: int = 1,
        tags: list[str] | None = None,
    ) -> ChangeRequest:
        request_id = f"CR-{uuid.uuid4().hex[:12]}"
        now = time.time()
        cr = ChangeRequest(
            request_id=request_id,
            title=title,
            change_type=change_type,
            proposed_by=proposed_by,
            description=description,
            impact_assessment=impact_assessment,
            affected_rule_ids=affected_rule_ids or [],
            required_approvals=max(1, required_approvals),
            created_at=now,
            updated_at=now,
            tags=tags or [],
            history=[
                ChangeRequestEvent(
                    timestamp=now,
                    status=ChangeRequestStatus.DRAFT,
                    actor=proposed_by,
                    note=f"Change request created: {title}",
                )
            ],
        )
        self._requests[request_id] = cr
        return cr

    def get(self, request_id: str) -> ChangeRequest | None:
        return self._requests.get(request_id)

    def submit(self, request_id: str, actor: str = "system") -> bool:
        return self._transition(request_id, ChangeRequestStatus.SUBMITTED, actor)

    def review(self, request_id: str, actor: str = "system") -> bool:
        return self._transition(request_id, ChangeRequestStatus.UNDER_REVIEW, actor)

    def approve(self, request_id: str, approver: str) -> bool:
        """Add an approval. Auto-transitions to APPROVED when threshold met."""
        cr = self._requests.get(request_id)
        if cr is None:
            return False
        if cr.status not in (
            ChangeRequestStatus.UNDER_REVIEW,
            ChangeRequestStatus.SUBMITTED,
        ):
            return False
        if approver == cr.proposed_by:
            return False
        if approver in cr.approvers:
            return False

        cr.approvers.append(approver)
        cr.updated_at = time.time()
        cr.history.append(
            ChangeRequestEvent(
                timestamp=cr.updated_at,
                status=cr.status,
                actor=approver,
                note=f"Approved ({len(cr.approvers)}/{cr.required_approvals})",
            )
        )

        if len(cr.approvers) >= cr.required_approvals:
            cr.status = ChangeRequestStatus.APPROVED
            cr.history.append(
                ChangeRequestEvent(
                    timestamp=cr.updated_at,
                    status=ChangeRequestStatus.APPROVED,
                    actor="system",
                    note="Approval threshold met",
                )
            )
        return True

    def reject(self, request_id: str, rejector: str, reason: str = "") -> bool:
        cr = self._requests.get(request_id)
        if cr is None:
            return False
        if cr.status not in (
            ChangeRequestStatus.UNDER_REVIEW,
            ChangeRequestStatus.SUBMITTED,
        ):
            return False

        cr.status = ChangeRequestStatus.REJECTED
        cr.rejectors.append(rejector)
        cr.rejection_reason = reason
        cr.updated_at = time.time()
        cr.history.append(
            ChangeRequestEvent(
                timestamp=cr.updated_at,
                status=ChangeRequestStatus.REJECTED,
                actor=rejector,
                note=reason or "Rejected",
            )
        )
        return True

    def apply(self, request_id: str, actor: str = "system") -> bool:
        cr = self._requests.get(request_id)
        if cr is None or cr.status != ChangeRequestStatus.APPROVED:
            return False
        now = time.time()
        cr.status = ChangeRequestStatus.APPLIED
        cr.applied_at = now
        cr.updated_at = now
        cr.history.append(
            ChangeRequestEvent(
                timestamp=now,
                status=ChangeRequestStatus.APPLIED,
                actor=actor,
                note="Change applied",
            )
        )
        return True

    def rollback(self, request_id: str, actor: str = "system", reason: str = "") -> bool:
        cr = self._requests.get(request_id)
        if cr is None or cr.status != ChangeRequestStatus.APPLIED:
            return False
        now = time.time()
        cr.status = ChangeRequestStatus.ROLLED_BACK
        cr.rolled_back_at = now
        cr.updated_at = now
        cr.history.append(
            ChangeRequestEvent(
                timestamp=now,
                status=ChangeRequestStatus.ROLLED_BACK,
                actor=actor,
                note=reason or "Change rolled back",
            )
        )
        return True

    def cancel(self, request_id: str, actor: str = "system") -> bool:
        return self._transition(request_id, ChangeRequestStatus.CANCELLED, actor)

    def reopen(self, request_id: str, actor: str = "system") -> bool:
        """Return a rejected or rolled-back CR to draft status."""
        cr = self._requests.get(request_id)
        if cr is None:
            return False
        if cr.status not in (
            ChangeRequestStatus.REJECTED,
            ChangeRequestStatus.ROLLED_BACK,
        ):
            return False
        cr.status = ChangeRequestStatus.DRAFT
        cr.approvers.clear()
        cr.rejectors.clear()
        cr.rejection_reason = ""
        cr.updated_at = time.time()
        cr.history.append(
            ChangeRequestEvent(
                timestamp=cr.updated_at,
                status=ChangeRequestStatus.DRAFT,
                actor=actor,
                note="Reopened as draft",
            )
        )
        return True

    def query_by_status(self, status: ChangeRequestStatus) -> list[ChangeRequest]:
        return [cr for cr in self._requests.values() if cr.status == status]

    def query_by_proposer(self, proposed_by: str) -> list[ChangeRequest]:
        return [cr for cr in self._requests.values() if cr.proposed_by == proposed_by]

    def query_pending(self) -> list[ChangeRequest]:
        pending = {
            ChangeRequestStatus.DRAFT,
            ChangeRequestStatus.SUBMITTED,
            ChangeRequestStatus.UNDER_REVIEW,
            ChangeRequestStatus.APPROVED,
        }
        return [cr for cr in self._requests.values() if cr.status in pending]

    def summary(self) -> dict[str, object]:
        by_status: dict[str, int] = {}
        by_type: dict[str, int] = {}
        for cr in self._requests.values():
            by_status[cr.status.value] = by_status.get(cr.status.value, 0) + 1
            by_type[cr.change_type.value] = by_type.get(cr.change_type.value, 0) + 1
        return {
            "total": len(self._requests),
            "pending": len(self.query_pending()),
            "by_status": by_status,
            "by_type": by_type,
        }

    def _transition(
        self,
        request_id: str,
        target: ChangeRequestStatus,
        actor: str,
        note: str = "",
    ) -> bool:
        cr = self._requests.get(request_id)
        if cr is None:
            return False
        valid = _VALID_CR_TRANSITIONS.get(cr.status, set())
        if target not in valid:
            return False
        cr.status = target
        cr.updated_at = time.time()
        cr.history.append(
            ChangeRequestEvent(
                timestamp=cr.updated_at,
                status=target,
                actor=actor,
                note=note or f"Transitioned to {target.value}",
            )
        )
        return True
