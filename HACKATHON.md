# Build with ACGS -- 21-Day Hackathon Challenge

> **Constitutional governance for AI agents. Build something that proves machines can be constrained.**

| Detail | Info |
|--------|------|
| **Start** | April 14, 2026 |
| **End** | May 4, 2026 (21 days) |
| **Prizes** | $3,000 USDT total |
| **Open to** | Anyone, anywhere |
| **Stack** | `pip install acgs-lite` (Python 3.10+) |

---

## Why This Exists

$203 billion was invested in building decision-making AI engines in 2025. Less than 1% went to constraining them.

ACGS is the constitutional governance layer for AI agents -- machine-readable rules, runtime action validation, MACI separation of powers, and tamper-evident audit trails. We want to see what you build with it.

This hackathon is not about building the prettiest demo. It is about building something that shows AI governance working in a real scenario: healthcare, finance, hiring, code review, content moderation, autonomous systems, or anything else where decisions matter.

---

## Prizes

### Builder Prizes (judged)

| Place | Prize |
|-------|-------|
| 1st Place | $1,000 USDT |
| 2nd Place | $500 USDT |
| 3rd Place | $500 USDT |

### Community Prizes (engagement-based)

Top 10 most-shared posts about the hackathon on X/Twitter, LinkedIn, or Dev.to during the challenge period:

**$100 USDT each** (10 prizes)

Sharing means: original posts with the hashtag `#BuildWithACGS` that link to your project, a demo, or the hackathon page. Retweets/reshares of your own post count toward your total. We measure by total engagement (likes + reposts + comments) across platforms.

---

## How to Enter

### Step 1: Install ACGS

```bash
pip install acgs-lite
```

Optional extras for specific LLM providers:

```bash
pip install "acgs-lite[anthropic]"   # Claude
pip install "acgs-lite[openai]"      # OpenAI
pip install "acgs-lite[all]"         # Everything
```

### Step 2: Build Something

Use ACGS to govern an AI agent, workflow, or system. Your project must:

1. Use `acgs-lite` as a dependency (any version >= 2.4.0)
2. Define at least one constitutional rule set (YAML or programmatic)
3. Show governance in action -- a decision being validated, blocked, audited, or escalated

Beyond that, build whatever you want.

### Step 3: Submit

Create a **public GitHub/GitLab repository** with your project and submit it by opening an issue at:

**https://github.com/dislovelhl/acgs/issues/new**

Use the title format: `[HACKATHON] Your Project Name`

Your issue must include:

- **Repository link** (public, with a README)
- **What it does** (2-3 sentences)
- **How ACGS is used** (which features: constitution, GovernedAgent, MACI, audit trail, compliance, etc.)
- **How to run it** (setup + run instructions, must work with `pip install` + `python main.py` or equivalent)
- **Demo** (one of: screenshot, video link, or live URL)

**Deadline: May 4, 2026 at 23:59 UTC**

### Step 4 (Optional): Share for Community Prizes

Post about your project on X/Twitter, LinkedIn, or Dev.to with the hashtag `#BuildWithACGS`. The 10 posts with the highest total engagement during the challenge period win $100 USDT each.

---

## Judging Criteria

Builder prizes are judged on four dimensions, equally weighted:

### 1. Governance Depth (25%)

Does the project use ACGS governance meaningfully, or is it a surface-level integration?

- Constitutional rules that reflect real domain constraints
- MACI separation of powers (proposer != validator)
- Audit trail that captures governance decisions
- Fail-closed behavior (denied by default, not allowed by default)

### 2. Real-World Relevance (25%)

Could this solve a real problem? Does the domain make sense?

- Clear problem statement
- Governance rules tied to actual regulations, safety requirements, or ethical constraints
- Not a toy example wrapped in governance

### 3. Technical Quality (25%)

Is the code clean, tested, and runnable?

- Works out of the box (`pip install` + run)
- Has tests
- Clean code, good README
- Handles errors (not just the happy path)

### 4. Creativity (25%)

Did you surprise us?

- Novel domain or use case
- Creative use of ACGS features (constrained decoding, multi-agent governance, compliance reporting, etc.)
- Something we have not seen before

---

## Ideas to Get You Started

You do not have to use these. They are starting points.

| Domain | Idea | ACGS Features |
|--------|------|---------------|
| Healthcare | AI medication checker that blocks dangerous drug combinations | Constitution, GovernedAgent, MACI, audit trail |
| Finance | Loan approval agent with anti-discrimination governance | Constitution, compliance reporting, fail-closed |
| Hiring | Resume screening agent that cannot see protected attributes | Constitution, MACI (proposer != reviewer) |
| Code Review | AI reviewer that enforces security rules before merge | GovernedAgent, constitutional rules, audit |
| Content | Moderation agent with transparent appeal process | Constitution, audit trail, HITL escalation |
| Autonomous | Robot task planner with safety constitution | GovernedAgent, risk tiers, MACI |
| Education | AI tutor with age-appropriate content governance | Constitution, compliance, fail-closed |
| Legal | Contract review agent with regulatory rule sets | Constitution, audit trail, compliance |
| EU AI Act | Compliance assessment tool for high-risk AI systems | `acgs-lite eu-ai-act`, compliance reporting |
| Multi-agent | Swarm of agents with constitutional governance | `constitutional-swarm`, MACI, audit |

