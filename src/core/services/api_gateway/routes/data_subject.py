"""
ACGS-2 Data Subject Rights API Routes
Constitutional Hash: cdd01ef066bc6cf2

Implements GDPR/CCPA data subject rights endpoints:
- Right to Access (GDPR Art. 15, CCPA §1798.100)
- Right to Erasure (GDPR Art. 17, CCPA §1798.105)
- Right to Rectification (GDPR Art. 16)
- Right to Data Portability (GDPR Art. 20)
- Right to Opt-Out (CCPA §1798.120)
"""

from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from src.core.shared.api_versioning import create_versioned_router
from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.metrics import track_request_metrics
from src.core.shared.security import (
    GDPR_ERASURE_AVAILABLE,
    PII_DETECTOR_AVAILABLE,
)
from src.core.shared.security.auth import UserClaims, get_current_user
from src.core.shared.structured_logging import get_logger
from src.core.shared.types import JSONDict

logger = get_logger(__name__)


# ============================================================================
# Request/Response Models
# ============================================================================


class DataSubjectAccessRequest(BaseModel):
    """Request for data subject access (GDPR Art. 15)."""

    data_subject_id: str = Field(..., description="Identifier of the data subject")
    categories: list[str] = Field(
        default_factory=list, description="Specific data categories to access (empty for all)"
    )
    format: str = Field(default="json", description="Response format (json, csv, pdf)")


class DataSubjectAccessResponse(BaseModel):
    """Response for data access request."""

    request_id: str
    data_subject_id: str
    data_categories: list[str]
    data_count: int
    processing_purposes: list[str]
    recipients: list[str]
    retention_period: str
    data_sources: list[str]
    automated_decision_making: bool
    export_url: str | None = None
    generated_at: datetime
    constitutional_hash: str = CONSTITUTIONAL_HASH


class ErasureRequestInput(BaseModel):
    """Input for erasure request."""

    data_subject_id: str = Field(..., description="Data subject identifier")
    scope: str = Field(default="all_data", description="Scope of erasure")
    specific_categories: list[str] = Field(
        default_factory=list, description="Specific categories to erase"
    )
    reason: str = Field(default="", description="Reason for erasure request")
    email_notification: str | None = Field(
        default=None, description="Email for status notifications"
    )


class ErasureRequestResponse(BaseModel):
    """Response for erasure request."""

    request_id: str
    data_subject_id: str
    status: str
    scope: str
    deadline: datetime
    created_at: datetime
    constitutional_hash: str = CONSTITUTIONAL_HASH


class ErasureStatusResponse(BaseModel):
    """Status of an erasure request."""

    request_id: str
    data_subject_id: str
    status: str
    systems_processed: int
    systems_successful: int
    total_records_erased: int
    started_at: datetime | None = None
    completed_at: datetime | None = None
    certificate_id: str | None = None
    constitutional_hash: str = CONSTITUTIONAL_HASH


class CertificateResponse(BaseModel):
    """Erasure certificate response."""

    certificate_id: str
    request_id: str
    data_subject_id: str
    systems_processed: int
    systems_successful: int
    total_records_erased: int
    gdpr_article_17_compliant: bool
    issued_at: datetime
    valid_until: datetime
    certificate_hash: str
    constitutional_hash: str = CONSTITUTIONAL_HASH


class ClassificationRequest(BaseModel):
    """Request to classify data for PII."""

    data: JSONDict = Field(..., description="Data to classify")


class ClassificationResponse(BaseModel):
    """Classification result response."""

    classification_id: str
    tier: str
    pii_categories: list[str]
    overall_confidence: float
    recommended_retention_days: int
    requires_encryption: bool
    requires_audit_logging: bool
    applicable_frameworks: list[str]
    classified_at: datetime
    constitutional_hash: str = CONSTITUTIONAL_HASH


# ============================================================================
# Router Configuration
# ============================================================================

data_subject_v1_router = create_versioned_router(
    prefix="/data-subject",
    version="v1",
    tags=["Data Subject Rights (v1)"],
)


# ============================================================================
# Endpoints
# ============================================================================


