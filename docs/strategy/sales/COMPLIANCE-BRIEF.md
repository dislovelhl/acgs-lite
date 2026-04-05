# ACGS Compliance Brief

**Audience:** CISOs, DPOs, Compliance Officers, Auditors
**Date:** 2026-03-19
**Version:** 1.0

---

## Executive Summary

ACGS (Advanced Constitutional Governance System) provides automated compliance evidence for AI systems across nine regulatory frameworks. Every AI decision produces a cryptographically verified audit record linked to specific regulatory requirements. This brief outlines ACGS's coverage, evidence types, and audit readiness capabilities.

---

## 1. Regulatory Framework Coverage

### Coverage Matrix

| Framework | Articles/Sections | Auto-Populated Items | Manual Items | Total Items |
|-----------|-------------------|---------------------|-------------|------------|
| **EU AI Act** | Art. 12, 13, 14 | 5 | 4 | 9 |
| **NIST AI RMF** | GOVERN, MAP, MEASURE, MANAGE | 7 | 9 | 16 |
| **ISO/IEC 42001** | AIMS requirements | 9 | 9 | 18 |
| **GDPR** | Art. 22, 35, 40 | 10 | 2 | 12 |
| **SOC 2 + AI** | Trust Service Criteria | 10 | 6 | 16 |
| **HIPAA + AI** | PHI protection | 9 | 6 | 15 |
| **ECOA/FCRA** | Fair lending | 6 | 6 | 12 |
| **NYC LL 144** | Employment automation | 6 | 6 | 12 |
| **OECD AI Principles** | 5 principles | 10 | 5 | 15 |
| **Total** | | **72** | **53** | **125** |

**Auto-populated:** ACGS generates evidence automatically from runtime validation data.
**Manual:** Requires organizational input (policies, procedures, training records).

### EU AI Act Specific Coverage

| Article | Requirement | ACGS Capability | Tier |
|---------|-------------|-----------------|------|
| **Article 12** | Record-keeping for high-risk AI | `Article12Logger` — structured audit records with timestamps, inputs, outputs, decision rationale | Pro |
| **Article 13** | Transparency and information to deployers | `TransparencyDisclosure` — automated capability and limitation statements | Team |
| **Article 14** | Human oversight measures | `HumanOversightGateway` — configurable human-in-the-loop gates for high-risk decisions | Team |
| **Article 6 + Annex III** | Risk classification | `RiskClassifier` — 6-level risk assessment with regulatory alignment | Pro |
| **Annex IV** | Technical documentation | `ComplianceChecklist` — auto-populated documentation template | Pro |

### EU AI Act Key Dates

| Date | Milestone | ACGS Relevance |
|------|-----------|----------------|
| **2025-08-02** | GPAI model obligations | Affects foundation model providers |
| **2026-08-02** | **High-risk AI provisions** | **Primary compliance trigger** |
| **2027-08-02** | Full enforcement (Annex I) | Remaining provisions |

### Penalties

| Violation Type | Maximum Fine |
|----------------|-------------|
| Prohibited AI practices | 7% global annual revenue or EUR 35M |
| High-risk AI non-compliance | 3% global annual revenue or EUR 15M |
| Incorrect information to authorities | 1.5% global annual revenue or EUR 7.5M |

---

## 2. Evidence Types Produced

### Audit Trail

Every ACGS validation produces a structured audit record:

```json
{
  "timestamp": "2026-03-19T14:32:07.123Z",
  "action": "process mortgage application",
  "decision": "ALLOW",
  "rules_evaluated": 12,
  "rules_triggered": 0,
  "latency_ns": 487,
  "constitutional_hash": "608508a9bd224290",
  "chain_hash": "a7f3...9c21",
  "previous_hash": "b2e1...4f87",
  "agent_role": "EXECUTOR",
  "validated_by": "VALIDATOR_003",
  "frameworks": ["EU_AI_ACT", "GDPR", "ECOA_FCRA"]
}
```

### Evidence Properties

| Property | Description | Regulatory Value |
|----------|-------------|-----------------|
| **Tamper evidence** | Each record includes a chain hash linking to the previous record. Any modification breaks the chain | Art. 12 record integrity |
| **Constitutional hash** | Immutable hash of the governance rules at validation time. Proves which rules were active | Art. 12 rule provenance |
| **MACI role attribution** | Records which agent proposed, validated, and executed each decision | Separation of duties evidence |
| **Latency tracking** | Sub-microsecond timestamps for each validation step | Performance SLA evidence |
| **Framework mapping** | Each validation is tagged with applicable regulatory frameworks | Cross-framework compliance |

### Compliance Reports

