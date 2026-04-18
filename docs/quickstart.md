# Quickstart

Get ACGS running in a few minutes with the same API surface exercised by
[`examples/quickstart.py`](https://github.com/dislovelhl/acgs-lite/blob/main/examples/quickstart.py).

## 1. Install

Install the core package:

```bash
pip install acgs-lite
```

Install an extra only when you need a specific integration:

```bash
pip install "acgs-lite[anthropic]"  # Claude integration
pip install "acgs-lite[mcp]"        # MCP governance server
pip install "acgs-lite[otel]"       # OpenTelemetry export
```

## 2. Add a Constitution

Create `constitution.yaml`:

```yaml
constitutional_hash: "608508a9bd224290"
rules:
  - id: no-pii
    pattern: "SSN|social security|passport number"
    severity: CRITICAL
    description: Block PII exposure

  - id: no-destructive
    pattern: "delete|drop table|rm -rf"
    severity: HIGH
    description: Block destructive operations

  - id: require-approval
    pattern: "transfer|payment|wire"
    severity: HIGH
    description: Financial actions require human approval
```

## 3. Govern a Callable

```python
from acgs_lite import Constitution, GovernedAgent


def my_agent(prompt: str) -> str:
    return f"Processed: {prompt}"


constitution = Constitution.from_yaml("constitution.yaml")
agent = GovernedAgent(my_agent, constitution=constitution, agent_id="demo-agent")

result = agent.run("Summarize the quarterly report")
print(result)
```

## 4. See Blocking Behavior

```python
from acgs_lite import ConstitutionalViolationError

try:
    agent.run("My social security number is 123-45-6789")
except ConstitutionalViolationError as exc:
    print(f"Blocked: {exc}")
```

## 5. Run the Example

The repo includes a fuller walkthrough covering default constitutions, custom
rules, MACI enforcement, audit stats, and the decorator API:

```bash
python examples/quickstart.py
```

## 6. CLI Bootstrap

Scaffold a starter `rules.yaml` and CI governance job:

```bash
acgs init
```

Check your environment and license state:

```bash
acgs status
```

## 7. MCP Server

If you installed the `mcp` extra, run the governance server over stdio:

```bash
python -m acgs_lite.integrations.mcp_server --constitution constitution.yaml
```

## Next Steps

- Read the [MCP Governance Guide](mcp-guide.md).
- Review [MACI Architecture](maci.md).
- Run an [EU AI Act assessment](compliance-2026.md).
- Explore more runnable examples in
  [`examples/README.md`](https://github.com/dislovelhl/acgs-lite/blob/main/examples/README.md).
