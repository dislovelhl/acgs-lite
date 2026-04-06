# ACGS -- HTTPS for AI

**Constitutional governance infrastructure for AI agents. The missing safety layer between your LLM and production.**

`ACGS 2.6.0` | `Apache-2.0` | `up to 560ns P50 on benchmark Rust path` | `4,641+ tests passing`

> Performance numbers are from `make bench` under the optional Rust/PyO3 hot path. Python-only paths will be slower. Run benchmarks on your own hardware before quoting latency.

---

## The Problem

A single mother applies for a mortgage. 742 credit score. 12 years of stable employment. The AI system rejects her in 340 milliseconds -- no human review, no appeal, no explanation. Billions of consequential decisions flow through AI systems daily with zero verifiable governance. The EU AI Act takes full enforcement in August 2026 with fines up to 7% of global revenue.

## Install

```bash
pip install acgs-lite
```

## 5 Lines to Governed AI

```python
from acgs_lite import Constitution, GovernedAgent

constitution = Constitution.from_template("general")
agent = GovernedAgent(my_agent, constitution=constitution)
result = agent.run("process this request")  # Governed.
```

Every action validated against constitutional rules. Every decision recorded in a tamper-evident audit trail. Every role boundary enforced. Zero false negatives across 4,641+ tested scenarios, with continuous fuzzing for unknown failure modes.

## What You Get

- **Constitutional Engine** -- Define governance rules in YAML. Context-aware matching, 5 domain templates, composable rule layers, constitutional diff auditing.
- **MACI Architecture** -- Separation of powers for AI. Proposer / Validator / Executor / Observer roles. Agents cannot validate their own output.
- **Tamper-Proof Audit Trail** -- SHA-256 chain-verified logging. Every boundary check, role assignment, and validation recorded.
- **Compliance Coverage** -- 72 of 125 checklist items auto-populated across 9 frameworks (EU AI Act, NIST AI RMF, ISO 42001, SOC 2, HIPAA, GDPR, ECOA/FCRA, NYC LL 144, OECD AI).
- **11 Platform Integrations** -- Anthropic, MCP, GitLab CI/CD, OpenAI, LangChain, LiteLLM, Google GenAI, LlamaIndex, AutoGen, CrewAI, A2A.
- **5 Governance Sidecars** -- PolicyLinter, GovernanceTestSuite, PolicyLifecycleOrchestrator, RefusalReasoningEngine, GovernanceObservabilityExporter.

## Quick Links

