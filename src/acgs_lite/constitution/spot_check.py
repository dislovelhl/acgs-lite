"""Spot-check auditing for governance validation quality.

Randomly samples finalized governance cases and re-validates them using a
higher-fidelity process. Compares spot-check outcomes against original
validator votes to detect:

- **Lazy validation** — validators who rubber-stamp without genuine review.
- **Correct dissent** — minority validators who were right when the majority
  was wrong (these get a trust bonus, not a penalty).
- **Systematic bias** — validators who consistently approve or reject
  regardless of case content.

Integrates with :mod:`trust_score` for reputation adjustments and produces
audit reports for governance transparency.

Example::

    from acgs_lite.constitution.spot_check import SpotCheckAuditor, AuditPolicy

    auditor = SpotCheckAuditor(policy=AuditPolicy(sample_rate=0.1))

    # Register a completed case with validator votes
    auditor.register_completed(
        case_id="case-001",
        domain="finance",
        original_outcome="approved",
        validator_votes={"val-1": "approve", "val-2": "approve", "val-3": "reject"},
        submission_hash="abc123",
    )

    # Run spot-check on sampled cases
    results = auditor.run_spot_check(
        check_fn=my_revalidation_function,  # (case_id, submission_hash) → "approve"|"reject"
    )

    # Apply trust adjustments
    adjustments = auditor.compute_adjustments(results)
    auditor.apply_adjustments(trust_manager, adjustments)

"""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

# ── Types ────────────────────────────────────────────────────────────────────


@dataclass
class CompletedCase:
    """Record of a finalized governance case for spot-check eligibility.

    Attributes:
        case_id: Unique case identifier.
        domain: Governance domain.
        original_outcome: The quorum's final outcome ("approved" or "rejected").
        validator_votes: Mapping of validator_id → vote ("approve" or "reject").
        submission_hash: Hash of the submitted content (for re-validation).
        producer_id: The agent that produced the submission.
        finalized_at: ISO-8601 timestamp of finalization.
        spot_checked: Whether this case has already been spot-checked.
        metadata: Arbitrary extension data.
    """

    case_id: str
    domain: str
    original_outcome: str
    validator_votes: dict[str, str]
    submission_hash: str
    producer_id: str = ""
    finalized_at: str = ""
    spot_checked: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SpotCheckResult:
    """Result of a single spot-check re-validation.

    Attributes:
        case_id: The case that was spot-checked.
        domain: Governance domain.
        original_outcome: What the quorum decided.
        spot_check_outcome: What the re-validation found.
        agrees_with_original: Whether the spot-check agrees with the quorum.
        validator_assessments: Per-validator assessment of their vote accuracy.
        checked_at: ISO-8601 timestamp.
        checker_id: Identifier of the spot-check process/agent.
        reasoning: Free-text explanation from the re-validation.
    """

    case_id: str
    domain: str
    original_outcome: str
    spot_check_outcome: str
    agrees_with_original: bool
    validator_assessments: list[ValidatorAssessment]
    checked_at: str
    checker_id: str = "spot-check-system"
    reasoning: str = ""


@dataclass
class ValidatorAssessment:
    """Assessment of a single validator's vote on a spot-checked case.

    Attributes:
        validator_id: The validator being assessed.
        vote: Their original vote ("approve" or "reject").
        agreed_with_majority: Whether their vote matched the quorum outcome.
        agreed_with_spot_check: Whether their vote matched the spot-check outcome.
        assessment: Classification of the vote quality.
        trust_delta: Recommended trust score change.
    """

    validator_id: str
    vote: str
    agreed_with_majority: bool
    agreed_with_spot_check: bool
    assessment: str  # "correct", "lazy_agree", "correct_dissent", "wrong_dissent", "wrong_agree"
    trust_delta: float


@dataclass
class TrustAdjustment:
    """Aggregated trust adjustment for a validator across spot-checks.

    Attributes:
        validator_id: The validator to adjust.
        domain: Governance domain (empty = global).
        delta: Net trust score change.
        cases_checked: Number of cases contributing to this adjustment.
        correct_count: Number of cases where the validator was correct.
        lazy_count: Number of cases flagged as lazy validation.
        dissent_bonus_count: Number of correct dissent bonuses awarded.
        assessments: Individual assessment details.
    """

    validator_id: str
    domain: str
    delta: float
    cases_checked: int
    correct_count: int
    lazy_count: int
    dissent_bonus_count: int
    assessments: list[str] = field(default_factory=list)


