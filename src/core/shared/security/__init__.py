from typing import TYPE_CHECKING

from src.core.shared.constants import CONSTITUTIONAL_HASH

"""
ACGS-2 Security Module
Constitutional Hash: cdd01ef066bc6cf2

Centralized security utilities for the ACGS-2 platform:
- CORS configuration and validation
- Rate limiting middleware
- Tenant context middleware for multi-tenant isolation
- API key and token management
- Security headers enforcement
- Post-quantum cryptography (PQC) for quantum-resistant security
- Data classification and PII detection (§16.4)
- Retention policy management
- GDPR Article 17 erasure handling
"""

from .cors_config import (
    DEFAULT_ORIGINS,
    CORSConfig,
    CORSEnvironment,
    detect_environment,
    get_cors_config,
    get_strict_cors_config,
    validate_origin,
)
from .dual_key_jwt import (
    CONSTITUTIONAL_HASH as DUAL_KEY_CONSTITUTIONAL_HASH,
)
from .dual_key_jwt import (
    DualKeyConfig,
    DualKeyJWTValidator,
    JWTValidationResult,
    KeyMetadata,
    get_dual_key_validator,
)
from .error_sanitizer import safe_error_detail, safe_error_message, sanitize_error
from .expression_utils import redact_pii, safe_eval_expr
from .pqc import (
    CONSTITUTIONAL_HASH,
    ConstitutionalHashMismatchError,
    KEMResult,
    PQCConfigurationError,
    PQCDecapsulationError,
    PQCEncapsulationError,
    PQCError,
    PQCKeyGenerationError,
    PQCKeyPair,
    PQCSignature,
    PQCSignatureError,
    PQCVerificationError,
    PQCWrapper,
    SignatureSubstitutionError,
    UnsupportedAlgorithmError,
)
from .rate_limiter import (
    REDIS_AVAILABLE,
    TENANT_CONFIG_AVAILABLE,
    RateLimitAlgorithm,
    RateLimitConfig,
    RateLimitMiddleware,
    RateLimitResult,
    RateLimitRule,
    RateLimitScope,
    TenantQuota,
    TenantQuotaProviderProtocol,
    TenantRateLimitProvider,
    create_rate_limit_middleware,
)
from .security_headers import (
    SecurityHeadersConfig,
    SecurityHeadersMiddleware,
    add_security_headers,
)
from .tenant_context import (
    TENANT_ID_MAX_LENGTH,
    TENANT_ID_MIN_LENGTH,
    TENANT_ID_PATTERN,
    TenantContextConfig,
    TenantContextMiddleware,
    TenantValidationError,
    get_current_tenant_id,
    get_optional_tenant_id,
    get_tenant_id,
    require_tenant_scope,
    sanitize_tenant_id,
    validate_tenant_id,
)

# §16.4 Optional Security Modules
# TYPE_CHECKING ensures mypy sees correct types; runtime preserves graceful degradation.

