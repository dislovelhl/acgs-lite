# ACGS-Lite

For repo-wide rules, see `/AGENTS.md`. Use `/CLAUDE.md` only if a tool specifically loads it.

## Structure

```
src/acgs_lite/
├── constitution/     # Constitution models, loading, templates, export
├── engine/           # Validation engine and execution helpers
├── compliance/       # Compliance mapping and assessment helpers
├── integrations/     # External ecosystem adapters
├── audit.py          # Audit trail
├── governed.py       # Governed wrappers
├── maci.py           # MACI enforcement
├── eu_ai_act/        # EU AI Act assessment subpackage
└── server.py         # FastAPI wrapper

rust/
├── core/             # Core Rust crate
├── pyo3/             # Python bindings crate
├── wasm/             # WASM target
└── src.legacy/       # Legacy Rust sources kept for reference/migration
```

## Testing

```bash
# From repo root
python -m pytest packages/acgs-lite/tests/ -v --import-mode=importlib

# From package root (preferred for acgs-lite-only work)
cd packages/acgs-lite
make test            # full suite
make test-quick      # skip slow/benchmark tests
make test-cov        # coverage report → htmlcov/
make test-examples   # smoke-test all examples/

# Rust-backed tests (only needed when Rust paths change)
cd packages/acgs-lite/rust && maturin develop --release
```

**No API keys required.** All tests use `InMemory*` stubs for external deps.
Set placeholder keys to silence import-time validation:
```bash
export OPENAI_API_KEY=test-key-for-unit-tests
export ANTHROPIC_API_KEY=test-key-for-unit-tests
```

## Mock/Stub Pattern (Pluggable Protocol)

Every external dependency is defined as a `typing.Protocol` with an `InMemory*`
stub for tests. **Never import live services in test code.**

```
typing.Protocol              ← interface (structural typing, no inheritance)
     ↑                              ↑
InMemory*Stub                RealImplementation
(tests, CI — zero I/O)       (production — swap at runtime)
```

### Built-in stubs

| Protocol | InMemory stub | Where |
|----------|--------------|-------|
| `GovernanceStateBackend` | `InMemoryGovernanceStateBackend` | `acgs_lite.openshell_state` |
| `ChainSubmitter` | `InMemorySubmitter` | `constitutional_swarm.bittensor.chain_anchor` |
| `ArweaveClient` | `InMemoryArweaveClient` | `constitutional_swarm.bittensor.arweave_audit_log` |

### Pattern rules

1. **Protocol first** — define the interface before any implementation
2. **`InMemory*` ships with the Protocol** — always in the same module
3. **No `isinstance()` checks on Protocol types** — duck typing only
4. **Add `save_calls` / `load_calls` lists** to stubs for assertion in tests
5. **Chaos stubs for error paths** — `class FailingFoo` raises always

See [`examples/mock_stub_testing/`](examples/mock_stub_testing/) for a full walkthrough.

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
