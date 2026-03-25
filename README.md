# ACGS -- HTTPS for AI

### If Machines Are Deciding Our Fate, Who Constrains the Machines?

**Constitutional governance infrastructure for AI agents. The missing safety layer between your LLM and production.**

`ACGS 2.1.0` | `AGPL-3.0-or-later` | `up to 560ns P50 on benchmark Rust path` | `3,267 tests passing`

> **Note:** Performance numbers are from the local benchmark suite (`make bench`) and the fastest figures refer to the optional Rust/PyO3 hot path under benchmark conditions. Python-only and mixed integration paths will be slower. The benchmark target runs focused `pytest-benchmark` microbenchmarks for engine construction and steady-state validation. Run benchmarks on your own hardware before quoting exact latency. The import path is `from acgs import ...` (preferred) or `from acgs_lite import ...` (legacy, still supported).
>
> **License:** AGPL-3.0-or-later for open-source use. [Commercial license](COMMERCIAL_LICENSE.md) available for proprietary/SaaS use.
>
> **Naming:** `ACGS` is the product name, `acgs` is the PyPI package, and `acgs_lite` is the compatibility import namespace. See [docs/brand-architecture.md](docs/brand-architecture.md).

---

## The Problem

$203 billion was invested in building decision-making AI engines in 2025. Less than 1% went to the infrastructure required to constrain them.

**We built the most powerful decision-making engines in human history and forgot the brakes.**

A single mother applies for a mortgage. 742 credit score. 12 years of stable employment. 28% debt-to-income ratio. The AI system rejects her in 340 milliseconds.

```json
{ "status": "REJECTED", "reason": "Risk score insufficient" }
```

- 0 Human Review
- 0 Appeal Process
- 0 Transparency

Billions of consequential decisions flow through AI systems daily -- none with verifiable governance.

---

## The Solution

```bash
pip install acgs
```

```python
from acgs import Constitution, GovernedAgent

constitution = Constitution.from_yaml("rules.yaml")
agent = GovernedAgent(my_agent, constitution=constitution)
result = agent.run("process this request")  # Governed.
```

Every action validated against constitutional rules. Every decision recorded in a tamper-evident audit trail. Every role boundary enforced.

### EU AI Act Compliance in 60 Seconds

```bash
pip install acgs
acgs init                                                    # Scaffold rules + CI
acgs eu-ai-act --system-id "my-system" --domain healthcare   # Assess + PDF report
```

```
  EU AI Act Compliance Assessment
  ==================================================
  System:            my-system
  Compliance Score:  65%
  ACGS Coverage:     65%
  Enforcement:       August 2, 2026
  Max Penalty:       7% global revenue / EUR 35M

  EU AI Act Article Checklist (High-Risk):
    ✅ Article 9:  Risk management system
    ⬜ Article 10: Data governance
    ⬜ Article 11: Technical documentation
    ✅ Article 12: Record-keeping (auto-logged)
    ✅ Article 13: Transparency (auto-generated)
    ✅ Article 14: Human oversight (MACI enforced)
    ✅ Article 72: Conformity assessment

  ✅ Report generated: eu_ai_act_my-system.pdf
  Hand this to your compliance officer.
```

Also available: `acgs assess`, `acgs report --pdf`, `acgs lint`.

---

## Translating 300 Years of Constitutional Law into Code

| The Human Legal Paradigm | The ACGS Machine Equivalent |
|---|---|
| **Separation of Powers** (Checks and Balances) | MACI Architecture. Agents cannot act as their own Validator. Role-based isolation ensures structural integrity. |
| **The Rule of Law** | Constitutional Engine. Immutable YAML rule definitions evaluated with O(n) Aho-Corasick deterministic scanning. |
| **Due Process & Right to Appeal** | Cryptographic Audit Trails. Every boundary check, role assignment, and validation is logged and tamper-evident. |

---

## The MACI Architecture: Ending Self-Validation