@dataclass
class AuditPolicy:
    """Configuration for spot-check auditing behavior.

    Attributes:
        sample_rate: Fraction of finalized cases to spot-check (0.0–1.0).
        correct_reward: Trust bonus for a correct vote confirmed by spot-check.
        lazy_penalty: Trust penalty for a vote that agreed with a wrong majority.
        correct_dissent_bonus: Trust bonus for correctly disagreeing with a wrong majority.
            This is the key anti-rubber-stamping incentive: validators who do
            genuine review and catch errors are rewarded, not punished.
        wrong_dissent_penalty: Penalty for disagreeing with a correct majority.
        bias_threshold: Fraction of approve/reject votes above which a validator
            is flagged for systematic bias (e.g., 0.95 = flags if >95% same vote).
        min_cases_for_bias: Minimum cases before bias detection activates.
        seed: Override random seed for sampling (testing/replay).
    """

    sample_rate: float = 0.10
    correct_reward: float = 0.005
    lazy_penalty: float = 0.03
    correct_dissent_bonus: float = 0.05
    wrong_dissent_penalty: float = 0.01
    bias_threshold: float = 0.95
    min_cases_for_bias: int = 20
    seed: str = ""


@dataclass
class ValidatorProfile:
    """Accumulated voting profile for bias detection.

    Attributes:
        validator_id: Validator identifier.
        approve_count: Total approve votes.
        reject_count: Total reject votes.
        spot_check_correct: Times confirmed correct by spot-check.
        spot_check_wrong: Times found wrong by spot-check.
        correct_dissents: Times correctly dissented from wrong majority.
        lazy_flags: Times flagged for lazy agreement with wrong majority.
    """

    validator_id: str
    approve_count: int = 0
    reject_count: int = 0
    spot_check_correct: int = 0
    spot_check_wrong: int = 0
    correct_dissents: int = 0
    lazy_flags: int = 0

    @property
    def total_votes(self) -> int:
        return self.approve_count + self.reject_count

    @property
    def approve_rate(self) -> float:
        if self.total_votes == 0:
            return 0.0
        return self.approve_count / self.total_votes

    @property
    def reject_rate(self) -> float:
        if self.total_votes == 0:
            return 0.0
        return self.reject_count / self.total_votes

    def has_bias(self, threshold: float = 0.95, min_cases: int = 20) -> bool:
        """Check if the validator shows systematic voting bias."""
        if self.total_votes < min_cases:
            return False
        return self.approve_rate > threshold or self.reject_rate > threshold

    @property
    def bias_direction(self) -> str:
        """Return the direction of bias, if any."""
        if self.approve_rate > self.reject_rate:
            return "approve"
        if self.reject_rate > self.approve_rate:
            return "reject"
        return "neutral"

    def to_dict(self) -> dict[str, Any]:
        return {
            "validator_id": self.validator_id,
            "total_votes": self.total_votes,
            "approve_count": self.approve_count,
            "reject_count": self.reject_count,
            "approve_rate": round(self.approve_rate, 4),
            "reject_rate": round(self.reject_rate, 4),
            "spot_check_correct": self.spot_check_correct,
            "spot_check_wrong": self.spot_check_wrong,
            "correct_dissents": self.correct_dissents,
            "lazy_flags": self.lazy_flags,
        }


# ── Auditor ──────────────────────────────────────────────────────────────────


