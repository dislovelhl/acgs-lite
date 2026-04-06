# ACGS Outreach Templates & Design Partner Materials

**Last updated:** 2026-04-06
**Purpose:** Copy-paste-ready outreach for pre-launch pipeline building

---

## 1. LinkedIn DM Templates

### 1A. Platform Engineer at EU B2B SaaS

> Hi [Name], I noticed you're working on platform engineering at [Company]. We're building ACGS -- a runtime governance layer for AI agents. Think of it as the missing enforcement plane between your orchestration tools and your compliance requirements.
>
> We're looking for a small group of design partners who are deploying AI in production and care about audit evidence and approval boundaries. Partners get free Team tier for 6 months and direct founder access.
>
> Would you be open to a 15-minute call to see if it's relevant to what you're building?

### 1B. CTO at Series B Healthtech

> Hi [Name], congrats on the [recent raise / product milestone]. Healthcare AI is moving fast, and the compliance surface area is expanding just as quickly.
>
> We built ACGS -- constitutional governance for AI agents. It validates actions before execution, enforces role separation (proposer vs. validator), and leaves behind audit-ready evidence. 5 lines of Python to wrap an agent. 560ns of overhead.
>
> We're recruiting design partners in healthtech specifically. Free Team tier for 6 months, founder-level access, and your compliance needs directly shaping the roadmap. Worth a quick look?

### 1C. DevOps Lead at Fintech Using GitLab

> Hi [Name], saw that [Company] runs on GitLab -- we have a native CI/CD governance gate that adds constitutional rule checks to every merge request. 5 lines of YAML, runs in your existing pipeline.
>
> ACGS governs what AI systems are allowed to do and leaves behind the evidence your auditors need. We already cover 9 regulatory frameworks including SOC 2 and EU AI Act.
>
> We're looking for a few fintech teams to be design partners. Free Team tier, direct input on the product. Would love your feedback if this is on your radar.

### 1D. CISO at Mid-Stage Company Deploying AI

> Hi [Name], quick question: as [Company] deploys more AI capabilities, how are you handling governance proof for agent-initiated actions? Not output filtering -- actual runtime governance with audit trails.
>
> That's exactly what ACGS does. It enforces structural separation of powers (proposer, validator, executor are separate roles), validates actions against machine-readable rules before execution, and produces evidence your security and compliance teams can review.
>
> We're recruiting 3-5 design partners. Would be very interested in your perspective on what runtime governance needs to look like in practice.

### 1E. AI/ML Engineer Building Agents

> Hi [Name], I saw your work on [project / post about agents]. Cool stuff.
>
> We built ACGS -- `pip install acgs-lite`, wrap your agent in 5 lines, and you get runtime governance: every action validated against constitutional rules before execution, MACI role separation baked in, and a full audit trail. 560ns overhead on the hot path.
>
> We're looking for builders who are pushing agents into real workflows to be early design partners. Free Team tier for 6 months, and your use cases directly shape the product. Interested?

---

## 2. Design Partner Program One-Pager

*Format: send as PDF attachment or paste into email body.*

---

### ACGS Design Partner Program

**Constitutional Governance for AI Agents**

---

#### What This Program Is

We're selecting 3-5 companies building serious AI/ML systems to be founding design partners for ACGS. You get early access, direct founder collaboration, and a free tier. We get real-world feedback that shapes the product.

This is not a sales pitch. It's a partnership for teams who need runtime governance and want to help define what good looks like.

---

#### What Partners Get

| Benefit | Details |
|---------|---------|
| **Free Team tier** | Full product access for 6 months (normally $999/mo) |
| **Direct founder access** | Slack channel + monthly 1:1 call |
| **Feature input priority** | Your use cases move to the top of the roadmap |
| **Early access** | New capabilities before public release |
| **Compliance support** | Help mapping your governance needs to ACGS rules |
| **Co-marketing** | Joint case study amplified through our channels |

---

#### What ACGS Gets

| Commitment | Details |
|------------|---------|
| **Logo usage** | Permission to display your logo on our website |
| **Case study** | One written case study after the first 3 months |
| **Quarterly feedback** | 30-minute feedback call each quarter |
| **Reference availability** | Willingness to speak to 2-3 enterprise prospects per year |

---

#### Ideal Partner Profile

