# ACGS Economic Engine Design

**Date:** 2026-03-19
**Status:** Design proposal (pre-implementation)
**Dependencies:** Business Panel Analysis (01), Market Research Evidence (02)

---

## Design Thesis

> **Don't sell software. Sell proof of compliance.**
>
> ACGS's economic engine is not "governance engine as a service" -- that is the OPA/Styra $12M trap. The economic engine is **continuous proof of compliance status** -- every validation is an auditable receipt proving your AI was constitutionally compliant at that moment, against a specific regulatory framework.

---

## 1. License Strategy

### Recommended: AGPL-3.0-or-later + Commercial Dual License

ACGS now ships under AGPL-3.0-or-later with a separate commercial license for proprietary and SaaS deployments. Contribution terms are documented in `CONTRIBUTING.md`; maintainers can request additional CLA paperwork when dual-licensing rights are required.

| Component | License | Rationale |
|-----------|---------|-----------|
| ACGS Python library (`acgs`, compatibility namespace `acgs_lite`) | **AGPL-3.0-or-later** | Prevents cloud provider strip-mining; OSI-compliant; validated by Grafana ($270M ARR) |
| ACGS integrations | AGPL-3.0-or-later | Follows core |
| `enhanced-agent-bus` | AGPL-3.0-or-later | Platform layer needs stronger protection |
| Commercial license | Proprietary | For enterprises that cannot comply with AGPL |
| `propriety-ai` SaaS | Proprietary | Never open-sourced |

**Why AGPL over other options:**

| License | Problem for ACGS |
|---------|-----------------|
| Apache-2.0 (legacy baseline) | AWS/GCP can package as managed service with zero contribution |
| SSPL | Not OSI-approved; controversial (Redis/Elastic backlash) |
| BSL | Not OSI-approved; triggered OpenTofu fork for HashiCorp |
| **AGPL-3.0-or-later** | **OSI-approved; prevents SaaS exploitation; Grafana validated at $270M ARR** |

**Contribution policy:** Contributions land under AGPL-3.0-or-later by default. When maintainers need dual-licensing rights for commercial distribution, they can request separate CLA paperwork before merge.

### AGPL for Embedded Libraries: Impact Analysis

**Panel critique (Round 2):** Grafana is an observability tool (not embedded in customer products). ACGS is an embedded library (`pip install acgs` into customer AI pipelines). The AGPL implications differ fundamentally.

**AGPL trigger for ACGS users:**

| Usage Pattern | AGPL Triggered? | Explanation |
|---------------|-----------------|-------------|
| Internal-only AI pipeline (not exposed over network) | **No** | AGPL only triggers on network interaction with third parties. Internal tools are exempt |
| SaaS product using ACGS to validate AI output served to users | **Yes** | Network interaction with external users triggers AGPL Section 13 (Corresponding Source obligation) |
| CI/CD pipeline (GitLab stage) | **No** | CI/CD runs internally; output is a pass/fail, not a network service |
| On-prem enterprise deployment | **No** | No network interaction with third parties |
| Cloud provider wrapping ACGS as a managed service | **Yes** | This is the primary protection target |

**Key insight:** Most ACGS use cases (internal pipelines, CI/CD, on-prem) do **not** trigger AGPL. The license only bites when:
1. A cloud provider offers ACGS-as-a-service (the protection target), or
2. A SaaS company embeds ACGS validations into a customer-facing service

For case #2, the **commercial dual license** exists: enterprises embedding ACGS in SaaS products purchase a commercial license (removing AGPL obligations). This is the identical model MongoDB (SSPL) and Grafana (AGPL) use -- and it is itself a revenue stream.

**Enterprise objection mitigation:**

| Enterprise concern | Response |
|-------------------|----------|
| "AGPL means we have to open-source our product" | Only if you serve ACGS functionality over a network to external users. Internal use is fully exempt. For SaaS embedding, we offer a commercial license |
| "Our legal team rejects all AGPL" | We offer a commercial license (included in Team and Enterprise tiers) that removes all AGPL obligations |
| "What about transitive AGPL contamination?" | AGPL applies to the ACGS library and modifications to it, not to your application that calls it via API. FSF guidance and case law support this interpretation for library usage |

