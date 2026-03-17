# ACGS — Advanced Constitutional Governance System

> **Constitutional Hash**: `cdd01ef066bc6cf2`
> **Version**: 3.0.0

**Constitutional governance infrastructure for AI agents.** Validates agent actions against
constitutional rules at 560ns median latency with tamper-evident audit trails and separation
of powers enforcement.

## Architecture

```
acgs/
├── packages/
│   ├── acgs-lite/              # Library: pip install acgs-lite
│   └── enhanced-agent-bus/     # Platform engine: message routing + MACI + policy
├── src/core/
│   ├── services/api_gateway/   # Unified API ingress
│   └── shared/                 # Shared types, auth, config, logging
├── autoresearch/               # Benchmark optimization harness
├── start_agent_bus.py          # Agent Bus entry point
└── ecosystem.config.cjs        # PM2 service definitions
```

### Product Domains

| Domain                 | Package                          | What It Does                                                     |
| ---------------------- | -------------------------------- | ---------------------------------------------------------------- |
| **Governance Library** | `packages/acgs-lite/`            | `pip install acgs-lite` — govern any AI agent in 5 lines of code |
| **Agent Bus**          | `packages/enhanced-agent-bus/`   | High-performance message routing with constitutional validation  |
| **API Gateway**        | `src/core/services/api_gateway/` | Unified ingress, auth, rate limiting, API versioning             |

### Performance

| Metric                 | Value                            |
| ---------------------- | -------------------------------- |
| Validation latency P50 | **560 ns** (Rust dual-automaton) |
| Validation latency P99 | **3.8 μs**                       |
| Throughput             | **2.8M validations/sec**         |
| Fast-lane routing P99  | **0.91 ms**                      |
| Cache hit rate         | **95%+**                         |

## Quick Start

### Library (acgs-lite)

```python
from acgs_lite import Constitution, GovernedAgent

constitution = Constitution.from_yaml("rules.yaml")
agent = GovernedAgent(my_agent, constitution=constitution)
result = agent.run("process this request")  # Governed.
```

### Platform Services

```bash
# Install dependencies
pip install -e ".[dev,test]"
pip install -e packages/acgs-lite
pip install -e packages/enhanced-agent-bus

# Start services
pm2 start ecosystem.config.cjs

# Run tests
make test
```

## MACI Separation of Powers

| Role          | Can                              | Cannot              |
| ------------- | -------------------------------- | ------------------- |
| **Proposer**  | Suggest governance actions       | Approve or validate |
| **Validator** | Verify constitutional compliance | Propose             |
| **Executor**  | Execute approved actions         | Validate own work   |

Agents NEVER validate their own output. Always independent validators.

## Integrations (acgs-lite)

| Platform     | Install Extra           | Status |
| ------------ | ----------------------- | ------ |
| OpenAI       | `acgs-lite[openai]`     | ✅     |
| Anthropic    | `acgs-lite[anthropic]`  | ✅     |
| LangChain    | `acgs-lite[langchain]`  | ✅     |
| LiteLLM      | `acgs-lite[litellm]`    | ✅     |
| Google GenAI | `acgs-lite[google]`     | ✅     |
| LlamaIndex   | `acgs-lite[llamaindex]` | ✅     |
| AutoGen      | `acgs-lite[autogen]`    | ✅     |
| CrewAI       | `acgs-lite[crewai]`     | ✅     |
| MCP          | `acgs-lite[mcp]`        | ✅     |
| A2A          | `acgs-lite[a2a]`        | ✅     |
| GitLab       | built-in                | ✅     |

## Compliance Frameworks

EU AI Act, NIST AI RMF, ISO/IEC 42001, GDPR Art. 22, SOC 2 + AI,
HIPAA + AI, ECOA/FCRA, NYC LL 144, OECD AI Principles.

## Development

```bash
make test           # Full test suite
make test-quick     # Skip slow tests
make lint           # Ruff + MyPy
make format         # Auto-fix formatting
```

## License

Apache License 2.0

Constitutional Hash: `cdd01ef066bc6cf2`
