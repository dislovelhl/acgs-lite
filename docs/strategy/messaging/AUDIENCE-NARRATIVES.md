# ACGS Audience-Segmented Messaging

**Date:** 2026-03-19
**Panel input:** Doumont (structured clarity), Godin (tribe building), Drucker (customer definition)

---

## Core Positioning (All Audiences)

**One-liner:** ACGS is HTTPS for AI — cryptographic proof that AI decisions are constitutionally compliant.

**Tagline:** Govern your AI. Prove it.

---

## Audience 1: Developers (B2D)

### Who They Are
- Python developers building AI applications
- Using OpenAI, Claude, LangChain, or similar frameworks
- Concerned about doing the right thing but unclear on how
- Evaluate tools by: documentation quality, ease of install, performance overhead

### Core Message

> **Lint your AI decisions.** You lint your code. You scan for vulnerabilities. Now lint your AI. `pip install acgs-lite`, five lines of Python, 560 nanoseconds of overhead. Constitutional governance that runs faster than a cache hit.

### Tone
Technical, concise, show-don't-tell. Lead with code, not concepts.

### Key Content

**README / PyPI:**
```python
from acgs_lite import Constitution, GovernedAgent

constitution = Constitution.from_yaml("rules.yaml")
agent = GovernedAgent(my_agent, constitution=constitution)
result = agent.run("process this request")  # Governed.
```

**Blog post angles:**
- "Adding AI governance to your FastAPI app in 5 minutes"
- "How ACGS validates 2.8M decisions per second (Rust + PyO3 deep dive)"
- "MACI: Why your AI agent shouldn't validate its own output"
- "Building a GitLab governance gate in 10 lines of YAML"

**Where they live:**
- Hacker News, Reddit r/MachineLearning, r/Python
- Python/AI Discord servers
- GitHub trending
- PyCon, AI Engineer Summit

### What NOT to say to developers
- Don't lead with compliance or regulation (that's the CISO pitch)
- Don't use enterprise jargon ("stakeholder alignment," "risk posture")
- Don't oversell — let the code speak
- Don't mention the "built by non-technical founder" story (focus on engineering quality)

---

## Audience 2: CTOs / VP Engineering (B2B Technical Decision Maker)

### Who They Are
- Responsible for engineering organization's technical decisions
- Evaluate tools by: architectural fit, team adoption, maintenance burden
- Care about: developer productivity, system reliability, audit readiness
- Already managing SOC 2, GDPR, and other compliance obligations

### Core Message

> **Governance infrastructure, not governance theater.** Your AI systems make consequential decisions at scale. ACGS embeds constitutional governance directly into your pipeline — a CI/CD stage, not a consulting engagement. Sub-microsecond overhead. Cryptographic audit trail. Nine regulatory frameworks. Your team adopts it like any other dev tool.

### Tone
Architectural, strategic, ROI-aware. Speak to system design, not features.

### Key Content

**One-pager / email:**
- Problem: AI decisions are unaudited; compliance is manual
- Solution: Governance as infrastructure (CI/CD stage + runtime validation)
- Differentiation: 560ns (no performance excuse to disable); 9 frameworks (single tool); MACI (architectural innovation)
- Proof: 3,820 tests, 847 benchmark scenarios, Rust backend
- Ask: 15-minute demo or design partner conversation

**Blog post angles:**
- "Why we built MACI: Separation of powers for AI agents"
- "The governance maturity model: from 'we have a policy doc' to provable compliance"
- "ACGS architecture deep-dive: constitutional hash, audit chains, and Rust validation"

**Where they reach decisions:**
- LinkedIn (thought leadership posts)
- Engineering blogs from peer companies
- Conference talks (GitLab Commit, KubeCon)
- Peer recommendations

### What NOT to say to CTOs
- Don't be salesy (they detect it instantly)
- Don't claim "zero false negatives" (say "847 tested scenarios, active fuzzing for edge cases")
- Don't oversimplify the architecture (they want to see depth)

---

## Audience 3: CISOs / DPOs / Compliance Officers (B2B Budget Holder)

### Who They Are
- Responsible for regulatory compliance and risk management
- Evaluate tools by: framework coverage, audit evidence quality, vendor risk
- Care about: regulatory deadlines, audit findings, insurance requirements
- Already managing GDPR, SOC 2, ISO 27001 compliance programs

### Core Message

> **Compliance evidence, not compliance promises.** EU AI Act enforcement begins August 2, 2026. Fines: up to 7% of global annual revenue. ACGS produces auditable, cryptographically verified compliance evidence for nine regulatory frameworks — EU AI Act, GDPR, NIST AI RMF, ISO 42001, SOC 2, HIPAA, ECOA/FCRA, NYC LL 144, and OECD AI Principles. Every AI decision generates a tamper-evident audit record. Your auditor gets a compliance report, not a trust-me.

### Tone
Risk-focused, evidence-based, regulatory-precise. Use framework names and article numbers.

### Key Content