**Commercial license as revenue accelerator:** Every enterprise that embeds ACGS in a SaaS product needs a commercial license. This converts AGPL from a "developer friction" problem into a **sales qualification signal** -- any SaaS company using ACGS in production is a pre-qualified commercial license buyer.

**Decision: AGPL-3.0-or-later confirmed and implemented.** The embedded-library concern is real but manageable through dual licensing. The commercial license requirement for SaaS embedding creates an additional monetization path that Apache-2.0 would not provide.

---

## 2. Pricing Architecture

### Three pricing dimensions: Validation Volume x Compliance Frameworks x Enterprise Features

---

### Tier 0: Community (Free, AGPL)

**Target:** Individual developers, open-source projects, evaluation

| Feature | Included |
|---------|----------|
| ACGS library complete engine | Yes |
| Single custom constitution | Yes |
| Local audit log (no cloud sync) | Yes |
| Community support (GitHub Issues) | Yes |
| MACI separation of powers | Yes |
| Rust backend (self-compiled) | Yes |
| **Compliance report export** | **No** |
| **EU AI Act modules** | **No** |
| **Cloud audit sync** | **No** |
| **SLA** | **No** |

**Limits:** No validation cap (runs locally). No support SLA.

**Purpose:** Developer adoption. Bottom of funnel. This is the "pip install" that creates habit formation.

---

### Tier 1: Pro -- $299/month ($249/month annual)

**Target:** 10-50 person AI teams with early compliance needs

| Feature | Included |
|---------|----------|
| Everything in Community | Yes |
| **1M validations/month** | Yes (overage: $0.10/1K) |
| **3 compliance frameworks** (choose from 9) | Yes |
| EU AI Act Article 12 audit logger | Yes |
| Risk classification engine | Yes |
| Compliance gap report (PDF/JSON export) | Yes |
| Cloud audit log sync (30-day retention) | Yes |
| Email support (48h SLA) | Yes |
| Dashboard (Propriety.ai) | Yes |

**Key upsell triggers:** Team growth (need more frameworks), retention requirements (need longer audit logs), compliance audit preparation.

---

### Tier 2: Team -- $999/month ($849/month annual)

**Target:** 50-500 person organizations with multi-team AI deployment

| Feature | Included |
|---------|----------|
| Everything in Pro | Yes |
| **10M validations/month** | Yes (overage: $0.06/1K) |
| **All 9 compliance frameworks** | Yes |
| EU AI Act Article 13 transparency disclosure | Yes |
| EU AI Act Article 14 human oversight gateway | Yes |
| Multi-constitution management (dev/staging/prod) | Yes |
| Constitutional change approval workflow | Yes |
| Cloud audit log (1-year retention) | Yes |
| MACI separation dashboard | Yes |
| SSO (SAML/OIDC) | Yes |
| Slack/Teams alert integration | Yes |
| Priority support (4h SLA) | Yes |

**Key upsell triggers:** Regulated industry requirements, on-prem needs, custom framework requests, dedicated support needs.

---

### Tier 3: Enterprise -- Custom (starting $5K/month)

**Target:** Banks, healthcare, government, insurance, Fortune 500

| Feature | Included |
|---------|----------|
| Everything in Team | Yes |
| **Unlimited validations** | Yes |
| **All frameworks + custom frameworks** | Yes |
| On-premise / VPC deployment | Yes |
| 560ns P50 SLA (Rust backend guaranteed) | Yes |
| Dedicated compliance engineer | Yes |
| Quarterly constitutional review | Yes |
| Audit integration (Splunk, Datadog, ELK) | Yes |
| FedRAMP / ISO 27001 readiness support | Yes |
| Custom rule engine extensions | Yes |
| 99.99% uptime SLA | Yes |
| Dedicated support (1h SLA, named engineer) | Yes |

---

### Pricing Rationale

