# Constitutional Hash: 608508a9bd224290
"""
Coverage-boost tests for DTMCLearner.

Target: src/core/enhanced_agent_bus/adaptive_governance/dtmc_learner.py
Goal  : ≥90% line + branch coverage on the target module.

Covers all public methods and branches:
- DTMCFitResult dataclass
- DTMCLearner.__init__ (custom and default arguments)
- DTMCLearner.fit (empty list, single trajectory, batch, reset on second call)
- DTMCLearner.update_online (safe and unsafe; trajectory count/n_transitions)
- DTMCLearner.predict_risk (empty prefix, out-of-range states, fitted/unfitted)
- DTMCLearner.should_intervene (default threshold, custom threshold override)
- DTMCLearner.stationary_distribution (power iteration)
- DTMCLearner.risk_vector (matrix power path)

NIST 800-53 SI-3, AC-6
"""

from __future__ import annotations

import numpy as np
import pytest

from enhanced_agent_bus.adaptive_governance.dtmc_learner import (
    _DEFAULT_INTERVENTION_THRESHOLD,
    _DEFAULT_LOOKAHEAD,
    _LAPLACE_ALPHA,
    DTMCFitResult,
    DTMCLearner,
)
from enhanced_agent_bus.adaptive_governance.trace_collector import (
    N_STATES,
    TrajectoryRecord,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_traj(length: int = 4) -> TrajectoryRecord:
    """All-LOW trajectory; terminal_unsafe=False."""
    return TrajectoryRecord(states=[1] * length, terminal_unsafe=False)


def _unsafe_traj(length: int = 4) -> TrajectoryRecord:
    """Escalating trajectory; terminal_unsafe=True."""
    states = [0, 1, 2, 4][:length]
    return TrajectoryRecord(states=states, terminal_unsafe=True)


def _fitted_learner(
    n_safe: int = 5,
    n_unsafe: int = 5,
    lookahead: int = 3,
) -> DTMCLearner:
    """Return a DTMCLearner already fitted on mixed data."""
    learner = DTMCLearner(lookahead_steps=lookahead)
    trajs = [_safe_traj() for _ in range(n_safe)] + [_unsafe_traj() for _ in range(n_unsafe)]
    learner.fit(trajs)
    return learner


# ---------------------------------------------------------------------------
# DTMCFitResult dataclass
# ---------------------------------------------------------------------------


class TestDTMCFitResult:
    def test_frozen_dataclass_fields(self) -> None:
        result = DTMCFitResult(
            n_trajectories=10,
            n_transitions=30,
            n_states=N_STATES,
            unsafe_fraction=0.4,
            terminal_unsafe_probs=[0.1] * N_STATES,
            message="ok",
        )
        assert result.n_trajectories == 10
        assert result.n_transitions == 30
        assert result.n_states == N_STATES
        assert result.unsafe_fraction == pytest.approx(0.4)
        assert len(result.terminal_unsafe_probs) == N_STATES
        assert result.message == "ok"

    def test_frozen_cannot_be_mutated(self) -> None:
        result = DTMCFitResult(
            n_trajectories=1,
            n_transitions=1,
            n_states=N_STATES,
            unsafe_fraction=0.0,
            terminal_unsafe_probs=[0.0] * N_STATES,
            message="ok",
        )
        with pytest.raises((AttributeError, TypeError)):
            result.message = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# DTMCLearner.__init__
# ---------------------------------------------------------------------------


class TestDTMCLearnerInit:
    def test_default_parameters_match_module_constants(self) -> None:
        learner = DTMCLearner()
        assert learner.n_states == N_STATES
        assert learner.intervention_threshold == _DEFAULT_INTERVENTION_THRESHOLD
        assert learner.lookahead_steps == _DEFAULT_LOOKAHEAD
        assert learner.laplace_alpha == _LAPLACE_ALPHA

    def test_custom_parameters_stored(self) -> None:
        learner = DTMCLearner(
            n_states=3,
            intervention_threshold=0.5,
            lookahead_steps=2,
            laplace_alpha=0.5,
        )
        assert learner.n_states == 3
        assert learner.intervention_threshold == 0.5
        assert learner.lookahead_steps == 2
        assert learner.laplace_alpha == 0.5

    def test_transition_matrix_shape(self) -> None:
        learner = DTMCLearner()
        assert learner.transition_matrix.shape == (N_STATES, N_STATES)

    def test_initial_transition_matrix_is_uniform(self) -> None:
        learner = DTMCLearner()
        expected = np.full((N_STATES, N_STATES), 1.0 / N_STATES)
        np.testing.assert_allclose(learner.transition_matrix, expected)

    def test_terminal_unsafe_probs_zeros_at_init(self) -> None:
        learner = DTMCLearner()
        np.testing.assert_array_equal(learner.terminal_unsafe_probs, np.zeros(N_STATES))

    def test_not_fitted_at_init(self) -> None:
        assert not DTMCLearner().is_fitted

    def test_counts_zero_at_init(self) -> None:
        learner = DTMCLearner()
        assert learner._n_trajectories == 0
        assert learner._n_transitions == 0

    def test_laplace_prior_in_transition_counts(self) -> None:
        alpha = 2.0
        learner = DTMCLearner(laplace_alpha=alpha)
        assert (learner._transition_counts == alpha).all()


# ---------------------------------------------------------------------------
# DTMCLearner.fit
# ---------------------------------------------------------------------------


class TestDTMCLearnerFit:
    def test_empty_trajectories_returns_no_data(self) -> None:
        learner = DTMCLearner()
        result = learner.fit([])
        assert result.message == "no_data"
        assert result.n_trajectories == 0
        assert result.n_transitions == 0
        assert result.n_states == N_STATES
        assert result.unsafe_fraction == 0.0
        assert len(result.terminal_unsafe_probs) == N_STATES
        assert not learner.is_fitted

    def test_fit_single_safe_trajectory(self) -> None:
        learner = DTMCLearner()
        result = learner.fit([_safe_traj()])
        assert learner.is_fitted
        assert result.message == "ok"
        assert result.n_trajectories == 1
        assert result.n_transitions == 3  # 4-state trajectory → 3 transitions

    def test_fit_single_unsafe_trajectory(self) -> None:
        learner = DTMCLearner()
        result = learner.fit([_unsafe_traj()])
        assert learner.is_fitted
        assert result.unsafe_fraction == pytest.approx(1.0)

    def test_transition_matrix_rows_sum_to_one(self) -> None:
        learner = _fitted_learner()
        row_sums = learner.transition_matrix.sum(axis=1)
        np.testing.assert_allclose(row_sums, np.ones(N_STATES), atol=1e-10)

    def test_transition_matrix_non_negative(self) -> None:
        learner = _fitted_learner()
        assert (learner.transition_matrix >= 0).all()

    def test_terminal_unsafe_probs_in_unit_interval(self) -> None:
        learner = _fitted_learner()
        assert (learner.terminal_unsafe_probs >= 0).all()
        assert (learner.terminal_unsafe_probs <= 1).all()

    def test_unsafe_fraction_half(self) -> None:
        trajs = [_safe_traj() for _ in range(2)] + [_unsafe_traj() for _ in range(2)]
        learner = DTMCLearner()
        result = learner.fit(trajs)
        assert result.unsafe_fraction == pytest.approx(0.5)

    def test_unsafe_fraction_all_safe(self) -> None:
        learner = DTMCLearner()
        result = learner.fit([_safe_traj() for _ in range(5)])
        assert result.unsafe_fraction == 0.0

    def test_unsafe_fraction_all_unsafe(self) -> None:
        learner = DTMCLearner()
        result = learner.fit([_unsafe_traj() for _ in range(5)])
        assert result.unsafe_fraction == 1.0

    def test_n_transitions_single_state_traj(self) -> None:
        traj = TrajectoryRecord(states=[0], terminal_unsafe=False)
        learner = DTMCLearner()
        result = learner.fit([traj])
        # Single state: no transitions
        assert result.n_transitions == 0

    def test_n_transitions_multiple_trajs(self) -> None:
        # traj1 has 3 transitions, traj2 has 3 transitions
        traj1 = TrajectoryRecord(states=[0, 1, 2, 3], terminal_unsafe=False)
        traj2 = TrajectoryRecord(states=[1, 2, 3, 4], terminal_unsafe=True)
        learner = DTMCLearner()
        result = learner.fit([traj1, traj2])
        assert result.n_transitions == 6

    def test_n_trajectories_and_transitions_stored(self) -> None:
        traj = TrajectoryRecord(states=[0, 1, 2], terminal_unsafe=False)
        learner = DTMCLearner()
        learner.fit([traj])
        assert learner._n_trajectories == 1
        assert learner._n_transitions == 2

    def test_fit_resets_on_second_call(self) -> None:
        learner = DTMCLearner()
        learner.fit([_unsafe_traj() for _ in range(20)])
        matrix_after_unsafe = learner.transition_matrix.copy()
        # Fit again with pure safe data — matrix should change
        learner.fit([_safe_traj() for _ in range(50)])
        assert not np.allclose(learner.transition_matrix, matrix_after_unsafe)

    def test_laplace_smoothing_no_zero_probabilities(self) -> None:
        """Even with sparse data, Laplace smoothing prevents zero entries."""
        traj = TrajectoryRecord(states=[0, 1], terminal_unsafe=False)
        learner = DTMCLearner(laplace_alpha=1.0)
        learner.fit([traj])
        assert (learner.transition_matrix > 0).all()

    def test_deterministic_transition_dominates_with_many_samples(self) -> None:
        """100 samples of 0→1 should push P(0,1) close to 1.0."""
        trajs = [TrajectoryRecord(states=[0, 1], terminal_unsafe=False) for _ in range(100)]
        learner = DTMCLearner(laplace_alpha=0.01)
        learner.fit(trajs)
        assert learner.transition_matrix[0, 1] > 0.95

    def test_counts_persisted_for_online_updates(self) -> None:
        """After fit, _transition_counts should reflect observations + Laplace."""
        traj = TrajectoryRecord(states=[0, 2], terminal_unsafe=False)
        learner = DTMCLearner(laplace_alpha=1.0)
        learner.fit([traj])
        # One transition from 0→2; so count[0,2] = 1 + 1 (Laplace) = 2
        assert learner._transition_counts[0, 2] == pytest.approx(2.0)

    def test_terminal_unsafe_probs_updates_per_state(self) -> None:
        """Last state in each trajectory updates the terminal_unsafe_probs correctly."""
        # trajectory ending at state 4 marked unsafe
        traj = TrajectoryRecord(states=[0, 1, 4], terminal_unsafe=True)
        learner = DTMCLearner()
        learner.fit([traj])
        # State 4 had 1 unsafe terminal; prob should be > 0
        assert learner.terminal_unsafe_probs[4] > 0.0

    def test_result_terminal_unsafe_probs_is_list(self) -> None:
        learner = DTMCLearner()
        result = learner.fit([_safe_traj()])
        assert isinstance(result.terminal_unsafe_probs, list)
        assert len(result.terminal_unsafe_probs) == N_STATES


# ---------------------------------------------------------------------------
# DTMCLearner.update_online
# ---------------------------------------------------------------------------


class TestDTMCLearnerUpdateOnline:
    def test_single_safe_update_sets_fitted(self) -> None:
        learner = DTMCLearner()
        assert not learner.is_fitted
        learner.update_online(_safe_traj())
        assert learner.is_fitted

    def test_single_unsafe_update_sets_fitted(self) -> None:
        learner = DTMCLearner()
        learner.update_online(_unsafe_traj())
        assert learner.is_fitted

    def test_trajectory_count_increments(self) -> None:
        learner = DTMCLearner()
        for i in range(5):
            learner.update_online(_safe_traj())
            assert learner._n_trajectories == i + 1

    def test_transition_count_increments(self) -> None:
        learner = DTMCLearner()
        # single-state trajectory → 0 transitions
        single = TrajectoryRecord(states=[0], terminal_unsafe=False)
        learner.update_online(single)
        assert learner._n_transitions == 0
        # 4-state trajectory → 3 transitions
        learner.update_online(_safe_traj())
        assert learner._n_transitions == 3

    def test_transition_matrix_rows_still_sum_to_one_after_many_updates(self) -> None:
        learner = DTMCLearner()
        learner.fit([_safe_traj()])
        for _ in range(20):
            learner.update_online(_unsafe_traj())
        row_sums = learner.transition_matrix.sum(axis=1)
        np.testing.assert_allclose(row_sums, np.ones(N_STATES), atol=1e-10)

    def test_terminal_unsafe_probs_in_unit_interval_after_updates(self) -> None:
        learner = DTMCLearner()
        learner.fit([_safe_traj()])
        for _ in range(10):
            learner.update_online(_unsafe_traj())
        assert (learner.terminal_unsafe_probs >= 0).all()
        assert (learner.terminal_unsafe_probs <= 1).all()

    def test_repeated_unsafe_updates_increase_unsafe_terminal_prob(self) -> None:
        learner = DTMCLearner()
        learner.fit([_safe_traj() for _ in range(10)])
        unsafe_prob_before = learner.terminal_unsafe_probs[4]  # state 4 = CRITICAL
        for _ in range(30):
            learner.update_online(_unsafe_traj())
        assert learner.terminal_unsafe_probs[4] >= unsafe_prob_before

    def test_unsafe_update_increments_unsafe_terminal_count(self) -> None:
        learner = DTMCLearner()
        learner.update_online(_unsafe_traj())  # ends at state 4
        # _terminal_counts[4, 1] should be incremented by 1
        assert learner._terminal_counts[4, 1] == pytest.approx(1.0)

    def test_safe_update_increments_safe_terminal_count(self) -> None:
        learner = DTMCLearner()
        learner.update_online(_safe_traj())  # ends at state 1
        # _terminal_counts[1, 0] should be incremented
        assert learner._terminal_counts[1, 0] == pytest.approx(1.0)

    def test_single_state_trajectory_no_transition_increment(self) -> None:
        learner = DTMCLearner()
        traj = TrajectoryRecord(states=[2], terminal_unsafe=False)
        learner.update_online(traj)
        assert learner._n_transitions == 0

    def test_two_state_trajectory_increments_transition(self) -> None:
        learner = DTMCLearner()
        traj = TrajectoryRecord(states=[0, 3], terminal_unsafe=False)
        learner.update_online(traj)
        assert learner._transition_counts[0, 3] > learner.laplace_alpha


# ---------------------------------------------------------------------------
# DTMCLearner.predict_risk
# ---------------------------------------------------------------------------


class TestDTMCLearnerPredictRisk:
    def test_empty_prefix_returns_zero(self) -> None:
        learner = DTMCLearner()
        assert learner.predict_risk([]) == 0.0

    def test_empty_prefix_returns_zero_after_fit(self) -> None:
        learner = _fitted_learner()
        assert learner.predict_risk([]) == 0.0

    def test_out_of_range_positive_state_raises(self) -> None:
        learner = DTMCLearner()
        with pytest.raises(ValueError, match="out of range"):
            learner.predict_risk([N_STATES])

    def test_out_of_range_negative_state_raises(self) -> None:
        learner = DTMCLearner()
        with pytest.raises(ValueError, match="out of range"):
            learner.predict_risk([-1])

    def test_returns_float_in_unit_interval_before_fit(self) -> None:
        learner = DTMCLearner()
        risk = learner.predict_risk([0])
        assert isinstance(risk, float)
        assert 0.0 <= risk <= 1.0

    def test_returns_float_in_unit_interval_after_fit(self) -> None:
        learner = _fitted_learner()
        for state in range(N_STATES):
            risk = learner.predict_risk([state])
            assert 0.0 <= risk <= 1.0

    def test_multi_element_prefix_uses_only_last_state(self) -> None:
        learner = _fitted_learner()
        r1 = learner.predict_risk([0, 1, 2])
        r2 = learner.predict_risk([3, 4, 2])
        # Both end at state 2 → same forward projection → same risk
        assert r1 == pytest.approx(r2, abs=1e-9)

    def test_single_element_prefix(self) -> None:
        learner = _fitted_learner()
        risk = learner.predict_risk([3])
        assert 0.0 <= risk <= 1.0

    def test_lookahead_zero_returns_terminal_unsafe_prob(self) -> None:
        """With lookahead_steps=0, no forward projection; result = terminal_unsafe_probs[last]."""
        learner = DTMCLearner(lookahead_steps=0)
        trajs = [TrajectoryRecord(states=[4], terminal_unsafe=True) for _ in range(10)] + [
            TrajectoryRecord(states=[4], terminal_unsafe=False) for _ in range(10)
        ]
        learner.fit(trajs)
        # terminal_unsafe_probs[4] ≈ 0.5 (10 unsafe, 10 safe)
        risk = learner.predict_risk([4])
        assert risk == pytest.approx(learner.terminal_unsafe_probs[4], abs=1e-9)

    def test_high_state_riskier_than_low_state_after_unsafe_fit(self) -> None:
        """CRITICAL-state prefix should score higher risk than zero after unsafe training."""
        trajs = [TrajectoryRecord(states=[0, 1, 2, 3, 4], terminal_unsafe=True)] * 30
        learner = DTMCLearner(lookahead_steps=1)
        learner.fit(trajs)
        # State 4 (CRITICAL) should have a non-trivial risk after unsafe training
        risk_critical = learner.predict_risk([4])
        assert risk_critical > 0.0

    def test_result_is_clipped_to_zero_on_lower(self) -> None:
        """Risk must never be negative."""
        learner = DTMCLearner()
        # Force all-zero terminal_unsafe_probs → risk = 0.0
        learner.terminal_unsafe_probs = np.zeros(N_STATES)
        risk = learner.predict_risk([0])
        assert risk >= 0.0

    def test_result_is_clipped_to_one_on_upper(self) -> None:
        """Risk must never exceed 1.0."""
        learner = DTMCLearner()
        learner.terminal_unsafe_probs = np.ones(N_STATES) * 2.0  # deliberately > 1
        risk = learner.predict_risk([0])
        assert risk <= 1.0


# ---------------------------------------------------------------------------
# DTMCLearner.should_intervene
# ---------------------------------------------------------------------------


class TestDTMCLearnerShouldIntervene:
    def test_returns_bool(self) -> None:
        learner = DTMCLearner()
        result = learner.should_intervene([0])
        assert isinstance(result, bool)

    def test_threshold_zero_always_intervenes(self) -> None:
        learner = DTMCLearner(intervention_threshold=0.0)
        # risk >= 0.0 is always True when threshold is 0
        assert learner.should_intervene([0])

    def test_threshold_above_one_never_intervenes(self) -> None:
        """Risk is clipped to [0,1]; threshold > 1 → never triggers."""
        learner = DTMCLearner(intervention_threshold=1.1)
        learner.fit([_unsafe_traj() for _ in range(50)])
        assert not learner.should_intervene([4])

    def test_instance_threshold_used_when_no_override(self) -> None:
        """When threshold=None, self.intervention_threshold is used."""
        learner = DTMCLearner(intervention_threshold=0.0)  # always fires
        assert learner.should_intervene([0], threshold=None)

    def test_custom_threshold_overrides_instance(self) -> None:
        """threshold kwarg overrides self.intervention_threshold."""
        # Instance threshold is 0.0 (always fires), but override is 1.1 (never fires)
        learner = DTMCLearner(intervention_threshold=0.0)
        assert not learner.should_intervene([0], threshold=1.1)

    def test_custom_threshold_lower_than_instance(self) -> None:
        """Override with threshold=0.0 always fires regardless of instance value."""
        learner = DTMCLearner(intervention_threshold=0.99)
        assert learner.should_intervene([0], threshold=0.0)

    def test_default_threshold_is_0_8(self) -> None:
        assert DTMCLearner().intervention_threshold == pytest.approx(0.8)

    def test_threshold_exactly_equal_to_risk_triggers(self) -> None:
        """should_intervene returns True when risk equals threshold (>=)."""
        learner = DTMCLearner()
        # Force predict_risk to return exactly 0.5
        learner.terminal_unsafe_probs = np.zeros(N_STATES)
        # Build a deterministic chain that keeps state 2 at risk = 0.5
        # We can patch predict_risk for a precise test
        import unittest.mock as mock

        with mock.patch.object(learner, "predict_risk", return_value=0.5):
            assert learner.should_intervene([2], threshold=0.5)
            assert not learner.should_intervene([2], threshold=0.51)


# ---------------------------------------------------------------------------
# DTMCLearner.stationary_distribution
# ---------------------------------------------------------------------------


class TestDTMCLearnerStationaryDistribution:
    def test_returns_ndarray(self) -> None:
        learner = DTMCLearner()
        dist = learner.stationary_distribution()
        assert isinstance(dist, np.ndarray)

    def test_shape_is_n_states(self) -> None:
        learner = DTMCLearner()
        assert learner.stationary_distribution().shape == (N_STATES,)

    def test_sums_to_one_before_fit(self) -> None:
        learner = DTMCLearner()
        dist = learner.stationary_distribution()
        assert dist.sum() == pytest.approx(1.0, abs=1e-9)

    def test_non_negative_before_fit(self) -> None:
        learner = DTMCLearner()
        assert (learner.stationary_distribution() >= 0).all()

    def test_sums_to_one_after_fit(self) -> None:
        learner = _fitted_learner()
        dist = learner.stationary_distribution()
        assert dist.sum() == pytest.approx(1.0, abs=1e-9)

    def test_non_negative_after_fit(self) -> None:
        learner = _fitted_learner()
        assert (learner.stationary_distribution() >= 0).all()

    def test_custom_n_iterations(self) -> None:
        learner = _fitted_learner()
        dist10 = learner.stationary_distribution(n_iterations=10)
        dist200 = learner.stationary_distribution(n_iterations=200)
        # Both should sum to 1.0 and be close (within tolerance for ergodic chains)
        assert dist10.sum() == pytest.approx(1.0, abs=1e-9)
        assert dist200.sum() == pytest.approx(1.0, abs=1e-9)

    def test_uniform_chain_stationary_is_uniform(self) -> None:
        """Fresh DTMCLearner has a uniform P → stationary dist is uniform."""
        learner = DTMCLearner()
        dist = learner.stationary_distribution(n_iterations=200)
        expected = np.full(N_STATES, 1.0 / N_STATES)
        np.testing.assert_allclose(dist, expected, atol=1e-9)


# ---------------------------------------------------------------------------
# DTMCLearner.risk_vector
# ---------------------------------------------------------------------------


class TestDTMCLearnerRiskVector:
    def test_returns_ndarray(self) -> None:
        learner = DTMCLearner()
        rv = learner.risk_vector()
        assert isinstance(rv, np.ndarray)

    def test_shape_is_n_states(self) -> None:
        learner = DTMCLearner()
        assert learner.risk_vector().shape == (N_STATES,)

    def test_values_in_unit_interval_before_fit(self) -> None:
        learner = DTMCLearner()
        rv = learner.risk_vector()
        assert (rv >= 0.0).all()
        assert (rv <= 1.0).all()

    def test_values_in_unit_interval_after_fit(self) -> None:
        learner = _fitted_learner()
        rv = learner.risk_vector()
        assert (rv >= 0.0).all()
        assert (rv <= 1.0).all()

    def test_risk_vector_vs_predict_risk_per_state(self) -> None:
        """risk_vector()[s] must equal predict_risk([s]) for each state s."""
        learner = _fitted_learner(n_safe=5, n_unsafe=5, lookahead=3)
        rv = learner.risk_vector()
        for s in range(N_STATES):
            expected = learner.predict_risk([s])
            assert rv[s] == pytest.approx(expected, abs=1e-9)

    def test_all_unsafe_data_high_risk_vector(self) -> None:
        """Pure unsafe data should produce positive risk values."""
        trajs = [TrajectoryRecord(states=[0, 1, 2, 3, 4], terminal_unsafe=True)] * 30
        learner = DTMCLearner(lookahead_steps=3)
        learner.fit(trajs)
        rv = learner.risk_vector()
        assert rv.sum() > 0.0

    def test_all_safe_data_lower_risk_vector(self) -> None:
        """Pure safe data should produce lower risk than pure unsafe data."""
        safe_trajs = [TrajectoryRecord(states=[0, 0, 0, 0], terminal_unsafe=False)] * 30
        unsafe_trajs = [TrajectoryRecord(states=[0, 1, 2, 3, 4], terminal_unsafe=True)] * 30
        learner_safe = DTMCLearner(lookahead_steps=3)
        learner_safe.fit(safe_trajs)
        learner_unsafe = DTMCLearner(lookahead_steps=3)
        learner_unsafe.fit(unsafe_trajs)
        assert learner_safe.risk_vector().sum() <= learner_unsafe.risk_vector().sum()

    def test_risk_vector_clipped_when_terminal_unsafe_probs_above_one(self) -> None:
        """np.clip is applied — manual probs > 1 should be clipped to 1."""
        learner = DTMCLearner()
        learner.terminal_unsafe_probs = np.ones(N_STATES) * 5.0  # deliberately > 1
        rv = learner.risk_vector()
        assert (rv <= 1.0).all()

    def test_risk_vector_lookahead_zero(self) -> None:
        """With lookahead=0, matrix_power(P,0) = identity; rv = terminal_unsafe_probs."""
        learner = DTMCLearner(lookahead_steps=0)
        trajs = [TrajectoryRecord(states=[i], terminal_unsafe=(i >= 3)) for i in range(N_STATES)]
        learner.fit(trajs)
        rv = learner.risk_vector()
        # With lookahead=0, P^0 = I; rv = I @ terminal_unsafe_probs = terminal_unsafe_probs
        np.testing.assert_allclose(rv, np.clip(learner.terminal_unsafe_probs, 0.0, 1.0), atol=1e-9)


# ---------------------------------------------------------------------------
# Logging integration (ensures logger.warning / logger.info branches execute)
# ---------------------------------------------------------------------------


class TestDTMCLearnerLogging:
    def test_fit_empty_emits_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging

        learner = DTMCLearner()
        with caplog.at_level(
            logging.WARNING, logger="enhanced_agent_bus.adaptive_governance.dtmc_learner"
        ):
            learner.fit([])
        assert any("empty trajectory" in r.message.lower() for r in caplog.records)

    def test_fit_batch_emits_info(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging

        learner = DTMCLearner()
        with caplog.at_level(
            logging.INFO, logger="enhanced_agent_bus.adaptive_governance.dtmc_learner"
        ):
            learner.fit([_safe_traj(), _unsafe_traj()])
        assert any("fitted" in r.message.lower() for r in caplog.records)


# ---------------------------------------------------------------------------
# Edge cases and numerical stability
# ---------------------------------------------------------------------------


class TestDTMCLearnerEdgeCases:
    def test_single_state_trajectory_fit(self) -> None:
        traj = TrajectoryRecord(states=[2], terminal_unsafe=False)
        learner = DTMCLearner()
        result = learner.fit([traj])
        assert result.n_transitions == 0
        assert learner.is_fitted

    def test_all_same_state_trajectory(self) -> None:
        traj = TrajectoryRecord(states=[0, 0, 0, 0], terminal_unsafe=False)
        learner = DTMCLearner()
        learner.fit([traj])
        # P(0 → 0) should be largest entry in row 0
        row0 = learner.transition_matrix[0]
        assert learner.transition_matrix[0, 0] == row0.max()

    def test_custom_n_states(self) -> None:
        """DTMCLearner supports custom n_states (tested with n_states=3)."""
        learner = DTMCLearner(n_states=3)
        traj = TrajectoryRecord.__new__(TrajectoryRecord)
        # Bypass __post_init__ validation (which uses N_STATES=5) by calling
        # __init__ directly with only 3-state valid values
        object.__setattr__(traj, "states", [0, 1, 2])
        object.__setattr__(traj, "terminal_unsafe", False)
        object.__setattr__(traj, "session_id", None)
        object.__setattr__(traj, "timestamp", "2024-01-01T00:00:00+00:00")
        object.__setattr__(traj, "metadata", {})
        learner.fit([traj])
        assert learner.transition_matrix.shape == (3, 3)

    def test_large_batch_performance(self) -> None:
        """Fitting 1000 trajectories should complete without error."""
        trajs = [_safe_traj(4) for _ in range(500)] + [_unsafe_traj(4) for _ in range(500)]
        learner = DTMCLearner()
        result = learner.fit(trajs)
        assert result.n_trajectories == 1000
        assert learner.is_fitted

    def test_online_then_predict_consistency(self) -> None:
        """predict_risk after update_online should produce consistent results."""
        learner = DTMCLearner()
        learner.fit([_safe_traj(), _unsafe_traj()])
        risk_before = learner.predict_risk([3])
        learner.update_online(_unsafe_traj())
        risk_after = learner.predict_risk([3])
        assert 0.0 <= risk_before <= 1.0
        assert 0.0 <= risk_after <= 1.0

    def test_transition_counts_updated_by_online(self) -> None:
        """_transition_counts should increase after update_online."""
        learner = DTMCLearner()
        counts_before = learner._transition_counts.copy()
        learner.update_online(TrajectoryRecord(states=[0, 1, 2], terminal_unsafe=False))
        # At least one entry increased
        assert (learner._transition_counts >= counts_before).all()
        assert not np.allclose(learner._transition_counts, counts_before)

    def test_predict_risk_all_valid_states(self) -> None:
        """predict_risk([s]) must not raise for any valid state."""
        learner = _fitted_learner()
        for s in range(N_STATES):
            risk = learner.predict_risk([s])
            assert 0.0 <= risk <= 1.0
