# Optimization Toolkit

> Scope: `packages/enhanced_agent_bus/optimization_toolkit/` — profiling, cost strategy, context
> compression, and optimization orchestration.

## Structure

- `agents.py`: optimization/profiling agents
- `context.py`: context compression helpers
- `cost.py`: cost and model-strategy helpers
- `orchestrator.py`: orchestration facade

## Where to Look

| Task | Location |
| ---- | -------- |
| Profiling agent behavior | `agents.py` |
| Context compression | `context.py` |
| Budget/model strategy | `cost.py` |
| Optimization orchestration | `orchestrator.py` |

## Conventions

- Keep optimization decisions centralized instead of hardcoding them in callers.
- Preserve important instructions and recent context when compressing.

## Anti-Patterns

- Do not bypass the cost/optimization strategy layer with hardcoded model choices.
- Do not reduce context by blind truncation when semantic filtering exists.