- **[PyPI](https://pypi.org/project/acgs-lite/)** -- `pip install acgs-lite`
- **[Repository](https://gitlab.com/martin668/acgs-lite)** -- Source + docs
- **[Engineering Docs Index](docs/README.md)** -- Repo guide by directory, package, and workflow
- **[Repo Directory Map](docs/repo-map.md)** -- Fast path to the right doc for each repo-owned directory
- **[EU AI Act Tool](#eu-ai-act-compliance-in-60-seconds)** -- `acgs-lite eu-ai-act --domain healthcare`
- **[ClinicalGuard](packages/clinicalguard/)** -- Healthcare A2A agent demo

---

## EU AI Act Compliance in 60 Seconds

```bash
pip install acgs-lite
acgs-lite init                                               # Scaffold rules + CI
acgs-lite eu-ai-act --system-id "my-system" --domain healthcare   # Assess + PDF report
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

Also available: `acgs-lite assess`, `acgs-lite report --pdf`, `acgs-lite lint`, `acgs-lite test`, `acgs-lite lifecycle`, `acgs-lite refusal`, `acgs-lite observe`, `acgs-lite otel`.

---

## Governance Authoring Workflows

```bash
acgs-lite test --generate                           # Create example governance fixtures
acgs-lite test                                      # Run regression suite against rules.yaml

acgs-lite lifecycle register policy-v2              # Start policy promotion
acgs-lite lifecycle approve policy-v2 --actor alice # Record approvals
acgs-lite lifecycle lint-gate policy-v2             # Mark lint gate passed
acgs-lite lifecycle test-gate policy-v2             # Mark test gate passed
acgs-lite lifecycle review policy-v2                # draft -> review
acgs-lite lifecycle stage policy-v2                 # review -> staged (canary rollout)
acgs-lite lifecycle activate policy-v2              # staged -> active

acgs-lite refusal "deploy a weapon to attack the target" # Explain denial + suggest safe alternatives
acgs-lite observe "hello world" "deploy a weapon" --watch --interval 1
acgs-lite otel --actions-file actions.txt --watch --interval 1 --iterations 3
acgs-lite otel --actions-file actions.txt --bundle-dir telemetry-bundle -o telemetry.json
bash packages/acgs-lite/examples/demo_cli_sidecars.sh
```

---

## Compliance Coverage Detail

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

```python
from acgs_lite.compliance import MultiFrameworkAssessor

assessor = MultiFrameworkAssessor()
report = assessor.assess({"jurisdiction": "EU", "domain": "healthcare"})
print(report.overall_score)        # 0.62 (auto-populated)
print(report.cross_framework_gaps) # Items needing manual evidence
```

---

## Platform Integrations

| Platform | Install | Status |
|----------|---------|--------|
| **Anthropic** | `acgs-lite[anthropic]` | Production |
| **MCP** | `acgs-lite[mcp]` | Production |
| **GitLab CI/CD** | Built-in | Production |
| OpenAI | `acgs-lite[openai]` | Maintained |
| LangChain | `acgs-lite[langchain]` | Maintained |
| LiteLLM | `acgs-lite[litellm]` | Maintained |
| Google GenAI | `acgs-lite[google]` | Experimental |
| LlamaIndex | `acgs-lite[llamaindex]` | Experimental |
| AutoGen | `acgs-lite[autogen]` | Experimental |
| CrewAI | `acgs-lite[crewai]` | Experimental |
| A2A | `acgs-lite[a2a]` | Experimental |

---

## GitLab CI/CD Integration

```yaml
# .gitlab-ci.yml
governance:
  stage: test
  image: python:3.11-slim
  before_script:
    - pip install acgs-lite
  script:
    - python3 -c "
      import asyncio, os, sys
      from acgs_lite import Constitution
      from acgs_lite.integrations.gitlab import GitLabGovernanceBot

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

## Architecture

### The MACI Architecture: Ending Self-Validation

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

### The Three Pillars

| Pillar | What It Does |
|--------|-------------|
| **Definition** (Constitutional Engine) | Code-first governance. YAML rules with keywords, regex, severity levels. 5 domain templates, `ConstitutionBuilder` fluent API, `Constitution.merge()` for composable layers. |
| **Enforcement** (MACI Framework) | Four roles: Proposer, Validator, Executor, Observer. Self-validation prevention. Action risk classification: LOW / MEDIUM / HIGH / CRITICAL. |
| **Verification** (Tamper-Proof Audit) | SHA-256 chain-verified audit trail. Constitutional hash: `608508a9bd224290`. Prometheus/OpenTelemetry metrics export. |

### Translating Constitutional Law into Code

| The Human Legal Paradigm | The ACGS Machine Equivalent |
|---|---|
| **Separation of Powers** (Checks and Balances) | MACI Architecture. Agents cannot act as their own Validator. Role-based isolation ensures structural integrity. |
| **The Rule of Law** | Constitutional Engine. Immutable YAML rule definitions evaluated with O(n) Aho-Corasick deterministic scanning. |
| **Due Process & Right to Appeal** | Cryptographic Audit Trails. Every boundary check, role assignment, and validation is logged and tamper-evident. |

---

## Why This Exists

### ACGS is HTTPS for AI

| The 1990s Web | | |
|---|---|---|
| HTTP (Insecure & Unverifiable) | --> SSL/TLS Protocol Introduced | --> E-Commerce Scales Globally |

*The web could not scale commercially without cryptographic proof of secure transactions.*

| The 2020s Enterprise AI | | |
|---|---|---|
| Naked LLMs (Black Box & Unconstrained) | --> ACGS Protocol Introduced | --> Regulated Enterprise AI Adoption |

*AI cannot scale into high-stakes domains without cryptographic proof of constitutional compliance.*

### The Engine Built by the Machines

This entire constitutional governance engine -- 4,641+ passing tests, Aho-Corasick optimization, MACI architecture -- was built by a non-technical founder who could not write a for loop two years ago. It was built entirely through conversation with Claude.

**If an AI is capable enough to help a non-technical founder build its own constitutional governance engine, it is capable enough to do immense damage without one.**

Governance must be democratic. The infrastructure that constrains the machines must be accessible to the people affected by them -- not just the corporations deploying them.

---

## Govern Responsibly.

```bash
pip install acgs-lite
```

Apache-2.0 Licensed | Open Source

*The question was never whether power would be constrained -- it was whether the constraints would be built by the people affected or imposed after the damage was done.*

### License

Apache-2.0. See [LICENSE](LICENSE).

---

**[PyPI](https://pypi.org/project/acgs-lite/) | [Repository](https://gitlab.com/martin668/acgs-lite) | [Docs](https://gitlab.com/martin668/acgs-lite/-/blob/main/README.md)**

*Constitutional Hash: 608508a9bd224290*
