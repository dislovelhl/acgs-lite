---
name: hackathon-cloud-run
description: Cloud Run server endpoints — /health, /webhook, /governance/summary — and Cloud Logging export
type: capability + regression
target: pass@3 > 90% capability, pass^3 = 100% regression
---

## EVAL: hackathon-cloud-run

### Context
`acgs_lite.integrations.cloud_run_server` is the deployable service for Google Cloud Run.
This is what registers as an External Agent in GitLab and receives MR webhook events.

---

### Capability Evals

#### CAP-CR-01: /health returns constitutional hash and rules count
```bash
python -c "
import asyncio
from starlette.testclient import TestClient
from acgs_lite.integrations.cloud_run_server import app

client = TestClient(app)
r = client.get('/health')
assert r.status_code == 200
data = r.json()
assert data['status'] == 'healthy'
assert data['constitutional_hash'] == '608508a9bd224290'
assert data['rules_loaded'] > 0
print(f'PASS — {data[\"rules_loaded\"]} rules loaded')
" && echo "PASS" || echo "FAIL: ensure starlette installed: pip install starlette httpx"
```

#### CAP-CR-02: /governance/summary returns structured posture
```bash
python -c "
from starlette.testclient import TestClient
from acgs_lite.integrations.cloud_run_server import app

client = TestClient(app)
r = client.get('/governance/summary')
assert r.status_code == 200
data = r.json()
assert 'constitutional_hash' in data
assert 'summary' in data
assert data['constitutional_hash'] == '608508a9bd224290'
print('PASS')
" && echo "PASS" || echo "FAIL"
```

#### CAP-CR-03: /webhook returns 503 when credentials missing
```bash
python -c "
import os
# Ensure no credentials set
os.environ.pop('GITLAB_TOKEN', None)
os.environ.pop('GITLAB_PROJECT_ID', None)

from starlette.testclient import TestClient
# Reimport to pick up env state
import importlib
import acgs_lite.integrations.cloud_run_server as srv
importlib.reload(srv)

client = TestClient(srv.app)
r = client.post('/webhook', json={}, headers={'X-Gitlab-Token': 'any', 'X-Gitlab-Event': 'Merge Request Hook'})
# Either 503 (no credentials) or 401 (no valid token configured) is acceptable
assert r.status_code in (401, 503), f'Expected 401 or 503, got {r.status_code}'
print(f'PASS — status {r.status_code} (no credentials)')
" && echo "PASS" || echo "FAIL"
```

#### CAP-CR-04: App has exactly 3 routes
```bash
python -c "
from acgs_lite.integrations.cloud_run_server import app
routes = [str(r.path) for r in app.routes]
expected = {'/webhook', '/health', '/governance/summary'}
actual = set(routes)
assert expected == actual, f'Route mismatch: expected {expected}, got {actual}'
print('PASS')
" && echo "PASS" || echo "FAIL"
```

#### CAP-CR-05: Cloud Logging exporter optional — server starts without GCP credentials
```bash
python -c "
# Should not raise even without GCP credentials
from acgs_lite.integrations.cloud_run_server import app, _cloud_exporter
# _cloud_exporter may be None if google-cloud-logging not installed — that is OK
print(f'PASS — cloud_exporter: {type(_cloud_exporter).__name__}')
" && echo "PASS" || echo "FAIL"
```

---

### Deployment Evals (manual / `[HUMAN REVIEW REQUIRED]`)

#### CAP-CR-06: Cloud Run health check responds within 2s
```
[HUMAN REVIEW REQUIRED] Risk: MEDIUM
After `gcloud run deploy`, curl https://<service-url>/health
Expected: status=200, constitutional_hash=608508a9bd224290, latency < 2000ms
Command: time curl -s https://<cloud-run-url>/health | python -m json.tool
```

#### CAP-CR-07: Webhook registered in GitLab points to Cloud Run URL
```
[HUMAN REVIEW REQUIRED] Risk: LOW
In GitLab project Settings > Webhooks, verify:
  URL: https://<cloud-run-url>/webhook
  Events: Merge request events ✓
  SSL verification: ✓
  Secret token: matches GITLAB_WEBHOOK_SECRET env var
```

---

### Regression Evals (pass^3 = 100% required)

#### REG-CR-01: Cloud Run server module importable
```bash
python -c "from acgs_lite.integrations.cloud_run_server import app, health_endpoint, webhook_endpoint, governance_summary_endpoint; print('PASS')" && echo "PASS" || echo "FAIL"
```

#### REG-CR-02: /health status is always 'healthy'
```bash
python -c "
from starlette.testclient import TestClient
from acgs_lite.integrations.cloud_run_server import app
client = TestClient(app)
for _ in range(3):
    r = client.get('/health')
    assert r.json()['status'] == 'healthy'
print('PASS — 3/3 healthy')
" && echo "PASS" || echo "FAIL"
```

---

### Grader Notes
- CAP-CR-01..05: code-based, no GCP credentials needed
- CAP-CR-06..07: manual post-deploy verification
- starlette + httpx required for TestClient: `pip install starlette httpx`
- Baseline: CAP-CR-01..05 established March 2026