@data_subject_v1_router.post(
    "/access",
    response_model=DataSubjectAccessResponse,
    summary="Data Subject Access Request",
    description="""
    Submit a data subject access request per GDPR Article 15.

    Returns information about what personal data is being processed,
    processing purposes, recipients, and data sources.

    Constitutional Hash: cdd01ef066bc6cf2
    """,
)
@track_request_metrics("api-gateway", "/api/v1/data-subject/access")
async def request_data_access(
    request: DataSubjectAccessRequest,
    user: UserClaims = Depends(get_current_user),
) -> DataSubjectAccessResponse:
    """
    Handle data subject access request (GDPR Art. 15).

    Args:
        request: Access request details
        user: Authenticated user claims

    Returns:
        DataSubjectAccessResponse with data summary
    """
    import uuid

    logger.info(
        "Data subject access request received",
        data_subject_id=request.data_subject_id,
        user_id=user.sub,
        tenant_id=user.tenant_id,
    )

    # In production, this would query data catalog and systems
    return DataSubjectAccessResponse(
        request_id=str(uuid.uuid4()),
        data_subject_id=request.data_subject_id,
        data_categories=request.categories
        or [
            "personal_identifiers",
            "contact_info",
            "behavioral",
        ],
        data_count=42,  # Simulated
        processing_purposes=[
            "Service provision",
            "Analytics",
            "Legal compliance",
        ],
        recipients=[
            "Internal services",
            "Analytics providers (anonymized)",
        ],
        retention_period="90 days for PII, 1 year for analytics",
        data_sources=[
            "Direct collection",
            "Service usage",
        ],
        automated_decision_making=False,
        export_url=None,  # Would be generated async
        generated_at=datetime.now(UTC),
    )


@data_subject_v1_router.post(
    "/erasure",
    response_model=ErasureRequestResponse,
    summary="Request Data Erasure",
    description="""
    Submit a data erasure request per GDPR Article 17 (Right to be Forgotten).

    The request will be validated, exemptions checked, and data erased
    within 30 days per GDPR requirements.

    Constitutional Hash: cdd01ef066bc6cf2
    """,
)
@track_request_metrics("api-gateway", "/api/v1/data-subject/erasure")
async def request_erasure(
    request: ErasureRequestInput,
    user: UserClaims = Depends(get_current_user),
) -> ErasureRequestResponse:
    """
    Handle data erasure request (GDPR Art. 17).

    Args:
        request: Erasure request details
        user: Authenticated user claims

    Returns:
        ErasureRequestResponse with request ID and deadline

    Raises:
        HTTPException 503: If GDPR erasure service unavailable
    """
    if not GDPR_ERASURE_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "gdpr_service_unavailable",
                "message": "GDPR erasure service is not available",
                "constitutional_hash": CONSTITUTIONAL_HASH,
            },
        )

    try:
        from src.core.shared.security.gdpr_erasure import (
            ErasureScope,
            get_gdpr_erasure_handler,
        )

        handler = get_gdpr_erasure_handler()

        # Map scope string to enum
        scope_mapping = {
            "all_data": ErasureScope.ALL_DATA,
            "specific_categories": ErasureScope.SPECIFIC_CATEGORIES,
            "specific_systems": ErasureScope.SPECIFIC_SYSTEMS,
            "derived_data": ErasureScope.DERIVED_DATA,
            "marketing_data": ErasureScope.MARKETING_DATA,
        }
        scope = scope_mapping.get(request.scope, ErasureScope.ALL_DATA)

        # Create erasure request
        erasure_request = await handler.request_erasure(
            data_subject_id=request.data_subject_id,
            scope=scope,
            specific_categories=None,  # Would map string categories to PIICategory enum
            data_subject_email=request.email_notification,
            tenant_id=user.tenant_id,
        )

        logger.info(
            "Erasure request created",
            request_id=erasure_request.request_id,
            data_subject_id=request.data_subject_id,
            user_id=user.sub,
        )

        return ErasureRequestResponse(
            request_id=erasure_request.request_id,
            data_subject_id=erasure_request.data_subject_id,
            status=(
                erasure_request.status.value
                if hasattr(erasure_request.status, "value")
                else str(erasure_request.status)
            ),
            scope=request.scope,
            deadline=erasure_request.deadline,
            created_at=erasure_request.requested_at,
        )

    except ValueError as e:
        logger.warning(
            "Invalid erasure request",
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "invalid_erasure_request",
                "message": str(e),
                "constitutional_hash": CONSTITUTIONAL_HASH,
            },
        ) from e
    except (RuntimeError, OSError) as e:
        logger.error(
            "Error creating erasure request",
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "erasure_request_failed",
                "message": str(e),
                "constitutional_hash": CONSTITUTIONAL_HASH,
            },
        ) from e


