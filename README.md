# ACGS-Lite: Constitutional AI Governance for Agents

[![PyPI](https://img.shields.io/pypi/v/acgs-lite?color=blue&style=for-the-badge)](https://pypi.org/project/acgs-lite/)
[![Python](https://img.shields.io/pypi/pyversions/acgs-lite?style=for-the-badge)](https://pypi.org/project/acgs-lite/)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-green.svg?style=for-the-badge)](https://www.apache.org/licenses/LICENSE-2.0)
[![CI](https://img.shields.io/github/actions/workflow/status/dislovelhl/acgs-lite/ci.yml?branch=main&style=for-the-badge&label=CI)](https://github.com/dislovelhl/acgs-lite/actions)
[![Coverage](https://img.shields.io/badge/tests-4641%20passing-brightgreen?style=for-the-badge)](https://github.com/dislovelhl/acgs-lite/actions)
[![Documentation](https://img.shields.io/badge/docs-acgs.ai-brightgreen?style=for-the-badge)](https://acgs.ai/docs)
[![GitHub stars](https://img.shields.io/github/stars/dislovelhl/acgs-lite?style=social)](https://github.com/dislovelhl/acgs-lite/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/dislovelhl/acgs-lite?style=social)](https://github.com/dislovelhl/acgs-lite/network/members)
[![Featured in Awesome LLM Security](https://awesome.re/badge-flat2.svg)](https://github.com/beyefendi/awesome-llm-security)


<img width="1280" height="680" alt="ACGS_Lite" src="https://github.com/user-attachments/assets/0d6deeef-40fe-4e8e-9dc0-537744162dff" />

# **The missing safety layer between your LLM and production.**

**acgs-lite** is the production-ready runtime governance engine for AI agents. It sits **between your agent and execution** — every action is validated against a YAML constitution **before** it runs. Violations are blocked by default (fail-closed). Every decision is recorded in a tamper-evident audit chain. Human operators can intervene at any time.

**Current status:** Stable core (v2.9.0) • 4,641 tests passing • Used in regulated pilots.

**Star this repo** if you want more open-source infrastructure for governed, production-safe agents. Early stars materially help discovery.

## ❤️ Community favorites

If you found ACGS-Lite through [Awesome LLM Security](https://github.com/beyefendi/awesome-llm-security), these are the most shared starting points:

- **AI-agent install verify** — [`examples/agent_quickstart/`](./examples/agent_quickstart/) runs a self-verifying suite: `GovernedCallable` + MACI + AuditLog in one script, exits 0 on success
- **Fastest proof** — [`examples/basic_governance/`](./examples/basic_governance/) shows safe requests passing and unsafe ones blocked before execution
- **Best audit demo** — [`examples/audit_trail/`](./examples/audit_trail/) shows the tamper-evident decision chain
- **Favorite infrastructure path** — [`examples/mcp_agent_client.py`](./examples/mcp_agent_client.py) runs governance as shared MCP-compatible infrastructure
- **Favorite compliance proof** — `acgs assess --framework eu-ai-act` maps controls to real regulatory requirements

## Hero demo

**20-second proof:** safe actions pass, unsafe actions get blocked before execution.

- run `python examples/basic_governance/main.py`
- watch a safe request pass
- watch harmful and PII-like requests get blocked

<!-- Hero asset placement, add once captured:
<p align="center">
  <img src="./docs/assets/basic-governance-hero.gif" alt="Terminal demo of acgs-lite allowing a safe request and blocking harmful and PII-like requests before execution." width="900" />
</p>
-->

---

## Start here in 3 minutes

**Fastest proof path:**

1. **Block an unsafe action** with [`examples/basic_governance/`](./examples/basic_governance/)
2. **Inspect the audit evidence** with [`examples/audit_trail/`](./examples/audit_trail/)
3. **Run governance as shared infrastructure** with [`examples/mcp_agent_client.py`](./examples/mcp_agent_client.py)

```bash
pip install acgs-lite
python examples/basic_governance/main.py
```

Expected result includes these three outcomes near the top:

```text
✅  Allowed:  Response to: What is the capital of France?
🚫  Blocked:  no-harmful-content — Block requests containing harmful keywords
🚫  PII gate: no-pii — Prevent PII leakage in requests
```

If you want the full example path, go to [`examples/README.md`](./examples/README.md).

---

## What this proves

- **Block before execution**: unsafe actions are denied before your agent runs them
- **Separate powers with MACI**: proposer, validator, executor do not collapse into one actor
- **Keep audit evidence**: each decision can be chained, inspected, and verified later

---

## 🚀 5-Line Quickstart

```python
from acgs_lite import Constitution, GovernedAgent

constitution = Constitution.from_yaml("constitution.yaml")
agent = GovernedAgent(my_llm_agent, constitution=constitution)
result = agent.run("Process this high-risk transaction")
```

Rules in YAML (`constitution.yaml`):

```yaml
constitutional_hash: "608508a9bd224290"
rules:
  - id: no-pii
    pattern: "SSN|social security|passport number"
    severity: CRITICAL
    description: Block PII exposure

  - id: no-destructive
    pattern: "delete|drop table|rm -rf"
    severity: HIGH
    description: Block destructive operations

  - id: require-approval
    pattern: "transfer|payment|wire"
    severity: HIGH
    description: Financial actions require human approval
```

---

## 📦 Installation

```bash
pip install acgs-lite
```

With framework integrations:

```bash
pip install "acgs-lite[openai]"       # OpenAI
pip install "acgs-lite[anthropic]"    # Anthropic Claude
pip install "acgs-lite[langchain]"    # LangChain / LangGraph
pip install "acgs-lite[mcp]"          # Model Context Protocol server
pip install "acgs-lite[autogen]"      # AutoGen / AG2
pip install "acgs-lite[a2a]"          # Google A2A protocol
pip install "acgs-lite[agno]"         # Agno agent framework
pip install "acgs-lite[server]"       # FastAPI lifecycle HTTP server
pip install "acgs-lite[all]"          # All integrations
```

---

## 🛡️ Core Concepts

### Governance Engine

The `GovernanceEngine` sits between your agent and its tools. Every action passes through it before execution. Matching rules block or flag the action; the result is an immutable `ValidationResult`.

```python
from acgs_lite import Constitution, GovernanceEngine, Rule, Severity

constitution = Constitution.from_rules([
    Rule(id="no-pii", pattern=r"SSN|\bpassport\b", severity=Severity.CRITICAL),
    Rule(id="no-delete", pattern=r"\bdelete\b|\bdrop\b", severity=Severity.HIGH),
])

engine = GovernanceEngine(constitution)
result = engine.validate("summarize the quarterly report", agent_id="analyst-01")

if not result.valid:
    for v in result.violations:
        print(f"[{v.severity}] {v.rule_id}: {v.description}")
```

### MACI — Separation of Powers

MACI prevents a single agent from proposing, validating, and executing the same action:

```python
from acgs_lite import MACIEnforcer, MACIRole

enforcer = MACIEnforcer()

# Assign roles
enforcer.assign(agent_id="planner",   role=MACIRole.PROPOSER)
enforcer.assign(agent_id="reviewer",  role=MACIRole.VALIDATOR)
enforcer.assign(agent_id="executor",  role=MACIRole.EXECUTOR)

# Proposer creates; Validator checks; Executor runs — never the same agent
proposal = enforcer.propose("planner", action="deploy v2.1 to production")
approval = enforcer.validate("reviewer", proposal)
enforcer.execute("executor", approval)
```

### Tamper-Evident Audit Trail

Every governance decision is written to an append-only, SHA-256-chained log:

```python
from acgs_lite import AuditLog

log = AuditLog()
engine = GovernanceEngine(constitution, audit_log=log)

engine.validate("send email to user@example.com", agent_id="mailer")

for entry in log.entries():
    print(entry.id, entry.valid, entry.constitutional_hash)

# Verify chain integrity
assert log.verify_chain(), "Audit log tampered!"
```

### GovernedAgent — Drop-in Wrapper

```python
from acgs_lite import Constitution, GovernedAgent

@GovernedAgent.decorate(constitution=constitution, agent_id="summarizer")
def summarize(text: str) -> str:
    return my_llm.complete(f"Summarize: {text}")

# Raises ConstitutionalViolationError if text contains violations
result = summarize("Q4 revenue was $4.2M")
```

---

## 🔒 Safety Defaults

`acgs-lite` is **fail-closed by default**. This is a design principle, not a configuration option.

| Guarantee | Behavior |
|-----------|----------|
| **Engine exception** | Validation raises `ConstitutionalViolationError`; the action is blocked, not silently passed |
| **Missing constitution** | Engine refuses to initialize; no degraded-mode passthrough |
| **Rule match** | Action is blocked unless the rule explicitly sets `workflow_action: warn` |
| **Audit write failure** | Logged at warning level; does not unblock the action |
| **MACI misconfiguration** | Warning raised at startup; enforcement is advisory unless `enforce_maci=True` |
| **MCP server strict-mode** | `engine.strict` is restored in `try/finally` at every call site — an exception during `validate()` cannot leave strict mode permanently disabled (as of 2.9.0) |

> **Note:** The strict-mode restoration guarantee above is scoped to the MCP server integration.
> Other integrations that mutate `engine.strict` directly (e.g., custom adapters) are responsible
> for their own restoration. Use `engine.non_strict()` (a context manager at `acgs_lite.engine.core`)
> for safe per-call non-strict validation that always restores strict mode.

To opt into fail-open (e.g., for testing), you must set it explicitly:

```python
engine = GovernanceEngine(constitution, strict=False)  # explicit; off by default
```

Enforcement actions progress from least to most restrictive:
`warn` → `block` → `block_and_notify` → `require_human_review` → `escalate_to_senior` → `halt_and_alert`

---

## 🗺️ Component Stability

Not all layers are equally hardened. Use this table to calibrate trust in each area:

| Component | Status | Notes |
|-----------|--------|-------|
| `GovernanceEngine` — rule validation | ✅ **Stable** | Core hot path; Aho-Corasick matcher, fail-closed exceptions |
| `Constitution` — YAML loading, rule parsing | ✅ **Stable** | Hash-pinned; schema-validated |
| `Rule`, `Severity`, `ValidationResult` | ✅ **Stable** | Stable data model; additive changes only |
| `MACIEnforcer` — role separation | ✅ **Stable** | Role checks are enforced; pass `enforce_maci=True` for hard failures |
| `AuditLog` — SHA-256 chained trail | ✅ **Stable** | Thread-safe append-only; chain verification tested |
| `GovernedAgent` — drop-in wrapper | ✅ **Stable** | Synchronous and async paths covered |
| OpenAI / Anthropic / LangChain adapters | ✅ **Stable** | Thin validated wrappers; covers completions and streaming |
| Constitution lifecycle API (HTTP) | 🔶 **Beta** | Draft/review/activate/rollback endpoints are functional; API may evolve |
| SQLite bundle store, lifecycle persistence | 🔶 **Beta** | WAL-mode; covers single-node; multi-writer not yet hardened |
| `acgs assess` compliance mapping | 🔶 **Beta** | 18-framework coverage; control mappings improve with each release |
| MCP server integration | 🔶 **Beta** | Single-node; production use requires your own transport hardening |
| Intervention / quarantine / halt workflow | 🔶 **Beta** | Full path functional; thread-safety hardened; API may evolve |
| Z3 constraint verifier | 🧪 **Experimental** | Useful for high-risk scenarios; requires separate Z3 install |
| Lean 4 / Leanstral proof certificates | 🧪 **Experimental** | Requires `mistralai` extra and external Lean kernel |
| Newer framework adapters (Agno, A2A, LiteLLM, Mistral) | 🧪 **Experimental** | Community-contributed; test coverage varies |

---

## ✅ What is production-hardened today (v2.9.0)

| Layer | Status | What you get |
|-------|--------|--------------|
| `GovernanceEngine` | Stable | YAML rules, deterministic validation, fail-closed enforcement |
| MACI role separation | Stable | Proposer / Validator / Executor enforced at runtime |
| Audit Trail | Stable | SHA-256 chained, SQLite-backed, queryable, exportable |
| `GovernedAgent` wrapper | Stable | Drop-in decorator for OpenAI, Anthropic, LangChain, MCP, etc. |
| Intervention & Quarantine | Stable | `require_human_review`, `halt_and_alert`, `quarantine` actions |
| CLI (`acgs validate`, `audit`, `halt`) | Stable | Full local & CI usage |

**Everything else** (constitution lifecycle API, formal verification with Z3/Lean, 18-framework compliance mapping) is **Beta / Experimental** and clearly marked in the Component Stability table above.

---

## 🌐 Integrations

### OpenAI

```python
from acgs_lite.integrations.openai import GovernedOpenAI
from openai import OpenAI

client = GovernedOpenAI(OpenAI(), constitution=constitution)
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Analyze the contract"}],
)
```

### Anthropic Claude

```python
from acgs_lite.integrations.anthropic import GovernedAnthropic
import anthropic

client = GovernedAnthropic(anthropic.Anthropic(), constitution=constitution)
message = client.messages.create(
    model="claude-opus-4-5",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Review this code"}],
)
```

### LangChain

```python
from acgs_lite.integrations.langchain import GovernanceRunnable
from langchain_openai import ChatOpenAI

governed_llm = GovernanceRunnable(
    ChatOpenAI(model="gpt-4o"),
    constitution=constitution,
)
result = governed_llm.invoke("Translate this document")
```

### MCP Server

Start a governance server that any MCP-compatible agent can query:

```bash
acgs serve --host 0.0.0.0 --port 8080
```

```python
from acgs_lite.integrations.mcp_server import create_mcp_server
app = create_mcp_server(constitution=constitution)
```

---

## 📋 Compliance Coverage

ACGS maps governance controls to 18 regulatory frameworks. Run `acgs assess` to generate a compliance report:

```bash
acgs assess --framework eu-ai-act --output report.pdf
```

| Framework | Coverage | Key Controls |
|-----------|----------|--------------|
| **EU AI Act (High-Risk)** | Art. 9, 10, 13, 14, 17 | Risk management, human oversight, transparency |
| **NIST AI RMF** | 7 / 16 functions | Govern, Map, Measure, Manage |
| **SOC 2 + AI** | 10 / 16 criteria | CC6, CC7, CC9 trust service criteria |
| **HIPAA + AI** | 9 / 15 safeguards | PHI detection, access controls, audit controls |
| **GDPR Art. 22** | 10 / 12 requirements | Automated decision-making, right to explanation |
| **CCPA / CPRA** | 8 / 10 rights | Opt-out, data minimisation, transparency |
| **ISO 42001** | Clause 6, 8, 9, 10 | AI management system controls |
| **OWASP LLM Top 10** | 9 / 10 risks | Prompt injection, insecure output, data poisoning |

---

## 🔬 Advanced: Formal Verification

For the highest-risk scenarios, ACGS supports mathematical proof of safety properties.

### Z3 SMT Solver

```python
from acgs_lite.integrations.z3_verifier import Z3ConstraintVerifier

verifier = Z3ConstraintVerifier()
result = verifier.verify(
    action="transfer $50,000 to external account",
    constraints=["amount <= 10000", "recipient in approved_list"],
)
print(result.satisfiable, result.counterexample)
```

### Lean 4 Proof Certificates (Leanstral)

```python
from acgs_lite import LeanstralVerifier

verifier = LeanstralVerifier()  # requires mistralai extra
certificate = await verifier.verify(
    property="∀ action : Action, action.amount ≤ 10000",
    context={"action": "transfer $5,000"},
)
print(certificate.kernel_verified)  # True only if Lean kernel accepted proof
print(certificate.to_audit_dict())  # attach to AuditEntry
```

---

## ⚡ Performance

| Operation | Latency | Notes |
|-----------|---------|-------|
| Rule validation (Python) | < 1 ms | Aho-Corasick multi-pattern |
| Rule validation (Rust) | ~560 ns | Optional Rust extension |
| Engine batch (100 rules) | ~2 ms | Parallel severity evaluation |
| Audit write (JSONL) | ~50 µs | Append-only, SHA-256 chained |
| Compliance report | < 500 ms | 18 frameworks, cached |

---

## 🖥️ CLI

```bash
# Validate a single action
acgs validate "send email to user@corp.com" --constitution rules.yaml

# Run governance status check
acgs status

# Generate compliance report
acgs assess --framework hipaa --output hipaa_report.pdf

# Audit log inspection
acgs audit --tail 20
acgs audit --verify-chain

# Start MCP governance server
acgs serve --port 8080

# EU AI Act Art. 14(3) kill switch
acgs halt --agent-id agent-01 --reason "anomalous behaviour detected"
acgs resume --agent-id agent-01
```

---

## 📖 Documentation

| Guide | Description |
|-------|-------------|
| [Examples](./examples/README.md) | Canonical demo path: block, audit, then MCP |
| [Quickstart](https://acgs.ai/docs/quickstart) | Up and running in 5 minutes |
| [Architecture](https://acgs.ai/docs/architecture) | Engine internals, MACI deep dive |
| [Integrations](https://acgs.ai/docs/integrations) | OpenAI, Anthropic, LangChain, MCP, A2A |
| [Compliance](https://acgs.ai/docs/compliance-2026) | 18-framework regulatory mapping |
| [CLI Reference](https://acgs.ai/docs/cli) | Full command reference |
| [Why Governance?](https://acgs.ai/docs/why-governance) | The case for deterministic guardrails |
| [OWASP LLM Top 10](https://acgs.ai/docs/owasp-2026) | ACGS coverage of each risk |
| [Testing Guide](https://acgs.ai/docs/testing-governance) | Testing governed agents |
| [Constitution Lifecycle API](./docs/api/lifecycle.md) | HTTP endpoints for draft, review, eval, activation, rollback, and reject |

---

## 🤝 Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

```bash
git clone https://github.com/dislovelhl/acgs-lite
cd acgs-lite/packages/acgs-lite
pip install -e ".[dev]"
pytest tests/ --import-mode=importlib
```

---

## 📄 License

Apache-2.0. See [LICENSE](LICENSE) for details.

Commercial enterprise licences (SLA, support, air-gapped deployment) available at [acgs.ai](https://acgs.ai).

---

*Constitutional Hash: `608508a9bd224290` — embedded in every validation path.*
