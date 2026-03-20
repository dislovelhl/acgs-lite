"""Tests for Manifold-Constrained Agent Governance.

Validates the mathematical properties that make omalhc defensible:
doubly stochastic trust matrices, compositional closure, bounded
influence, and Sinkhorn-Knopp convergence.
"""

from __future__ import annotations

import math
import time

import pytest

from omalhc.manifold import GovernanceManifold, ManifoldProjectionResult, sinkhorn_knopp


class TestSinkhornKnopp:
    """Test the core Sinkhorn-Knopp projection."""

    def test_identity_like_input(self) -> None:
        """Uniform input → uniform doubly stochastic output."""
        result = sinkhorn_knopp([[0.0, 0.0], [0.0, 0.0]])
        assert result.converged
        # exp(0) = 1, so uniform → 0.5 each
        for row in result.matrix:
            assert abs(sum(row) - 1.0) < 1e-6

    def test_arbitrary_input_becomes_ds(self) -> None:
        """Any non-negative input projects to doubly stochastic."""
        raw = [[3.0, 1.0, 0.5], [0.1, 2.0, 1.0], [1.0, 0.5, 3.0]]
        result = sinkhorn_knopp(raw)
        assert result.converged
        n = len(result.matrix)
        for i in range(n):
            row_sum = sum(result.matrix[i])
            assert abs(row_sum - 1.0) < 1e-4, f"Row {i} sum = {row_sum}"
        for j in range(n):
            col_sum = sum(result.matrix[i][j] for i in range(n))
            assert abs(col_sum - 1.0) < 1e-4, f"Col {j} sum = {col_sum}"

    def test_spectral_bound_leq_one(self) -> None:
        """Spectral norm of DS matrix is bounded by 1."""
        raw = [[5.0, 1.0, 0.1], [0.1, 5.0, 1.0], [1.0, 0.1, 5.0]]
        result = sinkhorn_knopp(raw)
        assert result.spectral_bound <= 1.0 + 1e-4

    def test_convergence_in_20_iterations(self) -> None:
        """Should converge within 20 iterations (same as mHC)."""
        raw = [[1.0] * 10 for _ in range(10)]
        result = sinkhorn_knopp(raw, max_iterations=20)
        assert result.converged
        assert result.iterations <= 20

    def test_non_negative_output(self) -> None:
        """All entries in projected matrix are non-negative."""
        raw = [[-2.0, 1.0], [3.0, -1.0]]  # Negative inputs ok — exp makes positive
        result = sinkhorn_knopp(raw)
        for row in result.matrix:
            for val in row:
                assert val >= 0.0

    def test_empty_matrix(self) -> None:
        result = sinkhorn_knopp([])
        assert result.converged
        assert result.matrix == ()

    def test_single_element(self) -> None:
        """N=1 degenerates to scalar 1 (identity mapping, same as mHC)."""
        result = sinkhorn_knopp([[5.0]])
        assert len(result.matrix) == 1
        assert abs(result.matrix[0][0] - 1.0) < 1e-6


