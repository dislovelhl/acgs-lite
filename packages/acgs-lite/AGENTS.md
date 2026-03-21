# ACGS-Lite

> Scope: `packages/acgs-lite/` — standalone governance library published as `acgs-lite`.

## Planning

- Planning notes live in `PLANS.md`.

## Structure

```
acgs-lite/
├── src/acgs_lite/
│   ├── engine/              # Core validation and execution logic
│   ├── constitution/        # Constitution loading, templates, policy export
│   ├── compliance/          # Compliance mapping and regulatory helpers
│   ├── integrations/        # Adapter modules for external agent ecosystems
│   ├── governed.py          # GovernedAgent / GovernedCallable wrappers
│   ├── maci.py              # MACI role enforcement
│   ├── matcher.py           # Rule matching hot path
│   ├── audit.py             # Tamper-evident audit trail
│   ├── cli.py               # `acgs-lite` CLI entrypoint
│   └── server.py            # FastAPI wrapper
├── src/eu_ai_act_tool/      # EU AI Act assessment tool
├── rust/                    # Optional Rust workspace (`core/`, `pyo3/`, `wasm/`)
├── tests/                   # Python package tests
└── examples/                # Quickstarts and examples
```

## Where to Look

| Task | Location |
| ---- | -------- |
| Add governance rule type | `src/acgs_lite/constitution/` |
| Change validation logic | `src/acgs_lite/engine/`, `src/acgs_lite/matcher.py` |
| Add integration adapter | `src/acgs_lite/integrations/` |
| Compliance framework work | `src/acgs_lite/compliance/` |
| MACI role boundaries | `src/acgs_lite/maci.py` |
| MCP server tools | `src/acgs_lite/integrations/mcp_server.py` |
| GitLab governance integration | `src/acgs_lite/integrations/gitlab.py` |
| Audit trail | `src/acgs_lite/audit.py` |
| CLI commands | `src/acgs_lite/cli.py` |
| Rust acceleration | `rust/` |

## Conventions

- Package runtime target is Python 3.10+.
- Keep integrations optional through extras and lazy imports.
- Keep Python fallbacks when Rust acceleration is optional.
- Constitutional hash `cdd01ef066bc6cf2` is part of validation flows.
- Use `_make_*` helpers in tests for fixture creation when available.

## Anti-Patterns

- Do not import optional platform SDKs at module import time.
- Do not change `matcher.py` hot-path behavior without benchmarking or targeted tests.
- Do not bypass MACI enforcement in wrappers or integrations.
- Do not rely on raw `cargo test` as the only verification for Python-facing Rust changes.

## Commands

```bash
make test-lite
python -m pytest packages/acgs-lite/tests/ -v --import-mode=importlib
cd packages/acgs-lite/rust && maturin develop --release
acgs-lite status
```

If you touch the Rust-backed validation path, rebuild with `maturin develop --release` and then
run the relevant pytest selection from the repo root.
