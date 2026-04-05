# enhanced-agent-bus

[![PyPI](https://img.shields.io/pypi/v/enhanced-agent-bus)](https://pypi.org/project/enhanced-agent-bus/)
[![Python](https://img.shields.io/pypi/pyversions/enhanced-agent-bus)](https://pypi.org/project/enhanced-agent-bus/)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)

**High-performance agent communication infrastructure with constitutional governance.**

`enhanced-agent-bus` is the ACGS runtime layer for governed agent-to-agent messaging. It
combines message routing, registration, constitutional validation, MACI-aware controls,
deliberation hooks, and FastAPI API surfaces in a single package.

## Installation

`enhanced-agent-bus` supports Python 3.11+.

```bash
pip install enhanced-agent-bus
pip install enhanced-agent-bus[dev]
pip install enhanced-agent-bus[ml]
pip install enhanced-agent-bus[pqc]
pip install enhanced-agent-bus[postgres]
pip install enhanced-agent-bus[messaging]
```

## Quick Start

```python
from enhanced_agent_bus import AgentMessage, EnhancedAgentBus, MessageType, Priority

bus = EnhancedAgentBus(redis_url="redis://localhost:6379", enable_maci=True)
await bus.start()

await bus.register_agent(
    "planner",
    agent_type="supervisor",
    capabilities=["planning", "reasoning"],
)
await bus.register_agent(
    "executor",
    capabilities=["code", "deploy"],
)

message = AgentMessage(
    from_agent="planner",
    to_agent="executor",
    message_type=MessageType.COMMAND,
    priority=Priority.HIGH,
    content={"action": "deploy", "target": "staging"},
    constitutional_hash=bus.constitutional_hash,
)

result = await bus.send_message(message)
assert result.is_valid

await bus.stop()
```

## API Server

```bash
python -m enhanced_agent_bus.api
```

That starts the package's FastAPI app. The application factory also lives at
`enhanced_agent_bus.api.app:create_app`.

## Deliberation and Adapters

- The deliberation layer is exposed via `enhanced_agent_bus.deliberation_layer` and is
  also split into the separate `acgs-deliberation` compatibility package.
- LLM adapter primitives live under `enhanced_agent_bus.llm_adapters`, including
  `LLMAdapterRegistry`, `FallbackChain`, provider configs, and constrained-output
  helpers.
- Some optional adapter and ML features require the extras listed above.

## Key Features

- Redis-backed or mixed-mode agent registration and message routing.
- Constitutional hash validation, tenant isolation, and fail-closed validation paths.
- MACI enforcement and governance-aware message processing.
- Deliberation, impact scoring, and approval-routing hooks for higher-risk actions.
- Observability, rate limiting, retry/idempotency handling, and extensible plugin
  surfaces.

## Testing

```bash
python -m pytest packages/enhanced_agent_bus/tests/ -v --import-mode=importlib
python -m pytest packages/enhanced_agent_bus/tests/ -m "not slow" -v --import-mode=importlib
```

## License

AGPL-3.0-or-later. Commercial licensing is available; contact `hello@acgs.ai`.

## Links

- [Homepage](https://acgs.ai)
- [Documentation](https://github.com/dislovelhl/acgs/tree/main/packages/enhanced_agent_bus)
- [PyPI](https://pypi.org/project/enhanced-agent-bus/)
- [Repository](https://github.com/dislovelhl/acgs)
- [Issues](https://github.com/dislovelhl/acgs/issues)
- [Changelog](https://github.com/dislovelhl/acgs/releases)

Constitutional Hash: `608508a9bd224290`
