# Final Show HN Post to Paste

## Title

```text
Show HN: ACGS, constitutional governance for AI agents
```

## Body

```text
Microsoft’s Agent Governance Toolkit launch last week was a useful signal: agent governance is now a real category.

That is good for the whole field, but it also clarifies a distinction I think matters.

A lot of runtime governance tooling is fundamentally about policy enforcement: intercept an action, evaluate it against policy, then allow or deny.

ACGS is trying to solve a slightly different problem: constitutional governance for AI agents.

The question is not only "does this action match policy?" It is:
- was this agent structurally permitted to attempt the action,
- under which constitutional version,
- with which role boundaries,
- and can that be proven afterward?

That leads to a different design center:
- fail-closed by default,
- structural separation of powers (MACI),
- constitutional hashing and amendment lineage,
- governed workflows like block / audit / escalate / human review,
- and audit evidence intended to be useful in regulated settings.

This is the thesis behind acgs-lite:

    pip install acgs-lite

    from acgs_lite import Constitution, GovernedAgent

    constitution = Constitution.from_yaml("rules.yaml")
    agent = GovernedAgent(my_agent, constitution=constitution)
    result = agent.run("process this request")

What I think is different from most guardrails/policy tools:
- governance of actions, not just model outputs,
- fail-closed posture when authorization is unclear,
- MACI separation of proposer / validator / executor roles,
- constitutional versioning and tamper-evident audit trail,
- workflow-aware violations via workflow_action.

What it is not:
- not a replacement for content-safety tools,
- not a hypervisor or sandbox that makes bypass impossible,
- not legal advice,
- not a full competitor to Microsoft’s broad seven-package platform.

My view is simpler:
- Microsoft validated runtime governance as a market.
- ACGS is aiming at the narrower but harder layer: constitutional authority, auditability, and regulator-facing evidence.

Would love feedback on:
1. whether this distinction resonates,
2. whether fail-closed governance feels practical in real systems,
3. and whether constitutional versioning / amendment lineage is something teams would actually care about.

Repo: https://github.com/dislovelhl/acgs
PyPI: https://pypi.org/project/acgs-lite/
```

## Notes

- This is the exact paste-ready version for the HN submission form.
- Keep the first comment conversational, not defensive.
- If asked about Microsoft directly, frame ACGS as narrower and more constitutional, not as a broader replacement.