if TYPE_CHECKING:
    # Data Classification System (§16.4)
    # CCPA (California Consumer Privacy Act) Handler
    from .ccpa_handler import (
        CONSTITUTIONAL_HASH as CCPA_CONSTITUTIONAL_HASH,
    )
    from .ccpa_handler import (
        CCPABusinessPurpose,
        CCPADataSource,
        CCPADenialReason,
        CCPAHandler,
        CCPAPersonalInfoCategory,
        CCPAPrivacyNotice,
        CCPARequest,
        CCPARequestStatus,
        CCPARequestType,
        ConsumerDataReport,
        ConsumerInfoRecord,
        OptOutConfirmation,
        get_ccpa_handler,
        reset_ccpa_handler,
    )
    from .data_classification import (
        CONSTITUTIONAL_HASH as DATA_CLASSIFICATION_HASH,
    )
    from .data_classification import (
        DEFAULT_RETENTION_POLICIES,
        PII_COMPLIANCE_MAPPING,
        TIER_REQUIREMENTS,
        ClassificationResult,
        ComplianceFramework,
        DataClassificationPolicy,
        DataClassificationTier,
        DisposalMethod,
        GDPRLawfulBasis,
        PIICategory,
        PIIDetection,
        RetentionPolicy,
        classify_by_pii_categories,
        get_compliance_frameworks,
        get_default_retention_policy,
        get_tier_requirements,
    )

    # GDPR Article 17 Erasure Handler
    from .gdpr_erasure import (
        DataLocation,
        DataLocationType,
        ErasureCertificate,
        ErasureExemption,
        ErasureRequest,
        ErasureScope,
        ErasureStatus,
        ErasureSystemResult,
        GDPRErasureHandler,
        get_gdpr_erasure_handler,
        reset_gdpr_erasure_handler,
    )

    # PII Detection Engine
    from .pii_detector import (
        FIELD_NAME_INDICATORS,
        PII_PATTERNS,
        PIIDetector,
        PIIPattern,
        classify_data,
        detect_pii,
        get_pii_detector,
        reset_pii_detector,
    )

    # Retention Policy Engine
    from .retention_policy import (
        AnonymizeHandler,
        ArchiveHandler,
        DeleteHandler,
        DisposalHandler,
        DisposalResult,
        InMemoryRetentionStorage,
        PseudonymizeHandler,
        RetentionAction,
        RetentionActionType,
        RetentionEnforcementReport,
        RetentionPolicyEngine,
        RetentionRecord,
        RetentionStatus,
        RetentionStorageProtocol,
        get_retention_engine,
        reset_retention_engine,
    )

    # Secret Rotation Lifecycle (T004)
    from .secret_rotation import (
        CONSTITUTIONAL_HASH as SECRET_ROTATION_CONSTITUTIONAL_HASH,
    )
    from .secret_rotation import (
        InMemorySecretBackend,
        RotationPolicy,
        RotationRecord,
        RotationResult,
        RotationStatus,
        RotationTrigger,
        SecretBackend,
        SecretRotationManager,
        SecretType,
        SecretVersion,
        VaultSecretBackend,
        get_rotation_manager,
        reset_rotation_manager,
    )

    # URL/File Validation (SEC-003 SSRF, SEC-006 File Upload)
    from .url_file_validator import (
        CONSTITUTIONAL_HASH as URL_FILE_CONSTITUTIONAL_HASH,
    )
    from .url_file_validator import (
        FileSignature,
        FileType,
        FileValidationConfig,
        FileValidationError,
        FileValidator,
        SSRFProtectionConfig,
        URLValidationError,
        URLValidator,
        get_file_validator,
        get_url_validator,
        reset_file_validator,
        reset_url_validator,
        validate_file_content,
        validate_upload,
        validate_url,
    )

    DATA_CLASSIFICATION_AVAILABLE: bool
    PII_DETECTOR_AVAILABLE: bool
    RETENTION_POLICY_AVAILABLE: bool
    GDPR_ERASURE_AVAILABLE: bool
    CCPA_HANDLER_AVAILABLE: bool
    URL_FILE_VALIDATOR_AVAILABLE: bool
    SECRET_ROTATION_AVAILABLE: bool

