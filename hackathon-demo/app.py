"""Governed Agent Vault -- ACGS x Auth0 Token Vault Demo.

FastAPI app demonstrating constitutional governance over Token Vault.
The constitution decides which OAuth scopes an agent can access.
Tokens are NEVER issued if the constitution says no.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from acgs_auth0 import (
    ConstitutionalTokenVault,
    MACIScopePolicy,
    TokenAuditLog,
)
from acgs_auth0.token_vault import TokenVaultRequest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CONSTITUTION_PATH = Path(__file__).parent / "constitution.yaml"

app = FastAPI(
    title="Governed Agent Vault",
    description="Constitutional AI governance for Auth0 Token Vault",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Initialize governance engine
# ---------------------------------------------------------------------------

policy = MACIScopePolicy.from_yaml(str(CONSTITUTION_PATH))
audit_log = TokenAuditLog()
vault = ConstitutionalTokenVault(
    policy=policy,
    audit_log=audit_log,
    auth0_domain=os.getenv("AUTH0_DOMAIN", "demo.auth0.com"),
    auth0_client_id=os.getenv("AUTH0_CLIENT_ID", ""),
    auth0_client_secret=os.getenv("AUTH0_CLIENT_SECRET", ""),
)

# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class AgentActionRequest(BaseModel):
    agent_id: str = "demo-agent"
    role: str  # EXECUTIVE, JUDICIAL, IMPLEMENTER
    connection: str  # github, google-oauth2, slack
    scopes: list[str]
    action_description: str = ""


class GovernanceDecision(BaseModel):
    allowed: bool
    agent_id: str
    role: str
    connection: str
    requested_scopes: list[str]
    granted_scopes: list[str]
    denied_scopes: list[str]
    reason: str
    step_up_required: bool
    constitutional_hash: str
    timestamp: float


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the demo UI."""
    html_path = Path(__file__).parent / "static" / "index.html"
    return HTMLResponse(html_path.read_text())


@app.get("/api/constitution")
async def get_constitution():
    """Return the current constitutional policy."""
    return {
        "constitutional_hash": "608508a9bd224290",
        "connections": {
            conn: {
                role: {
                    "permitted_scopes": list(rule.permitted_scopes),
                    "high_risk_scopes": list(rule.high_risk_scopes),
                }
                for role, rule in roles.items()
            }
            for conn, roles in policy._rules.items()
        },
    }


@app.post("/api/validate", response_model=GovernanceDecision)
async def validate_action(req: AgentActionRequest):
    """Pre-flight constitutional validation -- no token exchange, just governance check."""
    request = TokenVaultRequest(
        agent_id=req.agent_id,
        role=req.role,
        connection=req.connection,
        scopes=req.scopes,
        refresh_token="",  # Not needed for validation-only
        user_id="demo-user",
        tool_name=req.action_description or f"{req.connection}:{','.join(req.scopes)}",
    )

    result = vault.validate(request)

    return GovernanceDecision(
        allowed=result.permitted,
        agent_id=req.agent_id,
        role=req.role,
        connection=req.connection,
        requested_scopes=req.scopes,
        granted_scopes=list(result.permitted_scopes),
        denied_scopes=list(result.denied_scopes),
        reason=str(result.error) if result.error else ("Step-up required" if result.step_up_required else "Permitted"),
        step_up_required=bool(result.step_up_required),
        constitutional_hash="608508a9bd224290",
        timestamp=time.time(),
    )


