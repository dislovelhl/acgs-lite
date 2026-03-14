"""Governance validation engine.

The engine evaluates actions against constitutional rules and produces
structured validation results with full audit trails.

Constitutional Hash: cdd01ef066bc6cf2
"""

from __future__ import annotations

# Optional Aho-Corasick C extension for O(n) keyword scanning
try:
    import ahocorasick as _ac

    _HAS_AHO = True
except ImportError:
    _HAS_AHO = False

# Optional Rust hot-path extension (exp79/80: PyO3 native validate loop)
try:
    import acgs_lite_rust as _rust

    _HAS_RUST = True
    _RUST_ALLOW = _rust.ALLOW
    _RUST_DENY_CRITICAL = _rust.DENY_CRITICAL
    _RUST_DENY = _rust.DENY
except ImportError:
    _HAS_RUST = False
    _RUST_ALLOW = 0
    _RUST_DENY_CRITICAL = 1
    _RUST_DENY = 2
