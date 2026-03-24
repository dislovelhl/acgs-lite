# ACGS Sales Battlecard

**Last updated:** 2026-03-19
**Audience:** Founder (pre-sales team), design partners, early enterprise conversations

---

## 30-Second Pitch

> "ACGS is HTTPS for AI. Just as SSL/TLS gave the web cryptographic proof that transactions were secure, ACGS gives AI systems cryptographic proof that decisions are constitutionally compliant. Five lines of code. 560 nanoseconds of overhead. Nine regulatory frameworks. The EU AI Act takes full enforcement August 2026 — with fines up to 7% of global revenue. ACGS is how you prove compliance."

---

## Elevator Pitches by Audience

### To a Developer

> "pip install acgs-lite. Five lines of Python. Every AI action validated against your constitutional rules in 560 nanoseconds. Cryptographic audit trail included. You already lint your code — now lint your AI decisions."

### To a CTO / VP Engineering

> "Your AI systems make thousands of decisions per second. Can you prove to an auditor that every one was compliant? ACGS embeds constitutional governance into your pipeline — 560ns overhead, nine regulatory frameworks, tamper-proof audit trail. It's a CI/CD stage, not a consulting engagement."

### To a CISO / DPO

> "EU AI Act enforcement begins August 2026. Fines: 7% of global annual revenue. ACGS provides automated compliance evidence for nine frameworks — EU AI Act, GDPR, NIST AI RMF, ISO 42001, SOC 2, HIPAA, and more. Every validation produces an auditable receipt with a cryptographic chain. Your auditor gets a compliance report, not a promise."

### To a CFO / Risk Officer

> "AI governance is becoming an insurance and liability issue. Insurers are asking about AI governance for cyber policy renewals. Class action lawyers are using 'no governance' as evidence of negligence. ACGS costs $299/month and produces the compliance evidence that reduces your risk premium and legal exposure."

### To an Investor (Due Diligence)

> "We have constitutional governance infrastructure covering nine regulatory frameworks with sub-microsecond latency. The EU AI Act market alone is EUR 3.4B+. We're the only tool that produces auditable compliance proof — not just content safety. Our Rust backend validates at 2.8M operations per second."

---

## Objection Handling

### Price Objections

| Objection | Response |
|-----------|----------|
| "Too expensive" | Compared to what? A compliance consulting engagement is $50K-100K. A single EU AI Act fine starts at EUR 15M. $299/month is a rounding error on your compliance budget. |
| "We don't have budget for AI governance" | You have budget for SOC 2 tools, GDPR tools, or security scanning. This goes in the same line item. Which budget owner handles your compliance? |
| "The open-source version is enough" | For local development, absolutely. When your auditor asks for compliance reports, cloud-synced audit trails, and multi-framework assessment — that's when Pro pays for itself. |

### Technical Objections

| Objection | Response |
|-----------|----------|
| "We can build this ourselves" | You can build a governance engine. But 9 regulatory framework mappings, 125 compliance checklist items, MACI separation of powers, and a cryptographic audit chain took 118 optimization experiments. Your compliance deadline is August 2026. |
| "We already use OPA / Rego" | OPA is excellent for general policy. ACGS adds AI-specific regulatory compliance mapping on top. They're complementary — ACGS can even export to OPA policy format. You keep OPA for infra, add ACGS for AI governance. |
| "We already use Guardrails AI" | Guardrails AI focuses on LLM output quality (toxicity, PII, hallucination). ACGS focuses on constitutional compliance (regulatory proof, audit trail, separation of powers). Different layers. Many teams use both. |
| "Rule-based matching isn't sophisticated enough" | For content safety, you want LLM-based tools. For regulatory compliance, you want deterministic, auditable rules. An auditor needs to verify that a rule was applied correctly — not that a model's probabilistic output was "probably compliant." Determinism is the feature. |
| "560ns is impressive but we don't need that performance" | The performance means governance adds zero overhead to your pipeline. You'll never need to turn it off for performance reasons. Governance that's too slow gets disabled — ours never will be. |

### Trust / Risk Objections

