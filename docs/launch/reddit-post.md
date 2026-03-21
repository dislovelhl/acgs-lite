# Reddit r/MachineLearning — Post

**Title:** [P] ACGS — Constitutional governance for AI agents. 9 regulatory frameworks, tamper-evident audit trail, 5 lines of code.

**Body:**

I've been building ACGS for two years — it's a Python library that wraps any AI agent in enforceable constitutional rules.

```
pip install acgs
```

**The problem:** The EU AI Act takes full enforcement August 2026. Fines up to 7% of global annual revenue. Most AI deployments have zero governance infrastructure. If you're deploying AI in regulated industries (healthcare, finance, HR), you need provable governance.

**What ACGS does:**

- Define rules in YAML — keywords, regex patterns, severity levels
- Wrap any agent: `GovernedAgent(my_agent, constitution=constitution)`
- Every decision logged in a SHA-256 chain-verified audit trail
- MACI separation of powers — agents cannot validate their own output
- Covers 9 regulatory frameworks: EU AI Act, NIST AI RMF, GDPR Art. 22, SOC 2, HIPAA, ISO 42001, ECOA/FCRA, NYC LL 144, OECD AI Principles
- 125 compliance checklist items, 72 auto-populated
- Integrations for OpenAI, Anthropic, LangChain, LiteLLM, and 7 more

**Technical details:**

- Rule-based (not LLM-based) — deterministic, no inference cost
- Aho-Corasick single-pass keyword scanning
- Optional Rust acceleration via PyO3
- 3,133 tests passing
- Apache-2.0

I built this entirely with Claude (Anthropic's AI). No CS background. Two years of daily conversations with AI, learning to code by building governance infrastructure.

Links:
- PyPI: https://pypi.org/project/acgs/
- GitHub: https://github.com/acgs-ai/acgs-lite

Feedback welcome — especially on which regulatory frameworks matter most to your work.