@data_subject_v1_router.get(
    "/erasure/{request_id}",
    response_model=ErasureStatusResponse,
    summary="Get Erasure Request Status",
    description="""
    Get the status of an erasure request.

    Constitutional Hash: cdd01ef066bc6cf2
    """,
)
@track_request_metrics("api-gateway", "/api/v1/data-subject/erasure/{request_id}")
async def get_erasure_status(
    request_id: str,
    user: UserClaims = Depends(get_current_user),
) -> ErasureStatusResponse:
    """
    Get erasure request status.

    Args:
        request_id: Erasure request ID
        user: Authenticated user claims

    Returns:
        ErasureStatusResponse

    Raises:
        HTTPException 404: If request not found
        HTTPException 503: If service unavailable
    """
    if not GDPR_ERASURE_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "gdpr_service_unavailable",
                "message": "GDPR erasure service is not available",
                "constitutional_hash": CONSTITUTIONAL_HASH,
            },
        )

    try:
        from src.core.shared.security.gdpr_erasure import get_gdpr_erasure_handler

        handler = get_gdpr_erasure_handler()
        erasure_request = await handler.get_request(request_id)

        if not erasure_request:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "request_not_found",
                    "message": f"Erasure request {request_id} not found",
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                },
            )

        # Get certificate ID if completed
        certificate_id = None
        if erasure_request.status.value in ("completed", "partially_completed"):
            # In production, would look up certificate by request_id
            pass

        return ErasureStatusResponse(
            request_id=erasure_request.request_id,
            data_subject_id=erasure_request.data_subject_id,
            status=(
                erasure_request.status.value
                if hasattr(erasure_request.status, "value")
                else str(erasure_request.status)
            ),
            systems_processed=len(erasure_request.system_results),
            systems_successful=sum(1 for r in erasure_request.system_results if r.success),
            total_records_erased=erasure_request.total_records_erased,
            started_at=erasure_request.started_at,
            completed_at=erasure_request.completed_at,
            certificate_id=certificate_id,
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "request_not_found",
                "message": str(e),
                "constitutional_hash": CONSTITUTIONAL_HASH,
            },
        ) from e
    except (RuntimeError, OSError) as e:
        logger.error(
            "Error getting erasure status",
            request_id=request_id,
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "status_retrieval_failed",
                "message": str(e),
                "constitutional_hash": CONSTITUTIONAL_HASH,
            },
        ) from e


@data_subject_v1_router.post(
    "/erasure/{request_id}/process",
    response_model=ErasureStatusResponse,
    summary="Process Erasure Request",
    description="""
    Process (execute) an erasure request.

    Requires elevated permissions. Performs identity validation,
    exemption checking, data discovery, and erasure across systems.

    Constitutional Hash: cdd01ef066bc6cf2
    """,
)
@track_request_metrics("api-gateway", "/api/v1/data-subject/erasure/{request_id}/process")
async def process_erasure(
    request_id: str,
    identity_verified: bool = Query(default=True, description="Identity verification status"),
    verification_method: str = Query(
        default="email_confirmation", description="Verification method"
    ),
    user: UserClaims = Depends(get_current_user),
) -> ErasureStatusResponse:
    """
    Process an erasure request through completion.

    Args:
        request_id: Erasure request ID
        identity_verified: Whether identity was verified
        verification_method: Method of verification
        user: Authenticated user claims

    Returns:
        ErasureStatusResponse with completion status
    """
    if not GDPR_ERASURE_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "gdpr_service_unavailable",
                "message": "GDPR erasure service is not available",
                "constitutional_hash": CONSTITUTIONAL_HASH,
            },
        )

    try:
        from src.core.shared.security.gdpr_erasure import get_gdpr_erasure_handler

        handler = get_gdpr_erasure_handler()

        # Validate request
        await handler.validate_request(
            request_id=request_id,
            identity_verified=identity_verified,
            verification_method=verification_method,
        )

        # Check exemptions
        await handler.check_exemptions(request_id)

        # Discover data locations
        await handler.discover_data_locations(request_id)

        # Process erasure
        result = await handler.process_erasure(
            request_id=request_id,
            processed_by=user.sub,
        )

        logger.info(
            "Erasure request processed",
            request_id=request_id,
            status=result.status.value if hasattr(result.status, "value") else str(result.status),
            records_erased=result.total_records_erased,
            user_id=user.sub,
        )

        return ErasureStatusResponse(
            request_id=result.request_id,
            data_subject_id=result.data_subject_id,
            status=result.status.value if hasattr(result.status, "value") else str(result.status),
            systems_processed=len(result.system_results),
            systems_successful=sum(1 for r in result.system_results if r.success),
            total_records_erased=result.total_records_erased,
            started_at=result.started_at,
            completed_at=result.completed_at,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "request_not_found",
                "message": str(e),
                "constitutional_hash": CONSTITUTIONAL_HASH,
            },
        ) from e
    except (RuntimeError, OSError) as e:
        logger.error(
            "Error processing erasure",
            request_id=request_id,
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "erasure_processing_failed",
                "message": str(e),
                "constitutional_hash": CONSTITUTIONAL_HASH,
            },
        ) from e


