# clinicalguard

[![PyPI](https://img.shields.io/pypi/v/clinicalguard)](https://pypi.org/project/clinicalguard/)
[![Python](https://img.shields.io/pypi/pyversions/clinicalguard)](https://pypi.org/project/clinicalguard/)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)

**Constitutional AI governance for healthcare agents.**

`clinicalguard` is a Starlette-based A2A service for validating proposed clinical
actions against a healthcare constitution. It combines deterministic ACGS validation,
healthcare-specific validators, JSON-RPC 2.0 endpoints, and audit-trail persistence.

## Installation

`clinicalguard` supports Python 3.11+.

```bash
pip install acgs-lite clinicalguard
pip install clinicalguard[anthropic]
pip install clinicalguard[openai]
```

`clinicalguard` currently relies on `acgs-lite` at runtime; install it alongside the
package when working from PyPI or source checkouts.

## Quick Start

### Run the Service

```bash
uvicorn clinicalguard.main:app --host 0.0.0.0 --port 8080
```

### Validate a Clinical Action

```bash
curl -X POST http://localhost:8080/ \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tasks/send",
    "params": {
      "id": "task-001",
      "message": {
        "parts": [{
          "text": "validate_clinical_action: Patient SYNTH-042 on Warfarin. Propose Aspirin 325mg daily."
        }]
      }
    }
  }'
```

### Build the App in Python

```python
from clinicalguard.agent import ClinicalGuardApp

guard = ClinicalGuardApp.create(
    constitution_path="constitution/healthcare_v1.yaml",
    audit_log_path="audit.jsonl",
)
app = guard.build_starlette_app()
```

## Key Features

- Healthcare-focused constitutional validation with MACI-style self-approval blocking.
- A2A skills for clinical validation, HIPAA checks, and audit-trail queries.
- Starlette service surface with agent-card, health, and JSON-RPC endpoints.
- Audit-log persistence and restoration for forensic review.
- Optional Anthropic and OpenAI reasoning layers on top of deterministic checks.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `CLINICALGUARD_API_KEY` | unset | Optional `X-API-Key` protection for request handling |
| `CLINICALGUARD_URL` | unset | Optional published service URL for agent-card metadata |

## License

AGPL-3.0-or-later. Commercial licensing is available; contact `hello@acgs.ai`.

## Links

- [Homepage](https://acgs.ai)
- [Documentation](https://github.com/acgs2_admin/acgs/tree/main/packages/clinicalguard)
- [PyPI](https://pypi.org/project/clinicalguard/)
- [Repository](https://github.com/acgs2_admin/acgs)
- [Issues](https://github.com/acgs2_admin/acgs/issues)
- [Changelog](https://github.com/acgs2_admin/acgs/releases)

Constitutional Hash: `608508a9bd224290`