ACGS generates structured compliance reports (PDF and JSON):

- **Framework gap analysis:** Items covered vs items requiring manual evidence
- **Compliance score:** Percentage of auto-populated items per framework
- **Cross-framework alignment:** Items satisfied by a single control across multiple frameworks
- **Trend analysis:** Compliance posture over time
- **Violation summary:** Rules triggered, severity distribution, remediation status

---

## 3. MACI Separation of Powers

ACGS enforces separation of duties through the MACI (Multi-Agent Constitutional Integrity) model:

| Role | Responsibility | Enforcement |
|------|---------------|-------------|
| **Proposer** | Submits actions for governance review | Cannot validate own proposals |
| **Validator** | Independently evaluates proposals against constitution | Cannot propose or execute |
| **Executor** | Acts on validated decisions | Cannot propose or validate |
| **Observer** | Read-only access to audit trail | Cannot propose, validate, or execute |

**Regulatory alignment:**
- SOC 2: Segregation of duties control
- EU AI Act Art. 14: Human oversight separation
- NIST AI RMF: GOVERN function independence
- ISO 42001: Role-based access control

---

## 4. Audit Readiness Checklist

### What ACGS Provides to Your Auditor

- [ ] Complete audit trail with cryptographic chain verification
- [ ] Constitutional hash proving rule immutability at validation time
- [ ] MACI role assignment and enforcement logs
- [ ] Compliance gap report per framework
- [ ] Multi-framework cross-reference (one control satisfying multiple frameworks)
- [ ] Validation latency and throughput metrics
- [ ] Rule versioning history with change tracking
- [ ] Violation reports with severity classification and remediation status

### What You Provide (Manual)

- [ ] AI system inventory and risk classification
- [ ] Organizational AI governance policy document
- [ ] Training records for staff interacting with AI systems
- [ ] Data processing impact assessments (DPIAs)
- [ ] Incident response procedures for AI-related incidents
- [ ] Third-party AI vendor assessments
- [ ] Human oversight procedures and escalation protocols

---

## 5. Deployment Options

| Option | Description | Best For |
|--------|-------------|----------|
| **SaaS (Propriety.ai)** | Cloud-hosted, managed by ACGS team | Most organizations; fastest deployment |
| **On-premise** | Self-hosted within your infrastructure | Regulated industries (banking, healthcare, government) |
| **VPC deployment** | Hosted in your cloud VPC, managed by ACGS | Organizations requiring data residency |
| **Hybrid** | Validation on-premise, reporting via SaaS | Organizations wanting local validation with cloud analytics |

### Data Residency

- **SaaS:** EU-hosted (primary), US-hosted (optional)
- **On-premise:** Data never leaves your infrastructure
- **Audit logs:** Customer-owned. Exportable in JSON, CSV, or PDF at any time. ACGS retains no audit data after account termination.

---

## 6. Security Posture

| Aspect | Detail |
|--------|--------|
| **License** | AGPL-3.0 (source code auditable) + commercial license for SaaS embedding |
| **Dependencies** | Minimal: Python stdlib, Pydantic, structlog. Optional: Rust/PyO3 for performance |
| **Cryptography** | SHA-256 chain hashing for audit integrity; HMAC-SHA256 for license validation |
| **Authentication** | JWT, SAML, OIDC (Team+), API keys |
| **Data handling** | Validation inputs are not stored by default. Audit records store decisions, not raw data |
| **Test coverage** | 3,820 automated tests; 70%+ code coverage |
| **Code audit** | Open source — full code review available |

---

## 7. Pricing (Compliance-Relevant Tiers)

| Feature | Pro ($299/mo) | Team ($999/mo) | Enterprise (Custom) |
|---------|---------------|-----------------|---------------------|
| Compliance frameworks | 3 (choose) | All 9 | All 9 + custom |
| EU AI Act Art. 12 | Yes | Yes | Yes |
| EU AI Act Art. 13 | -- | Yes | Yes |
| EU AI Act Art. 14 | -- | Yes | Yes |
| Compliance reports (PDF/JSON) | Yes | Yes | Yes |
| Cloud audit retention | 30 days | 1 year | Custom |
| SSO/SAML | -- | Yes | Yes |
| On-premise deployment | -- | -- | Yes |
| Dedicated compliance engineer | -- | -- | Yes |
| Quarterly constitutional review | -- | -- | Yes |
| Commercial license (no AGPL) | -- | Included | Included |

---

## Contact

- Compliance inquiries: compliance@propriety.ai
- Commercial licensing: license@propriety.ai
- Security questions: security@propriety.ai
- General: governance@propriety.ai
