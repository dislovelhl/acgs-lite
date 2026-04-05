# ClinicalGuard Deployment Guide

## Quick Start (Local)

```bash
cd packages/clinicalguard
pip install -e ../acgs-lite
pip install starlette "uvicorn[standard]" pyyaml anthropic httpx pydantic
uvicorn clinicalguard.main:app --host 0.0.0.0 --port 8080
```

Health check: `curl http://localhost:8080/health`

## Docker

```bash
# From repo root
docker build -f packages/clinicalguard/Dockerfile -t clinicalguard .
docker run -p 8080:8080 \
  -v clinicalguard_data:/data \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  -e CLINICALGUARD_API_KEY=your-secret-key \
  clinicalguard
```

## Fly.io (Production)

```bash
# One-time setup
fly launch --config deploy/fly.toml --no-deploy
fly secrets set ANTHROPIC_API_KEY=sk-ant-...
fly secrets set CLINICALGUARD_API_KEY=your-secret-key
fly volumes create clinicalguard_data --region ord --size 1

# Deploy
fly deploy --config deploy/fly.toml
```

Live: https://clinicalguard.fly.dev

## Environment Variables

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `ANTHROPIC_API_KEY` | For LLM layer | — | Claude API key for clinical reasoning |
| `CLINICALGUARD_API_KEY` | Recommended | — | API key for request authentication |
| `CLINICALGUARD_AUDIT_LOG` | No | `/data/clinicalguard_audit.json` | Audit log file path |
| `CLINICALGUARD_MODEL` | No | `claude-haiku-4-5` | LLM model for clinical reasoning |
| `CLINICALGUARD_URL` | No | — | Public URL for agent card registration |
| `PORT` | No | `8080` | HTTP listen port |

## Security

- **Non-root container**: runs as `clinicalguard` user
- **Persistent audit**: `/data` volume for tamper-evident logs
- **Input limits**: 64KB request body, 10K char action text
- **Unicode normalization**: NFKC + zero-width/bidi stripping
- **Error sanitization**: no exception details leaked to clients
- **API key auth**: constant-time comparison when `CLINICALGUARD_API_KEY` is set

## Monitoring

Health endpoint returns:
```json
{
  "status": "ok",
  "rules": 20,
  "audit_entries": 142,
  "chain_valid": true,
  "constitutional_hash": "608508a9bd224290"
}
```

Monitor `chain_valid` — if false, the audit trail has been tampered with.

## CI/CD

GitHub Actions workflow at `.github/workflows/deploy-clinicalguard.yml`:
1. Runs full test suite (104 tests)
2. Deploys to Fly.io staging
3. Runs health check against live endpoint

Requires `FLY_API_TOKEN` secret in GitHub repo settings.
