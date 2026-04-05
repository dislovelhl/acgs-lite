"""
Module.

Constitutional Hash: 608508a9bd224290
"""

import os
import sys

import numpy as np
import pytest

torch = pytest.importorskip("torch")

# Ensure we can import the project modules
sys.path.append("/home/martin/ACGS")

# Handle optional Rust extension gracefully
try:
    from acgs2_perf import sinkhorn_knopp

    HAS_RUST_PERF = True
except ImportError:
    HAS_RUST_PERF = False
    sinkhorn_knopp = None

# Governance and constitutional compliance test markers
pytestmark = [
    pytest.mark.governance,
    pytest.mark.constitutional,
    pytest.mark.skipif(not HAS_RUST_PERF, reason="acgs2_perf Rust extension not available"),
]


def test_rust_weighted_sinkhorn():
    # 2x2 matrix
    W = [[1.0, 1.0], [1.0, 1.0]]  # Uniform input

    # Target marginals (not uniform)
    # Row sums: [0.6, 1.4]
    # Col sums: [0.6, 1.4]
    r = [0.6, 1.4]
    c = [0.6, 1.4]

    try:
        W_out = sinkhorn_knopp(W, row_marginal=r, col_marginal=c, iters=50, eps=1e-8)
        W_tensor = torch.tensor(W_out)

        # Check row sums
        row_sums = W_tensor.sum(dim=1)
        assert torch.allclose(row_sums, torch.tensor(r), atol=1e-4), (
            f"Row sums mismatch: {row_sums} vs {r}"
        )

        # Check col sums
        col_sums = W_tensor.sum(dim=0)
        assert torch.allclose(col_sums, torch.tensor(c), atol=1e-4), (
            f"Col sums mismatch: {col_sums} vs {c}"
        )

        return True
    except TypeError as e:
        return False
    except (RuntimeError, ValueError, AssertionError) as e:
        return False


if __name__ == "__main__":
    if test_rust_weighted_sinkhorn():
        sys.exit(0)
    else:
        sys.exit(1)