| Decision | Rationale | Evidence |
|----------|-----------|---------|
| $299 Pro entry point | Below Guardrails AI Pro; accessible to startup teams; above "toy" perception | Guardrails AI usage-based; Snyk Team ~$25/seat/month |
| Per-validation overage | Natural unit for governance (matches Guardrails AI model) | Guardrails AI validates per-operation |
| Framework count as tier differentiator | Framework coverage is the moat; more frameworks = more value | No competitor offers 9 frameworks |
| $999 Team (not per-seat) | Per-seat penalizes adoption; flat rate encourages org-wide deployment | PostHog explicitly avoided per-seat |
| $5K+ Enterprise floor | Matches compliance software expectations ($59K+/year at Checkmarx) | Checkmarx ~$59K/year starting |

---

### Budget Creation Playbook

**Panel critique (Round 2):** $299/month is not expensive, but "AI governance" is not yet a recognized budget line item. The friction is not price -- it is creating a new budget category.

**Who pays and why (by trigger):**

| Trigger | Budget Owner | Budget Category (existing) | Pitch |
|---------|-------------|---------------------------|-------|
| EU AI Act deadline | CISO / DPO | Regulatory compliance | "This is the same budget line as GDPR tools. AI Act is the next GDPR" |
| SOC 2 audit finding | CTO / VP Eng | Security tooling | "Auditor flagged AI governance gap. This closes it for $299/month vs $50K consulting" |
| Investor due diligence | CEO / CTO | Operational readiness | "Investors are asking about AI governance. This gives you a compliance dashboard to show them" |
| Customer contract clause | Head of Sales / Legal | Revenue protection | "Enterprise customer requires AI governance attestation. Without it, we lose the deal" |
| Insurance underwriting | CFO / Risk | Insurance premium reduction | "Insurer offers lower premium with provable AI governance. ACGS pays for itself" |

**Key insight:** Never sell "AI governance" as a new budget. Always attach to an existing budget with a recognized category. The champion creates the PO; the budget owner signs it.

**First-deal playbook:**
1. Find teams already in SOC 2 audit or EU AI Act preparation (they have budget allocated)
2. Position ACGS as a tool within their existing compliance program (not a new initiative)
3. Price anchor against the alternative: $50K-100K compliance consulting engagement
4. $299/month looks like a rounding error against a $50K consulting quote

### Demand Drivers Beyond EU AI Act

**Panel critique (Round 2):** The flywheel depends entirely on EU AI Act as the forcing function. This is single-point-of-failure risk.

| Demand Driver | Timeline | Forcing Mechanism | Independence from EU AI Act |
|---------------|----------|-------------------|----------------------------|
| **EU AI Act** (primary) | Aug 2026 | 7% global revenue fine | -- |
| **Insurance underwriting** | Now | Insurers requiring AI governance for cyber policy renewal | Fully independent |
| **Investor due diligence** | Now | VCs asking "what's your AI governance?" in diligence | Fully independent |
| **Customer contracts** | Now | Enterprise buyers adding AI governance clauses to vendor contracts | Fully independent |
| **SOC 2 + AI criteria** | 2025-2026 | SOC 2 auditors adding AI-specific trust criteria | Partially independent |
| **NIST AI RMF adoption** | 2025-2027 | US federal procurement requiring NIST AI RMF compliance | Fully independent |
| **State-level US regulation** | 2025-2028 | Colorado AI Act (2024), NYC LL 144 (2023), others pending | Fully independent |
| **Class action litigation** | Now | Plaintiffs using "no AI governance" as evidence of negligence | Fully independent |

**Revised flywheel (multi-driver):** The EU AI Act is the strongest single driver, but the flywheel should be activated by ANY compliance trigger -- not exclusively by EU regulation. Insurance, investor DD, and customer contracts are already active today and do not require waiting until August 2026.

## 3. Economic Engine Flywheel