```
PROPOSER          VALIDATOR          EXECUTOR          OBSERVER
(Agent)     -->   (ACGS Engine) -->  (System)    -->   (Audit Log)
                       |
Generates the    Validates against   Only triggers    Cryptographically
proposed action. immutable YAML      if Validator     chains every
Cannot execute.  constitution        explicitly       boundary check.
                 in 560ns.           approves.
```

**The Critical Structural Boundary:** The Proposer can never act as its own Validator.

---

## Deployment Without Provable Governance is Uninsurable

**EU AI Act Takes Full Enforcement: August 2026**

Fines up to **7% of Global Annual Revenue**.

- Liability has permanently shifted from "who built the model" to "who deployed the model into production."
- Most enterprise architectures currently have zero infrastructure in place to programmatically prove compliance.

---

## ACGS is HTTPS for AI

| The 1990s Web | | |
|---|---|---|
| HTTP (Insecure & Unverifiable) | --> SSL/TLS Protocol Introduced | --> E-Commerce Scales Globally |

*The web could not scale commercially without cryptographic proof of secure transactions.*

| The 2020s Enterprise AI | | |
|---|---|---|
| Naked LLMs (Black Box & Unconstrained) | --> ACGS Protocol Introduced | --> Regulated Enterprise AI Adoption |

*AI cannot scale into high-stakes domains without cryptographic proof of constitutional compliance.*

---

## The Three Pillars of ACGS Architecture

### 1. Definition (Constitutional Engine)

Code-first governance. Context-aware matching, custom validators, and tamper-proof constitutional hashing.

- Define rules in YAML with keywords, regex patterns, and severity levels
- 5 domain templates: `Constitution.from_template("gitlab")`
- `ConstitutionBuilder` fluent API for code-first governance
- `Constitution.merge()` for composable, layered governance
- Constitutional diff for change auditing between versions

### 2. Enforcement (MACI Framework)

Role-based execution. Explicit permission sets. Self-validation prevention. Action risk classification.

- Four roles: Proposer, Validator, Executor, Observer
- Self-validation prevention: agents cannot validate their own output
- Action risk classification: LOW / MEDIUM / HIGH / CRITICAL
- Escalation tiers with SLA recommendations

### 3. Verification (Tamper-Proof Audit)

Immutable RuleSnapshot history. Inter-rule dependency graphs. OpenTelemetry metrics export.

- SHA-256 chain-verified audit trail
- Constitutional hash: `608508a9bd224290`
- Governance metrics collector for Prometheus/OpenTelemetry

---

## Out-of-the-Box Global Compliance Coverage

| Regulatory Framework | Primary Business Risk | ACGS Auto-Coverage |
|---|---|---|
| **EU AI Act** | 7% global revenue penalty | 5/9 items auto-covered |
| **NIST AI RMF** | US Federal Procurement gate | 7/16 items auto-covered |
| **ISO/IEC 42001** | International Audit failure risk | 9/18 items auto-covered |
| **SOC 2 + AI** | Enterprise gate / Lost contracts | 10/16 items auto-covered |
| **HIPAA + AI** | $1.5M fine per violation | 9/15 items auto-covered |
| **GDPR Art. 22** | 4% global revenue | 10/12 items auto-covered |
| **ECOA/FCRA** | Unlimited damages | 6/12 items auto-covered |
| **NYC LL 144** | $1,500/day | 6/12 items auto-covered |
| **OECD AI** | Baseline standard | 10/15 items auto-covered |

**125 total compliance checklist items across 9 global frameworks. 72 auto-populated by ACGS instantly.**

```python
from acgs.compliance import MultiFrameworkAssessor

assessor = MultiFrameworkAssessor()
report = assessor.assess({"jurisdiction": "EU", "domain": "healthcare"})
print(report.overall_score)        # 0.62 (auto-populated)
print(report.cross_framework_gaps) # Items needing manual evidence
```

