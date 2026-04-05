"""
Canonical Enumeration Definitions for ACGS-2.

Constitutional Hash: 608508a9bd224290

This module provides the canonical source-of-truth for shared enumerations
used across the ACGS-2 codebase. Domain-specific modules should import from
here rather than defining their own copies.

Domain-specific variants (e.g., EU AI Act RiskLevel with UNACCEPTABLE/LIMITED/MINIMAL)
are NOT included here — they belong in their respective domain modules.
"""

from enum import Enum, StrEnum


class RiskLevel(StrEnum):
    """Risk levels for governance operations.

    Standard 4-level classification used across session governance,
    policy evaluation, and constitutional compliance.

    Constitutional Hash: 608508a9bd224290
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DecisionType(Enum):
    """Types of decisions in constitutional governance.

    Used by MACI role separation for classifying governance actions
    across executive, legislative, and judicial branches.

    Constitutional Hash: 608508a9bd224290
    """

    POLICY_CREATION = "policy_creation"
    POLICY_EXECUTION = "policy_execution"
    CONSTITUTIONAL_REVIEW = "constitutional_review"
    DISPUTE_RESOLUTION = "dispute_resolution"
    OVERRIDE_REQUEST = "override_request"
