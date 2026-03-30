"""ACGS-Auth0: Constitutional Token Governance — Web Demo

FastAPI application demonstrating constitutional token governance.
Deployable to Railway, Render, Hugging Face Spaces, or any Python host.

Endpoints:
  GET  /                  — Dashboard UI
  GET  /api/policy        — Constitutional policy overview
  POST /api/check         — Validate a token request (governance gate only)
  GET  /api/audit         — Session audit trail
  POST /api/simulate      — Full simulation (grant / deny / step-up)

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure acgs_auth0 is importable when run from examples/
_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_ROOT / "packages"))

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from acgs_auth0 import MACIScopePolicy
from acgs_auth0.audit import TokenAuditLog
from acgs_auth0.token_vault import ConstitutionalTokenVault, TokenVaultRequest

# ── Constitution & vault ─────────────────────────────────────────────────────

CONSTITUTION_PATH = Path(__file__).parent.parent / "governed_agents" / "constitutions" / "default.yaml"
policy = MACIScopePolicy.from_yaml(CONSTITUTION_PATH)
audit_log = TokenAuditLog()
vault = ConstitutionalTokenVault(policy=policy, audit_log=audit_log)

# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="ACGS-Auth0: Constitutional Token Governance",
    description="Live demo — constitutional MACI governance over Auth0 Token Vault",
    version="0.1.0",
)

# Mount static files
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# ── Request/response models ───────────────────────────────────────────────────


class CheckRequest(BaseModel):
    agent_id: str = "planner"
    role: str = "EXECUTIVE"
    connection: str = "github"
    scopes: list[str] = ["read:user", "repo:read"]


class CheckResponse(BaseModel):
    permitted: bool
    role: str
    connection: str
    requested_scopes: list[str]
    permitted_scopes: list[str]
    denied_scopes: list[str]
    step_up_required: list[str]
    outcome: str
    message: str
    constitutional_hash: str


class SimulateRequest(BaseModel):
    scenario: str = "grant"  # "grant" | "deny" | "step-up" | "role-blocked"


# ── Routes ────────────────────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
async def dashboard() -> HTMLResponse:
    """Serve the governance dashboard UI."""
    html_path = Path(__file__).parent / "static" / "index.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text())
    return HTMLResponse(content=_inline_dashboard())


@app.get("/api/policy")
async def get_policy() -> dict:
    """Return the constitutional policy overview."""
    connections: dict = {}
    for (conn, role), rule in policy._rules.items():  # noqa: SLF001
        if conn not in connections:
            connections[conn] = {}
        connections[conn][role] = {
            "permitted_scopes": rule.permitted_scopes,
            "high_risk_scopes": rule.high_risk_scopes,
        }
    return {
        "constitutional_hash": policy.constitutional_hash,
        "connections": connections,
        "maci_golden_rule": "JUDICIAL role intentionally absent from all connections — validators never access external APIs",
    }


@app.post("/api/check", response_model=CheckResponse)
async def check_governance(req: CheckRequest) -> CheckResponse:
    """Validate a token request against the constitutional policy."""
    result = vault.validate(
        TokenVaultRequest(
            agent_id=req.agent_id,
            role=req.role,
            connection=req.connection,
            scopes=req.scopes,
            refresh_token="validation_only",
        )
    )

    if not result.permitted:
        outcome = "denied_role_not_permitted" if not result.permitted_scopes else "denied_scope_violation"
        audit_log.record_denied(
            agent_id=req.agent_id,
            role=req.role,
            connection=req.connection,
            scopes=req.scopes,
            reason="role_not_permitted" if not result.permitted_scopes else "scope_violation",
            error_message=str(result.error),
        )
        return CheckResponse(
            permitted=False,
            role=req.role,
            connection=req.connection,
            requested_scopes=req.scopes,
            permitted_scopes=result.permitted_scopes,
            denied_scopes=result.denied_scopes,
            step_up_required=[],
            outcome=outcome,
            message=str(result.error),
            constitutional_hash=policy.constitutional_hash,
        )

    if result.step_up_required:
        audit_log.record_step_up_initiated(
            agent_id=req.agent_id,
            role=req.role,
            connection=req.connection,
            scopes=result.step_up_required,
            binding_message=f"{req.agent_id} ({req.role}) requests {req.connection} write access. Approve?",
        )
        return CheckResponse(
            permitted=True,
            role=req.role,
            connection=req.connection,
            requested_scopes=req.scopes,
            permitted_scopes=result.permitted_scopes,
            denied_scopes=[],
            step_up_required=result.step_up_required,
            outcome="step_up_required",
            message=f"CIBA step-up required for: {result.step_up_required}. Push notification sent to user.",
            constitutional_hash=policy.constitutional_hash,
        )

    audit_log.record_granted(
        agent_id=req.agent_id,
        role=req.role,
        connection=req.connection,
        scopes=req.scopes,
    )
    return CheckResponse(
        permitted=True,
        role=req.role,
        connection=req.connection,
        requested_scopes=req.scopes,
        permitted_scopes=result.permitted_scopes,
        denied_scopes=[],
        step_up_required=[],
        outcome="granted",
        message="Constitutional gate passed. Token Vault exchange would proceed.",
        constitutional_hash=policy.constitutional_hash,
    )


@app.get("/api/audit")
async def get_audit() -> dict:
    """Return the session audit trail."""
    entries = audit_log.get_entries()
    return {
        "total": len(entries),
        "constitutional_hash": policy.constitutional_hash,
        "entries": [e.to_dict() for e in entries],
    }


@app.post("/api/simulate")
async def simulate(req: SimulateRequest) -> CheckResponse:
    """Run a preset simulation scenario."""
    scenarios = {
        "grant": CheckRequest(
            agent_id="planner", role="EXECUTIVE", connection="github",
            scopes=["read:user", "repo:read"],
        ),
        "deny": CheckRequest(
            agent_id="planner", role="EXECUTIVE", connection="github",
            scopes=["repo:write"],
        ),
        "step-up": CheckRequest(
            agent_id="executor", role="IMPLEMENTER", connection="github",
            scopes=["repo:read", "repo:write"],
        ),
        "role-blocked": CheckRequest(
            agent_id="validator", role="JUDICIAL", connection="github",
            scopes=["read:user"],
        ),
        "calendar-read": CheckRequest(
            agent_id="planner", role="EXECUTIVE", connection="google-oauth2",
            scopes=["openid", "https://www.googleapis.com/auth/calendar.freebusy"],
        ),
        "calendar-write": CheckRequest(
            agent_id="executor", role="IMPLEMENTER", connection="google-oauth2",
            scopes=["https://www.googleapis.com/auth/calendar"],
        ),
    }
    scenario_req = scenarios.get(req.scenario)
    if not scenario_req:
        raise HTTPException(status_code=400, detail=f"Unknown scenario: {req.scenario}. Valid: {list(scenarios)}")
    return await check_governance(scenario_req)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "constitutional_hash": policy.constitutional_hash}


# ── Inline fallback dashboard ─────────────────────────────────────────────────


def _inline_dashboard() -> str:
    """Fallback inline HTML if static/index.html is missing."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ACGS-Auth0: Constitutional Token Governance</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: #0f1117; color: #e2e8f0; min-height: 100vh; padding: 2rem; }
  .container { max-width: 900px; margin: 0 auto; }
  h1 { font-size: 1.5rem; font-weight: 700; color: #fff; margin-bottom: 0.25rem; }
  .subtitle { color: #64748b; font-size: 0.875rem; margin-bottom: 2rem; }
  .hash { font-family: monospace; font-size: 0.75rem; color: #22d3ee;
          background: #0f172a; padding: 0.2em 0.5em; border-radius: 4px; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; margin-bottom: 2rem; }
  .card { background: #1e2130; border: 1px solid #2d3748; border-radius: 8px; padding: 1.5rem; }
  .card h2 { font-size: 1rem; font-weight: 600; margin-bottom: 1rem; color: #93c5fd; }
  .scenario-btn { display: block; width: 100%; margin-bottom: 0.5rem; padding: 0.6rem 1rem;
                  border-radius: 6px; border: 1px solid #2d3748; background: #0f172a;
                  color: #e2e8f0; cursor: pointer; text-align: left; font-size: 0.875rem;
                  transition: all 0.15s; }
  .scenario-btn:hover { background: #1e40af; border-color: #3b82f6; }
  .result { background: #0f172a; border-radius: 6px; padding: 1rem; min-height: 120px;
            font-family: monospace; font-size: 0.8rem; white-space: pre-wrap; }
  .granted { color: #4ade80; }
  .denied { color: #f87171; }
  .stepup { color: #fbbf24; }
  .audit-list { max-height: 200px; overflow-y: auto; font-family: monospace;
                font-size: 0.75rem; }
  .audit-entry { padding: 0.3rem 0; border-bottom: 1px solid #1e2130; }
  .tag { display: inline-block; padding: 0.1em 0.4em; border-radius: 3px;
         font-size: 0.7rem; font-weight: 600; margin-right: 0.3rem; }
  .tag-granted { background: #064e3b; color: #4ade80; }
  .tag-denied { background: #7f1d1d; color: #f87171; }
  .tag-stepup { background: #78350f; color: #fbbf24; }
  @media (max-width: 600px) { .grid { grid-template-columns: 1fr; } }
</style>
</head>
<body>
<div class="container">
  <h1>ACGS-Auth0 <span style="color:#64748b;font-weight:400">Constitutional Token Governance</span></h1>
  <p class="subtitle">
    Constitutional Hash: <span class="hash">608508a9bd224290</span> &nbsp;|&nbsp;
    Auth0 "Authorized to Act" Hackathon 2026
  </p>

  <div class="grid">
    <div class="card">
      <h2>Run a Scenario</h2>
      <button class="scenario-btn" onclick="run('grant')">✅ Grant — EXECUTIVE reads GitHub</button>
      <button class="scenario-btn" onclick="run('deny')">🚫 Deny — EXECUTIVE tries to write GitHub</button>
      <button class="scenario-btn" onclick="run('role-blocked')">🔒 Role blocked — JUDICIAL accesses GitHub</button>
      <button class="scenario-btn" onclick="run('step-up')">⚠️ Step-up — IMPLEMENTER writes GitHub (CIBA)</button>
      <button class="scenario-btn" onclick="run('calendar-read')">📅 Grant — EXECUTIVE reads Calendar</button>
      <button class="scenario-btn" onclick="run('calendar-write')">📅 Step-up — IMPLEMENTER writes Calendar (CIBA)</button>
    </div>

    <div class="card">
      <h2>Result</h2>
      <div class="result" id="result">Click a scenario to see the constitutional gate in action.</div>
    </div>
  </div>

  <div class="grid">
    <div class="card">
      <h2>Audit Trail</h2>
      <div class="audit-list" id="audit">Loading...</div>
    </div>
    <div class="card">
      <h2>Constitutional Policy</h2>
      <div class="result" id="policy" style="max-height:200px;overflow-y:auto;">Loading...</div>
    </div>
  </div>
</div>

<script>
async function run(scenario) {
  const resultEl = document.getElementById('result');
  resultEl.textContent = 'Running...';
  try {
    const r = await fetch('/api/simulate', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({scenario})
    });
    const data = await r.json();
    const cls = data.outcome === 'granted' ? 'granted' : data.outcome === 'step_up_required' ? 'stepup' : 'denied';
    resultEl.className = 'result ' + cls;
    resultEl.textContent = JSON.stringify(data, null, 2);
    loadAudit();
  } catch(e) { resultEl.textContent = 'Error: ' + e.message; }
}

async function loadAudit() {
  const el = document.getElementById('audit');
  try {
    const r = await fetch('/api/audit');
    const data = await r.json();
    if (!data.entries.length) { el.innerHTML = '<em style="color:#64748b">No activity yet</em>'; return; }
    el.innerHTML = data.entries.slice(-10).reverse().map(e => {
      const tag = e.outcome.startsWith('granted') ? 'granted' : e.outcome.includes('step_up') ? 'stepup' : 'denied';
      return `<div class="audit-entry"><span class="tag tag-${tag}">${e.outcome}</span>${e.agent_id} (${e.role}) → ${e.connection}</div>`;
    }).join('');
  } catch(e) { el.textContent = 'Error loading audit'; }
}

async function loadPolicy() {
  const el = document.getElementById('policy');
  try {
    const r = await fetch('/api/policy');
    const data = await r.json();
    el.textContent = JSON.stringify(data, null, 2);
  } catch(e) { el.textContent = 'Error loading policy'; }
}

loadAudit(); loadPolicy();
setInterval(loadAudit, 5000);
</script>
</body>
</html>"""


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)
