# ACGS Go-to-Market Playbook

**Date:** 2026-03-19
**Status:** Pre-launch plan
**Dependencies:** Economic Engine Design (03), Competitive Landscape (04)

---

## 1. Market Entry Strategy

### Primary Wedge: GitLab CI/CD Governance Gate

**Why GitLab first:**
- Most mature existing integration (webhook + CI/CD stage + MCP server + MACI enforcer)
- Clear buyer persona: DevOps/Platform Engineering leads
- Distribution channel: GitLab Marketplace
- Viral mechanism: every MR with governance is visible to the entire team
- Natural upsell: one team adopts -> other teams see it -> org-wide deployment

**Important distinction (Panel Round 2 fix):** GitLab CI/CD integration provides **code-level governance** (scanning diffs, commit messages, MR descriptions against constitutional rules). This is complementary to but distinct from the core engine's **runtime governance** (validating AI agent actions in production). Both are valuable. The GitLab wedge gets ACGS into the development workflow; runtime governance follows as the next sell.

- **GitLab integration** = "Governance gate in your pipeline" (catches policy violations before merge)
- **Runtime engine** = "Governance proof in production" (proves AI decisions are compliant at execution time)

**Positioning statement:**

> "Constitutional governance for every merge request -- and every AI decision in production. 5 lines of YAML. 560 nanoseconds of overhead. 9 regulatory frameworks covered."

### Target Customer Profile (Year 1)

| Attribute | Ideal Customer |
|-----------|---------------|
| **Size** | 10-200 engineers |
| **Region** | EU (primary), US (secondary) |
| **Industry** | B2B SaaS, FinTech, HealthTech, InsurTech |
| **Trigger** | EU AI Act preparation, SOC 2 audit, investor due diligence |
| **Champion** | Platform engineer, DevOps lead, or Head of AI/ML |
| **Budget holder** | CTO, CISO, or VP Engineering |
| **Tech stack** | GitLab CI/CD, Python, any AI/ML framework |
| **Pain** | "We deploy AI but can't prove governance to auditors/regulators" |

---

## 2. Distribution Channels

### Channel 1: PyPI / pip install (Developer Adoption)

**Goal:** 10K monthly downloads within 12 months

**Actions:**
- Publish `acgs` to PyPI with excellent metadata and classifiers
- README optimized for PyPI rendering (the 5-line quickstart)
- Depends on zero heavy dependencies for initial install
- Mention in popular AI/ML newsletters and communities

### Channel 2: GitLab Marketplace

**Goal:** Top 10 in "Security & Compliance" category

**Actions:**
- Submit ACGS as GitLab CI/CD component
- Include one-click pipeline stage addition
- Co-marketing opportunity with GitLab (governance is a GitLab strategic priority)
- Integration with GitLab Duo Chat via MCP server

### Channel 3: Content Marketing (EU AI Act Focus)

**Goal:** Establish ACGS as the go-to resource for EU AI Act technical compliance

**Content calendar:**
- **Weekly:** Technical blog post on AI governance topic
- **Monthly:** EU AI Act compliance deep-dive (one article per Article)
- **Quarterly:** State of AI Governance report (using anonymized data)
- **Countdown:** "X days until EU AI Act enforcement" content series (starting 500 days out)

**SEO targets:**
- "EU AI Act compliance software"
- "AI governance framework Python"
- "constitutional AI governance"
- "AI audit trail"
- "MACI separation of powers AI"

### Channel 4: Conference / Speaking

**Priority events:**
- KubeCon EU (OPA/governance audience overlap)
- GitLab Commit (direct customer audience)
- AI Engineer Summit (developer audience)
- EU AI Act compliance conferences (buyer audience)
- PyCon (Python developer community)

### Channel 5: AI Code Generation Tools

**Goal:** `acgs` suggested by AI coding assistants when developers ask about AI governance

**Actions:**
- Ensure high-quality documentation that LLMs can index
- Create clear CLAUDE.md and .cursorrules for AI assistant context
- Contribute governance-related examples to popular AI framework docs
- Similar to Supabase's viral distribution via Bolt.new/Lovable/Cursor

---

## 3. Conversion Funnel

```
AWARENESS                    ADOPTION                    CONVERSION
(know ACGS exists)           (using free tier)           (paying customer)

Blog/SEO/Conf ──►  pip install ──► Local usage ──► Need compliance report ──► Pro ($299/mo)
                                        │                                         │
GitLab Marketplace ──► CI/CD stage ─────┘                                         │
                                                                                  │
                                        Multi-team ──► Need SSO/frameworks ──► Team ($999/mo)
                                                                                  │
                                        Regulated industry ──► Need SLA/on-prem ──► Enterprise ($5K+)
```

