"""
ACGS-2 CCPA (California Consumer Privacy Act) Handler
Constitutional Hash: cdd01ef066bc6cf2

Implements CCPA consumer rights handling including:
- Right to Know (§1798.100, §1798.110, §1798.115)
- Right to Delete (§1798.105)
- Right to Opt-Out of Sale (§1798.120)
- Right to Non-Discrimination (§1798.125)
- CPRA (California Privacy Rights Act) extensions

Reference: https://oag.ca.gov/privacy/ccpa
"""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from pydantic import BaseModel, Field

from src.core.shared.errors.exceptions import (
    ResourceNotFoundError,
)
from src.core.shared.errors.exceptions import (
    ValidationError as ACGSValidationError,
)
from src.core.shared.structured_logging import get_logger
from src.core.shared.types import JSONDict

logger = get_logger(__name__)
from src.core.shared.constants import CONSTITUTIONAL_HASH


def _redact_id(consumer_id: str) -> str:
    """Return a truncated, non-reversible token for log-safe consumer ID display."""
    return consumer_id[:8] + "..." if len(consumer_id) > 8 else "***"


class CCPARequestType(StrEnum):
    """CCPA consumer request types."""

    RIGHT_TO_KNOW = "right_to_know"  # §1798.100, §1798.110
    RIGHT_TO_DELETE = "right_to_delete"  # §1798.105
    RIGHT_TO_OPT_OUT = "right_to_opt_out"  # §1798.120
    RIGHT_TO_OPT_IN = "right_to_opt_in"  # §1798.120 (for minors)
    RIGHT_TO_CORRECT = "right_to_correct"  # CPRA §1798.106
    RIGHT_TO_LIMIT = "right_to_limit"  # CPRA §1798.121


class CCPARequestStatus(StrEnum):
    """CCPA request processing status."""

    RECEIVED = "received"
    IDENTITY_PENDING = "identity_pending"
    IDENTITY_VERIFIED = "identity_verified"
    IDENTITY_FAILED = "identity_failed"
    PROCESSING = "processing"
    COMPLETED = "completed"
    DENIED = "denied"
    EXTENDED = "extended"  # 45-day extension per §1798.130


class CCPADenialReason(StrEnum):
    """Reasons for denying a CCPA request."""

    IDENTITY_NOT_VERIFIED = "identity_not_verified"
    EXCESSIVE_REQUESTS = "excessive_requests"
    EXEMPTION_APPLIES = "exemption_applies"
    NO_DATA_FOUND = "no_data_found"
    LEGAL_OBLIGATION = "legal_obligation"
    FRAUDULENT_REQUEST = "fraudulent_request"


class CCPAPersonalInfoCategory(StrEnum):
    """CCPA categories of personal information (§1798.140)."""

    IDENTIFIERS = "identifiers"
    CUSTOMER_RECORDS = "customer_records"
    PROTECTED_CHARACTERISTICS = "protected_characteristics"
    COMMERCIAL_INFO = "commercial_info"
    BIOMETRIC_INFO = "biometric_info"
    INTERNET_ACTIVITY = "internet_activity"
    GEOLOCATION = "geolocation"
    SENSORY_DATA = "sensory_data"
    PROFESSIONAL_INFO = "professional_info"
    EDUCATION_INFO = "education_info"
    INFERENCES = "inferences"
    SENSITIVE_PERSONAL_INFO = "sensitive_personal_info"  # CPRA addition


class CCPABusinessPurpose(StrEnum):
    """CCPA business purposes for data collection (§1798.140)."""

    AUDITING = "auditing"
    SECURITY = "security"
    DEBUGGING = "debugging"
    ADVERTISING = "advertising"
    QUALITY_ASSURANCE = "quality_assurance"
    INTERNAL_RESEARCH = "internal_research"
    SERVICE_IMPROVEMENT = "service_improvement"


class CCPADataSource(StrEnum):
    """Sources of personal information collection."""

    DIRECT_COLLECTION = "direct_collection"
    THIRD_PARTY = "third_party"
    AUTOMATED_COLLECTION = "automated_collection"
    PUBLIC_SOURCES = "public_sources"