---

## Quick Start: Your First Governed Agent

```python
from acgs_lite import Constitution, GovernedAgent

# Define rules
constitution = Constitution.from_yaml("rules.yaml")

# Wrap any agent
agent = GovernedAgent(my_agent, constitution=constitution)

# Every action is now governed
result = agent.run("process this loan application")
# -> Validated against rules. Audited. Fail-closed on violation.
```

Example `rules.yaml`:

```yaml
name: My Governance Rules
rules:
  - id: RULE-001
    severity: critical
    text: No decision may be made without human review for amounts over $10,000.
    keywords: ["auto-approve", "skip review", "bypass"]

  - id: RULE-002
    severity: high
    text: Protected attributes (race, gender, age) must not influence scoring.
    keywords: ["race", "gender", "age", "ethnicity"]
```

For more examples, see:
- [Quickstart script](https://github.com/dislovelhl/acgs/blob/main/examples/quickstart.py)
- [Governed agents example](https://github.com/dislovelhl/acgs/tree/main/examples/governed_agents)
- [EU AI Act quickstart](https://github.com/dislovelhl/acgs/blob/main/examples/eu_ai_act_quickstart.py)

---

## Resources

| Resource | Link |
|----------|------|
| **PyPI** | https://pypi.org/project/acgs-lite/ |
| **GitHub (monorepo)** | https://github.com/dislovelhl/acgs |
| **GitLab (standalone)** | https://gitlab.com/martin668/acgs-lite |
| **Documentation** | https://gitlab.com/martin668/acgs-lite/-/blob/main/README.md |
| **Website** | https://acgs.ai |
| **Examples** | https://github.com/dislovelhl/acgs/tree/main/examples |

### Key ACGS Features

- **Constitution** -- Machine-readable YAML rules validated at runtime
- **GovernedAgent** -- Wrap any agent with constitutional governance
- **MACI** -- Separation of powers: proposer, validator, executor are distinct roles
- **Audit Trail** -- Tamper-evident JSONL log of every governance decision
- **Compliance** -- EU AI Act assessment, HIPAA checklist, PDF reporting
- **Constrained Decoding** -- Force LLM outputs to conform to governance schemas
- **CLI** -- `acgs-lite init`, `acgs-lite test`, `acgs-lite eu-ai-act`, `acgs-lite observe`

---

## Rules

1. **Eligibility**: Open to individuals and teams worldwide. No purchase necessary.
2. **Original work**: Your project must be created during the challenge period (April 14 -- May 4, 2026). You may use existing code as a foundation, but the ACGS integration must be new.
3. **Open source**: Submissions must be in a public repository with a license (MIT, Apache-2.0, or similar).
4. **ACGS dependency**: Your project must use `acgs-lite` as a Python dependency. Minimum version 2.4.0.
5. **Runnable**: Judges must be able to clone your repo and run the project. Include clear setup instructions.
6. **One submission per person/team**: You may update your submission until the deadline, but only one project per participant.
7. **Community prizes**: Engagement is measured from April 14 through May 4. Posts must use `#BuildWithACGS` and link to your project or the hackathon. Self-engagement (liking/sharing your own post from alt accounts) is grounds for disqualification.
8. **Prize distribution**: USDT sent to a wallet address you provide. Builder prizes paid within 14 days of results. Community prizes paid within 7 days of final engagement count.
9. **Judging**: Builder prizes judged by ACGS maintainers. Decisions are final.
10. **Code of conduct**: Be respectful. No plagiarism. No harassment. Violations result in disqualification.

---

## Timeline

| Date | Event |
|------|-------|
| **April 7 -- 13** | Pre-launch promotion. Star the repo. Install `acgs-lite`. Join the conversation. |
| **April 14** | Hackathon starts. Build. |
| **April 28** | 1-week warning. Share your progress with `#BuildWithACGS`. |
| **May 4, 23:59 UTC** | Submissions close. |
| **May 5 -- 9** | Judging period. |
| **May 10** | Winners announced on X/Twitter and GitHub. |
| **May 14** | Community prize engagement finalized. |
| **May 17** | All prizes distributed. |

---

## Questions?

- **GitHub Discussions**: https://github.com/dislovelhl/acgs/discussions
- **Issue tracker**: https://github.com/dislovelhl/acgs/issues
- **X/Twitter**: [@dislovelhl](https://x.com/dislovelhl)
- **Email**: martin@acgs.ai

Tag your questions with `[HACKATHON]` so we can find them quickly.

---

## Spread the Word

Help us reach more builders:

```
Build with ACGS -- 21-day hackathon challenge.

$3,000 in prizes. Constitutional governance for AI agents.

pip install acgs-lite

#BuildWithACGS
```

---

*Constitutional Hash: 608508a9bd224290*
