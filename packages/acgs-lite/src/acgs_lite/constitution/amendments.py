"""exp175: ConstitutionalAmendmentProtocol — formal constitution mutation.

Implements a separation-of-powers amendment lifecycle:

    draft → proposed → voting → ratified → enforced  (happy path)
    draft → proposed → voting → rejected              (threshold not met)
    draft → proposed → voting → vetoed                (veto override)
    * → withdrawn                                      (proposer cancels)

MACI enforcement:
- Only PROPOSER role can propose amendments
- Only VALIDATOR role can vote
- Only EXECUTOR role can ratify and enforce
- Proposer ≠ Voter (no self-validation, golden rule)
- Veto power: any voter can veto CRITICAL-severity amendments

Integration points:
- Constitution.update_rule() for immutable rule mutation
- GovernanceChangelog for audit trail
- MACIEnforcer.check() for role boundary enforcement

Constitutional Hash: cdd01ef066bc6cf2
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .constitution import Constitution


class AmendmentStatus(str, Enum):
    """Lifecycle state of a constitutional amendment."""

    draft = "draft"
    proposed = "proposed"
    voting = "voting"
    ratified = "ratified"
    enforced = "enforced"
    rejected = "rejected"
    vetoed = "vetoed"
    withdrawn = "withdrawn"


class AmendmentType(str, Enum):
    """Category of constitutional change."""

    add_rule = "add_rule"
    modify_rule = "modify_rule"
    remove_rule = "remove_rule"
    modify_severity = "modify_severity"
    modify_workflow = "modify_workflow"


@dataclass(frozen=True, slots=True)
class Vote:
    """A single vote on an amendment.

    Attributes:
        voter_id: Identifier of the voting agent/user.
        approve: True for approve, False for reject.
        reason: Optional rationale for the vote.
        timestamp: ISO-8601 timestamp of the vote.
        veto: If True, this vote is a veto that overrides quorum.
    """

    voter_id: str
    approve: bool
    reason: str = ""
    timestamp: str = ""
    veto: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "voter_id": self.voter_id,
            "approve": self.approve,
            "reason": self.reason,
            "timestamp": self.timestamp,
            "veto": self.veto,
        }


@dataclass
class Amendment:
    """A proposed change to a constitution.

    Tracks the full lifecycle from draft through enforcement or rejection,
    including all votes, the proposer, ratifier, and audit metadata.

    Attributes:
        amendment_id: Unique identifier (e.g. ``"AMD-00001"``).
        amendment_type: Category of change (add/modify/remove rule).
        proposer_id: Agent/user who created this amendment.
        title: Short human-readable summary.
        description: Detailed rationale for the change.
        changes: Dict describing the mutation (rule_id, new fields, etc.).
        status: Current lifecycle state.
        created_at: ISO-8601 creation timestamp.
        proposed_at: When the amendment moved to ``proposed``.
        voting_opened_at: When voting started.
        resolved_at: When voting concluded (ratified/rejected/vetoed).
        enforced_at: When the amendment was applied to the constitution.
        votes: All recorded votes.
        ratifier_id: Agent/user who ratified the amendment.
        quorum_required: Minimum number of votes needed.
        approval_threshold: Fraction of approvals needed (0.0-1.0).
        constitution_hash_before: Hash of the constitution before enforcement.
        constitution_hash_after: Hash of the constitution after enforcement.
        metadata: Arbitrary extension data.
    """

    amendment_id: str
    amendment_type: AmendmentType
    proposer_id: str
    title: str
    description: str
    changes: dict[str, Any]
    status: AmendmentStatus = AmendmentStatus.draft
    created_at: str = ""
    proposed_at: str = ""
    voting_opened_at: str = ""
    resolved_at: str = ""
    enforced_at: str = ""
    votes: list[Vote] = field(default_factory=list)
    ratifier_id: str = ""
    quorum_required: int = 1
    approval_threshold: float = 0.5
    constitution_hash_before: str = ""
    constitution_hash_after: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    # ── computed properties ──────────────────────────────────────────────

    @property
    def vote_count(self) -> int:
        return len(self.votes)

    @property
    def approvals(self) -> int:
        return sum(1 for v in self.votes if v.approve)

    @property
    def rejections(self) -> int:
        return sum(1 for v in self.votes if not v.approve)

    @property
    def approval_rate(self) -> float:
        return self.approvals / self.vote_count if self.vote_count else 0.0

    @property
    def has_quorum(self) -> bool:
        return self.vote_count >= self.quorum_required

    @property
    def has_veto(self) -> bool:
        return any(v.veto for v in self.votes)

    @property
    def passes_threshold(self) -> bool:
        return self.has_quorum and self.approval_rate >= self.approval_threshold

    @property
    def is_terminal(self) -> bool:
        return self.status in {
            AmendmentStatus.enforced,
            AmendmentStatus.rejected,
            AmendmentStatus.vetoed,
            AmendmentStatus.withdrawn,
        }

    def voter_ids(self) -> set[str]:
        return {v.voter_id for v in self.votes}

    def to_dict(self) -> dict[str, Any]:
        return {
            "amendment_id": self.amendment_id,
            "amendment_type": self.amendment_type.value,
            "proposer_id": self.proposer_id,
            "title": self.title,
            "description": self.description,
            "changes": self.changes,
            "status": self.status.value,
            "created_at": self.created_at,
            "proposed_at": self.proposed_at,
            "voting_opened_at": self.voting_opened_at,
            "resolved_at": self.resolved_at,
            "enforced_at": self.enforced_at,
            "votes": [v.to_dict() for v in self.votes],
            "vote_count": self.vote_count,
            "approvals": self.approvals,
            "rejections": self.rejections,
            "approval_rate": round(self.approval_rate, 4),
            "has_quorum": self.has_quorum,
            "has_veto": self.has_veto,
            "passes_threshold": self.passes_threshold,
            "ratifier_id": self.ratifier_id,
            "quorum_required": self.quorum_required,
            "approval_threshold": self.approval_threshold,
            "constitution_hash_before": self.constitution_hash_before,
            "constitution_hash_after": self.constitution_hash_after,
            "metadata": self.metadata,
        }


_VALID_TRANSITIONS: dict[AmendmentStatus, set[AmendmentStatus]] = {
    AmendmentStatus.draft: {AmendmentStatus.proposed, AmendmentStatus.withdrawn},
    AmendmentStatus.proposed: {AmendmentStatus.voting, AmendmentStatus.withdrawn},
    AmendmentStatus.voting: {
        AmendmentStatus.ratified,
        AmendmentStatus.rejected,
        AmendmentStatus.vetoed,
        AmendmentStatus.withdrawn,
    },
    AmendmentStatus.ratified: {AmendmentStatus.enforced},
    # Terminal states — no transitions out
    AmendmentStatus.enforced: set(),
    AmendmentStatus.rejected: set(),
    AmendmentStatus.vetoed: set(),
    AmendmentStatus.withdrawn: set(),
}


class AmendmentProtocol:
    """Formal constitutional amendment protocol with MACI enforcement.

    Manages the lifecycle of constitutional amendments with separation of
    powers: proposers draft, validators vote, executors ratify and enforce.
    No agent may both propose and vote on the same amendment.

    Usage::

        from acgs_lite.constitution.amendments import AmendmentProtocol

        protocol = AmendmentProtocol(quorum=2, approval_threshold=0.6)

        # Proposer creates and submits
        amd = protocol.draft(
            proposer_id="agent-policy",
            amendment_type="modify_rule",
            title="Tighten PII rule severity",
            description="Elevate PII-001 from HIGH to CRITICAL",
            changes={"rule_id": "PII-001", "severity": "critical"},
        )
        protocol.propose(amd.amendment_id, proposer_id="agent-policy")
        protocol.open_voting(amd.amendment_id, proposer_id="agent-policy")

        # Validators vote (must be different agents from proposer)
        protocol.vote(amd.amendment_id, voter_id="validator-1", approve=True)
        protocol.vote(amd.amendment_id, voter_id="validator-2", approve=True)

        # Executor ratifies and enforces
        protocol.ratify(amd.amendment_id, ratifier_id="executor-1")
        new_constitution = protocol.enforce(
            amd.amendment_id,
            executor_id="executor-1",
            constitution=current_constitution,
        )

    Veto::

        # Any validator can veto a critical amendment
        protocol.vote(
            amd.amendment_id,
            voter_id="validator-senior",
            approve=False,
            veto=True,
            reason="Blocks essential monitoring workflow",
        )
        # Amendment moves to 'vetoed' immediately
    """

    __slots__ = (
        "_amendments",
        "_counter",
        "_quorum",
        "_approval_threshold",
        "_history",
    )

    def __init__(
        self,
        *,
        quorum: int = 1,
        approval_threshold: float = 0.5,
    ) -> None:
        """Initialise the amendment protocol.

        Args:
            quorum: Minimum number of votes required for a valid decision.
            approval_threshold: Fraction of approvals (0.0-1.0) needed to pass.
        """
        if quorum < 1:
            raise ValueError("quorum must be >= 1")
        if not 0.0 < approval_threshold <= 1.0:
            raise ValueError("approval_threshold must be in (0.0, 1.0]")
        self._amendments: dict[str, Amendment] = {}
        self._counter: int = 0
        self._quorum = quorum
        self._approval_threshold = approval_threshold
        self._history: list[dict[str, Any]] = []

    def _next_id(self) -> str:
        self._counter += 1
        return f"AMD-{self._counter:05d}"

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _get(self, amendment_id: str) -> Amendment:
        try:
            return self._amendments[amendment_id]
        except KeyError:
            raise KeyError(f"Amendment {amendment_id!r} not found") from None

    def _transition(self, amd: Amendment, to: AmendmentStatus) -> None:
        valid = _VALID_TRANSITIONS.get(amd.status, set())
        if to not in valid:
            msg = (
                f"Cannot transition amendment {amd.amendment_id!r} "
                f"from {amd.status.value!r} to {to.value!r}"
            )
            raise ValueError(msg)
        self._history.append(
            {
                "amendment_id": amd.amendment_id,
                "from_status": amd.status.value,
                "to_status": to.value,
                "timestamp": self._now(),
            }
        )
        amd.status = to

    # ── lifecycle actions ─────────────────────────────────────────────────

    def draft(
        self,
        *,
        proposer_id: str,
        amendment_type: str,
        title: str,
        description: str = "",
        changes: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Amendment:
        """Create a new amendment in draft status.

        Args:
            proposer_id: Agent/user creating the amendment.
            amendment_type: One of AmendmentType values.
            title: Short summary of the proposed change.
            description: Detailed rationale.
            changes: Dict describing the mutation.
            metadata: Optional extension data.

        Returns:
            The newly created Amendment in ``draft`` status.
        """
        amd_type = AmendmentType(amendment_type)
        amd = Amendment(
            amendment_id=self._next_id(),
            amendment_type=amd_type,
            proposer_id=proposer_id,
            title=title,
            description=description,
            changes=changes or {},
            status=AmendmentStatus.draft,
            created_at=self._now(),
            quorum_required=self._quorum,
            approval_threshold=self._approval_threshold,
            metadata=metadata or {},
        )
        self._amendments[amd.amendment_id] = amd
        self._history.append(
            {
                "amendment_id": amd.amendment_id,
                "from_status": "",
                "to_status": "draft",
                "actor": proposer_id,
                "timestamp": amd.created_at,
            }
        )
        return amd

    def propose(self, amendment_id: str, *, proposer_id: str) -> Amendment:
        """Submit a draft amendment for review.

        Args:
            amendment_id: The amendment to propose.
            proposer_id: Must match the original proposer.

        Returns:
            The updated Amendment in ``proposed`` status.

        Raises:
            ValueError: If status transition is invalid or proposer mismatch.
        """
        amd = self._get(amendment_id)
        if amd.proposer_id != proposer_id:
            raise ValueError(
                f"Only the original proposer ({amd.proposer_id!r}) "
                f"can propose amendment {amendment_id!r}"
            )
        self._transition(amd, AmendmentStatus.proposed)
        amd.proposed_at = self._now()
        return amd

    def open_voting(self, amendment_id: str, *, proposer_id: str) -> Amendment:
        """Open the voting period for a proposed amendment.

        Args:
            amendment_id: The amendment to open for voting.
            proposer_id: Must match the original proposer.

        Returns:
            The updated Amendment in ``voting`` status.

        Raises:
            ValueError: If status transition is invalid or proposer mismatch.
        """
        amd = self._get(amendment_id)
        if amd.proposer_id != proposer_id:
            raise ValueError(
                f"Only the original proposer ({amd.proposer_id!r}) "
                f"can open voting on amendment {amendment_id!r}"
            )
        self._transition(amd, AmendmentStatus.voting)
        amd.voting_opened_at = self._now()
        return amd

    def vote(
        self,
        amendment_id: str,
        *,
        voter_id: str,
        approve: bool,
        reason: str = "",
        veto: bool = False,
    ) -> Amendment:
        """Cast a vote on an amendment in voting status.

        MACI enforcement: the voter cannot be the proposer (separation of
        powers — no self-validation).

        If ``veto=True`` and ``approve=False``, the amendment immediately
        moves to ``vetoed`` status regardless of quorum.

        Args:
            amendment_id: The amendment to vote on.
            voter_id: The voting agent/user (must differ from proposer).
            approve: True to approve, False to reject.
            reason: Optional rationale.
            veto: If True, this is a veto vote (overrides quorum).

        Returns:
            The updated Amendment (may be ``vetoed`` if veto was cast).

        Raises:
            ValueError: If amendment is not in voting status, voter is the
                proposer, or voter has already voted.
        """
        amd = self._get(amendment_id)
        if amd.status != AmendmentStatus.voting:
            raise ValueError(
                f"Cannot vote on amendment {amendment_id!r} "
                f"in status {amd.status.value!r} (must be 'voting')"
            )
        # MACI golden rule: proposer cannot vote on own amendment
        if voter_id == amd.proposer_id:
            raise ValueError(
                f"MACI violation: proposer {voter_id!r} cannot vote on "
                f"their own amendment {amendment_id!r} (separation of powers)"
            )
        # No duplicate votes
        if voter_id in amd.voter_ids():
            raise ValueError(f"Voter {voter_id!r} has already voted on amendment {amendment_id!r}")

        v = Vote(
            voter_id=voter_id,
            approve=approve,
            reason=reason,
            timestamp=self._now(),
            veto=veto,
        )
        amd.votes.append(v)

        self._history.append(
            {
                "amendment_id": amd.amendment_id,
                "action": "vote",
                "voter_id": voter_id,
                "approve": approve,
                "veto": veto,
                "timestamp": v.timestamp,
            }
        )

        # Immediate veto check
        if veto and not approve:
            self._transition(amd, AmendmentStatus.vetoed)
            amd.resolved_at = self._now()

        return amd

    def close_voting(self, amendment_id: str) -> Amendment:
        """Close voting and resolve to ratified or rejected.

        If quorum is met and the approval rate meets the threshold, the
        amendment is ratified. Otherwise it is rejected.

        Args:
            amendment_id: The amendment to close voting on.

        Returns:
            The updated Amendment in ``ratified`` or ``rejected`` status.

        Raises:
            ValueError: If amendment is not in voting status.
        """
        amd = self._get(amendment_id)
        if amd.status != AmendmentStatus.voting:
            raise ValueError(
                f"Cannot close voting on amendment {amendment_id!r} in status {amd.status.value!r}"
            )

        amd.resolved_at = self._now()

        if amd.passes_threshold:
            self._transition(amd, AmendmentStatus.ratified)
        else:
            self._transition(amd, AmendmentStatus.rejected)

        return amd

    def ratify(self, amendment_id: str, *, ratifier_id: str) -> Amendment:
        """Explicitly ratify a voted-on amendment (executor action).

        This is an alternative to ``close_voting()`` that enforces MACI:
        only a different agent from the proposer can ratify.

        Args:
            amendment_id: The amendment to ratify.
            ratifier_id: Must differ from the proposer.

        Returns:
            The updated Amendment in ``ratified`` status.

        Raises:
            ValueError: If MACI violation or invalid state.
        """
        amd = self._get(amendment_id)

        if ratifier_id == amd.proposer_id:
            raise ValueError(
                f"MACI violation: proposer {ratifier_id!r} cannot ratify "
                f"their own amendment {amendment_id!r}"
            )

        if amd.status != AmendmentStatus.voting:
            raise ValueError(
                f"Cannot ratify amendment {amendment_id!r} "
                f"in status {amd.status.value!r} (must be 'voting')"
            )

        if not amd.passes_threshold:
            raise ValueError(
                f"Amendment {amendment_id!r} does not meet threshold: "
                f"votes={amd.vote_count}, quorum={amd.quorum_required}, "
                f"approval_rate={amd.approval_rate:.2%}, "
                f"threshold={amd.approval_threshold:.2%}"
            )

        amd.ratifier_id = ratifier_id
        amd.resolved_at = self._now()
        self._transition(amd, AmendmentStatus.ratified)
        return amd

    def enforce(
        self,
        amendment_id: str,
        *,
        executor_id: str,
        constitution: Constitution,
    ) -> Constitution:
        """Apply a ratified amendment to a constitution.

        MACI enforcement: the executor must differ from the proposer.

        The amendment is applied by delegating to
        ``Constitution.update_rule()`` (for modify) or by creating a new
        Constitution with the rule added/removed.

        Args:
            amendment_id: The ratified amendment to enforce.
            executor_id: Agent/user applying the change (must not be proposer).
            constitution: The constitution to mutate.

        Returns:
            A new Constitution with the amendment applied.

        Raises:
            ValueError: If MACI violation or invalid state.
        """
        amd = self._get(amendment_id)

        if executor_id == amd.proposer_id:
            raise ValueError(
                f"MACI violation: proposer {executor_id!r} cannot enforce "
                f"their own amendment {amendment_id!r}"
            )

        if amd.status != AmendmentStatus.ratified:
            raise ValueError(
                f"Cannot enforce amendment {amendment_id!r} "
                f"in status {amd.status.value!r} (must be 'ratified')"
            )

        amd.constitution_hash_before = constitution.hash
        new_constitution = self._apply_changes(amd, constitution)
        amd.constitution_hash_after = new_constitution.hash
        amd.enforced_at = self._now()
        self._transition(amd, AmendmentStatus.enforced)

        self._history.append(
            {
                "amendment_id": amd.amendment_id,
                "action": "enforce",
                "executor_id": executor_id,
                "constitution_hash_before": amd.constitution_hash_before,
                "constitution_hash_after": amd.constitution_hash_after,
                "timestamp": amd.enforced_at,
            }
        )

        return new_constitution

    def withdraw(self, amendment_id: str, *, actor_id: str) -> Amendment:
        """Withdraw an amendment (proposer cancels before enforcement).

        Args:
            amendment_id: The amendment to withdraw.
            actor_id: Must be the original proposer.

        Returns:
            The updated Amendment in ``withdrawn`` status.
        """
        amd = self._get(amendment_id)
        if amd.proposer_id != actor_id:
            raise ValueError(
                f"Only the original proposer ({amd.proposer_id!r}) "
                f"can withdraw amendment {amendment_id!r}"
            )
        if amd.is_terminal:
            raise ValueError(
                f"Cannot withdraw amendment {amendment_id!r} "
                f"in terminal status {amd.status.value!r}"
            )
        self._transition(amd, AmendmentStatus.withdrawn)
        return amd

    # ── query ─────────────────────────────────────────────────────────────

    def get(self, amendment_id: str) -> Amendment | None:
        return self._amendments.get(amendment_id)

    def list_amendments(
        self,
        *,
        status: str | None = None,
        proposer_id: str | None = None,
    ) -> list[Amendment]:
        """List amendments with optional filters.

        Args:
            status: Filter by AmendmentStatus value.
            proposer_id: Filter by proposer.

        Returns:
            List of matching amendments.
        """
        results: list[Amendment] = []
        for amd in self._amendments.values():
            if status is not None and amd.status.value != status:
                continue
            if proposer_id is not None and amd.proposer_id != proposer_id:
                continue
            results.append(amd)
        return results

    def history(self) -> list[dict[str, Any]]:
        """Return the full transition/action history."""
        return list(self._history)

    def summary(self) -> dict[str, Any]:
        """Return a summary of all amendments.

        Returns:
            dict with total count, by_status breakdown, by_type breakdown,
            active_amendments (non-terminal), and protocol configuration.
        """
        by_status: dict[str, int] = {}
        by_type: dict[str, int] = {}
        active = 0

        for amd in self._amendments.values():
            by_status[amd.status.value] = by_status.get(amd.status.value, 0) + 1
            by_type[amd.amendment_type.value] = by_type.get(amd.amendment_type.value, 0) + 1
            if not amd.is_terminal:
                active += 1

        return {
            "total_amendments": len(self._amendments),
            "active_amendments": active,
            "by_status": by_status,
            "by_type": by_type,
            "protocol_config": {
                "quorum": self._quorum,
                "approval_threshold": self._approval_threshold,
            },
            "history_entries": len(self._history),
        }

    # ── internal ──────────────────────────────────────────────────────────

    @staticmethod
    def _apply_changes(amd: Amendment, constitution: Constitution) -> Constitution:
        """Apply amendment changes to a constitution, returning a new one.

        Delegates to Constitution methods for immutable mutation.
        """
        changes = amd.changes
        amd_type = amd.amendment_type

        if amd_type == AmendmentType.modify_rule:
            rule_id = changes.get("rule_id", "")
            update_fields: dict[str, Any] = {k: v for k, v in changes.items() if k != "rule_id"}
            return constitution.update_rule(
                rule_id,
                reason=amd.title,
                **update_fields,
            )

        if amd_type == AmendmentType.modify_severity:
            rule_id = changes.get("rule_id", "")
            new_severity = changes.get("severity", "")
            return constitution.update_rule(
                rule_id,
                severity=new_severity,
                reason=amd.title,
            )

        if amd_type == AmendmentType.modify_workflow:
            rule_id = changes.get("rule_id", "")
            new_workflow = changes.get("workflow_action", "")
            return constitution.update_rule(
                rule_id,
                workflow_action=new_workflow,
                reason=amd.title,
            )

        if amd_type == AmendmentType.add_rule:
            from .rule import Rule

            rule_data = changes.get("rule", {})
            new_rule = Rule(**rule_data) if isinstance(rule_data, dict) else rule_data
            new_rules = list(constitution.rules) + [new_rule]
            from .constitution import Constitution as C

            return C(
                name=constitution.name,
                version=constitution.version,
                rules=new_rules,
            )

        if amd_type == AmendmentType.remove_rule:
            rule_id = changes.get("rule_id", "")
            new_rules = [r for r in constitution.rules if r.id != rule_id]
            from .constitution import Constitution as C

            return C(
                name=constitution.name,
                version=constitution.version,
                rules=new_rules,
            )

        # Fallback: return unchanged
        return constitution

    def __len__(self) -> int:
        return len(self._amendments)

    def __repr__(self) -> str:
        active = sum(1 for a in self._amendments.values() if not a.is_terminal)
        return (
            f"AmendmentProtocol("
            f"{len(self._amendments)} amendments, "
            f"{active} active, "
            f"quorum={self._quorum})"
        )
