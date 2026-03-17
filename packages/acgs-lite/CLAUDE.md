# ACGS-Lite (Constitutional Governance Engine)

**For project-wide instructions, see the root `/CLAUDE.md`.**

## Structure

```
src/acgs_lite/
  ├── constitution/     # Core governance: Rule, Constitution, analytics, metrics, versioning
  ├── engine/           # Validation engine (Python + Rust/PyO3 backend)
  ├── maci.py           # MACI role enforcement
  ├── compliance/       # Compliance mapping, regulatory alignment
  └── eu_ai_act/        # EU AI Act risk classification

rust/src/               # PyO3 native extension (6 modules)
  ├── validator.rs      # Core rule validation
  ├── severity.rs       # Severity enum + ordering
  ├── verbs.rs          # Action verb parsing
  ├── result.rs         # Validation result types
  ├── context.rs        # Governance context
  └── hash.rs           # Constitutional hash computation
```

## Testing

```bash
python -m pytest packages/acgs-lite/tests/ -v --import-mode=importlib   # Python tests (from project root)
cd packages/acgs-lite/rust && cargo test                                 # Rust tests
cd packages/acgs-lite/rust && cargo bench                                # Benchmarks (560ns P50)
```

## Rust Build

```bash
cd packages/acgs-lite/rust
maturin develop --release    # Build PyO3 extension into venv
cargo clippy                 # Lint
cargo audit                  # Security audit (4 ignored CVEs in CI)
```

## Autoresearch

The autoresearch system runs governance-quality experiments against the constitution engine.
See `autoresearch/program.md` for the experiment loop and `autoresearch/results.tsv` for history.

## Gotchas

- **Python 3.10+ minimum** (more permissive than root project's 3.11+)
- **`constitution/__init__.py`** uses `__getattr__` lazy loading — imports are deferred until accessed
- **Rust extension optional** — Python fallback exists, but Rust is 100-1000x faster for hot paths
- **Cargo audit ignores**: RUSTSEC-2025-0123, RUSTSEC-2024-0387, RUSTSEC-2024-0436, RUSTSEC-2025-0134 in CI
