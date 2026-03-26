"""
x402 Endpoint Bundles — Tiered Micropayment Packages

Constitutional Hash: 608508a9bd224290

Bundles aggregate individually-priced x402 governance endpoints into
discounted tiers.  A single x402 payment settles the full bundle,
raising ARPU while lowering per-call friction for agents.

Tiers:
    Scout    $0.05  — /check + /validate + /scan
    Shield   $0.25  — Scout + /audit + /classify-risk + /trust + /anomaly + /explain
    Fortress $1.00  — Shield + /certify + /compliance + /simulate
                       + /invariant-guard + /circuit-breaker + /policy-lint + /eu-ai-log

Savings are computed dynamically from individual endpoint prices so
operators can tune per-endpoint pricing without breaking bundle math.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.structured_logging import get_logger

from ._x402_common import PAID_RESPONSE_DISCLAIMER
from ._x402_revenue import RevenueEvent, emit_revenue_event

logger = get_logger(__name__)

router = APIRouter(prefix="/x402", tags=["x402-bundles"])

# ---------------------------------------------------------------------------
# Individual endpoint prices (mirrors x402_governance + x402_marketplace)
# ---------------------------------------------------------------------------

_ENDPOINT_PRICES: dict[str, str] = {
    "/check": "0.00",
    "/validate": os.getenv("X402_PRICE_VALIDATE", "0.01"),
    "/scan": os.getenv("X402_PRICE_SCAN", "0.03"),
    "/audit": os.getenv("X402_PRICE_AUDIT", "0.05"),
    "/classify-risk": os.getenv("X402_PRICE_CLASSIFY_RISK", "0.10"),
    "/trust": os.getenv("X402_PRICE_TRUST", "0.02"),
    "/anomaly": os.getenv("X402_PRICE_ANOMALY", "0.03"),
    "/explain": os.getenv("X402_PRICE_EXPLAIN", "0.05"),
    "/certify": os.getenv("X402_PRICE_CERTIFY", "0.50"),
    "/compliance": os.getenv("X402_PRICE_COMPLIANCE", "0.25"),
    "/simulate": os.getenv("X402_PRICE_SIMULATE", "0.15"),
    "/invariant-guard": os.getenv("X402_PRICE_INVARIANT", "0.10"),
    "/circuit-breaker": os.getenv("X402_PRICE_CIRCUIT", "0.10"),
    "/policy-lint": os.getenv("X402_PRICE_POLICY_LINT", "0.05"),
    "/eu-ai-log": os.getenv("X402_PRICE_EU_AI_LOG", "0.10"),
}

# ---------------------------------------------------------------------------
# Bundle tier definitions
# ---------------------------------------------------------------------------

_SCOUT_ENDPOINTS: list[str] = ["/check", "/validate", "/scan"]

_SHIELD_ENDPOINTS: list[str] = [
    *_SCOUT_ENDPOINTS,
    "/audit",
    "/classify-risk",
    "/trust",
    "/anomaly",
    "/explain",
]

_FORTRESS_ENDPOINTS: list[str] = [
    *_SHIELD_ENDPOINTS,
    "/certify",
    "/compliance",
    "/simulate",
    "/invariant-guard",
    "/circuit-breaker",
    "/policy-lint",
    "/eu-ai-log",
]

_BUNDLE_PRICES: dict[str, str] = {
    "scout": os.getenv("X402_PRICE_BUNDLE_SCOUT", "0.05"),
    "shield": os.getenv("X402_PRICE_BUNDLE_SHIELD", "0.25"),
    "fortress": os.getenv("X402_PRICE_BUNDLE_FORTRESS", "1.00"),
}

_BUNDLE_ENDPOINT_LISTS: dict[str, list[str]] = {
    "scout": _SCOUT_ENDPOINTS,
    "shield": _SHIELD_ENDPOINTS,
    "fortress": _FORTRESS_ENDPOINTS,
}


# ---------------------------------------------------------------------------
# Savings calculation
# ---------------------------------------------------------------------------


def _individual_total(endpoints: list[str]) -> Decimal:
    """Sum the individual prices for a list of endpoint slugs."""
    return sum(
        (Decimal(str(_ENDPOINT_PRICES.get(ep, "0"))) for ep in endpoints),
        Decimal("0"),
    )


def _savings_pct(bundle_price: Decimal, individual_total: Decimal) -> float:
    """Return percentage savings vs buying endpoints individually."""
    if individual_total <= 0:
        return 0.0
    saved = individual_total - bundle_price
    pct = (saved / individual_total * Decimal("100")).quantize(
        Decimal("0.1"),
        rounding=ROUND_HALF_UP,
    )
    return float(max(pct, Decimal("0")))


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class Bundle(BaseModel):
    """Describes a priced bundle of x402 governance endpoints."""

    name: str = Field(..., description="Bundle tier name")
    price_usd: str = Field(..., description="Bundle price in USD")
    endpoints: list[str] = Field(
        ...,
        description="Included endpoint paths (relative to /x402)",
    )
    endpoint_count: int = Field(..., description="Number of included endpoints")
    individual_total_usd: str = Field(
        ...,
        description="Sum of individual endpoint prices",
    )
    savings_vs_individual: float = Field(
        ...,
        description="Percentage saved vs purchasing individually",
    )
    description: str = Field(default="", description="Human-readable tier summary")


class BundleRequest(BaseModel):
    """Request body for executing a bundle."""

    action: str = Field(
        ...,
        max_length=5000,
        description="Action string to evaluate",
    )
    agent_id: str = Field(default="anonymous", max_length=200)
    context: dict[str, Any] = Field(default_factory=dict)

    @field_validator("context")
    @classmethod
    def cap_context_size(cls, v: dict[str, Any]) -> dict[str, Any]:
        if len(json.dumps(v, separators=(",", ":"))) > 50_000:
            raise ValueError("context payload exceeds 50KB limit")
        return v


class BundleResultResponse(BaseModel):
    """Combined results from all endpoints in the bundle."""

    bundle: str
    price_usd: str
    savings_vs_individual: float
    results: dict[str, Any]
    endpoint_count: int
    succeeded: int
    failed: int
    constitutional_hash: str
    processing_ms: int
    disclaimer: str | None = None


# ---------------------------------------------------------------------------
# Build the BUNDLES registry
# ---------------------------------------------------------------------------

_BUNDLE_DESCRIPTIONS: dict[str, str] = {
    "scout": "Basic safety check package: quick check, validation, and injection scan.",
    "shield": (
        "Full risk analysis: Scout tier plus audit, risk classification, "
        "trust scoring, anomaly detection, and decision explainability."
    ),
    "fortress": (
        "Enterprise compliance suite: Shield tier plus signed attestation, "
        "multi-framework compliance, policy simulation, invariant enforcement, "
        "circuit breaker, policy lint, and EU AI Act logging."
    ),
}


def _build_bundles() -> dict[str, Bundle]:
    """Construct the immutable BUNDLES mapping at import time."""
    bundles: dict[str, Bundle] = {}
    for tier_name, endpoints in _BUNDLE_ENDPOINT_LISTS.items():
        bundle_price = Decimal(str(_BUNDLE_PRICES[tier_name]))
        indiv_total = _individual_total(endpoints)
        bundles[tier_name] = Bundle(
            name=tier_name,
            price_usd=str(bundle_price),
            endpoints=list(endpoints),
            endpoint_count=len(endpoints),
            individual_total_usd=str(indiv_total),
            savings_vs_individual=_savings_pct(bundle_price, indiv_total),
            description=_BUNDLE_DESCRIPTIONS.get(tier_name, ""),
        )
    return bundles


BUNDLES: dict[str, Bundle] = _build_bundles()


# ---------------------------------------------------------------------------
# Per-endpoint evaluation functions (direct calls, not HTTP)
# ---------------------------------------------------------------------------


async def _eval_check(action: str, context: dict[str, Any]) -> dict[str, Any]:
    """Run the free /check evaluation logic."""
    from .x402_governance import _evaluate_action

    result = _evaluate_action(action, context, detailed=True)
    return {
        "compliant": result["compliant"],
        "decision": result["decision"],
        "risk_level": result["risk_level"],
        "total_violations": len(result["violations"]),
    }


async def _eval_validate(action: str, context: dict[str, Any]) -> dict[str, Any]:
    """Run the /validate evaluation logic."""
    from .x402_governance import _evaluate_action

    return _evaluate_action(action, context)


async def _eval_scan(action: str, context: dict[str, Any]) -> dict[str, Any]:
    """Run the /scan injection detection logic."""
    from .x402_marketplace import _get_injection_detector

    detector = _get_injection_detector()
    if detector is None:
        return {"error": "Injection detector unavailable", "is_injection": None}

    result = detector.detect(action, context or None)
    return {
        "is_injection": result.is_injection,
        "severity": result.severity.value if result.severity else None,
        "injection_type": (result.injection_type.value if result.injection_type else None),
        "confidence": result.confidence,
        "matched_patterns": result.matched_patterns,
    }


async def _eval_audit(action: str, context: dict[str, Any]) -> dict[str, Any]:
    """Run the /audit evaluation logic."""
    from .x402_governance import _evaluate_action

    return _evaluate_action(action, context, detailed=True)


async def _eval_classify_risk(
    action: str,
    _context: dict[str, Any],
) -> dict[str, Any]:
    """Run the /classify-risk evaluation logic."""
    from .x402_marketplace import _get_risk_classifier

    classifier = _get_risk_classifier()
    if classifier is None:
        return {"error": "Risk classifier unavailable"}

    try:
        from acgs_lite.eu_ai_act.risk_classification import SystemDescription

        desc = SystemDescription(
            system_id="bundle-eval",
            purpose=action,
            domain="general",
        )
        result = classifier.classify(desc)
        return result.to_dict()
    except ImportError:
        return {"error": "Risk classification module unavailable"}


async def _eval_trust(action: str, _context: dict[str, Any]) -> dict[str, Any]:
    """Run the /trust scoring logic (query-only in bundle context)."""
    from .x402_marketplace import _get_trust_manager

    manager = _get_trust_manager()
    if manager is None:
        return {"error": "Trust manager unavailable"}

    agent_id = "bundle-eval"
    return {
        "agent_id": agent_id,
        "action": "query",
        "score": manager.score(agent_id),
        "tier": manager.tier(agent_id),
    }


async def _eval_anomaly(action: str, _context: dict[str, Any]) -> dict[str, Any]:
    """Run the /anomaly detection logic."""
    from .x402_marketplace import _get_anomaly_detector

    detector = _get_anomaly_detector()
    if detector is None:
        return {"error": "Anomaly detector unavailable"}

    signals = detector.record_decision(
        outcome="allow",
        agent_id="bundle-eval",
        severity="low",
    )
    return {
        "anomalies": [s.to_dict() for s in signals],
        "anomaly_count": len(signals),
        "stats": detector.stats(),
    }


async def _eval_explain(action: str, context: dict[str, Any]) -> dict[str, Any]:
    """Run the /explain decision explainability logic."""
    try:
        from acgs_lite.constitution import Constitution
        from acgs_lite.constitution.decision_explainer import (
            explain_decision as _explain,
        )

        constitution = Constitution.from_template("default")
        result = constitution.validate(action, context)
        explanation = _explain(result, constitution=constitution, detail_level="standard")
        return (
            explanation.to_dict()
            if hasattr(explanation, "to_dict")
            else {"explanation": str(explanation)}
        )
    except ImportError:
        return {"error": "Decision explainer unavailable"}


async def _eval_certify(action: str, context: dict[str, Any]) -> dict[str, Any]:
    """Run the /certify signed attestation logic."""
    from .x402_governance import _evaluate_action, _sign_receipt

    result = _evaluate_action(action, context, detailed=True)
    attestation = _sign_receipt(result)
    return {
        **result,
        "attestation": attestation.model_dump(),
    }


async def _eval_compliance(
    action: str,
    _context: dict[str, Any],
) -> dict[str, Any]:
    """Run the /compliance multi-framework assessment logic."""
    try:
        from acgs_lite.compliance.multi_framework import MultiFrameworkAssessor

        assessor = MultiFrameworkAssessor()
        system_desc = {
            "system_id": "bundle-eval",
            "purpose": action,
            "domain": "general",
            "jurisdiction": "",
        }
        report = assessor.assess(system_desc)
        return report.to_dict()
    except ImportError:
        return {"error": "Compliance module unavailable"}


async def _eval_simulate(action: str, context: dict[str, Any]) -> dict[str, Any]:
    """Run the /simulate policy change simulation logic."""
    try:
        from acgs_lite.constitution import Constitution
        from acgs_lite.constitution.policy_simulator import GovernancePolicySimulator

        baseline = Constitution.from_template("default")
        candidate = Constitution.from_template("strict")
        simulator = GovernancePolicySimulator()
        report = simulator.evaluate_single(
            baseline=baseline,
            candidate=candidate,
            actions=[action],
            context=context or None,
        )
        return report.to_dict()
    except ImportError:
        return {"error": "Policy simulator unavailable"}


async def _eval_invariant_guard(
    action: str,
    context: dict[str, Any],
) -> dict[str, Any]:
    """Run the /invariant-guard three-tier invariant enforcement logic."""
    from .x402_marketplace import _get_invariant_guard

    guard = _get_invariant_guard()
    if guard is None:
        return {"error": "InvariantGuard unavailable"}

    try:
        result = guard.check(
            action=action,
            agent_id="bundle-eval",
            tier="all",
            context=context or None,
        )
        return result.to_dict() if hasattr(result, "to_dict") else {"result": str(result)}
    except Exception:
        logger.exception("invariant_guard_eval_failed")
        return {"error": "Invariant check failed"}


async def _eval_circuit_breaker(
    action: str,
    context: dict[str, Any],
) -> dict[str, Any]:
    """Run the /circuit-breaker governance circuit breaker logic."""
    from .x402_marketplace import _get_circuit_breaker

    breaker = _get_circuit_breaker()
    if breaker is None:
        return {"error": "GovernanceCircuitBreaker unavailable"}

    try:
        result = breaker.evaluate(
            agent_id="bundle-eval",
            action=action,
            severity="medium",
            context=context or None,
        )
        return result.to_dict() if hasattr(result, "to_dict") else {"result": str(result)}
    except Exception:
        logger.exception("circuit_breaker_eval_failed")
        return {"error": "Circuit breaker evaluation failed"}


async def _eval_policy_lint(
    action: str,
    _context: dict[str, Any],
) -> dict[str, Any]:
    """Run the /policy-lint policy quality scan logic."""
    from .x402_marketplace import _get_policy_linter

    linter = _get_policy_linter()
    if linter is None:
        return {"error": "PolicyLinter unavailable"}

    try:
        result = linter.lint(rules=[action], strict=False)
        return result.to_dict() if hasattr(result, "to_dict") else {"result": str(result)}
    except Exception:
        logger.exception("policy_lint_eval_failed")
        return {"error": "Policy lint failed"}


async def _eval_eu_ai_log(
    action: str,
    context: dict[str, Any],
) -> dict[str, Any]:
    """Run the /eu-ai-log Article 12 logging logic."""
    from .x402_marketplace import _get_article12_logger

    art12 = _get_article12_logger()
    if art12 is None:
        return {"error": "Article12Logger unavailable"}

    try:
        result = art12.log_decision(
            system_id="bundle-eval",
            decision=action,
            risk_level="unknown",
            agent_id="bundle-eval",
            context=context or None,
        )
        return result.to_dict() if hasattr(result, "to_dict") else {"result": str(result)}
    except Exception:
        logger.exception("eu_ai_log_eval_failed")
        return {"error": "Article 12 logging failed"}


# ---------------------------------------------------------------------------
# Endpoint slug -> evaluation function mapping
# ---------------------------------------------------------------------------

_EVALUATORS: dict[str, Any] = {
    "/check": _eval_check,
    "/validate": _eval_validate,
    "/scan": _eval_scan,
    "/audit": _eval_audit,
    "/classify-risk": _eval_classify_risk,
    "/trust": _eval_trust,
    "/anomaly": _eval_anomaly,
    "/explain": _eval_explain,
    "/certify": _eval_certify,
    "/compliance": _eval_compliance,
    "/simulate": _eval_simulate,
    "/invariant-guard": _eval_invariant_guard,
    "/circuit-breaker": _eval_circuit_breaker,
    "/policy-lint": _eval_policy_lint,
    "/eu-ai-log": _eval_eu_ai_log,
}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/bundles")
async def list_bundles() -> dict[str, Any]:
    """
    List available endpoint bundles — FREE.

    Returns all bundle tiers with pricing, included endpoints,
    and percentage savings vs purchasing individually.
    """
    return {
        "bundles": {name: bundle.model_dump() for name, bundle in BUNDLES.items()},
        "constitutional_hash": CONSTITUTIONAL_HASH,
        "note": (
            "Use POST /x402/bundle/{bundle_name} with an action string "
            "to execute all endpoints in a bundle with a single payment."
        ),
    }


@router.post("/bundle/{bundle_name}")
async def execute_bundle(
    bundle_name: str,
    request: Request,
    body: BundleRequest,
) -> BundleResultResponse:
    """
    Execute an endpoint bundle — single payment runs all included endpoints.

    Scout  ($0.05): /check + /validate + /scan
    Shield ($0.25): Scout + /audit + /classify-risk + /trust + /anomaly + /explain
    Fortress ($1.00): Shield + /certify + /compliance + /simulate
                       + /invariant-guard + /circuit-breaker + /policy-lint + /eu-ai-log
    """
    bundle_key = bundle_name.lower().strip()
    bundle = BUNDLES.get(bundle_key)
    if bundle is None:
        available = ", ".join(sorted(BUNDLES.keys()))
        raise HTTPException(
            status_code=404,
            detail=f"Bundle '{bundle_name}' not found. Available: {available}",
        )

    t0 = time.monotonic()
    results: dict[str, Any] = {}
    succeeded = 0
    failed = 0

    # Run all endpoint evaluators concurrently
    async def _run_one(endpoint: str) -> tuple[str, dict[str, Any], bool]:
        evaluator = _EVALUATORS.get(endpoint)
        if evaluator is None:
            return endpoint, {"error": f"No evaluator for {endpoint}"}, False
        try:
            result = await evaluator(body.action, body.context)
            has_error = isinstance(result, dict) and "error" in result
            return endpoint, result, not has_error
        except Exception:
            logger.exception("bundle_evaluator_failed", endpoint=endpoint)
            return endpoint, {"error": "Evaluator failed"}, False

    tasks = [_run_one(ep) for ep in bundle.endpoints]
    completed = await asyncio.gather(*tasks)

    for endpoint, result, ok in completed:
        results[endpoint] = result
        if ok:
            succeeded += 1
        else:
            failed += 1

    processing_ms = int((time.monotonic() - t0) * 1000)

    logger.info(
        "x402 bundle execution",
        bundle=bundle_key,
        price_usd=bundle.price_usd,
        endpoints=bundle.endpoint_count,
        succeeded=succeeded,
        failed=failed,
        agent_id=body.agent_id,
        processing_ms=processing_ms,
    )

    x402_network = os.getenv("X402_NETWORK", "eip155:84532")
    x402_pay_to = os.getenv("EVM_ADDRESS", "")
    await emit_revenue_event(
        RevenueEvent(
            endpoint=f"/x402/bundle/{bundle_key}",
            price_usd=bundle.price_usd,
            agent_id=body.agent_id,
            decision=f"bundle:{succeeded}/{bundle.endpoint_count}",
            timestamp=datetime.now(UTC).isoformat(),
            processing_ms=processing_ms,
            network=x402_network,
            wallet_address=x402_pay_to,
        )
    )

    return BundleResultResponse(
        bundle=bundle_key,
        price_usd=bundle.price_usd,
        savings_vs_individual=bundle.savings_vs_individual,
        results=results,
        endpoint_count=bundle.endpoint_count,
        succeeded=succeeded,
        failed=failed,
        constitutional_hash=CONSTITUTIONAL_HASH,
        processing_ms=processing_ms,
        disclaimer=PAID_RESPONSE_DISCLAIMER,
    )
