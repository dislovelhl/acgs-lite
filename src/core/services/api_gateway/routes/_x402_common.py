from __future__ import annotations

import importlib
import os
from collections.abc import Mapping
from typing import Any, Final

from fastapi import FastAPI
from pydantic import BaseModel

from src.core.shared.structured_logging import get_logger

DEFAULT_ATTESTATION_SECRET: Final[str] = "acgs2-dev-key"
PAID_RESPONSE_DISCLAIMER: Final[str] = (
    "Informational governance signal only. Not legal advice or a substitute for "
    "professional compliance assessment."
)
_STRICT_ENVIRONMENTS: Final[frozenset[str]] = frozenset({"production", "prod", "staging"})

logger = get_logger(__name__)


class RelatedEndpoint(BaseModel):
    endpoint: str
    method: str
    price_usd: str
    relation: str
    reason: str


def build_related_endpoint(
    *,
    endpoint: str,
    method: str,
    price_usd: str,
    relation: str,
    reason: str,
) -> RelatedEndpoint:
    return RelatedEndpoint(
        endpoint=endpoint,
        method=method,
        price_usd=price_usd,
        relation=relation,
        reason=reason,
    )


def resolve_attestation_secret() -> str:
    return os.getenv("ATTESTATION_SECRET") or os.getenv("JWT_SECRET") or DEFAULT_ATTESTATION_SECRET


def ensure_attestation_secret_config() -> str:
    secret = resolve_attestation_secret()
    environment = os.getenv("ENVIRONMENT", os.getenv("ENV", "development")).strip().lower()
    if environment in _STRICT_ENVIRONMENTS and secret == DEFAULT_ATTESTATION_SECRET:
        raise RuntimeError(
            "ATTESTATION_SECRET must be set to a non-default value in production/staging"
        )
    return secret