- **Team size:** 20-100 people
- **Region:** EU-based (primary) or EU-regulated
- **Industry:** B2B SaaS, FinTech, HealthTech, InsurTech, or AI/ML tooling
- **Stage:** Series A-B or equivalent revenue
- **Trigger:** SOC 2 preparation, EU AI Act readiness, or customer AI governance requests
- **Tech stack:** Python, GitLab or GitHub CI/CD, any AI/ML framework
- **AI maturity:** Deploying agents or copilots that take actions (not just chatbots)

---

#### Program Timeline

| Phase | Timeframe | Activity |
|-------|-----------|----------|
| **Onboarding** | Weeks 1-2 | Integration support, initial governance setup |
| **Active use** | Months 1-3 | Weekly async check-ins, feature requests |
| **Case study** | Month 3 | Draft case study from early results |
| **Ongoing** | Months 4-6 | Quarterly calls, continued free access |
| **Transition** | Month 6 | Convert to paid Team tier or graceful offboarding |

---

#### How to Apply

Reply to this email or DM with:

1. **Company name** and what you build
2. **AI use case** you'd govern with ACGS
3. **Compliance context** (SOC 2, EU AI Act, internal policy, other)
4. **Timeline** -- when do you need governance in production?

We'll schedule a 20-minute call within 48 hours. No pitch deck. Just a conversation about what you need.

---

#### About ACGS

ACGS is the constitutional governance layer for AI agents. It governs actions inside the runtime, keeps proposer and validator roles separate, and produces audit-ready evidence tied to rule state.

- `pip install acgs-lite` -- 5 lines to wrap any agent
- 560ns hot-path overhead -- governance that teams won't disable
- 9 regulatory frameworks covered (SOC 2, EU AI Act, HIPAA, and more)
- AGPL open source with commercial options

**Website:** propriety.ai
**GitHub:** github.com/acgs

---

## 3. Cold Email Sequence

### Email 1: Problem-Aware Intro

**Subject:** EU AI Act enforcement is coming -- is [Company] ready?

**Body:**

Hi [Name],

The EU AI Act enforcement deadline is approaching, and Article 12 requires logging and audit trails for all AI systems -- not just high-risk ones.

Most teams deploying AI agents today can't prove governance to an auditor. They have orchestration (LangGraph, CrewAI) and maybe output filters (Guardrails AI), but no runtime governance layer that validates actions before execution and leaves behind reviewable evidence.

That's the gap ACGS fills. Constitutional governance for AI agents. 5 lines of Python. 560ns overhead. 9 regulatory frameworks mapped.

Would it be useful to see a 2-minute demo of what governance proof looks like for an AI agent?

Best,
[Your name]

---

### Email 2: Value Demo

**Subject:** What runtime AI governance actually looks like (2-min video)

**Body:**

Hi [Name],

Following up -- here's what ACGS looks like in practice:

**For developers:** `pip install acgs-lite`, wrap your agent, and every action is validated against constitutional rules before execution. [Link to CLI quickstart]

**For compliance teams:** Every governed action produces an audit record with the rule version, decision outcome, and cryptographic hash. Exportable, inspectable, regulator-ready. [Link to ClinicalGuard healthcare showcase]

The core engine is open source. Teams pay when they need compliance reports, multi-framework assessment, or cloud audit retention -- the things auditors actually require.

Happy to do a 15-minute walkthrough tailored to [Company]'s stack if that's useful.

Best,
[Your name]

---

### Email 3: Social Proof + Soft Close

**Subject:** Design partner spots filling up

**Body:**

Hi [Name],

Last note -- we're selecting 3-5 design partners for ACGS and have [X] spots remaining. Partners get:

- Free Team tier for 6 months ($999/mo value)
- Direct founder access and feature priority
- Your governance use cases shaping the roadmap

What we ask: logo permission, one case study, and a quarterly feedback call.

Ideal fit: EU-based AI/ML team, 20-100 people, in SOC 2 or EU AI Act prep, deploying agents that take real actions.

If [Company] is thinking about AI governance at all, I'd love 15 minutes to explore whether this partnership makes sense.

No pressure either way -- happy to stay in touch if the timing isn't right yet.

Best,
[Your name]

---

## 4. Target Company Criteria Checklist

### Where to Find Prospects

