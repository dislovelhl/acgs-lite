"""LEGACY: Constitutional Hash 608508a9bd224290.

Canonical context subsystem is ``context_memory/``.
New code should not add modules in this package.
"""

from .mamba_hybrid import (
    CONSTITUTIONAL_HASH,
    TORCH_AVAILABLE,
    ConstitutionalContextProcessor,
    ConstitutionalMambaHybrid,
    Mamba2SSM,
    SharedAttentionLayer,
)

__all__ = [
    "CONSTITUTIONAL_HASH",
    "TORCH_AVAILABLE",
    "ConstitutionalContextProcessor",
    "ConstitutionalMambaHybrid",
    "Mamba2SSM",
    "SharedAttentionLayer",
]
