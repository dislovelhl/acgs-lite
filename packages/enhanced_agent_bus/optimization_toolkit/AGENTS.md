# AGENTS.md - Optimization Toolkit

Scope: `src/core/enhanced_agent_bus/optimization_toolkit/`

## OVERVIEW

Specialized performance engineering module providing multi-agent profiling, token cost management, and semantic context compression. It enables the Agent Bus to self-optimize for latency, throughput, and operational cost.

## STRUCTURE

- `agents.py`: Domain-specific profiling agents (DB, App, Frontend).
- `context.py`: `ContextCompressor` for semantic context distillation.
- `cost.py`: `CostOptimizer` for token budget and model strategy selection.
- `orchestrator.py`: `MultiAgentOrchestrator` facade for parallel optimization cycles.

## WHERE TO LOOK

- **System Profiling**: `DatabasePerformanceAgent`, `ApplicationPerformanceAgent` in `agents.py`.
- **Heuristic Compression**: `ContextCompressor._is_low_value` in `context.py`.
- **Budgeting Logic**: `CostOptimizer.select_model` in `cost.py`.
- **Toolkit Entrypoint**: `MultiAgentOrchestrator.run_optimization_cycle` in `orchestrator.py`.

## CONVENTIONS

- **Base Inheritance**: All profiling agents MUST inherit from `PerformanceAgent`.
- **Structured Metrics**: Always return `PerformanceMetrics` dataclass from profiling tasks.
- **Async Execution**: Use `asyncio.gather` for parallel profiling to minimize overhead.
- **Non-Destructive Compression**: Preserve system instructions (top 5 lines) and recent history (last 10 lines) during context distillation.

## ANTI-PATTERNS

- **Serial Profiling**: Avoid blocking the bus with sequential agent runs.
- **Budget Bypass**: Do not hardcode model selections; use `CostOptimizer` to respect daily limits.
- **Context Erasure**: Never compress context purely by truncation without semantic filtering.
- **Hardcoded Costs**: Avoid defining model pricing in individual agents; centralize in `cost.py`.
