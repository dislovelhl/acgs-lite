# ACGS - Constitutional AI Governance
# Copyright (C) 2024-2026 ACGS Contributors
# Licensed under AGPL-3.0-or-later. See LICENSE for details.
# Commercial license: https://acgs.ai

"""FastAPI microservice wrapper for GovernanceEngine."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from acgs_lite._meta import VERSION
from acgs_lite.audit import AuditLog
from acgs_lite.constitution import Constitution
from acgs_lite.engine import GovernanceEngine
from acgs_lite.integrations.openshell_governance import (
    GovernanceStateBackend,
    GovernanceStateObservabilityHook,
    JsonFileGovernanceStateBackend,
    create_openshell_governance_router,
)

if TYPE_CHECKING:
    from fastapi import FastAPI


def create_governance_app(
    constitution: Constitution | None = None,
    *,
    include_openshell_governance: bool = True,
    include_openshell_experimental: bool | None = None,
    openshell_observability_hook: GovernanceStateObservabilityHook | None = None,
    openshell_state_backend: GovernanceStateBackend | None = None,
    openshell_state_path: str | Path | None = None,
) -> FastAPI:
    """Create a FastAPI app exposing governance validation endpoints.

    When ``include_openshell_governance`` is true, the app also mounts the
    stable OpenShell/OpenClaw governance router under ``/governance``.

    ``include_openshell_experimental`` is kept as a compatibility alias.
    """
    from fastapi import FastAPI, HTTPException

    gov_constitution = constitution if constitution is not None else Constitution.default()
    audit_log = AuditLog()
    engine = GovernanceEngine(gov_constitution, audit_log=audit_log, strict=False, audit_mode="full")
    app = FastAPI(title="acgs-lite-governance", version=VERSION)

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
            context=context,
        )
        return result.to_dict()

    @app.get("/health")  # type: ignore[untyped-decorator]
    def health_check() -> dict[str, str]:
        return {"status": "ok", "engine": "ready"}

    @app.get("/stats")  # type: ignore[untyped-decorator]
    def get_stats() -> dict[str, Any]:
        return {
            **engine.stats,
            "audit_entry_count": len(audit_log),
            "audit_chain_valid": audit_log.verify_chain(),
        }

    if include_openshell_experimental is not None:
        include_openshell_governance = include_openshell_experimental

    if include_openshell_governance:
        state_backend = openshell_state_backend
        if state_backend is None and openshell_state_path is not None:
            state_backend = JsonFileGovernanceStateBackend(openshell_state_path)
        app.include_router(
            create_openshell_governance_router(
                audit_log=audit_log,
                observability_hook=openshell_observability_hook,
                state_backend=state_backend,
            )
        )

    return app
