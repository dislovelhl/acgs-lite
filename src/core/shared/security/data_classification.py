"""
ACGS-2 Data Classification System (§16.4)
Constitutional Hash: 608508a9bd224290

Implements unified data classification taxonomy for enterprise AI governance:
- Classification tiers (PUBLIC, INTERNAL, CONFIDENTIAL, RESTRICTED)
- PII category identification
- Retention policy models
- GDPR/CCPA compliance mapping
"""

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

# Constitutional Hash for governance validation
from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.types import JSONDict

# ============================================================================
# Classification Enums
# ============================================================================


class DataClassificationTier(StrEnum):
    """
    Data classification tiers based on sensitivity level.

    Higher tiers require stricter access controls, encryption,
    and audit logging requirements.
    """

    PUBLIC = "public"  # No restrictions, publicly available
    INTERNAL = "internal"  # Internal use only, not for external sharing
    CONFIDENTIAL = "confidential"  # Limited access, business sensitive
    RESTRICTED = "restricted"  # Strict controls, PII/PHI/financial data


class PIICategory(StrEnum):
    """
    PII (Personally Identifiable Information) categories per GDPR Article 4.

    Used for automatic classification and compliance reporting.
    """

    PERSONAL_IDENTIFIERS = "personal_identifiers"  # Name, SSN, ID numbers
    CONTACT_INFO = "contact_info"  # Email, phone, address
    FINANCIAL = "financial"  # Bank accounts, credit cards
    HEALTH = "health"  # Medical records (PHI)
    BIOMETRIC = "biometric"  # Fingerprints, facial data
    LOCATION = "location"  # GPS, IP addresses
    BEHAVIORAL = "behavioral"  # Browsing history, preferences
    GENETIC = "genetic"  # DNA, genetic markers
    POLITICAL = "political"  # Political opinions
    RELIGIOUS = "religious"  # Religious beliefs
    ETHNIC = "ethnic"  # Racial/ethnic origin
    SEXUAL_ORIENTATION = "sexual_orientation"  # Sexual orientation/life


class GDPRLawfulBasis(StrEnum):
    """
    GDPR Article 6 lawful bases for processing personal data.
    """

    CONSENT = "consent"  # Article 6(1)(a)
    CONTRACT = "contract"  # Article 6(1)(b)
    LEGAL_OBLIGATION = "legal_obligation"  # Article 6(1)(c)
    VITAL_INTERESTS = "vital_interests"  # Article 6(1)(d)
    PUBLIC_TASK = "public_task"  # Article 6(1)(e)
    LEGITIMATE_INTERESTS = "legitimate_interests"  # Article 6(1)(f)


class DisposalMethod(StrEnum):
    """
    Data disposal methods for retention policy enforcement.
    """

    DELETE = "delete"  # Complete and irreversible deletion
    ARCHIVE = "archive"  # Move to cold storage with restricted access
    ANONYMIZE = "anonymize"  # Remove identifying information, keep analytics
    PSEUDONYMIZE = "pseudonymize"  # Replace identifiers with pseudonyms


class ComplianceFramework(StrEnum):
    """
    Supported compliance frameworks for data classification mapping.
    """

    GDPR = "gdpr"  # EU General Data Protection Regulation
    CCPA = "ccpa"  # California Consumer Privacy Act
    HIPAA = "hipaa"  # Health Insurance Portability and Accountability Act
    SOC2 = "soc2"  # Service Organization Control 2
    ISO27001 = "iso27001"  # Information Security Management
    NIST_AI_RMF = "nist_ai_rmf"  # NIST AI Risk Management Framework
    EU_AI_ACT = "eu_ai_act"  # EU AI Act


# ============================================================================
# Classification Models
# ============================================================================


class PIIDetection(BaseModel):
    """Result of PII detection for a specific category."""

    category: PIICategory = Field(..., description="Detected PII category")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Detection confidence")
    field_path: str = Field(..., description="JSON path to the detected field")
    matched_pattern: str | None = Field(default=None, description="Pattern that matched")
    sample_value_hash: str | None = Field(default=None, description="Hash of detected value")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "category": "contact_info",
                "confidence": 0.95,
                "field_path": "$.user.email",
                "matched_pattern": "email_pattern",
                "sample_value_hash": "a1b2c3d4e5f6",
            }
        }
    )


