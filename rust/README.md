# ACGS-2 Governance Engine (Rust/PyO3)

## Overview

This is the high-performance governance validation engine for ACGS-2,
implemented in Rust with a pure core crate and a thin PyO3 companion wheel.

**Constitutional Hash:** `608508a9bd224290`

## Modules

| Path | Purpose |
|--------|---------|
| `core/` | Supported native validator core with hot/full validation paths |
| `pyo3/` | Supported Python companion wheel, exported as `acgs_lite_rust` |
| `wasm/` | WASM build of the same validator core |
| `spacetime_governance/` | Experimental standalone SpacetimeDB module; excluded from the shipping workspace |

## Build

Build the extension in release mode:

```bash
cd packages/acgs-lite/rust
maturin build --release
```

The compiled wheel is placed in `target/wheels/`.

The workspace members are the shipping path: `core`, `pyo3`, and `wasm`.
`spacetime_governance/` is intentionally standalone so wheel builds do not
pull SpacetimeDB dependencies.

## Installation

Install the compiled wheel:

```bash
pip install target/wheels/acgs_lite_rust-*.whl
```

Or during development with editable install:

```bash
pip install -e .
```

## Testing

Run Rust unit tests:

```bash
cd packages/acgs-lite/rust
cargo test
cargo test --manifest-path spacetime_governance/Cargo.toml
```

Run integration tests from Python:

```bash
python -m pytest tests/core/shared/test_governance_engine.py -v
```

## Python API

### Supported API

The supported `acgs_lite_rust` Python API is intentionally small:

- `GovernanceValidator`
- `ALLOW`
- `DENY_CRITICAL`
- `DENY`

`ImpactScorer` is not exported by the supported companion wheel. Impact
scoring remains Python-first in `acgs_lite.scoring`; the `RustScorer`
compatibility wrapper only activates if a future or private native module
exports `ImpactScorer` explicitly.

### GovernanceValidator

Main class for governance validation.

```python
from acgs_lite_rust import GovernanceValidator, ALLOW, DENY, DENY_CRITICAL

validator = GovernanceValidator()

# Fast path validation (hot)
result = validator.validate_hot(
    content="user message",
    context={"policy_id": "pol_123"}
)

# Full validation with all checks
result = validator.validate_full(
    content="user message",
    context={"policy_id": "pol_123", "user_role": "admin"}
)

# Result contains:
# - severity: ALLOW, DENY, or DENY_CRITICAL
# - matched_rules: list of rule IDs that matched
# - reasoning: explanation of decision
```

### Severity Constants

```python
from acgs_lite_rust import ALLOW, DENY, DENY_CRITICAL

# ALLOW (0) — Message passes governance checks
# DENY (1) — Message violates policy but recoverable
# DENY_CRITICAL (2) — Message violates critical governance rule
```

## Fallback Behavior

When the Rust extension is not available (build failure, Python version mismatch), the system falls back to the pure Python implementation in `packages/acgs-lite/src/acgs_lite/engine/core.py`. The Python fallback maintains feature parity with the Rust version.

## Performance

Typical latency:
- Hot path (fast validation): <0.5ms P99
- Full path (complete validation): <2ms P99
- Throughput: >5000 validations/sec

## Development Notes

- **PyO3 version**: see `pyo3/Cargo.toml`
- **Optimization level**: 3 (O3) with LTO and single codegen unit
- **Panic mode**: abort (prevents unwinding into Python)
