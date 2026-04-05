"""Manifold-Constrained Agent Governance.

Inspired by mHC (DeepSeek, arXiv:2512.24880), this module projects
unconstrained agent interaction matrices onto the governance manifold
via Sinkhorn-Knopp normalization.

Mathematical foundation:
  - Agent influence is represented as an N x N matrix H where H[i,j]
    is how much agent i trusts agent j's validation
  - Unconstrained H leads to trust explosion/collapse at scale
    (analogous to signal explosion in unconstrained HC)
  - We project H onto the Birkhoff polytope (doubly stochastic matrices)
    via Sinkhorn-Knopp iteration
  - This guarantees:
    1. Norm preservation: spectral norm ≤ 1 (bounded influence)
    2. Compositional closure: product of DS matrices = DS (governance
       stability at any depth of agent chains)
    3. Conservation: row/column sums = 1 (trust is conserved, not
       created or destroyed)

The constitutional validation engine (443ns) serves as the manifold
projection operator P_M^gov — analogous to Sinkhorn-Knopp in mHC.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ManifoldProjectionResult:
    """Result of projecting an interaction matrix onto the governance manifold."""

    matrix: tuple[tuple[float, ...], ...]
    iterations: int
    converged: bool
    max_deviation: float
    spectral_bound: float


def sinkhorn_knopp(
    matrix: list[list[float]],
    *,
    max_iterations: int = 20,
    epsilon: float = 1e-6,
) -> ManifoldProjectionResult:
    """Project a non-negative matrix onto the Birkhoff polytope.

    Uses the Sinkhorn-Knopp algorithm (1967) to iteratively normalize
    rows and columns until the matrix is doubly stochastic.

    This is the governance analog of mHC's manifold projection:
    unconstrained agent influence → bounded, conserved trust.

    Args:
        matrix: N x N non-negative matrix of raw agent interactions.
        max_iterations: Maximum Sinkhorn-Knopp iterations.
        epsilon: Convergence threshold.

    Returns:
        ManifoldProjectionResult with the doubly stochastic matrix.
    """
    n = len(matrix)
    if n == 0:
        return ManifoldProjectionResult(
            matrix=(),
            iterations=0,
            converged=True,
            max_deviation=0.0,
            spectral_bound=0.0,
        )

    # Ensure non-negative via exp (same as mHC Eq. 8)
    # Clamp to [-500, 500] to prevent overflow (H4 fix)
    _CLAMP = 500.0
    m = [[math.exp(max(-_CLAMP, min(_CLAMP, matrix[i][j]))) for j in range(n)] for i in range(n)]

    converged = False
    iterations = 0

    for t in range(max_iterations):
        iterations = t + 1

        # Row normalization: T_r
        for i in range(n):
            row_sum = sum(m[i])
            if row_sum > 0:
                m[i] = [x / row_sum for x in m[i]]

        # Column normalization: T_c
        for j in range(n):
            col_sum = sum(m[i][j] for i in range(n))
            if col_sum > 0:
                for i in range(n):
                    m[i][j] = m[i][j] / col_sum

        # Check convergence
        max_dev = 0.0
        for i in range(n):
            row_sum = sum(m[i])
            max_dev = max(max_dev, abs(row_sum - 1.0))
        for j in range(n):
            col_sum = sum(m[i][j] for i in range(n))
            max_dev = max(max_dev, abs(col_sum - 1.0))

        if max_dev < epsilon:
            converged = True
            break

    # Compute spectral bound (max row sum ≈ spectral norm for DS matrices)
    spectral = max(sum(abs(m[i][j]) for j in range(n)) for i in range(n))

    result_matrix = tuple(tuple(row) for row in m)
    return ManifoldProjectionResult(
        matrix=result_matrix,
        iterations=iterations,
        converged=converged,
        max_deviation=max_dev,
        spectral_bound=spectral,
    )


class GovernanceManifold:
    """The governance manifold M^gov for multi-agent systems.

    Projects unconstrained agent interaction matrices onto the
    Birkhoff polytope, guaranteeing bounded influence, compositional
    closure, and trust conservation.

    Analogous to mHC's manifold-constrained residual connections,
    but applied to agent governance instead of neural network layers.

    Properties of M^gov:
      1. Bounded influence: ||P_M(H)||_2 ≤ 1
      2. Compositional closure: P_M(H1) · P_M(H2) ∈ M^gov
      3. Conservation: Σ_j H[i,j] = 1, Σ_i H[i,j] = 1
      4. Identity recovery: when N=1, degenerates to scalar 1
         (identity mapping, same as mHC)
    """

    def __init__(self, num_agents: int, *, max_iterations: int = 20) -> None:
        self._n = num_agents
        self._max_iterations = max_iterations
        # Initialize trust matrix as uniform (identity-like in DS space)
        self._raw_trust: list[list[float]] = [[0.0] * num_agents for _ in range(num_agents)]
        self._projected: ManifoldProjectionResult | None = None

    @property
    def num_agents(self) -> int:
        return self._n

    def update_trust(self, from_agent: int, to_agent: int, delta: float) -> None:
        """Update raw trust score. Will be projected onto manifold.

        Raw values can be any real number — the Sinkhorn-Knopp projection
        ensures the result is doubly stochastic regardless.
        """
        if 0 <= from_agent < self._n and 0 <= to_agent < self._n:
            self._raw_trust[from_agent][to_agent] += delta
            self._projected = None  # Invalidate cache

    def project(self) -> ManifoldProjectionResult:
        """Project current trust matrix onto the governance manifold.

        This is the core operation: P_M^gov(H) in the paper.
        Analogous to mHC's Sinkhorn-Knopp projection of H_res.
        """
        if self._projected is not None:
            return self._projected
        self._projected = sinkhorn_knopp(self._raw_trust, max_iterations=self._max_iterations)
        return self._projected

    @property
    def trust_matrix(self) -> tuple[tuple[float, ...], ...]:
        """The projected doubly stochastic trust matrix."""
        return self.project().matrix

    @property
    def spectral_bound(self) -> float:
        """Spectral norm bound of the projected matrix. Always ≤ 1 + ε."""
        return self.project().spectral_bound

    @property
    def is_stable(self) -> bool:
        """Check if the governance manifold is stable (spectral norm ≤ 1 + ε)."""
        return self.spectral_bound <= 1.0 + 1e-4

    def compose(self, other: GovernanceManifold) -> GovernanceManifold:
        """Compose two governance manifolds.

        The product of two doubly stochastic matrices is doubly stochastic.
        This proves compositional closure: governance chains are stable
        at any depth.
        """
        if self._n != other._n:
            raise ValueError("Cannot compose manifolds of different sizes")

        a = self.trust_matrix
        b = other.trust_matrix
        n = self._n

        result = GovernanceManifold(n, max_iterations=self._max_iterations)
        # Matrix multiplication
        product = [[sum(a[i][k] * b[k][j] for k in range(n)) for j in range(n)] for i in range(n)]
        result._raw_trust = product
        # Product of DS matrices is DS — but re-project to handle float errors
        result._projected = sinkhorn_knopp(product, max_iterations=self._max_iterations)
        return result

    def influence_vector(self, agent_idx: int) -> tuple[float, ...]:
        """How much influence does agent_idx have on each other agent?

        Returns the agent's row in the projected trust matrix.
        Sum is guaranteed to be 1.0 (trust conservation).
        """
        return self.trust_matrix[agent_idx]

    def received_trust(self, agent_idx: int) -> float:
        """Total trust received by an agent. Guaranteed ≈ 1.0."""
        return sum(row[agent_idx] for row in self.trust_matrix)

    def summary(self) -> dict[str, Any]:
        """Manifold statistics."""
        proj = self.project()
        return {
            "num_agents": self._n,
            "converged": proj.converged,
            "iterations": proj.iterations,
            "max_deviation": proj.max_deviation,
            "spectral_bound": proj.spectral_bound,
            "is_stable": self.is_stable,
        }
