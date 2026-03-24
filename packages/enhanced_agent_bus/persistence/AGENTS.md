# Persistence

> Scope: `packages/enhanced_agent_bus/persistence/` — durable workflow execution and persistence.

## Structure

- `executor.py`: durable execution
- `repository.py`, `postgres_repository.py`: persistence backends/repositories
- `replay.py`: replay support
- `models.py`: persistence models
- `metrics.py`: persistence metrics

## Where to Look

| Task | Location |
| ---- | -------- |
| Durable workflow execution | `executor.py` |
| Repository behavior | `repository.py`, `postgres_repository.py` |
| Replay logic | `replay.py` |
| Model/schema changes | `models.py` |

## Conventions

- Keep this package separated from `saga_persistence/`.
- Prefer durable execution/repository abstractions over ad hoc writes.

## Anti-Patterns

- Do not add cross-imports with `saga_persistence/`.
- Do not bypass the persistence layer with direct caller-owned state mutations.
