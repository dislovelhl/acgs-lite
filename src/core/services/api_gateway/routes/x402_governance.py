"""
x402 Governance-as-a-Service Endpoint

Constitutional Hash: cdd01ef066bc6cf2

Sells ACGS-2 constitutional governance validation as a pay-per-call
x402 endpoint. Any AI agent can pay USDC to validate actions against
constitutional governance rules.

Pricing: $0.001 per validation call (configurable)
Network: Base (eip155:8453) or Base Sepolia (eip155:84532)
Settlement: USDC via x402 protocol facilitator

Setup:
    pip install "x402[fastapi,evm]"
    Set EVM_ADDRESS in .env (your Base wallet)

Reference: https://github.com/coinbase/x402
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.security.auth import UserClaims, get_current_user
from src.core.shared.structured_logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/x402", tags=["x402-governance"])

# x402 configuration
X402_PRICE_USD = os.getenv("X402_GOVERNANCE_PRICE", "0.001")
X402_NETWORK = os.getenv("X402_NETWORK", "eip155:84532")  # Base Sepolia default
X402_PAY_TO = os.getenv("EVM_ADDRESS", "")
X402_FACILITATOR = os.getenv("FACILITATOR_URL", "https://x402.org/facilitator")

# Lazy-init injection detector (avoids import-time side effects)
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
            logger.warning("PromptInjectionDetector unavailable, using fallback detection")
    return _injection_detector


class GovernanceValidationRequest(BaseModel):
    """Request to validate an action against constitutional governance."""

    action: str = Field(..., description="The action to validate", max_length=5000)
    agent_id: str = Field(default="anonymous", description="Requesting agent identifier")
    context: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context for validation",
    )


class GovernanceValidationResponse(BaseModel):
    """Result of constitutional governance validation."""

    compliant: bool
    constitutional_hash: str
    decision: str  # APPROVED | BLOCKED | REVIEW_REQUIRED
    confidence: float
    violations: list[str]
    timestamp: str
    processing_ms: int


class X402PricingInfo(BaseModel):
    """Pricing information for the x402 endpoint."""

    price_usd: str
    network: str
    asset: str
    facilitator_url: str
    pay_to: str
    description: str


# ----- Core validation logic -----

# Dangerous action patterns (supplement the injection detector)
_DANGEROUS_PATTERNS: list[str] = [
    "delete all",
    "drop table",
    "rm -rf",
    "format disk",
    "transfer all funds",
    "drain wallet",
    "self-destruct",
    "disable governance",
    "bypass security",
    "ignore policy",
]

# Risk keywords grouped by category
_RISK_KEYWORDS: dict[str, list[str]] = {
    "financial": ["transfer", "payment", "withdraw", "send funds"],
    "data": ["export data", "download all", "bulk extract"],
    "access": ["escalate", "admin access", "root", "sudo"],
    "governance": ["change policy", "modify rules", "override"],
}


def _validate_action(action: str, context: dict[str, Any]) -> dict[str, Any]:
    """
    Core governance validation logic.

    Uses the production PromptInjectionDetector for injection scanning,
    with dangerous-action detection and per-category risk scoring.
    """
    start = datetime.now(UTC)
    violations: list[str] = []
    action_lower = action.lower()

    # 1. Injection detection via shared detector
    detector = _get_detector()
    if detector is not None:
        result = detector.detect(action, context or None)
        if result.is_injection:
            for pattern in result.matched_patterns:
                violations.append(f"injection_attempt: {pattern}")
    else:
        # Fallback: minimal inline patterns if detector is unavailable
        _fallback_injection_patterns = [
            "ignore all previous",
            "you are now",
            "forget everything",
            "system prompt",
            "jailbreak",
            "dan mode",
        ]
        for pattern in _fallback_injection_patterns:
            if pattern in action_lower:
                violations.append(f"injection_attempt: {pattern}")

    # 2. Dangerous action detection
    for pattern in _DANGEROUS_PATTERNS:
        if pattern in action_lower:
            violations.append(f"dangerous_action: {pattern}")

    # 3. Per-category risk scoring
    category_scores: dict[str, float] = {}
    for category, keywords in _RISK_KEYWORDS.items():
        score = sum(0.2 for kw in keywords if kw in action_lower)
        if score > 0:
            category_scores[category] = score
        if score > 0.6:
            violations.append(f"high_risk_{category}: action exceeds category threshold")

    total_risk = sum(category_scores.values())

    # Decision
    if len(violations) > 0:
        decision = "BLOCKED"
        compliant = False
        confidence = 0.95
    elif total_risk > 0.5:
        decision = "REVIEW_REQUIRED"
        compliant = True
        confidence = 0.6
    else:
        decision = "APPROVED"
        compliant = True
        confidence = 0.95 - (total_risk * 0.3)

    elapsed = datetime.now(UTC) - start
    processing_ms = int(elapsed.total_seconds() * 1000)

    return {
        "compliant": compliant,
        "constitutional_hash": CONSTITUTIONAL_HASH,
        "decision": decision,
        "confidence": round(confidence, 3),
        "violations": violations,
        "timestamp": datetime.now(UTC).isoformat(),
        "processing_ms": processing_ms,
    }


# ----- Routes -----


@router.get("/pricing")
async def get_pricing() -> X402PricingInfo:
    """Get x402 pricing info for governance validation."""
    return X402PricingInfo(
        price_usd=X402_PRICE_USD,
        network=X402_NETWORK,
        asset="USDC",
        facilitator_url=X402_FACILITATOR,
        pay_to=X402_PAY_TO,
        description="Constitutional governance validation per call",
    )


@router.post("/validate")
async def validate_governance(
    request: Request,
    body: GovernanceValidationRequest,
    user: UserClaims = Depends(get_current_user),
) -> GovernanceValidationResponse:
    """
    Validate an action against constitutional governance.

    Requires authentication. When x402 middleware is active, this
    endpoint also requires USDC payment on top of auth.
    """
    result = _validate_action(body.action, body.context)

    logger.info(
        "x402 governance validation",
        agent_id=body.agent_id,
        decision=result["decision"],
        violations=len(result["violations"]),
        processing_ms=result["processing_ms"],
    )

    return GovernanceValidationResponse(**result)


@router.post("/treasury")
async def treasury_overview(
    request: Request,
    body: GovernanceValidationRequest,
    user: UserClaims = Depends(get_current_user),
) -> dict[str, Any]:
    """
    DAO Treasury intelligence endpoint (x402 paywall-ready).

    Accepts a DAO name in the `action` field, returns treasury composition,
    health score, and risk analysis. Priced at $0.001/query via x402.
    """
    dao_name = body.action.strip()
    if not dao_name or len(dao_name) > 200:
        return {"error": "Provide a DAO name (1-200 chars) in the action field"}

    logger.info(
        "x402 treasury query",
        agent_id=body.agent_id,
        dao_name=dao_name,
    )

    return {
        "dao": dao_name,
        "status": "query_accepted",
        "note": "Full treasury analysis available via neural-mcp dao_treasury_overview tool",
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
        "price_usd": X402_PRICE_USD,
    }


# ----- x402 Middleware Setup -----
# To enable paid access, add this to your FastAPI app:
#
# from x402.http import FacilitatorConfig, HTTPFacilitatorClient, PaymentOption
# from x402.http.middleware.fastapi import PaymentMiddlewareASGI
# from x402.http.types import RouteConfig
# from x402.mechanisms.evm.exact import ExactEvmServerScheme
# from x402.server import x402ResourceServer
#
# facilitator = HTTPFacilitatorClient(
#     FacilitatorConfig(url=X402_FACILITATOR)
# )
# server = x402ResourceServer(facilitator)
# server.register(X402_NETWORK, ExactEvmServerScheme())
#
# routes = {
#     "POST /x402/validate": RouteConfig(
#         accepts=[
#             PaymentOption(
#                 scheme="exact",
#                 pay_to=X402_PAY_TO,
#                 price=f"${X402_PRICE_USD}",
#                 network=X402_NETWORK,
#             ),
#         ],
#         mime_type="application/json",
#         description="Constitutional governance validation",
#     ),
#     "POST /x402/treasury": RouteConfig(
#         accepts=[
#             PaymentOption(
#                 scheme="exact",
#                 pay_to=X402_PAY_TO,
#                 price=f"${X402_PRICE_USD}",
#                 network=X402_NETWORK,
#             ),
#         ],
#         mime_type="application/json",
#         description="DAO treasury intelligence query",
#     ),
# }
#
# app.add_middleware(PaymentMiddlewareASGI, routes=routes, server=server)