else:
    # Data Classification System (§16.4)
    try:
        from .data_classification import (
            CONSTITUTIONAL_HASH as DATA_CLASSIFICATION_HASH,
        )
        from .data_classification import (
            DEFAULT_RETENTION_POLICIES,
            PII_COMPLIANCE_MAPPING,
            TIER_REQUIREMENTS,
            ClassificationResult,
            ComplianceFramework,
            DataClassificationPolicy,
            DataClassificationTier,
            DisposalMethod,
            GDPRLawfulBasis,
            PIICategory,
            PIIDetection,
            RetentionPolicy,
            classify_by_pii_categories,
            get_compliance_frameworks,
            get_default_retention_policy,
            get_tier_requirements,
        )

        DATA_CLASSIFICATION_AVAILABLE = True
    except ImportError:
        DATA_CLASSIFICATION_AVAILABLE = False
        DATA_CLASSIFICATION_HASH = CONSTITUTIONAL_HASH
        DataClassificationTier = object
        PIICategory = object
        ComplianceFramework = object
        DisposalMethod = object
        GDPRLawfulBasis = object
        PIIDetection = object
        ClassificationResult = object
        RetentionPolicy = object
        DataClassificationPolicy = object
        TIER_REQUIREMENTS = {}
        PII_COMPLIANCE_MAPPING = {}
        DEFAULT_RETENTION_POLICIES = []
        get_tier_requirements = object
        get_compliance_frameworks = object
        get_default_retention_policy = object
        classify_by_pii_categories = object

    # PII Detection Engine
    try:
        from .pii_detector import (
            FIELD_NAME_INDICATORS,
            PII_PATTERNS,
            PIIDetector,
            PIIPattern,
            classify_data,
            detect_pii,
            get_pii_detector,
            reset_pii_detector,
        )

        PII_DETECTOR_AVAILABLE = True
    except ImportError:
        PII_DETECTOR_AVAILABLE = False
        PIIDetector = object
        PIIPattern = object
        PII_PATTERNS = []
        FIELD_NAME_INDICATORS = {}
        get_pii_detector = object
        reset_pii_detector = object
        detect_pii = object
        classify_data = object

    # Retention Policy Engine
    try:
        from .retention_policy import (
            AnonymizeHandler,
            ArchiveHandler,
            DeleteHandler,
            DisposalHandler,
            DisposalResult,
            InMemoryRetentionStorage,
            PseudonymizeHandler,
            RetentionAction,
            RetentionActionType,
            RetentionEnforcementReport,
            RetentionPolicyEngine,
            RetentionRecord,
            RetentionStatus,
            RetentionStorageProtocol,
            get_retention_engine,
            reset_retention_engine,
        )

        RETENTION_POLICY_AVAILABLE = True
    except ImportError:
        RETENTION_POLICY_AVAILABLE = False
        RetentionStatus = object
        RetentionActionType = object
        RetentionRecord = object
        RetentionAction = object
        DisposalResult = object
        RetentionEnforcementReport = object
        RetentionStorageProtocol = object
        InMemoryRetentionStorage = object
        DisposalHandler = object
        DeleteHandler = object
        ArchiveHandler = object
        AnonymizeHandler = object
        PseudonymizeHandler = object
        RetentionPolicyEngine = object
        get_retention_engine = object
        reset_retention_engine = object

    # GDPR Article 17 Erasure Handler
    try:
        from .gdpr_erasure import (
            DataLocation,
            DataLocationType,
            ErasureCertificate,
            ErasureExemption,
            ErasureRequest,
            ErasureScope,
            ErasureStatus,
            ErasureSystemResult,
            GDPRErasureHandler,
            get_gdpr_erasure_handler,
            reset_gdpr_erasure_handler,
        )

        GDPR_ERASURE_AVAILABLE = True
    except ImportError:
        GDPR_ERASURE_AVAILABLE = False
        ErasureScope = object
        ErasureStatus = object
        ErasureExemption = object
        DataLocationType = object
        DataLocation = object
        ErasureSystemResult = object
        ErasureRequest = object
        ErasureCertificate = object
        GDPRErasureHandler = object
        get_gdpr_erasure_handler = object
        reset_gdpr_erasure_handler = object

    # CCPA (California Consumer Privacy Act) Handler
    try:
        from .ccpa_handler import (
            CONSTITUTIONAL_HASH as CCPA_CONSTITUTIONAL_HASH,
        )
        from .ccpa_handler import (
            CCPABusinessPurpose,
            CCPADataSource,
            CCPADenialReason,
            CCPAHandler,
            CCPAPersonalInfoCategory,
            CCPAPrivacyNotice,
            CCPARequest,
            CCPARequestStatus,
            CCPARequestType,
            ConsumerDataReport,
            ConsumerInfoRecord,
            OptOutConfirmation,
            get_ccpa_handler,
            reset_ccpa_handler,
        )

        CCPA_HANDLER_AVAILABLE = True
    except ImportError:
        CCPA_HANDLER_AVAILABLE = False
        CCPA_CONSTITUTIONAL_HASH = CONSTITUTIONAL_HASH
        CCPARequestType = object
        CCPARequestStatus = object
        CCPADenialReason = object
        CCPAPersonalInfoCategory = object
        CCPABusinessPurpose = object
        CCPADataSource = object
        ConsumerInfoRecord = object
        ConsumerDataReport = object
        OptOutConfirmation = object
        CCPAPrivacyNotice = object
        CCPARequest = object
        CCPAHandler = object
        get_ccpa_handler = object
        reset_ccpa_handler = object

    # URL/File Validation (SEC-003 SSRF, SEC-006 File Upload)
    try:
        from .url_file_validator import (
            CONSTITUTIONAL_HASH as URL_FILE_CONSTITUTIONAL_HASH,
        )
        from .url_file_validator import (
            FileSignature,
            FileType,
            FileValidationConfig,
            FileValidationError,
            FileValidator,
            SSRFProtectionConfig,
            URLValidationError,
            URLValidator,
            get_file_validator,
            get_url_validator,
            reset_file_validator,
            reset_url_validator,
            validate_file_content,
            validate_upload,
            validate_url,
        )

        URL_FILE_VALIDATOR_AVAILABLE = True
    except ImportError:
        URL_FILE_VALIDATOR_AVAILABLE = False
        URL_FILE_CONSTITUTIONAL_HASH = CONSTITUTIONAL_HASH
        SSRFProtectionConfig = object
        URLValidationError = object
        URLValidator = object
        FileType = object
        FileSignature = object
        FileValidationConfig = object
        FileValidationError = object
        FileValidator = object
        get_url_validator = object
        reset_url_validator = object
        get_file_validator = object
        reset_file_validator = object
        validate_url = object
        validate_upload = object
        validate_file_content = object

    # Secret Rotation Lifecycle (T004)
    try:
        from .secret_rotation import (
            CONSTITUTIONAL_HASH as SECRET_ROTATION_CONSTITUTIONAL_HASH,
        )
        from .secret_rotation import (
            InMemorySecretBackend,
            RotationPolicy,
            RotationRecord,
            RotationResult,
            RotationStatus,
            RotationTrigger,
            SecretBackend,
            SecretRotationManager,
            SecretType,
            SecretVersion,
            VaultSecretBackend,
            get_rotation_manager,
            reset_rotation_manager,
        )

        SECRET_ROTATION_AVAILABLE = True
    except ImportError:
        SECRET_ROTATION_AVAILABLE = False
        SECRET_ROTATION_CONSTITUTIONAL_HASH = CONSTITUTIONAL_HASH
        SecretRotationManager = object
        RotationPolicy = object
        RotationTrigger = object
        RotationStatus = object
        RotationResult = object
        SecretType = object
        SecretVersion = object
        RotationRecord = object
        SecretBackend = object
        InMemorySecretBackend = object
        VaultSecretBackend = object
        get_rotation_manager = object
        reset_rotation_manager = object

