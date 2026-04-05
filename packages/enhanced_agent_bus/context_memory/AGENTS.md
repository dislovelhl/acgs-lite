# Context Memory

> Scope: `packages/enhanced_agent_bus/context_memory/` — canonical context and memory subsystem.

## Structure

- `hybrid_context_manager.py`: main context orchestration entrypoint
- `mamba_processor.py`: sequence-model-backed context processing
- `constitutional_context_cache.py`: constitution-aware cache
- `context_optimizer.py`: context reduction and prioritization
- `jrt_context_preparer.py`: prepared context for downstream reasoning/workflows
- `long_term_memory.py`: longer-lived memory handling
- `optimizer/`: supporting scoring, streaming, prefetch, and batch helpers

## Where to Look

| Task | Location |
| ---- | -------- |
| Context orchestration | `hybrid_context_manager.py` |
| Mamba tuning | `mamba_processor.py` |
| Constitutional cache behavior | `constitutional_context_cache.py` |
| Context compression/prioritization | `context_optimizer.py`, `optimizer/` |
| Long-term memory behavior | `long_term_memory.py` |

## Conventions

- Prefer this package over the legacy `context/` shim for new code.
- Keep constitutional-hash-aware cache invalidation explicit.
- Route callers through the manager/orchestrator layer instead of ad hoc direct use.

## Anti-Patterns

- Do not add new imports from `enhanced_agent_bus.context`.
- Do not keep unbounded context windows without passing through optimization.
