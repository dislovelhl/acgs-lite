# Reddit r/MachineLearning — Post

**Title:** [P] ACGS — Constitutional governance for AI agents. Runtime governance, audit evidence, 5 lines of code.

**Body:**

I've been building ACGS for two years — it's a Python library that wraps AI agents in enforceable constitutional rules.

```bash
pip install acgs-lite
```

**The problem:** once agents can approve, deploy, deny, escalate, or call tools, the question is no longer only whether the output is safe. The question becomes:

- who proposed the action?
- who validated it?
- what rules were active?
- can governance later be proven?

**What ACGS does:**

- Define rules in YAML
- Wrap any agent: `GovernedAgent(my_agent, constitution=constitution)`
- Govern actions before execution
- Keep proposer and validator roles structurally separate
- Write decisions into a SHA-256 chain-verified audit trail
- Produce compliance-oriented outputs mapped to major frameworks

The framing I'm aiming for is:

Guardrails filter outputs. ACGS governs actions.

7-minute walkthrough: https://youtu.be/uWacmC3CbYg

Links:
- Website: https://acgs.ai
- PyPI: https://pypi.org/project/acgs-lite/
- GitHub: https://github.com/acgs2_admin/acgs

Feedback welcome — especially on where you think runtime governance should sit in the agent stack.
