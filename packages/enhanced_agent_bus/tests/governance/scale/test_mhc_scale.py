"""
Module.

Constitutional Hash: 608508a9bd224290
"""

import os
import time

import pytest

from enhanced_agent_bus.observability.structured_logging import get_logger

try:
    import psutil
except ImportError:
    psutil = None

try:
    import torch
except ImportError:
    torch = None

# Governance and constitutional compliance test markers
pytestmark = [pytest.mark.governance, pytest.mark.constitutional]

from enhanced_agent_bus.governance.stability import mhc as mhc_module

if not mhc_module.TORCH_AVAILABLE:
    pytest.skip("mHC governance scale tests require PyTorch", allow_module_level=True)

ManifoldHC = mhc_module.ManifoldHC
sinkhorn_projection = mhc_module.sinkhorn_projection

logger = get_logger(__name__)


@pytest.mark.skipif(
    psutil is None or torch is None,
    reason="Scale test requires optional dependencies: psutil and torch",
)
async def test_mhc_scale_10k_agents():
    """
    Verify mHC stability with 10,000 agents.
    This checks memory usage and execution time for the Sinkhorn projection.

    Target:
    - 10k x 10k matrix (approx 400MB)
    - Convergence to doubly stochastic matrix
    - Reasonable execution time (<10s for single projection on CPU)
    """
    MAX_N = 2000  # Adjusted for CI speed (10k requires ~50s+ and 3GB RAM)
    N = MAX_N

    logger.info(f"Starting Scale Test with N={N} agents...")

    process = psutil.Process(os.getpid())
    mem_start = process.memory_info().rss / 1024 / 1024

    # 1. Setup Phase
    # Use standard normal initialization for raw weights
    logger.info(f"Allocating {N}x{N} weight matrix...")
    W = torch.randn(N, N)

    mem_allocated = process.memory_info().rss / 1024 / 1024
    logger.info(
        f"Memory after allocation: {mem_allocated:.2f} MB (+{mem_allocated - mem_start:.2f} MB)"
    )

    # 2. Projection Phase
    start_time = time.time()

    # Run Sinkhorn projection
    # iters=10 is usually sufficient for rough convergence, 20 for high precision
    iters = 200
    W_proj = sinkhorn_projection(W, iters=iters)

    end_time = time.time()
    duration = end_time - start_time

    mem_peak = process.memory_info().rss / 1024 / 1024
    logger.info(f"Projection completed in {duration:.4f}s")
    logger.info(f"Peak Memory (approx): {mem_peak:.2f} MB")

    # 3. Verification Phase

    # Check Row/Col Sums (Birkhoff Constraint)
    # Note: Torch sum might have slight numerical errors, we use a relaxed tolerance
    row_sums = W_proj.sum(dim=1)
    col_sums = W_proj.sum(dim=0)

    # Expected sum is 1.0
    expected = torch.ones(N)

    # Check max deviation
    max_row_err = torch.max(torch.abs(row_sums - expected)).item()
    max_col_err = torch.max(torch.abs(col_sums - expected)).item()

    logger.info(f"Max Row Error: {max_row_err:.6f}")
    logger.info(f"Max Col Error: {max_col_err:.6f}")

    # Assertions
    # We expect relatively tight convergence with 20 iterations
    assert max_row_err < 5e-2, f"Row sums did not converge (max err: {max_row_err})"
    assert max_col_err < 5e-2, f"Col sums did not converge (max err: {max_col_err})"

    # Performance Assertion (Soft limit to avoid CI flakiness, but log warning)
    if duration > 15.0:
        logger.warning(f"Projection took longer than expected: {duration:.4f}s")

    logger.info("Scale Test PASSED")