class ClassificationResult(BaseModel):
    """Result of data classification analysis."""

    classification_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), description="Unique classification ID"
    )
    tier: DataClassificationTier = Field(..., description="Assigned classification tier")
    pii_detections: list[PIIDetection] = Field(
        default_factory=list, description="List of PII detections"
    )
    pii_categories: set[PIICategory] = Field(
        default_factory=set, description="Set of detected PII categories"
    )
    overall_confidence: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Overall classification confidence"
    )
    recommended_retention_days: int = Field(
        default=365, description="Recommended retention period in days"
    )
    applicable_frameworks: list[ComplianceFramework] = Field(
        default_factory=list, description="Applicable compliance frameworks"
    )
    requires_encryption: bool = Field(default=False, description="Whether encryption is required")
    requires_audit_logging: bool = Field(
        default=False, description="Whether audit logging is required"
    )
    classified_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Classification timestamp"
    )
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH)

    model_config = ConfigDict(use_enum_values=True)


class RetentionPolicy(BaseModel):
    """
    Data retention policy definition.

    Defines how long data should be retained and how it should
    be disposed of after the retention period expires.
    """

    policy_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), description="Unique policy identifier"
    )
    name: str = Field(..., description="Policy name")
    description: str = Field(default="", description="Policy description")
    classification_tier: DataClassificationTier = Field(
        ..., description="Classification tier this policy applies to"
    )
    pii_categories: list[PIICategory] = Field(
        default_factory=list, description="PII categories this policy applies to"
    )
    retention_days: int = Field(
        ..., ge=-1, description="Retention period in days (-1 for indefinite)"
    )
    disposal_method: DisposalMethod = Field(
        ..., description="Method for data disposal after retention period"
    )
    gdpr_article_17_applicable: bool = Field(
        default=False, description="Whether GDPR Article 17 (right to erasure) applies"
    )
    lawful_basis: GDPRLawfulBasis | None = Field(
        default=None, description="GDPR lawful basis for processing"
    )
    applicable_frameworks: list[ComplianceFramework] = Field(
        default_factory=list, description="Compliance frameworks this policy satisfies"
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    version: int = Field(default=1, ge=1)
    is_active: bool = Field(default=True)
    tenant_id: str | None = Field(default=None, description="Tenant ID for multi-tenancy")
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH)

    model_config = ConfigDict(
        use_enum_values=True,
        json_schema_extra={
            "example": {
                "name": "PII Retention 90 Days",
                "classification_tier": "restricted",
                "pii_categories": ["personal_identifiers", "contact_info"],
                "retention_days": 90,
                "disposal_method": "delete",
                "gdpr_article_17_applicable": True,
                "lawful_basis": "consent",
            }
        },
    )


class DataClassificationPolicy(BaseModel):
    """
    Policy for automatic data classification rules.

    Defines patterns and rules for classifying data based on
    content, structure, and context.
    """

    policy_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), description="Unique policy identifier"
    )
    name: str = Field(..., description="Policy name")
    description: str = Field(default="", description="Policy description")
    target_tier: DataClassificationTier = Field(
        ..., description="Classification tier to assign when rules match"
    )
    field_patterns: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Field name patterns to match (field_name: [regex patterns])",
    )
    content_patterns: list[str] = Field(
        default_factory=list, description="Content patterns to match (regex)"
    )
    pii_categories_trigger: list[PIICategory] = Field(
        default_factory=list, description="PII categories that trigger this classification"
    )
    min_pii_confidence: float = Field(
        default=0.8, ge=0.0, le=1.0, description="Minimum PII detection confidence to trigger"
    )
    priority: int = Field(default=100, description="Policy priority (lower = higher priority)")
    is_active: bool = Field(default=True)
    tenant_id: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH)

    model_config = ConfigDict(use_enum_values=True)


# ============================================================================
# Classification Requirements by Tier
# ============================================================================


