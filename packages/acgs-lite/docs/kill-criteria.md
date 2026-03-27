# Kill / Pivot / Proceed Criteria

Written 2026-03-27. Evaluate at end of user research sprint (2026-04-24).

## The Experiment

Talk to 10-15 teams deploying multi-agent AI systems in production. Ask:
"How do you currently handle agent approvals, audit logging, and compliance evidence?
What breaks? What scares you?"

## Decision Matrix

| Signal | Proceed | Pivot | Kill |
|--------|---------|-------|------|
| Conversations completed | 10+ | 5-9 | <5 (nobody cares enough to talk) |
| "This replaces something manual" | 3+ teams | 1-2 teams | 0 |
| Willing to pilot in staging | 1+ team | 0, but clear pain articulated | 0, no pain articulated |
| Pain pattern consistency | Same pain across 3+ teams | Pain exists but fragmented | "We don't need this" |
| Urgency signal | "We need this before [date]" | "Nice to have someday" | "We already solved this" |

## Proceed (build the MVP)

All three must be true:
1. At least 3 teams independently describe the same manual workflow pain
2. At least 1 team commits to piloting ACGS-Lite in staging
3. You can name the specific person, their role, their company, and their exact pain

If proceed: ship the narrow wedge (core engine + one framework integration + audit evidence
export) and get it into the pilot team's hands within 2 weeks.

## Pivot (change the wedge, keep the thesis)

Any of these:
- Pain exists but is about something different than what ACGS-Lite solves today
- Teams want audit trails but not runtime governance
- Teams want compliance reports but not separation of powers
- The pain is real but in a different persona (compliance officer, not platform engineer)

Pivot options:
- **Audit-trail-only**: Strip governance, ship just hash-chained audit logging
- **Compliance report generator**: Strip runtime, ship evidence export as a CLI tool
- **Different framework**: If CrewAI teams don't care but LangGraph teams do, follow the pain
- **Different buyer**: If compliance officers care more than engineers, redesign the onramp

## Kill (stop building)

Any of these:
- <5 conversations in 4 weeks (market doesn't exist or can't be reached)
- 10+ conversations and zero pain articulated
- Every team says "we already solved this" with existing tools
- The pain is real but teams will never pay or adopt OSS for it

If kill: archive the code, write a postmortem, move on. The engineering is solid. The
market wasn't there. That's not failure, that's learning.

## What "pain" actually looks like

Real pain sounds like:
- "We have a spreadsheet where someone manually approves every agent action"
- "Our audit log is just grep on CloudWatch and we pray it's complete"
- "We failed a SOC2 audit because we couldn't prove agent actions were authorized"
- "An agent approved its own output and we didn't catch it for 3 days"

Fake pain sounds like:
- "Yeah, governance is important" (agreeing to be polite)
- "We should probably do something about that" (no urgency)
- "That's interesting, send me a link" (polite dismissal)

## Tracking

Log every conversation:

| Date | Name | Company | Role | Current workflow | Pain level (1-5) | Would pilot? | Notes |
|------|------|---------|------|-----------------|-------------------|-------------|-------|
| | | | | | | | |

Pain levels:
1. No pain, doesn't think about it
2. Aware of gap, low priority
3. Active workaround in place, annoyed by it
4. Significant time/risk cost, actively looking for solutions
5. Blocking a launch, audit, or compliance deadline
