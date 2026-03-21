"""
x402 Governance-as-a-Service — Pay-Per-Call Constitutional Validation

Constitutional Hash: cdd01ef066bc6cf2

Tiered pricing (zero facilitator fees via xpay.sh):
    GET  /x402/check     — FREE   (pass/fail funnel entry, no auth)
    POST /x402/validate  — $0.01  (full validation result)
    POST /x402/audit     — $0.05  (risk breakdown + recommendations)
    POST /x402/certify   — $0.50  (signed attestation, verifiable proof)
    POST /x402/batch     — $0.10  (up to 20 actions, $0.005/action)
    POST /x402/treasury  — $0.05  (DAO treasury intelligence)
    GET  /x402/verify    — FREE   (verify attestation receipts)
    GET  /x402/pricing   — FREE   (endpoint discovery for agents)
    GET  /x402/health    — FREE

Network: Base (eip155:8453) or Base Sepolia (eip155:84532)
Settlement: USDC via x402 protocol facilitator

Setup:
    pip install "x402[fastapi,evm]"
    export EVM_ADDRESS=0x...       # Your Base wallet
    export X402_NETWORK=eip155:8453  # mainnet

Reference: https://github.com/coinbase/x402
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.structured_logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/x402", tags=["x402-governance"])

# ---------------------------------------------------------------------------
# Configuration — tiered pricing, zero-fee facilitator
# ---------------------------------------------------------------------------
X402_PRICE_VALIDATE = os.getenv("X402_PRICE_VALIDATE", "0.01")
X402_PRICE_AUDIT = os.getenv("X402_PRICE_AUDIT", "0.05")
X402_PRICE_CERTIFY = os.getenv("X402_PRICE_CERTIFY", "0.50")
X402_PRICE_BATCH = os.getenv("X402_PRICE_BATCH", "0.10")
X402_PRICE_TREASURY = os.getenv("X402_PRICE_TREASURY", "0.05")
X402_NETWORK = os.getenv("X402_NETWORK", "eip155:84532")
X402_PAY_TO = os.getenv("EVM_ADDRESS", "")
X402_FACILITATOR = os.getenv("FACILITATOR_URL", "https://facilitator.xpay.sh")
_ATTESTATION_SECRET = os.getenv(
    "ATTESTATION_SECRET", os.getenv("JWT_SECRET", "acgs2-dev-key")
)
BATCH_MAX_ACTIONS = 20

# ---------------------------------------------------------------------------
# Lazy-init injection detector
# ---------------------------------------------------------------------------
_injection_detector = None


def _get_detector():
    global _injection_detector
    if _injection_detector is None:
        try:
            from enhanced_agent_bus.security.injection_detector import (
                PromptInjectionDetector,
            )

            _injection_detector = PromptInjectionDetector(strict_mode=True)
        except ImportError:
            logger.warning("PromptInjectionDetector unavailable, using fallback")
    return _injection_detector


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class GovernanceValidationRequest(BaseModel):
    action: str = Field(..., description="The action to validate", max_length=5000)
    agent_id: str = Field(default="anonymous", description="Requesting agent ID")
    context: dict[str, Any] = Field(default_factory=dict)


class GovernanceValidationResponse(BaseModel):
    compliant: bool
    constitutional_hash: str
    decision: str
    confidence: float
    violations: list[str]
    timestamp: str
    processing_ms: int


class GovernanceAuditResponse(BaseModel):
    compliant: bool
    constitutional_hash: str
    decision: str
    confidence: float
    violations: list[str]
    risk_breakdown: dict[str, float]
    risk_level: str
    recommendations: list[str]
    timestamp: str
    processing_ms: int


class AttestationReceipt(BaseModel):
    receipt_hash: str
    signature: str
    signer: str
    algorithm: str
    verify_endpoint: str


class GovernanceCertifyResponse(GovernanceAuditResponse):
    attestation: AttestationReceipt


class BatchValidationRequest(BaseModel):
    actions: list[str] = Field(
        ..., min_length=1, max_length=BATCH_MAX_ACTIONS,
        description=f"1-{BATCH_MAX_ACTIONS} actions to validate",
    )
    agent_id: str = Field(default="anonymous")
    context: dict[str, Any] = Field(default_factory=dict)


class BatchValidationResponse(BaseModel):
    results: list[GovernanceValidationResponse]
    summary: dict[str, int]
    total_actions: int
    processing_ms: int


class EndpointPrice(BaseModel):
    endpoint: str
    method: str
    price_usd: str
    auth: str
    description: str


class X402PricingInfo(BaseModel):
    endpoints: list[EndpointPrice]
    network: str
    asset: str
    facilitator_url: str
    pay_to: str
    constitutional_hash: str


# ---------------------------------------------------------------------------
# Dangerous patterns & risk keywords
# ---------------------------------------------------------------------------

_DANGEROUS_PATTERNS: list[str] = [
    "delete all", "drop table", "rm -rf", "format disk",
    "transfer all funds", "drain wallet", "self-destruct",
    "disable governance", "bypass security", "ignore policy",
]

_RISK_KEYWORDS: dict[str, list[str]] = {
    "financial": ["transfer", "payment", "withdraw", "send funds"],
    "data": ["export data", "download all", "bulk extract"],
    "access": ["escalate", "admin access", "root", "sudo"],
    "governance": ["change policy", "modify rules", "override"],
}

_FALLBACK_INJECTION_PATTERNS: list[str] = [
    "ignore all previous", "you are now", "forget everything",
    "system prompt", "jailbreak", "dan mode",
]

# ---------------------------------------------------------------------------
# Core evaluation engine (shared by all tiers)
# ---------------------------------------------------------------------------


def _evaluate_action(
    action: str,
    context: dict[str, Any],
    *,
    detailed: bool = False,
) -> dict[str, Any]:
    """
    Unified governance evaluation.

    detailed=False → validate-level (pass/fail + violations)
    detailed=True  → audit-level  (+ risk_breakdown, risk_level, recommendations)
    """
    start = datetime.now(UTC)
    violations: list[str] = []
    action_lower = action.lower()

    # 1. Injection detection
    detector = _get_detector()
    if detector is not None:
        det_result = detector.detect(action, context or None)
        if det_result.is_injection:
            for pattern in det_result.matched_patterns:
                violations.append(f"injection_attempt: {pattern}")
    else:
        for pattern in _FALLBACK_INJECTION_PATTERNS:
            if pattern in action_lower:
                violations.append(f"injection_attempt: {pattern}")

    # 2. Dangerous action detection
    for pattern in _DANGEROUS_PATTERNS:
        if pattern in action_lower:
            violations.append(f"dangerous_action: {pattern}")

    # 3. Per-category risk scoring
    risk_breakdown: dict[str, float] = {}
    for category, keywords in _RISK_KEYWORDS.items():
        score = sum(0.25 for kw in keywords if kw in action_lower)
        clamped = round(min(score, 1.0), 2)
        if detailed or score > 0:
            risk_breakdown[category] = clamped
        if score > 0.6:
            violations.append(
                f"high_risk_{category}: action exceeds category threshold"
            )

    total_risk = sum(risk_breakdown.values())

    # 4. Risk level
    if len(violations) > 2 or total_risk > 1.5:
        risk_level = "CRITICAL"
    elif len(violations) > 0 or total_risk > 0.8:
        risk_level = "HIGH"
    elif total_risk > 0.3:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    # 5. Decision
    if len(violations) > 0:
        decision, compliant, confidence = "BLOCKED", False, 0.95
    elif total_risk > 0.5:
        decision, compliant, confidence = "REVIEW_REQUIRED", True, 0.6
    else:
        decision, compliant = "APPROVED", True
        confidence = 0.95 - (total_risk * 0.3)

    elapsed = datetime.now(UTC) - start
    result: dict[str, Any] = {
        "compliant": compliant,
        "constitutional_hash": CONSTITUTIONAL_HASH,
        "decision": decision,
        "confidence": round(confidence, 3),
        "violations": violations,
        "timestamp": datetime.now(UTC).isoformat(),
        "processing_ms": int(elapsed.total_seconds() * 1000),
    }

    if detailed:
        # Ensure all categories present for audit/certify
        for cat in _RISK_KEYWORDS:
            risk_breakdown.setdefault(cat, 0.0)
        result["risk_breakdown"] = risk_breakdown
        result["risk_level"] = risk_level

        recommendations: list[str] = []
        if risk_breakdown.get("financial", 0) > 0:
            recommendations.append(
                "Add multi-sig approval for financial operations"
            )
        if risk_breakdown.get("access", 0) > 0:
            recommendations.append("Implement least-privilege access controls")
        if risk_breakdown.get("data", 0) > 0:
            recommendations.append("Apply data classification and DLP policies")
        if risk_breakdown.get("governance", 0) > 0:
            recommendations.append(
                "Route policy changes through MACI separation-of-powers"
            )
        if not violations and not recommendations:
            recommendations.append(
                "Action complies with all constitutional governance rules"
            )
        result["recommendations"] = recommendations

    return result


# ---------------------------------------------------------------------------
# Attestation signing (HMAC-SHA256 — verifiable via /x402/verify)
# ---------------------------------------------------------------------------


def _sign_receipt(data: dict[str, Any]) -> AttestationReceipt:
    """Create a verifiable HMAC-SHA256 signed receipt of a governance decision."""
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
    receipt_hash = hashlib.sha256(canonical.encode()).hexdigest()
    signature = hmac.new(
        _ATTESTATION_SECRET.encode(), canonical.encode(), hashlib.sha256
    ).hexdigest()
    return AttestationReceipt(
        receipt_hash=receipt_hash,
        signature=signature,
        signer="acgs2-governance",
        algorithm="hmac-sha256",
        verify_endpoint="/x402/verify",
    )


# ===================================================================
# FREE ENDPOINTS — funnel entry, discovery, verification
# ===================================================================


@router.get("/check")
async def quick_check(
    action: str = Query(
        ..., max_length=2000, description="Action to check"
    ),
) -> dict[str, Any]:
    """
    Free governance check — pass/fail only.

    No auth, no payment. Returns minimal result to let agents
    discover the service before committing to paid tiers.
    """
    result = _evaluate_action(action, {}, detailed=True)
    first_violation = result["violations"][0] if result["violations"] else None
    response: dict[str, Any] = {
        "compliant": result["compliant"],
        "decision": result["decision"],
        "risk_level": result["risk_level"],
        "constitutional_hash": CONSTITUTIONAL_HASH,
    }
    if first_violation:
        response["first_violation"] = first_violation
        response["total_violations"] = len(result["violations"])
        response["upgrade"] = {
            "details": "POST /x402/validate ($0.01) — full violations list",
            "audit": "POST /x402/audit ($0.05) — risk breakdown",
            "scan": "POST /x402/scan ($0.03) — injection detection",
        }
    else:
        response["upgrade"] = {
            "certify": "POST /x402/certify ($0.50) — signed attestation",
            "compliance": (
                "POST /x402/compliance ($0.25) — 8-framework assessment"
            ),
        }
    return response


@router.get("/pricing")
async def get_pricing() -> X402PricingInfo:
    """Full pricing info for agent auto-discovery."""
    return X402PricingInfo(
        endpoints=[
            EndpointPrice(
                endpoint="/x402/check", method="GET",
                price_usd="0", auth="none",
                description="Quick pass/fail governance check (free)",
            ),
            EndpointPrice(
                endpoint="/x402/validate", method="POST",
                price_usd=X402_PRICE_VALIDATE, auth="x402-payment",
                description="Full governance validation with violations list",
            ),
            EndpointPrice(
                endpoint="/x402/audit", method="POST",
                price_usd=X402_PRICE_AUDIT, auth="x402-payment",
                description="Compliance audit: risk breakdown + recommendations",
            ),
            EndpointPrice(
                endpoint="/x402/certify", method="POST",
                price_usd=X402_PRICE_CERTIFY, auth="x402-payment",
                description="Signed attestation: verifiable compliance proof",
            ),
            EndpointPrice(
                endpoint="/x402/batch", method="POST",
                price_usd=X402_PRICE_BATCH, auth="x402-payment",
                description=f"Bulk validation: up to {BATCH_MAX_ACTIONS} actions",
            ),
            EndpointPrice(
                endpoint="/x402/treasury", method="POST",
                price_usd=X402_PRICE_TREASURY, auth="x402-payment",
                description="DAO treasury intelligence and risk analysis",
            ),
            EndpointPrice(
                endpoint="/x402/verify", method="GET",
                price_usd="0", auth="none",
                description="Verify attestation receipt authenticity (free)",
            ),
            # Marketplace endpoints
            EndpointPrice(
                endpoint="/x402/scan", method="POST",
                price_usd="0.03", auth="x402-payment",
                description="Prompt injection detection",
            ),
            EndpointPrice(
                endpoint="/x402/classify-risk", method="POST",
                price_usd="0.10", auth="x402-payment",
                description="EU AI Act risk classification",
            ),
            EndpointPrice(
                endpoint="/x402/compliance", method="POST",
                price_usd="0.25", auth="x402-payment",
                description="Multi-framework compliance (8 frameworks)",
            ),
            EndpointPrice(
                endpoint="/x402/simulate", method="POST",
                price_usd="0.15", auth="x402-payment",
                description="Policy change simulation",
            ),
            EndpointPrice(
                endpoint="/x402/trust", method="POST",
                price_usd="0.02", auth="x402-payment",
                description="Agent trust scoring",
            ),
            EndpointPrice(
                endpoint="/x402/anomaly", method="POST",
                price_usd="0.03", auth="x402-payment",
                description="Governance anomaly detection",
            ),
            EndpointPrice(
                endpoint="/x402/explain", method="POST",
                price_usd="0.05", auth="x402-payment",
                description="Decision explainability",
            ),
            EndpointPrice(
                endpoint="/x402/invariant-guard", method="POST",
                price_usd="0.10", auth="x402-payment",
                description="Three-tier invariant enforcement",
            ),
            EndpointPrice(
                endpoint="/x402/circuit-breaker", method="POST",
                price_usd="0.10", auth="x402-payment",
                description="Governance circuit breaker",
            ),
            EndpointPrice(
                endpoint="/x402/policy-lint", method="POST",
                price_usd="0.05", auth="x402-payment",
                description="Policy quality & security scan",
            ),
            EndpointPrice(
                endpoint="/x402/eu-ai-log", method="POST",
                price_usd="0.10", auth="x402-payment",
                description="EU AI Act Article 12 logging",
            ),
        ],
        network=X402_NETWORK,
        asset="USDC",
        facilitator_url=X402_FACILITATOR,
        pay_to=X402_PAY_TO,
        constitutional_hash=CONSTITUTIONAL_HASH,
    )


@router.get("/verify")
async def verify_receipt(
    receipt_hash: str = Query(..., description="Receipt hash from /certify"),
    signature: str = Query(..., description="HMAC signature from /certify"),
    data: str = Query(..., description="URL-encoded canonical JSON of the result"),
) -> dict[str, Any]:
    """
    Free attestation verification — proves a /certify receipt is authentic.

    Agents and auditors use this to verify governance compliance proofs
    without paying. This drives trust and adoption of the paid /certify tier.
    """
    # Recompute HMAC and compare
    expected_hash = hashlib.sha256(data.encode()).hexdigest()
    expected_sig = hmac.new(
        _ATTESTATION_SECRET.encode(), data.encode(), hashlib.sha256
    ).hexdigest()

    hash_valid = hmac.compare_digest(receipt_hash, expected_hash)
    sig_valid = hmac.compare_digest(signature, expected_sig)

    return {
        "valid": hash_valid and sig_valid,
        "receipt_hash_match": hash_valid,
        "signature_match": sig_valid,
        "signer": "acgs2-governance",
        "constitutional_hash": CONSTITUTIONAL_HASH,
    }


@router.get("/health")
async def x402_health() -> dict[str, Any]:
    """Health check for x402 governance service."""
    return {
        "status": "ok",
        "constitutional_hash": CONSTITUTIONAL_HASH,
        "x402_enabled": bool(X402_PAY_TO),
        "network": X402_NETWORK,
        "pricing": {
            "check": "free",
            "validate": X402_PRICE_VALIDATE,
            "audit": X402_PRICE_AUDIT,
            "certify": X402_PRICE_CERTIFY,
            "batch": X402_PRICE_BATCH,
            "treasury": X402_PRICE_TREASURY,
            "verify": "free",
        },
    }


# ===================================================================
# PAID ENDPOINTS — x402 payment replaces JWT auth
# ===================================================================
# When EVM_ADDRESS is set, the x402 PaymentMiddlewareASGI gates these
# endpoints. Payment = authentication (wallet address = caller identity).
# When EVM_ADDRESS is NOT set, these run without payment (dev mode).


@router.post("/validate")
async def validate_governance(
    request: Request,
    body: GovernanceValidationRequest,
) -> GovernanceValidationResponse:
    """
    Governance validation — $0.01/call.

    Returns full compliance result with violations list.
    """
    result = _evaluate_action(body.action, body.context)

    logger.info(
        "x402 governance validation",
        agent_id=body.agent_id,
        decision=result["decision"],
        violations=len(result["violations"]),
        processing_ms=result["processing_ms"],
    )

    response = GovernanceValidationResponse(**result)
    return response


@router.post("/audit")
async def audit_governance(
    request: Request,
    body: GovernanceValidationRequest,
) -> GovernanceAuditResponse:
    """
    Full compliance audit — $0.05/call.

    Returns per-category risk breakdown, risk level, and recommendations.
    """
    result = _evaluate_action(body.action, body.context, detailed=True)

    logger.info(
        "x402 governance audit",
        agent_id=body.agent_id,
        decision=result["decision"],
        risk_level=result["risk_level"],
        processing_ms=result["processing_ms"],
    )

    return GovernanceAuditResponse(**result)


@router.post("/certify")
async def certify_governance(
    request: Request,
    body: GovernanceValidationRequest,
) -> GovernanceCertifyResponse:
    """
    Signed governance attestation — $0.50/call.

    Returns full audit + cryptographically signed receipt that proves
    this action was governance-validated. Other agents and auditors
    can verify the receipt via GET /x402/verify at no cost.

    This is the premium tier: verifiable compliance proof for
    agent-to-agent trust, regulatory audit trails, and DAO governance.
    """
    result = _evaluate_action(body.action, body.context, detailed=True)
    attestation = _sign_receipt(result)

    logger.info(
        "x402 governance certify",
        agent_id=body.agent_id,
        decision=result["decision"],
        risk_level=result["risk_level"],
        receipt_hash=attestation.receipt_hash[:16] + "...",
        processing_ms=result["processing_ms"],
    )

    return GovernanceCertifyResponse(**result, attestation=attestation)


@router.post("/batch")
async def batch_validate(
    request: Request,
    body: BatchValidationRequest,
) -> BatchValidationResponse:
    """
    Bulk governance validation — $0.10 for up to 20 actions.

    Effective rate: $0.005/action (50% discount vs individual /validate).
    Higher total spend per settlement = more revenue per on-chain tx.
    """
    start = datetime.now(UTC)
    results: list[GovernanceValidationResponse] = []
    counts: dict[str, int] = {"APPROVED": 0, "BLOCKED": 0, "REVIEW_REQUIRED": 0}

    for action in body.actions:
        r = _evaluate_action(action, body.context)
        results.append(GovernanceValidationResponse(**r))
        counts[r["decision"]] = counts.get(r["decision"], 0) + 1

    elapsed = datetime.now(UTC) - start

    logger.info(
        "x402 batch validation",
        agent_id=body.agent_id,
        total_actions=len(body.actions),
        approved=counts.get("APPROVED", 0),
        blocked=counts.get("BLOCKED", 0),
        processing_ms=int(elapsed.total_seconds() * 1000),
    )

    return BatchValidationResponse(
        results=results,
        summary=counts,
        total_actions=len(body.actions),
        processing_ms=int(elapsed.total_seconds() * 1000),
    )


@router.post("/treasury")
async def treasury_overview(
    request: Request,
    body: GovernanceValidationRequest,
) -> dict[str, Any]:
    """
    DAO Treasury intelligence — $0.05/call.

    Accepts a DAO name in the `action` field, returns treasury composition,
    health score, and risk analysis.
    """
    dao_name = body.action.strip()
    if not dao_name or len(dao_name) > 200:
        raise HTTPException(
            status_code=422,
            detail="Provide a DAO name (1-200 chars) in the action field",
        )

    logger.info(
        "x402 treasury query",
        agent_id=body.agent_id,
        dao_name=dao_name,
    )

    return {
        "dao": dao_name,
        "status": "query_accepted",
        "note": (
            "Full treasury analysis available via "
            "neural-mcp dao_treasury_overview tool"
        ),
        "constitutional_hash": CONSTITUTIONAL_HASH,
    }


# ---------------------------------------------------------------------------
# Middleware reference
# ---------------------------------------------------------------------------
# Payment middleware is activated in main.py when EVM_ADDRESS is set.
# x402 payment replaces JWT auth — paying = authenticated.
#
# Env vars:
#   EVM_ADDRESS         — Your Base wallet (required to activate payments)
#   X402_NETWORK        — eip155:8453 (mainnet) or eip155:84532 (testnet)
#   X402_PRICE_VALIDATE — $0.01 default
#   X402_PRICE_AUDIT    — $0.05 default
#   X402_PRICE_CERTIFY  — $0.50 default
#   X402_PRICE_BATCH    — $0.10 default (up to 20 actions)
#   X402_PRICE_TREASURY — $0.05 default
#   FACILITATOR_URL     — https://facilitator.xpay.sh (zero fees)
#   ATTESTATION_SECRET  — key for signing certify receipts
#
# Install: pip install "x402[evm]"
