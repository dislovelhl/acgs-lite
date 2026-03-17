# Enhanced Agent Bus

**For project-wide instructions, see the root `/CLAUDE.md`.**

## Imports

```python
from enhanced_agent_bus.models import Priority       # NOT MessagePriority (deprecated)
from enhanced_agent_bus.agent_bus import EnhancedAgentBus
from enhanced_agent_bus.maci.enforcer import MACIRole
```

Always import from `enhanced_agent_bus.*` — never `src.core.enhanced_agent_bus.*` (Phase 3 extraction complete).

## Testing

```bash
python -m pytest packages/enhanced_agent_bus/tests/ -v --import-mode=importlib   # 3,534 tests
python -m pytest packages/enhanced_agent_bus/tests/ -m "not slow" -v             # Skip slow tests
```

## Performance Targets

P99 < 0.103ms | Throughput > 5,066 RPS | Memory < 5MB/1000 msgs

## Gotchas

- **MACI enforcement** is at middleware level (`middlewares/batch/governance.py`), not in deleted `maci_metrics.py`
- **Rust backend** provides 10-50x speedup — see `rust/AGENTS.md` for build/test instructions
- **Module migration**: 6 modules deleted in refactor — see `docs/CLAUDE.md` for the full migration table
- **Entry point**: `enhanced_agent_bus.api.app:app` (PM2 uvicorn path)
- **PYTHONPATH**: Must include both project root and `src/` for cross-package imports
- **mypy excluded**: This entire package is excluded from mypy checking in `.pre-commit-config.yaml`
