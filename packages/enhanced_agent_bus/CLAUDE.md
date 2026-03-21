# Enhanced Agent Bus

For repo-wide rules, see `/CLAUDE.md`.

## Imports

```python
from enhanced_agent_bus.models import Priority
from enhanced_agent_bus.agent_bus import EnhancedAgentBus
from enhanced_agent_bus.maci import MACIRole
```

Always import from `enhanced_agent_bus.*`.

## Structure

```
enhanced_agent_bus/
├── api/                  # FastAPI app and routes
├── agent_bus.py          # Core bus class
├── message_processor.py  # Routing and orchestration
├── models.py             # Shared models and enums
├── maci/                 # MACI enforcement
├── constitutional/       # Constitutional workflows
├── middlewares/          # Canonical middleware stack
├── context_memory/       # Context and memory subsystem
├── persistence/          # Persistence layer
├── saga_persistence/     # Saga persistence layer
└── _ext_*.py             # Optional dependency wrappers
```

## Testing

```bash
python -m pytest packages/enhanced_agent_bus/tests/ -v --import-mode=importlib
python -m pytest packages/enhanced_agent_bus/tests/ -m "not slow" -v --import-mode=importlib
```

The package also has its own `pyproject.toml` with stricter package-local coverage settings.

## Performance

This package contains hot paths, but performance targets should be validated from current
benchmarks or tests rather than copied from old docs.

## Gotchas

- MACI enforcement and governance checks span middleware and runtime paths; avoid narrow
  assumptions about a single file owning the invariant.
- Legacy namespaces such as `middleware/` and `context/` still appear for compatibility but are
  not for new code.
- `_ext_*.py` modules intentionally use fallback stubs for missing optional dependencies.
- Package-level MyPy is enabled in `packages/enhanced_agent_bus/pyproject.toml`; do not assume
  the package is globally exempt from type discipline.
