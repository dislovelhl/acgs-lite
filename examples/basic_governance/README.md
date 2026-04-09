# Example: Basic Constitutional Governance

Govern any Python callable with a `Constitution` in ~5 lines. No API keys required.

## What it shows

| Concept | File |
|---------|------|
| `Constitution` with `Rule` objects | `main.py` |
| `GovernedCallable` wrapper | `main.py` |
| `ConstitutionalViolationError` handling | `main.py` |
| Blocking vs. non-blocking rules | `main.py` |

## Run

```bash
# From repo root
python packages/acgs-lite/examples/basic_governance/main.py

# Or from acgs-lite package root
python examples/basic_governance/main.py
```

## Expected output

```
=======================================================
  Basic Constitutional Governance Demo
=======================================================

✅  Allowed:  Response to: What is the capital of France?

🚫  Blocked:  no-harmful-content — Block requests containing harmful keywords

🚫  PII gate: no-pii — Prevent PII leakage in responses
```

## Key concepts

```python
# 1. Define rules
rule = Rule(id="no-pii", pattern=r"\b\d{3}-\d{2}-\d{4}\b", blocking=True)

# 2. Create constitution
constitution = Constitution(name="policy", rules=[rule])

# 3. Wrap any callable — zero changes to the original
governed = GovernedCallable(my_function, constitution=constitution)

# 4. Call normally — violations raise ConstitutionalViolationError
governed("safe input")        # ✅ passes through
governed("123-45-6789")       # 🚫 raises ConstitutionalViolationError
```

## Next steps

- [`../maci_separation/`](../maci_separation/) — add role separation (Proposer/Validator/Executor)
- [`../audit_trail/`](../audit_trail/) — persist every decision for compliance
- [`../compliance_eu_ai_act/`](../compliance_eu_ai_act/) — map to EU AI Act articles
