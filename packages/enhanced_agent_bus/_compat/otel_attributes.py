"""Shim for src.core.shared.otel_attributes."""

from __future__ import annotations

try:
    from src.core.shared.otel_attributes import *  # noqa: F403
except ImportError:
    # Standard OpenTelemetry semantic attribute keys used in the codebase.
    SERVICE_NAME = "service.name"
    SERVICE_VERSION = "service.version"
    DEPLOYMENT_ENVIRONMENT = "deployment.environment"

    AGENT_ID = "acgs.agent.id"
    AGENT_ROLE = "acgs.agent.role"
    TENANT_ID = "acgs.tenant.id"
    CORRELATION_ID = "acgs.correlation.id"
    CONSTITUTIONAL_HASH = "acgs.constitutional.hash"
    POLICY_ID = "acgs.policy.id"
    DECISION_TYPE = "acgs.decision.type"
    RISK_LEVEL = "acgs.risk.level"
    MACI_ROLE = "acgs.maci.role"
