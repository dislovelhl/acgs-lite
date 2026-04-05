"""
Transaction Coordinator Alerting Rules

Constitutional Hash: 608508a9bd224290

Prometheus alerting rule definitions and YAML generator for
TransactionCoordinator observability.
"""

from dataclasses import dataclass
from typing import cast

try:
    from enhanced_agent_bus._compat.types import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"  # type: ignore[misc,assignment]


@dataclass
class AlertRule:
    """Prometheus alerting rule definition."""

    name: str
    condition: str
    severity: str
    duration: str
    description: str
    runbook_url: str = ""


# Pre-defined alert rules for transaction coordinator
ALERT_RULES: list[AlertRule] = [
    AlertRule(
        name="TransactionCoordinatorHighFailureRate",
        condition='rate(acgs_transactions_failed_total[5m]) / rate(acgs_transactions_total{status="started"}[5m]) > 0.01',
        severity="critical",
        duration="2m",
        description="Transaction failure rate exceeds 1%",
        runbook_url="https://wiki.internal/transaction-alerts",
    ),
    AlertRule(
        name="TransactionCoordinatorLatencyP99",
        condition="histogram_quantile(0.99, sum(rate(acgs_transaction_latency_seconds_bucket[5m])) by (le)) > 5",
        severity="warning",
        duration="5m",
        description="Transaction P99 latency exceeds 5 seconds",
    ),
    AlertRule(
        name="TransactionCoordinatorConsistencyBelowTarget",
        condition="acgs_consistency_ratio < 0.999",
        severity="critical",
        duration="1m",
        description="Consistency ratio below 99.9% target",
    ),
    AlertRule(
        name="TransactionCoordinatorUnhealthy",
        condition="acgs_transaction_coordinator_health == 0",
        severity="critical",
        duration="0m",
        description="Transaction coordinator is unhealthy",
    ),
    AlertRule(
        name="TransactionCoordinatorCompensationFailures",
        condition='rate(acgs_compensations_total{status="failure"}[5m]) > 0.1',
        severity="warning",
        duration="2m",
        description="High rate of compensation failures",
    ),
    AlertRule(
        name="TransactionCoordinatorCheckpointFailures",
        condition='rate(acgs_checkpoint_saves_total{status="failure"}[5m]) > 0.01',
        severity="warning",
        duration="5m",
        description="Checkpoint save failures detected",
    ),
]


def generate_alert_rules_yaml() -> str:
    """
    Generate Prometheus alert rules in YAML format.

    Returns:
        YAML string with alert rules
    """
    import yaml

    rules = []
    for alert in ALERT_RULES:
        rules.append(
            {
                "alert": alert.name,
                "expr": alert.condition,
                "for": alert.duration,
                "labels": {
                    "severity": alert.severity,
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                },
                "annotations": {
                    "summary": alert.name,
                    "description": alert.description,
                    "runbook_url": alert.runbook_url,
                },
            }
        )

    output = {
        "groups": [
            {
                "name": "transaction_coordinator",
                "rules": rules,
            }
        ]
    }

    return cast(str, yaml.dump(output, default_flow_style=False))
