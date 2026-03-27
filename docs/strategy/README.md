# ACGS Strategy Documents

**Generated:** 2026-03-19
**Last updated:** 2026-03-27

Current naming reference: the public package is `acgs`, the compatibility namespace is
`acgs_lite`, and `ACGS-2` is an internal historical platform label. See
[../brand-architecture.md](../brand-architecture.md).

---

## Strategy & Analysis

| # | Document | Description |
|---|----------|-------------|
| 01 | [Business Panel Analysis](01-business-panel-analysis.md) | Multi-expert analysis (9 simulated experts: Christensen, Porter, Taleb, Kim/Mauborgne, Drucker, Meadows, Godin, Collins, Doumont). Consensus points, disagreements, priority recommendations. |
| 02 | [Market Research Evidence](02-market-research-evidence.md) | Competitive intelligence (Guardrails AI, NeMo, OPA/Styra, Snyk, Checkmarx), OSS monetization precedents (HashiCorp, Elastic, Redis, Grafana, PostHog, Supabase), market sizing ($200M-$15.8B), PLG playbook, product surface inventory. |
| 03 | [Economic Engine Design](03-economic-engine-design.md) | Monetization model: Apache-2.0 license (updated from AGPL), 4-tier pricing, flywheel design, OPA/Styra differentiation, ARR growth path, revenue streams, risk mitigation, framework maintenance, funding strategy. |
| 04 | [Competitive Landscape](04-competitive-landscape.md) | Head-to-head comparison matrix (ACGS vs Guardrails AI vs NeMo vs OPA vs LlamaGuard), potential new entrants, partner opportunities, moat assessment, win/loss scenarios. |
| 05 | [GTM Playbook](05-gtm-playbook.md) | Go-to-market: GitLab wedge, distribution channels, conversion funnel, Day Zero pipeline, design partner program, community building, enterprise sales motion, 90-day launch plan. |

## Legal

License changed to Apache-2.0 (2026-03-27). Previous AGPL strategy docs archived.

## Sales Enablement

| Document | Description |
|----------|-------------|
| [Battlecard](sales/BATTLECARD.md) | 30-second pitches by audience, objection handling (price/technical/trust/competitive), MEDDPICC qualification, design partner pitch, key numbers. |
| [Compliance Brief](sales/COMPLIANCE-BRIEF.md) | CISO/auditor-facing: 9-framework coverage matrix, evidence types, MACI separation, audit readiness checklist, deployment options, security posture. |
| [Budget Playbook](sales/BUDGET-PLAYBOOK.md) | How to get ACGS purchased when "AI governance" is not a budget line item. Budget attachment map by trigger event, price anchoring, conversation templates, deal acceleration. |
| [Design Partner Program](sales/DESIGN-PARTNER-PROGRAM.md) | Terms, ideal partner profile, prospecting sources, outreach cadence, onboarding checklist, exit criteria, success metrics. |
| [Pitch Deck Outline](sales/PITCH-DECK.md) | 10-slide founder deck narrative: problem, category gap, product, competition, GTM, and closing thesis. |

## Messaging

| Document | Description |
|----------|-------------|
| [Core Messaging](messaging/CORE-MESSAGING.md) | Canonical positioning, one-liners, category framing, founder narrative, language to use and avoid. |
| [Audience Narratives](messaging/AUDIENCE-NARRATIVES.md) | Segmented messaging for 5 audiences: developers, CTOs, CISOs, investors, design partners. Tone, content angles, channels, what NOT to say. |
| [Landing Page Copy](messaging/LANDING-PAGE-COPY.md) | Full copy for propriety.ai homepage: hero, problem, solution, metrics, frameworks, how-it-works, integrations, EU AI Act countdown, pricing preview, CTAs. |

## Launch

| Document | Description |
|----------|-------------|
| [Launch Pack](../launch/LAUNCH-PACK.md) | Founder-style launch copy in English and Chinese for LinkedIn, X, Hacker News, and short-form posts. |

---

## Key Findings Summary

1. **Market timing is optimal** -- EU AI Act August 2026 enforcement creates a hard regulatory deadline
2. **"HTTPS for AI" is the positioning** -- concise, accurate, memorable
3. **License: AGPL-3.0 + commercial dual license** (decided 2026-03-19) -- with embedded-library impact analysis
4. **Sell compliance proof, not governance engine** -- avoids the OPA/Styra $12M monetization trap
5. **GitLab CI/CD is the entry wedge** -- code-level governance first, runtime governance follows
6. **$299/$999/$5K+ pricing** -- with budget creation playbook for new category
7. **Multi-driver demand** -- EU AI Act + insurance + investor DD + customer contracts + SOC 2
8. **Bus factor = 1 is the #1 operational risk** -- recruit core contributors immediately
9. **Framework accuracy maintenance** -- hybrid model (core team + community + legal advisory)
10. **Bootstrapped-first** -- seed round optional, only if PMF validated

## Revision History

| Date | Change | Trigger |
|------|--------|---------|
| 2026-03-19 | Initial creation (docs 01-05) | Business panel analysis |
| 2026-03-19 | Round 2 revisions (docs 03, 04, 05) | Panel adversarial review: 6 contradictions, 5 omissions fixed |
| 2026-03-19 | Operational documents (legal, sales, messaging) | Execution readiness |
| 2026-03-27 | Messaging refresh and launch collateral | Core positioning, landing page refresh, pitch deck outline, bilingual launch pack |

### Round 2 Fixes Applied

- **Doc 03:** AGPL embedded-library impact analysis; budget creation playbook; multi-driver demand strategy; framework maintenance plan; operating constraints & funding section; updated decision log
- **Doc 04:** Corrected Guardrails AI capability assessment (not "0 frameworks" but "no compliance reporting")
- **Doc 05:** Added Day Zero pipeline and design partner program; clarified GitLab wedge as code-level governance (distinct from runtime); revised 90-day plan with pre-launch warm-up

## Confidence Levels

| Finding | Confidence |
|---------|------------|
| Market size | Medium-High (multi-source, but wide range in emerging market) |
| EU AI Act as trigger | High (legislative timeline is fixed) |
| OPA/Styra cautionary tale | High (direct comparable) |
| AGPL + dual license for embedded library | High (MongoDB, Grafana precedent; embedded-library analysis completed) |
| PLG playbook | Medium-High (proven pattern, newer category) |
| Pricing | Medium (needs A/B testing; budget creation playbook added) |
| Multi-driver demand | Medium (insurance/investor DD drivers are real but unquantified) |

## Document Dependency Map

```
01-Business Panel ──► 02-Market Research ──► 03-Economic Engine
                                                    │
                                          ┌─────────┼──────────┐
                                          ▼         ▼          ▼
                                    04-Competitive  05-GTM   legal/AGPL-*
                                          │         │
                                          ▼         ▼
                                    sales/         messaging/
                                    BATTLECARD     AUDIENCE-NARRATIVES
                                    COMPLIANCE     LANDING-PAGE-COPY
                                    BUDGET
                                    DESIGN-PARTNER
```

## Next Steps

After reviewing these documents:
- Use `/sc:design` for architectural changes (e.g., AGPL migration, cloud audit service)
- Use `/sc:workflow` for implementation planning
- Use `/sc:implement` for feature development
