# AGENTS.md - Enhanced Agent Bus (Rust Kernels)

Scope: `src/core/enhanced_agent_bus/rust/`

## OVERVIEW

Performance-critical Rust extensions for the Enhanced Agent Bus. These kernels provide SIMD-accelerated security scanning, parallel governance validation, and geometric tensor projections (Sinkhorn-Knopp) to ensure sub-millisecond P99 latency.

## STRUCTURE

- `src/lib.rs`: PyO3 entry point; implements the `MessageProcessor` orchestration logic.
- `src/tensor_ops.rs`: Parallel BERT embedding pooling using Rayon.
- `src/optimization.rs`: Birkhoff stabilization via Sinkhorn-Knopp algorithm.
- `src/opa.rs`: High-throughput OPA client with Moka-based in-memory caching.
- `src/security.rs`: SIMD-optimized prompt injection detection.
- `src/deliberation.rs`: Adaptive routing and impact scoring logic.

## WHERE TO LOOK

- Parallel Validation: `MessageProcessor::validate_message_parallel` in `lib.rs`.
- Prompt Injection (primary): `PromptGuard::detect` in `prompt_guard.rs` — full 3-phase scan (Aho-Corasick → regex → heuristics).
- Prompt Injection (legacy): `detect_prompt_injection` in `security.rs` — kept for backward-compat; `process_internal` now runs both.
- Geometric Projections: `sinkhorn_knopp_stabilize` in `optimization.rs`.
- In-Memory Cache: `OpaClient` implementation in `opa.rs`.

## CONVENTIONS

- **Parallelism**: Use `Rayon` for all CPU-bound tensor/validation operations.
- **Safety**: Prefer safe Rust; `unsafe` is strictly for SIMD/FFI performance and must be documented.
- **Interop**: Map all internal errors to `PyErr` via `thiserror` for seamless Python integration.
- **Compliance**: `CONSTITUTIONAL_HASH` is defined **once** in `src/crypto.rs` and re-exported via `lib.rs`. Do not re-define it in other modules — import it with `use crate::crypto::CONSTITUTIONAL_HASH;`.
- **Lints**: The crate root has `#![deny(clippy::unwrap_used, clippy::expect_used, clippy::panic)]`. All `unwrap()` usages require explicit `#[allow]` with a justification comment.

## ANTI-PATTERNS

- **Tokio Block**: Do not perform heavy CPU operations directly in async tasks; use `spawn_blocking`.
- **Large Clones**: Avoid cloning `AgentMessage` in the hot path; use `Arc` or references.
- **Panic**: Never use `unwrap()` or `panic!`; always return `Result` for Python bubble-up.
- **Duplicate CONSTITUTIONAL_HASH**: Adding `pub const CONSTITUTIONAL_HASH = ...` to any module is now a compile error — import from `crate::crypto` instead.
- **Scanning only `content`**: All injection detection must iterate both `message.content.values()` and `message.payload.values()`.

## BUILD & TEST

```bash
# Type-check (fast, no Python needed)
cargo check

# Compile tests (no Python needed)
cargo check --tests

# Full build + Python extension (requires maturin)
pip install maturin
maturin develop --release

# Run tests via Python after maturin develop
pytest tests/
```

Note: `cargo test` fails to link because PyO3 `extension-module` crates defer Python symbol resolution to Python's runtime loader. Use `maturin develop` + pytest for integration testing.
