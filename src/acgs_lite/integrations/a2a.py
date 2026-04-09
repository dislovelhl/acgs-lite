"""ACGS-Lite A2A (Agent-to-Agent) Integration.

Enables any acgs-lite governed agent to communicate with external agents
via Google's Agent-to-Agent protocol, and exposes governance as an A2A service.

Two modes:
1. GovernanceA2AServer: Expose your constitution as an A2A-compatible agent
2. A2AGovernedClient: Validate actions via a remote governance agent

Usage::

    # Server mode — expose governance as A2A
    from acgs_lite.integrations.a2a import GovernanceA2AServer

    server = GovernanceA2AServer(constitution=my_rules)
    server.run(port=9000)

    # Client mode — call remote governance agent
    from acgs_lite.integrations.a2a import A2AGovernedClient

    client = A2AGovernedClient("http://governance-agent:9000")
    result = await client.validate("deploy to production")

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import uuid
from typing import Any

from acgs_lite.audit import AuditLog
from acgs_lite.constitution import Constitution
from acgs_lite.engine import GovernanceEngine

try:
    import httpx

    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False


class A2AGovernedClient:
    """Client that validates actions via a remote A2A governance agent.

    Usage::

        client = A2AGovernedClient("http://localhost:9000")
        card = await client.get_agent_card()
        result = await client.validate("deploy to production")
    """

    def __init__(
        self,
        agent_url: str,
        *,
        timeout: float = 30.0,
    ) -> None:
        if not HTTPX_AVAILABLE:
            raise ImportError("httpx is required for A2A. Install with: pip install acgs-lite[a2a]")
        self.agent_url = agent_url.rstrip("/")
        self.timeout = timeout

    async def get_agent_card(self) -> dict[str, Any]:
        """Fetch the remote agent's capability card."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(f"{self.agent_url}/.well-known/agent.json")
            resp.raise_for_status()
            result: dict[str, Any] = resp.json()
            return result

    async def validate(
        self,
        action: str,
        *,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        """Send a validation request to the remote governance agent."""
        payload = {
            "jsonrpc": "2.0",
            "method": "tasks/send",
            "id": str(uuid.uuid4())[:8],
            "params": {
                "id": task_id or f"task-{uuid.uuid4().hex[:8]}",
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": f"Validate: {action}"}],
                },
            },
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                self.agent_url,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()

        result: dict[str, Any] = data.get("result", {})
        return dict(result.get("result", result))

    async def send_task(
        self,
        message: str,
        *,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        """Send an arbitrary task to the remote agent."""
        payload = {
            "jsonrpc": "2.0",
            "method": "tasks/send",
            "id": str(uuid.uuid4())[:8],
            "params": {
                "id": task_id or f"task-{uuid.uuid4().hex[:8]}",
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": message}],
                },
            },
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(self.agent_url, json=payload)
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()

        return dict(data.get("result", data))


def create_a2a_app(
    constitution: Constitution | None = None,
    *,
    agent_id: str = "acgs-governance",
    port: int = 9000,
) -> Any:
    """Create a FastAPI app that serves governance as an A2A agent.

    Usage::

        from acgs_lite.integrations.a2a import create_a2a_app
        from acgs_lite import Constitution

        app = create_a2a_app(Constitution.from_yaml("rules.yaml"))
        # Run with: uvicorn app:app --port 9000

    Returns:
        FastAPI application instance.
    """
    try:
        from starlette.applications import Starlette
        from starlette.requests import Request as StarletteRequest
        from starlette.responses import JSONResponse as StarletteJSONResponse
        from starlette.routing import Route
    except ImportError as e:
        raise ImportError(
            "starlette is required for A2A server. Install with: pip install starlette uvicorn"
        ) from e

    constitution = constitution or Constitution.default()
    audit_log = AuditLog()
    engine = GovernanceEngine(constitution, audit_log=audit_log, strict=False, audit_mode="full")

    a2a_agent_card = {
        "name": f"ACGS Governance Agent ({constitution.name})",
        "description": (
            "Constitutional AI governance agent. Validates agent actions "
            "against constitutional rules with audit trails and MACI enforcement."
        ),
        "url": f"http://localhost:{port}",
        "version": "0.1.0",
        "capabilities": ["streaming"],
        "skills": [
            {
                "name": "validate_action",
                "description": "Validate an agent action against constitutional rules",
            },
            {
                "name": "audit_trail",
                "description": "Get the audit trail for governance decisions",
            },
            {
                "name": "governance_status",
                "description": "Get constitution status, rules, and statistics",
            },
        ],
        "defaultInputModes": ["text/plain"],
        "defaultOutputModes": ["text/plain", "application/json"],
    }

    async def get_agent_card_handler(request: StarletteRequest) -> StarletteJSONResponse:
        return StarletteJSONResponse(a2a_agent_card)

    async def handle_a2a(request: StarletteRequest) -> StarletteJSONResponse:
        body: dict[str, Any] = await request.json()

        if body.get("method") == "tasks/send":
            params = body.get("params", {})
            message = params.get("message", {})
            parts = message.get("parts", [])
            text = parts[0].get("text", "") if parts else ""

            text_lower = text.lower()

            if "audit" in text_lower:
                result_data: dict[str, Any] = {
                    "audit_log": audit_log.export_dicts()[-20:],
                    "total_entries": len(audit_log),
                    "chain_valid": audit_log.verify_chain(),
                }
            elif "status" in text_lower or "rules" in text_lower:
                result_data = {
                    "constitution_name": constitution.name,
                    "constitutional_hash": constitution.hash,
                    "constitutional_hash_versioned": constitution.hash_versioned,
                    "rules_count": len(constitution.rules),
                    "rules": [
                        {"id": r.id, "text": r.text, "severity": r.severity.value}
                        for r in constitution.rules
                    ],
                    "stats": engine.stats,
                }
            else:
                # Default: validate
                validation = engine.validate(text, agent_id=agent_id)
                result_data = validation.to_dict()

            return StarletteJSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": body.get("id"),
                    "result": {
                        "id": params.get("id", str(uuid.uuid4())),
                        "status": "completed",
                        "result": result_data,
                    },
                }
            )

        return StarletteJSONResponse(
            {
                "jsonrpc": "2.0",
                "id": body.get("id"),
                "error": {
                    "code": -32601,
                    "message": f"Unknown method: {body.get('method')}",
                },
            }
        )

    app = Starlette(
        routes=[
            Route("/.well-known/agent.json", get_agent_card_handler, methods=["GET"]),
            Route("/", handle_a2a, methods=["POST"]),
        ],
    )

    return app
