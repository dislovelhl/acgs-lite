# Middlewares

> Scope: `packages/enhanced_agent_bus/middlewares/` — canonical middleware package. New middleware
> belongs here, not in the deleted singular `middleware/` namespace.

## Structure

- `session_extraction.py`
- `security.py`
- `tool_privilege.py`, `tool_privilege_policy.py`
- `temporal_policy.py`
- `prov.py`
- `ifc.py`
- `orchestrator.py`
- `batch/`: batch governance, validation, concurrency, deduplication, context, metrics

## Where to Look

| Task | Location |
| ---- | -------- |
| Session/JWT extraction | `session_extraction.py` |
| Security guards | `security.py` |
| Tool capability gating | `tool_privilege.py` |
| Provenance | `prov.py` |
| IFC | `ifc.py` |
| Batch behavior | `batch/` |

## Conventions

- Put all new middleware in this package.
- Keep ordering assumptions explicit in callers that compose middleware stacks.

## Anti-Patterns

- Never import from `enhanced_agent_bus.middleware`.
- Do not scatter middleware logic into unrelated API modules when it belongs here.
