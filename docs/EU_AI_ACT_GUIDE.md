# EU AI Act Compliance Guide for Engineering Teams

> Your legal counsel sent you a letter. You have until **August 2, 2026** to comply.
> This guide shows you what to build, what ACGS-Lite handles for you, and what you
> still need to do yourself.

**Last updated**: 2026-03-21
**Regulation**: [Regulation (EU) 2024/1689](https://eur-lex.europa.eu/eli/reg/2024/1689/oj) (EU AI Act)
**Enforcement date**: August 2, 2026 (high-risk provisions)
**Maximum penalty**: 7% of global annual revenue or EUR 35 million, whichever is higher

---

## What the EU AI Act Requires (The 60-Second Version)

The EU AI Act is the world's first comprehensive AI regulation. It classifies every AI system
by risk level and imposes obligations proportional to that risk. If your system makes or
influences decisions about people -- hiring, lending, healthcare, education -- you are almost
certainly building a **high-risk** system. High-risk systems must satisfy nine technical
requirements (Articles 9-16 plus Article 72) before they can be deployed in the EU.

This is not a "check the box and forget it" regulation. It requires continuous risk management,
tamper-evident logging, human oversight mechanisms, and transparency disclosures that you
maintain for the lifetime of the system.

The good news: most of the technical requirements map to engineering practices you should
already be doing. The bad news: "should be doing" and "are doing with auditable evidence" are
different things. That gap is what this guide helps you close.

---

## Risk Classification

The EU AI Act defines four risk tiers. Your obligations depend entirely on which tier your
system falls into.

| Risk Level | What It Means | Examples | Your Obligations |
|---|---|---|---|
| **Unacceptable** | Prohibited. Cannot be deployed in the EU. | Social scoring by governments, subliminal manipulation, real-time biometric ID for law enforcement | Shut it down. |
| **High-Risk** | Regulated. Full compliance required by Aug 2026. | Hiring tools, credit scoring, healthcare diagnostics, education assessment, critical infrastructure | Articles 9-16 + conformity assessment |
| **Limited Risk** | Transparency obligations only. | Chatbots, content generators, emotion recognition | Disclose that users are interacting with AI |
| **Minimal Risk** | No mandatory obligations. | Spam filters, search ranking, game AI | Voluntary codes of conduct encouraged |

You can classify your system programmatically:

```python
from acgs_lite.eu_ai_act import RiskClassifier, SystemDescription

classifier = RiskClassifier()
result = classifier.classify(SystemDescription(
    system_id="candidate-screener-v2",
    purpose="Automated first-pass screening of job applications",
    domain="employment",
    autonomy_level=3,
    human_oversight=True,
    employment=True,
))

print(result.level)          # "high_risk"
print(result.is_high_risk)   # True
print(result.obligations)    # ["Article 9 -- Risk management...", ...]
print(result.high_risk_deadline)  # "2026-08-02"
```

If `result.is_prohibited` returns `True`, stop here. You cannot deploy that system in the EU.

---

## The 9 Technical Requirements (and What ACGS-Lite Covers)

High-risk systems must satisfy nine article-level requirements. Here is the honest breakdown of
what ACGS-Lite automates versus what your team still needs to build.

| # | Article | Requirement | ACGS-Lite | Status |
|---|---------|-------------|-----------|--------|
| 1 | **Article 9** | Risk management system | `RiskClassifier` | **Partial** -- classifies risk and maps obligations; you write the risk management plan |
| 2 | **Article 10** | Data governance | -- | **Manual** -- training data quality, bias testing, lineage documentation |
| 3 | **Article 11** | Technical documentation (Annex IV) | -- | **Manual** -- system description, design choices, validation results |
| 4 | **Article 12** | Record-keeping | `Article12Logger` | **Automated** -- tamper-evident JSONL logging with SHA-256 chaining |
| 5 | **Article 13** | Transparency to deployers | `TransparencyDisclosure` | **Automated** -- generates Article 13 compliant system cards |
| 6 | **Article 14** | Human oversight | `HumanOversightGateway` | **Automated** -- configurable HITL approval gates with audit trail |
| 7 | **Article 15** | Accuracy, robustness, cybersecurity | -- | **Manual** -- accuracy benchmarks, adversarial testing, security hardening |
| 8 | **Article 16** | Provider obligations (CE marking, EU database registration) | -- | **Manual** -- regulatory filing, EU representative appointment |
| 9 | **Article 72** | Conformity assessment | `ComplianceChecklist` | **Partial** -- generates assessment documentation; self-assessment is still your responsibility |

**Bottom line**: ACGS-Lite automates 5 of 9 items (Articles 9, 12, 13, 14, 72). Articles 10,
11, 15, and 16 require work that no library can do for you -- they depend on your specific
data, model, and organizational processes.

---

## Step-by-Step Implementation

### Step 1: Install and Configure

```bash
pip install acgs-lite
```

Set your license key (EU AI Act features require PRO tier or above):

```python
import acgs_lite
acgs_lite.set_license("ACGS-PRO-...")  # Get yours at acgs.dev
```

Verify your license covers the features you need:

```python
from acgs_lite.eu_ai_act import check_license

info = check_license()
print(info["tier"])               # "PRO"
print(info["pro_features"])       # True
print(info["available_classes"])  # ["Article12Logger", "RiskClassifier", "ComplianceChecklist"]
```

### Step 2: Classify Your System

Before writing any compliance code, determine your risk level. This determines which articles
apply to you.

```python
from acgs_lite.eu_ai_act import RiskClassifier, SystemDescription

classifier = RiskClassifier()
result = classifier.classify(SystemDescription(
    system_id="loan-underwriter-v3",
    purpose="Automated credit risk assessment for consumer loans",
    domain="credit_scoring",
    autonomy_level=4,
    human_oversight=True,
))

if result.is_prohibited:
    raise RuntimeError(f"BLOCKED: {result.rationale}")

if result.is_high_risk:
    print(f"High-risk system. Deadline: {result.high_risk_deadline}")
    for obligation in result.obligations:
        print(f"  - {obligation}")
```

### Step 3: Add Article 12 Record-Keeping

Article 12 requires automatic, tamper-evident logging of every decision your AI system makes.
Logs must be retained for at least 10 years.

```python
from acgs_lite.eu_ai_act import Article12Logger

logger = Article12Logger(
    system_id="loan-underwriter-v3",
    risk_level="high_risk",
    tenant_id="acme-corp",
)

# Wrap any LLM call -- logging is automatic
response = logger.log_call(
    operation="assess_credit_risk",
    call=lambda: llm.complete(prompt),
    input_text=prompt,
    human_oversight_applied=False,
    metadata={"applicant_segment": "consumer", "loan_type": "personal"},
)

# Verify chain integrity (detect tampering)
assert logger.verify_chain(), "Audit trail integrity compromised"

# Export to append-only JSONL (Article 12 compliant format)
logger.export_jsonl("audit/loan_underwriter_v3.jsonl")
```

Each record includes a cryptographic chain link (`prev_record_hash`), making any retroactive
modification detectable. Inputs and outputs are stored as SHA-256 hashes, not raw text, so the
audit trail does not become a privacy liability.

### Step 4: Wire Up Human Oversight (Article 14)

Article 14 requires that humans can monitor, intervene, and override your AI system. The
`HumanOversightGateway` enforces this by routing high-impact decisions through a review queue.

```python
from acgs_lite.eu_ai_act import HumanOversightGateway

gateway = HumanOversightGateway(
    system_id="loan-underwriter-v3",
    require_oversight_above_score=0.8,
)

# AI produces a decision
decision = gateway.submit(
    operation="deny_loan",
    ai_output="Denied: debt-to-income ratio exceeds threshold",
    impact_score=0.95,  # High impact -- triggers human review
    context={"application_id": "APP-2026-1234"},
)

if decision.requires_human_review:
    # Route to your existing review queue / notification system
    send_to_review_queue(decision)
    # Later, when the reviewer acts:
    decision = gateway.approve(
        decision.decision_id,
        reviewer_id="senior-underwriter-7",
    )

print(decision.outcome)  # "approved" or "rejected"
```

Decisions below the threshold score are auto-approved with an `auto_approved` outcome, so your
pipeline does not bottleneck on low-risk decisions.

### Step 5: Generate Transparency Disclosure (Article 13)

Article 13 requires clear documentation of your system's purpose, capabilities, limitations,
and oversight measures. This disclosure goes to deployers (your customers), not end users.

```python
from acgs_lite.eu_ai_act import TransparencyDisclosure

disclosure = TransparencyDisclosure(
    system_id="loan-underwriter-v3",
    system_name="Acme Consumer Loan Underwriter",
    provider="Acme Financial Technologies Ltd",
    intended_purpose="Automated first-pass credit risk assessment for consumer loans under EUR 50,000",
    capabilities=[
        "Credit risk scoring based on financial history",
        "Debt-to-income ratio calculation",
        "Regulatory flag detection (sanctions, PEP status)",
    ],
    limitations=[
        "Does not assess non-standard income sources (freelance, crypto)",
        "Trained on EU consumer data only; accuracy outside EU not validated",
        "Cannot process applications in languages other than English, German, French",
    ],
    human_oversight_measures=[
        "All denials reviewed by a licensed underwriter before communication to applicant",
        "Monthly bias audit by compliance team",
        "Applicants can request full human review via support portal",
    ],
    contact_email="ai-compliance@acme-fintech.eu",
    known_biases=["Under-representation of self-employed applicants in training data"],
    performance_metrics={"accuracy": 0.94, "false_positive_rate": 0.03, "AUC": 0.97},
)

# Validate all required fields are present
missing = disclosure.validate()
if missing:
    raise ValueError(f"Article 13 disclosure incomplete: {missing}")

# Generate system card for Annex IV documentation
system_card = disclosure.to_system_card()
```

### Step 6: Track Compliance with the Checklist

The `ComplianceChecklist` tracks your progress across all nine requirements. Use it as a CI/CD
gate so incomplete compliance blocks deployment.

```python
from acgs_lite.eu_ai_act import ComplianceChecklist

checklist = ComplianceChecklist(system_id="loan-underwriter-v3")

# Auto-populate the 5 items that ACGS-Lite handles
checklist.auto_populate_acgs_lite()

print(checklist.compliance_score)  # 0.5556 (5 of 9 items)
print(checklist.blocking_gaps)     # Shows what you still need to do

# Mark remaining items as you complete them
checklist.mark_complete(
    "Article 10",
    evidence="Bias testing report v2.1 at docs/bias-audit-2026-q1.pdf",
)
checklist.mark_complete(
    "Article 11",
    evidence="Annex IV technical documentation at docs/annex-iv/loan-underwriter-v3.md",
)
checklist.mark_complete(
    "Article 15",
    evidence="Adversarial robustness report at docs/security/adversarial-testing-v3.pdf",
)
checklist.mark_complete(
    "Article 16",
    evidence="EU database registration ID: EU-AI-DB-2026-00412",
)

# Check the gate
if checklist.is_gate_clear:
    print("All blocking items resolved. Ready for conformity assessment.")
else:
    print(f"BLOCKED: {checklist.blocking_gaps}")

# Generate report for your conformity assessment file
report = checklist.generate_report()
```

### Step 7: Add to CI/CD Pipeline

Make compliance a build gate, not a quarterly review. Here is a minimal CI check:

```python
# ci/compliance_gate.py
import json
import sys

from acgs_lite.eu_ai_act import ComplianceChecklist

checklist = ComplianceChecklist(system_id="loan-underwriter-v3")
checklist.auto_populate_acgs_lite()

# Load manual evidence from your evidence file
with open("compliance/evidence.json") as f:
    evidence = json.load(f)

for article_ref, details in evidence.items():
    checklist.mark_complete(article_ref, evidence=details["evidence"])

report = checklist.generate_report()

if not report["gate_clear"]:
    print("COMPLIANCE GATE FAILED", file=sys.stderr)
    for gap in report["blocking_gaps"]:
        print(f"  MISSING: {gap}", file=sys.stderr)
    sys.exit(1)

print(f"Compliance score: {report['compliance_score']:.0%}")
print("Compliance gate passed.")
```

Add it to your pipeline:

```yaml
# .github/workflows/compliance.yml
name: EU AI Act Compliance Gate
on: [push, pull_request]

jobs:
  compliance:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install acgs-lite
      - run: python ci/compliance_gate.py
```

### Step 8: Multi-Framework Assessment

If you operate across jurisdictions, run a single assessment that covers all applicable
frameworks simultaneously. ACGS-Lite evaluates against GDPR, NIST AI RMF, ISO 42001, SOC 2,
HIPAA, and five other frameworks.

```python
from acgs_lite.compliance import MultiFrameworkAssessor

assessor = MultiFrameworkAssessor()
report = assessor.assess({
    "system_id": "loan-underwriter-v3",
    "jurisdiction": "european_union",
    "domain": "finance",
})

print(f"Overall score: {report.overall_score:.0%}")
print(f"Frameworks assessed: {report.frameworks_assessed}")
print(f"ACGS-Lite coverage: {report.acgs_lite_total_coverage:.0%}")

# Cross-framework gaps (items missing across multiple regulations)
for gap in report.cross_framework_gaps:
    print(f"  CROSS-FRAMEWORK GAP: {gap}")

# Per-framework detail
for fw_id, assessment in report.by_framework.items():
    print(f"\n{assessment.framework_name}: {assessment.compliance_score:.0%}")
    for gap in assessment.gaps[:3]:
        print(f"  - {gap}")
```

---

## Timeline: What Needs to Happen by When

| Date | Milestone | What to Do |
|------|-----------|------------|
| **Now** | Risk classification | Run `RiskClassifier` on every AI system you deploy in the EU. Know your risk level. |
| **Now** | Inventory | List every AI system your company operates. Yes, that internal chatbot counts. |
| **Q2 2026** | Article 12 logging | Attach `Article12Logger` to every high-risk system. Start accumulating audit trail. |
| **Q2 2026** | Article 13 disclosures | Generate `TransparencyDisclosure` for each system. Have legal review it. |
| **Q2 2026** | Article 14 human oversight | Wire `HumanOversightGateway` into decision pipelines. Test that reviewers can actually intervene. |
| **Q3 2026** | Articles 10, 11, 15 (manual) | Complete data governance documentation, Annex IV technical docs, and accuracy/robustness testing. |
| **Q3 2026** | Article 16 | Register high-risk systems in the EU database. Appoint EU representative if you are outside the EU. |
| **July 2026** | Conformity assessment | Run `ComplianceChecklist`. All blocking items must be green. Have legal sign off. |
| **August 2, 2026** | **Enforcement begins** | High-risk provisions fully enforceable. Fines up to 7% of global annual revenue. |

> **February 2, 2025** has already passed -- prohibitions on unacceptable-risk systems
> (Article 5) are already in force. If you have a social scoring or subliminal manipulation
> system, you are already non-compliant.

---

## What ACGS-Lite Covers vs. What You Still Need

### ACGS-Lite handles these automatically

| Capability | Article | What It Does |
|---|---|---|
| `RiskClassifier` | Art. 9 | Classifies your system's risk tier and lists applicable obligations |
| `Article12Logger` | Art. 12 | Tamper-evident, append-only audit logging with cryptographic chaining |
| `TransparencyDisclosure` | Art. 13 | Generates system cards with capabilities, limitations, oversight measures |
| `HumanOversightGateway` | Art. 14 | Routes high-impact decisions to human reviewers with full audit trail |
| `ComplianceChecklist` | Art. 72 | Tracks compliance across all nine requirements, generates assessment docs |

### You still need to do this yourself

| Requirement | Article | Why a Library Cannot Do It |
|---|---|---|
| **Data governance** | Art. 10 | Requires examining your specific training data for bias, completeness, and representativeness. This is dataset-specific work. |
| **Technical documentation** | Art. 11 | Annex IV requires documenting your system's architecture, design choices, training methodology, and validation results. Only you know these. |
| **Accuracy and robustness testing** | Art. 15 | You must benchmark your specific model's accuracy, test against adversarial inputs, and document cybersecurity measures. |
| **CE marking and EU registration** | Art. 16 | Regulatory filing with the EU AI database, CE marking, and appointing an EU representative are organizational obligations. |
| **Bias auditing** | Art. 10 | Statistical analysis of your model's outputs across protected characteristics. Tools like Fairlearn or Aequitas can help, but the analysis is yours. |
| **Incident response plan** | Multiple | Procedures for when your AI system fails, harms someone, or produces unexpected results. |

### Recommended tooling for the gaps

- **Article 10 (bias testing)**: [Fairlearn](https://fairlearn.org/), [Aequitas](http://www.datasciencepublicpolicy.org/our-work/tools-guides/aequitas/)
- **Article 11 (technical docs)**: Structured templates from your conformity assessment body
- **Article 15 (adversarial testing)**: [Adversarial Robustness Toolbox](https://adversarial-robustness-toolbox.readthedocs.io/)
- **Article 16 (EU registration)**: [EU AI Act Database](https://artificialintelligenceact.eu/database/) (not yet live as of this writing)

---

## Define Constitutional Rules for EU AI Act

Beyond the EU AI Act-specific modules, you can encode your compliance rules directly into your
agent's constitution. These rules enforce behavior at runtime, blocking non-compliant actions
before they execute.

```yaml
# eu_ai_act_constitution.yaml
name: eu-ai-act-governance
version: "1.0"
rules:
  - id: EU-001
    text: Agent must not make final decisions about individuals without human review
    severity: critical
    keywords: [final decision, reject candidate, deny application, terminate]
    category: regulatory
    workflow_action: require_human_review

  - id: EU-002
    text: Agent must not process special category data without explicit consent
    severity: critical
    keywords: [ethnicity, religion, political opinion, health data, sexual orientation]
    category: data-protection
    workflow_action: block

  - id: EU-003
    text: All AI-generated content must be disclosed as AI-generated
    severity: high
    keywords: [generate report, draft response, create summary]
    category: transparency
    workflow_action: warn

  - id: EU-004
    text: Agent must not bypass human oversight controls
    severity: critical
    keywords: [skip review, auto-approve, override human, bypass oversight]
    category: regulatory
    workflow_action: block
```

Load it and use it:

```python
from acgs_lite import Constitution, GovernedAgent

constitution = Constitution.from_yaml("eu_ai_act_constitution.yaml")
agent = GovernedAgent(my_agent, constitution=constitution)

# This will be blocked: EU-001 requires human review for final decisions
result = agent.run("reject candidate John Smith for the engineering role")
# -> Blocked: EU-001. Action requires human review.
```

Or build it programmatically:

```python
from acgs_lite import ConstitutionBuilder

constitution = (
    ConstitutionBuilder("eu-ai-act-governance", version="1.0.0")
    .add_rule(
        "EU-001",
        "No final decisions about individuals without human review",
        severity="critical",
        keywords=["final decision", "reject candidate", "deny application"],
        workflow_action="require_human_review",
    )
    .add_rule(
        "EU-002",
        "No processing of special category data without consent",
        severity="critical",
        keywords=["ethnicity", "religion", "health data"],
        workflow_action="block",
    )
    .build()
)
```

---

## Disclaimer

This guide is provided for informational purposes only. It is not legal advice. The EU AI Act
is a complex regulation and its interpretation continues to evolve through guidance documents,
delegated acts, and enforcement practice. Consult qualified legal counsel before relying on any
compliance self-assessment. ACGS-Lite generates indicative assessments that support -- but do
not replace -- professional legal review.
