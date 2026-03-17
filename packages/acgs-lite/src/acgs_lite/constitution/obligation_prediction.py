"""exp233: Probabilistic Obligation Tracking — Markov chain breach prediction.

Extends the basic ObligationEngine (exp229) with *predictive analytics*: models
obligation state transitions as a Discrete-Time Markov Chain (DTMC), then uses
matrix exponentiation to predict the probability of breach within N future steps.
Proactive warnings are emitted before actual breaches occur.

Motivation (from Pro2Guard arXiv:2508.00500):

> Reactive obligation tracking only detects breaches *after* they happen.
> By modeling obligation lifecycle as a Markov chain with learned transition
> probabilities, we can predict which obligations are *likely to breach*
> and surface early warnings while remediation is still possible.

Design
------
- **ObligationState** — 5 states: PENDING, FULFILLED, BREACHED, WAIVED, EXPIRED.
  FULFILLED/BREACHED/WAIVED/EXPIRED are absorbing (terminal).
- **TransitionModel** — maintains transition counts and computes a row-stochastic
  transition matrix.  Supports both learned (from observations) and prior
  (manually specified) probabilities.
- **BreachPrediction** — predicted breach probability, expected steps to
  resolution, and current state for a single obligation.
- **ObligationPredictor** — the main API: ``observe()`` transitions, ``predict()``
  breach risk for a given state, ``scan()`` a portfolio of obligations for
  proactive warnings, ``matrix()`` for inspection.

Matrix exponentiation: P^N is computed by repeated squaring for efficiency
(O(S^3 log N) where S=5 states), though for S=5 direct multiplication is fine.

Zero hot-path overhead — purely additive; the core engine is never touched.

Usage::

    from acgs_lite.constitution.obligation_prediction import (
        ObligationPredictor, ObligationState,
    )

    pred = ObligationPredictor()

    # Learn from historical obligation outcomes
    for _ in range(70): pred.observe("pending", "fulfilled")
    for _ in range(15): pred.observe("pending", "breached")
    for _ in range(10): pred.observe("pending", "waived")
    for _ in range(5):  pred.observe("pending", "expired")

    # Predict breach risk for a pending obligation
    risk = pred.predict("pending", lookahead=10)
    print(risk.breach_probability)   # ~0.15
    print(risk.should_warn)          # depends on threshold

    # Scan a portfolio
    warnings = pred.scan(["pending", "pending", "fulfilled"])
    print(len(warnings))  # 2 (only pending ones get predictions)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ObligationState(str, Enum):
    """Obligation lifecycle states for the Markov chain model."""

    PENDING = "pending"
    FULFILLED = "fulfilled"
    BREACHED = "breached"
    WAIVED = "waived"
    EXPIRED = "expired"


_STATES: tuple[str, ...] = tuple(s.value for s in ObligationState)
_STATE_IDX: dict[str, int] = {s: i for i, s in enumerate(_STATES)}
_NUM_STATES: int = len(_STATES)
_ABSORBING: frozenset[str] = frozenset({"fulfilled", "breached", "waived", "expired"})


@dataclass(frozen=True, slots=True)
class BreachPrediction:
    """Predicted breach outcome for a single obligation."""

    current_state: str
    breach_probability: float
    fulfilled_probability: float
    steps_lookahead: int
    should_warn: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_state": self.current_state,
            "breach_probability": round(self.breach_probability, 6),
            "fulfilled_probability": round(self.fulfilled_probability, 6),
            "steps_lookahead": self.steps_lookahead,
            "should_warn": self.should_warn,
        }


@dataclass(frozen=True, slots=True)
class PortfolioRisk:
    """Aggregate risk assessment across a portfolio of obligations."""

    total_obligations: int
    pending_count: int
    predictions: tuple[BreachPrediction, ...]
    avg_breach_probability: float
    max_breach_probability: float
    warnings_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_obligations": self.total_obligations,
            "pending_count": self.pending_count,
            "avg_breach_probability": round(self.avg_breach_probability, 6),
            "max_breach_probability": round(self.max_breach_probability, 6),
            "warnings_count": self.warnings_count,
            "predictions": [p.to_dict() for p in self.predictions],
        }


# ── matrix operations ─────────────────────────────────────────────────────────


def _identity(n: int) -> list[list[float]]:
    """NxN identity matrix."""
    return [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]


def _mat_mul(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    """Multiply two square matrices."""
    n = len(a)
    result = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for k in range(n):
            a_ik = a[i][k]
            if a_ik == 0.0:
                continue
            for j in range(n):
                result[i][j] += a_ik * b[k][j]
    return result


def _mat_pow(m: list[list[float]], power: int) -> list[list[float]]:
    """Matrix exponentiation by repeated squaring: M^power."""
    n = len(m)
    if power == 0:
        return _identity(n)
    if power == 1:
        return [row[:] for row in m]

    result = _identity(n)
    base = [row[:] for row in m]

    while power > 0:
        if power & 1:
            result = _mat_mul(result, base)
        base = _mat_mul(base, base)
        power >>= 1

    return result


# ── predictor ─────────────────────────────────────────────────────────────────


class ObligationPredictor:
    """Markov chain model for obligation breach prediction.

    Learns transition probabilities from observed state changes, then predicts
    the probability of reaching the BREACHED state within N future steps via
    matrix exponentiation.

    Attributes:
        warn_threshold: Breach probability (0–1) at which ``should_warn`` is
            set on predictions (default 0.1 = 10%).
        default_lookahead: Default number of steps for prediction (default 10).
    """

    __slots__ = ("warn_threshold", "default_lookahead", "_counts", "_total_from")

    def __init__(
        self,
        *,
        warn_threshold: float = 0.1,
        default_lookahead: int = 10,
    ) -> None:
        self.warn_threshold = max(0.0, min(1.0, warn_threshold))
        self.default_lookahead = max(1, default_lookahead)
        # _counts[(from_idx, to_idx)] -> observed transition count
        self._counts: dict[tuple[int, int], int] = {}
        # _total_from[from_idx] -> total transitions from that state
        self._total_from: dict[int, int] = {}

    def observe(self, from_state: str, to_state: str) -> None:
        """Record an observed state transition.

        Absorbing states (fulfilled, breached, waived, expired) self-loop
        with probability 1.0 and cannot transition elsewhere, so only
        transitions *from* PENDING are meaningful.  Other transitions are
        silently recorded but won't affect absorbing-state rows.
        """
        fi = _STATE_IDX.get(from_state)
        ti = _STATE_IDX.get(to_state)
        if fi is None or ti is None:
            return
        key = (fi, ti)
        self._counts[key] = self._counts.get(key, 0) + 1
        self._total_from[fi] = self._total_from.get(fi, 0) + 1

    def observe_batch(self, transitions: list[tuple[str, str]]) -> None:
        """Record multiple transitions at once."""
        for from_s, to_s in transitions:
            self.observe(from_s, to_s)

    def matrix(self) -> list[list[float]]:
        """Return the current row-stochastic transition matrix.

        Absorbing states have self-loops (P[s][s] = 1.0).
        States with no observed transitions get uniform distribution over
        non-self targets (Laplace smoothing).
        """
        m: list[list[float]] = [[0.0] * _NUM_STATES for _ in range(_NUM_STATES)]

        for i, state in enumerate(_STATES):
            if state in _ABSORBING:
                m[i][i] = 1.0
                continue

            total = self._total_from.get(i, 0)
            if total == 0:
                # No observations — uniform prior (equal chance of any target)
                p = 1.0 / _NUM_STATES
                for j in range(_NUM_STATES):
                    m[i][j] = p
            else:
                for j in range(_NUM_STATES):
                    count = self._counts.get((i, j), 0)
                    m[i][j] = count / total

        return m

    def predict(
        self,
        current_state: str,
        lookahead: int | None = None,
    ) -> BreachPrediction:
        """Predict breach probability for an obligation in ``current_state``.

        Computes P^N[current_state, BREACHED] via matrix exponentiation.

        Args:
            current_state: Current obligation state.
            lookahead: Number of future steps to simulate.

        Returns:
            BreachPrediction with breach/fulfilled probabilities and warning.
        """
        steps = lookahead if lookahead is not None else self.default_lookahead
        si = _STATE_IDX.get(current_state)

        if si is None or current_state in _ABSORBING:
            is_breached = current_state == "breached"
            is_fulfilled = current_state == "fulfilled"
            return BreachPrediction(
                current_state=current_state,
                breach_probability=1.0 if is_breached else 0.0,
                fulfilled_probability=1.0 if is_fulfilled else 0.0,
                steps_lookahead=steps,
                should_warn=is_breached,
            )

        p_n = _mat_pow(self.matrix(), steps)
        breach_idx = _STATE_IDX["breached"]
        fulfilled_idx = _STATE_IDX["fulfilled"]
        bp = p_n[si][breach_idx]
        fp = p_n[si][fulfilled_idx]

        return BreachPrediction(
            current_state=current_state,
            breach_probability=bp,
            fulfilled_probability=fp,
            steps_lookahead=steps,
            should_warn=bp >= self.warn_threshold,
        )

    def scan(
        self,
        obligation_states: list[str],
        lookahead: int | None = None,
    ) -> PortfolioRisk:
        """Scan a portfolio of obligations and return aggregate risk.

        Args:
            obligation_states: List of current states for each obligation.
            lookahead: Steps to look ahead (uses default if None).

        Returns:
            PortfolioRisk with per-obligation predictions and aggregate metrics.
        """
        steps = lookahead if lookahead is not None else self.default_lookahead
        predictions: list[BreachPrediction] = []
        pending_count = 0

        for state in obligation_states:
            if state == "pending":
                pending_count += 1
            pred = self.predict(state, steps)
            predictions.append(pred)

        bps = [p.breach_probability for p in predictions if p.current_state == "pending"]
        avg_bp = sum(bps) / len(bps) if bps else 0.0
        max_bp = max(bps) if bps else 0.0
        warn_count = sum(1 for p in predictions if p.should_warn)

        return PortfolioRisk(
            total_obligations=len(obligation_states),
            pending_count=pending_count,
            predictions=tuple(predictions),
            avg_breach_probability=avg_bp,
            max_breach_probability=max_bp,
            warnings_count=warn_count,
        )

    def observation_count(self) -> int:
        """Total number of observed transitions."""
        return sum(self._total_from.values())

    def summary(self) -> dict[str, Any]:
        """Summary of model state."""
        m = self.matrix()
        pending_idx = _STATE_IDX["pending"]
        return {
            "observations": self.observation_count(),
            "warn_threshold": self.warn_threshold,
            "default_lookahead": self.default_lookahead,
            "pending_transition_probs": {
                _STATES[j]: round(m[pending_idx][j], 4) for j in range(_NUM_STATES)
            },
        }

    def reset(self) -> None:
        """Clear all observed transitions."""
        self._counts.clear()
        self._total_from.clear()
