# ACGS-Lite

> Scope: `packages/acgs-lite/` — Standalone governance library. `pip install acgs-lite`.

## Planning

- Planning notes live in [PLANS.md](PLANS.md).

## Structure

```
acgs-lite/
├── src/acgs_lite/
│   ├── engine/              # GovernanceEngine core (validation, batch, metrics)
│   ├── constitution/        # Constitution loader, builder, templates, diff, merge
│   ├── compliance/          # 9-framework regulatory assessor (EU AI Act, NIST, ISO, GDPR…)
│   ├── eu_ai_act/           # EU AI Act self-assessment tool
│   ├── integrations/        # 11 platform integrations + MCP server + GitLab bot
│   ├── governed.py          # GovernedAgent / GovernedCallable wrappers
│   ├── maci.py              # MACI enforcer (4 roles, separation of powers)
│   ├── matcher.py           # Aho-Corasick + regex rule matching (560ns P50)
│   ├── audit.py             # Tamper-evident audit trail (chain-verified)
│   ├── cli.py               # `acgs-lite` CLI (activate, status, verify)
│   ├── server.py            # FastAPI microservice wrapper
│   └── errors.py            # Exception hierarchy
├── rust/                    # PyO3 Rust extension (optional, 10-50x speedup)
├── tests/                   # 286 tests
└── examples/                # Quickstart examples
```

## Where to Look

| Task                       | Location                              |
| -------------------------- | ------------------------------------- |
| Add governance rule type   | `constitution/models.py`              |
| Change validation logic    | `engine/`, `matcher.py`               |
| Add platform integration   | `integrations/` (copy existing)       |
| Compliance framework       | `compliance/` + `eu_ai_act/`          |
| MACI role boundaries       | `maci.py`                             |
| MCP server tools           | `integrations/mcp_server.py`          |
| GitLab MR governance       | `integrations/gitlab.py`              |
| Audit trail                | `audit.py`                            |
| CLI commands               | `cli.py`                              |
| Rust acceleration          | `rust/src/` (PyO3, maturin)           |

## Conventions

- Library targets Python 3.10+ (broader compat than platform).
- All integrations are optional extras: `acgs-lite[openai]`, `acgs-lite[mcp]`, etc.
- Rust extension is optional — Python fallback always exists.
- Constitutional hash `cdd01ef066bc6cf2` embedded in all validation paths.
- `Constitution.from_template("gitlab")` for zero-config governance.
- `_make_*` factory functions in tests for fixture creation.

## Anti-Patterns

- Do not import platform SDKs at module level — lazy-load in integration modules.
- Do not modify `matcher.py` hot path without benchmarking (560ns P50 target).
- Do not skip MACI checks — `maci.py` enforces that proposers cannot self-validate.
- Rust extension: `maturin develop --release` then `pytest` (not `cargo test`).

## Commands

### Dev / Build / Test Loop

- If you change Python code or docs, run `pytest packages/acgs-lite/tests/ -v` from the package root after the edit.
- If you change the Rust extension, run `maturin develop --release` first, then run `pytest packages/acgs-lite/tests/ -v`.
- Treat the loop as successful when the command exits with status `0` and pytest reports all selected tests passing.

```bash
make test-lite                        # Run acgs-lite tests only
pytest packages/acgs-lite/tests/ -v   # Direct pytest
acgs-lite activate <key>              # License activation
acgs-lite status                      # Show tier/features
```
