# CLI Reference

The CLI is available as both `acgs` (preferred) and `acgs-lite` (compatibility alias).

## Commands

| Command | Description |
|---|---|
| `acgs init` | Scaffold `rules.yaml` + CI governance job |
| `acgs assess` | Run multi-framework compliance assessment |
| `acgs report` | Generate auditor-ready compliance report |
| `acgs eu-ai-act` | One-shot EU AI Act compliance + PDF |
| `acgs lint` | Lint governance rules for quality issues |
| `acgs test` | Run governance test fixtures |
| `acgs lifecycle` | Manage policy promotion lifecycle |
| `acgs refusal` | Explain governance denials + suggest alternatives |
| `acgs observe` | Export governance telemetry / Prometheus |
| `acgs otel` | Export OpenTelemetry-compatible telemetry |
| `acgs activate` | Store a license key |
| `acgs status` | Show current license tier and features |
| `acgs verify` | Validate license key integrity |

## Usage Examples

```bash
# Scaffold a new project
acgs init

# Compliance
acgs assess --jurisdiction european_union --domain healthcare
acgs report --markdown
acgs report --pdf
acgs eu-ai-act --domain healthcare

# Rule quality
acgs lint rules.yaml
acgs test --fixtures tests.yaml

# Policy lifecycle
acgs lifecycle summary

# Observability
acgs observe "approve deployment" --prometheus
acgs otel --endpoint http://localhost:4317

# Licensing
acgs activate ACGS-PRO-XXXX-XXXX
acgs status
acgs verify

# Governance denial explanation
acgs refusal --last
```

!!! info "Constitutional Hash"
    `608508a9bd224290` is the documented constitutional hash for this release line. `acgs verify` currently validates license key integrity only.
