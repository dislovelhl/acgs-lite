# ACGS-Lite 2.5.2 — Examples

Runnable quickstarts covering the core governance patterns.
**No API keys or network access required** for any of these examples.

## Quickstart

```bash
pip install acgs-lite==2.5.2

# Run any example
python packages/acgs-lite/examples/basic_governance/main.py
python packages/acgs-lite/examples/compliance_eu_ai_act/main.py
python packages/acgs-lite/examples/maci_separation/main.py
python packages/acgs-lite/examples/audit_trail/main.py
python packages/acgs-lite/examples/mock_stub_testing/main.py
```

## Index

| Example | What it teaches | Difficulty |
|---------|----------------|------------|
| [`basic_governance/`](basic_governance/) | Wrap any callable with a `Constitution` + `Rule` objects | ⭐ Beginner |
| [`compliance_eu_ai_act/`](compliance_eu_ai_act/) | EU AI Act risk-tier inference, article-level gap assessment, multi-framework scoring | ⭐⭐ Intermediate |
| [`maci_separation/`](maci_separation/) | Proposer → Validator → Executor role gates; Golden Rule enforcement | ⭐⭐ Intermediate |
| [`audit_trail/`](audit_trail/) | Tamper-evident audit chain; query + JSON export | ⭐⭐ Intermediate |
| [`mock_stub_testing/`](mock_stub_testing/) | `typing.Protocol` + `InMemory*` stub pattern; chaos stubs; production swap | ⭐⭐⭐ Advanced |

## Existing examples (pre-2.5.0)

| File | Description |
|------|-------------|
| [`quickstart.py`](quickstart.py) | 5-minute core API walkthrough |
| [`eu_ai_act_quickstart.py`](eu_ai_act_quickstart.py) | EU AI Act tool demo |
| [`gitlab_mr_governance.py`](gitlab_mr_governance.py) | GitLab MR governance integration |
| [`gitlab_anthropic_demo.py`](gitlab_anthropic_demo.py) | Anthropic + GitLab pipeline demo |

## Learning path

```
basic_governance  →  maci_separation  →  audit_trail
        ↓
compliance_eu_ai_act  →  mock_stub_testing
```

For production deployments, see [`CONTRIBUTING.md`](../CONTRIBUTING.md) and the
`InMemory*` stub pattern in [`mock_stub_testing/`](mock_stub_testing/).
