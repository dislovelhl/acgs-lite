# ACGS -- HTTPS for AI

### If Machines Are Deciding Our Fate, Who Constrains the Machines?

**Constitutional governance infrastructure for AI agents. The missing safety layer between your LLM and production.**

`ACGS 2.4.1` | `AGPL-3.0-or-later` | `optional Rust fast path` | `pytest-backed verification`

[![Demo Video](https://img.youtube.com/vi/uWacmC3CbYg/maxresdefault.jpg)](https://youtu.be/uWacmC3CbYg)

> **Hackathon fast path:** If you're here for the GitLab AI Hackathon demo, start with **Constitutional Sentinel** — an ACGS-powered GitLab merge request governance agent that reviews AI-generated code, posts inline violations, and blocks unsafe merges. See `hackathon/devpost-submission.md`, `hackathon/demo-video-script.md`, `hackathon/constitution.yaml`, and the demo MR: <https://gitlab.com/martin664/constitutional-sentinel-demo/-/merge_requests/1>.
>
> **Note:** Performance numbers are from the local benchmark suite (`make bench`) and the fastest figures refer to the optional Rust/PyO3 hot path under benchmark conditions. Python-only and mixed integration paths will be slower. The benchmark target runs focused `pytest-benchmark` microbenchmarks for engine construction and steady-state validation. Run benchmarks on your own hardware before quoting exact latency. The public import path for this package is `from acgs_lite import ...`. Reserve `from acgs import ...` for the partial-open-source `acgs` distribution.
>
> **License:** AGPL-3.0-or-later for open-source use. [Commercial license](COMMERCIAL_LICENSE.md) available for proprietary/SaaS use.
>
> **Naming:** `ACGS` is the product name, `acgs-lite` is the public PyPI package, and `acgs_lite` is the Python import namespace for this distribution. See [../../docs/brand-architecture.md](../../docs/brand-architecture.md).

---

## GitLab AI Hackathon Demo: Constitutional Sentinel

**Constitutional Sentinel** is the hackathon demo built on ACGS. It is an independent governance agent for GitLab merge requests that:

- reacts to merge request events
- validates AI-generated diffs against constitutional rules
- posts inline comments on violating lines
- generates a governance summary with a constitutional hash
- blocks unsafe merges when violations are severe

### Judge / reviewer quick links

- Devpost draft: `hackathon/devpost-submission.md`
- Demo script: `hackathon/demo-video-script.md`
- Demo constitution: `hackathon/constitution.yaml`
- CI example: `hackathon/.gitlab-ci.yml`
- Demo MR: <https://gitlab.com/martin664/constitutional-sentinel-demo/-/merge_requests/1>

### Why it matters

AI coding agents can produce useful code quickly, but they do not inherently know your security, privacy, or compliance boundaries. Constitutional Sentinel inserts an independent validator into the GitLab workflow so unsafe changes are flagged before merge.

### Demo architecture

1. GitLab merge request event triggers Sentinel
2. Sentinel fetches and validates the diff using ACGS rules
3. Violations are posted back inline on the merge request
4. A governance summary records risk, findings, and constitutional hash
5. Human executor decides whether the merge proceeds

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
pip install acgs-lite
```

```python
from acgs_lite import Constitution, GovernedAgent

constitution = Constitution.from_yaml("rules.yaml")
agent = GovernedAgent(my_agent, constitution=constitution)
result = agent.run("process this request")  # Governed.
```

Every action validated against constitutional rules. Every decision recorded in a tamper-evident audit trail. Every role boundary enforced.

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
                 in benchmarked Rust paths. approves.
```

**The Critical Structural Boundary:** The Proposer can never act as its own Validator.

---

## Deployment Without Provable Governance is Uninsurable

**EU AI Act High-Risk Provisions Take Full Enforcement: August 2, 2026**

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
from acgs_lite.compliance import MultiFrameworkAssessor

assessor = MultiFrameworkAssessor()
report = assessor.assess({"jurisdiction": "EU", "domain": "healthcare"})
print(report.overall_score)        # 0.62 (auto-populated)
print(report.cross_framework_gaps) # Items needing manual evidence
```

---

## Frictionless Adoption: 5 Lines of Code

```python
from acgs_lite import Constitution, GovernedAgent

constitution = Constitution.from_template("general")
agent = GovernedAgent(my_agent, constitution=constitution)
result = agent.run("process this request")
```

Ships with 11 integration surfaces for common agent runtimes and deployment paths:

| Platform | Install | Status |
|----------|---------|--------|
| **Anthropic** | `acgs-lite[anthropic]` | Production |
| **MCP Server** | `acgs-lite[mcp]` | Production |
| **GitLab CI/CD** | `acgs-lite[gitlab]` | Production |
| OpenAI | `acgs-lite[openai]` | Maintained |
| xAI (OpenAI-compatible) | `acgs-lite[openai]` | Experimental |
| LangChain | `acgs-lite[langchain]` | Maintained |
| LiteLLM | `acgs-lite[litellm]` | Maintained |
| Google GenAI | `acgs-lite[google]` | Experimental |
| LlamaIndex | `acgs-lite[llamaindex]` | Experimental |
| AutoGen | `acgs-lite[autogen]` | Experimental |
| A2A | `acgs-lite[a2a]` | Experimental |

Additional built-in surfaces include HTTP middleware (`acgs_lite.middleware`),
the OpenShell governance API (`create_openshell_governance_app`), the Cloud
Run webhook server (`acgs_lite.integrations.cloud_run_server`), and optional
Cloud Logging export (`acgs-lite[google-cloud]`).

## CLI Surface

`acgs-lite` ships a package-local CLI for scaffolding, compliance scoring, report
generation, policy lifecycle management, telemetry export, and license flows.

```bash
acgs-lite init
acgs-lite assess --jurisdiction european_union --domain healthcare
acgs-lite report --markdown
acgs-lite eu-ai-act --domain healthcare
acgs-lite lint rules.yaml
acgs-lite test --fixtures tests.yaml
acgs-lite lifecycle summary
acgs-lite observe "approve deployment" --prometheus
acgs-lite activate ACGS-PRO-...
acgs-lite status
acgs-lite verify
```

---

## HTTP Middleware for Existing Apps

ACGS can be attached directly to HTTP services so inbound requests and outbound
responses are checked against your constitution without rewriting your app.

```python
from acgs_lite.middleware import GovernanceASGIMiddleware

app.add_middleware(
    GovernanceASGIMiddleware,
    strict=False,
    validate_responses=True,
    agent_id="http-middleware",
)
```

```python
from acgs_lite.middleware import GovernanceWSGIMiddleware

app.wsgi_app = GovernanceWSGIMiddleware(
    app.wsgi_app,
    strict=False,
    agent_id="http-middleware",
)
```

Both middleware variants restore engine strictness after non-blocking validation
paths, so response/request checks do not leak validation mode across requests.

---

## OpenShell Governance API

`acgs-lite` also exposes a stable FastAPI surface for the
`OpenClaw + OpenShell + ACGS` integration model. This is intended for PoC work
where OpenClaw proposes actions, ACGS makes the governance decision, and
OpenShell enforces the execution boundary.

Run it with `uvicorn`:

```bash
uvicorn "acgs_lite.server:create_governance_app" --factory --host 0.0.0.0 --port 8000
```

The app exposes both the original validation API and the OpenShell
governance routes:

- `POST /validate`
- `GET /stats`
- `POST /governance/evaluate-action`
- `POST /governance/submit-for-approval`
- `POST /governance/review-approval`
- `POST /governance/record-outcome`
- `GET /governance/audit-log`

Minimal example:

```bash
curl -X POST http://127.0.0.1:8000/governance/evaluate-action \
  -H "content-type: application/json" \
  -d '{
    "action_type": "github.write",
    "operation": "write",
    "risk_level": "high",
    "actor": {
      "actor_id": "agent/openclaw-primary",
      "role": "proposer",
      "sandbox_id": "sandbox-demo"
    },
    "resource": {
      "uri": "github://repo/org/repo/issues",
      "kind": "github_repo"
    },
    "context": {
      "request_id": "req_123",
      "session_id": "sess_456",
      "environment": "prod"
    },
    "requirements": {
      "requires_network": true,
      "requires_secret": true,
      "mutates_state": true
    },
    "payload": {
      "payload_hash": "sha256:abcd1234",
      "summary": "Create a GitHub issue for follow-up."
    }
  }'
```

`POST /governance/record-outcome` writes into the package's real
tamper-evident `AuditLog`, and `GET /governance/audit-log` returns the current
entries plus chain verification state.

Stable import surface:

```python
from acgs_lite import (
    ActionEnvelope,
    JsonFileGovernanceStateBackend,
    RedisGovernanceStateBackend,
    SQLiteGovernanceStateBackend,
    create_openshell_governance_app,
)
```

Pluggable persistence backends share a common state-storage protocol:

```python
app = create_openshell_governance_app(
    state_backend=JsonFileGovernanceStateBackend("state/openshell-governance.json")
)

# Or:
app = create_openshell_governance_app(
    state_backend=SQLiteGovernanceStateBackend("state/openshell-governance.db")
)

# Or:
app = create_openshell_governance_app(
    state_backend=RedisGovernanceStateBackend(redis_client)
)
```

---

## Human Oversight for High-Impact Decisions

For Article 14 style human-in-the-loop control, route risky decisions through
the human oversight gateway:

```python
from acgs_lite.eu_ai_act.human_oversight import HumanOversightGateway

gateway = HumanOversightGateway(
    system_id="cv-screener-v1",
    oversight_threshold=0.8,
)

decision = gateway.submit(
    "reject_candidate",
    "Rejected: insufficient Python experience",
    impact_score=0.91,
    context={"candidate_id": "abc123"},
)

if decision.requires_human_review:
    gateway.approve(decision.decision_id, reviewer_id="hr-1", notes="Approved after review")
```

Optional review/approval/rejection callbacks may fail without interrupting the
governance decision record itself, which makes notification hooks safe to use
with email, queue, or webhook transports.

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

## The Engine Built by the Machines

This entire constitutional governance engine -- 3,284 passing tests, Aho-Corasick optimization, MACI architecture -- was built by a non-technical founder who could not write a for loop two years ago. It was built entirely through conversation with Claude.

**If an AI is capable enough to help a non-technical founder build its own constitutional governance engine, it is capable enough to do immense damage without one.**

Governance must be democratic. The infrastructure that constrains the machines must be accessible to the people affected by them -- not just the corporations deploying them.

---

## Govern Responsibly.

```bash
pip install acgs-lite
```

AGPL-3.0-or-later Licensed | Open Source | [Commercial License Available](COMMERCIAL_LICENSE.md)

*The question was never whether power would be constrained -- it was whether the constraints would be built by the people affected or imposed after the damage was done.*

### Development Verification

For local package development, run pytest with importlib mode from the package
root:

```bash
python -m pytest tests -q --import-mode=importlib
```

The test configuration forces pytest to prefer the checked-out `src/` tree over
an already installed `acgs_lite` copy, so local verification exercises the code
you are editing.

### License

ACGS is dual-licensed:

- **AGPL-3.0-or-later** -- Free for open-source use, internal pipelines, CI/CD, and on-premise deployment.
- **Commercial License** -- Required if you embed ACGS in a proprietary SaaS product served to external users. Contact hello@acgs.ai.

See [COMMERCIAL_LICENSE.md](COMMERCIAL_LICENSE.md) for details and FAQ.

---

**[PyPI](https://pypi.org/project/acgs-lite/) | [Repository](https://gitlab.com/martin668/acgs-lite) | [Docs](https://gitlab.com/martin668/acgs-lite/-/blob/main/README.md)**

*Constitutional Hash: 608508a9bd224290*
