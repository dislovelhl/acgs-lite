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

    # --- Rules CRUD ---

    @app.get("/rules")  # type: ignore[untyped-decorator]
    def list_rules() -> list[dict[str, Any]]:
        return [
            {
                "id": r.id,
                "text": r.text,
                "severity": r.severity.value,
                "keywords": r.keywords,
                "patterns": r.patterns,
                "category": r.category,
                "subcategory": r.subcategory,
                "workflow_action": r.workflow_action,
                "enabled": r.enabled,
                "tags": r.tags,
                "priority": r.priority,
            }
            for r in gov_constitution.rules
        ]

    @app.get("/rules/{rule_id}")  # type: ignore[untyped-decorator]
    def get_rule(rule_id: str) -> dict[str, Any]:
        for r in gov_constitution.rules:
            if r.id == rule_id:
                return r.model_dump()
        raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found")

    @app.post("/rules", status_code=201)  # type: ignore[untyped-decorator]
    def create_rule(payload: dict[str, Any]) -> dict[str, Any]:
        from acgs_lite.constitution import Rule, Severity

        rule_id = payload.get("id", "")
        if not rule_id or not isinstance(rule_id, str):
            raise HTTPException(status_code=422, detail="'id' is required and must be a string")

        if any(r.id == rule_id for r in gov_constitution.rules):
            raise HTTPException(status_code=409, detail=f"Rule '{rule_id}' already exists")

        try:
            rule = Rule(
                id=rule_id,
                text=payload.get("text", ""),
                severity=Severity(payload.get("severity", "medium")),
                keywords=payload.get("keywords", []),
                patterns=payload.get("patterns", []),
                category=payload.get("category", "custom"),
                subcategory=payload.get("subcategory", ""),
                workflow_action=payload.get("workflow_action", "warn"),
                tags=payload.get("tags", []),
                priority=payload.get("priority", 50),
            )
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        gov_constitution.add_rule(rule)
        _rebuild_engine()
        return rule.model_dump()

    @app.put("/rules/{rule_id}")  # type: ignore[untyped-decorator]
    def update_rule(rule_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        from acgs_lite.constitution import Rule, Severity

        existing = None
        for r in gov_constitution.rules:
            if r.id == rule_id:
                existing = r
                break
        if existing is None:
            raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found")

        try:
            updated = Rule(
                id=rule_id,
                text=payload.get("text", existing.text),
                severity=Severity(payload.get("severity", existing.severity.value)),
                keywords=payload.get("keywords", existing.keywords),
                patterns=payload.get("patterns", existing.patterns),
                category=payload.get("category", existing.category),
                subcategory=payload.get("subcategory", existing.subcategory),
                workflow_action=payload.get("workflow_action", existing.workflow_action),
                tags=payload.get("tags", existing.tags),
                priority=payload.get("priority", existing.priority),
                enabled=payload.get("enabled", existing.enabled),
            )
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        gov_constitution.replace_rule(rule_id, updated)
        _rebuild_engine()
        return updated.model_dump()

    @app.delete("/rules/{rule_id}", status_code=204)  # type: ignore[untyped-decorator]
    def delete_rule(rule_id: str) -> None:
        if not any(r.id == rule_id for r in gov_constitution.rules):
            raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found")
        gov_constitution.remove_rule(rule_id)
        _rebuild_engine()

    def _rebuild_engine() -> None:
        """Rebuild engine internals after rule changes."""
        nonlocal engine
        engine = GovernanceEngine(gov_constitution, audit_log=audit_log, strict=False, audit_mode="full")

    # --- Audit Trail ---

    @app.get("/audit/entries")  # type: ignore[untyped-decorator]
    def list_audit_entries(
        limit: int = 100,
        offset: int = 0,
        agent_id: str | None = None,
    ) -> list[dict[str, Any]]:
        entries = audit_log.entries
        if agent_id is not None:
            entries = [e for e in entries if e.agent_id == agent_id]
        page = entries[offset : offset + limit]
        return [
            {
                "id": e.id,
                "type": e.type,
                "agent_id": e.agent_id,
                "action": e.action,
                "valid": e.valid,
                "violations": e.violations,
                "timestamp": e.timestamp,
            }
            for e in page
        ]

    @app.get("/audit/chain")  # type: ignore[untyped-decorator]
    def audit_chain_status() -> dict[str, Any]:
        return {
            "valid": audit_log.verify_chain(),
            "entry_count": len(audit_log),
        }

    @app.get("/audit/count")  # type: ignore[untyped-decorator]
    def audit_count() -> dict[str, int]:
        return {"count": len(audit_log)}

    # --- Health & Stats ---

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
