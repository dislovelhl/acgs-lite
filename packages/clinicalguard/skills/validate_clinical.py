"""ClinicalGuard: validate_clinical_action skill.

Two-layer architecture:
  1. LLM clinical reasoning  -- interprets free-text proposals, assesses
                                 evidence tier, drug interactions, step therapy.
  2. GovernanceEngine check  -- deterministic constitutional rule enforcement
                                 (MACI, keyword/pattern matching, audit trail).

The LLM layer handles what rule-based software cannot (novel clinical scenarios,
semantic reasoning). The GovernanceEngine handles what LLMs should not be trusted
to do alone (cryptographic audit, MACI enforcement, reproducible rule checks).

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from acgs_lite.audit import AuditEntry, AuditLog
from acgs_lite.engine import GovernanceEngine
from acgs_lite.maci import MACIRole

logger = logging.getLogger(__name__)

# Decision constants
APPROVED = "APPROVED"
CONDITIONAL = "CONDITIONALLY_APPROVED"
REJECTED = "REJECTED"

# Risk tiers
RISK_LOW = "LOW"
RISK_MEDIUM = "MEDIUM"
RISK_HIGH = "HIGH"
RISK_CRITICAL = "CRITICAL"

# Severity → risk tier mapping
_SEVERITY_TO_RISK = {
    "critical": RISK_CRITICAL,
    "high": RISK_HIGH,
    "medium": RISK_MEDIUM,
    "low": RISK_LOW,
}

# ──────────────────────────────────────────────────────────────────────────────
# LLM Clinical Reasoning Layer
# ──────────────────────────────────────────────────────────────────────────────

_CLINICAL_PROMPT_TEMPLATE = """You are a constitutional clinical AI governance validator.
Analyse the proposed clinical action below and respond with ONLY valid JSON — no markdown fences,
no commentary, just the JSON object.

JSON schema:
{{
  "evidence_tier": "FDA_APPROVED | GUIDELINE | RCT_SUPPORTED | OFF_LABEL | UNKNOWN",
  "drug_interactions": [
    {{"drugs": ["drug_a", "drug_b"], "severity": "MAJOR | MODERATE | MINOR", "description": "..."}}
  ],
  "step_therapy_concern": true | false,
  "step_therapy_detail": "brief explanation or empty string",
  "dosing_concern": true | false,
  "dosing_detail": "brief explanation or empty string",
  "risk_tier": "LOW | MEDIUM | HIGH | CRITICAL",
  "reasoning": "1-3 sentences explaining the clinical assessment",
  "recommended_decision": "APPROVED | CONDITIONALLY_APPROVED | REJECTED",
  "conditions": ["condition 1 if CONDITIONALLY_APPROVED", "..."]
}}

Rules:
- Use only SYNTHETIC or de-identified patient identifiers (SYNTH-XXX, PATIENT-XXX).
- A MAJOR drug interaction → risk_tier at minimum HIGH, recommended_decision REJECTED or CONDITIONAL.
- A CRITICAL dosing deviation (e.g. 10x dose) → risk_tier CRITICAL, recommended_decision REJECTED.
- OFF_LABEL evidence tier → risk_tier at minimum HIGH.
- Missing step therapy → CONDITIONALLY_APPROVED with step-therapy condition.
- If no concerns and evidence is solid → APPROVED.
- Be concise. Clinicians read this.

