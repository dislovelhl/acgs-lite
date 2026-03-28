# ACGS-Lite

For repo-wide rules, see `/CLAUDE.md`.

## Structure

```
src/acgs_lite/
├── _meta.py          # Package metadata
├── cli.py            # CLI entry point
├── cli/              # CLI subcommands
├── commands/         # Command implementations (assess, init, lifecycle, observe, etc.)
├── compliance/       # Compliance mapping and assessment helpers
├── constitution/     # Constitution models, loading, templates, export
├── engine/           # Validation engine and execution helpers
├── errors.py         # Error definitions including ConstitutionalViolationError
├── eu_ai_act/        # EU AI Act compliance module
├── integrations/     # External ecosystem adapters
├── licensing.py      # Licensing logic
├── matcher.py        # Pattern/rule matching
├── middleware.py     # Middleware utilities
├── openshell.py      # Interactive shell
├── report.py         # Reporting utilities
├── schema/           # Data schemas
├── audit.py          # Audit trail
├── governed.py       # Governed wrappers
├── maci.py           # MACI enforcement
└── server.py         # FastAPI wrapper

src/eu_ai_act_tool/   # EU AI Act assessment app

rust/
├── core/                    # Core Rust crate
├── pyo3/                    # Python bindings crate
├── spacetime_governance/    # Spacetime governance crate
├── wasm/                    # WASM target
└── src.legacy/              # Legacy Rust sources kept for reference/migration
```

## Testing

```bash
make test-lite  # shortcut
python -m pytest packages/acgs-lite/tests/ -v --import-mode=importlib
cd packages/acgs-lite/rust && maturin develop --release
```

Use `maturin develop --release` before pytest when your change affects the Python-facing Rust
extension path.

## Rust Build

```bash
cd packages/acgs-lite/rust
maturin develop --release
```

If you add Rust-only logic, keep the Python fallback behavior intact and verify the Python test
surface, not only the Rust workspace.

## Gotchas

- `GovernanceEngine.validate()` raises `ConstitutionalViolationError` on violations — it does
  not return a result with `valid=False`. Catch the exception to inspect violations.
- Package minimum runtime is Python 3.10.
- Many integrations are optional extras; preserve lazy import behavior.
- Rust acceleration is optional and should not become mandatory for baseline tests.
- Benchmarks and latency claims in docs drift quickly; prefer measured results over hard-coded
  numbers when updating docs.
