"""
ACGS-2 Governance Stability Layer
Constitutional Hash: cdd01ef066bc6cf2

This subpackage provides manifold-constrained stability projections for governance.
"""

from .mhc import ManifoldHC, sinkhorn_projection

__all__ = ["ManifoldHC", "sinkhorn_projection"]
