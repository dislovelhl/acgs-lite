"""
x402 AI Governance Marketplace — Premium Paid Endpoints

Constitutional Hash: cdd01ef066bc6cf2

Wraps production ACGS-2 modules behind x402 micropayments.
Every endpoint is pure profit: existing code, zero marginal compute,
zero facilitator fees (xpay.sh).

Pricing (market-rate, env-configurable):
    POST /x402/scan             $0.03  Prompt injection detection
    POST /x402/classify-risk    $0.10  EU AI Act risk classification
    POST /x402/compliance       $0.25  Multi-framework compliance (8 frameworks)
    POST /x402/simulate         $0.15  Policy change simulation
    POST /x402/trust            $0.02  Agent trust scoring
    POST /x402/anomaly          $0.03  Governance anomaly detection
    POST /x402/explain          $0.05  Decision explainability
    POST /x402/invariant-guard  $0.10  Three-tier invariant enforcement
    POST /x402/circuit-breaker  $0.10  Governance circuit breaker
    POST /x402/policy-lint      $0.05  Policy quality/security scan
    POST /x402/eu-ai-log        $0.10  EU AI Act Article 12 logging

All endpoints: x402 payment = authentication. No JWT required.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.structured_logging import get_logger

from ._x402_common import PAID_RESPONSE_DISCLAIMER, build_related_endpoint
from ._x402_revenue import RevenueEvent, emit_revenue_event

logger = get_logger(__name__)

router = APIRouter(prefix="/x402", tags=["x402-marketplace"])

X402_NETWORK = os.getenv("X402_NETWORK", "eip155:84532")
X402_PAY_TO = os.getenv("EVM_ADDRESS", "")

# ---------------------------------------------------------------------------
# Configurable pricing — env vars override defaults
# ---------------------------------------------------------------------------
X402_PRICE_SCAN = os.getenv("X402_PRICE_SCAN", "0.03")
X402_PRICE_CLASSIFY_RISK = os.getenv("X402_PRICE_CLASSIFY_RISK", "0.10")
X402_PRICE_COMPLIANCE = os.getenv("X402_PRICE_COMPLIANCE", "0.25")
X402_PRICE_SIMULATE = os.getenv("X402_PRICE_SIMULATE", "0.15")
X402_PRICE_TRUST = os.getenv("X402_PRICE_TRUST", "0.02")
X402_PRICE_ANOMALY = os.getenv("X402_PRICE_ANOMALY", "0.03")
X402_PRICE_EXPLAIN = os.getenv("X402_PRICE_EXPLAIN", "0.05")
X402_PRICE_INVARIANT = os.getenv("X402_PRICE_INVARIANT", "0.10")
X402_PRICE_CIRCUIT = os.getenv("X402_PRICE_CIRCUIT", "0.10")
X402_PRICE_POLICY_LINT = os.getenv("X402_PRICE_POLICY_LINT", "0.05")
X402_PRICE_EU_AI_LOG = os.getenv("X402_PRICE_EU_AI_LOG", "0.10")

# ---------------------------------------------------------------------------
# Lazy loaders — avoid import-time side effects, graceful fallback
# ---------------------------------------------------------------------------

_injection_detector = None
_risk_classifier = None
_trust_manager = None
_anomaly_detector = None
_invariant_guard = None
_circuit_breaker = None
_policy_linter = None
_article12_logger = None


def _get_injection_detector():
    global _injection_detector
    if _injection_detector is None:
        try:
            from enhanced_agent_bus.security.injection_detector import (
                PromptInjectionDetector,
            )

            _injection_detector = PromptInjectionDetector(strict_mode=True)
        except ImportError:
            logger.warning("PromptInjectionDetector unavailable")
    return _injection_detector


def _get_risk_classifier():
    global _risk_classifier
    if _risk_classifier is None:
        try:
            from acgs_lite.eu_ai_act.risk_classification import RiskClassifier

            _risk_classifier = RiskClassifier()
        except ImportError:
            logger.warning("RiskClassifier unavailable")
    return _risk_classifier


def _get_trust_manager():
    global _trust_manager
    if _trust_manager is None:
        try:
            from acgs_lite.constitution.trust_score import TrustScoreManager

            _trust_manager = TrustScoreManager()
        except ImportError:
            logger.warning("TrustScoreManager unavailable")
    return _trust_manager


def _get_anomaly_detector():
    global _anomaly_detector
    if _anomaly_detector is None:
        try:
            from acgs_lite.constitution.anomaly import GovernanceAnomalyDetector

            _anomaly_detector = GovernanceAnomalyDetector()
        except ImportError:
            logger.warning("GovernanceAnomalyDetector unavailable")
    return _anomaly_detector


def _get_invariant_guard():
    global _invariant_guard
    if _invariant_guard is None:
        try:
            from acgs_lite.constitution.invariant import InvariantGuard

            _invariant_guard = InvariantGuard()
        except ImportError:
            logger.warning("InvariantGuard unavailable")
    return _invariant_guard


def _get_circuit_breaker():
    global _circuit_breaker
    if _circuit_breaker is None:
        try:
            from acgs_lite.constitution.circuit_breaker import (
                GovernanceCircuitBreaker,
            )

            _circuit_breaker = GovernanceCircuitBreaker()
        except ImportError:
            logger.warning("GovernanceCircuitBreaker unavailable")
    return _circuit_breaker


def _get_policy_linter():
    global _policy_linter
    if _policy_linter is None:
        try:
            from acgs_lite.constitution.policy_linter import PolicyLinter

            _policy_linter = PolicyLinter()
        except ImportError:
            logger.warning("PolicyLinter unavailable")
    return _policy_linter


def _get_article12_logger():
    global _article12_logger
    if _article12_logger is None:
        try:
            from acgs_lite.eu_ai_act.article12_logger import Article12Logger

            _article12_logger = Article12Logger()
        except ImportError:
            logger.warning("Article12Logger unavailable")
    return _article12_logger


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class ScanRequest(BaseModel):
    content: str = Field(..., max_length=10000, description="Text to scan")
    context: dict[str, Any] = Field(default_factory=dict)


class ScanResponse(BaseModel):
    is_injection: bool
    severity: str | None
    injection_type: str | None
    confidence: float
    matched_patterns: list[str]
    sanitized_content: str | None
    constitutional_hash: str
    processing_ms: int


class RiskClassifyRequest(BaseModel):
    system_id: str = Field(..., max_length=200)
    purpose: str = Field(..., max_length=2000)
    domain: str = Field(..., max_length=200)
    autonomy_level: int = Field(default=0, ge=0, le=5)
    human_oversight: bool = True
    biometric_processing: bool = False
    critical_infrastructure: bool = False
    law_enforcement: bool = False
    education: bool = False
    employment: bool = False
    social_scoring: bool = False


class ComplianceRequest(BaseModel):
    system_id: str = Field(..., max_length=200)
    frameworks: list[str] = Field(
        default_factory=list,
        description="Frameworks to assess (empty = all applicable)",
    )
    jurisdiction: str = Field(default="", max_length=100)
    domain: str = Field(default="", max_length=200)
    purpose: str = Field(default="", max_length=2000)


class SimulateRequest(BaseModel):
    actions: list[str] = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Actions to simulate against policy change",
    )
    context: dict[str, Any] = Field(default_factory=dict)


class TrustRequest(BaseModel):
    agent_id: str = Field(..., max_length=200)
    compliant: bool | None = Field(
        default=None,
        description="Record a decision (null = query only)",
    )
    severity: str = Field(default="medium")


class AnomalyRequest(BaseModel):
    outcome: str = Field(..., description="Decision outcome (allow/deny)")
    agent_id: str = Field(..., max_length=200)
    rule_ids: list[str] = Field(default_factory=list)
    severity: str = Field(default="low")


class ExplainRequest(BaseModel):
    action: str = Field(..., max_length=5000)
    detail_level: str = Field(default="standard", pattern="^(brief|standard|verbose)$")
    context: dict[str, Any] = Field(default_factory=dict)


class InvariantGuardRequest(BaseModel):
    action: str = Field(..., max_length=5000, description="Action to check")
    agent_id: str = Field(default="anonymous", max_length=200)
    tier: str = Field(
        default="all",
        pattern="^(constitutional|operational|runtime|all)$",
        description="Invariant tier to enforce",
    )
    context: dict[str, Any] = Field(default_factory=dict)


class CircuitBreakerRequest(BaseModel):
    agent_id: str = Field(..., max_length=200)
    action: str = Field(..., max_length=5000)
    severity: str = Field(default="medium")
    context: dict[str, Any] = Field(default_factory=dict)


class PolicyLintRequest(BaseModel):
    rules: list[str] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Policy rules to lint",
    )
    strict: bool = Field(default=False, description="Enable strict mode")


class EUAIActLogRequest(BaseModel):
    system_id: str = Field(..., max_length=200)
    decision: str = Field(..., max_length=5000, description="Decision to log")
    risk_level: str = Field(default="unknown", max_length=50)
    agent_id: str = Field(default="anonymous", max_length=200)
    context: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Machine-readable discovery metadata
# ---------------------------------------------------------------------------


def _related_endpoints(
    current: str,
    decision: str | None = None,
    risk_level: str | None = None,
) -> list[dict[str, str]]:
    hints = []

    if current == "scan":
        hints.append(
            build_related_endpoint(
                endpoint="/x402/validate",
                method="POST",
                price_usd=os.getenv("X402_PRICE_VALIDATE", "0.01"),
                relation="full_result",
                reason="Run a full governance validation after the security scan.",
            )
        )
        if decision == "BLOCKED":
            hints.append(
                build_related_endpoint(
                    endpoint="/x402/explain",
                    method="POST",
                    price_usd=X402_PRICE_EXPLAIN,
                    relation="explanation",
                    reason="Explain why the content was blocked.",
                )
            )
    elif current == "validate":
        if decision == "BLOCKED":
            hints.extend(
                [
                    build_related_endpoint(
                        endpoint="/x402/audit",
                        method="POST",
                        price_usd="0.05",
                        relation="deeper_analysis",
                        reason="Inspect the blocked action with category-level risk data.",
                    ),
                    build_related_endpoint(
                        endpoint="/x402/scan",
                        method="POST",
                        price_usd=X402_PRICE_SCAN,
                        relation="security_analysis",
                        reason="Check whether injection patterns triggered the failure.",
                    ),
                ]
            )
        else:
            hints.append(
                build_related_endpoint(
                    endpoint="/x402/certify",
                    method="POST",
                    price_usd="0.50",
                    relation="trust_proof",
                    reason="Produce a signed governance attestation for downstream verifiers.",
                )
            )
    elif current == "audit":
        if risk_level in ("HIGH", "CRITICAL"):
            hints.extend(
                [
                    build_related_endpoint(
                        endpoint="/x402/certify",
                        method="POST",
                        price_usd="0.50",
                        relation="trust_proof",
                        reason="Capture the audited result as a verifiable attestation.",
                    ),
                    build_related_endpoint(
                        endpoint="/x402/simulate",
                        method="POST",
                        price_usd=X402_PRICE_SIMULATE,
                        relation="policy_testing",
                        reason="Test tighter policy controls against similar actions.",
                    ),
                ]
            )
    elif current == "classify-risk":
        hints.extend(
            [
                build_related_endpoint(
                    endpoint="/x402/compliance",
                    method="POST",
                    price_usd=X402_PRICE_COMPLIANCE,
                    relation="framework_assessment",
                    reason="Assess the system against multiple compliance frameworks.",
                ),
                build_related_endpoint(
                    endpoint="/x402/eu-ai-log",
                    method="POST",
                    price_usd=X402_PRICE_EU_AI_LOG,
                    relation="record_keeping",
                    reason="Log the decision for Article 12 record-keeping.",
                ),
            ]
        )
    elif current == "compliance":
        hints.extend(
            [
                build_related_endpoint(
                    endpoint="/x402/certify",
                    method="POST",
                    price_usd="0.50",
                    relation="trust_proof",
                    reason="Create a signed proof of the compliance assessment.",
                ),
                build_related_endpoint(
                    endpoint="/x402/simulate",
                    method="POST",
                    price_usd=X402_PRICE_SIMULATE,
                    relation="policy_testing",
                    reason="Test policy changes before rollout.",
                ),
            ]
        )
    elif current == "trust":
        hints.append(
            build_related_endpoint(
                endpoint="/x402/anomaly",
                method="POST",
                price_usd=X402_PRICE_ANOMALY,
                relation="behavior_monitoring",
                reason="Inspect agent behavior for anomalous governance patterns.",
            )
        )
    elif current == "anomaly":
        hints.append(
            build_related_endpoint(
                endpoint="/x402/circuit-breaker",
                method="POST",
                price_usd=X402_PRICE_CIRCUIT,
                relation="fail_safe",
                reason="Escalate detected anomalies into active safety controls.",
            )
        )
    elif current == "explain":
        hints.append(
            build_related_endpoint(
                endpoint="/x402/compliance",
                method="POST",
                price_usd=X402_PRICE_COMPLIANCE,
                relation="framework_assessment",
                reason="Extend the explanation into a broader compliance assessment.",
            )
        )
    elif current == "invariant-guard":
        hints.append(
            build_related_endpoint(
                endpoint="/x402/circuit-breaker",
                method="POST",
                price_usd=X402_PRICE_CIRCUIT,
                relation="fail_safe",
                reason="Escalate invariant violations into circuit-breaker enforcement.",
            )
        )
    elif current == "circuit-breaker":
        hints.append(
            build_related_endpoint(
                endpoint="/x402/anomaly",
                method="POST",
                price_usd=X402_PRICE_ANOMALY,
                relation="behavior_monitoring",
                reason="Review the anomaly signals that informed the breaker state.",
            )
        )
    elif current == "policy-lint":
        hints.append(
            build_related_endpoint(
                endpoint="/x402/simulate",
                method="POST",
                price_usd=X402_PRICE_SIMULATE,
                relation="policy_testing",
                reason="Test the linted policy changes before rollout.",
            )
        )
    elif current == "eu-ai-log":
        hints.append(
            build_related_endpoint(
                endpoint="/x402/classify-risk",
                method="POST",
                price_usd=X402_PRICE_CLASSIFY_RISK,
                relation="risk_analysis",
                reason="Tie the log entry back to a formal EU AI Act risk level.",
            )
        )

    return [item.model_dump() for item in hints]


# ===================================================================
# PAID ENDPOINTS
# ===================================================================


@router.post("/scan")
async def scan_injection(request: Request, body: ScanRequest) -> dict[str, Any]:
    """
    Prompt injection detection — $0.03/call.

    Production-grade multi-pattern scanner detecting instruction override,
    jailbreak, persona override, context poisoning, encoding bypass.
    Every AI agent needs this.
    """
    start = datetime.now(UTC)
    detector = _get_injection_detector()

    if detector is None:
        raise HTTPException(503, "Injection detector unavailable")

    result = detector.detect(body.content, body.context or None)
    elapsed = datetime.now(UTC) - start

    logger.info(
        "x402 injection scan",
        is_injection=result.is_injection,
        severity=str(result.severity) if result.severity else None,
        processing_ms=int(elapsed.total_seconds() * 1000),
    )

    decision = "BLOCKED" if result.is_injection else "CLEAN"
    ms = int(elapsed.total_seconds() * 1000)
    await emit_revenue_event(RevenueEvent(
        endpoint="/x402/scan", price_usd=X402_PRICE_SCAN, agent_id="anonymous",
        decision=decision, timestamp=datetime.now(UTC).isoformat(),
        processing_ms=ms, network=X402_NETWORK, wallet_address=X402_PAY_TO,
    ))
    return {
        "is_injection": result.is_injection,
        "severity": result.severity.value if result.severity else None,
        "injection_type": (result.injection_type.value if result.injection_type else None),
        "confidence": result.confidence,
        "matched_patterns": result.matched_patterns,
        "sanitized_content": result.sanitized_content,
        "constitutional_hash": CONSTITUTIONAL_HASH,
        "processing_ms": ms,
        "disclaimer": PAID_RESPONSE_DISCLAIMER,
        "related_endpoints": _related_endpoints("scan", decision=decision),
    }


@router.post("/classify-risk")
async def classify_risk(
    request: Request,
    body: RiskClassifyRequest,
) -> dict[str, Any]:
    """
    EU AI Act risk classification — $0.10/call.

    Classifies AI systems per Article 6 and Annex III into
    UNACCEPTABLE / HIGH_RISK / LIMITED_RISK / MINIMAL_RISK.
    Returns regulatory obligations and compliance deadlines.
    """
    start = datetime.now(UTC)
    classifier = _get_risk_classifier()

    if classifier is None:
        raise HTTPException(503, "Risk classifier unavailable")

    try:
        from acgs_lite.eu_ai_act.risk_classification import SystemDescription

        desc = SystemDescription(
            system_id=body.system_id,
            purpose=body.purpose,
            domain=body.domain,
            autonomy_level=body.autonomy_level,
            human_oversight=body.human_oversight,
            biometric_processing=body.biometric_processing,
            critical_infrastructure=body.critical_infrastructure,
            law_enforcement=body.law_enforcement,
            education=body.education,
            employment=body.employment,
            social_scoring=body.social_scoring,
        )
        result = classifier.classify(desc)
    except ImportError as exc:
        raise HTTPException(503, "Risk classification module unavailable") from exc

    elapsed = datetime.now(UTC) - start

    logger.info(
        "x402 risk classification",
        system_id=body.system_id,
        risk_level=result.level.value,
        processing_ms=int(elapsed.total_seconds() * 1000),
    )

    ms = int(elapsed.total_seconds() * 1000)
    output = result.to_dict()
    output["constitutional_hash"] = CONSTITUTIONAL_HASH
    output["processing_ms"] = ms
    output["disclaimer"] = PAID_RESPONSE_DISCLAIMER
    output["related_endpoints"] = _related_endpoints("classify-risk")
    await emit_revenue_event(RevenueEvent(
        endpoint="/x402/classify-risk", price_usd=X402_PRICE_CLASSIFY_RISK,
        agent_id=body.system_id, decision=result.level.value,
        timestamp=datetime.now(UTC).isoformat(), processing_ms=ms,
        network=X402_NETWORK, wallet_address=X402_PAY_TO,
    ))
    return output


@router.post("/compliance")
async def assess_compliance(
    request: Request,
    body: ComplianceRequest,
) -> dict[str, Any]:
    """
    Multi-framework compliance assessment — $0.25/call.

    Assesses against 8 frameworks: GDPR, HIPAA-AI, ISO 42001,
    NIST AI RMF, NYC LL 144, OECD AI, SOC2-AI, Fair Lending.
    Returns per-framework scores, gaps, and recommendations.
    """
    start = datetime.now(UTC)

    try:
        from acgs_lite.compliance.multi_framework import MultiFrameworkAssessor

        frameworks = body.frameworks or None
        assessor = MultiFrameworkAssessor(frameworks=frameworks)

        system_desc = {
            "system_id": body.system_id,
            "jurisdiction": body.jurisdiction,
            "domain": body.domain,
            "purpose": body.purpose,
        }
        report = assessor.assess(system_desc)
    except ImportError as exc:
        raise HTTPException(503, "Compliance module unavailable") from exc

    elapsed = datetime.now(UTC) - start

    logger.info(
        "x402 compliance assessment",
        system_id=body.system_id,
        overall_score=report.overall_score,
        frameworks=len(report.frameworks_assessed),
        processing_ms=int(elapsed.total_seconds() * 1000),
    )

    ms = int(elapsed.total_seconds() * 1000)
    output = report.to_dict()
    output["constitutional_hash"] = CONSTITUTIONAL_HASH
    output["processing_ms"] = ms
    output["disclaimer"] = PAID_RESPONSE_DISCLAIMER
    output["related_endpoints"] = _related_endpoints("compliance")
    await emit_revenue_event(RevenueEvent(
        endpoint="/x402/compliance", price_usd=X402_PRICE_COMPLIANCE,
        agent_id=body.system_id, decision=f"score:{report.overall_score}",
        timestamp=datetime.now(UTC).isoformat(), processing_ms=ms,
        network=X402_NETWORK, wallet_address=X402_PAY_TO,
    ))
    return output


@router.post("/simulate")
async def simulate_policy(
    request: Request,
    body: SimulateRequest,
) -> dict[str, Any]:
    """
    Policy change simulation — $0.15/call.

    What-if analysis: how would a policy change affect existing actions?
    Returns blast radius, regressions, risk levels, and go/no-go recommendation.
    """
    start = datetime.now(UTC)

    try:
        from acgs_lite.constitution import Constitution
        from acgs_lite.constitution.policy_simulator import GovernancePolicySimulator

        baseline = Constitution.from_template("default")
        candidate = Constitution.from_template("strict")

        simulator = GovernancePolicySimulator()
        report = simulator.evaluate_single(
            baseline=baseline,
            candidate=candidate,
            actions=body.actions,
            context=body.context or None,
        )
    except ImportError as exc:
        raise HTTPException(503, "Policy simulator unavailable") from exc
    except Exception as exc:
        raise HTTPException(422, f"Simulation failed: {exc}") from exc

    elapsed = datetime.now(UTC) - start

    logger.info(
        "x402 policy simulation",
        actions=len(body.actions),
        recommendation=report.recommendation,
        blast_radius=report.blast_radius,
        processing_ms=int(elapsed.total_seconds() * 1000),
    )

    ms = int(elapsed.total_seconds() * 1000)
    output = report.to_dict()
    output["constitutional_hash"] = CONSTITUTIONAL_HASH
    output["processing_ms"] = ms
    output["disclaimer"] = PAID_RESPONSE_DISCLAIMER
    output["related_endpoints"] = _related_endpoints("simulate")
    await emit_revenue_event(RevenueEvent(
        endpoint="/x402/simulate", price_usd=X402_PRICE_SIMULATE,
        agent_id="anonymous", decision=report.recommendation,
        timestamp=datetime.now(UTC).isoformat(), processing_ms=ms,
        network=X402_NETWORK, wallet_address=X402_PAY_TO,
    ))
    return output


@router.post("/trust")
async def trust_score(request: Request, body: TrustRequest) -> dict[str, Any]:
    """
    Agent trust scoring — $0.02/call.

    Query or update per-agent trust scores (0.0-1.0).
    Tiers: TRUSTED / MONITORED / RESTRICTED.
    """
    start = datetime.now(UTC)
    manager = _get_trust_manager()

    if manager is None:
        raise HTTPException(503, "Trust manager unavailable")

    if body.compliant is not None:
        event = manager.record_decision(
            body.agent_id,
            compliant=body.compliant,
            severity=body.severity,
        )
        result = {
            "agent_id": body.agent_id,
            "action": "record_decision",
            "score": event.score_after,
            "delta": event.delta,
            "tier": manager.tier(body.agent_id),
        }
    else:
        result = {
            "agent_id": body.agent_id,
            "action": "query",
            "score": manager.score(body.agent_id),
            "tier": manager.tier(body.agent_id),
        }

    elapsed = datetime.now(UTC) - start
    result["constitutional_hash"] = CONSTITUTIONAL_HASH
    result["processing_ms"] = int(elapsed.total_seconds() * 1000)
    result["disclaimer"] = PAID_RESPONSE_DISCLAIMER
    result["related_endpoints"] = _related_endpoints("trust")

    logger.info(
        "x402 trust score",
        **{
            k: v
            for k, v in result.items()
            if k not in ("constitutional_hash", "disclaimer", "related_endpoints")
        },
    )
    await emit_revenue_event(RevenueEvent(
        endpoint="/x402/trust", price_usd=X402_PRICE_TRUST,
        agent_id=body.agent_id, decision=result.get("action", "query"),
        timestamp=datetime.now(UTC).isoformat(),
        processing_ms=result["processing_ms"],
        network=X402_NETWORK, wallet_address=X402_PAY_TO,
    ))
    return result


@router.post("/anomaly")
async def detect_anomaly(request: Request, body: AnomalyRequest) -> dict[str, Any]:
    """
    Governance anomaly detection — $0.03/call.

    Statistical anomaly detection: decision distribution shifts,
    agent concentration spikes, unusual denial rates.
    """
    start = datetime.now(UTC)
    detector = _get_anomaly_detector()

    if detector is None:
        raise HTTPException(503, "Anomaly detector unavailable")

    signals = detector.record_decision(
        outcome=body.outcome,
        agent_id=body.agent_id,
        rule_ids=body.rule_ids or None,
        severity=body.severity,
    )

    elapsed = datetime.now(UTC) - start

    logger.info(
        "x402 anomaly detection",
        agent_id=body.agent_id,
        anomalies_detected=len(signals),
        processing_ms=int(elapsed.total_seconds() * 1000),
    )

    ms = int(elapsed.total_seconds() * 1000)
    await emit_revenue_event(RevenueEvent(
        endpoint="/x402/anomaly", price_usd=X402_PRICE_ANOMALY,
        agent_id=body.agent_id, decision=f"anomalies:{len(signals)}",
        timestamp=datetime.now(UTC).isoformat(), processing_ms=ms,
        network=X402_NETWORK, wallet_address=X402_PAY_TO,
    ))
    return {
        "anomalies": [s.to_dict() for s in signals],
        "anomaly_count": len(signals),
        "stats": detector.stats(),
        "constitutional_hash": CONSTITUTIONAL_HASH,
        "processing_ms": ms,
        "disclaimer": PAID_RESPONSE_DISCLAIMER,
        "related_endpoints": _related_endpoints("anomaly"),
    }


@router.post("/explain")
async def explain_decision(request: Request, body: ExplainRequest) -> dict[str, Any]:
    """
    Decision explainability — $0.05/call.

    Human-readable explanation of why an action was approved/blocked.
    Includes blocking rules, risk categories, and remediation hints.
    """
    start = datetime.now(UTC)

    try:
        from acgs_lite.constitution import Constitution
        from acgs_lite.constitution.decision_explainer import explain_decision as _explain

        constitution = Constitution.from_template("default")
        result = constitution.validate(body.action, body.context)
        explanation = _explain(
            result,
            constitution=constitution,
            detail_level=body.detail_level,
        )
    except ImportError as exc:
        raise HTTPException(503, "Decision explainer unavailable") from exc
    except Exception as exc:
        raise HTTPException(422, f"Explanation failed: {exc}") from exc

    elapsed = datetime.now(UTC) - start

    logger.info(
        "x402 decision explanation",
        detail_level=body.detail_level,
        processing_ms=int(elapsed.total_seconds() * 1000),
    )

    ms = int(elapsed.total_seconds() * 1000)
    output = (
        explanation.to_dict()
        if hasattr(explanation, "to_dict")
        else {"explanation": str(explanation)}
    )
    output["constitutional_hash"] = CONSTITUTIONAL_HASH
    output["processing_ms"] = ms
    output["disclaimer"] = PAID_RESPONSE_DISCLAIMER
    output["related_endpoints"] = _related_endpoints("explain")
    await emit_revenue_event(RevenueEvent(
        endpoint="/x402/explain", price_usd=X402_PRICE_EXPLAIN,
        agent_id="anonymous", decision="explained",
        timestamp=datetime.now(UTC).isoformat(), processing_ms=ms,
        network=X402_NETWORK, wallet_address=X402_PAY_TO,
    ))
    return output


# ===================================================================
# PREMIUM ENDPOINTS — high-value governance modules
# ===================================================================


@router.post("/invariant-guard")
async def invariant_guard(
    request: Request,
    body: InvariantGuardRequest,
) -> dict[str, Any]:
    """
    Three-tier invariant enforcement — $0.10/call.

    Enforces Constitutional, Operational, and Runtime invariants.
    Returns violations per tier with severity and remediation.
    Mission-critical safety for autonomous agents.
    """
    start = datetime.now(UTC)
    guard = _get_invariant_guard()

    if guard is None:
        raise HTTPException(503, "InvariantGuard unavailable")

    try:
        result = guard.check(
            action=body.action,
            agent_id=body.agent_id,
            tier=body.tier,
            context=body.context or None,
        )
    except Exception as exc:
        raise HTTPException(422, f"Invariant check failed: {exc}") from exc

    elapsed = datetime.now(UTC) - start
    output = result.to_dict() if hasattr(result, "to_dict") else {"result": str(result)}
    output["constitutional_hash"] = CONSTITUTIONAL_HASH
    output["processing_ms"] = int(elapsed.total_seconds() * 1000)
    output["disclaimer"] = PAID_RESPONSE_DISCLAIMER
    output["related_endpoints"] = _related_endpoints("invariant-guard")

    logger.info(
        "x402 invariant guard",
        agent_id=body.agent_id,
        tier=body.tier,
        processing_ms=output["processing_ms"],
    )
    await emit_revenue_event(RevenueEvent(
        endpoint="/x402/invariant-guard", price_usd=X402_PRICE_INVARIANT,
        agent_id=body.agent_id, decision="checked",
        timestamp=datetime.now(UTC).isoformat(),
        processing_ms=output["processing_ms"],
        network=X402_NETWORK, wallet_address=X402_PAY_TO,
    ))
    return output


@router.post("/circuit-breaker")
async def circuit_breaker(
    request: Request,
    body: CircuitBreakerRequest,
) -> dict[str, Any]:
    """
    Governance circuit breaker — $0.10/call.

    Fail-safe kill switch: tracks violation rates per agent and trips
    when thresholds are exceeded. Returns circuit state (CLOSED/OPEN/HALF_OPEN),
    violation count, and cooldown remaining.
    """
    start = datetime.now(UTC)
    breaker = _get_circuit_breaker()

    if breaker is None:
        raise HTTPException(503, "GovernanceCircuitBreaker unavailable")

    try:
        result = breaker.evaluate(
            agent_id=body.agent_id,
            action=body.action,
            severity=body.severity,
            context=body.context or None,
        )
    except Exception as exc:
        raise HTTPException(422, f"Circuit breaker failed: {exc}") from exc

    elapsed = datetime.now(UTC) - start
    output = result.to_dict() if hasattr(result, "to_dict") else {"result": str(result)}
    output["constitutional_hash"] = CONSTITUTIONAL_HASH
    output["processing_ms"] = int(elapsed.total_seconds() * 1000)
    output["disclaimer"] = PAID_RESPONSE_DISCLAIMER
    output["related_endpoints"] = _related_endpoints("circuit-breaker")

    logger.info(
        "x402 circuit breaker",
        agent_id=body.agent_id,
        processing_ms=output["processing_ms"],
    )
    await emit_revenue_event(RevenueEvent(
        endpoint="/x402/circuit-breaker", price_usd=X402_PRICE_CIRCUIT,
        agent_id=body.agent_id, decision="evaluated",
        timestamp=datetime.now(UTC).isoformat(),
        processing_ms=output["processing_ms"],
        network=X402_NETWORK, wallet_address=X402_PAY_TO,
    ))
    return output


@router.post("/policy-lint")
async def policy_lint(
    request: Request,
    body: PolicyLintRequest,
) -> dict[str, Any]:
    """
    Policy quality & security scan — $0.05/call.

    Lints governance rules for: contradictions, redundancy, gaps,
    overly permissive patterns, missing safeguards. Returns per-rule
    findings with severity and suggested fixes.
    """
    start = datetime.now(UTC)
    linter = _get_policy_linter()

    if linter is None:
        raise HTTPException(503, "PolicyLinter unavailable")

    try:
        result = linter.lint(rules=body.rules, strict=body.strict)
    except Exception as exc:
        raise HTTPException(422, f"Policy lint failed: {exc}") from exc

    elapsed = datetime.now(UTC) - start
    output = result.to_dict() if hasattr(result, "to_dict") else {"result": str(result)}
    output["constitutional_hash"] = CONSTITUTIONAL_HASH
    output["processing_ms"] = int(elapsed.total_seconds() * 1000)
    output["disclaimer"] = PAID_RESPONSE_DISCLAIMER
    output["related_endpoints"] = _related_endpoints("policy-lint")

    logger.info(
        "x402 policy lint",
        rules_count=len(body.rules),
        strict=body.strict,
        processing_ms=output["processing_ms"],
    )
    await emit_revenue_event(RevenueEvent(
        endpoint="/x402/policy-lint", price_usd=X402_PRICE_POLICY_LINT,
        agent_id="anonymous", decision="linted",
        timestamp=datetime.now(UTC).isoformat(),
        processing_ms=output["processing_ms"],
        network=X402_NETWORK, wallet_address=X402_PAY_TO,
    ))
    return output


@router.post("/eu-ai-log")
async def eu_ai_act_log(
    request: Request,
    body: EUAIActLogRequest,
) -> dict[str, Any]:
    """
    EU AI Act Article 12 logging — $0.10/call.

    Mandatory record-keeping for high-risk AI systems.
    Enforcement deadline: August 2, 2026.
    Logs decisions with full audit metadata for regulatory compliance.
    Returns log entry ID and compliance status.
    """
    start = datetime.now(UTC)
    art12 = _get_article12_logger()

    if art12 is None:
        raise HTTPException(503, "Article12Logger unavailable")

    try:
        result = art12.log_decision(
            system_id=body.system_id,
            decision=body.decision,
            risk_level=body.risk_level,
            agent_id=body.agent_id,
            context=body.context or None,
        )
    except Exception as exc:
        raise HTTPException(422, f"Article 12 logging failed: {exc}") from exc

    elapsed = datetime.now(UTC) - start
    output = result.to_dict() if hasattr(result, "to_dict") else {"result": str(result)}
    output["constitutional_hash"] = CONSTITUTIONAL_HASH
    output["processing_ms"] = int(elapsed.total_seconds() * 1000)
    output["disclaimer"] = PAID_RESPONSE_DISCLAIMER
    output["related_endpoints"] = _related_endpoints("eu-ai-log")

    logger.info(
        "x402 eu ai act article 12 log",
        system_id=body.system_id,
        risk_level=body.risk_level,
        processing_ms=output["processing_ms"],
    )
    await emit_revenue_event(RevenueEvent(
        endpoint="/x402/eu-ai-log", price_usd=X402_PRICE_EU_AI_LOG,
        agent_id=body.agent_id, decision=f"logged:{body.risk_level}",
        timestamp=datetime.now(UTC).isoformat(),
        processing_ms=output["processing_ms"],
        network=X402_NETWORK, wallet_address=X402_PAY_TO,
    ))
    return output