```
                    +------------------+
                    |  Open Source      |
                    |  Adoption         |
                    |  (AGPL engine)    |
                    +--------+---------+
                             |
                    pip install acgs
                    5 lines of code, zero friction
                             |
                             v
                    +------------------+
                    |  Developer Habit  |
                    |  Formation        |
                    |  (local usage)    |
                    +--------+---------+
                             |
                    ANY compliance trigger:
                    EU AI Act / SOC 2 audit / insurance /
                    investor DD / customer contract / litigation
                             |
                             v
                    +------------------+
                    |  Compliance Need  |<---- Multiple forcing functions
                    |  Trigger          |      (not single EU dependency)
                    |  (need proof)     |
                    +--------+---------+
                             |
                    Need: compliance reports, audit retention,
                    framework coverage, change workflows
                             |
                             v
                    +------------------+
                    |  Pro/Team         |
                    |  Purchase         |
                    |  ($299-$999/mo)   |
                    +--------+---------+
                             |
                    Multi-team expansion, more frameworks,
                    more validation volume, more integrations
                             |
                             v
                    +------------------+
                    |  Enterprise       |---- Net revenue retention >120%
                    |  Expansion        |
                    |  ($5K+/mo)        |
                    +--------+---------+
                             |
                    Enterprise demands more frameworks,
                    more integrations, more features
                             |
                             v
                    +------------------+
                    |  Product          |---- Feeds back to open source core
                    |  Improvement      |
                    +------------------+
```

### Flywheel Acceleration Mechanisms

1. **GitLab Marketplace listing** -- every GitLab CI/CD user sees ACGS as a governance stage option
2. **`X-Governed-By: ACGS` response header** -- viral awareness in every API call
3. **"ACGS Certified" badge** -- social proof on websites and marketing materials
4. **AI code generation tools** (Cursor, Copilot, Claude Code) suggesting `acgs` for governance -- similar to Supabase's viral distribution via Bolt.new/Lovable
5. **EU AI Act countdown content** -- urgency-driven demand generation

---

## 4. Differentiation from OPA/Styra ($12M Trap)

OPA/Styra's $12M ARR trap stems from: policy execution is **infrastructure** -- undifferentiated, anyone can write Rego policies.

ACGS avoids this trap through four mechanisms:

| Mechanism | OPA/Styra | ACGS |
|-----------|-----------|------|
| **Output** | Policy pass/fail | Auditable compliance report with regulatory mapping |
| **Moat** | Rego language (replicable) | 9-framework compliance knowledge base (domain expertise) |
| **Trust anchor** | None built-in | Constitutional hash (`608508a9bd224290`) providing cryptographic non-repudiation |
| **Forcing function** | Optional (security best practice) | Mandatory (EU AI Act = 7% global revenue fine) |

---

## 5. Key Revenue Metrics & Targets

### Leading Indicators

| Metric | Target | Benchmark |
|--------|--------|-----------|
| PyPI monthly downloads | >10K (Y1) -> >100K (Y3) | Guardrails AI trajectory |
| GitHub stars | >5K (Y1) -> >20K (Y3) | PostHog/Supabase trajectory |
| Free -> Pro conversion rate | 3-5% | PLG industry standard |
| Pro -> Team upgrade rate | 15-20%/year | Snyk experience |
| Monthly active constitutions | Track as engagement metric | Novel metric for category |

### Revenue Targets

| Metric | Target | Benchmark |
|--------|--------|-----------|
| Net revenue retention | >120% | HashiCorp/Datadog standard |
| Average revenue per Pro customer | $3,588/year | $299/mo |
| Average revenue per Team customer | $11,988/year | $999/mo |
| Average revenue per Enterprise customer | $60K-200K/year | Checkmarx comparable |
| CAC payback period | <6 months (Pro self-serve), <12 months (Enterprise sales) | SaaS standard |
| Gross margin | >85% | Pure software, no COGS |

### ARR Growth Path

| Timeframe | Milestone | ARR Target | Key Actions |
|-----------|-----------|------------|-------------|
| **Y0 (Now)** | Product readiness | $0 | AGPL migration, Propriety.ai launch, PyPI publish |
| **Y0+6mo** | Early adoption | $30K | 10 Pro customers, GitLab integration viral spread |
| **Y1** | PMF validation | $300K | 50 Pro + 5 Team, first EU enterprise customer |
| **Y1.5** | Pre-EU AI Act | $1M | Urgency-driven demand, compliance reports as primary sell |
| **Y2** | Enterprise engine starts | $3M | First Enterprise customers, hire sales |
| **Y3** | Scale | $10M | Exceed Styra/OPA, prove governance can monetize |
| **Y5** | Category leadership | $30-50M | Multi-product (engine + SaaS + consulting) |

