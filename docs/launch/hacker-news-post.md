# Hacker News — Show HN Post

**Title:** Show HN: ACGS – Constitutional governance for AI agents (pip install acgs-lite)

**Body:**

Constitutional governance for AI agents.

    pip install acgs-lite

    from acgs_lite import Constitution, GovernedAgent
    constitution = Constitution.from_yaml("rules.yaml")
    agent = GovernedAgent(my_agent, constitution=constitution)

We built it around a simple thesis:

Once agents start acting in the world, the problem is no longer only whether the output is safe.
The questions become institutional:

- who proposed the action?
- who validated it?
- who is allowed to execute it?
- which rules were active?
- can you prove governance actually happened?

What it does:

- Define governance rules in YAML (keywords, regex patterns, severity levels)
- Govern actions before execution
- Keep proposer and validator roles separate
- Write governed decisions into a tamper-evident audit trail
- Produce compliance-oriented outputs mapped to major frameworks
- Optional Rust hot path for benchmarked low-latency evaluation

This is not a generic GRC dashboard, not just an input/output guardrails library, and not an orchestration framework.

It is a constitutional governance layer for agentic systems.

- https://acgs.ai
- https://pypi.org/project/acgs-lite/
- https://github.com/acgs2_admin/acgs
- Demo (7 min): https://youtu.be/uWacmC3CbYg

Would love feedback on the API design, the runtime governance model, and where you think this should sit in the agent stack.