### Conversion Triggers (from free to paid)

| Trigger | Signal | Target Tier |
|---------|--------|-------------|
| Team needs compliance report for audit | User exports audit log manually | Pro |
| Team needs more than 1 compliance framework | User reads framework docs | Pro |
| Org deploying across multiple environments | Multiple constitutions needed | Team |
| Org needs SSO/SAML | IT security policy requires it | Team |
| Regulated industry requiring SLA | Legal/compliance team involved | Enterprise |
| On-premise deployment requirement | Security review rejects cloud | Enterprise |

---

## 4. Pricing Communication

### Landing Page Structure

```
HERO: "HTTPS for AI"
Constitutional governance for your AI systems.
560ns overhead. 9 regulatory frameworks. 5 lines of code.
[Get Started Free]  [View Pricing]

PROBLEM: (The single mother story -- 3 sentences)

SOLUTION: (Code snippet -- 5 lines)

SOCIAL PROOF: (Logos, stats, testimonials -- when available)

PRICING:
  Community (Free)     Pro ($299/mo)        Team ($999/mo)        Enterprise
  Full engine          + Compliance          + All frameworks      + Everything
  Local audit          + Cloud audit         + SSO                 + On-prem
  Community support    + Email support       + Priority support    + Dedicated engineer
  [Install]            [Start Free Trial]    [Start Free Trial]    [Contact Sales]

EU AI ACT COUNTDOWN: "X days until enforcement. Are you ready?"
[Take the free assessment]
```

### Objection Handling

| Objection | Response |
|-----------|----------|
| "We can build this ourselves" | You can. But 9 regulatory frameworks, cryptographic audit trails, and MACI separation of powers took 118 optimization experiments. Your compliance team needs proof now, not in 6 months. |
| "We already use OPA" | OPA is great for policy execution. ACGS adds regulatory compliance mapping, audit trail verification, and EU AI Act coverage on top. They are complementary. |
| "Why not just use Guardrails AI?" | Guardrails AI focuses on content safety (LLM output quality). ACGS focuses on constitutional governance (regulatory compliance proof). Different problems. |
| "It's open source, why pay?" | The engine is free forever. You pay for compliance reports, cloud audit retention, multi-framework assessment, and SLA -- the things your auditor and regulator require. |
| "Our AI is low-risk, we don't need this" | The EU AI Act requires risk assessment documentation for ALL AI systems, not just high-risk. Article 12 logging applies broadly. A governance audit trail is the minimum. |

---

## 5. Community Building

### Phase 1: Foundation (Months 1-3)

- GitHub Discussions enabled (not a separate forum)
- Contributing guide with CLA process
- Issue templates for bug reports, feature requests, framework requests
- First 10 external contributors targeted

### Phase 2: Growth (Months 4-9)

- Discord server with channels: #general, #compliance, #integrations, #showcase
- Monthly community call (30 min: roadmap update + Q&A)
- "ACGS Champions" program for active contributors
- Governance framework contribution guide (how to add a new regulatory framework)

### Phase 3: Ecosystem (Months 10-18)

- Third-party validator/rule marketplace
- Community-contributed compliance framework mappings
- Partner integrations (contributed by partners)
- Annual "Constitutional AI" virtual conference

---

## 6. Sales Motion (Enterprise)

### When to Introduce Sales (not before)

**Prerequisites (all must be true):**
- [ ] >$100K ARR from self-serve
- [ ] >3 inbound Enterprise inquiries per month
- [ ] At least 1 existing customer in regulated industry
- [ ] Product supports on-premise deployment
- [ ] SOC 2 Type II certification in progress

### Enterprise Sales Process

```
1. INBOUND SIGNAL
   - Self-serve user hits Team tier limits
   - Security review requires on-prem deployment
   - Compliance team requests custom framework
   - IT requires SSO/SCIM

2. DISCOVERY (Week 1)
   - Map regulatory requirements
   - Identify compliance frameworks needed
   - Understand AI deployment landscape
   - Identify budget holder (CISO vs CTO)

3. PROOF OF VALUE (Weeks 2-4)
   - Deploy in staging environment
   - Run compliance assessment against current AI systems
   - Generate gap report
   - Demonstrate MACI separation in their context

4. PROPOSAL (Week 5)
   - Custom pricing based on:
     - Number of AI systems
     - Compliance frameworks needed
     - Deployment model (cloud vs on-prem vs hybrid)
     - Support level required
   - Typical deal: $60K-200K/year

5. CLOSE (Weeks 6-8)
   - Legal review (AGPL or commercial license)
   - Security review
   - Contract signing
   - Onboarding kickoff
```

---

## 7. Key Metrics Dashboard

### Weekly Tracking

