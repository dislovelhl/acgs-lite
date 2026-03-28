# ACGS -- HTTPS for AI

**Constitutional governance for AI agents. Enforce rules, audit decisions, prevent self-validation.**

`Apache-2.0` | `Python 3.10+` | `optional Rust fast path` | `pip install acgs-lite`

---

## Quickstart

```bash
pip install acgs-lite
```

```python
from acgs_lite import Constitution, GovernedAgent

constitution = Constitution.from_template("general")
agent = GovernedAgent(my_agent, constitution=constitution)
result = agent.run("process this request")  # Governed.
```

Every action validated against constitutional rules. Every decision recorded in a tamper-evident audit trail. Every role boundary enforced.

---

## What It Does

| Capability | How |
|---|---|
| **Separation of powers** | MACI architecture. Agents cannot validate their own output. Proposer / Validator / Executor / Observer. |
| **Tamper-evident audit** | SHA-256 chain-verified audit trail. Constitutional hash: `608508a9bd224290`. |
| **Constitutional rules** | Define rules in YAML with keywords, regex patterns, and severity levels. 5 domain templates included. |
| **Compliance evidence** | Auto-populates 72/125 checklist items across 9 frameworks (EU AI Act, NIST AI RMF, SOC 2, GDPR, HIPAA, ISO 42001, ECOA/FCRA, NYC LL 144, OECD AI). |
| **Framework integrations** | Wrap any agent framework in governance with one line. |

---

## Integrations

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

Additional surfaces: HTTP middleware (`acgs_lite.middleware`), OpenShell governance API,
Cloud Run webhook server, and optional Cloud Logging export (`acgs-lite[google-cloud]`).

---

## The MACI Architecture

```
PROPOSER          VALIDATOR          EXECUTOR          OBSERVER
(Agent)     -->   (ACGS Engine) -->  (System)    -->   (Audit Log)
                       |
Generates the    Validates against   Only triggers    Cryptographically
proposed action. immutable YAML      if Validator     chains every
Cannot execute.  constitution        explicitly       boundary check.
                 in benchmarked Rust paths. approves.
```

**The critical boundary:** The Proposer can never act as its own Validator.

---

## Compliance Coverage

| Framework | Risk | ACGS Auto-Coverage |
|---|---|---|
| **EU AI Act** | 7% global revenue penalty | 5/9 items |
| **NIST AI RMF** | US Federal procurement gate | 7/16 items |
| **ISO/IEC 42001** | International audit failure | 9/18 items |
| **SOC 2 + AI** | Enterprise gate / lost contracts | 10/16 items |
| **HIPAA + AI** | $1.5M fine per violation | 9/15 items |
| **GDPR Art. 22** | 4% global revenue | 10/12 items |

```python
from acgs_lite.compliance import MultiFrameworkAssessor

assessor = MultiFrameworkAssessor()
report = assessor.assess({"jurisdiction": "EU", "domain": "healthcare"})
print(report.overall_score)        # 0.62 (auto-populated)
print(report.cross_framework_gaps) # Items needing manual evidence
```

---

## CLI

```bash
acgs-lite init
acgs-lite assess --jurisdiction european_union --domain healthcare
acgs-lite report --markdown
acgs-lite eu-ai-act --domain healthcare
acgs-lite lint rules.yaml
acgs-lite test --fixtures tests.yaml
acgs-lite lifecycle summary
acgs-lite observe "approve deployment" --prometheus
acgs-lite verify
```

---

## HTTP Middleware

Attach governance to existing HTTP services without rewriting your app.

```python
from acgs_lite.middleware import GovernanceASGIMiddleware

app.add_middleware(
    GovernanceASGIMiddleware,
    strict=False,
    validate_responses=True,
    agent_id="http-middleware",
)
```

WSGI variant also available via `GovernanceWSGIMiddleware`.

---

## Human Oversight

For Article 14 style human-in-the-loop control:

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

## OpenShell Governance API

A FastAPI surface for the OpenClaw + OpenShell + ACGS integration model.

```bash
uvicorn "acgs_lite.server:create_governance_app" --factory --host 0.0.0.0 --port 8000
```

Endpoints: `POST /validate`, `GET /stats`, `POST /governance/evaluate-action`,
`POST /governance/submit-for-approval`, `POST /governance/review-approval`,
`POST /governance/record-outcome`, `GET /governance/audit-log`.

Pluggable persistence: `JsonFileGovernanceStateBackend`, `SQLiteGovernanceStateBackend`,
`RedisGovernanceStateBackend`.

---

## Development

```bash
python -m pytest tests -q --import-mode=importlib
```

Performance benchmarks use the optional Rust/PyO3 hot path. Run `make bench` on your
own hardware before quoting latency numbers. Python-only paths will be slower.

The public import path is `from acgs_lite import ...`.

---

## GitLab AI Hackathon: Constitutional Sentinel

Constitutional Sentinel is a governance agent for GitLab merge requests that validates
AI-generated diffs against constitutional rules, posts inline violations, and blocks
unsafe merges.

- Devpost: `hackathon/devpost-submission.md`
- Demo: `hackathon/demo-video-script.md`
- Constitution: `hackathon/constitution.yaml`
- Demo MR: <https://gitlab.com/martin664/constitutional-sentinel-demo/-/merge_requests/1>

[![Demo Video](https://img.youtube.com/vi/uWacmC3CbYg/maxresdefault.jpg)](https://youtu.be/uWacmC3CbYg)

---

## License

Apache-2.0. See [LICENSE](LICENSE).

**[PyPI](https://pypi.org/project/acgs-lite/) | [Repository](https://gitlab.com/martin668/acgs-lite) | [Docs](https://gitlab.com/martin668/acgs-lite/-/blob/main/README.md)**

*Constitutional Hash: 608508a9bd224290*