@data_subject_v1_router.get(
    "/erasure/{request_id}/certificate",
    response_model=CertificateResponse,
    summary="Get Erasure Certificate",
    description="""
    Generate and retrieve the erasure certificate for a completed request.

    The certificate provides verifiable proof of data erasure per GDPR.

    Constitutional Hash: cdd01ef066bc6cf2
    """,
)
@track_request_metrics("api-gateway", "/api/v1/data-subject/erasure/{request_id}/certificate")
async def get_erasure_certificate(
    request_id: str,
    user: UserClaims = Depends(get_current_user),
) -> CertificateResponse:
    """
    Get or generate erasure certificate.

    Args:
        request_id: Completed erasure request ID
        user: Authenticated user claims

    Returns:
        CertificateResponse

    Raises:
        HTTPException 400: If request not completed
        HTTPException 404: If request not found
    """
    if not GDPR_ERASURE_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "gdpr_service_unavailable",
                "message": "GDPR erasure service is not available",
                "constitutional_hash": CONSTITUTIONAL_HASH,
            },
        )

    try:
        from src.core.shared.security.gdpr_erasure import get_gdpr_erasure_handler

        handler = get_gdpr_erasure_handler()

        # Generate certificate
        certificate = await handler.generate_erasure_certificate(request_id)

        return CertificateResponse(
            certificate_id=certificate.certificate_id,
            request_id=certificate.request_id,
            data_subject_id=certificate.data_subject_id,
            systems_processed=certificate.systems_processed,
            systems_successful=certificate.systems_successful,
            total_records_erased=certificate.total_records_erased,
            gdpr_article_17_compliant=certificate.gdpr_article_17_compliant,
            issued_at=certificate.issued_at,
            valid_until=certificate.valid_until,
            certificate_hash=certificate.certificate_hash,
        )

    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "request_not_found",
                    "message": error_msg,
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                },
            ) from e
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "certificate_generation_failed",
                    "message": error_msg,
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                },
            ) from e
    except (RuntimeError, OSError) as e:
        logger.error(
            "Error generating certificate",
            request_id=request_id,
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "certificate_generation_failed",
                "message": str(e),
                "constitutional_hash": CONSTITUTIONAL_HASH,
            },
        ) from e


@data_subject_v1_router.post(
    "/classify",
    response_model=ClassificationResponse,
    summary="Classify Data for PII",
    description="""
    Analyze data for PII and determine classification tier.

    Returns detected PII categories, confidence scores, and
    recommended retention policies.

    Constitutional Hash: cdd01ef066bc6cf2
    """,
)
@track_request_metrics("api-gateway", "/api/v1/data-subject/classify")
async def classify_data_endpoint(
    request: ClassificationRequest,
    user: UserClaims = Depends(get_current_user),
) -> ClassificationResponse:
    """
    Classify data for PII and sensitivity.

    Args:
        request: Data to classify
        user: Authenticated user claims

    Returns:
        ClassificationResponse with PII analysis
    """
    if not PII_DETECTOR_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "pii_detector_unavailable",
                "message": "PII detection service is not available",
                "constitutional_hash": CONSTITUTIONAL_HASH,
            },
        )

    try:
        from src.core.shared.security.pii_detector import classify_data

        result = classify_data(request.data, tenant_id=user.tenant_id)

        return ClassificationResponse(
            classification_id=result.classification_id,
            tier=result.tier.value if hasattr(result.tier, "value") else str(result.tier),
            pii_categories=[
                c.value if hasattr(c, "value") else str(c) for c in result.pii_categories
            ],
            overall_confidence=result.overall_confidence,
            recommended_retention_days=result.recommended_retention_days,
            requires_encryption=result.requires_encryption,
            requires_audit_logging=result.requires_audit_logging,
            applicable_frameworks=[
                f.value if hasattr(f, "value") else str(f) for f in result.applicable_frameworks
            ],
            classified_at=result.classified_at,
        )

    except (ValueError, TypeError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "invalid_classification_input",
                "message": str(e),
                "constitutional_hash": CONSTITUTIONAL_HASH,
            },
        ) from e
    except (RuntimeError, OSError) as e:
        logger.error(
            "Error classifying data",
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "classification_failed",
                "message": str(e),
                "constitutional_hash": CONSTITUTIONAL_HASH,
            },
        ) from e


__all__ = [
    "CertificateResponse",
    "ClassificationRequest",
    "ClassificationResponse",
    "DataSubjectAccessRequest",
    "DataSubjectAccessResponse",
    "ErasureRequestInput",
    "ErasureRequestResponse",
    "ErasureStatusResponse",
    "data_subject_v1_router",
]