| Metric | Source | Target (Y1) |
|--------|--------|-------------|
| PyPI weekly downloads | PyPI stats | >2.5K/week |
| GitHub stars | GitHub | >5K total |
| Propriety.ai signups | Stripe/analytics | >500 total |
| Free -> Pro conversion (monthly) | Billing system | 3-5% |
| MRR | Stripe | >$25K by month 12 |

### Monthly Tracking

| Metric | Source | Target (Y1) |
|--------|--------|-------------|
| Monthly active constitutions | Telemetry (opt-in) | >1K |
| Compliance reports generated | Platform analytics | >500/month |
| NPS score | Survey | >50 |
| Community contributors | GitHub | >25 |
| Content impressions | Analytics | >100K/month |

### Quarterly Tracking

| Metric | Source | Target (Y1) |
|--------|--------|-------------|
| ARR | Stripe | $300K by Q4 |
| Net revenue retention | Billing cohort analysis | >110% |
| Enterprise pipeline | CRM | >$500K by Q4 |
| Framework coverage | Product | 9 -> 12 frameworks |

---

## 8. Pre-Launch Pipeline (Day Zero)

**Panel critique (Round 2):** The original 90-day plan assumed starting from zero awareness. B2B SaaS conversion from discovery to first payment typically takes 30-90 days. Without a pre-launch pipeline, the first paying customer arrives at Day 120-180, not Day 90.

### Pre-Launch Actions (Before Day 1)

| Action | Goal | Method |
|--------|------|--------|
| **Identify 20 warm leads** | People who will try ACGS on Day 1 | Scan: AI governance Twitter/LinkedIn discussions, EU AI Act compliance threads, GitLab governance feature requests |
| **Recruit 3-5 design partners** | Beta users who get free Team tier for 6 months in exchange for case study + logo | Direct outreach to EU-based AI startups in SOC 2 prep or facing customer AI governance questions |
| **Build in public** | Awareness before launch | Tweet/post progress on ACGS development; share benchmark results; engage in AI governance discussions |
| **Secure 1 conference talk** | Credibility + pipeline | Submit to GitLab Commit, KubeCon EU, or AI Engineer Summit (CFPs often open 3-6 months early) |
| **Legal preparation** | AGPL migration ready on Day 1 | CLA template drafted; AGPL FAQ written; trademark search completed |

### Design Partner Program

| Term | Detail |
|------|--------|
| **What partners get** | Free Team tier for 6 months; direct access to founder; feature input priority |
| **What ACGS gets** | Logo for website; written case study; quarterly feedback call; reference for enterprise prospects |
| **Ideal partner profile** | 20-100 person EU AI/ML company; in SOC 2 or EU AI Act prep; using GitLab or GitHub CI/CD |
| **Target count** | 3-5 partners pre-launch |
| **Exit** | After 6 months, convert to paid Team or graceful offboarding |

## 9. 90-Day Launch Plan (Revised)

### Days 1-30: Ship

| Week | Action | Deliverable |
|------|--------|-------------|
| 1 | AGPL license migration | LICENSE file updated, CLA process live |
| 1 | PyPI package published | `pip install acgs` works |
| 2 | Propriety.ai pricing page live | Stripe checkout integrated |
| 2 | Landing page with "HTTPS for AI" positioning | propriety.ai homepage |
| 3 | GitLab Marketplace submission | Listing submitted |
| 3 | Developer quickstart documentation | docs.propriety.ai |
| 4 | Cloud audit log service (MVP) | Pro feature operational |
| 4 | **Design partners onboarded (3-5)** | **Partners using ACGS in staging/prod** |

### Days 31-60: Seed

| Week | Action | Deliverable |
|------|--------|-------------|
| 5-6 | First 5 blog posts (EU AI Act series) | Published on blog |
| 5-6 | Submit to Hacker News, Reddit r/MachineLearning | Posts live |
| 7 | GitHub Discussions + Contributing guide | Community foundation |
| 7-8 | Reach out to 20 additional potential adopters | 10 conversations started |
| 8 | EU AI Act countdown landing page | Countdown timer live |
| 8 | **First design partner case study drafted** | **Social proof ready** |

### Days 61-90: Validate

| Week | Action | Deliverable |
|------|--------|-------------|
| 9-10 | **First 3 Pro customers** (from warm pipeline + design partner referrals) | **$897/month MRR** |
| 10-11 | User feedback interviews (5 users) | Feedback synthesized |
| 11-12 | Product iteration based on feedback | V1.1 shipped |
| 12 | First monthly community call | Recording published |
| 12 | 90-day retrospective | PMF assessment document |

**Revised confidence:** With pre-launch pipeline and design partners, 3 Pro customers by Day 90 is achievable (Medium-High confidence vs Low confidence without pre-launch work).