@app.post("/api/execute")
async def execute_action(req: AgentActionRequest):
    """Full governance check + simulated token exchange.

    In production, this would call Auth0 Token Vault. For the demo,
    we validate constitutionally and simulate the token response.
    """
    request = TokenVaultRequest(
        agent_id=req.agent_id,
        role=req.role,
        connection=req.connection,
        scopes=req.scopes,
        refresh_token="demo-refresh-token",  # noqa: S106
        user_id="demo-user|abc123",
        tool_name=req.action_description or f"{req.connection}:{','.join(req.scopes)}",
    )

    result = vault.validate(request)

    if not result.permitted:
        audit_log.record_denied(
            agent_id=req.agent_id, role=req.role, connection=req.connection,
            scopes=req.scopes, reason="constitutional_scope_violation",
            error_message=str(result.error) if result.error else "Denied by constitution",
            user_id="demo-user",
        )
        return JSONResponse(
            status_code=403,
            content={
                "allowed": False,
                "reason": str(result.error) if result.error else "Scope not permitted for this role",
                "denied_scopes": list(result.denied_scopes),
                "audit_entry": "logged",
                "constitutional_hash": "608508a9bd224290",
            },
        )

    if result.step_up_required:
        audit_log.record_step_up_initiated(
            agent_id=req.agent_id, role=req.role, connection=req.connection,
            scopes=req.scopes,
            binding_message=f"Approve high-risk scopes: {', '.join(result.step_up_required)}",
            user_id="demo-user",
        )
        return JSONResponse(
            status_code=202,
            content={
                "allowed": True,
                "step_up_required": True,
                "reason": "High-risk scopes require CIBA step-up approval",
                "high_risk_scopes": list(result.step_up_required),
                "constitutional_hash": "608508a9bd224290",
            },
        )

    # Simulate successful token exchange
    audit_log.record_granted(
        agent_id=req.agent_id, role=req.role, connection=req.connection,
        scopes=req.scopes, user_id="demo-user",
    )
    return {
        "allowed": True,
        "token_issued": True,
        "connection": req.connection,
        "granted_scopes": list(result.permitted_scopes),
        "simulated_token": f"tv_{req.connection}_{req.role.lower()}_{'_'.join(s.split(':')[0] for s in req.scopes[:2])}",
        "audit_entry": "logged",
        "constitutional_hash": "608508a9bd224290",
    }


@app.get("/api/audit")
async def get_audit_log():
    """Return the constitutional audit trail."""
    return {
        "entries": [
            {
                "agent_id": e.agent_id,
                "role": e.role,
                "connection": e.connection,
                "requested_scopes": list(e.requested_scopes),
                "granted_scopes": list(e.granted_scopes),
                "outcome": e.outcome,
                "constitutional_hash": e.constitutional_hash,
                "timestamp": e.timestamp,
            }
            for e in audit_log.get_entries()
        ],
        "total": len(audit_log.get_entries()),
    }


@app.get("/api/scenarios")
async def get_scenarios():
    """Return pre-built demo scenarios showing governance in action."""
    return [
        {
            "name": "Read GitHub repos (EXECUTIVE)",
            "description": "Executive agent reads repos -- ALLOWED by constitution",
            "request": {
                "agent_id": "exec-agent",
                "role": "EXECUTIVE",
                "connection": "github",
                "scopes": ["read:user", "repo"],
                "action_description": "List user repositories",
            },
            "expected": "ALLOWED",
        },
        {
            "name": "Delete GitHub repo (EXECUTIVE)",
            "description": "Executive agent tries to delete repos -- DENIED: scope not permitted for this role",
            "request": {
                "agent_id": "exec-agent",
                "role": "EXECUTIVE",
                "connection": "github",
                "scopes": ["delete_repo"],
                "action_description": "Delete repository",
            },
            "expected": "DENIED",
        },
        {
            "name": "Delete GitHub repo (IMPLEMENTER)",
            "description": "Implementer can delete repos -- but STEP-UP required (high-risk scope)",
            "request": {
                "agent_id": "impl-agent",
                "role": "IMPLEMENTER",
                "connection": "github",
                "scopes": ["delete_repo"],
                "action_description": "Delete repository",
            },
            "expected": "STEP-UP REQUIRED",
        },
        {
            "name": "Read Gmail (EXECUTIVE)",
            "description": "Executive agent reads Gmail -- ALLOWED",
            "request": {
                "agent_id": "exec-agent",
                "role": "EXECUTIVE",
                "connection": "google-oauth2",
                "scopes": ["openid", "https://www.googleapis.com/auth/gmail.readonly"],
                "action_description": "Read email inbox",
            },
            "expected": "ALLOWED",
        },
        {
            "name": "Send Gmail (JUDICIAL)",
            "description": "Judicial agent tries to send email -- DENIED: role lacks send scope",
            "request": {
                "agent_id": "judicial-agent",
                "role": "JUDICIAL",
                "connection": "google-oauth2",
                "scopes": ["https://www.googleapis.com/auth/gmail.send"],
                "action_description": "Send email on behalf of user",
            },
            "expected": "DENIED",
        },
        {
            "name": "Send Slack message (EXECUTIVE)",
            "description": "Executive writes to Slack -- STEP-UP required (chat:write is high-risk)",
            "request": {
                "agent_id": "exec-agent",
                "role": "EXECUTIVE",
                "connection": "slack",
                "scopes": ["channels:read", "chat:write"],
                "action_description": "Post status update to #general",
            },
            "expected": "STEP-UP REQUIRED",
        },
    ]


# ---------------------------------------------------------------------------
# Mount static files
# ---------------------------------------------------------------------------

static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