Proposed clinical action:
{action_text}
"""


@dataclass
class LLMClinicalAssessment:
    """Structured output from the LLM clinical reasoning layer."""

    evidence_tier: str = "UNKNOWN"
    drug_interactions: list[dict[str, Any]] = field(default_factory=list)
    step_therapy_concern: bool = False
    step_therapy_detail: str = ""
    dosing_concern: bool = False
    dosing_detail: str = ""
    risk_tier: str = RISK_MEDIUM
    reasoning: str = ""
    recommended_decision: str = CONDITIONAL
    conditions: list[str] = field(default_factory=list)
    llm_available: bool = True
    error: str = ""

    @property
    def has_major_interaction(self) -> bool:
        return any(
            i.get("severity", "").upper() == "MAJOR" for i in self.drug_interactions
        )


async def _call_llm_anthropic_api(action_text: str) -> dict[str, Any]:
    """Direct Anthropic API call using ANTHROPIC_API_KEY.

    Used in production (Fly.io) where pi OAuth is not available.
    """
    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    model = os.environ.get("CLINICALGUARD_MODEL", "claude-haiku-4-5")
    prompt = _CLINICAL_PROMPT_TEMPLATE.format(action_text=action_text)

    client = anthropic.AsyncAnthropic(api_key=api_key)
    response = await client.messages.create(
        model=model,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text.strip()
    # Strip markdown fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    return json.loads(text)


async def _call_llm_pi_rpc(action_text: str) -> dict[str, Any]:
    """Call the LLM via pi's RPC mode.

    Spawns `pi --mode rpc --no-session`, sends the prompt, collects streamed
    text deltas until agent_end, then parses the JSON response.
    Uses pi's existing OAuth credentials — no separate API key needed.
    Best for local development and demo recording.
    """
    import shutil

    pi_binary = os.environ.get("PI_BINARY") or shutil.which("pi") or "pi"
    prompt = _CLINICAL_PROMPT_TEMPLATE.format(action_text=action_text)

    proc = await asyncio.create_subprocess_exec(
        pi_binary, "--mode", "rpc", "--no-session",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )

    cmd = json.dumps({"type": "prompt", "message": prompt}) + "\n"
    proc.stdin.write(cmd.encode())
    await proc.stdin.drain()

    collected: list[str] = []
    buffer = b""

    assert proc.stdout is not None
    try:
        while True:
            chunk = await asyncio.wait_for(proc.stdout.read(4096), timeout=30.0)
            if not chunk:
                break
            buffer += chunk
            while b"\n" in buffer:
                line_bytes, buffer = buffer.split(b"\n", 1)
                line = line_bytes.decode("utf-8", errors="replace").rstrip("\r")
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                etype = event.get("type", "")
                if etype == "message_update":
                    delta = event.get("assistantMessageEvent", {})
                    if delta.get("type") == "text_delta":
                        collected.append(delta["delta"])
                elif etype == "agent_end":
                    break
            else:
                continue
            break
    finally:
        try:
            proc.stdin.close()
        except Exception:
            pass
        if proc.returncode is None:
            proc.kill()
        try:
            await asyncio.wait_for(proc.wait(), timeout=2.0)
        except Exception:
            pass

    full_text = "".join(collected).strip()
    if full_text.startswith("```"):
        lines = full_text.split("\n")
        full_text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    return json.loads(full_text)


def _pi_available() -> bool:
    """Return True if the pi binary is in PATH or PI_BINARY is set."""
    import shutil
    return bool(os.environ.get("PI_BINARY") or shutil.which("pi"))


async def get_llm_assessment(action_text: str) -> LLMClinicalAssessment:
    """Get LLM clinical assessment.

    Provider selection (in order):
      1. ANTHROPIC_API_KEY set  → direct Anthropic API  (production / Fly.io)
      2. pi binary available    → pi RPC subprocess     (local dev / demo)
      3. fallback               → constitutional rules only
    """
    # Choose provider
    if os.environ.get("ANTHROPIC_API_KEY"):
        caller = _call_llm_anthropic_api
        label = "Anthropic API"
    elif _pi_available():
        caller = _call_llm_pi_rpc
        label = "pi RPC"
    else:
        logger.warning("No LLM provider available — using rule-only fallback")
        return LLMClinicalAssessment(
            llm_available=False,
            error="No LLM provider: set ANTHROPIC_API_KEY or ensure pi is in PATH.",
            reasoning="LLM reasoning unavailable — constitutional rules only.",
            recommended_decision=CONDITIONAL,
            risk_tier=RISK_MEDIUM,
        )

    try:
        data = await asyncio.wait_for(caller(action_text), timeout=60.0)
        logger.debug("LLM assessment via %s: decision=%s", label, data.get("recommended_decision"))
        # Validate LLM response types — untrusted JSON may have wrong field types
        raw_interactions = data.get("drug_interactions", [])
        drug_interactions = raw_interactions if isinstance(raw_interactions, list) else []
        raw_conditions = data.get("conditions", [])
        conditions = raw_conditions if isinstance(raw_conditions, list) else []
        return LLMClinicalAssessment(
            evidence_tier=str(data.get("evidence_tier", "UNKNOWN")),
            drug_interactions=drug_interactions,
            step_therapy_concern=bool(data.get("step_therapy_concern", False)),
            step_therapy_detail=str(data.get("step_therapy_detail", "")),
            dosing_concern=bool(data.get("dosing_concern", False)),
            dosing_detail=str(data.get("dosing_detail", "")),
            risk_tier=str(data.get("risk_tier", RISK_MEDIUM)),
            reasoning=str(data.get("reasoning", "")),
            recommended_decision=str(data.get("recommended_decision", CONDITIONAL)),
            conditions=conditions,
            llm_available=True,
        )
    except Exception as exc:
        logger.warning("%s clinical reasoning failed: %s — rule-only fallback", label, type(exc).__name__)
        return LLMClinicalAssessment(
            llm_available=False,
            error=type(exc).__name__,
            reasoning="LLM reasoning unavailable — constitutional rules only.",
            recommended_decision=CONDITIONAL,
            risk_tier=RISK_MEDIUM,
        )


# ──────────────────────────────────────────────────────────────────────────────
# Main validate_clinical_action skill
# ──────────────────────────────────────────────────────────────────────────────


async def validate_clinical_action(
    action_text: str,
    *,
    engine: GovernanceEngine,
    audit_log: AuditLog,
    proposer_id: str = "external-agent",
    on_persist: Any = None,  # optional callback(audit_log) → None after write
) -> dict[str, Any]:
    """Validate a proposed clinical action.

    Returns a dict with:
        decision:            APPROVED | CONDITIONALLY_APPROVED | REJECTED
        confidence:          float 0-1
        risk_tier:           LOW | MEDIUM | HIGH | CRITICAL
        reasoning:           str (LLM reasoning or fallback text)
        llm_available:       bool
        violations:          list[dict] — constitutional rule violations
        conditions:          list[str] — conditions for CONDITIONAL decisions
        drug_interactions:   list[dict]
        audit_id:            str
        constitutional_hash: str
        maci_role:           str
        timestamp:           str
    """
    if not action_text or not action_text.strip():
        return {
            "decision": REJECTED,
            "confidence": 1.0,
            "risk_tier": RISK_CRITICAL,
            "reasoning": "Empty clinical action rejected.",
            "violations": [{"rule_id": "INPUT", "rule_text": "Action text is required.", "severity": "critical"}],
            "conditions": [],
            "drug_interactions": [],
            "audit_id": f"HC-ERROR-{uuid.uuid4().hex[:8].upper()}",
            "constitutional_hash": engine.constitution.hash if hasattr(engine, "constitution") else "",
            "maci_role": MACIRole.VALIDATOR,
            "timestamp": datetime.now(UTC).isoformat(),
            "llm_available": False,
        }

    # Step 1: LLM clinical reasoning (async, non-blocking, with timeout fallback)
    llm = await get_llm_assessment(action_text)

    # Step 2: GovernanceEngine constitutional check (deterministic)
    gov_result = engine.validate(action_text, agent_id=proposer_id)
    blocking = gov_result.blocking_violations
    warnings = gov_result.warnings

    # Step 3: Combine LLM + constitutional results → final decision
    all_violations = [
        {
            "rule_id": v.rule_id,
            "rule_text": v.rule_text,
            "severity": v.severity.value,
            "matched_content": v.matched_content,
        }
        for v in (blocking + warnings)
    ]

    # Risk tier: take worst of LLM assessment and constitutional violations
    const_risk = _highest_risk_from_violations(blocking + warnings)
    final_risk = _max_risk(llm.risk_tier, const_risk)

    # Decision logic:
    # - Any CRITICAL constitutional violation → REJECTED
    # - LLM recommends REJECTED + CRITICAL risk → REJECTED
    # - Blocking constitutional violations → at minimum CONDITIONAL
    # - Step therapy concern or conditions → CONDITIONAL
    # - Otherwise: APPROVED
    conditions: list[str] = list(llm.conditions)

    if blocking:
        if final_risk == RISK_CRITICAL or llm.recommended_decision == REJECTED:
            decision = REJECTED
        else:
            decision = CONDITIONAL
        if decision != REJECTED:
            for v in blocking:
                conditions.append(f"Resolve {v.rule_id}: {v.rule_text[:100]}")
    elif llm.recommended_decision == REJECTED and final_risk in (RISK_CRITICAL, RISK_HIGH):
        decision = REJECTED
    elif llm.step_therapy_concern or llm.conditions or warnings:
        decision = CONDITIONAL
    else:
        decision = llm.recommended_decision if llm.llm_available else CONDITIONAL

    # Confidence: lower if LLM unavailable or low-severity-only violations
    confidence = _compute_confidence(llm, blocking, warnings)

    # Build reasoning text
    reasoning_parts = []
    if llm.reasoning:
        reasoning_parts.append(llm.reasoning)
    if llm.drug_interactions:
        major = [i for i in llm.drug_interactions if i.get("severity", "").upper() == "MAJOR"]
        if major:
            reasoning_parts.append(
                "Major drug interaction(s) detected: "
                + "; ".join(f"{'+'.join(i.get('drugs', []))}: {i.get('description', '')}" for i in major)
            )
    if llm.dosing_concern and llm.dosing_detail:
        reasoning_parts.append(f"Dosing concern: {llm.dosing_detail}")
    if llm.step_therapy_concern and llm.step_therapy_detail:
        reasoning_parts.append(f"Step therapy: {llm.step_therapy_detail}")
    if blocking:
        rule_ids = ", ".join(v.rule_id for v in blocking)
        reasoning_parts.append(f"Constitutional violations: {rule_ids}")
    reasoning = " ".join(reasoning_parts) or "Assessment complete."

    # Step 4: Audit trail entry
    audit_id = f"HC-{datetime.now(UTC).strftime('%Y%m%d')}-{uuid.uuid4().hex[:10].upper()}"
    constitutional_hash = ""
    try:
        constitutional_hash = engine.constitution.hash
    except Exception:
        pass

    entry = AuditEntry(
        id=audit_id,
        type="clinical_validation",
        agent_id=proposer_id,
        action=action_text[:500],
        valid=(decision == APPROVED),
        violations=[v.rule_id for v in (blocking + warnings)],
        constitutional_hash=constitutional_hash,
        latency_ms=gov_result.latency_ms,
        metadata={
            "decision": decision,
            "risk_tier": final_risk,
            "confidence": confidence,
            "llm_available": llm.llm_available,
            "evidence_tier": llm.evidence_tier,
            "drug_interactions": llm.drug_interactions,
            "conditions": conditions,
        },
    )
    audit_log.record(entry)

    # Optional persistence callback (file export)
    if on_persist is not None:
        try:
            on_persist(audit_log)
        except Exception as exc:
            logger.warning("Audit persistence callback failed: %s", type(exc).__name__)

    return {
        "decision": decision,
        "confidence": round(confidence, 3),
        "risk_tier": final_risk,
        "reasoning": reasoning,
        "llm_available": llm.llm_available,
        "evidence_tier": llm.evidence_tier,
        "drug_interactions": llm.drug_interactions,
        "violations": all_violations,
        "conditions": conditions,
        "audit_id": audit_id,
        "constitutional_hash": constitutional_hash,
        "maci_role": MACIRole.VALIDATOR,
        "timestamp": entry.timestamp,
        "appeal_path": f"Contact your governance administrator with audit_id={audit_id}" if decision != APPROVED else None,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

_RISK_ORDER = [RISK_LOW, RISK_MEDIUM, RISK_HIGH, RISK_CRITICAL]


def _risk_level(tier: str) -> int:
    try:
        return _RISK_ORDER.index(tier.upper())
    except ValueError:
        return 1  # MEDIUM default


def _max_risk(a: str, b: str) -> str:
    return _RISK_ORDER[max(_risk_level(a), _risk_level(b))]


def _highest_risk_from_violations(violations: list) -> str:
    if not violations:
        return RISK_LOW
    severities = [v.severity.value for v in violations]
    for level in ("critical", "high", "medium", "low"):
        if level in severities:
            return _SEVERITY_TO_RISK[level]
    return RISK_LOW


def _compute_confidence(
    llm: LLMClinicalAssessment,
    blocking: list,
    warnings: list,
) -> float:
    base = 0.90 if llm.llm_available else 0.65
    if blocking:
        base -= 0.10  # lower confidence when constitutional rules fire
    if warnings:
        base -= 0.05
    if not llm.llm_available:
        base -= 0.10
    return max(0.40, min(1.0, base))
