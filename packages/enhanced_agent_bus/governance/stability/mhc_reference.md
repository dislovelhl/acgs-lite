# Technical Reference: Manifold-Constrained HyperConnections (mHC)

Definitive technical documentation for the ACGS-2 Governance Stability system.

## Overview

Manifold-Constrained HyperConnections (mHC) provide mathematical stability for hierarchical governance deliberation. By projecting policy weight matrices onto the Birkhoff Polytope (doubly stochastic manifold), we ensure that residual information propagation satisfies a spectral radius bound of &le; 1.0, preventing weight divergence in deep agent networks.

---

## Quick Reference

| Component   | Key Interface                   | Purpose                              |
| :---------- | :------------------------------ | :----------------------------------- |
| **Python**  | `sinkhorn_projection()`         | High-level API for matrix projection |
| **Rust**    | `acgs2_perf.sinkhorn_knopp()`   | Performance-optimized kernel         |
| **PyTorch** | `ManifoldHC` (nn.Module)        | Neural layer for stable aggregation  |
| **API**     | `/governance/stability/metrics` | Real-time observability              |

---

## Detailed Reference: Python API

### `sinkhorn_projection`

**Type**: `Function`
**Location**: `src/core/enhanced_agent_bus/governance/stability/mhc.py`

**Description**:
Projects a weight matrix onto a Transportation Polytope (multi-marginal manifold). Ensures rows and columns sum to specified marginals.

**Parameters**:

- `W` (torch.Tensor): Input weight matrix of shape `[N, N]` (or `[B, N, N]`).
- `iters` (int): Number of Sinkhorn iterations. Default: `20`.
- `eps` (float): Numerical stability epsilon. Default: `1e-6`.
- `row_marginal` (Optional[torch.Tensor]): Target row sums. Default: `1.0`.
- `col_marginal` (Optional[torch.Tensor]): Target column sums. Default: `1.0`.
- `alpha` (Optional[float]): Adversarial capping value (max individual weight).

**Returns**:

- `torch.Tensor`: Manifold-constrained weight matrix.

**Implementation Note**:
Uses the Rust `acgs2_perf` kernel if available and `alpha` is `None`. Falls back to PyTorch implementation for CUDA tensors or capped projections.

---

### `ManifoldHC`

**Type**: `class (nn.Module)`
**Location**: `src/core/enhanced_agent_bus/governance/stability/mhc.py`

**Description**:
A stabilizing layer for governance residuals. Wraps wait aggregation with mHC projection logic.

**Initialization**:

- `dim` (int): Dimension of the weight matrix.
- `projection_type` (str): Type of manifold (e.g., `"birkhoff"`).

**Methods**:

- `forward(x, residual=None, ...)`: Applies projection to input `x` and adds optional `residual`.

**Observability Metrics**:
Stored in `self.last_stats`:

- `spectral_radius_bound`: Guaranteed &le; 1.0.
- `divergence`: L2 distance of projection.
- `stability_hash`: Auditable checksum of weights.

---

## Detailed Reference: Rust Performance Kernel

### `acgs2_perf.sinkhorn_knopp`

**Type**: `Native Function (PyO3)`
**Location**: `src/core/rust-perf/src/lib.rs`

**Description**:
Optimized implementation of the Sinkhorn-Knopp algorithm using `ndarray`. Designed for low-latency execution on large agent networks (up to 2000+ agents).

**Signature**:

```python
def sinkhorn_knopp(
    w_vec: List[List[float]],
    row_marginal: Optional[List[float]] = None,
    col_marginal: Optional[List[float]] = None,
    iters: int = 20,
    eps: float = 1e-6
) -> List[List[float]]
```

**Throws**:

- `ValueError`: If matrix is not square (when marginals are uniform) or if marginal dimensions mismatch.

---

## Detailed Reference: REST API

### `GET /governance/stability/metrics`

**Endpoint**: `http://localhost:8100/governance/stability/metrics`
**Tags**: `Governance`

**Description**:
Exposes real-time stability telemetry from the active governance layer.

**Response Schema**:

```json
{
  "spectral_radius_bound": 1.0,
  "divergence": 0.0012,
  "max_weight": 0.45,
  "stability_hash": "mhc_af31b2...",
  "input_norm": 10.5,
  "output_norm": 10.49
}
```

---

## Troubleshooting & Best Practices

- **Warning**: High `divergence` values indicates that initial weights were very far from the stability manifold. Consider small initialization scales.
- **Note**: The Rust kernel requires the `acgs2_perf` package to be compiled. Use `maturin develop` or the provided Dockerfile.
- **Tip**: For adversarial environments, always set `alpha` (e.g., `alpha=0.2`) to prevent individual agents from dominating policy decisions through high weights.

**See Also**:

- [mHC Stability Theory](file:///home/martin/ACGS/src/core/enhanced_agent_bus/governance/stability/mhc_stability.md)
- [Staging Deployment Script](file:///home/martin/ACGS/scripts/deploy_governance_staging.sh)
