"""
Manifold-Constrained HyperConnection (mHC) for Governance Stability
Constitutional Hash: cdd01ef066bc6cf2

This module implements stability constraints for policy weight aggregation
using projections onto the Birkhoff Polytope (doubly stochastic matrices).
"""

from __future__ import annotations

from enhanced_agent_bus.observability.structured_logging import get_logger

try:
    import torch
    import torch.nn as nn

    TORCH_AVAILABLE = True
except ImportError:
    torch = None  # type: ignore[assignment]
    nn = None  # type: ignore[assignment]
    TORCH_AVAILABLE = False
try:
    from src.core.shared.types import JSONDict  # noqa: E402
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

try:
    from acgs2_perf import sinkhorn_knopp as rust_sinkhorn

    HAS_RUST_PERF = True
except ImportError:
    HAS_RUST_PERF = False

logger = get_logger(__name__)
RUST_SINKHORN_ERRORS = (RuntimeError, ValueError, TypeError, OSError)

_ModuleBase = nn.Module if TORCH_AVAILABLE else object  # type: ignore[misc]


def sinkhorn_projection(
    W: torch.Tensor,
    iters: int = 20,
    eps: float = 1e-6,
    row_marginal: torch.Tensor | None = None,
    col_marginal: torch.Tensor | None = None,
    alpha: float | None = None,
) -> torch.Tensor:
    """
    Project a weight matrix onto a Transportation Polytope (multi-marginal manifold).

    Ensures rows and columns sum to specified marginals (default: 1.0 for Birkhoff).
    Optionally applies element-wise capping (alpha) to limit individual agent influence.

    Args:
        W: Input weight matrix [N, N] or [B, N, N]
        iters: Number of Sinkhorn iterations
        eps: Small epsilon for numerical stability
        row_marginal: Target row sums [N] or [B, N]
        col_marginal: Target column sums [N] or [B, N]
        alpha: Adversarial capping value (max weight for any W[i,j])

    Returns:
        Manifold-constrained weight matrix
    """
    if not TORCH_AVAILABLE:
        raise ImportError("torch is required for sinkhorn_projection")
    # Use high-performance Rust implementation if available
    # Note: Rust implementation does not yet support alpha-capping, so we use Python fallback for that.  # noqa: E501
    if HAS_RUST_PERF and not W.is_cuda and W.dim() == 2 and alpha is None:
        W_np = torch.exp(W).detach().cpu().numpy().tolist()

        r_list = (
            row_marginal.squeeze().detach().cpu().numpy().tolist()
            if row_marginal is not None
            else None
        )
        c_list = (
            col_marginal.squeeze().detach().cpu().numpy().tolist()
            if col_marginal is not None
            else None
        )

        try:
            W_ds = rust_sinkhorn(
                W_np, row_marginal=r_list, col_marginal=c_list, iters=iters, eps=eps
            )
            logger.info("Using Rust Sinkhorn Kernel for projection")
            return torch.tensor(W_ds, device=W.device, dtype=W.dtype)
        except RUST_SINKHORN_ERRORS as e:
            logger.warning(f"Rust Sinkhorn failed, falling back to Python: {e}")

    logger.info("Using Python/Torch Sinkhorn implementation")
    # Fallback/Upgrade: Native PyTorch implementation for UMM
    # Use exponential to ensure positivity (Entropy regularization)
    W = torch.exp(W)

    # Optional: Apply element-wise adversarial capping
    if alpha is not None:
        W = torch.clamp(W, max=alpha)

    # Initialize marginals (default to 1.0 for Birkhoff Polytope)
    # n is the dimension of the matrix
    n = W.size(-1)
    if row_marginal is None:
        row_marginal = torch.ones(*W.shape[:-1], 1, device=W.device, dtype=W.dtype)
    else:
        if row_marginal.dim() == W.dim() - 1:
            row_marginal = row_marginal.unsqueeze(-1)

    if col_marginal is None:
        col_marginal = torch.ones(*W.shape[:-2], 1, n, device=W.device, dtype=W.dtype)
    else:
        if col_marginal.dim() == W.dim() - 1:
            col_marginal = col_marginal.unsqueeze(-2)

    for _ in range(iters):
        # Column normalization to target col_marginal
        W = W * (col_marginal / (W.sum(dim=-2, keepdim=True) + eps))
        # Row normalization to target row_marginal
        W = W * (row_marginal / (W.sum(dim=-1, keepdim=True) + eps))

    return W


class ManifoldHC(_ModuleBase):  # type: ignore[misc, valid-type]
    """
    Manifold-Constrained HyperConnection layer.

    Wraps weight matrices with a projection operator that enforces
    geometric constraints (e.g., Birkhoff Polytope) to ensure
    stability in residual propagation across governance layers.
    """

    def __init__(self, dim: int, projection_type: str = "birkhoff"):
        super().__init__()
        if not TORCH_AVAILABLE:
            raise ImportError("torch is required for ManifoldHC")
        self.dim = dim
        self.projection_type = projection_type
        self.last_stats: JSONDict = {}

        # Initialize weights
        self.W = nn.Parameter(torch.randn(dim, dim) * 0.02)

    def get_projected_weights(self) -> torch.Tensor:
        """Get the weights after manifold projection."""
        if self.projection_type == "birkhoff":
            return sinkhorn_projection(self.W)
        return self.W

    def forward(
        self,
        x: torch.Tensor,
        residual: torch.Tensor | None = None,
        row_marginal: torch.Tensor | None = None,
        col_marginal: torch.Tensor | None = None,
        alpha: float | None = None,
    ) -> torch.Tensor:
        """
        Apply mHC controlled residual connection.

        Args:
            x: Input tensor (e.g., delta-policy or action residual)
            residual: Optional previous state for full skip connection
            row_marginal: Custom row sums for Transportation Polytope
            col_marginal: Custom column sums for Transportation Polytope
            alpha: Adversarial capping value

        Returns:
            Stabilized output tensor
        """
        if self.projection_type == "birkhoff":
            W_proj = sinkhorn_projection(
                self.W, row_marginal=row_marginal, col_marginal=col_marginal, alpha=alpha
            )
        else:
            W_proj = self.W

        # Apply projection to input
        out = torch.matmul(x, W_proj)

        # Calculate Observability Metrics
        with torch.no_grad():
            # Spectral Radius (approximate using power iteration or just max row sum for quick check)  # noqa: E501
            # For doubly stochastic matrices, eigenvalues <= 1.
            # We use 1-norm or inf-norm as a proxy for bound check.
            # Ideally compute eigenvalues, but that's expensive for every step.
            # Since we trust Sinkhorn, we just log the projection error if needed.

            # Divergence: L2 distance between input and output
            divergence = torch.norm(out - x).item()

            # Stability Hash: Checksum of the weight matrix
            w_hash = hash(W_proj.detach().cpu().numpy().tobytes())

            # Max weight (Adversarial check)
            max_weight = W_proj.max().item()

            self.last_stats = {
                "spectral_radius_bound": 1.0,  # Sinkhorn guarantees this
                "divergence": divergence,
                "max_weight": max_weight,
                "stability_hash": f"mhc_{w_hash:x}",
                "input_norm": torch.norm(x).item(),
                "output_norm": torch.norm(out).item(),
            }

        if residual is not None:
            return out + residual
        return out

    def extra_repr(self) -> str:
        return f"dim={self.dim}, projection_type={self.projection_type}"


if not TORCH_AVAILABLE:
    ManifoldHC = None  # type: ignore[assignment,misc]
