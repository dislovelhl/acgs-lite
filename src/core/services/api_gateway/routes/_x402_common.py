from __future__ import annotations

import os
from typing import Final

from pydantic import BaseModel

DEFAULT_ATTESTATION_SECRET: Final[str] = "acgs2-dev-key"  # noqa: S105
PAID_RESPONSE_DISCLAIMER: Final[str] = (
    "Informational governance signal only. Not legal advice or a substitute for "
    "professional compliance assessment."
)
_STRICT_ENVIRONMENTS: Final[frozenset[str]] = frozenset({"production", "prod", "staging"})


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