class SpotCheckAuditor:
    """Spot-check auditor for governance validation quality.

    Maintains a pool of completed cases, samples them for re-validation,
    compares results, and computes trust adjustments. Also tracks per-validator
    voting profiles for bias detection.

    Args:
        policy: Audit policy configuration.

    Example::

        auditor = SpotCheckAuditor()
        auditor.register_completed(
            case_id="c1",
            domain="finance",
            original_outcome="approved",
            validator_votes={"v1": "approve", "v2": "approve", "v3": "reject"},
            submission_hash="abc",
        )

        results = auditor.run_spot_check(check_fn=my_checker)
        adjustments = auditor.compute_adjustments(results)
    """

    def __init__(self, policy: AuditPolicy | None = None) -> None:
        self.policy = policy or AuditPolicy()
        self._cases: dict[str, CompletedCase] = {}
        self._profiles: dict[str, ValidatorProfile] = {}
        self._results: list[SpotCheckResult] = []

    # ── Registration ─────────────────────────────────────────────────────

    def register_completed(
        self,
        case_id: str,
        domain: str,
        original_outcome: str,
        validator_votes: dict[str, str],
        submission_hash: str,
        *,
        producer_id: str = "",
        metadata: dict[str, Any] | None = None,
        _now: datetime | None = None,
    ) -> CompletedCase:
        """Register a finalized case for potential spot-checking.

        Also updates per-validator voting profiles for bias tracking.

        Args:
            case_id: Unique case identifier.
            domain: Governance domain.
            original_outcome: Quorum outcome ("approved" or "rejected").
            validator_votes: {validator_id: "approve"|"reject"}.
            submission_hash: Hash of submitted content.
            producer_id: Agent that produced the submission.
            metadata: Extension data.
            _now: Override current time.

        Returns:
            The CompletedCase record.
        """
        now = _now or datetime.now(timezone.utc)
        case = CompletedCase(
            case_id=case_id,
            domain=domain,
            original_outcome=original_outcome.lower(),
            validator_votes={k: v.lower() for k, v in validator_votes.items()},
            submission_hash=submission_hash,
            producer_id=producer_id,
            finalized_at=now.isoformat(),
            metadata=metadata or {},
        )
        self._cases[case_id] = case

        # Update validator profiles
        for vid, vote in case.validator_votes.items():
            profile = self._get_profile(vid)
            if vote == "approve":
                profile.approve_count += 1
            else:
                profile.reject_count += 1

        return case

    def _get_profile(self, validator_id: str) -> ValidatorProfile:
        if validator_id not in self._profiles:
            self._profiles[validator_id] = ValidatorProfile(validator_id=validator_id)
        return self._profiles[validator_id]

    # ── Sampling ─────────────────────────────────────────────────────────

    def sample_cases(self, *, _seed: str = "") -> list[str]:
        """Select cases for spot-checking based on the sample rate.

        Uses deterministic sampling when a seed is provided (for reproducibility).

        Returns:
            List of case IDs selected for spot-checking.
        """
        eligible = [c for c in self._cases.values() if not c.spot_checked]
        if not eligible:
            return []

        seed = _seed or self.policy.seed or secrets.token_hex(16)
        seed_bytes = seed.encode()

        selected: list[str] = []
        for case in eligible:
            # Deterministic per-case selection using HMAC
            h = hashlib.new(
                "sha256",
                seed_bytes + case.case_id.encode(),
            ).hexdigest()
            # Convert first 8 hex chars to a float in [0, 1)
            threshold = int(h[:8], 16) / 0xFFFFFFFF
            if threshold < self.policy.sample_rate:
                selected.append(case.case_id)

        return sorted(selected)

    # ── Spot-check execution ─────────────────────────────────────────────

    def run_spot_check(
        self,
        check_fn: Callable[[str, str], str],
        *,
        case_ids: list[str] | None = None,
        checker_id: str = "spot-check-system",
        _seed: str = "",
        _now: datetime | None = None,
    ) -> list[SpotCheckResult]:
        """Run spot-checks on sampled (or specified) cases.

        Args:
            check_fn: Re-validation function. Takes (case_id, submission_hash)
                and returns "approve" or "reject".
            case_ids: Specific cases to check (overrides sampling).
            checker_id: Identifier for the checking process.
            _seed: Override sampling seed.
            _now: Override current time.

        Returns:
            List of SpotCheckResult for each checked case.
        """
        now = _now or datetime.now(timezone.utc)

        if case_ids is None:
            case_ids = self.sample_cases(_seed=_seed)

        results: list[SpotCheckResult] = []
        for cid in case_ids:
            case = self._cases.get(cid)
            if case is None or case.spot_checked:
                continue

            # Run re-validation
            spot_outcome = check_fn(cid, case.submission_hash).lower()
            # Normalize: "approve"↔"approved", "reject"↔"rejected"
            _normalize = {"approved": "approve", "rejected": "reject"}
            agrees = _normalize.get(spot_outcome, spot_outcome) == _normalize.get(
                case.original_outcome, case.original_outcome
            )

            # Assess each validator
            assessments = self._assess_validators(case, spot_outcome)

            result = SpotCheckResult(
                case_id=cid,
                domain=case.domain,
                original_outcome=case.original_outcome,
                spot_check_outcome=spot_outcome,
                agrees_with_original=agrees,
                validator_assessments=assessments,
                checked_at=now.isoformat(),
                checker_id=checker_id,
            )
            results.append(result)
            self._results.append(result)
            case.spot_checked = True

            # Update profiles
            for assessment in assessments:
                profile = self._get_profile(assessment.validator_id)
                if assessment.agreed_with_spot_check:
                    profile.spot_check_correct += 1
                else:
                    profile.spot_check_wrong += 1
                if assessment.assessment == "correct_dissent":
                    profile.correct_dissents += 1
                elif assessment.assessment == "lazy_agree":
                    profile.lazy_flags += 1

        return results

    def _assess_validators(
        self,
        case: CompletedCase,
        spot_outcome: str,
    ) -> list[ValidatorAssessment]:
        """Assess each validator's vote against the spot-check outcome."""
        # Map outcomes to vote equivalents
        outcome_to_vote = {"approved": "approve", "rejected": "reject"}
        original_vote_equiv = outcome_to_vote.get(case.original_outcome, case.original_outcome)

        assessments: list[ValidatorAssessment] = []
        pol = self.policy

        for vid, vote in case.validator_votes.items():
            agreed_with_majority = vote == original_vote_equiv
            agreed_with_spot = vote == spot_outcome

            if agreed_with_spot:
                if agreed_with_majority:
                    # Correct and agreed with majority — normal correct vote
                    assessment = "correct"
                    delta = pol.correct_reward
                else:
                    # Correct but disagreed with majority — correct dissent!
                    # This is the key incentive: rewarding validators who
                    # did genuine review and caught what others missed
                    assessment = "correct_dissent"
                    delta = pol.correct_dissent_bonus
            else:
                if agreed_with_majority:
                    # Wrong and agreed with majority — lazy rubber-stamp
                    assessment = "lazy_agree"
                    delta = -pol.lazy_penalty
                else:
                    # Wrong and disagreed with majority — wrong dissent
                    assessment = "wrong_dissent"
                    delta = -pol.wrong_dissent_penalty

            assessments.append(
                ValidatorAssessment(
                    validator_id=vid,
                    vote=vote,
                    agreed_with_majority=agreed_with_majority,
                    agreed_with_spot_check=agreed_with_spot,
                    assessment=assessment,
                    trust_delta=delta,
                )
            )

        return assessments

    # ── Trust adjustments ────────────────────────────────────────────────

    def compute_adjustments(
        self,
        results: list[SpotCheckResult] | None = None,
    ) -> list[TrustAdjustment]:
        """Compute per-validator trust adjustments from spot-check results.

        Args:
            results: Results to process (defaults to all unprocessed results).

        Returns:
            List of TrustAdjustment, one per validator that appeared in results.
        """
        target_results = results if results is not None else self._results

        # Aggregate per-validator
        agg: dict[str, dict[str, Any]] = {}

        for result in target_results:
            for va in result.validator_assessments:
                key = va.validator_id
                if key not in agg:
                    agg[key] = {
                        "domain": result.domain,
                        "delta": 0.0,
                        "cases": 0,
                        "correct": 0,
                        "lazy": 0,
                        "dissent_bonus": 0,
                        "assessments": [],
                    }
                entry = agg[key]
                entry["delta"] += va.trust_delta
                entry["cases"] += 1
                entry["assessments"].append(va.assessment)
                if va.agreed_with_spot_check:
                    entry["correct"] += 1
                if va.assessment == "lazy_agree":
                    entry["lazy"] += 1
                if va.assessment == "correct_dissent":
                    entry["dissent_bonus"] += 1

        return [
            TrustAdjustment(
                validator_id=vid,
                domain=data["domain"],
                delta=round(data["delta"], 6),
                cases_checked=data["cases"],
                correct_count=data["correct"],
                lazy_count=data["lazy"],
                dissent_bonus_count=data["dissent_bonus"],
                assessments=data["assessments"],
            )
            for vid, data in sorted(agg.items())
        ]

    def apply_adjustments(
        self,
        trust_manager: Any,
        adjustments: list[TrustAdjustment],
        *,
        _now: datetime | None = None,
    ) -> int:
        """Apply trust adjustments to a TrustScoreManager.

        Args:
            trust_manager: A :class:`TrustScoreManager` instance.
            adjustments: Adjustments from :meth:`compute_adjustments`.
            _now: Override current time.

        Returns:
            Number of adjustments applied.
        """
        now = _now or datetime.now(timezone.utc)
        applied = 0

        for adj in adjustments:
            if abs(adj.delta) < 1e-10:
                continue

            compliant = adj.delta > 0
            severity = "low"  # spot-check adjustments are always "low" severity
            note = (
                f"Spot-check: {adj.cases_checked} cases, "
                f"{adj.correct_count} correct, {adj.lazy_count} lazy, "
                f"{adj.dissent_bonus_count} correct dissents"
            )

            trust_manager.record_decision(
                adj.validator_id,
                compliant=compliant,
                severity=severity,
                note=note,
                domain=adj.domain,
                _now=now,
            )
            applied += 1

        return applied

    # ── Bias detection ───────────────────────────────────────────────────

    def biased_validators(self) -> list[dict[str, Any]]:
        """Return validators showing systematic voting bias.

        Returns:
            List of dicts with validator_id, bias_direction, approve_rate,
            total_votes for each biased validator.
        """
        result: list[dict[str, Any]] = []
        for profile in self._profiles.values():
            if profile.has_bias(self.policy.bias_threshold, self.policy.min_cases_for_bias):
                result.append(
                    {
                        "validator_id": profile.validator_id,
                        "bias_direction": profile.bias_direction,
                        "approve_rate": round(profile.approve_rate, 4),
                        "reject_rate": round(profile.reject_rate, 4),
                        "total_votes": profile.total_votes,
                        "lazy_flags": profile.lazy_flags,
                    }
                )
        return sorted(result, key=lambda x: x["validator_id"])

    # ── Queries ──────────────────────────────────────────────────────────

    def profile(self, validator_id: str) -> ValidatorProfile | None:
        """Return the voting profile for a validator."""
        return self._profiles.get(validator_id)

    def profiles(self) -> list[ValidatorProfile]:
        """Return all validator profiles."""
        return sorted(self._profiles.values(), key=lambda p: p.validator_id)

    def results(self) -> list[SpotCheckResult]:
        """Return all spot-check results."""
        return list(self._results)

    def unchecked_count(self) -> int:
        """Return number of cases not yet spot-checked."""
        return sum(1 for c in self._cases.values() if not c.spot_checked)

    def summary(self) -> dict[str, Any]:
        """Return aggregate spot-check audit summary."""
        total_checks = len(self._results)
        agreements = sum(1 for r in self._results if r.agrees_with_original)
        disagreements = total_checks - agreements

        total_assessments = sum(len(r.validator_assessments) for r in self._results)
        lazy_count = sum(
            1
            for r in self._results
            for va in r.validator_assessments
            if va.assessment == "lazy_agree"
        )
        dissent_count = sum(
            1
            for r in self._results
            for va in r.validator_assessments
            if va.assessment == "correct_dissent"
        )

        return {
            "total_cases_registered": len(self._cases),
            "total_spot_checks": total_checks,
            "agreements": agreements,
            "disagreements": disagreements,
            "agreement_rate": round(agreements / total_checks, 4) if total_checks else 0.0,
            "unchecked_count": self.unchecked_count(),
            "total_validator_assessments": total_assessments,
            "lazy_validations_detected": lazy_count,
            "correct_dissents_rewarded": dissent_count,
            "biased_validators": len(self.biased_validators()),
            "sample_rate": self.policy.sample_rate,
        }

    def __repr__(self) -> str:
        checked = len(self._results)
        total = len(self._cases)
        return f"SpotCheckAuditor({total} cases, {checked} checked)"
