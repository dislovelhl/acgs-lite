"""ClinicalGuard A2A Agent.

Custom Starlette dispatcher — NOT a wrapper around create_a2a_app().
create_a2a_app() has no extension point; this is a clean reimplementation
that reuses the ACGS components (GovernanceEngine, AuditLog, MACIEnforcer).

Skill dispatch: reads a "skill" field from the first message part, or falls
back to a keyword prefix in the text itself.

Supported skills:
  validate_clinical_action   — LLM + constitutional clinical validation
  check_hipaa_compliance     — HIPAA checklist against an agent description
  query_audit_trail          — Tamper-evident audit log query

Security: X-API-Key header required when CLINICALGUARD_API_KEY is set.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import json
import logging
import os
import unicodedata
import uuid
from pathlib import Path
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from acgs_lite.audit import AuditLog
from acgs_lite.constitution import Constitution
from acgs_lite.engine import GovernanceEngine

from .skills.audit_query import query_audit_trail
from .skills.hipaa_checker import check_hipaa_compliance
from .skills.validate_clinical import validate_clinical_action

logger = logging.getLogger(__name__)

CONSTITUTIONAL_HASH = "8494a847758c08dc"

# Security limits
MAX_REQUEST_BODY_BYTES = 64 * 1024  # 64 KB max request body
MAX_ACTION_TEXT_CHARS = 10_000  # 10K chars max clinical action text

# ──────────────────────────────────────────────────────────────────────────────
# Agent card (Prompt Opinion Marketplace registration)
# ──────────────────────────────────────────────────────────────────────────────

_AGENT_CARD: dict[str, Any] = {
    "name": "ClinicalGuard",
    "description": (
        "AI safety infrastructure for clinical decision support. "
        "Validates proposed clinical actions (medication orders, prior auth) against a "
        "20-rule Healthcare AI Constitution using LLM reasoning + deterministic "
        "constitutional enforcement (MACI separation of powers). "
        "Every decision is cryptographically logged in a tamper-evident audit trail."
    ),
    "version": "1.0.0",
    "url": os.environ.get("CLINICALGUARD_URL", "http://localhost:8080"),
    "capabilities": ["tasks"],
    "defaultInputModes": ["text/plain", "application/json"],
    "defaultOutputModes": ["application/json"],
    "skills": [
        {
            "id": "validate_clinical_action",
            "name": "Validate Clinical Action",
            "description": (
                "Validate a proposed clinical action (medication order, prior auth, "
                "care plan change) against the Healthcare AI Constitution. "
                "Returns: decision (APPROVED/CONDITIONALLY_APPROVED/REJECTED), "
                "risk_tier, reasoning, drug_interactions, conditions, audit_id."
            ),
            "inputModes": ["text/plain"],
            "outputModes": ["application/json"],
            "examples": [
                "validate_clinical_action: Patient SYNTH-042 on Warfarin. Propose Aspirin 325mg daily.",
                "validate_clinical_action: Prescribe Adalimumab 40mg Q2W for RA. No prior treatment documented.",
            ],
        },
        {
            "id": "check_hipaa_compliance",
            "name": "Check HIPAA Compliance",
            "description": (
                "Run a HIPAA compliance checklist against an AI agent system "
                "description. Returns: compliant bool, items_checked, checklist with "
                "status and MACI-mapped mitigations, constitutional_hash."
            ),
            "inputModes": ["text/plain"],
            "outputModes": ["application/json"],
            "examples": [
                "check_hipaa_compliance: This agent processes synthetic patient data, maintains an audit log...",
            ],
        },
        {
            "id": "query_audit_trail",
            "name": "Query Audit Trail",
            "description": (
                "Query the tamper-evident audit trail. "
                "Returns entries by audit_id or the most recent N entries. "
                "Includes chain_valid flag for integrity verification."
            ),
            "inputModes": ["text/plain"],
            "outputModes": ["application/json"],
            "examples": [
                "query_audit_trail: HC-20260401-A7F2B3",
                "query_audit_trail: recent 10",
            ],
        },
    ],
    "provider": {
        "organization": "ACGS Project",
        "url": "https://github.com/acgs-project/acgs-clean",
    },
    "securitySchemes": {
        "apiKey": {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
        }
    },
}


# ──────────────────────────────────────────────────────────────────────────────
# ClinicalGuardApp
# ──────────────────────────────────────────────────────────────────────────────


class ClinicalGuardApp:
    """Starlette-based A2A server for ClinicalGuard.

    Usage::

        app = ClinicalGuardApp.create()
        # Run with: uvicorn clinicalguard.agent:app_instance
    """

    def __init__(
        self,
        constitution: Constitution,
        audit_log: AuditLog,
        audit_log_path: Path | None = None,
    ) -> None:
        self.engine = GovernanceEngine(constitution, strict=False)
        # Wire custom healthcare validators (PHI-PHONE, PHI-DOB, etc.)
        from .skills.healthcare_validators import register_all

        register_all(self.engine)
        self.audit_log = audit_log
        self.audit_log_path = audit_log_path
        self._api_key = os.environ.get("CLINICALGUARD_API_KEY", "")

    @classmethod
    def create(
        cls,
        constitution_path: str | Path | None = None,
        audit_log_path: str | Path | None = None,
    ) -> ClinicalGuardApp:
        """Factory: load constitution from YAML, restore audit log from file."""
        if constitution_path is None:
            constitution_path = Path(__file__).parent / "constitution" / "healthcare_v1.yaml"

        constitution = Constitution.from_yaml(str(constitution_path))
        logger.info(
            "Loaded Healthcare AI Constitution: %d rules, hash=%s",
            len(constitution.rules),
            constitution.hash,
        )

        audit_log = AuditLog()

        # Restore persisted audit entries on startup
        if audit_log_path is not None:
            audit_log_path = Path(audit_log_path)
            if audit_log_path.exists():
                try:
                    _restore_audit_log(audit_log, audit_log_path)
                    logger.info("Restored %d audit entries from %s", len(audit_log), audit_log_path)
                except (OSError, ValueError, KeyError) as exc:
                    logger.warning("Could not restore audit log: %s", exc)

        return cls(constitution=constitution, audit_log=audit_log, audit_log_path=audit_log_path)

    def _persist(self, audit_log: AuditLog) -> None:
        """Persist audit log to file (called after each write)."""
        if self.audit_log_path:
            try:
                audit_log.export_json(self.audit_log_path)
            except OSError as exc:
                logger.warning("Audit log persistence failed: %s", type(exc).__name__)

    def _check_auth(self, request: Request) -> bool:
        """Return True if auth passes (or no API key configured)."""
        import hmac

        if not self._api_key:
            return True
        return hmac.compare_digest(
            request.headers.get("X-API-Key", "").encode(),
            self._api_key.encode(),
        )

    # ── Route handlers ────────────────────────────────────────────────────────

    async def handle_agent_card(self, request: Request) -> JSONResponse:
        return JSONResponse(_AGENT_CARD)

    async def handle_health(self, request: Request) -> JSONResponse:
        return JSONResponse(
            {
                "status": "ok",
                "rules": len(self.engine.constitution.rules),
                "audit_entries": len(self.audit_log),
                "chain_valid": self.audit_log.verify_chain(),
                "constitutional_hash": CONSTITUTIONAL_HASH,
            }
        )

    async def handle_a2a(self, request: Request) -> JSONResponse:
        """Main A2A task handler — dispatches to skills by name."""
        if not self._check_auth(request):
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32001, "message": "Unauthorized — provide X-API-Key header"},
                },
                status_code=401,
            )

        # Enforce request body size limit (handle non-numeric Content-Length)
        content_length = request.headers.get("content-length")
        try:
            if content_length and int(content_length) > MAX_REQUEST_BODY_BYTES:
                return JSONResponse(
                    {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": -32600, "message": "Request body too large"},
                    },
                    status_code=413,
                )
        except (ValueError, TypeError):
            pass  # Non-numeric Content-Length — let body read handle it

        try:
            raw_body = await request.body()
            if len(raw_body) > MAX_REQUEST_BODY_BYTES:
                return JSONResponse(
                    {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": -32600, "message": "Request body too large"},
                    },
                    status_code=413,
                )
            body_parsed = json.loads(raw_body)
        except (json.JSONDecodeError, ValueError, UnicodeDecodeError):
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": "Parse error — invalid JSON"},
                },
                status_code=400,
            )

        # Reject top-level non-object JSON (arrays, strings, etc.)
        if not isinstance(body_parsed, dict):
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32600, "message": "Request must be a JSON object"},
                },
                status_code=400,
            )
        body: dict[str, Any] = body_parsed

        req_id = body.get("id")
        method = body.get("method", "")

        if method != "tasks/send":
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {method!r}. Supported: tasks/send",
                    },
                }
            )

        params = body.get("params", {})
        if not isinstance(params, dict):
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32602, "message": "Invalid params — expected object"},
                },
                status_code=400,
            )
        task_id = params.get("id") or f"task-{uuid.uuid4().hex[:8]}"
        message = params.get("message", {})
        parts = message.get("parts", []) if isinstance(message, dict) else []
        if not isinstance(parts, list):
            parts = []
        first_part = parts[0] if parts else {}
        text = first_part.get("text", "") if isinstance(first_part, dict) else ""
        if not isinstance(text, str):
            text = str(text) if text is not None else ""

        # Enforce action text size limit
        if len(text) > MAX_ACTION_TEXT_CHARS:
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32602,
                        "message": f"Action text too long ({len(text)} chars, max {MAX_ACTION_TEXT_CHARS})",
                    },
                },
                status_code=400,
            )

        # Normalize Unicode (NFKC) to defeat homoglyph/zero-width bypasses,
        # then strip null bytes, control characters, and default-ignorable code points
        text = unicodedata.normalize("NFKC", text)
        text = "".join(
            c
            for c in text
            if c in ("\n", "\t")
            or (ord(c) >= 32 and unicodedata.category(c) not in ("Cf", "Cc", "Cn"))
        )

        skill_name, skill_input = _parse_skill(text)

        try:
            result_data = await self._dispatch(skill_name, skill_input)
        except Exception:
            logger.exception("Skill dispatch error for skill=%r", skill_name)
            # Return JSON-RPC error — never fake a successful completion
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32603,
                        "message": "Internal processing error",
                        "data": {"skill": skill_name, "task_id": task_id},
                    },
                },
                status_code=500,
            )

        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "id": task_id,
                    "status": "completed",
                    "result": result_data,
                },
            }
        )

    async def _dispatch(self, skill_name: str, skill_input: str) -> dict[str, Any]:
        """Route to the appropriate skill handler."""
        if skill_name == "validate_clinical_action":
            return await validate_clinical_action(
                skill_input,
                engine=self.engine,
                audit_log=self.audit_log,
                on_persist=self._persist,
            )

        if skill_name == "check_hipaa_compliance":
            return check_hipaa_compliance(skill_input)

        if skill_name == "query_audit_trail":
            # Input can be an audit_id ("HC-20260401-XXXXXX") or "recent N"
            audit_id: str | None = None
            limit = 20
            stripped = skill_input.strip()
            if stripped.upper().startswith("HC-") or (
                stripped and all(c.isalnum() or c == "-" for c in stripped.split()[0])
            ):
                audit_id = stripped.split()[0]
            elif "recent" in stripped.lower():
                parts = stripped.lower().split()
                idx = parts.index("recent")
                if idx + 1 < len(parts) and parts[idx + 1].isdigit():
                    limit = min(int(parts[idx + 1]), 500)
            return query_audit_trail(self.audit_log, audit_id=audit_id, limit=limit)

        # Unknown skill — return helpful error
        available = ["validate_clinical_action", "check_hipaa_compliance", "query_audit_trail"]
        return {
            "error": f"Unknown skill: {skill_name!r}",
            "available_skills": available,
            "hint": f"Prefix your message with one of: {', '.join(available)}: <your input>",
        }

    def build_starlette_app(self) -> Starlette:
        """Build and return the Starlette ASGI app."""
        return Starlette(
            routes=[
                Route("/.well-known/agent.json", self.handle_agent_card, methods=["GET"]),
                Route("/health", self.handle_health, methods=["GET"]),
                Route("/", self.handle_a2a, methods=["POST"]),
            ]
        )


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _parse_skill(text: str) -> tuple[str, str]:
    """Parse 'skill_name: input text' or fall back to keyword detection.

    Returns (skill_name, skill_input).
    """
    text = text.strip()
    known_skills = [
        "validate_clinical_action",
        "check_hipaa_compliance",
        "query_audit_trail",
    ]

    # Try explicit prefix "skill_name: ..."
    for skill in known_skills:
        if text.lower().startswith(skill + ":"):
            return skill, text[len(skill) + 1 :].strip()
        # Also match without underscore spaces for natural use
        alt = skill.replace("_", " ")
        if text.lower().startswith(alt + ":"):
            return skill, text[len(alt) + 1 :].strip()

    # Keyword-based fallback
    text_lower = text.lower()
    if any(
        kw in text_lower
        for kw in ["validate", "prescribe", "medication", "dose", "drug", "patient synth"]
    ):
        return "validate_clinical_action", text
    if any(kw in text_lower for kw in ["hipaa", "compliance", "phi", "privacy"]):
        return "check_hipaa_compliance", text
    if any(kw in text_lower for kw in ["audit", "query audit", "trail", "hc-2"]):
        return "query_audit_trail", text

    # Default: try to validate as a clinical action
    return "validate_clinical_action", text


def _restore_audit_log(audit_log: AuditLog, path: Path) -> None:
    """Reload persisted audit entries into the live AuditLog."""
    from acgs_lite.audit import AuditEntry

    data = json.loads(path.read_text())
    for entry_dict in data.get("entries", []):
        entry = AuditEntry(
            id=entry_dict["id"],
            type=entry_dict.get("type", "clinical_validation"),
            agent_id=entry_dict.get("agent_id", ""),
            action=entry_dict.get("action", ""),
            valid=entry_dict.get("valid", True),
            violations=entry_dict.get("violations", []),
            constitutional_hash=entry_dict.get("constitutional_hash", ""),
            latency_ms=entry_dict.get("latency_ms", 0.0),
            metadata=entry_dict.get("metadata", {}),
            timestamp=entry_dict.get("timestamp", ""),
        )
        audit_log.record(entry)


# ──────────────────────────────────────────────────────────────────────────────
# Module-level app instance (for uvicorn: clinicalguard.agent:app)
# ──────────────────────────────────────────────────────────────────────────────


def create_app(
    constitution_path: str | Path | None = None,
    audit_log_path: str | Path | None = None,
) -> Starlette:
    """Create the ClinicalGuard Starlette app."""
    guard = ClinicalGuardApp.create(
        constitution_path=constitution_path,
        audit_log_path=audit_log_path,
    )
    return guard.build_starlette_app()