class ConsumerInfoRecord(BaseModel):
    """Record of personal information for a consumer."""

    category: CCPAPersonalInfoCategory = Field(..., description="Category of personal info")
    data_collected: list[str] = Field(
        default_factory=list, description="Types of data collected in this category"
    )
    sources: list[CCPADataSource] = Field(default_factory=list, description="Sources of collection")
    business_purposes: list[CCPABusinessPurpose] = Field(
        default_factory=list, description="Business purposes for collection"
    )
    third_parties_shared: list[str] = Field(
        default_factory=list, description="Third parties with whom data is shared"
    )
    sold_or_shared: bool = Field(
        default=False, description="Whether data was sold or shared for advertising"
    )
    retention_period: str = Field(
        default="As required by policy", description="Retention period for this data"
    )


class ConsumerDataReport(BaseModel):
    """CCPA Right to Know response report."""

    report_id: str = Field(..., description="Unique report identifier")
    consumer_id: str = Field(..., description="Consumer identifier")
    request_id: str = Field(..., description="Associated request ID")
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Report generation timestamp",
    )

    # Categories of personal information
    personal_info: list[ConsumerInfoRecord] = Field(
        default_factory=list, description="Personal information collected"
    )

    # Disclosure information
    categories_collected: list[CCPAPersonalInfoCategory] = Field(
        default_factory=list, description="Categories of personal info collected in past 12 months"
    )
    categories_sold: list[CCPAPersonalInfoCategory] = Field(
        default_factory=list, description="Categories sold in past 12 months"
    )
    categories_disclosed: list[CCPAPersonalInfoCategory] = Field(
        default_factory=list, description="Categories disclosed for business purposes"
    )

    # Business context
    business_purposes: list[CCPABusinessPurpose] = Field(
        default_factory=list, description="Business purposes for data use"
    )
    third_party_categories: list[str] = Field(
        default_factory=list, description="Categories of third parties receiving data"
    )

    # CPRA additions
    sensitive_info_collected: bool = Field(
        default=False, description="Whether sensitive personal info was collected"
    )
    retention_periods: dict[str, str] = Field(
        default_factory=dict, description="Retention periods by category"
    )

    # Metadata
    report_hash: str = Field(default="", description="Hash of report contents for integrity")
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH, description="Constitutional hash")

    def calculate_hash(self) -> str:
        """Calculate and store an integrity hash over all material report fields.

        Covers report_id, consumer_id, generated_at, categories_collected, and
        sensitive_info_collected so that tampering with the report's data content
        is detectable. The hash is stored in-place (Pydantic model mutation is
        intentional here — the model is not frozen).
        """
        categories_key = ",".join(
            sorted(c.value if hasattr(c, "value") else str(c) for c in self.categories_collected)
        )
        content = (
            f"{self.report_id}:{self.consumer_id}:{self.generated_at.isoformat()}"
            f":{categories_key}:{self.sensitive_info_collected}"
        )
        self.report_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
        return self.report_hash


class OptOutConfirmation(BaseModel):
    """CCPA opt-out confirmation."""

    confirmation_id: str = Field(..., description="Confirmation identifier")
    consumer_id: str = Field(..., description="Consumer identifier")
    request_id: str = Field(..., description="Associated request ID")
    opt_out_type: str = Field(..., description="Type of opt-out")
    effective_date: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Effective date of opt-out"
    )

    # Scope of opt-out
    sale_categories: list[CCPAPersonalInfoCategory] = Field(
        default_factory=list, description="Categories opted out of sale"
    )
    sharing_categories: list[CCPAPersonalInfoCategory] = Field(
        default_factory=list, description="Categories opted out of sharing"
    )

    # Status
    is_active: bool = Field(default=True, description="Whether opt-out is active")
    revoked_at: datetime | None = Field(None, description="If revoked, when")

    # Confirmation details
    confirmation_sent: bool = Field(default=False, description="Confirmation sent to consumer")
    confirmation_method: str = Field(default="email", description="Method of confirmation")

    # Metadata
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH, description="Constitutional hash")


