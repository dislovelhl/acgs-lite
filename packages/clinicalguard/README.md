# clinicalguard

[![PyPI](https://img.shields.io/pypi/v/clinicalguard)](https://pypi.org/project/clinicalguard/)
[![Python](https://img.shields.io/pypi/pyversions/clinicalguard)](https://pypi.org/project/clinicalguard/)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)

**Constitutional AI governance for clinical decision support — an A2A agent that validates proposed clinical actions against a 20-rule Healthcare AI Constitution.**

ClinicalGuard is a Starlette-based A2A (Agent-to-Agent) JSON-RPC service. It exposes three skills: clinical action validation (LLM reasoning + constitutional enforcement), HIPAA compliance checking, and tamper-evident audit log queries. Every decision is cryptographically logged in a hash-chained audit trail.

## Installation

```bash
pip install clinicalguard
```

> ClinicalGuard is a **service**, not a library. Install then run with `uvicorn` (see below). LLM-backed clinical reasoning also requires an LLM provider:
>
> ```bash
> pip install "clinicalguard[anthropic]"   # or [openai]
> ```

Requires Python 3.11+.

## Running the Service

```bash
uvicorn clinicalguard.main:app --host 0.0.0.0 --port 8080
```

Or with the module entry point:

```bash
python -m clinicalguard.main
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CLINICALGUARD_API_KEY` | _(unset)_ | When set, all requests require `X-API-Key: <key>` header |
| `CLINICALGUARD_AUDIT_LOG` | `/tmp/clinicalguard_audit.json` | Path for persisting the audit log |
| `CLINICALGUARD_URL` | `http://localhost:8080` | Public URL reported in the agent card |
| `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` | _(unset)_ | LLM credentials for clinical reasoning skill |

## Calling the Agent

ClinicalGuard speaks the A2A JSON-RPC protocol. All requests are `POST /` with `Content-Type: application/json`. The only supported method is `tasks/send`.

### Validate a clinical action

```bash
curl -s http://localhost:8080/ \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "1",
    "method": "tasks/send",
    "params": {
      "id": "task-001",
      "message": {
        "role": "user",
        "parts": [{"type": "text",
                   "text": "validate_clinical_action: Patient on Warfarin. Propose Aspirin 325mg daily."}]
      }
    }
  }'
```

Response fields: `decision` (APPROVED / CONDITIONALLY_APPROVED / REJECTED), `risk_tier` (LOW / MEDIUM / HIGH / CRITICAL), `reasoning`, `drug_interactions`, `conditions`, `audit_id`.

### Check HIPAA compliance

```bash
curl -s http://localhost:8080/ \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "2",
    "method": "tasks/send",
    "params": {
      "id": "task-002",
      "message": {
        "role": "user",
        "parts": [{"type": "text",
                   "text": "check_hipaa_compliance: Agent processes synthetic patient records, maintains MACI audit log, uses TLS in transit."}]
      }
    }
  }'
```

Response fields: `compliant` (bool), `items_checked`, `items_passing`, `items_failing`, `checklist` (list with status + MACI-mapped mitigations), `constitutional_hash`.

### Query audit trail

```bash
curl -s http://localhost:8080/ \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "3",
    "method": "tasks/send",
    "params": {
      "id": "task-003",
      "message": {
        "role": "user",
        "parts": [{"type": "text", "text": "query_audit_trail: last 5"}]
      }
    }
  }'
```

Skill name can also be provided in the `skill` field of the first message part instead of as a text prefix.

## Key Features

- **`validate_clinical_action`** — two-layer architecture: LLM clinical reasoning (evidence tier, drug interactions, step therapy) + `GovernanceEngine` constitutional enforcement (MACI, keyword/pattern rules, audit)
- **`check_hipaa_compliance`** — runs `acgs_lite.compliance.hipaa_ai.HIPAAAIFramework` against an agent description; maps each checklist item to its MACI role mitigation
- **`query_audit_trail`** — tamper-evident audit trail query; returns entries from the hash-chained `AuditLog`
- **Healthcare AI Constitution** — bundled 20-rule `constitution/healthcare_v1.yaml`; covers medication safety, PII/PHI, MACI enforcement, EHR access controls
- **PHI detection** — `phi_detector` custom validator catches 10 of 18 HIPAA Safe Harbor identifiers (SSN, MRN, DOB, phone, email, insurance ID, IP, account #, device/UDI, license #)
- **Clinical decision audit** — `clinical_decision_auditor` custom validator logs every clinical decision as a governance event
- **Security** — `X-API-Key` auth (when `CLINICALGUARD_API_KEY` is set), 64 KB request body limit, 10 K char text limit, input Unicode normalisation
- **A2A agent card** — `GET /.well-known/agent.json` returns the agent card for discovery

## Skill Reference

| Skill ID | Prefix / `skill` field | Description |
|----------|----------------------|-------------|
| `validate_clinical_action` | `validate_clinical_action: <text>` | Clinical action validation with LLM + constitutional rules |
| `check_hipaa_compliance` | `check_hipaa_compliance: <text>` | HIPAA compliance checklist against an agent description |
| `query_audit_trail` | `query_audit_trail: <query>` | Query the tamper-evident audit log |

## Package Structure

| Module | Description |
|--------|-------------|
| `clinicalguard.agent` | `create_app()` — builds the Starlette app with all routes and validators |
| `clinicalguard.main` | `app` — ASGI app; entry point for `uvicorn` |
| `clinicalguard.skills.validate_clinical` | `validate_clinical_action(text, engine, audit_log)` |
| `clinicalguard.skills.hipaa_checker` | `check_hipaa_compliance(agent_description)` |
| `clinicalguard.skills.healthcare_validators` | `phi_detector`, `clinical_decision_auditor`, `adverse_event_logger` custom validators |
| `constitution/healthcare_v1.yaml` | Bundled 20-rule Healthcare AI Constitution |

## Runtime dependencies

- `acgs-lite>=2.5`
- `starlette>=0.37`
- `uvicorn[standard]>=0.29`
- `pyyaml>=6.0`
- `httpx>=0.27`
- `pydantic>=2.0`

## License

AGPL-3.0-or-later.

## Links

- [Homepage](https://acgs.ai)
- [PyPI](https://pypi.org/project/clinicalguard/)
- [Issues](https://github.com/dislovelhl/clinicalguard/issues)