| Source | How to Use It |
|--------|---------------|
| **LinkedIn Sales Navigator** | Filter: EU region, 20-200 employees, AI/ML or SaaS industry, Series A-B. Search for titles: "Head of AI", "Platform Engineer", "CISO", "CTO", "DevOps Lead" |
| **GitHub** | Search for repos using LangGraph, CrewAI, AutoGen, or agent frameworks. Filter by org size and activity. Look at contributor profiles for company info |
| **GitLab public groups** | Companies using GitLab CI/CD with AI/ML pipelines. Check GitLab Marketplace reviews for governance/compliance tools |
| **EU AI Act events** | Attendee lists from AI Act compliance webinars, EU AI conferences (AI Summit, Web Summit AI track). Speaker companies at governance panels |
| **Crunchbase / Dealroom** | Filter: EU, Series A-B, AI/ML vertical, raised in last 18 months. Cross-reference with compliance hiring signals |
| **SOC 2 directories** | Companies listed as "in progress" on Vanta, Drata, or Secureframe partner pages. They're actively investing in compliance |
| **Hacker News** | Search for "EU AI Act", "AI governance", "AI compliance" discussions. Check commenter profiles |
| **Product Hunt** | AI agent products launched in last 6 months, EU-based founders |

### Qualification Criteria

Score each prospect 1-5 on each dimension. Minimum score of 15/25 to pursue.

| Criterion | 1 (Weak) | 3 (Moderate) | 5 (Strong) |
|-----------|----------|--------------|------------|
| **AI maturity** | Experimenting with chatbots | AI features in production | Agents taking autonomous actions |
| **Compliance pressure** | No regulatory requirements | General security practices | Active SOC 2 / EU AI Act / HIPAA prep |
| **Team size** | <10 or >500 | 10-20 or 200-500 | 20-100 |
| **Tech fit** | No Python, no CI/CD | Some Python, basic CI/CD | Python-heavy, GitLab/GitHub CI/CD |
| **Engagement signal** | Cold -- no prior interaction | Warm -- liked/commented content | Hot -- replied to DM, attended event |

### Priority Signals (Pursue Immediately)

These signals indicate high-probability prospects. If you see any of these, move the company to the top of your outreach list:

- [ ] **Hiring for compliance**: Job postings for "AI Governance", "Compliance Engineer", "DPO", or "AI Ethics" roles
- [ ] **EU AI Act mentions**: Blog posts, LinkedIn posts, or conference talks referencing EU AI Act preparation
- [ ] **Agent framework usage**: Public repos or job postings mentioning LangGraph, CrewAI, AutoGen, or custom agent frameworks
- [ ] **Recent funding**: Series A-B in last 6 months (budget available, need to professionalize)
- [ ] **SOC 2 in progress**: Mentioned in blog, job posts, or listed on compliance tool partner pages
- [ ] **GitLab CI/CD**: Visible in public repos or mentioned in engineering blog (direct integration path)
- [ ] **Customer governance requests**: Company blog or changelog mentions adding governance features for their customers
- [ ] **Regulated industry**: Healthcare, finance, insurance, legal, or government-adjacent

### Disqualification Signals (Deprioritize)

- Pure research / experimentation with no production AI
- Interest only in prompt filtering or content safety (Guardrails AI territory, not ACGS)
- Wants a compliance dashboard but not runtime governance
- No Python in stack
- Pre-seed with no revenue (can't convert to paid after 6 months)
- >500 employees (enterprise sales motion needed, not design partner)

### Outreach Tracking Template

| Company | Contact | Title | Source | Qual Score | Priority Signals | Status | Next Action | Date |
|---------|---------|-------|--------|------------|------------------|--------|-------------|------|
| | | | | /25 | | Cold / Contacted / Replied / Call Scheduled / Partner | | |

Fill in 20 rows before launch. Target: 3-5 convert to design partners.

---

## Quick Reference: Key Talking Points

Keep these handy for any conversation:

| Topic | Line |
|-------|------|
| **What ACGS is** | Constitutional governance layer for AI agents. Governs actions, not outputs. |
| **Differentiation** | Guardrails AI validates outputs. OPA governs infrastructure. ACGS governs agent actions. |
| **Developer hook** | `pip install acgs-lite`. 5 lines. 560ns overhead. |
| **Compliance hook** | 9 regulatory frameworks. Audit-ready evidence. MACI role separation. |
| **Why now** | EU AI Act enforcement approaching. Article 12 logging applies to all AI systems. |
| **Design partner ask** | Free Team tier for 6 months. We want your feedback, not your money (yet). |
| **Soft CTA** | "Would love your perspective on what runtime governance needs to look like." |