TIER_REQUIREMENTS: dict[DataClassificationTier, JSONDict] = {
    DataClassificationTier.PUBLIC: {
        "encryption_required": False,
        "audit_logging_required": False,
        "access_control_level": "none",
        "default_retention_days": -1,  # Indefinite
        "disposal_method": DisposalMethod.DELETE,
        "pii_allowed": False,
    },
    DataClassificationTier.INTERNAL: {
        "encryption_required": False,
        "audit_logging_required": True,
        "access_control_level": "basic",
        "default_retention_days": 365,
        "disposal_method": DisposalMethod.ARCHIVE,
        "pii_allowed": False,
    },
    DataClassificationTier.CONFIDENTIAL: {
        "encryption_required": True,
        "audit_logging_required": True,
        "access_control_level": "role_based",
        "default_retention_days": 180,
        "disposal_method": DisposalMethod.DELETE,
        "pii_allowed": True,
    },
    DataClassificationTier.RESTRICTED: {
        "encryption_required": True,
        "audit_logging_required": True,
        "access_control_level": "strict",
        "default_retention_days": 90,
        "disposal_method": DisposalMethod.DELETE,
        "pii_allowed": True,
        "gdpr_article_17_applicable": True,
    },
}


# ============================================================================
# PII Category to Compliance Framework Mapping
# ============================================================================


PII_COMPLIANCE_MAPPING: dict[PIICategory, list[ComplianceFramework]] = {
    PIICategory.PERSONAL_IDENTIFIERS: [
        ComplianceFramework.GDPR,
        ComplianceFramework.CCPA,
        ComplianceFramework.SOC2,
    ],
    PIICategory.CONTACT_INFO: [
        ComplianceFramework.GDPR,
        ComplianceFramework.CCPA,
    ],
    PIICategory.FINANCIAL: [
        ComplianceFramework.GDPR,
        ComplianceFramework.CCPA,
        ComplianceFramework.SOC2,
        ComplianceFramework.ISO27001,
    ],
    PIICategory.HEALTH: [
        ComplianceFramework.GDPR,
        ComplianceFramework.HIPAA,
    ],
    PIICategory.BIOMETRIC: [
        ComplianceFramework.GDPR,
        ComplianceFramework.CCPA,
        ComplianceFramework.EU_AI_ACT,
    ],
    PIICategory.LOCATION: [
        ComplianceFramework.GDPR,
        ComplianceFramework.CCPA,
    ],
    PIICategory.BEHAVIORAL: [
        ComplianceFramework.GDPR,
        ComplianceFramework.CCPA,
        ComplianceFramework.EU_AI_ACT,
    ],
    PIICategory.GENETIC: [
        ComplianceFramework.GDPR,
        ComplianceFramework.HIPAA,
    ],
    PIICategory.POLITICAL: [
        ComplianceFramework.GDPR,
    ],
    PIICategory.RELIGIOUS: [
        ComplianceFramework.GDPR,
    ],
    PIICategory.ETHNIC: [
        ComplianceFramework.GDPR,
    ],
    PIICategory.SEXUAL_ORIENTATION: [
        ComplianceFramework.GDPR,
    ],
}


# ============================================================================
# Default Retention Policies
# ============================================================================