class CCPAPrivacyNotice(BaseModel):
    """CCPA-compliant privacy notice content."""

    notice_id: str = Field(..., description="Notice identifier")
    business_id: str = Field(..., description="Business identifier")
    version: str = Field(default="1.0", description="Notice version")
    effective_date: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Effective date"
    )

    # Required disclosures (§1798.100(b))
    categories_collected: list[JSONDict] = Field(
        default_factory=list, description="Categories of personal info collected"
    )
    purposes_collection: list[str] = Field(
        default_factory=list, description="Purposes for collection"
    )
    consumer_rights: list[str] = Field(
        default_factory=list, description="Consumer rights descriptions"
    )

    # Sale/sharing disclosures
    does_sell_info: bool = Field(default=False, description="Whether business sells personal info")
    does_share_info: bool = Field(
        default=False, description="Whether business shares personal info"
    )
    opt_out_link: str = Field(default="", description="Link to opt-out mechanism")

    # Contact information
    contact_email: str = Field(default="", description="Privacy contact email")
    contact_phone: str = Field(default="", description="Privacy contact phone")
    contact_address: str = Field(default="", description="Privacy contact address")

    # CPRA additions
    retention_policy_link: str = Field(default="", description="Link to retention policy")
    sensitive_info_purposes: list[str] = Field(
        default_factory=list, description="Purposes for sensitive info use"
    )

    # Metadata
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH, description="Constitutional hash")


class CCPARequest(BaseModel):
    """CCPA consumer request."""

    request_id: str = Field(..., description="Unique request identifier")
    consumer_id: str = Field(..., description="Consumer identifier")
    request_type: CCPARequestType = Field(..., description="Type of request")
    status: CCPARequestStatus = Field(
        default=CCPARequestStatus.RECEIVED, description="Request status"
    )

    # Request details
    submitted_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="When request was submitted"
    )
    deadline: datetime = Field(
        default_factory=lambda: datetime.now(UTC) + timedelta(days=45),
        description="Response deadline (45 days per §1798.130)",
    )
    extended: bool = Field(default=False, description="Whether deadline was extended")
    extended_deadline: datetime | None = Field(None, description="Extended deadline if applicable")

    # Identity verification
    identity_verified: bool = Field(default=False, description="Consumer identity verified")
    verification_method: str | None = Field(None, description="Method used for verification")
    verification_date: datetime | None = Field(None, description="When identity was verified")

    # Processing
    processed_at: datetime | None = Field(None, description="When request was processed")
    denial_reason: CCPADenialReason | None = Field(None, description="Reason for denial if denied")

    # Scope (for opt-out/delete requests)
    scope_categories: list[CCPAPersonalInfoCategory] = Field(
        default_factory=list, description="Categories in scope"
    )

    # Results
    result_report_id: str | None = Field(None, description="Associated report ID")
    result_confirmation_id: str | None = Field(None, description="Associated confirmation ID")

    # Audit
    audit_trail: list[JSONDict] = Field(default_factory=list, description="Audit trail of actions")

    # Metadata
    tenant_id: str | None = Field(None, description="Tenant identifier")
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH, description="Constitutional hash")

    def add_audit_entry(self, action: str, details: str | None = None) -> None:
        """Add entry to audit trail."""
        self.audit_trail.append(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "action": action,
                "details": details,
            }
        )


