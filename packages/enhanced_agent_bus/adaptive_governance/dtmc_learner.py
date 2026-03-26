"""
Pro2Guard-inspired Discrete-Time Markov Chain (DTMC) trajectory risk scorer.

Learns a 5x5 transition probability matrix from labelled execution trajectories
produced by TraceCollector. At runtime, predicts P(unsafe terminal | current
trajectory prefix) using a k-step forward-projection algorithm, enabling
proactive intervention before governance violations occur.

Key properties
--------------
- **PAC-correctness** (Pro2Guard §4): Laplace smoothing ensures no zero
  transition probabilities; the learned matrix is a proper stochastic matrix.
- **O(k·n²) per prediction** where k=lookahead_steps, n=N_STATES=5 -- well
  within the <1 ms P99 budget.
- **Online updates** via ``update_online()`` -- no full refit needed for
  incremental learning.
- **No external deps beyond numpy** -- scipy is not required.

Usage::

    learner = DTMCLearner()
    learner.fit(records)           # from TraceCollector
    risk = learner.predict_risk([0, 1, 2])  # current prefix
    if learner.should_intervene([0, 1, 2]):
        trigger_hitl()

Constitutional Hash: 608508a9bd224290
NIST 800-53 SI-3, AC-6 -- Integrity, Least Privilege
Reference: Pro2Guard (Wang/Poskitt/Sun, Aug 2025)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from enhanced_agent_bus.observability.structured_logging import get_logger

from .trace_collector import N_STATES, TrajectoryRecord

logger = get_logger(__name__)
# ---------------------------------------------------------------------------
# Module-level defaults (aligned with ACGS governance thresholds)
# ---------------------------------------------------------------------------

#: P(unsafe) threshold above which proactive intervention fires.
#: Calibrated to match the HITL trigger at impact_score >= 0.8 (CLAUDE.md).
_DEFAULT_INTERVENTION_THRESHOLD: float = 0.8

#: Steps to project forward when computing risk from current prefix.
_DEFAULT_LOOKAHEAD: int = 5

#: Laplace smoothing count applied to transition count matrix.
#: Ensures no zero probabilities (PAC-correctness requirement).
_LAPLACE_ALPHA: float = 1.0


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DTMCFitResult:
    """Summary statistics returned by :meth:`DTMCLearner.fit`.

    Attributes:
        n_trajectories: Number of TrajectoryRecord instances used for fitting.
        n_transitions: Total (from, to) state-transition pairs observed.
        n_states: Dimensionality of the state space.
        unsafe_fraction: Fraction of trajectories labelled terminal_unsafe=True.
        terminal_unsafe_probs: Per-state P(unsafe terminal | last_state=i), len=n_states.
        message: Human-readable status ("ok" | "no_data").
    """

    n_trajectories: int
    n_transitions: int
    n_states: int
    unsafe_fraction: float
    terminal_unsafe_probs: list[float]
    message: str


# ---------------------------------------------------------------------------
# DTMC Learner
# ---------------------------------------------------------------------------


class DTMCLearner:
    """Maximum-likelihood DTMC estimator with proactive risk prediction.

    State space mirrors ImpactLevel ordinals::

        0=NEGLIGIBLE  1=LOW  2=MEDIUM  3=HIGH  4=CRITICAL

    The model maintains two learned parameter arrays:

    * ``transition_matrix[i, j]``: P(next_state=j | current_state=i).
      Shape (N_STATES, N_STATES), rows sum to 1.0.
    * ``terminal_unsafe_probs[i]``: P(unsafe terminal | last_state=i).
      Shape (N_STATES,), values in [0, 1].

    Prediction algorithm (``predict_risk``):

    1. Start with a point-mass distribution at ``current_prefix[-1]``.
    2. Project forward ``lookahead_steps`` steps by repeated matrix
       multiplication: ``dist = dist @ P``.
    3. Return ``dot(dist, terminal_unsafe_probs)`` as the scalar risk estimate.

    Args:
        n_states: Dimensionality of state space (default 5).
        intervention_threshold: P(unsafe) above which ``should_intervene``
            returns True (default 0.8, matching HITL trigger).
        lookahead_steps: Forward-projection horizon for risk estimation.
        laplace_alpha: Pseudocount added to each cell of the transition count
            matrix before normalisation (prevents zero probabilities).
    """

    def __init__(
        self,
        n_states: int = N_STATES,
        intervention_threshold: float = _DEFAULT_INTERVENTION_THRESHOLD,
        lookahead_steps: int = _DEFAULT_LOOKAHEAD,
        laplace_alpha: float = _LAPLACE_ALPHA,
    ) -> None:
        self.n_states = n_states
        self.intervention_threshold = intervention_threshold
        self.lookahead_steps = lookahead_steps
        self.laplace_alpha = laplace_alpha

        # Learned parameters -- initialised to uniform prior
        self.transition_matrix: np.ndarray = np.full(
            (n_states, n_states), 1.0 / n_states, dtype=np.float64
        )
        self.terminal_unsafe_probs: np.ndarray = np.zeros(n_states, dtype=np.float64)

        # Running counts for incremental online updates
        self._transition_counts: np.ndarray = np.full(
            (n_states, n_states), laplace_alpha, dtype=np.float64
        )
        # _terminal_counts[s, 0] = safe endings at state s
        # _terminal_counts[s, 1] = unsafe endings at state s
        self._terminal_counts: np.ndarray = np.zeros((n_states, 2), dtype=np.float64)

        self.is_fitted: bool = False
        self._n_trajectories: int = 0
        self._n_transitions: int = 0

    # ------------------------------------------------------------------
    # Fitting
    # ------------------------------------------------------------------

    def fit(self, trajectories: list[TrajectoryRecord]) -> DTMCFitResult:
        """Estimate DTMC parameters from a batch of labelled trajectories.

        Uses maximum-likelihood estimation with Laplace smoothing.  Calling
        ``fit()`` resets internal counts and re-learns from scratch.  For
        incremental updates use :meth:`update_online` instead.

        Args:
            trajectories: Labelled trajectory records from :class:`TraceCollector`.

        Returns:
            :class:`DTMCFitResult` with fit statistics.
        """
        if not trajectories:
            logger.warning(
                "DTMCLearner.fit() called with empty trajectory list; parameters unchanged."
            )
            return DTMCFitResult(
                n_trajectories=0,
                n_transitions=0,
                n_states=self.n_states,
                unsafe_fraction=0.0,
                terminal_unsafe_probs=[0.0] * self.n_states,
                message="no_data",
            )

        # Reset counts with Laplace smoothing prior
        counts = np.full((self.n_states, self.n_states), self.laplace_alpha, dtype=np.float64)
        term_counts = np.zeros((self.n_states, 2), dtype=np.float64)

        n_trans = 0
        n_unsafe = 0

        for traj in trajectories:
            states = traj.states

            # Count consecutive (from, to) transition pairs
            for t in range(len(states) - 1):
                s_from, s_to = states[t], states[t + 1]
                counts[s_from, s_to] += 1.0
                n_trans += 1

            # Terminal label for last state
            last_state = states[-1]
            if traj.terminal_unsafe:
                term_counts[last_state, 1] += 1.0
                n_unsafe += 1
            else:
                term_counts[last_state, 0] += 1.0

        # Normalise rows → proper stochastic matrix
        row_sums = counts.sum(axis=1, keepdims=True)
        self.transition_matrix = counts / row_sums

        # Terminal unsafe probability per state
        total_term = term_counts.sum(axis=1) + 1e-9  # guard div-by-zero
        self.terminal_unsafe_probs = term_counts[:, 1] / total_term

        # Persist counts for future online updates
        self._transition_counts = counts.copy()
        self._terminal_counts = term_counts.copy()

        self.is_fitted = True
        self._n_trajectories = len(trajectories)
        self._n_transitions = n_trans

        unsafe_fraction = n_unsafe / len(trajectories)
        logger.info(
            "DTMCLearner fitted: %d trajectories, %d transitions, unsafe_fraction=%.3f",
            len(trajectories),
            n_trans,
            unsafe_fraction,
        )
        return DTMCFitResult(
            n_trajectories=len(trajectories),
            n_transitions=n_trans,
            n_states=self.n_states,
            unsafe_fraction=unsafe_fraction,
            terminal_unsafe_probs=self.terminal_unsafe_probs.tolist(),
            message="ok",
        )

    def update_online(self, trajectory: TrajectoryRecord) -> None:
        """Incrementally update DTMC parameters with a single new trajectory.

        Adds new transition counts to the running totals and re-normalises
        the transition matrix.  No full refit is required -- suitable for
        continuous online learning as new sessions complete.

        Args:
            trajectory: A single labelled trajectory from the current session.
        """
        states = trajectory.states

        for t in range(len(states) - 1):
            self._transition_counts[states[t], states[t + 1]] += 1.0

        last_state = states[-1]
        if trajectory.terminal_unsafe:
            self._terminal_counts[last_state, 1] += 1.0
        else:
            self._terminal_counts[last_state, 0] += 1.0

        # Re-normalise
        row_sums = self._transition_counts.sum(axis=1, keepdims=True)
        self.transition_matrix = self._transition_counts / row_sums

        total_term = self._terminal_counts.sum(axis=1) + 1e-9
        self.terminal_unsafe_probs = self._terminal_counts[:, 1] / total_term

        self.is_fitted = True
        self._n_trajectories += 1
        self._n_transitions += max(0, len(states) - 1)

    # ------------------------------------------------------------------
    # Prediction
    # ------------------------------------------------------------------

    def predict_risk(self, current_prefix: list[int]) -> float:
        """Compute P(unsafe terminal | current trajectory prefix).

        Algorithm:

        1. Start with a point-mass probability distribution at the last
           observed state: ``dist[last_state] = 1.0``.
        2. Project forward ``lookahead_steps`` steps via repeated matrix
           multiplication: ``dist = dist @ transition_matrix``.
        3. Return ``dot(dist, terminal_unsafe_probs)`` clipped to [0, 1].

        The result is an estimate of the probability that the current session
        will ultimately reach an unsafe terminal state given the trajectory
        observed so far.

        Args:
            current_prefix: List of ImpactLevel ordinal values (0-4) observed
                so far in the current session.  Must be non-empty.

        Returns:
            float in [0.0, 1.0] -- higher means more likely unsafe outcome.

        Raises:
            ValueError: If any state in ``current_prefix`` is out of range.
        """
        if not current_prefix:
            return 0.0

        last_state = current_prefix[-1]
        if not (0 <= last_state < self.n_states):
            raise ValueError(f"State {last_state!r} out of range [0, {self.n_states - 1}]")

        # Point-mass distribution at last observed state
        state_dist = np.zeros(self.n_states, dtype=np.float64)
        state_dist[last_state] = 1.0

        # Forward projection
        P = self.transition_matrix
        for _ in range(self.lookahead_steps):
            state_dist = state_dist @ P

        risk = float(np.dot(state_dist, self.terminal_unsafe_probs))
        return float(np.clip(risk, 0.0, 1.0))

    def should_intervene(
        self,
        current_prefix: list[int],
        threshold: float | None = None,
    ) -> bool:
        """Return True if trajectory risk meets or exceeds the intervention threshold.

        Args:
            current_prefix: Observed trajectory prefix (ImpactLevel ordinals).
            threshold: Override the instance-level ``intervention_threshold``.
                If None, uses ``self.intervention_threshold``.

        Returns:
            True if ``predict_risk(current_prefix) >= threshold``.
        """
        thr = threshold if threshold is not None else self.intervention_threshold
        return self.predict_risk(current_prefix) >= thr

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def stationary_distribution(self, n_iterations: int = 200) -> np.ndarray:
        """Compute the stationary distribution via power iteration.

        Runs ``n_iterations`` steps of the power method starting from a
        uniform initial distribution.  Converges quickly for ergodic chains.

        Args:
            n_iterations: Number of power-iteration steps.

        Returns:
            np.ndarray of shape (n_states,) summing to 1.0.  Entry i is the
            long-run fraction of time spent in state i.
        """
        dist = np.full(self.n_states, 1.0 / self.n_states, dtype=np.float64)
        P = self.transition_matrix
        for _ in range(n_iterations):
            dist = dist @ P
        return dist

    def risk_vector(self) -> np.ndarray:
        """Return per-state risk after ``lookahead_steps`` forward projection.

        Equivalent to ``predict_risk([s])`` for each state s independently.
        Useful for diagnostics and threshold calibration.

        Returns:
            np.ndarray of shape (n_states,) with risk values in [0, 1].
        """
        P_k = np.linalg.matrix_power(self.transition_matrix, self.lookahead_steps)
        return np.clip(P_k @ self.terminal_unsafe_probs, 0.0, 1.0)  # type: ignore[no-any-return]