| Objection | Response |
|-----------|----------|
| "Small company, no track record" | We're open source — you can audit every line. The constitutional hash is cryptographically verifiable. We offer on-premise deployment so you never depend on our infrastructure. |
| "AGPL license concerns" | For internal use (pipeline, CI/CD, on-prem), AGPL has zero obligations. For SaaS embedding, our Team and Enterprise tiers include a commercial license. See our AGPL FAQ. |
| "What if you disappear?" | The code is AGPL open source — it can't disappear. Your audit logs are yours. On-premise deployment means zero dependency on our SaaS. |
| "One-person company?" | The codebase has 3,820 tests, 70%+ coverage, and is built on production-grade infrastructure (FastAPI, Rust/PyO3, Redis, structlog). We're actively recruiting core contributors and offer a design partner program. |

### Competitive Objections

| Objection | Response |
|-----------|----------|
| "AWS/Google/Azure will build this" | They might — in 2-3 years. Your EU AI Act deadline is August 2026. We're available today with 9 frameworks. When a cloud provider launches, we'll be the established standard they compete against. |
| "We'll wait for a bigger vendor" | Every month without governance is a month of unaudited AI decisions. When the auditor arrives, you need history — not just a tool you installed last week. Start now, build the audit trail. |

---

## Competitive Positioning

### vs Guardrails AI

| Dimension | ACGS | Guardrails AI |
|-----------|------|---------------|
| Focus | Regulatory compliance proof | LLM output quality |
| Output | Compliance report, audit trail | Validated/corrected LLM output |
| Latency | 560ns | 5-50ms |
| Regulatory mapping | 9 frameworks | None (has PII/toxicity validators) |
| Separation of powers | MACI (Proposer/Validator/Executor) | None |
| Positioning | Complementary — different layers |

**Key line:** "Guardrails AI makes sure your AI says the right thing. ACGS proves to your auditor that your AI is governed."

### vs OPA / Styra

| Dimension | ACGS | OPA/Styra |
|-----------|------|-----------|
| Focus | AI governance | General policy |
| Policy language | YAML constitution | Rego |
| Regulatory mapping | 9 AI-specific frameworks | None |
| Audit trail | Cryptographic chain | Decision logs |
| Positioning | ACGS for AI governance, OPA for infrastructure policy |

**Key line:** "OPA governs your infrastructure. ACGS governs your AI. You need both."

---

## Qualification Criteria (MEDDPICC)

| Criterion | Strong Signal | Weak Signal |
|-----------|--------------|-------------|
| **Metrics** | "We need to prove compliance to auditors" | "We're exploring governance options" |
| **Economic Buyer** | CISO, CTO, or VP Eng identified | "I'll check with my manager" |
| **Decision Criteria** | Regulatory deadline, audit finding, customer requirement | "Nice to have" |
| **Decision Process** | Procurement timeline under 30 days | "We'll evaluate next quarter" |
| **Paper Process** | Standard SaaS procurement | "We need board approval" |
| **Implicate Pain** | SOC 2 audit finding, EU AI Act prep, insurance requirement | General interest in AI ethics |
| **Champion** | Platform engineer already using free tier | Someone who attended a webinar |
| **Competition** | "We have nothing" or "We built something basic" | "We're already using [competitor]" |

---

## Design Partner Pitch

> "We're launching ACGS commercially and looking for 3-5 design partners to shape the product. As a design partner, you get free Team tier ($999/month value) for 6 months, direct access to the founder, and priority feature input. In return, we ask for a case study, your logo on our site, and quarterly feedback. Interested?"

**Ideal design partner:**
- 20-100 person EU-based AI/ML company
- Currently in SOC 2 audit prep or starting EU AI Act compliance
- Using GitLab or GitHub CI/CD
- Has a platform engineer who can champion internally

---

## Key Numbers

| Metric | Value |
|--------|-------|
| Validation latency (P50) | 560ns |
| Validation latency (P99) | 3.9us |
| Throughput | 2.8M validations/sec |
| Regulatory frameworks | 9 |
| Compliance checklist items | 125 (72 auto-populated) |
| Test suite | 3,820 tests |
| Benchmark scenarios | 847 |
| EU AI Act enforcement | August 2, 2026 |
| EU AI Act max fine | 7% global annual revenue |
| Pro price | $299/month |
| Team price | $999/month |
| Enterprise floor | $5,000/month |