**Compliance brief (PDF):**
- Framework coverage matrix (9 frameworks, 125 checklist items)
- EU AI Act Article 12/13/14 specific coverage
- Audit trail architecture diagram
- Sample compliance report output
- MACI separation of powers alignment with regulatory expectations
- Constitutional hash for tamper evidence

**Blog post angles:**
- "EU AI Act compliance checklist: 125 items, 72 automated"
- "What your SOC 2 auditor will ask about AI governance (and how to answer)"
- "From GDPR to AI Act: Why AI needs its own compliance layer"
- "MACI and the regulatory expectation of separation of duties"

**Where they reach decisions:**
- Industry compliance conferences
- Peer CISO networks (ISSA, ISC2)
- Analyst reports (Gartner, Forrester)
- Vendor security questionnaires

### What NOT to say to CISOs
- Don't say "open source" without immediately mentioning commercial license and support SLA
- Don't say "built by AI" (say "118 optimization experiments" and "3,820 automated tests")
- Don't undersell vendor risk — proactively address bus factor and roadmap

---

## Audience 4: Investors (Fundraising)

### Who They Are
- VC partners or angels evaluating AI infrastructure
- Evaluate by: market size, timing, moat, team, traction
- Care about: TAM, competitive positioning, path to $100M ARR

### Core Message

> **Constitutional governance for AI is a new infrastructure category — like SSL/TLS for the web.** The EU AI Act (Aug 2026, 7% fines) is the GDPR moment for AI. ACGS is the only tool producing auditable compliance proof across 9 regulatory frameworks with sub-microsecond latency. Bootstrapped, pre-revenue, 120+ product capabilities, Rust backend at 2.8M validations/sec. The AI governance market is $200M-750M today, growing to $1.4B-15.8B by 2030 (30-50% CAGR).

### Tone
Market-aware, data-driven, honest about stage. Show founder-market fit.

### Key Content

**Pitch deck structure:**
1. Problem (AI decisions are ungoverned)
2. Market (TAM: $1.4B-15.8B by 2030; EU AI Act as catalyst)
3. Solution (ACGS: HTTPS for AI)
4. Product (demo: 5 lines of code, 560ns, 9 frameworks)
5. Traction (if any: PyPI downloads, GitHub stars, design partners)
6. Business model (open-core, $299/$999/$5K+ tiers)
7. Competition (unique: only tool with compliance proof output)
8. Team (founder story + recruitment plan)
9. Ask (seed: $1-3M for GTM acceleration before Aug 2026 deadline)

### What NOT to say to investors
- Don't lead with "built by non-technical founder with AI" (lead with market timing and product moat)
- Don't claim $10M ARR in 3 years without showing the bottoms-up math
- Don't hide the bus factor — present the recruitment plan as mitigation

---

## Audience 5: Design Partners (Pre-Launch)

### Who They Are
- 20-100 person EU-based AI/ML companies
- Currently in SOC 2 audit prep or beginning EU AI Act compliance
- Have a platform engineer who could champion ACGS internally
- Willing to provide feedback, case study, and logo in exchange for free access

### Core Message

> **Shape the future of AI governance.** We're looking for 3-5 design partners to co-develop the standard for AI constitutional governance. You get free Team tier ($12K/year value) for 6 months, direct founder access, and priority feature input. We get your feedback, a case study, and your logo. Help us build the tool your industry needs.

### Tone
Collaborative, exclusive, mutual-value. This is a partnership, not a sale.

### Outreach Template

```
Subject: Shaping AI governance together — design partner invitation

Hi [Name],

I'm building ACGS — constitutional governance infrastructure for AI systems.
Think: HTTPS for AI. 560ns validation, 9 regulatory frameworks, cryptographic
audit trails.

I'm looking for 3-5 design partners to shape the product before public launch.
[Company] caught my attention because [specific reason — SOC 2 prep, EU presence,
AI product].

As a design partner:
- Free Team tier ($999/month) for 6 months
- Direct access to me for feature requests
- Priority input on compliance framework coverage

In return:
- Quarterly feedback call (30 min)
- Case study when ready (co-authored, your approval)
- Logo on propriety.ai (with your permission)

Would a 15-minute call make sense? I can demo the GitLab CI/CD integration
or the runtime governance engine — your choice.

[Founder name]
```

---

## Cross-Audience Message Map

| Element | Developer | CTO | CISO | Investor |
|---------|-----------|-----|------|----------|
| **Lead with** | Code snippet | Architecture | Regulatory deadline | Market size |
| **Key metric** | 560ns, 5 lines | 3,820 tests, MACI | 9 frameworks, 125 items | $1.4B-15.8B TAM |
| **Social proof** | GitHub stars, benchmarks | Architectural innovation | Framework coverage | Growth trajectory |
| **CTA** | pip install | 15-min architecture review | Compliance assessment | Pitch meeting |
| **Avoid** | Compliance jargon | Sales pressure | "Open source" without context | Bus factor denial |
| **Channel** | HN, Reddit, PyCon | LinkedIn, conferences | Compliance events, peer networks | Warm intros, demo days |