def configure_x402_payment_middleware(
    app: FastAPI,
    *,
    environ: Mapping[str, str] | None = None,
) -> bool:
    env = environ or os.environ
    pay_to = env.get("EVM_ADDRESS", "")
    if not pay_to:
        logger.info("x402 payment middleware disabled (EVM_ADDRESS not set)")
        return False

    try:
        x402_module = importlib.import_module("x402")
        x402_http = importlib.import_module("x402.http")
        x402_http_fastapi = importlib.import_module("x402.http.middleware.fastapi")
        x402_http_types = importlib.import_module("x402.http.types")
        x402_evm = importlib.import_module("x402.mechanisms.evm.exact")
        x402_server_module = importlib.import_module("x402.server")
    except ImportError as exc:
        raise RuntimeError(
            "EVM_ADDRESS is set but x402[evm] is not installed. "
            "Refusing to start payment routes without middleware readiness."
        ) from exc

    facilitator_config = x402_module.FacilitatorConfig
    facilitator_client_cls = x402_http.HTTPFacilitatorClient
    payment_middleware_cls = x402_http_fastapi.PaymentMiddlewareASGI
    payment_option_cls = x402_http_types.PaymentOption
    route_config_cls = x402_http_types.RouteConfig
    exact_evm_server_scheme = x402_evm.ExactEvmServerScheme
    x402_resource_server = x402_server_module.x402ResourceServer

    network = env.get("X402_NETWORK", "eip155:84532")
    price_validate = env.get("X402_PRICE_VALIDATE", "0.01")
    price_audit = env.get("X402_PRICE_AUDIT", "0.05")
    price_certify = env.get("X402_PRICE_CERTIFY", "0.50")
    price_batch = env.get("X402_PRICE_BATCH", "0.10")
    price_treasury = env.get("X402_PRICE_TREASURY", "0.05")
    facilitator_url = env.get("FACILITATOR_URL", "https://facilitator.xpay.sh")

    facilitator_cfg = facilitator_config(url=facilitator_url)
    facilitator_client = facilitator_client_cls(facilitator_cfg)
    x402_server = x402_resource_server([facilitator_client])
    x402_server.register(network, exact_evm_server_scheme())

    def _make_option(price: str) -> Any:
        return payment_option_cls(
            scheme="exact",
            pay_to=pay_to,
            price=f"${price}",
            network=network,
        )

    bazaar_meta = {
        "bazaar": {
            "category": "governance",
            "tags": ["ai", "compliance", "constitutional", "maci"],
        },
    }

    routes = {
        "POST /x402/validate": route_config_cls(
            accepts=[_make_option(price_validate)],
            description=f"Governance validation (${price_validate})",
            extensions=bazaar_meta,
        ),
        "POST /x402/audit": route_config_cls(
            accepts=[_make_option(price_audit)],
            description=f"Compliance audit with risk breakdown (${price_audit})",
            extensions=bazaar_meta,
        ),
        "POST /x402/certify": route_config_cls(
            accepts=[_make_option(price_certify)],
            description=f"Signed attestation — verifiable compliance proof (${price_certify})",
            extensions=bazaar_meta,
        ),
        "POST /x402/batch": route_config_cls(
            accepts=[_make_option(price_batch)],
            description=f"Bulk validation up to 20 actions (${price_batch})",
            extensions=bazaar_meta,
        ),
        "POST /x402/treasury": route_config_cls(
            accepts=[_make_option(price_treasury)],
            description=f"DAO treasury intelligence (${price_treasury})",
            extensions=bazaar_meta,
        ),
        "POST /x402/scan": route_config_cls(
            accepts=[_make_option(env.get("X402_PRICE_SCAN", "0.03"))],
            description="Prompt injection detection ($0.03)",
            extensions=bazaar_meta,
        ),
        "POST /x402/classify-risk": route_config_cls(
            accepts=[_make_option(env.get("X402_PRICE_CLASSIFY_RISK", "0.10"))],
            description="EU AI Act risk classification ($0.10)",
            extensions=bazaar_meta,
        ),
        "POST /x402/compliance": route_config_cls(
            accepts=[_make_option(env.get("X402_PRICE_COMPLIANCE", "0.25"))],
            description="Multi-framework compliance — 8 frameworks ($0.25)",
            extensions=bazaar_meta,
        ),
        "POST /x402/simulate": route_config_cls(
            accepts=[_make_option(env.get("X402_PRICE_SIMULATE", "0.15"))],
            description="Policy change simulation ($0.15)",
            extensions=bazaar_meta,
        ),
        "POST /x402/trust": route_config_cls(
            accepts=[_make_option(env.get("X402_PRICE_TRUST", "0.02"))],
            description="Agent trust scoring ($0.02)",
            extensions=bazaar_meta,
        ),
        "POST /x402/anomaly": route_config_cls(
            accepts=[_make_option(env.get("X402_PRICE_ANOMALY", "0.03"))],
            description="Governance anomaly detection ($0.03)",
            extensions=bazaar_meta,
        ),
        "POST /x402/explain": route_config_cls(
            accepts=[_make_option(env.get("X402_PRICE_EXPLAIN", "0.05"))],
            description="Decision explainability ($0.05)",
            extensions=bazaar_meta,
        ),
        "POST /x402/invariant-guard": route_config_cls(
            accepts=[_make_option(env.get("X402_PRICE_INVARIANT", "0.10"))],
            description="Three-tier invariant enforcement ($0.10)",
            extensions=bazaar_meta,
        ),
        "POST /x402/circuit-breaker": route_config_cls(
            accepts=[_make_option(env.get("X402_PRICE_CIRCUIT", "0.10"))],
            description="Governance circuit breaker ($0.10)",
            extensions=bazaar_meta,
        ),
        "POST /x402/policy-lint": route_config_cls(
            accepts=[_make_option(env.get("X402_PRICE_POLICY_LINT", "0.05"))],
            description="Policy quality & security scan ($0.05)",
            extensions=bazaar_meta,
        ),
        "POST /x402/eu-ai-log": route_config_cls(
            accepts=[_make_option(env.get("X402_PRICE_EU_AI_LOG", "0.10"))],
            description="EU AI Act Article 12 logging ($0.10)",
            extensions=bazaar_meta,
        ),
        "POST /x402/bundle/scout": route_config_cls(
            accepts=[_make_option(env.get("X402_PRICE_BUNDLE_SCOUT", "0.05"))],
            description="Scout bundle: check + validate + scan ($0.05)",
            extensions=bazaar_meta,
        ),
        "POST /x402/bundle/shield": route_config_cls(
            accepts=[_make_option(env.get("X402_PRICE_BUNDLE_SHIELD", "0.25"))],
            description="Shield bundle: 8-endpoint risk analysis ($0.25)",
            extensions=bazaar_meta,
        ),
        "POST /x402/bundle/fortress": route_config_cls(
            accepts=[_make_option(env.get("X402_PRICE_BUNDLE_FORTRESS", "1.00"))],
            description="Fortress bundle: 15-endpoint enterprise suite ($1.00)",
            extensions=bazaar_meta,
        ),
    }

    app.add_middleware(
        payment_middleware_cls,
        routes=routes,
        server=x402_server,
    )
    logger.info(
        "x402 payment middleware ACTIVE",
        network=network,
        prices={
            "validate": price_validate,
            "audit": price_audit,
            "certify": price_certify,
            "batch": price_batch,
            "treasury": price_treasury,
        },
        facilitator=facilitator_url,
        pay_to=pay_to[:10] + "...",
    )
    return True