---

## 6. Revenue Stream Decomposition

### Stream 1: SaaS Subscriptions (70% of revenue at scale)

The primary revenue stream. Propriety.ai hosted platform with tiered pricing.

**Economics:**
- Gross margin: >90% (cloud infrastructure costs minimal for validation workloads)
- Expansion: Framework additions, volume growth, tier upgrades
- Retention: Audit log retention creates switching costs (you can't easily migrate compliance history)

### Stream 2: Validation Overage (15% of revenue at scale)

Usage-based pricing for customers exceeding tier limits.

**Economics:**
- Pro overage: $0.10/1K validations (~$100/1M additional validations)
- Team overage: $0.06/1K validations (~$60/1M additional validations)
- Margin: >95% (computational cost per validation is negligible at 560ns)

### Stream 3: Professional Services (10% of revenue at scale)

Enterprise-only. High-touch engagement.

**Services:**
- Custom constitutional design ($10K-50K one-time)
- Compliance gap assessment ($5K-25K per framework)
- Quarterly constitutional review ($2K-5K/quarter)
- On-premise deployment assistance ($15K-30K one-time)
- Red team / penetration testing of governance rules ($10K-20K)

### Stream 4: Certification Program (5% of revenue at scale, long-term)

"ACGS Certified" brand program.

**Economics:**
- Annual certification fee: $1K-5K depending on organization size
- Audit verification service: $2K-10K per audit
- Badge program with public registry
- Creates network effects (more certified = more valuable certification)

---

## 7. Competitive Positioning Matrix

### Where ACGS Wins

| Scenario | Why ACGS Wins | Competitor Weakness |
|----------|---------------|---------------------|
| EU-regulated AI deployment | 9-framework coverage, Article 12/13/14 modules | Guardrails AI: 0 regulatory frameworks |
| High-throughput validation | 560ns P50 (Rust backend) | NeMo Guardrails: ~10ms (LLM-based) |
| CI/CD governance gate | GitLab native integration, 5-line setup | OPA: requires Rego expertise |
| Multi-agent governance | MACI separation of powers | No competitor has constitutional architecture |
| Audit trail requirements | Cryptographic chain verification with constitutional hash | Guardrails AI: basic logging |

### Where ACGS Loses (today)

| Scenario | Why ACGS Loses | Fix Required |
|----------|----------------|--------------|
| Brand awareness | Unknown; competitors have VC-funded marketing | Community building, content marketing |
| Enterprise sales | No sales team, no customer references | First 5 enterprise customers are critical |
| Content-based guardrails | ACGS is rule-based, not LLM-based | Different use case; position as complementary |
| Self-serve onboarding | No hosted free tier (requires local install) | Propriety.ai hosted free tier |

---

## 8. Framework Accuracy Maintenance Strategy

**Panel critique (Round 2):** 9-framework coverage is the primary moat, but regulations change continuously. Delegated acts, implementing acts, and national transpositions require ongoing domain expertise that engineering alone cannot provide.

### Maintenance Model: Hybrid (Core Team + Community + Legal Partners)

| Layer | Responsibility | Cadence | Owner |
|-------|---------------|---------|-------|
| **Core frameworks** (EU AI Act, GDPR, NIST) | Full accuracy guarantee; breaking changes = SaaS notification | Within 30 days of regulatory change | ACGS core team |
| **Secondary frameworks** (SOC 2, HIPAA, ISO 42001) | Best-effort accuracy; community PRs welcome | Within 90 days of regulatory change | Core + community |
| **Tertiary frameworks** (NYC LL 144, ECOA, OECD) | Community-maintained; core team reviews | As contributed | Community + review |

### Accuracy Assurance Mechanisms

1. **Regulatory change feed** -- Subscribe to EUR-Lex (EU), Federal Register (US), NIST CSRC, ISO updates. Automated alerts on AI governance keywords.
2. **Legal advisory board** (Phase 2, post-$1M ARR) -- 2-3 part-time legal advisors specializing in EU AI Act, US federal AI regulation, and data protection. Not full-time hires; retainer model ($2K-5K/month each).
3. **Framework version pinning** -- Each compliance mapping carries a version number and "last verified" date. Customers see: "EU AI Act mapping v2.3, verified 2026-09-15." Stale mappings trigger dashboard warnings.
4. **Community contribution guide** -- "How to add or update a regulatory framework" guide with structured PR template: (a) regulatory source citation, (b) checklist item mapping, (c) auto-population logic, (d) test cases.
5. **Annual framework audit** (Enterprise tier) -- Included in Enterprise pricing. External legal review of framework accuracy for the customer's specific jurisdiction.

### Cost Estimate

| Item | Monthly Cost | When |
|------|-------------|------|
| Regulatory alert subscriptions | $0 (EUR-Lex, Federal Register are free) | Y0 |
| Founder time on framework updates | ~20 hours/month | Y0-Y1 |
| Legal advisory retainers (2 advisors) | $4K-10K/month | Post-$1M ARR |
| Community manager for framework PRs | Part of DevRel hire | Post-$500K ARR |

## 9. Operating Constraints & Funding

**Panel critique (Round 2):** No document addresses the practical constraints of a bootstrapped solo founder.

### Current Constraints

| Constraint | Impact | Mitigation |
|-----------|--------|------------|
| Solo founder (bus factor = 1) | Cannot parallelize; single failure point | P0: recruit first contributor within 90 days |
| Bootstrapped (no external funding) | Limited marketing spend, no sales team, no legal retainers | Revenue-first: every action prioritized by proximity to first dollar |
| No existing customer base | No social proof, no case studies, no logos | Design partner program: 3-5 beta users get free Team tier for 6 months in exchange for case study + logo |
| No legal counsel | AGPL migration, CLA, trademark need legal review | Budget $3K-5K for one-time legal package (AGPL migration + CLA template + trademark filing) |

### Funding Strategy

| Phase | Source | Amount | Trigger |
|-------|--------|--------|---------|
| **Y0** | Self-funded | Minimal (domain, hosting, legal) | -- |
| **Y0-Y1** | Customer revenue | $0 -> $300K ARR target | First Pro customer |
| **Y1** | Design partners | $0 (free tier for case studies) | 3-5 design partners secured |
| **Y1-Y2** | Seed round (optional) | $1-3M | Only if: PMF validated ($300K+ ARR), clear path to $3M ARR, need to accelerate before EU AI Act deadline |
| **Y2+** | Revenue-funded growth | Reinvest revenue | Preferred path if growth supports it |

**Seed round decision criteria:** Only raise if (a) PMF is validated by revenue, (b) the EU AI Act deadline creates a time-limited land grab that revenue alone cannot fund, and (c) the right investor (compliance/governance domain expertise, not generic VC) is available. Bootstrapped is the default.

### First Hire Priority

| Order | Role | Trigger | Cost |
|-------|------|---------|------|
| 1st | **DevRel / Community Engineer** | >$100K ARR or >5K GitHub stars | $80-120K/year |
| 2nd | **Backend Engineer (Rust/Python)** | Feature backlog exceeds founder capacity | $120-160K/year |
| 3rd | **Compliance Domain Expert** | >$500K ARR, framework accuracy demands exceed founder + community | $100-140K/year |
| 4th | **Enterprise Sales** | >3 inbound Enterprise inquiries/month | $100K base + commission |

## 10. Risk Mitigation

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| AWS launches "AI Governance" service | High (2-3 years) | Critical | AGPL license prevents code copying; build brand moat with certification |
| Guardrails AI raises Series A, gains market | High (1 year) | High | Differentiate on compliance (9 frameworks vs 0); performance (560ns vs ~10ms) |
| EU AI Act enforcement delayed | Low | High | Multi-driver demand strategy (insurance, investor DD, customer contracts, SOC 2) |
| AGPL scares enterprise developers | Medium | High | Commercial dual license included in Team/Enterprise; clear FAQ on AGPL scope for embedded use |
| Framework mappings become stale/inaccurate | Medium | Critical | Framework version pinning, legal advisory board, community contribution pipeline |
| Pricing too high for developers | Medium | Medium | Free tier is full engine; Pro at $299 is below most compliance tools |
| Bus factor = 1 | Current state | Critical | **P0: recruit first contributor within 90 days; design partner program for external validation** |
| Bootstrapped constraints limit speed | Current state | High | Revenue-first prioritization; seed round as option if PMF validated |

---

## 11. Implementation Roadmap

### Phase 0: Foundation (Weeks 1-4)

| Action | Priority | Duration | Owner |
|--------|----------|----------|-------|
| AGPL-3.0 license migration + CLA setup | P0 | 1 week | Founder |
| Propriety.ai pricing page live | P0 | 1 week | Founder |
| `pip install acgs` published to PyPI | P0 | 2 weeks | Founder |
| Stripe integration for Pro/Team billing | P0 | 3 weeks | Founder |
| Cloud audit log service (Pro feature core) | P1 | 4 weeks | Founder |
| Compliance report PDF/JSON export | P1 | 2 weeks | Founder |

### Phase 1: Launch (Weeks 5-12)

| Action | Priority | Duration |
|--------|----------|----------|
| GitLab Marketplace submission | P1 | 2 weeks |
| EU AI Act countdown landing page | P1 | 1 week |
| Developer documentation site | P1 | 3 weeks |
| First 10 Pro customers (outbound + content) | P1 | 8 weeks |
| Usage metering + overage billing | P2 | 3 weeks |
| "ACGS Certified" badge program design | P2 | 4 weeks |

### Phase 2: Validate (Weeks 13-26)

| Action | Priority | Duration |
|--------|----------|----------|
| First Team tier customer | P1 | Ongoing |
| First Enterprise conversation | P1 | Ongoing |
| Community Discord/forum launch | P2 | 2 weeks |
| Contributor recruitment (target: 2 core) | P0 | Ongoing |
| Content marketing (blog, case studies) | P2 | Ongoing |
| Conference talks (EU AI Act angle) | P2 | Ongoing |

### Phase 3: Scale (Weeks 27-52)

| Action | Priority | Duration |
|--------|----------|----------|
| First Enterprise customer signed | P1 | Target Q3 |
| $300K ARR milestone | P1 | Target Q4 |
| Seed fundraise consideration | P2 | If PMF validated |
| Hire first sales person | P2 | When Enterprise pipeline exists |
| SOC 2 Type II certification for Propriety.ai | P2 | 3-6 months |

---

## 12. Decision Log

| Decision | Chosen | Rejected | Rationale |
|----------|--------|----------|-----------|
| License | AGPL-3.0-or-later + commercial dual license | Apache-2.0, BSL, SSPL | OSI-compliant + cloud protection; validated by Grafana; embedded-library concern mitigated by dual license |
| Pricing model | Flat tier + usage overage | Pure per-seat, pure usage-based | Flat tier encourages adoption; overage captures heavy users |
| Primary market | Developers (B2D) | Enterprise (B2B), Consumer advocacy (B2C) | Matches open-source distribution; enables bottom-up enterprise penetration |
| Entry wedge | GitLab CI/CD integration | Multi-platform simultaneous | Most mature integration; clear buyer persona; GitLab Marketplace distribution |
| Core product | ACGS library (`acgs`) | enhanced-agent-bus | Simpler product = more antifragile; 80+ subsystems = complexity risk |
| Primary sell | Compliance proof | Governance engine | Avoids OPA/Styra $12M infrastructure trap; compliance proof has direct buyer value |
| Demand strategy | Multi-driver (EU AI Act + insurance + investor DD + SOC 2 + customer contracts) | EU AI Act only | Eliminates single regulatory dependency; some drivers are active today |
| Funding | Bootstrapped-first, seed optional | Raise immediately | Preserves equity; forces revenue-first discipline; seed only if PMF validated |
