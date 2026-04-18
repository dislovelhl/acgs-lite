# GovernedAgent

`GovernedAgent` wraps any callable agent with constitutional governance. Every input and output passes through the validation pipeline before execution.

## Class Reference

::: acgs_lite.governed.GovernedAgent
    options:
      members:
        - __init__
        - run
        - arun
      show_source: true

## Examples

### Basic usage

```python
from acgs_lite import Constitution, GovernedAgent

constitution = Constitution.from_template("general")
agent = GovernedAgent(my_llm_agent, constitution=constitution)

result = agent.run("summarise this document")
```

### With MACI role enforcement

```python
from acgs_lite import MACIRole

agent = GovernedAgent(
    my_agent,
    constitution=constitution,
    maci_role=MACIRole.PROPOSER,
    enforce_maci=True,
)

result = agent.run("approve this policy change", governance_action="propose_rule")
```

### Async usage

```python
result = await agent.arun("process this request")
```
