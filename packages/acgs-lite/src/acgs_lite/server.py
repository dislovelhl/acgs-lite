"""FastAPI microservice wrapper for GovernanceEngine."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from acgs_lite.constitution import Constitution
from acgs_lite.engine import GovernanceEngine

if TYPE_CHECKING:
    from fastapi import FastAPI


def create_governance_app(constitution: Constitution | None = None) -> FastAPI:
    """Create a FastAPI app exposing governance validation endpoints."""
    from fastapi import FastAPI, HTTPException

    gov_constitution = constitution if constitution is not None else Constitution.default()
    engine = GovernanceEngine(gov_constitution, strict=False)
    app = FastAPI(title="acgs-lite-governance", version="0.1.0")

    @app.post("/validate")  # type: ignore[untyped-decorator]
    def validate_action(payload: dict[str, Any]) -> dict[str, Any]:
        action = cast(str, payload.get("action", ""))
        if not action.strip():
            raise HTTPException(status_code=422, detail="'action' must be a non-empty string")

        agent_id = payload.get("agent_id", "anonymous")
        if not isinstance(agent_id, str):
            raise HTTPException(status_code=422, detail="'agent_id' must be a string")

        context = payload.get("context", {})
        if not isinstance(context, dict):
            raise HTTPException(status_code=422, detail="'context' must be an object")

        result = engine.validate(
            action,
            agent_id=agent_id,
            context=cast(dict[str, Any], context),
        )
        return cast(dict[str, Any], result.to_dict())

    @app.get("/stats")  # type: ignore[untyped-decorator]
    def get_stats() -> dict[str, Any]:
        return cast(dict[str, Any], engine.stats)

    return app
