# Hacker News — Show HN Post

**Title:** Show HN: ACGS – Constitutional governance for AI agents (pip install acgs)

**Body:**

Constitutional governance for AI agents. Rule-based, not LLM-based.

    pip install acgs

    from acgs import Constitution, GovernedAgent
    constitution = Constitution.from_yaml("rules.yaml")
    agent = GovernedAgent(my_agent, constitution=constitution)

What it does:

- Define governance rules in YAML (keywords, regex, severity levels)
- Every AI decision validated and logged in a SHA-256 audit chain
- MACI separation of powers — agents cannot validate their own output
- 9 regulatory frameworks (EU AI Act, NIST, GDPR, SOC 2, HIPAA, ISO 42001, ECOA, NYC LL 144, OECD)
- 560ns P50 validation latency (Aho-Corasick + optional Rust/PyO3)
- 3,133 tests passing, Apache-2.0

The EU AI Act takes full enforcement August 2026. 125 compliance checklist items, 72 auto-populated.

- https://acgs.ai
- https://pypi.org/project/acgs/
- https://github.com/acgs-ai/acgs-lite

Would love feedback on the API design and which regulatory frameworks matter most to you.
