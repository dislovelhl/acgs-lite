"""Governance Coordinator — bridges acgs-lite validation primitives to the subnet.

Wires the four acgs-lite governance modules into the constitutional_swarm
bittensor lifecycle:

    SubnetOwner.package_case()
        ↓ create_case()
    CaseManager (OPEN)
        ↓ assign_miner()
    CaseManager (CLAIMED → SUBMITTED)
        ↓ select_validators() via ValidatorSelector
    CaseManager (VALIDATING)
        ↓ finalize_case() from ConstitutionalValidator result
    CaseManager (FINALIZED/REJECTED)
        ↓ record_for_audit()
    SpotCheckAuditor
        ↓ run_audit_cycle()
    TrustScoreManager → sync → ValidatorPool
        ↓ (loop: next selection uses updated trust)

This is the single coordination point that ties together:
  - constitutional_swarm/bittensor/ (miner, validator, subnet_owner)
  - acgs_lite.constitution.claim_lifecycle (CaseManager)
  - acgs_lite.constitution.validator_selection (ValidatorSelector, ValidatorPool)
  - acgs_lite.constitution.spot_check (SpotCheckAuditor)
  - acgs_lite.constitution.trust_score (TrustScoreManager)

Example::

    coordinator = GovernanceCoordinator(
        constitution_path="governance.yaml",
    )
    # Register validators
    coordinator.register_validator("val-1", trust_score=0.9, model="gpt-4")
    coordinator.register_validator("val-2", trust_score=0.85, model="claude-3")
    ...

    # Process a governance case
    case_id = coordinator.create_case(
        action="Evaluate privacy conflict",
        domain="finance",
        risk_tier="high",
    )
    coordinator.assign_miner(case_id, "miner-42")
    coordinator.submit_result(case_id, "miner-42", {"verdict": "allow"})
    coordinator.select_and_begin_validation(case_id)
    coordinator.finalize_case(case_id, accepted=True, votes={"val-1": "approve", ...})

    # Periodic audit cycle
    audit = coordinator.run_audit_cycle()
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from acgs_lite.constitution.claim_lifecycle import (
    CaseConfig,
    CaseManager,
    CaseRecord,
    CaseState,
)
from acgs_lite.constitution.spot_check import (
    AuditPolicy,
    SpotCheckAuditor,
    SpotCheckResult,
    TrustAdjustment,
)
from acgs_lite.constitution.trust_score import (
    TrustConfig,
    TrustScoreManager,
)
from acgs_lite.constitution.validator_selection import (
    SelectionPolicy,
    SelectionResult,
    ValidatorPool,
    ValidatorSelector,
)


# ── Configuration ────────────────────────────────────────────────────────────


@dataclass
class CoordinatorConfig:
    """Configuration for the governance coordinator.

    Attributes:
        case_config: Lifecycle configuration (timeouts, retry limits).
        selection_policy: Validator selection behaviour.
        audit_policy: Spot-check auditing behaviour.
        trust_config: Default trust config for new validators.
        default_risk_tier: Risk tier when not specified.
        auto_audit: Run audit cycle automatically after each finalization.
    """

    case_config: CaseConfig = field(default_factory=CaseConfig)
    selection_policy: SelectionPolicy = field(default_factory=SelectionPolicy)
    audit_policy: AuditPolicy = field(default_factory=AuditPolicy)
    trust_config: TrustConfig = field(default_factory=lambda: TrustConfig(
        initial_score=0.9,
        time_decay_rate=0.001,
    ))
    default_risk_tier: str = "medium"
    auto_audit: bool = False


# ── Audit results ────────────────────────────────────────────────────────────


@dataclass
class AuditCycleResult:
    """Result of a single audit cycle.

    Attributes:
        spot_check_results: Individual case spot-check outcomes.
        trust_adjustments: Aggregated per-validator trust deltas.
        adjustments_applied: Number of adjustments applied to trust manager.
        validators_synced: Number of validators synced to the pool.
        biased_validators: Validators flagged for systematic bias.
    """

    spot_check_results: list[SpotCheckResult]
    trust_adjustments: list[TrustAdjustment]
    adjustments_applied: int
    validators_synced: int
    biased_validators: list[dict[str, Any]]


# ── Coordinator ──────────────────────────────────────────────────────────────


class GovernanceCoordinator:
    """Bridges acgs-lite governance primitives to the subnet runtime.

    Provides a single API surface that orchestrates case lifecycle,
    validator selection, spot-check auditing, and trust management.
    """

    def __init__(self, config: CoordinatorConfig | None = None) -> None:
        cfg = config or CoordinatorConfig()
        self._config = cfg

        self._case_mgr = CaseManager(cfg.case_config)
        self._pool = ValidatorPool()
        self._selector = ValidatorSelector(self._pool, cfg.selection_policy)
        self._trust_mgr = TrustScoreManager()
        self._auditor = SpotCheckAuditor(cfg.audit_policy)

        # Track selection results per case for validation linkage
        self._selections: dict[str, SelectionResult] = {}

        # Track finalized cases pending audit registration
        self._pending_audit: dict[str, dict[str, Any]] = {}

    # ── Subsystem access ─────────────────────────────────────────────────

    @property
    def case_manager(self) -> CaseManager:
        return self._case_mgr

    @property
    def validator_pool(self) -> ValidatorPool:
        return self._pool

    @property
    def trust_manager(self) -> TrustScoreManager:
        return self._trust_mgr

    @property
    def auditor(self) -> SpotCheckAuditor:
        return self._auditor

    @property
    def selector(self) -> ValidatorSelector:
        return self._selector

    # ── Validator registration ───────────────────────────────────────────

    def register_validator(
        self,
        validator_id: str,
        *,
        trust_score: float | None = None,
        domains: list[str] | None = None,
        model: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Register a validator in both the pool and trust manager.

        Args:
            validator_id: Unique validator identifier.
            trust_score: Initial trust score (default from config).
            domains: Governance domains.
            model: Model/provider for diversity tracking.
            metadata: Arbitrary metadata.
        """
        score = trust_score if trust_score is not None else self._config.trust_config.initial_score
        self._pool.register(
            validator_id,
            trust_score=score,
            domains=domains,
            model=model,
            metadata=metadata,
        )
        try:
            self._trust_mgr.register(validator_id, TrustConfig(
                initial_score=score,
                time_decay_rate=self._config.trust_config.time_decay_rate,
                trusted_threshold=self._config.trust_config.trusted_threshold,
                monitored_threshold=self._config.trust_config.monitored_threshold,
            ))
        except ValueError:
            pass  # already registered, keep existing state

    def deactivate_validator(self, validator_id: str) -> None:
        """Remove a validator from active selection."""
        self._pool.deactivate(validator_id)

    # ── Case lifecycle ───────────────────────────────────────────────────

    def create_case(
        self,
        action: str,
        domain: str = "",
        risk_tier: str = "",
        *,
        case_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        _now: datetime | None = None,
    ) -> str:
        """Create a new governance case.

        Returns:
            The case_id.
        """
        tier = risk_tier or self._config.default_risk_tier
        return self._case_mgr.create(
            action, domain=domain, risk_tier=tier,
            case_id=case_id, metadata=metadata, _now=_now,
        )

    def assign_miner(
        self,
        case_id: str,
        miner_id: str,
        *,
        _now: datetime | None = None,
    ) -> CaseRecord:
        """Assign a miner to an OPEN case (claim).

        Returns:
            Updated CaseRecord.
        """
        return self._case_mgr.claim(case_id, miner_id, _now=_now)

    def submit_result(
        self,
        case_id: str,
        submitter_id: str,
        result: dict[str, Any],
        *,
        _now: datetime | None = None,
    ) -> CaseRecord:
        """Submit a miner's result for a claimed case.

        MACI: submitter must be the claimer.

        Returns:
            Updated CaseRecord.
        """
        return self._case_mgr.submit(case_id, submitter_id, result, _now=_now)

    def select_and_begin_validation(
        self,
        case_id: str,
        *,
        risk_tier: str | None = None,
        domain: str | None = None,
        seed: str | None = None,
        _now: datetime | None = None,
    ) -> SelectionResult:
        """Select a validator quorum and begin validation.

        Uses the ValidatorSelector with trust-weighted, diversity-aware,
        verifiable selection. The producer (claimer) is automatically excluded.

        Returns:
            SelectionResult with proof.
        """
        case = self._case_mgr.get(case_id)
        if case is None:
            raise KeyError(f"Case {case_id!r} not found")

        selection = self._selector.select(
            case_id=case_id,
            producer_id=case.claimer_id,
            risk_tier=risk_tier or case.risk_tier or self._config.default_risk_tier,
            domain=domain or case.domain,
            seed=seed,
            _now=_now,
        )

        self._case_mgr.begin_validation(case_id, selection.selected, _now=_now)
        self._selections[case_id] = selection
        return selection

    def finalize_case(
        self,
        case_id: str,
        *,
        accepted: bool,
        validator_votes: dict[str, str] | None = None,
        proof_hash: str = "",
        _now: datetime | None = None,
    ) -> CaseRecord:
        """Finalize a case after validation.

        If validator_votes is provided, also registers the case for
        spot-check auditing.

        Args:
            case_id: Case to finalize.
            accepted: Whether the validation quorum accepted.
            validator_votes: {validator_id: "approve"|"reject"}.
            proof_hash: Merkle proof hash.
            _now: Override time.

        Returns:
            Updated CaseRecord.
        """
        outcome = "approved" if accepted else "rejected"
        case = self._case_mgr.finalize(case_id, outcome, proof_hash=proof_hash, _now=_now)

        # Register for spot-check if we have vote data
        if validator_votes:
            self._register_for_audit(
                case_id=case_id,
                domain=case.domain,
                outcome=outcome,
                validator_votes=validator_votes,
                proof_hash=proof_hash,
                producer_id=case.claimer_id,
                _now=_now,
            )

        # Auto-audit if configured
        if self._config.auto_audit:
            self.run_audit_cycle(_now=_now)

        return case

    def _register_for_audit(
        self,
        case_id: str,
        domain: str,
        outcome: str,
        validator_votes: dict[str, str],
        proof_hash: str,
        producer_id: str,
        _now: datetime | None = None,
    ) -> None:
        """Register a finalized case for spot-check auditing."""
        submission_hash = proof_hash or hashlib.sha256(
            f"{case_id}:{outcome}".encode()
        ).hexdigest()[:16]

        self._auditor.register_completed(
            case_id=case_id,
            domain=domain,
            original_outcome=outcome,
            validator_votes=validator_votes,
            submission_hash=submission_hash,
            producer_id=producer_id,
            _now=_now,
        )

    # ── Audit cycle ──────────────────────────────────────────────────────

    def run_audit_cycle(
        self,
        check_fn: Any | None = None,
        *,
        _now: datetime | None = None,
    ) -> AuditCycleResult:
        """Run a spot-check audit cycle and apply trust adjustments.

        If no check_fn is provided, uses the default oracle that
        agrees with the original outcome (no-op audit). In production,
        this would be a higher-fidelity re-validation function.

        Returns:
            AuditCycleResult with all audit data.
        """
        if check_fn is None:
            # Default: agree with original (no spot-check disagreements)
            def _default_oracle(case_id: str, sub_hash: str) -> str:
                return "approve"
            check_fn = _default_oracle

        # Run spot-checks
        results = self._auditor.run_spot_check(check_fn, _now=_now)

        # Compute trust adjustments
        adjustments = self._auditor.compute_adjustments(results)

        # Apply adjustments to trust manager
        applied = self._auditor.apply_adjustments(
            self._trust_mgr, adjustments, _now=_now,
        )

        # Sync trust scores back to validator pool
        synced = self._trust_mgr.sync_to_validator_pool(self._pool, _now=_now)

        # Check for biased validators
        biased = self._auditor.biased_validators()

        return AuditCycleResult(
            spot_check_results=results,
            trust_adjustments=adjustments,
            adjustments_applied=applied,
            validators_synced=synced,
            biased_validators=biased,
        )

    # ── Timeout management ───────────────────────────────────────────────

    def expire_stale_cases(
        self, *, _now: datetime | None = None,
    ) -> list[str]:
        """Expire and optionally re-queue timed-out cases.

        Returns:
            List of expired case IDs.
        """
        return self._case_mgr.expire_stale(_now=_now)

    # ── Queries ──────────────────────────────────────────────────────────

    def case(self, case_id: str) -> CaseRecord | None:
        """Get a case record."""
        return self._case_mgr.get(case_id)

    def selection_proof(self, case_id: str) -> SelectionResult | None:
        """Get the selection result/proof for a case."""
        return self._selections.get(case_id)

    def open_cases(self, domain: str = "") -> list[str]:
        """List open cases, optionally filtered by domain."""
        return self._case_mgr.open_cases(domain)

    def claimable_cases(self, miner_id: str, domain: str = "") -> list[str]:
        """List cases a miner can claim."""
        return self._case_mgr.claimable_cases(miner_id, domain)

    def validator_trust(
        self,
        validator_id: str,
        domain: str = "",
        *,
        _now: datetime | None = None,
    ) -> float:
        """Get current trust score for a validator."""
        return self._trust_mgr.score(validator_id, domain, _now=_now)

    def validator_tier(
        self,
        validator_id: str,
        domain: str = "",
        *,
        _now: datetime | None = None,
    ) -> str:
        """Get current trust tier for a validator."""
        return self._trust_mgr.tier(validator_id, domain, _now=_now)

    def monoculture_report(self, domain: str = "") -> dict[str, Any]:
        """Get model diversity report for the validator pool."""
        return self._pool.monoculture_report(domain)

    # ── Summary ──────────────────────────────────────────────────────────

    def summary(self, *, _now: datetime | None = None) -> dict[str, Any]:
        """Comprehensive coordinator summary across all subsystems.

        Returns:
            dict with case_lifecycle, trust, audit, pool, and selection data.
        """
        return {
            "case_lifecycle": self._case_mgr.summary(),
            "trust": self._trust_mgr.summary(),
            "audit": self._auditor.summary(),
            "pool": {
                "total_validators": len(self._pool),
                "monoculture": self._pool.monoculture_report(),
            },
            "selections_tracked": len(self._selections),
            "pending_audit_cases": self._auditor.unchecked_count(),
        }

    def __repr__(self) -> str:
        return (
            f"GovernanceCoordinator("
            f"cases={len(self._case_mgr)}, "
            f"validators={len(self._pool)}, "
            f"selections={len(self._selections)})"
        )