DEFAULT_RETENTION_POLICIES: list[RetentionPolicy] = [
    RetentionPolicy(
        policy_id="default-public",
        name="Public Data - Indefinite",
        description="Default policy for public data with no retention limit",
        classification_tier=DataClassificationTier.PUBLIC,
        retention_days=-1,
        disposal_method=DisposalMethod.DELETE,
        gdpr_article_17_applicable=False,
    ),
    RetentionPolicy(
        policy_id="default-internal",
        name="Internal Data - 1 Year",
        description="Default policy for internal data with 1 year retention",
        classification_tier=DataClassificationTier.INTERNAL,
        retention_days=365,
        disposal_method=DisposalMethod.ARCHIVE,
        gdpr_article_17_applicable=False,
    ),
    RetentionPolicy(
        policy_id="default-confidential",
        name="Confidential Data - 180 Days",
        description="Default policy for confidential data with 6 month retention",
        classification_tier=DataClassificationTier.CONFIDENTIAL,
        retention_days=180,
        disposal_method=DisposalMethod.DELETE,
        gdpr_article_17_applicable=True,
        lawful_basis=GDPRLawfulBasis.LEGITIMATE_INTERESTS,
        applicable_frameworks=[ComplianceFramework.GDPR, ComplianceFramework.SOC2],
    ),
    RetentionPolicy(
        policy_id="default-restricted",
        name="Restricted Data - 90 Days",
        description="Default policy for restricted/PII data with 90 day retention",
        classification_tier=DataClassificationTier.RESTRICTED,
        retention_days=90,
        disposal_method=DisposalMethod.DELETE,
        gdpr_article_17_applicable=True,
        lawful_basis=GDPRLawfulBasis.CONSENT,
        applicable_frameworks=[
            ComplianceFramework.GDPR,
            ComplianceFramework.CCPA,
            ComplianceFramework.SOC2,
        ],
    ),
    RetentionPolicy(
        policy_id="hipaa-phi",
        name="HIPAA PHI - 6 Years",
        description="HIPAA-compliant retention for Protected Health Information",
        classification_tier=DataClassificationTier.RESTRICTED,
        pii_categories=[PIICategory.HEALTH],
        retention_days=2190,  # 6 years
        disposal_method=DisposalMethod.DELETE,
        gdpr_article_17_applicable=True,
        applicable_frameworks=[ComplianceFramework.HIPAA, ComplianceFramework.GDPR],
    ),
]


# ============================================================================
# Utility Functions
# ============================================================================


def get_tier_requirements(tier: DataClassificationTier) -> JSONDict:
    """Get security requirements for a classification tier."""
    return TIER_REQUIREMENTS.get(tier, TIER_REQUIREMENTS[DataClassificationTier.INTERNAL])


def get_compliance_frameworks(pii_categories: list[PIICategory]) -> set[ComplianceFramework]:
    """Get applicable compliance frameworks for given PII categories."""
    frameworks: set[ComplianceFramework] = set()
    for category in pii_categories:
        if category in PII_COMPLIANCE_MAPPING:
            frameworks.update(PII_COMPLIANCE_MAPPING[category])
    return frameworks


def get_default_retention_policy(tier: DataClassificationTier) -> RetentionPolicy:
    """Get the default retention policy for a classification tier."""
    for policy in DEFAULT_RETENTION_POLICIES:
        if policy.classification_tier == tier:
            return policy
    # Fallback to restricted policy if not found
    return DEFAULT_RETENTION_POLICIES[-1]


def classify_by_pii_categories(
    pii_categories: list[PIICategory],
    _pii_confidence: float = 0.8,
) -> DataClassificationTier:
    """
    Determine classification tier based on detected PII categories.

    Args:
        pii_categories: List of detected PII categories
        pii_confidence: Minimum confidence threshold

    Returns:
        Appropriate classification tier
    """
    if not pii_categories:
        return DataClassificationTier.INTERNAL

    # Special categories require RESTRICTED tier
    special_categories = {
        PIICategory.HEALTH,
        PIICategory.BIOMETRIC,
        PIICategory.GENETIC,
        PIICategory.POLITICAL,
        PIICategory.RELIGIOUS,
        PIICategory.ETHNIC,
        PIICategory.SEXUAL_ORIENTATION,
    }

    if any(cat in special_categories for cat in pii_categories):
        return DataClassificationTier.RESTRICTED

    # Financial or multiple PII categories = RESTRICTED
    if PIICategory.FINANCIAL in pii_categories or len(pii_categories) >= 2:
        return DataClassificationTier.RESTRICTED

    # Single basic PII category = CONFIDENTIAL
    return DataClassificationTier.CONFIDENTIAL


__all__ = [
    # Constants
    "CONSTITUTIONAL_HASH",
    "DEFAULT_RETENTION_POLICIES",
    "PII_COMPLIANCE_MAPPING",
    "TIER_REQUIREMENTS",
    "ClassificationResult",
    "ComplianceFramework",
    "DataClassificationPolicy",
    # Enums
    "DataClassificationTier",
    "DisposalMethod",
    "GDPRLawfulBasis",
    "PIICategory",
    # Models
    "PIIDetection",
    "RetentionPolicy",
    "classify_by_pii_categories",
    "get_compliance_frameworks",
    "get_default_retention_policy",
    # Functions
    "get_tier_requirements",
]