__all__ = [
    "CCPA_CONSTITUTIONAL_HASH",
    # CCPA Handler
    "CCPA_HANDLER_AVAILABLE",
    "CONSTITUTIONAL_HASH",
    # Data Classification System (§16.4)
    "DATA_CLASSIFICATION_AVAILABLE",
    "DATA_CLASSIFICATION_HASH",
    "DEFAULT_ORIGINS",
    "DEFAULT_RETENTION_POLICIES",
    "DUAL_KEY_CONSTITUTIONAL_HASH",
    "FIELD_NAME_INDICATORS",
    # GDPR Article 17 Erasure Handler
    "GDPR_ERASURE_AVAILABLE",
    "PII_COMPLIANCE_MAPPING",
    # PII Detection Engine
    "PII_DETECTOR_AVAILABLE",
    "PII_PATTERNS",
    "REDIS_AVAILABLE",
    # Retention Policy Engine
    "RETENTION_POLICY_AVAILABLE",
    # Secret Rotation Lifecycle (T004)
    "SECRET_ROTATION_AVAILABLE",
    "SECRET_ROTATION_CONSTITUTIONAL_HASH",
    "TENANT_CONFIG_AVAILABLE",
    "TENANT_ID_MAX_LENGTH",
    "TENANT_ID_MIN_LENGTH",
    "TENANT_ID_PATTERN",
    "TIER_REQUIREMENTS",
    "URL_FILE_CONSTITUTIONAL_HASH",
    # URL/File Validation (SEC-003, SEC-006)
    "URL_FILE_VALIDATOR_AVAILABLE",
    "AnonymizeHandler",
    "ArchiveHandler",
    "CCPABusinessPurpose",
    "CCPADataSource",
    "CCPADenialReason",
    "CCPAHandler",
    "CCPAPersonalInfoCategory",
    "CCPAPrivacyNotice",
    "CCPARequest",
    "CCPARequestStatus",
    "CCPARequestType",
    # CORS
    "CORSConfig",
    "CORSEnvironment",
    "ClassificationResult",
    "ComplianceFramework",
    "ConstitutionalHashMismatchError",
    "ConsumerDataReport",
    "ConsumerInfoRecord",
    "DataClassificationPolicy",
    "DataClassificationTier",
    "DataLocation",
    "DataLocationType",
    "DeleteHandler",
    "DisposalHandler",
    "DisposalMethod",
    "DisposalResult",
    "DualKeyConfig",
    # Dual-Key JWT (Zero-Downtime Rotation)
    "DualKeyJWTValidator",
    "ErasureCertificate",
    "ErasureExemption",
    "ErasureRequest",
    "ErasureScope",
    "ErasureStatus",
    "ErasureSystemResult",
    "FileSignature",
    "FileType",
    "FileValidationConfig",
    "FileValidationError",
    "FileValidator",
    "GDPRErasureHandler",
    "GDPRLawfulBasis",
    "InMemoryRetentionStorage",
    "InMemorySecretBackend",
    "JWTValidationResult",
    "KEMResult",
    "KeyMetadata",
    "OptOutConfirmation",
    "PIICategory",
    "PIIDetection",
    "PIIDetector",
    "PIIPattern",
    "PQCConfigurationError",
    "PQCDecapsulationError",
    "PQCEncapsulationError",
    "PQCError",
    "PQCKeyGenerationError",
    "PQCKeyPair",
    "PQCSignature",
    "PQCSignatureError",
    "PQCVerificationError",
    # Post-Quantum Cryptography
    "PQCWrapper",
    "PseudonymizeHandler",
    "RateLimitAlgorithm",
    "RateLimitConfig",
    # Rate Limiting
    "RateLimitMiddleware",
    "RateLimitResult",
    "RateLimitRule",
    "RateLimitScope",
    "RetentionAction",
    "RetentionActionType",
    "RetentionEnforcementReport",
    "RetentionPolicy",
    "RetentionPolicyEngine",
    "RetentionRecord",
    "RetentionStatus",
    "RetentionStorageProtocol",
    "RotationPolicy",
    "RotationRecord",
    "RotationResult",
    "RotationStatus",
    "RotationTrigger",
    "SSRFProtectionConfig",
    "SecretBackend",
    "SecretRotationManager",
    "SecretType",
    "SecretVersion",
    "SecurityHeadersConfig",
    # Security Headers
    "SecurityHeadersMiddleware",
    "SignatureSubstitutionError",
    "TenantContextConfig",
    # Tenant Context
    "TenantContextMiddleware",
    # Tenant-specific Rate Limiting
    "TenantQuota",
    "TenantQuotaProviderProtocol",
    "TenantRateLimitProvider",
    "TenantValidationError",
    "URLValidationError",
    "URLValidator",
    "UnsupportedAlgorithmError",
    "VaultSecretBackend",
    "add_security_headers",
    "classify_by_pii_categories",
    "classify_data",
    "create_rate_limit_middleware",
    "detect_environment",
    "detect_pii",
    "get_ccpa_handler",
    "get_compliance_frameworks",
    "get_cors_config",
    "get_current_tenant_id",
    "get_default_retention_policy",
    "get_dual_key_validator",
    "get_file_validator",
    "get_gdpr_erasure_handler",
    "get_optional_tenant_id",
    "get_pii_detector",
    "get_retention_engine",
    "get_rotation_manager",
    "get_strict_cors_config",
    "get_tenant_id",
    "get_tier_requirements",
    "get_url_validator",
    "redact_pii",
    "require_tenant_scope",
    "reset_ccpa_handler",
    "reset_file_validator",
    "reset_gdpr_erasure_handler",
    "reset_pii_detector",
    "reset_retention_engine",
    "reset_rotation_manager",
    "reset_url_validator",
    "safe_error_detail",
    "safe_error_message",
    # Expression Utils
    "safe_eval_expr",
    # Error Sanitization (production-safe error messages)
    "sanitize_error",
    "sanitize_tenant_id",
    "validate_file_content",
    "validate_origin",
    "validate_tenant_id",
    "validate_upload",
    "validate_url",
]
