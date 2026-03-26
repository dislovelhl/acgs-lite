"""
ACGS-2 Enhanced Agent Bus - Constitutional Evolution Module
Constitutional Hash: 608508a9bd224290

Self-evolving constitutional systems with version control, amendment workflows,
and automated rollback capabilities.
"""

import sys

_MODULE = sys.modules[__name__]
sys.modules.setdefault("enhanced_agent_bus.constitutional", _MODULE)
sys.modules.setdefault("packages.enhanced_agent_bus.constitutional", _MODULE)

from .activation_saga import (
    ActivationSagaActivities,
    ActivationSagaError,
    activate_amendment,
    create_activation_saga,
)
from .amendment_model import (
    AmendmentProposal,
    AmendmentStatus,
)
from .degradation_detector import (
    DegradationDetector,
    DegradationReport,
    DegradationSeverity,
    DegradationThresholds,
    MetricDegradationAnalysis,
    SignificanceLevel,
    StatisticalTest,
    TimeWindow,
)
from .diff_engine import (
    ConstitutionalDiffEngine,
    DiffChange,
    PrincipleChange,
    SemanticDiff,
)
from .hitl_integration import (
    ApprovalChainConfig,
    ApprovalPriority,
    ConstitutionalHITLIntegration,
    HITLApprovalRequest,
    NotificationChannel,
)
from .metrics_collector import (
    GovernanceMetricsCollector,
    GovernanceMetricsSnapshot,
    MetricsComparison,
)
from .opa_updater import (
    OPAPolicyUpdater,
    PolicyUpdateRequest,
    PolicyUpdateResult,
    PolicyUpdateStatus,
    PolicyValidationResult,
)
from .proposal_engine import (
    AmendmentProposalEngine,
    ProposalRequest,
    ProposalResponse,
    ProposalValidationError,
)
from .review_api import (
    AmendmentDetailResponse,
    AmendmentListResponse,
    ApprovalRequest,
    ApprovalResponse,
    RejectionRequest,
    router,
)
from .rollback_engine import (
    RollbackEngineError,
    RollbackReason,
    RollbackSagaActivities,
    RollbackTriggerConfig,
    create_rollback_saga,
    rollback_amendment,
)
from .storage import (  # type: ignore[attr-defined]
    ConstitutionalStorageService,
)
from .version_history import (
    VersionHistoryQuery,
    VersionHistoryService,
    VersionHistorySummary,
)
from .version_model import (
    ConstitutionalStatus,
    ConstitutionalVersion,
)

__all__ = [
    "ActivationSagaActivities",
    "ActivationSagaError",
    "AmendmentDetailResponse",
    "AmendmentListResponse",
    "AmendmentProposal",
    "AmendmentProposalEngine",
    "AmendmentStatus",
    "ApprovalChainConfig",
    "ApprovalPriority",
    "ApprovalRequest",
    "ApprovalResponse",
    "ConstitutionalDiffEngine",
    "ConstitutionalHITLIntegration",
    "ConstitutionalStatus",
    "ConstitutionalStorageService",
    "ConstitutionalVersion",
    "DegradationDetector",
    "DegradationReport",
    "DegradationSeverity",
    "DegradationThresholds",
    "DiffChange",
    "GovernanceMetricsCollector",
    "GovernanceMetricsSnapshot",
    "HITLApprovalRequest",
    "MetricDegradationAnalysis",
    "MetricsComparison",
    "NotificationChannel",
    "OPAPolicyUpdater",
    "PolicyUpdateRequest",
    "PolicyUpdateResult",
    "PolicyUpdateStatus",
    "PolicyValidationResult",
    "PrincipleChange",
    "ProposalRequest",
    "ProposalResponse",
    "ProposalValidationError",
    "RejectionRequest",
    "RollbackEngineError",
    "RollbackReason",
    "RollbackSagaActivities",
    "RollbackTriggerConfig",
    "SemanticDiff",
    "SignificanceLevel",
    "StatisticalTest",
    "TimeWindow",
    "VersionHistoryQuery",
    "VersionHistoryService",
    "VersionHistorySummary",
    "activate_amendment",
    "create_activation_saga",
    "create_rollback_saga",
    "rollback_amendment",
    "router",
]
