# Saga Persistence

> Scope: `packages/enhanced_agent_bus/saga_persistence/` — saga repositories, models, Redis and
> PostgreSQL implementations.

## Structure

- `factory.py`: repository selection/creation
- `models.py`: saga state models
- `repository.py`: common repository surface
- `redis_repository.py`, `redis/`: Redis-backed implementation
- `postgres_repository.py`, `postgres/`: PostgreSQL-backed implementation

## Where to Look

| Task | Location |
| ---- | -------- |
| Repository creation | `factory.py` |
| Saga models | `models.py` |
| Redis backend | `redis_repository.py`, `redis/` |
| PostgreSQL backend | `postgres_repository.py`, `postgres/` |

## Conventions

- Route callers through the factory/shared repository surface.
- Keep saga persistence concerns isolated from workflow persistence.

## Anti-Patterns

- Do not cross-import this package with `persistence/`.
- Do not hold backend-specific locking semantics outside the repository layer.
