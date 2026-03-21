# AGENTS.md - Enhanced Agent Bus (Rust Kernels)

Scope: `packages/enhanced_agent_bus/rust/`

## Overview

Rust kernels for performance-sensitive enhanced-agent-bus paths. This workspace contains the PyO3
extension crate plus benches and supporting modules for security scanning, optimization, OPA, and
deliberation-related helpers.

## Structure

- `src/lib.rs`: PyO3 entrypoint and exported module surface.
- `src/crypto.rs`: constitutional hash and crypto helpers.
- `src/audit.rs`: audit-related helpers.
- `src/opa.rs`: OPA client helpers.
- `src/security.rs`, `src/prompt_guard.rs`: security and prompt-injection checks.
- `src/optimization.rs`, `src/parallel_optimizer.rs`, `src/tensor_ops.rs`, `src/simd_ops.rs`:
  optimization and numerical kernels.
- `src/deliberation.rs`: deliberation helpers.
- `src/metrics.rs`, `src/error.rs`: metrics and error plumbing.
- `benches/kernel_benchmarks.rs`: Rust benchmarks.

## Where to Look

- PyO3 surface: `src/lib.rs`
- Constitutional hash handling: `src/crypto.rs`
- Prompt guard logic: `src/prompt_guard.rs`
- Security scanning: `src/security.rs`
- Optimization kernels: `src/optimization.rs`, `src/parallel_optimizer.rs`
- OPA helpers: `src/opa.rs`

## Conventions

- Prefer safe Rust; justify every `unsafe` block.
- Map Rust failures cleanly into Python-facing errors.
- Keep constitutional-hash handling centralized.
- Avoid copying large data in hot paths when references or shared ownership work.

## Anti-Patterns

- Do not duplicate constitutional-hash constants across modules.
- Do not assume async contexts are the right place for heavy CPU work.
- Do not introduce panic-driven error handling on Python-facing paths.

## Build & Test

```bash
cd packages/enhanced_agent_bus/rust
cargo check
cargo check --tests
maturin develop --release
python -m pytest packages/enhanced_agent_bus/tests/ -v --import-mode=importlib
```

`cargo test` is not the primary verification path for the Python extension integration. Validate
through `maturin develop --release` plus pytest when the Python boundary matters.