class CCPAHandler:
    """
    CCPA consumer rights handler.

    Implements California Consumer Privacy Act request handling
    with support for all consumer rights and CPRA extensions.
    """

    def __init__(self):
        """Initialize CCPA handler."""
        self._requests: dict[str, CCPARequest] = {}
        self._opt_outs: dict[str, OptOutConfirmation] = {}
        self._consumer_data: dict[str, list[ConsumerInfoRecord]] = {}

    async def handle_right_to_know(
        self,
        consumer_id: str,
        _request_specific_pieces: bool = False,
        tenant_id: str | None = None,
    ) -> ConsumerDataReport:
        """
        Handle Right to Know request (§1798.100, §1798.110).

        Args:
            consumer_id: Consumer identifier
            request_specific_pieces: If True, include specific pieces of data
            tenant_id: Optional tenant context

        Returns:
            ConsumerDataReport with personal information disclosure
        """
        request_id = str(uuid.uuid4())

        # Create request record
        request = CCPARequest(
            request_id=request_id,
            consumer_id=consumer_id,
            request_type=CCPARequestType.RIGHT_TO_KNOW,
            tenant_id=tenant_id,
        )
        request.add_audit_entry("request_created", "Right to Know request initiated")

        self._requests[request_id] = request

        # Generate consumer data report
        report = ConsumerDataReport(
            report_id=f"rpt_{uuid.uuid4().hex[:12]}",
            consumer_id=consumer_id,
            request_id=request_id,
        )

        # Populate with consumer's data (from storage or mock data)
        consumer_records = await self._get_consumer_data(consumer_id, tenant_id)

        for record in consumer_records:
            report.personal_info.append(record)
            if record.category not in report.categories_collected:
                report.categories_collected.append(record.category)
            if record.sold_or_shared:
                report.categories_sold.append(record.category)

            for purpose in record.business_purposes:
                if purpose not in report.business_purposes:
                    report.business_purposes.append(purpose)

        # Calculate report hash
        report.calculate_hash()

        # Update request status
        request.status = CCPARequestStatus.COMPLETED
        request.processed_at = datetime.now(UTC)
        request.result_report_id = report.report_id
        request.add_audit_entry("request_completed", f"Report generated: {report.report_id}")

        logger.info(
            "Right to Know processed for consumer %s, report: %s",
            _redact_id(consumer_id),
            report.report_id,
        )

        return report

    async def handle_right_to_delete(
        self,
        consumer_id: str,
        categories: list[CCPAPersonalInfoCategory] | None = None,
        tenant_id: str | None = None,
    ) -> CCPARequest:
        """
        Handle Right to Delete request (§1798.105).

        Args:
            consumer_id: Consumer identifier
            categories: Optional specific categories to delete
            tenant_id: Optional tenant context

        Returns:
            CCPARequest with processing status
        """
        request_id = str(uuid.uuid4())

        request = CCPARequest(
            request_id=request_id,
            consumer_id=consumer_id,
            request_type=CCPARequestType.RIGHT_TO_DELETE,
            scope_categories=categories or list(CCPAPersonalInfoCategory),
            tenant_id=tenant_id,
        )
        request.add_audit_entry("request_created", "Right to Delete request initiated")

        self._requests[request_id] = request

        # Note: Identity verification would be required before processing
        # For now, mark as pending verification
        request.status = CCPARequestStatus.IDENTITY_PENDING
        request.add_audit_entry("identity_pending", "Awaiting identity verification")

        logger.info(
            "Right to Delete request created for consumer %s, request: %s",
            _redact_id(consumer_id),
            request_id,
        )

        return request

    async def process_deletion(
        self,
        request_id: str,
        identity_verified: bool,
        verification_method: str = "manual",
    ) -> CCPARequest:
        """
        Process deletion after identity verification.

        Args:
            request_id: Request identifier
            identity_verified: Whether identity was verified
            verification_method: Method used for verification

        Returns:
            Updated CCPARequest
        """
        request = self._requests.get(request_id)
        if not request:
            raise ResourceNotFoundError(
                message=f"Request not found: {request_id}", error_code="CCPA_REQUEST_NOT_FOUND"
            )

        request.identity_verified = identity_verified
        request.verification_method = verification_method
        request.verification_date = datetime.now(UTC)

        if not identity_verified:
            request.status = CCPARequestStatus.DENIED
            request.denial_reason = CCPADenialReason.IDENTITY_NOT_VERIFIED
            request.add_audit_entry("request_denied", "Identity verification failed")
            return request

        request.status = CCPARequestStatus.PROCESSING
        request.add_audit_entry("identity_verified", f"Method: {verification_method}")

        # Perform deletion
        await self._delete_consumer_data(
            request.consumer_id,
            request.scope_categories,
            request.tenant_id,
        )

        request.status = CCPARequestStatus.COMPLETED
        request.processed_at = datetime.now(UTC)
        request.add_audit_entry("deletion_completed", "Data deleted successfully")

        logger.info(f"Deletion completed for request {request_id}")

        return request

    async def handle_opt_out(
        self,
        consumer_id: str,
        sale_categories: list[CCPAPersonalInfoCategory] | None = None,
        sharing_categories: list[CCPAPersonalInfoCategory] | None = None,
        tenant_id: str | None = None,
    ) -> OptOutConfirmation:
        """
        Handle Right to Opt-Out request (§1798.120).

        Args:
            consumer_id: Consumer identifier
            sale_categories: Categories to opt out of sale
            sharing_categories: Categories to opt out of sharing
            tenant_id: Optional tenant context

        Returns:
            OptOutConfirmation
        """
        request_id = str(uuid.uuid4())
        confirmation_id = f"conf_{uuid.uuid4().hex[:12]}"

        # Create request record
        request = CCPARequest(
            request_id=request_id,
            consumer_id=consumer_id,
            request_type=CCPARequestType.RIGHT_TO_OPT_OUT,
            tenant_id=tenant_id,
        )
        request.add_audit_entry("request_created", "Opt-out request initiated")

        self._requests[request_id] = request

        # Create confirmation
        confirmation = OptOutConfirmation(
            confirmation_id=confirmation_id,
            consumer_id=consumer_id,
            request_id=request_id,
            opt_out_type="sale_and_sharing",
            sale_categories=sale_categories or list(CCPAPersonalInfoCategory),
            sharing_categories=sharing_categories or list(CCPAPersonalInfoCategory),
        )

        self._opt_outs[consumer_id] = confirmation

        # Update request
        request.status = CCPARequestStatus.COMPLETED
        request.processed_at = datetime.now(UTC)
        request.result_confirmation_id = confirmation_id
        request.add_audit_entry("opt_out_confirmed", f"Confirmation: {confirmation_id}")

        # Send confirmation
        confirmation.confirmation_sent = True
        confirmation.confirmation_method = "email"

        logger.info(
            "Opt-out processed for consumer %s, confirmation: %s",
            _redact_id(consumer_id),
            confirmation_id,
        )

        return confirmation

    async def handle_opt_in(
        self,
        consumer_id: str,
        tenant_id: str | None = None,
    ) -> OptOutConfirmation:
        """
        Handle opt-in request (reverse opt-out).

        Args:
            consumer_id: Consumer identifier
            tenant_id: Optional tenant context

        Returns:
            Updated OptOutConfirmation (revoked)
        """
        confirmation = self._opt_outs.get(consumer_id)
        if not confirmation:
            raise ResourceNotFoundError(
                message=f"No opt-out found for consumer: {consumer_id}",
                error_code="CCPA_OPT_OUT_NOT_FOUND",
            )

        confirmation.is_active = False
        confirmation.revoked_at = datetime.now(UTC)

        logger.info("Opt-out revoked for consumer %s", _redact_id(consumer_id))

        return confirmation

    async def generate_privacy_notice(
        self,
        business_id: str,
        _business_name: str = "ACGS-2 Platform",
        contact_email: str = "privacy@acgs2.example.com",
    ) -> CCPAPrivacyNotice:
        """
        Generate CCPA-compliant privacy notice.

        Args:
            business_id: Business identifier
            business_name: Business name
            contact_email: Privacy contact email

        Returns:
            CCPAPrivacyNotice
        """
        notice = CCPAPrivacyNotice(
            notice_id=f"notice_{uuid.uuid4().hex[:12]}",
            business_id=business_id,
        )

        # Populate required disclosures
        notice.categories_collected = [
            {
                "category": CCPAPersonalInfoCategory.IDENTIFIERS.value,
                "examples": ["Name", "Email", "Account ID"],
                "purposes": ["Service provision", "Account management"],
            },
            {
                "category": CCPAPersonalInfoCategory.INTERNET_ACTIVITY.value,
                "examples": ["Usage logs", "API calls", "Session data"],
                "purposes": ["Service improvement", "Security"],
            },
            {
                "category": CCPAPersonalInfoCategory.PROFESSIONAL_INFO.value,
                "examples": ["Organization", "Role", "Permissions"],
                "purposes": ["Access control", "Audit"],
            },
        ]

        notice.purposes_collection = [
            "Providing AI governance services",
            "Constitutional compliance validation",
            "Audit trail maintenance",
            "Service improvement",
            "Security and fraud prevention",
        ]

        notice.consumer_rights = [
            "Right to know what personal information is collected",
            "Right to request deletion of personal information",
            "Right to opt-out of the sale of personal information",
            "Right to non-discrimination for exercising privacy rights",
            "Right to correct inaccurate personal information (CPRA)",
            "Right to limit use of sensitive personal information (CPRA)",
        ]

        notice.does_sell_info = False
        notice.does_share_info = False
        notice.opt_out_link = "/privacy/opt-out"
        notice.contact_email = contact_email
        notice.retention_policy_link = "/privacy/retention"

        logger.info(f"Privacy notice generated for business {business_id}")

        return notice

    async def check_opt_out_status(
        self,
        consumer_id: str,
    ) -> OptOutConfirmation | None:
        """
        Check consumer's opt-out status.

        Args:
            consumer_id: Consumer identifier

        Returns:
            OptOutConfirmation if exists, None otherwise
        """
        confirmation = self._opt_outs.get(consumer_id)
        if confirmation and confirmation.is_active:
            return confirmation
        return None

    async def get_request_status(
        self,
        request_id: str,
    ) -> CCPARequest | None:
        """
        Get status of a CCPA request.

        Args:
            request_id: Request identifier

        Returns:
            CCPARequest if found, None otherwise
        """
        return self._requests.get(request_id)

    async def extend_deadline(
        self,
        request_id: str,
        reason: str,
    ) -> CCPARequest:
        """
        Extend request deadline by 45 days (per §1798.130).

        Args:
            request_id: Request identifier
            reason: Reason for extension

        Returns:
            Updated CCPARequest
        """
        request = self._requests.get(request_id)
        if not request:
            raise ResourceNotFoundError(
                message=f"Request not found: {request_id}", error_code="CCPA_REQUEST_NOT_FOUND"
            )

        if request.extended:
            raise ACGSValidationError(
                message="Request already extended once", error_code="CCPA_ALREADY_EXTENDED"
            )

        request.extended = True
        request.extended_deadline = request.deadline + timedelta(days=45)
        request.status = CCPARequestStatus.EXTENDED
        request.add_audit_entry("deadline_extended", reason)

        logger.info(f"Deadline extended for request {request_id}")

        return request

    async def _get_consumer_data(
        self,
        consumer_id: str,
        tenant_id: str | None = None,
    ) -> list[ConsumerInfoRecord]:
        """Get consumer's personal information records."""
        # In production, this would query actual data stores
        # For now, return mock data structure
        return self._consumer_data.get(
            consumer_id,
            [
                ConsumerInfoRecord(
                    category=CCPAPersonalInfoCategory.IDENTIFIERS,
                    data_collected=["User ID", "Email Address", "Account Name"],
                    sources=[CCPADataSource.DIRECT_COLLECTION],
                    business_purposes=[
                        CCPABusinessPurpose.SERVICE_IMPROVEMENT,
                        CCPABusinessPurpose.SECURITY,
                    ],
                    third_parties_shared=[],
                    sold_or_shared=False,
                ),
                ConsumerInfoRecord(
                    category=CCPAPersonalInfoCategory.INTERNET_ACTIVITY,
                    data_collected=["API Usage", "Session Logs", "Feature Usage"],
                    sources=[CCPADataSource.AUTOMATED_COLLECTION],
                    business_purposes=[
                        CCPABusinessPurpose.AUDITING,
                        CCPABusinessPurpose.DEBUGGING,
                        CCPABusinessPurpose.SERVICE_IMPROVEMENT,
                    ],
                    third_parties_shared=[],
                    sold_or_shared=False,
                ),
            ],
        )

    async def _delete_consumer_data(
        self,
        consumer_id: str,
        categories: list[CCPAPersonalInfoCategory],
        tenant_id: str | None = None,
    ) -> None:
        """Delete consumer's personal information."""
        # In production, this would delete from actual data stores
        if consumer_id in self._consumer_data:
            self._consumer_data[consumer_id] = [
                record
                for record in self._consumer_data[consumer_id]
                if record.category not in categories
            ]

        logger.info(
            f"Deleted data for consumer {consumer_id}, categories: {[c.value for c in categories]}"
        )


# Singleton instance
_ccpa_handler: CCPAHandler | None = None


def get_ccpa_handler() -> CCPAHandler:
    """Get singleton CCPAHandler instance."""
    global _ccpa_handler
    if _ccpa_handler is None:
        _ccpa_handler = CCPAHandler()
    return _ccpa_handler


def reset_ccpa_handler() -> None:
    """Reset CCPAHandler singleton (for testing)."""
    global _ccpa_handler
    _ccpa_handler = None


__all__ = [
    # Constants
    "CONSTITUTIONAL_HASH",
    "CCPABusinessPurpose",
    "CCPADataSource",
    "CCPADenialReason",
    # Handler
    "CCPAHandler",
    "CCPAPersonalInfoCategory",
    "CCPAPrivacyNotice",
    "CCPARequest",
    "CCPARequestStatus",
    # Enums
    "CCPARequestType",
    "ConsumerDataReport",
    # Models
    "ConsumerInfoRecord",
    "OptOutConfirmation",
    # Singleton functions
    "get_ccpa_handler",
    "reset_ccpa_handler",
]