class TestGovernanceManifold:
    """Test the governance manifold M^gov."""

    def test_initial_state_is_uniform(self) -> None:
        gm = GovernanceManifold(4)
        proj = gm.project()
        assert proj.converged
        # Uniform trust: each agent trusts all equally
        for row in proj.matrix:
            assert abs(sum(row) - 1.0) < 1e-4

    def test_update_trust_and_project(self) -> None:
        gm = GovernanceManifold(3)
        gm.update_trust(0, 1, 5.0)  # Agent 0 strongly trusts agent 1
        proj = gm.project()
        # Sinkhorn-Knopp is approximate at 20 iters (same as mHC t_max=20)
        assert proj.max_deviation < 1e-3
        # Agent 0's trust should be skewed toward agent 1
        assert proj.matrix[0][1] > proj.matrix[0][0]

    def test_trust_conservation(self) -> None:
        """Each agent distributes ≈1.0 trust and receives ≈1.0.

        Tolerance is 1e-3 because Sinkhorn-Knopp with t_max=20 is
        approximate (same practical choice as mHC Section 4.2).
        """
        gm = GovernanceManifold(5)
        for i in range(5):
            for j in range(5):
                gm.update_trust(i, j, float(i * j))
        gm.project()
        for i in range(5):
            assert abs(sum(gm.trust_matrix[i]) - 1.0) < 1e-3
            assert abs(gm.received_trust(i) - 1.0) < 1e-3

    def test_stability_property(self) -> None:
        """Governance manifold is always stable (spectral bound ≤ 1)."""
        gm = GovernanceManifold(8)
        for i in range(8):
            gm.update_trust(i, (i + 1) % 8, 10.0)  # Strong chain
        assert gm.is_stable

    def test_influence_vector_sums_to_one(self) -> None:
        gm = GovernanceManifold(4)
        gm.update_trust(0, 2, 3.0)
        gm.project()
        iv = gm.influence_vector(0)
        assert abs(sum(iv) - 1.0) < 1e-4


class TestCompositionalClosure:
    """Prove that governance chains are stable at any depth.

    The product of doubly stochastic matrices is doubly stochastic.
    This is the compositional closure property from mHC Section 4.1.
    """

    def test_compose_two_manifolds(self) -> None:
        g1 = GovernanceManifold(3)
        g2 = GovernanceManifold(3)
        g1.update_trust(0, 1, 2.0)
        g2.update_trust(1, 2, 3.0)

        composed = g1.compose(g2)
        # Composed matrix should still be doubly stochastic
        for i in range(3):
            assert abs(sum(composed.trust_matrix[i]) - 1.0) < 1e-3
        for j in range(3):
            col_sum = sum(composed.trust_matrix[i][j] for i in range(3))
            assert abs(col_sum - 1.0) < 1e-3

    def test_deep_composition_stability(self) -> None:
        """Compose 100 manifolds — stability maintained (like mHC Fig. 7)."""
        n = 5
        current = GovernanceManifold(n)
        for layer in range(100):
            next_gm = GovernanceManifold(n)
            next_gm.update_trust(layer % n, (layer + 1) % n, 1.0)
            current = current.compose(next_gm)

        # After 100 compositions, still doubly stochastic and stable
        assert current.is_stable
        for i in range(n):
            assert abs(sum(current.trust_matrix[i]) - 1.0) < 1e-2

    def test_composition_does_not_explode(self) -> None:
        """Spectral bound stays ≤ 1 through compositions (mHC Thm 1 analog)."""
        n = 4
        current = GovernanceManifold(n)
        bounds = []
        for _ in range(50):
            other = GovernanceManifold(n)
            other.update_trust(0, 1, 5.0)
            current = current.compose(other)
            bounds.append(current.spectral_bound)

        # No explosion — all bounds ≤ 1 + ε
        assert all(b <= 1.0 + 1e-2 for b in bounds)


class TestScaling:
    """Test manifold projection at scale."""

    def test_50_agents(self) -> None:
        """50-agent manifold projects correctly."""
        gm = GovernanceManifold(50)
        for i in range(50):
            gm.update_trust(i, (i + 7) % 50, 2.0)
            gm.update_trust(i, (i + 13) % 50, 1.0)
        proj = gm.project()
        assert proj.converged
        assert gm.is_stable

    def test_projection_latency(self) -> None:
        """Sinkhorn-Knopp projection should be fast even for 100 agents."""
        gm = GovernanceManifold(100)
        for i in range(100):
            gm.update_trust(i, (i + 1) % 100, 1.0)

        start = time.perf_counter_ns()
        gm.project()
        elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000

        # 100x100 Sinkhorn-Knopp in pure Python should be under 100ms
        assert elapsed_ms < 100, f"Too slow: {elapsed_ms:.1f}ms"

    def test_summary(self) -> None:
        gm = GovernanceManifold(10)
        s = gm.summary()
        assert s["num_agents"] == 10
        assert s["is_stable"] is True
        assert "spectral_bound" in s