---

## Frictionless Adoption: 5 Lines of Code

```python
from acgs import Constitution, GovernedAgent

constitution = Constitution.from_template("general")
agent = GovernedAgent(my_agent, constitution=constitution)
result = agent.run("process this request")
```

Ships with 11 out-of-the-box platform integrations:

| Platform | Install | Status |
|----------|---------|--------|
| **Anthropic** | `acgs[anthropic]` | Production |
| **MCP** | `acgs[mcp]` | Production |
| **GitLab CI/CD** | Built-in | Production |
| OpenAI | `acgs[openai]` | Maintained |
| LangChain | `acgs[langchain]` | Maintained |
| LiteLLM | `acgs[litellm]` | Maintained |
| Google GenAI | `acgs[google]` | Experimental |
| LlamaIndex | `acgs[llamaindex]` | Experimental |
| AutoGen | `acgs[autogen]` | Experimental |
| CrewAI | `acgs[crewai]` | Experimental |
| A2A | `acgs[a2a]` | Experimental |

---

## Frictionless CI/CD: The GitLab Duo Integration

1. **MR Webhook Fires** -- GitLab event triggered. Code diffs and commit messages enter the ACGS pipeline.
2. **The Governance Gate** -- MACI enforces separation: The MR Author (Proposer) cannot act as the Approver (Validator).
3. **Inline Violations** -- Findings appear directly on the exact line of the Git diff in the developer's native workflow.
4. **Cryptographic Chain** -- The MR is merged or hard-blocked. The final decision is instantly committed to a tamper-evident audit log.

```yaml
# .gitlab-ci.yml
governance:
  stage: test
  image: python:3.11-slim
  before_script:
    - pip install acgs
  script:
    - python3 -c "
      import asyncio, os, sys
      from acgs import Constitution
      from acgs.integrations.gitlab import GitLabGovernanceBot

      async def main():
          constitution = Constitution.from_yaml('rules.yaml')
          bot = GitLabGovernanceBot(
              token=os.environ['GITLAB_TOKEN'],
              project_id=int(os.environ['CI_PROJECT_ID']),
              constitution=constitution,
          )
          report = await bot.run_governance_pipeline(
              mr_iid=int(os.environ['CI_MERGE_REQUEST_IID'])
          )
          return 1 if report.violations else 0

      sys.exit(asyncio.run(main()))
      "
  rules:
    - if: $CI_PIPELINE_SOURCE == 'merge_request_event'
```

---

## The Engine Built by the Machines

This entire constitutional governance engine -- 3,133 passing tests, Aho-Corasick optimization, MACI architecture -- was built by a non-technical founder who could not write a for loop two years ago. It was built entirely through conversation with Claude.

**If an AI is capable enough to help a non-technical founder build its own constitutional governance engine, it is capable enough to do immense damage without one.**

Governance must be democratic. The infrastructure that constrains the machines must be accessible to the people affected by them -- not just the corporations deploying them.

---

## Govern Responsibly.

```bash
pip install acgs
```

AGPL-3.0-or-later Licensed | Open Source | [Commercial License Available](COMMERCIAL_LICENSE.md)

*The question was never whether power would be constrained -- it was whether the constraints would be built by the people affected or imposed after the damage was done.*

### License

ACGS is dual-licensed:

- **AGPL-3.0-or-later** -- Free for open-source use, internal pipelines, CI/CD, and on-premise deployment.
- **Commercial License** -- Required if you embed ACGS in a proprietary SaaS product served to external users. Contact hello@acgs.ai.

See [COMMERCIAL_LICENSE.md](COMMERCIAL_LICENSE.md) for details and FAQ.

---

**[PyPI](https://pypi.org/project/acgs/) | [GitHub](https://github.com/acgs2_admin/acgs) | [Website](https://acgs.ai)**

*Constitutional Hash: 608508a9bd224290*
