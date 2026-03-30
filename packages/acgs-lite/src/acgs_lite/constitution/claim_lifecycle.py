"""Claim lifecycle manager for governance case processing.

Tracks governance cases through their full lifecycle::

    OPEN → CLAIMED → SUBMITTED → VALIDATING → FINALIZED
                                             → REJECTED
         → EXPIRED (timeout at any pre-final stage)

Each transition enforces MACI constraints:

- The claimer must be the submitter (no handoff without re-claim).
- Only validators from the selection quorum can move a case to VALIDATING.
- Timeouts trigger automatic expiry and re-queuing.

Integrates with :mod:`validator_selection` for quorum assignment and
:mod:`quorum` for the voting gate.

Example::

    from acgs_lite.constitution.claim_lifecycle import CaseManager, CaseConfig

    manager = CaseManager()
    case_id = manager.create(
        action="evaluate financial model v3",
        domain="finance",
        risk_tier="high",
        metadata={"model_version": "v3"},
    )

    # Miner claims the case
    manager.claim(case_id, claimer_id="miner-42")

    # Miner submits result (must be the same agent that claimed)
    manager.submit(case_id, submitter_id="miner-42", result={"decision": "allow"})

    # Validators begin validation (via quorum gate)
    manager.begin_validation(case_id, validator_ids=["val-1", "val-2", "val-3"])

    # Validation completes
    manager.finalize(case_id, outcome="approved", proof_hash="abcd1234")

    # Or: case times out
    expired = manager.expire_stale()  # returns list of expired case IDs

"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

# ── Case states ──────────────────────────────────────────────────────────────


class CaseState(str, Enum):
    """Lifecycle states for a governance case."""

    OPEN = "open"  # Published, awaiting claim
    CLAIMED = "claimed"  # Miner has claimed, working on it
    SUBMITTED = "submitted"  # Result submitted, awaiting validation
    VALIDATING = "validating"  # Validator quorum is reviewing
    FINALIZED = "finalized"  # Validation complete, outcome recorded
    REJECTED = "rejected"  # Validation quorum rejected the submission
    EXPIRED = "expired"  # Timed out at some stage


# Valid transitions
_TRANSITIONS: dict[CaseState, frozenset[CaseState]] = {
    CaseState.OPEN: frozenset({CaseState.CLAIMED, CaseState.EXPIRED}),
    CaseState.CLAIMED: frozenset({CaseState.SUBMITTED, CaseState.OPEN, CaseState.EXPIRED}),
    CaseState.SUBMITTED: frozenset({CaseState.VALIDATING, CaseState.EXPIRED}),
    CaseState.VALIDATING: frozenset({
        CaseState.FINALIZED,
        CaseState.REJECTED,
        CaseState.EXPIRED,
    }),
    CaseState.FINALIZED: frozenset(),  # terminal
    CaseState.REJECTED: frozenset({CaseState.OPEN}),  # can be re-queued
    CaseState.EXPIRED: frozenset({CaseState.OPEN}),  # can be re-queued
}


# ── Configuration ────────────────────────────────────────────────────────────


@dataclass
class CaseConfig:
    """Timeout and retry configuration for case lifecycle.

    Attributes:
        claim_timeout_minutes: Time allowed between OPEN→CLAIMED→SUBMITTED.
        submission_timeout_minutes: Time from CLAIMED to required SUBMITTED.
        validation_timeout_minutes: Time allowed for validator quorum to decide.
        max_claims: Maximum times a case can be claimed before permanent expiry.
        auto_requeue_on_expiry: Automatically move expired cases back to OPEN.
        auto_requeue_on_rejection: Automatically re-queue rejected cases.
    """

    claim_timeout_minutes: float = 60.0
    submission_timeout_minutes: float = 120.0
    validation_timeout_minutes: float = 480.0
    max_claims: int = 3
    auto_requeue_on_expiry: bool = True
    auto_requeue_on_rejection: bool = False


# ── Data types ───────────────────────────────────────────────────────────────


@dataclass
class TransitionRecord:
    """Audit record for a single state transition.

    Attributes:
        from_state: Previous state.
        to_state: New state.
        agent_id: Agent that triggered the transition.
        timestamp: ISO-8601 UTC timestamp.
        reason: Human-readable reason for the transition.
        metadata: Additional context.
    """

    from_state: str
    to_state: str
    agent_id: str
    timestamp: str
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CaseRecord:
    """Full state record for a governance case.

    Attributes:
        case_id: Unique case identifier.
        action: Description of the governance action being evaluated.
        domain: Governance domain (e.g. "finance", "privacy").
        risk_tier: Risk classification ("low", "medium", "high", "critical").
        state: Current lifecycle state.
        claimer_id: Agent that claimed the case (empty if unclaimed).
        validator_ids: Assigned validator quorum.
        result: Submitted evaluation result (empty dict if not yet submitted).
        outcome: Final outcome ("approved", "rejected", or empty).
        proof_hash: Hash of the finalization proof.
        claim_count: Number of times this case has been claimed.
        created_at: ISO-8601 creation timestamp.
        state_entered_at: ISO-8601 timestamp of last state transition.
        deadline: ISO-8601 deadline for current state (empty if none).
        transitions: Full audit trail of state transitions.
        metadata: Arbitrary extension data.
    """

    case_id: str
    action: str
    domain: str
    risk_tier: str
    state: CaseState
    claimer_id: str = ""
    validator_ids: list[str] = field(default_factory=list)
    result: dict[str, Any] = field(default_factory=dict)
    outcome: str = ""
    proof_hash: str = ""
    claim_count: int = 0
    created_at: str = ""
    state_entered_at: str = ""
    deadline: str = ""
    transitions: list[TransitionRecord] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


# ── Manager ──────────────────────────────────────────────────────────────────


class CaseManager:
    """Manages governance case lifecycle with MACI-enforced transitions.

    Tracks cases from creation through claim, submission, validation,
    and finalization. Enforces timeouts, claim-submitter identity,
    and retry limits.

    Args:
        config: Lifecycle configuration (timeouts, retry limits).

    Example::

        manager = CaseManager()
        cid = manager.create(action="review deployment", domain="ops", risk_tier="medium")
        manager.claim(cid, claimer_id="miner-5")
        manager.submit(cid, submitter_id="miner-5", result={"verdict": "safe"})
        manager.begin_validation(cid, validator_ids=["v1", "v2", "v3"])
        manager.finalize(cid, outcome="approved", proof_hash="abc123")
    """

    def __init__(self, config: CaseConfig | None = None) -> None:
        self._config = config or CaseConfig()
        self._cases: dict[str, CaseRecord] = {}
        self._counter: int = 0

    def _next_id(self) -> str:
        self._counter += 1
        return f"CASE-{self._counter:06d}"

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def _deadline_from(self, now: datetime, minutes: float) -> str:
        return (now + timedelta(minutes=minutes)).isoformat()

    def _transition(
        self,
        case: CaseRecord,
        to_state: CaseState,
        agent_id: str,
        now: datetime,
        reason: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record a state transition with audit trail."""
        allowed = _TRANSITIONS.get(case.state, frozenset())
        if to_state not in allowed:
            raise ValueError(
                f"Invalid transition: {case.state.value} → {to_state.value} "
                f"for case {case.case_id!r}. Allowed: {[s.value for s in allowed]}"
            )
        rec = TransitionRecord(
            from_state=case.state.value,
            to_state=to_state.value,
            agent_id=agent_id,
            timestamp=now.isoformat(),
            reason=reason,
            metadata=metadata or {},
        )
        case.transitions.append(rec)
        case.state = to_state
        case.state_entered_at = now.isoformat()

    # ── Creation ─────────────────────────────────────────────────────────

    def create(
        self,
        action: str,
        domain: str = "",
        risk_tier: str = "medium",
        *,
        case_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        _now: datetime | None = None,
    ) -> str:
        """Create a new governance case in OPEN state.

        Args:
            action: Description of the governance action.
            domain: Governance domain.
            risk_tier: Risk classification.
            case_id: Override auto-generated ID.
            metadata: Arbitrary extension data.
            _now: Override current time (testing).

        Returns:
            The case_id.

        Raises:
            ValueError: If case_id already exists.
        """
        now = _now or self._now()
        cid = case_id or self._next_id()
        if cid in self._cases:
            raise ValueError(f"Case {cid!r} already exists")

        deadline = self._deadline_from(now, self._config.claim_timeout_minutes)

        case = CaseRecord(
            case_id=cid,
            action=action,
            domain=domain,
            risk_tier=risk_tier,
            state=CaseState.OPEN,
            created_at=now.isoformat(),
            state_entered_at=now.isoformat(),
            deadline=deadline,
            metadata=metadata or {},
        )
        case.transitions.append(
            TransitionRecord(
                from_state="",
                to_state=CaseState.OPEN.value,
                agent_id="system",
                timestamp=now.isoformat(),
                reason="Case created",
            )
        )
        self._cases[cid] = case
        return cid

    # ── Claim ────────────────────────────────────────────────────────────

    def claim(
        self,
        case_id: str,
        claimer_id: str,
        *,
        _now: datetime | None = None,
    ) -> CaseRecord:
        """Claim an OPEN case for processing.

        Args:
            case_id: The case to claim.
            claimer_id: Agent claiming the case.
            _now: Override current time (testing).

        Returns:
            Updated CaseRecord.

        Raises:
            KeyError: Case not found.
            ValueError: Case not in OPEN state, or max claims exceeded.
        """
        case = self._get(case_id)
        now = _now or self._now()

        self._check_timeout(case, now)

        if case.state != CaseState.OPEN:
            raise ValueError(
                f"Case {case_id!r} is {case.state.value}, must be OPEN to claim"
            )

        if case.claim_count >= self._config.max_claims:
            raise ValueError(
                f"Case {case_id!r} has reached max claims ({self._config.max_claims})"
            )

        case.claimer_id = claimer_id
        case.claim_count += 1
        deadline = self._deadline_from(now, self._config.submission_timeout_minutes)
        case.deadline = deadline

        self._transition(
            case, CaseState.CLAIMED, claimer_id, now,
            reason=f"Claimed by {claimer_id} (attempt {case.claim_count})",
        )
        return case

    # ── Submit ───────────────────────────────────────────────────────────

    def submit(
        self,
        case_id: str,
        submitter_id: str,
        result: dict[str, Any],
        *,
        _now: datetime | None = None,
    ) -> CaseRecord:
        """Submit a result for a claimed case.

        MACI constraint: submitter must be the claimer.

        Args:
            case_id: The case to submit for.
            submitter_id: Agent submitting the result.
            result: The evaluation result.
            _now: Override current time (testing).

        Returns:
            Updated CaseRecord.

        Raises:
            KeyError: Case not found.
            ValueError: Not claimed, wrong submitter, or timed out.
        """
        case = self._get(case_id)
        now = _now or self._now()

        self._check_timeout(case, now)

        if case.state != CaseState.CLAIMED:
            raise ValueError(
                f"Case {case_id!r} is {case.state.value}, must be CLAIMED to submit"
            )

        # MACI: claimer must be submitter
        if case.claimer_id != submitter_id:
            raise ValueError(
                f"MACI violation: submitter {submitter_id!r} is not the claimer "
                f"{case.claimer_id!r} for case {case_id!r}. "
                "Claimer must be submitter (no handoff without re-claim)."
            )

        case.result = dict(result)
        self._transition(
            case, CaseState.SUBMITTED, submitter_id, now,
            reason="Result submitted",
            metadata={"result_keys": list(result.keys())},
        )
        return case

    # ── Validation ───────────────────────────────────────────────────────

    def begin_validation(
        self,
        case_id: str,
        validator_ids: list[str],
        *,
        _now: datetime | None = None,
    ) -> CaseRecord:
        """Assign validators and begin the validation phase.

        Args:
            case_id: The case to validate.
            validator_ids: Selected validator quorum (from ValidatorSelector).
            _now: Override current time (testing).

        Returns:
            Updated CaseRecord.

        Raises:
            KeyError: Case not found.
            ValueError: Case not in SUBMITTED state, or no validators provided.
        """
        case = self._get(case_id)
        now = _now or self._now()

        self._check_timeout(case, now)

        if case.state != CaseState.SUBMITTED:
            raise ValueError(
                f"Case {case_id!r} is {case.state.value}, must be SUBMITTED to begin validation"
            )

        if not validator_ids:
            raise ValueError("At least one validator must be assigned")

        # MACI: producer cannot be a validator
        if case.claimer_id in validator_ids:
            raise ValueError(
                f"MACI violation: producer {case.claimer_id!r} cannot be in the "
                f"validator set for case {case_id!r}"
            )

        case.validator_ids = list(validator_ids)
        deadline = self._deadline_from(now, self._config.validation_timeout_minutes)
        case.deadline = deadline

        self._transition(
            case, CaseState.VALIDATING, "system", now,
            reason=f"Validation started with {len(validator_ids)} validators",
            metadata={"validator_ids": validator_ids},
        )
        return case

    # ── Finalization ─────────────────────────────────────────────────────

    def finalize(
        self,
        case_id: str,
        outcome: str,
        proof_hash: str = "",
        *,
        _now: datetime | None = None,
    ) -> CaseRecord:
        """Finalize a case after validation quorum is reached.

        Args:
            case_id: The case to finalize.
            outcome: "approved" or "rejected".
            proof_hash: Merkle proof hash for the decision.
            _now: Override current time (testing).

        Returns:
            Updated CaseRecord.

        Raises:
            KeyError: Case not found.
            ValueError: Case not in VALIDATING state, or invalid outcome.
        """
        case = self._get(case_id)
        now = _now or self._now()

        if case.state != CaseState.VALIDATING:
            raise ValueError(
                f"Case {case_id!r} is {case.state.value}, must be VALIDATING to finalize"
            )

        outcome_lower = outcome.lower()
        if outcome_lower not in ("approved", "rejected"):
            raise ValueError(f"Outcome must be 'approved' or 'rejected', got {outcome!r}")

        case.outcome = outcome_lower
        case.proof_hash = proof_hash
        case.deadline = ""  # no more deadlines

        target = CaseState.FINALIZED if outcome_lower == "approved" else CaseState.REJECTED
        self._transition(
            case, target, "system", now,
            reason=f"Validation {outcome_lower}",
            metadata={"proof_hash": proof_hash},
        )

        # Auto-requeue rejected cases if configured
        if target == CaseState.REJECTED and self._config.auto_requeue_on_rejection:
            self._requeue(case, now, reason="Auto-requeued after rejection")

        return case

    # ── Release (unclaim) ────────────────────────────────────────────────

    def release(
        self,
        case_id: str,
        agent_id: str,
        reason: str = "",
        *,
        _now: datetime | None = None,
    ) -> CaseRecord:
        """Release a claimed case back to OPEN (voluntary unclaim).

        Args:
            case_id: The case to release.
            agent_id: The agent releasing (must be the claimer).
            reason: Why the case is being released.
            _now: Override current time (testing).

        Returns:
            Updated CaseRecord.

        Raises:
            KeyError: Case not found.
            ValueError: Case not claimed, or wrong agent.
        """
        case = self._get(case_id)
        now = _now or self._now()

        if case.state != CaseState.CLAIMED:
            raise ValueError(
                f"Case {case_id!r} is {case.state.value}, must be CLAIMED to release"
            )

        if case.claimer_id != agent_id:
            raise ValueError(
                f"Agent {agent_id!r} is not the claimer ({case.claimer_id!r}) "
                f"for case {case_id!r}"
            )

        case.claimer_id = ""
        deadline = self._deadline_from(now, self._config.claim_timeout_minutes)
        case.deadline = deadline

        self._transition(
            case, CaseState.OPEN, agent_id, now,
            reason=reason or "Released by claimer",
        )
        return case

    # ── Requeue ──────────────────────────────────────────────────────────

    def requeue(
        self,
        case_id: str,
        reason: str = "",
        *,
        _now: datetime | None = None,
    ) -> CaseRecord:
        """Manually re-queue an EXPIRED or REJECTED case.

        Args:
            case_id: The case to re-queue.
            reason: Why the case is being re-queued.
            _now: Override current time (testing).

        Returns:
            Updated CaseRecord.

        Raises:
            KeyError: Case not found.
            ValueError: Case not in EXPIRED or REJECTED state, or max claims exceeded.
        """
        case = self._get(case_id)
        now = _now or self._now()

        if case.state not in (CaseState.EXPIRED, CaseState.REJECTED):
            raise ValueError(
                f"Case {case_id!r} is {case.state.value}, must be EXPIRED or REJECTED to requeue"
            )

        if case.claim_count >= self._config.max_claims:
            raise ValueError(
                f"Case {case_id!r} has reached max claims ({self._config.max_claims}), "
                "cannot re-queue"
            )

        self._requeue(case, now, reason=reason or "Manual requeue")
        return case

    def _requeue(self, case: CaseRecord, now: datetime, reason: str) -> None:
        """Internal: move case back to OPEN with fresh deadline."""
        case.claimer_id = ""
        case.result = {}
        case.validator_ids = []
        case.outcome = ""
        case.proof_hash = ""
        deadline = self._deadline_from(now, self._config.claim_timeout_minutes)
        case.deadline = deadline

        self._transition(case, CaseState.OPEN, "system", now, reason=reason)

    # ── Timeout handling ─────────────────────────────────────────────────

    def _check_timeout(self, case: CaseRecord, now: datetime) -> None:
        """Check if the case has exceeded its deadline, and expire it."""
        if case.state in (CaseState.FINALIZED, CaseState.REJECTED, CaseState.EXPIRED):
            return
        if not case.deadline:
            return
        deadline_dt = datetime.fromisoformat(case.deadline)
        if now >= deadline_dt:
            self._expire(case, now)

    def _expire(self, case: CaseRecord, now: datetime) -> None:
        """Move a case to EXPIRED state."""
        prev = case.state
        case.deadline = ""
        self._transition(
            case, CaseState.EXPIRED, "system", now,
            reason=f"Timed out in {prev.value} state",
        )

        # Auto-requeue if configured and under claim limit
        if (
            self._config.auto_requeue_on_expiry
            and case.claim_count < self._config.max_claims
        ):
            self._requeue(case, now, reason="Auto-requeued after expiry")

    def expire_stale(self, *, _now: datetime | None = None) -> list[str]:
        """Scan all cases and expire any that have exceeded their deadlines.

        Returns:
            List of case IDs that were expired (or expired + re-queued).
        """
        now = _now or self._now()
        expired: list[str] = []
        for case in self._cases.values():
            if case.state in (CaseState.FINALIZED, CaseState.REJECTED, CaseState.EXPIRED):
                continue
            if not case.deadline:
                continue
            deadline_dt = datetime.fromisoformat(case.deadline)
            if now >= deadline_dt:
                self._expire(case, now)
                expired.append(case.case_id)
        return expired

    # ── Queries ──────────────────────────────────────────────────────────

    def get(self, case_id: str) -> CaseRecord | None:
        """Return case record or None."""
        return self._cases.get(case_id)

    def _get(self, case_id: str) -> CaseRecord:
        """Return case record or raise KeyError."""
        try:
            return self._cases[case_id]
        except KeyError:
            raise KeyError(f"Case {case_id!r} not found") from None

    def cases_by_state(self, state: CaseState) -> list[str]:
        """Return case IDs in the given state."""
        return sorted(c.case_id for c in self._cases.values() if c.state == state)

    def open_cases(self, domain: str = "") -> list[str]:
        """Return IDs of OPEN cases, optionally filtered by domain."""
        result: list[str] = []
        for c in self._cases.values():
            if c.state != CaseState.OPEN:
                continue
            if domain and c.domain.lower() != domain.lower():
                continue
            result.append(c.case_id)
        return sorted(result)

    def claimable_cases(
        self,
        agent_id: str,
        domain: str = "",
    ) -> list[str]:
        """Return OPEN cases that an agent can claim.

        Excludes cases that have reached max claims.

        Args:
            agent_id: The agent looking for work.
            domain: Optional domain filter.

        Returns:
            Sorted list of claimable case IDs.
        """
        result: list[str] = []
        for c in self._cases.values():
            if c.state != CaseState.OPEN:
                continue
            if c.claim_count >= self._config.max_claims:
                continue
            if domain and c.domain.lower() != domain.lower():
                continue
            result.append(c.case_id)
        return sorted(result)

    def agent_active_cases(self, agent_id: str) -> list[str]:
        """Return case IDs currently claimed by an agent."""
        return sorted(
            c.case_id
            for c in self._cases.values()
            if c.claimer_id == agent_id and c.state in (CaseState.CLAIMED, CaseState.SUBMITTED)
        )

    def transitions(self, case_id: str) -> list[TransitionRecord]:
        """Return the transition audit trail for a case.

        Raises:
            KeyError: Case not found.
        """
        return list(self._get(case_id).transitions)

    def summary(self) -> dict[str, Any]:
        """Return aggregate summary of all cases."""
        by_state: dict[str, int] = {}
        by_domain: dict[str, int] = {}
        total_claims = 0
        for c in self._cases.values():
            by_state[c.state.value] = by_state.get(c.state.value, 0) + 1
            if c.domain:
                by_domain[c.domain] = by_domain.get(c.domain, 0) + 1
            total_claims += c.claim_count

        return {
            "total_cases": len(self._cases),
            "by_state": by_state,
            "by_domain": by_domain,
            "total_claims": total_claims,
            "open_count": len(self.cases_by_state(CaseState.OPEN)),
            "active_count": len(self.cases_by_state(CaseState.CLAIMED))
            + len(self.cases_by_state(CaseState.SUBMITTED))
            + len(self.cases_by_state(CaseState.VALIDATING)),
            "finalized_count": len(self.cases_by_state(CaseState.FINALIZED)),
        }

    def __len__(self) -> int:
        return len(self._cases)

    def __repr__(self) -> str:
        open_n = len(self.cases_by_state(CaseState.OPEN))
        active_n = (
            len(self.cases_by_state(CaseState.CLAIMED))
            + len(self.cases_by_state(CaseState.SUBMITTED))
        )
        return f"CaseManager({len(self._cases)} cases, {open_n} open, {active_n} active)"
