"""
ACGS-2 GDPR Article 17 Erasure Handler
Constitutional Hash: cdd01ef066bc6cf2

Implements GDPR Article 17 "Right to Erasure" (Right to be Forgotten):
- Erasure request management
- Multi-system data location discovery
- Coordinated erasure across systems
- Erasure certificate generation
- Compliance audit trails
"""

import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from src.core.shared.errors.exceptions import (
    ResourceNotFoundError,
)
from src.core.shared.errors.exceptions import (
    ValidationError as ACGSValidationError,
)
from src.core.shared.types import JSONDict

from .data_classification import (
    CONSTITUTIONAL_HASH,
    ComplianceFramework,
    DataClassificationTier,
    PIICategory,
)

# ============================================================================
# Enums
# ============================================================================


class ErasureScope(StrEnum):
    """Scope of data erasure request."""

    ALL_DATA = "all_data"  # Erase all data for subject
    SPECIFIC_CATEGORIES = "specific_categories"  # Erase specific PII categories
    SPECIFIC_SYSTEMS = "specific_systems"  # Erase from specific systems
    DERIVED_DATA = "derived_data"  # Erase inferred/derived data only
    MARKETING_DATA = "marketing_data"  # Erase marketing preferences only


class ErasureStatus(StrEnum):
    """Status of an erasure request."""

    PENDING = "pending"  # Request received, not yet processed
    VALIDATING = "validating"  # Verifying identity and scope
    IN_PROGRESS = "in_progress"  # Erasure underway
    COMPLETED = "completed"  # Successfully completed
    PARTIALLY_COMPLETED = "partially_completed"  # Some systems failed
    REJECTED = "rejected"  # Request rejected (exemption applies)
    FAILED = "failed"  # Technical failure


class ErasureExemption(StrEnum):
    """
    GDPR Article 17(3) exemptions to right of erasure.
    """

    FREEDOM_OF_EXPRESSION = "freedom_of_expression"  # Art 17(3)(a)
    LEGAL_OBLIGATION = "legal_obligation"  # Art 17(3)(b)
    PUBLIC_INTEREST_HEALTH = "public_interest_health"  # Art 17(3)(c)
    ARCHIVING_RESEARCH = "archiving_research"  # Art 17(3)(d)
    LEGAL_CLAIMS = "legal_claims"  # Art 17(3)(e)


class DataLocationType(StrEnum):
    """Types of data storage locations."""

    PRIMARY_DATABASE = "primary_database"
    BACKUP = "backup"
    CACHE = "cache"
    LOG = "log"
    ANALYTICS = "analytics"
    THIRD_PARTY = "third_party"
    ARCHIVE = "archive"
    DERIVED = "derived"


# ============================================================================
# Models
# ============================================================================


class DataLocation(BaseModel):
    """Location where data subject's data is stored."""

    location_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    system_name: str = Field(..., description="Name of the system/service")
    location_type: DataLocationType = Field(...)
    data_categories: list[PIICategory] = Field(
        default_factory=list, description="PII categories stored in this location"
    )
    classification_tier: DataClassificationTier = Field(default=DataClassificationTier.INTERNAL)
    record_count: int = Field(default=0, description="Number of records found")
    can_be_erased: bool = Field(default=True, description="Whether location supports erasure")
    erasure_method: str = Field(default="delete", description="Method for erasure")
    estimated_size_bytes: int = Field(default=0)
    retention_policy_id: str | None = Field(default=None)
    last_accessed: datetime | None = Field(default=None)


class ErasureSystemResult(BaseModel):
    """Result of erasure from a single system."""

    location_id: str = Field(...)
    system_name: str = Field(...)
    success: bool = Field(...)
    records_erased: int = Field(default=0)
    bytes_erased: int = Field(default=0)
    erased_at: datetime | None = Field(default=None)
    error_message: str | None = Field(default=None)
    verification_hash: str = Field(default="")


