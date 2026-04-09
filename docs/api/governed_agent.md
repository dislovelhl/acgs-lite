# GovernedAgent

`GovernedAgent` wraps any callable agent with constitutional governance. Every input and output passes through the validation pipeline before execution.

## Class Reference

::: acgs_lite.agent.GovernedAgent
    options:
      members:
        - __init__
        - run
        - validate_input
        - validate_output
      show_source: true

## Examples

### Basic usage

```python
from acgs_lite import Constitution, GovernedAgent

constitution = Constitution.from_template("general")
agent = GovernedAgent(my_llm_agent, constitution=constitution)

result = agent.run("summarise this document")
```

### With custom MACI roles

```python
from acgs_lite.maci import MACIConfig, Role

config = MACIConfig(
    proposer=Role.LEGISLATIVE,
    validator=Role.JUDICIAL,
    executor=Role.EXECUTIVE,
)
agent = GovernedAgent(my_agent, constitution=constitution, maci=config)
```

### Async usage

```python
result = await agent.arun("process this request")
```
