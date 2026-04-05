"""
ACGS-2 Enhanced Agent Bus Integrations Module
Constitutional Hash: 608508a9bd224290

This module provides integration clients for connecting the Enhanced Agent Bus
to external services. These clients handle the communication, error handling,
and data transformation needed to interact with external systems.

Available Integrations:
- MLGovernanceClient: Client for the Adaptive Learning Engine service,
  enabling real-time governance model training via outcome reporting.

Usage:
    from enhanced_agent_bus.integrations import MLGovernanceClient

    # Initialize the client
    client = MLGovernanceClient(base_url="http://adaptive-learning-engine:8001")

    # Report governance outcomes for model training
    await client.report_outcome(
        features={"action": "deploy", "resource": "production"},
        label=True,  # Outcome was approved
        weight=1.0,
    )

Design Principles:
- All clients use async HTTP to avoid blocking the main event loop
- Circuit breaker pattern for resilience against service failures
- Graceful degradation when external services are unavailable
- Comprehensive error handling with detailed logging
- Retry logic with exponential backoff for transient failures
"""

import os

# Constitutional hash for governance validation
try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = os.environ.get("CONSTITUTIONAL_HASH", CONSTITUTIONAL_HASH)

# Import ML Governance integration client
from .ml_governance import (
    CircuitState,
    MLGovernanceClient,
    MLGovernanceConfig,
    MLGovernanceConnectionError,
    MLGovernanceError,
    MLGovernanceTimeoutError,
    OutcomeReport,
    OutcomeReportStatus,
    OutcomeResult,
    close_ml_governance_client,
    get_ml_governance_client,
    initialize_ml_governance_client,
    report_outcome,
)

__all__ = [
    # Constants
    "CONSTITUTIONAL_HASH",
    # Enums
    "CircuitState",
    # ML Governance Client
    "MLGovernanceClient",
    "MLGovernanceConfig",
    "MLGovernanceConnectionError",
    "MLGovernanceError",
    "MLGovernanceTimeoutError",
    # Data types
    "OutcomeReport",
    "OutcomeReportStatus",
    "OutcomeResult",
    "close_ml_governance_client",
    # Global instance functions
    "get_ml_governance_client",
    "initialize_ml_governance_client",
    # Convenience function
    "report_outcome",
]