class ErasureRequest(BaseModel):
    """GDPR Article 17 erasure request."""

    request_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), description="Unique request identifier"
    )
    data_subject_id: str = Field(..., description="Identifier of the data subject")
    data_subject_email: str | None = Field(default=None, description="Email for notifications")
    scope: ErasureScope = Field(default=ErasureScope.ALL_DATA, description="Scope of erasure")
    specific_categories: list[PIICategory] = Field(
        default_factory=list,
        description="Specific categories to erase (if scope is SPECIFIC_CATEGORIES)",
    )
    specific_systems: list[str] = Field(
        default_factory=list,
        description="Specific systems to erase from (if scope is SPECIFIC_SYSTEMS)",
    )
    status: ErasureStatus = Field(default=ErasureStatus.PENDING)
    identity_verified: bool = Field(default=False)
    identity_verification_method: str | None = Field(default=None)
    exemptions_checked: bool = Field(default=False)
    applicable_exemptions: list[ErasureExemption] = Field(default_factory=list)
    rejection_reason: str | None = Field(default=None)

    # Discovery results
    data_locations: list[DataLocation] = Field(
        default_factory=list, description="Discovered data locations"
    )

    # Erasure results
    system_results: list[ErasureSystemResult] = Field(
        default_factory=list, description="Results from each system"
    )
    total_records_erased: int = Field(default=0)
    total_bytes_erased: int = Field(default=0)

    # Timestamps
    requested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    validated_at: datetime | None = Field(default=None)
    started_at: datetime | None = Field(default=None)
    completed_at: datetime | None = Field(default=None)
    deadline: datetime = Field(
        default_factory=lambda: datetime.now(UTC) + timedelta(days=30),
        description="GDPR 30-day response deadline",
    )

    # Audit
    tenant_id: str | None = Field(default=None)
    requested_by: str = Field(default="data_subject")
    processed_by: str | None = Field(default=None)
    audit_notes: list[str] = Field(default_factory=list)
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH)

    model_config = ConfigDict(use_enum_values=True)


class ErasureCertificate(BaseModel):
    """
    Certificate of erasure completion.

    Provides verifiable proof that data was erased per GDPR requirements.
    """

    certificate_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    request_id: str = Field(..., description="Associated erasure request")
    data_subject_id: str = Field(...)

    # Erasure summary
    scope: ErasureScope = Field(...)
    systems_processed: int = Field(default=0)
    systems_successful: int = Field(default=0)
    total_records_erased: int = Field(default=0)
    total_bytes_erased: int = Field(default=0)

    # Compliance information
    gdpr_article_17_compliant: bool = Field(default=True)
    applicable_exemptions: list[ErasureExemption] = Field(default_factory=list)
    exemption_explanation: str | None = Field(default=None)

    # Verification
    certificate_hash: str = Field(
        default="", description="SHA-256 hash of certificate contents for verification"
    )
    issued_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    valid_until: datetime = Field(
        default_factory=lambda: datetime.now(UTC) + timedelta(days=365 * 7),
        description="Certificate validity (7 years per GDPR)",
    )

    # System details (for audit)
    system_summaries: list[JSONDict] = Field(
        default_factory=list, description="Summary of each system's erasure"
    )

    # Metadata
    issuer: str = Field(default="ACGS-2 GDPR Compliance Engine")
    compliance_frameworks: list[ComplianceFramework] = Field(
        default_factory=lambda: [ComplianceFramework.GDPR]
    )
    tenant_id: str | None = Field(default=None)
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH)

    model_config = ConfigDict(use_enum_values=True)


# ============================================================================
# GDPR Erasure Handler
# ============================================================================


class GDPRErasureHandler:
    """
    Handler for GDPR Article 17 erasure requests.

    Constitutional Hash: cdd01ef066bc6cf2

    Implements the complete erasure workflow:
    1. Request validation and identity verification
    2. Exemption checking
    3. Data location discovery
    4. Coordinated erasure across systems
    5. Certificate generation
    """

    def __init__(
        self,
        default_deadline_days: int = 30,
        certificate_validity_years: int = 7,
    ):
        """
        Initialize GDPR erasure handler.

        Args:
            default_deadline_days: GDPR response deadline (default 30)
            certificate_validity_years: Certificate retention period (default 7)
        """
        self.default_deadline_days = default_deadline_days
        self.certificate_validity_years = certificate_validity_years
        self.constitutional_hash = CONSTITUTIONAL_HASH

        # In-memory storage (production would use database)
        self._requests: dict[str, ErasureRequest] = {}
        self._certificates: dict[str, ErasureCertificate] = {}

        # Mock data locations for demonstration
        self._mock_systems: list[DataLocation] = [
            DataLocation(
                system_name="user_database",
                location_type=DataLocationType.PRIMARY_DATABASE,
                data_categories=[PIICategory.PERSONAL_IDENTIFIERS, PIICategory.CONTACT_INFO],
                classification_tier=DataClassificationTier.RESTRICTED,
                can_be_erased=True,
                erasure_method="delete",
            ),
            DataLocation(
                system_name="analytics_warehouse",
                location_type=DataLocationType.ANALYTICS,
                data_categories=[PIICategory.BEHAVIORAL],
                classification_tier=DataClassificationTier.CONFIDENTIAL,
                can_be_erased=True,
                erasure_method="anonymize",
            ),
            DataLocation(
                system_name="audit_logs",
                location_type=DataLocationType.LOG,
                data_categories=[PIICategory.PERSONAL_IDENTIFIERS],
                classification_tier=DataClassificationTier.INTERNAL,
                can_be_erased=False,  # Logs may be exempt
                erasure_method="redact",
            ),
            DataLocation(
                system_name="backup_storage",
                location_type=DataLocationType.BACKUP,
                data_categories=[PIICategory.PERSONAL_IDENTIFIERS, PIICategory.CONTACT_INFO],
                classification_tier=DataClassificationTier.RESTRICTED,
                can_be_erased=True,
                erasure_method="delete",
            ),
            DataLocation(
                system_name="cache_layer",
                location_type=DataLocationType.CACHE,
                data_categories=[PIICategory.PERSONAL_IDENTIFIERS],
                classification_tier=DataClassificationTier.INTERNAL,
                can_be_erased=True,
                erasure_method="invalidate",
            ),
        ]

    async def request_erasure(
        self,
        data_subject_id: str,
        scope: ErasureScope = ErasureScope.ALL_DATA,
        specific_categories: list[PIICategory] | None = None,
        specific_systems: list[str] | None = None,
        data_subject_email: str | None = None,
        tenant_id: str | None = None,
    ) -> ErasureRequest:
        """
        Submit a new erasure request.

        Args:
            data_subject_id: Identifier of the data subject
            scope: Scope of erasure
            specific_categories: Categories to erase (for SPECIFIC_CATEGORIES scope)
            specific_systems: Systems to erase from (for SPECIFIC_SYSTEMS scope)
            data_subject_email: Email for notifications
            tenant_id: Tenant identifier

        Returns:
            Created ErasureRequest
        """
        request = ErasureRequest(
            data_subject_id=data_subject_id,
            data_subject_email=data_subject_email,
            scope=scope,
            specific_categories=specific_categories or [],
            specific_systems=specific_systems or [],
            deadline=datetime.now(UTC) + timedelta(days=self.default_deadline_days),
            tenant_id=tenant_id,
        )

        self._requests[request.request_id] = request

        request.audit_notes.append(f"[{datetime.now(UTC).isoformat()}] Erasure request created")

        return request

    async def validate_request(
        self,
        request_id: str,
        identity_verified: bool = False,
        verification_method: str | None = None,
    ) -> ErasureRequest:
        """
        Validate an erasure request and verify identity.

        Args:
            request_id: Request to validate
            identity_verified: Whether identity was verified
            verification_method: Method used for verification

        Returns:
            Updated ErasureRequest

        Raises:
            ValueError: If request not found
        """
        request = self._requests.get(request_id)
        if not request:
            raise ResourceNotFoundError(
                message=f"Request not found: {request_id}", error_code="GDPR_REQUEST_NOT_FOUND"
            )

        request.status = ErasureStatus.VALIDATING
        request.identity_verified = identity_verified
        request.identity_verification_method = verification_method
        request.validated_at = datetime.now(UTC)

        request.audit_notes.append(
            f"[{datetime.now(UTC).isoformat()}] Identity verification: "
            f"{'passed' if identity_verified else 'failed'} via {verification_method}"
        )

        return request

    async def check_exemptions(
        self,
        request_id: str,
    ) -> ErasureRequest:
        """
        Check if any GDPR Article 17(3) exemptions apply.

        Args:
            request_id: Request to check

        Returns:
            Updated ErasureRequest with exemption information
        """
        request = self._requests.get(request_id)
        if not request:
            raise ResourceNotFoundError(
                message=f"Request not found: {request_id}", error_code="GDPR_REQUEST_NOT_FOUND"
            )

        # In production, this would check actual legal obligations
        exemptions: list[ErasureExemption] = []

        # Example: Check for legal hold on data
        # This is simulated - production would query legal hold database
        if request.scope == ErasureScope.ALL_DATA:
            # Audit logs may be exempt for legal compliance
            pass

        request.exemptions_checked = True
        request.applicable_exemptions = exemptions

        request.audit_notes.append(
            f"[{datetime.now(UTC).isoformat()}] Exemption check completed: "
            f"{len(exemptions)} exemptions apply"
        )

        return request

    async def discover_data_locations(
        self,
        request_id: str,
    ) -> ErasureRequest:
        """
        Discover all locations where data subject's data is stored.

        Args:
            request_id: Request to process

        Returns:
            Updated ErasureRequest with data locations
        """
        request = self._requests.get(request_id)
        if not request:
            raise ResourceNotFoundError(
                message=f"Request not found: {request_id}", error_code="GDPR_REQUEST_NOT_FOUND"
            )

        # In production, this would query a data catalog/discovery service
        discovered_locations: list[DataLocation] = []

        for system in self._mock_systems:
            # Filter by scope
            if request.scope == ErasureScope.SPECIFIC_SYSTEMS:
                if system.system_name not in request.specific_systems:
                    continue

            if request.scope == ErasureScope.SPECIFIC_CATEGORIES:
                matching_categories = set(system.data_categories) & set(request.specific_categories)
                if not matching_categories:
                    continue

            # Simulate finding records
            location = system.model_copy()
            location.record_count = 10  # Simulated
            location.estimated_size_bytes = 1024 * location.record_count
            location.last_accessed = datetime.now(UTC) - timedelta(days=5)
            discovered_locations.append(location)

        request.data_locations = discovered_locations

        request.audit_notes.append(
            f"[{datetime.now(UTC).isoformat()}] Data discovery completed: "
            f"{len(discovered_locations)} locations found"
        )

        return request

    async def process_erasure(
        self,
        request_id: str,
        processed_by: str = "system",
    ) -> ErasureRequest:
        """
        Execute erasure across all discovered data locations.

        Args:
            request_id: Request to process
            processed_by: Actor performing erasure

        Returns:
            Updated ErasureRequest with results
        """
        request = self._requests.get(request_id)
        if not request:
            raise ResourceNotFoundError(
                message=f"Request not found: {request_id}", error_code="GDPR_REQUEST_NOT_FOUND"
            )

        if not request.identity_verified:
            request.status = ErasureStatus.REJECTED
            request.rejection_reason = "Identity not verified"
            return request

        request.status = ErasureStatus.IN_PROGRESS
        request.started_at = datetime.now(UTC)
        request.processed_by = processed_by

        total_records = 0
        total_bytes = 0
        all_successful = True

        for location in request.data_locations:
            # Simulate erasure operation
            if location.can_be_erased:
                result = ErasureSystemResult(
                    location_id=location.location_id,
                    system_name=location.system_name,
                    success=True,
                    records_erased=location.record_count,
                    bytes_erased=location.estimated_size_bytes,
                    erased_at=datetime.now(UTC),
                    verification_hash=hashlib.sha256(
                        f"{location.location_id}:{request.data_subject_id}:erased".encode()
                    ).hexdigest()[:32],
                )
                total_records += location.record_count
                total_bytes += location.estimated_size_bytes
            else:
                result = ErasureSystemResult(
                    location_id=location.location_id,
                    system_name=location.system_name,
                    success=False,
                    error_message="System does not support erasure (may be exempt)",
                )
                all_successful = False

            request.system_results.append(result)

        request.total_records_erased = total_records
        request.total_bytes_erased = total_bytes
        request.completed_at = datetime.now(UTC)

        if all_successful:
            request.status = ErasureStatus.COMPLETED
        else:
            request.status = ErasureStatus.PARTIALLY_COMPLETED

        request.audit_notes.append(
            f"[{datetime.now(UTC).isoformat()}] Erasure completed: "
            f"{total_records} records, {total_bytes} bytes, "
            f"status={request.status.value if hasattr(request.status, 'value') else request.status}"
        )

        return request

    async def generate_erasure_certificate(
        self,
        request_id: str,
    ) -> ErasureCertificate:
        """
        Generate certificate of erasure completion.

        Args:
            request_id: Completed request to certify

        Returns:
            ErasureCertificate

        Raises:
            ValueError: If request not found or not completed
        """
        request = self._requests.get(request_id)
        if not request:
            raise ResourceNotFoundError(
                message=f"Request not found: {request_id}", error_code="GDPR_REQUEST_NOT_FOUND"
            )

        if request.status not in (ErasureStatus.COMPLETED, ErasureStatus.PARTIALLY_COMPLETED):
            raise ACGSValidationError(
                message=f"Request not completed: {request.status}",
                error_code="GDPR_REQUEST_NOT_COMPLETED",
            )

        # Build system summaries
        system_summaries = []
        for result in request.system_results:
            system_summaries.append(
                {
                    "system_name": result.system_name,
                    "success": result.success,
                    "records_erased": result.records_erased,
                    "verification_hash": result.verification_hash,
                }
            )

        # Create certificate
        certificate = ErasureCertificate(
            request_id=request_id,
            data_subject_id=request.data_subject_id,
            scope=request.scope,
            systems_processed=len(request.system_results),
            systems_successful=sum(1 for r in request.system_results if r.success),
            total_records_erased=request.total_records_erased,
            total_bytes_erased=request.total_bytes_erased,
            gdpr_article_17_compliant=request.status == ErasureStatus.COMPLETED,
            applicable_exemptions=request.applicable_exemptions,
            exemption_explanation=(
                "Some systems are exempt from erasure per GDPR Article 17(3)"
                if request.applicable_exemptions
                else None
            ),
            valid_until=datetime.now(UTC) + timedelta(days=365 * self.certificate_validity_years),
            system_summaries=system_summaries,
            tenant_id=request.tenant_id,
        )

        # Generate certificate hash for verification
        cert_content = json.dumps(
            {
                "certificate_id": certificate.certificate_id,
                "request_id": certificate.request_id,
                "data_subject_id": certificate.data_subject_id,
                "total_records_erased": certificate.total_records_erased,
                "issued_at": certificate.issued_at.isoformat(),
            },
            sort_keys=True,
        )
        certificate.certificate_hash = hashlib.sha256(cert_content.encode()).hexdigest()

        self._certificates[certificate.certificate_id] = certificate

        request.audit_notes.append(
            f"[{datetime.now(UTC).isoformat()}] Certificate issued: {certificate.certificate_id}"
        )

        return certificate

    async def get_request(self, request_id: str) -> ErasureRequest | None:
        """Get an erasure request by ID."""
        return self._requests.get(request_id)

    async def get_certificate(self, certificate_id: str) -> ErasureCertificate | None:
        """Get an erasure certificate by ID."""
        return self._certificates.get(certificate_id)

    async def verify_certificate(
        self,
        certificate_id: str,
    ) -> bool:
        """
        Verify the integrity of an erasure certificate.

        Args:
            certificate_id: Certificate to verify

        Returns:
            True if certificate is valid and not tampered
        """
        certificate = self._certificates.get(certificate_id)
        if not certificate:
            return False

        # Recalculate hash
        cert_content = json.dumps(
            {
                "certificate_id": certificate.certificate_id,
                "request_id": certificate.request_id,
                "data_subject_id": certificate.data_subject_id,
                "total_records_erased": certificate.total_records_erased,
                "issued_at": certificate.issued_at.isoformat(),
            },
            sort_keys=True,
        )
        expected_hash = hashlib.sha256(cert_content.encode()).hexdigest()

        # Use constant-time comparison to prevent timing attacks
        return hmac.compare_digest(certificate.certificate_hash, expected_hash)

    async def get_pending_requests(
        self,
        tenant_id: str | None = None,
    ) -> list[ErasureRequest]:
        """Get all pending erasure requests."""
        pending = []
        for request in self._requests.values():
            if request.status in (ErasureStatus.PENDING, ErasureStatus.VALIDATING):
                if tenant_id is None or request.tenant_id == tenant_id:
                    pending.append(request)
        return pending

    async def get_overdue_requests(self) -> list[ErasureRequest]:
        """Get requests past their GDPR deadline."""
        now = datetime.now(UTC)
        overdue = []
        for request in self._requests.values():
            if request.status not in (ErasureStatus.COMPLETED, ErasureStatus.REJECTED):
                if request.deadline < now:
                    overdue.append(request)
        return overdue


# ============================================================================
# Singleton Instance
# ============================================================================


_handler_instance: GDPRErasureHandler | None = None


def get_gdpr_erasure_handler() -> GDPRErasureHandler:
    """Get or create the singleton GDPRErasureHandler instance."""
    global _handler_instance
    if _handler_instance is None:
        _handler_instance = GDPRErasureHandler()
    return _handler_instance


def reset_gdpr_erasure_handler() -> None:
    """Reset the singleton instance (for testing)."""
    global _handler_instance
    _handler_instance = None


__all__ = [
    # Constants
    "CONSTITUTIONAL_HASH",
    # Models
    "DataLocation",
    "DataLocationType",
    "ErasureCertificate",
    "ErasureExemption",
    "ErasureRequest",
    # Enums
    "ErasureScope",
    "ErasureStatus",
    "ErasureSystemResult",
    # Handler
    "GDPRErasureHandler",
    "get_gdpr_erasure_handler",
    "reset_gdpr_erasure_handler",
]
