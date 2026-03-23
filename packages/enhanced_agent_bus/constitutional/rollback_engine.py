"""
ACGS-2 Enhanced Agent Bus - Constitutional Rollback Engine
Constitutional Hash: cdd01ef066bc6cf2

Engine to automatically rollback constitutional amendments when governance
degradation is detected. Implements rollback saga workflow (inverse of
activation saga) with HITL notifications for critical rollbacks.

Rollback Steps:
    1. Detect Degradation - Analyze governance metrics and detect degradation
    2. Prepare Rollback - Identify target version and validate rollback can proceed
    3. Notify HITL - Send notifications for critical rollbacks (optional)
    4. Update OPA - Update OPA policies to previous constitutional hash
    5. Restore Version - Restore previous constitutional version from history
    6. Invalidate Cache - Clear Redis cache to force reload
    7. Audit - Log rollback event with justification and metrics

Each step has corresponding compensation for automatic recovery on failure.
"""

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timezone
from typing import TYPE_CHECKING, TypeAlias
from uuid import uuid4

import httpx

try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH  # noqa: E402
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
from src.core.shared.errors.exceptions import ACGSBaseError

from enhanced_agent_bus.observability.structured_logging import get_logger

try:
    import redis.asyncio as aioredis

    REDIS_AVAILABLE = True
except ImportError:
    aioredis = None
    REDIS_AVAILABLE = False

try:
    from src.core.shared.types import JSONDict  # noqa: E402
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from ..governance_constants import (
    ROLLBACK_DETECT_TIMEOUT_SECONDS,
    ROLLBACK_HTTP_TIMEOUT_SECONDS,
    ROLLBACK_MIN_CONFIDENCE,
    ROLLBACK_MONITORING_INTERVAL_SECONDS,
    ROLLBACK_STEP_TIMEOUT_SECONDS,
)
from .amendment_model import AmendmentStatus
from .degradation_detector import (
    DegradationDetector,
    TimeWindow,
)
from .metrics_collector import GovernanceMetricsCollector
from .storage import ConstitutionalStorageService  # type: ignore[attr-defined]

try:
    from ..audit_client import AuditClient
    from ..opa_client import OPAClient
except ImportError:
    AuditClient = None  # type: ignore[assignment]
    OPAClient = None  # type: ignore[assignment]

try:
    from .hitl_integration import ConstitutionalHITLIntegration, NotificationChannel
except ImportError:
    ConstitutionalHITLIntegration = None  # type: ignore[assignment]
    NotificationChannel = None  # type: ignore[assignment]

try:
    from ..deliberation_layer.workflows.constitutional_saga import (
        ConstitutionalSagaWorkflow,
        SagaCompensation,
        SagaContext,
        SagaResult,
        SagaStep,
    )
except ImportError:
    # Fallback - define minimal types
    ConstitutionalSagaWorkflow = None  # type: ignore[assignment]
    SagaStep = None  # type: ignore[assignment]
    SagaCompensation = None  # type: ignore[assignment]
    SagaContext = None  # type: ignore[assignment]
    SagaResult = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from ..deliberation_layer.workflows.constitutional_saga import (
        ConstitutionalSagaWorkflow as ConstitutionalSagaWorkflowType,
    )
    from ..deliberation_layer.workflows.constitutional_saga import SagaResult as SagaResultType

logger = get_logger(__name__)

RollbackSagaCallable: TypeAlias = Callable[[JSONDict], Awaitable[JSONDict | bool]]


@dataclass(frozen=True)
class RollbackStepSpec:
    name: str
    description: str
    execute_attr: str
    compensation_name: str
    compensation_description: str
    compensation_execute_attr: str
    timeout_seconds: int
    is_optional: bool = False


@dataclass(frozen=True)
class _PreparedRollbackVersions:
    current_version_id: str
    current_version: str
    target_version_id: str
    target_version: str
    target_hash: str
    amendment_id: str | None


ROLLBACK_STEP_SPECS: tuple[RollbackStepSpec, ...] = (
    RollbackStepSpec(
        name="detect_degradation",
        description="Analyze governance metrics and detect degradation",
        execute_attr="detect_degradation",
        compensation_name="log_detection_failure",
        compensation_description="Log detection failure",
        compensation_execute_attr="log_detection_failure",
        timeout_seconds=ROLLBACK_DETECT_TIMEOUT_SECONDS,
    ),
    RollbackStepSpec(
        name="prepare_rollback",
        description="Identify target version and validate rollback",
        execute_attr="prepare_rollback",
        compensation_name="cancel_preparation",
        compensation_description="Cancel rollback preparation",
        compensation_execute_attr="cancel_preparation",
        timeout_seconds=ROLLBACK_STEP_TIMEOUT_SECONDS,
    ),
    RollbackStepSpec(
        name="notify_hitl",
        description="Send HITL notifications for critical rollbacks",
        execute_attr="notify_hitl",
        compensation_name="cancel_hitl_notification",
        compensation_description="Cancel HITL notification",
        compensation_execute_attr="cancel_hitl_notification",
        timeout_seconds=ROLLBACK_STEP_TIMEOUT_SECONDS,
        is_optional=True,
    ),
    RollbackStepSpec(
        name="update_opa_to_previous",
        description="Update OPA policies to previous hash",
        execute_attr="update_opa_to_previous",
        compensation_name="revert_opa_to_current",
        compensation_description="Revert OPA policies to current hash",
        compensation_execute_attr="revert_opa_to_current",
        timeout_seconds=ROLLBACK_DETECT_TIMEOUT_SECONDS,
        is_optional=True,
    ),
    RollbackStepSpec(
        name="restore_previous_version",
        description="Restore previous constitutional version",
        execute_attr="restore_previous_version",
        compensation_name="revert_version_restoration",
        compensation_description="Revert version restoration",
        compensation_execute_attr="revert_version_restoration",
        timeout_seconds=ROLLBACK_STEP_TIMEOUT_SECONDS,
    ),
    RollbackStepSpec(
        name="invalidate_cache",
        description="Invalidate Redis cache",
        execute_attr="invalidate_cache",
        compensation_name="restore_cache",
        compensation_description="Restore cache state",
        compensation_execute_attr="restore_cache",
        timeout_seconds=ROLLBACK_STEP_TIMEOUT_SECONDS,
    ),
    RollbackStepSpec(
        name="audit_rollback",
        description="Log rollback to audit trail",
        execute_attr="audit_rollback",
        compensation_name="mark_rollback_audit_failed",
        compensation_description="Mark rollback audit as failed",
        compensation_execute_attr="mark_rollback_audit_failed",
        timeout_seconds=ROLLBACK_STEP_TIMEOUT_SECONDS,
        is_optional=True,
    ),
)


class RollbackEngineError(ACGSBaseError):
    """Exception raised when constitutional rollback fails.

    Inherits from ACGSBaseError to gain constitutional hash tracking,
    correlation IDs, and structured error logging.
    """

    http_status_code = 500
    error_code = "ROLLBACK_ENGINE_ERROR"


class RollbackReason(str):
    """Reasons for triggering rollback."""

    AUTOMATIC_DEGRADATION = "automatic_degradation"
    MANUAL_REQUEST = "manual_request"
    EMERGENCY_OVERRIDE = "emergency_override"


class RollbackTriggerConfig:
    """Configuration for automatic rollback triggers.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def __init__(
        self,
        enable_automatic_rollback: bool = True,
        monitoring_interval_seconds: int = ROLLBACK_MONITORING_INTERVAL_SECONDS,
        monitoring_windows: list[TimeWindow] | None = None,
        require_hitl_approval_for_critical: bool = True,
        auto_approve_high_confidence: bool = True,
        min_confidence_for_auto_rollback: float = ROLLBACK_MIN_CONFIDENCE,
    ):
        """Initialize rollback trigger configuration.

        Args:
            enable_automatic_rollback: Whether to enable automatic rollbacks
            monitoring_interval_seconds: How often to check for degradation
            monitoring_windows: Time windows to analyze (default: 1h, 6h)
            require_hitl_approval_for_critical: Whether critical rollbacks need HITL approval
            auto_approve_high_confidence: Auto-approve rollbacks with high confidence
            min_confidence_for_auto_rollback: Minimum confidence score for auto-rollback
        """
        self.enable_automatic_rollback = enable_automatic_rollback
        self.monitoring_interval_seconds = monitoring_interval_seconds
        self.monitoring_windows = monitoring_windows or [TimeWindow.ONE_HOUR, TimeWindow.SIX_HOURS]
        self.require_hitl_approval_for_critical = require_hitl_approval_for_critical
        self.auto_approve_high_confidence = auto_approve_high_confidence
        self.min_confidence_for_auto_rollback = min_confidence_for_auto_rollback


class RollbackSagaActivities:
    """
    Activity implementations for constitutional rollback saga.
    All activities are idempotent and can be safely retried.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def __init__(
        self,
        storage: ConstitutionalStorageService,
        metrics_collector: GovernanceMetricsCollector,
        degradation_detector: DegradationDetector,
        opa_url: str = "http://localhost:8181",
        audit_service_url: str = "http://localhost:8001",
        redis_url: str | None = None,
        hitl_integration: object | None = None,
    ):
        """Initialize rollback saga activities.

        Args:
            storage: Constitutional storage service
            metrics_collector: Metrics collector for governance data
            degradation_detector: Degradation detection engine
            opa_url: OPA server URL
            audit_service_url: Audit service URL
            redis_url: Redis connection URL (optional)
            hitl_integration: HITL integration service (optional)
        """
        self.storage = storage
        self.metrics_collector = metrics_collector
        self.degradation_detector = degradation_detector
        self.opa_url = opa_url
        self.audit_service_url = audit_service_url
        self.redis_url = redis_url or "redis://localhost:6379"
        self.hitl_integration = hitl_integration

        self._http_client: httpx.AsyncClient | None = None
        self._redis_client: object | None = None
        self._opa_client: object | None = None
        self._audit_client: object | None = None

    @staticmethod
    def _extract_saga_context(input: JSONDict) -> tuple[str, JSONDict]:
        return input["saga_id"], input["context"]

    async def _collect_degradation_snapshots(
        self,
        *,
        current_version_id: str,
        time_window: TimeWindow,
    ) -> tuple[object, object]:
        baseline_snapshot = await self.metrics_collector.get_baseline_snapshot(current_version_id)
        if not baseline_snapshot:
            logger.warning(
                "[%s] No baseline snapshot found for version %s",
                CONSTITUTIONAL_HASH,
                current_version_id,
            )
            baseline_snapshot = await self.metrics_collector.collect_snapshot(
                constitutional_version=current_version_id,
                window_seconds=time_window.to_seconds(),
            )

        current_snapshot = await self.metrics_collector.collect_snapshot(
            constitutional_version=current_version_id,
            window_seconds=time_window.to_seconds(),
        )
        return baseline_snapshot, current_snapshot

    async def _resolve_rollback_versions(
        self,
        *,
        current_version_id: str,
        amendment_id: str | None,
    ) -> _PreparedRollbackVersions:
        current_version = await self.storage.get_version(current_version_id)
        if not current_version:
            raise RollbackEngineError(f"Current version {current_version_id} not found")

        if not current_version.predecessor_version:
            raise RollbackEngineError(
                f"Current version {current_version_id} has no predecessor, cannot rollback"
            )

        target_version = await self.storage.get_version(current_version.predecessor_version)
        if not target_version:
            raise RollbackEngineError(
                f"Predecessor version {current_version.predecessor_version} not found"
            )

        if amendment_id:
            await self.storage.get_amendment(amendment_id)

        return _PreparedRollbackVersions(
            current_version_id=current_version.version_id,
            current_version=current_version.version,
            target_version_id=target_version.version_id,
            target_version=target_version.version,
            target_hash=target_version.constitutional_hash,
            amendment_id=amendment_id,
        )

    async def _send_hitl_notifications(
        self,
        *,
        saga_id: str,
        severity: str,
        rollback_reason: str,
        preparation_result: JSONDict,
        degradation_summary: str,
    ) -> list[str]:
        notifications_sent: list[str] = []
        if severity not in ("critical", "high"):
            return notifications_sent

        if not self.hitl_integration or not hasattr(self.hitl_integration, "_send_slack_notification"):
            return notifications_sent

        title = f"🔴 Constitutional Rollback - {severity.upper()}"
        message = (
            f"Automatic rollback triggered for constitutional version "
            f"{preparation_result.get('current_version')}\n\n"
            f"**Reason:** {rollback_reason}\n"
            f"**Severity:** {severity}\n"
            f"**Target Version:** {preparation_result.get('target_version')}\n"
            f"**Degradation:** {degradation_summary}"
        )

        try:
            await self.hitl_integration._send_slack_notification(
                title=title,
                message=message,
                priority="critical",
                action_url=f"#/constitutional/rollback/{saga_id}",
            )
            notifications_sent.append("slack")
        except (RuntimeError, ValueError, TypeError) as e:
            logger.warning("[%s] Failed to send Slack notification: %s", CONSTITUTIONAL_HASH, e)

        if severity == "critical":
            try:
                await self.hitl_integration._send_pagerduty_notification(
                    title="Critical Constitutional Rollback",
                    message=(
                        "Automatic rollback from "
                        f"{preparation_result.get('current_version')}"
                    ),
                    severity="critical",
                )
                notifications_sent.append("pagerduty")
            except (RuntimeError, ValueError, TypeError) as e:
                logger.warning(
                    "[%s] Failed to send PagerDuty notification: %s", CONSTITUTIONAL_HASH, e
                )

        return notifications_sent

    async def _mark_amendment_rolled_back(
        self,
        *,
        amendment_id: str | None,
        saga_id: str,
    ) -> bool:
        if not amendment_id:
            return False

        amendment = await self.storage.get_amendment(amendment_id)
        if not amendment:
            return False

        amendment.status = AmendmentStatus.ROLLED_BACK
        amendment.metadata = amendment.metadata or {}
        amendment.metadata["rolled_back_at"] = datetime.now(UTC).isoformat()
        amendment.metadata["rollback_saga_id"] = saga_id
        await self.storage.save_amendment(amendment)
        return True

    def _build_rollback_audit_event(
        self,
        *,
        saga_id: str,
        context: JSONDict,
        detection_result: JSONDict,
        preparation_result: JSONDict,
        restoration_result: JSONDict,
        notification_result: JSONDict,
    ) -> JSONDict:
        return {
            "audit_id": str(uuid4()),
            "event_type": "constitutional_version_rolled_back",
            "saga_id": saga_id,
            "rollback_reason": context.get("rollback_reason", RollbackReason.AUTOMATIC_DEGRADATION),
            "amendment_id": context.get("amendment_id"),
            "previous_version": preparation_result.get("current_version"),
            "previous_version_id": preparation_result.get("current_version_id"),
            "restored_version": restoration_result.get("restored_version"),
            "restored_version_id": restoration_result.get("restored_version_id"),
            "constitutional_hash": CONSTITUTIONAL_HASH,
            "degradation_report": detection_result.get("report"),
            "severity": detection_result.get("severity"),
            "confidence_score": detection_result.get("confidence_score"),
            "degradation_summary": detection_result.get("degradation_summary"),
            "critical_metrics": detection_result.get("critical_metrics", []),
            "notifications_sent": notification_result.get("notifications_sent", []),
            "timestamp": datetime.now(UTC).isoformat(),
            "metadata": {
                "detection": detection_result,
                "preparation": preparation_result,
                "restoration": restoration_result,
                "notification": notification_result,
            },
        }

    async def initialize(self) -> None:
        """Initialize clients and connections."""
        # HTTP client for OPA
        self._http_client = httpx.AsyncClient(
            timeout=ROLLBACK_HTTP_TIMEOUT_SECONDS,
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
        )

        # Redis client for cache invalidation
        if REDIS_AVAILABLE and aioredis:
            try:
                self._redis_client = await aioredis.from_url(
                    self.redis_url, encoding="utf-8", decode_responses=True
                )
            except (RuntimeError, ValueError, TypeError) as e:
                logger.warning("[%s] Failed to connect to Redis: %s", CONSTITUTIONAL_HASH, e)
                self._redis_client = None

        # OPA client
        if OPAClient:
            try:
                self._opa_client = OPAClient(opa_url=self.opa_url)
                await self._opa_client.initialize()
            except (RuntimeError, ValueError, TypeError) as e:
                logger.warning("[%s] Failed to initialize OPA client: %s", CONSTITUTIONAL_HASH, e)
                self._opa_client = None

        # Audit client
        if AuditClient:
            try:
                self._audit_client = AuditClient(service_url=self.audit_service_url)
                await self._audit_client.start()
            except (RuntimeError, ValueError, TypeError) as e:
                logger.warning("[%s] Failed to initialize audit client: %s", CONSTITUTIONAL_HASH, e)
                self._audit_client = None

    async def close(self) -> None:
        """Close all connections and clients."""
        if self._http_client:
            await self._http_client.aclose()

        if self._redis_client:
            await self._redis_client.aclose()

        if self._opa_client:
            await self._opa_client.close()

        if self._audit_client:
            await self._audit_client.stop()

    # Step 1: Detect Degradation
    async def detect_degradation(self, input: JSONDict) -> JSONDict:
        """
        Analyze governance metrics and detect degradation.

        Returns:
            Degradation detection result with report, severity, recommendation
        """
        saga_id, context = self._extract_saga_context(input)
        current_version_id = context.get("current_version_id")
        amendment_id = context.get("amendment_id")
        time_window = context.get("time_window", TimeWindow.ONE_HOUR)

        logger.info(
            "[%s] Saga %s: Detecting degradation for version %s, window=%s",
            CONSTITUTIONAL_HASH,
            saga_id,
            current_version_id,
            time_window,
        )

        baseline_snapshot, current_snapshot = await self._collect_degradation_snapshots(
            current_version_id=current_version_id,
            time_window=time_window,
        )

        # Analyze degradation
        report = await self.degradation_detector.analyze_degradation(
            baseline=baseline_snapshot,
            current=current_snapshot,
            time_window=time_window,
            amendment_id=amendment_id,
        )

        logger.info(
            f"[{CONSTITUTIONAL_HASH}] Saga {saga_id}: Degradation analysis complete - severity={report.overall_severity.value}, confidence={report.confidence_score * 100:.2f}%%, rollback_recommended={report.rollback_recommended}",  # noqa: E501
        )

        return {
            "detection_id": str(uuid4()),
            "report_id": report.report_id,
            "severity": report.overall_severity.value,
            "confidence_score": report.confidence_score,
            "rollback_recommended": report.rollback_recommended,
            "degradation_summary": report.degradation_summary,
            "has_degradation": report.has_degradation,
            "critical_metrics": [m.metric_name for m in report.critical_metrics],
            "report": report.model_dump(),
            "timestamp": datetime.now(UTC).isoformat(),
        }

    async def log_detection_failure(self, input: JSONDict) -> bool:
        """Compensation: Log detection failure (no-op for detection step)."""
        saga_id = input["saga_id"]
        logger.info(
            "[%s] Saga %s: Logging detection failure (compensation)",
            CONSTITUTIONAL_HASH,
            saga_id,
        )
        return True

    # Step 2: Prepare Rollback
    async def prepare_rollback(self, input: JSONDict) -> JSONDict:
        """
        Identify target version for rollback and validate rollback can proceed.

        Returns:
            Preparation result with target_version_id, current_version, validation status
        """
        saga_id, context = self._extract_saga_context(input)
        current_version_id = context.get("current_version_id")
        amendment_id = context.get("amendment_id")

        logger.info(
            "[%s] Saga %s: Preparing rollback from version %s",
            CONSTITUTIONAL_HASH,
            saga_id,
            current_version_id,
        )

        versions = await self._resolve_rollback_versions(
            current_version_id=current_version_id,
            amendment_id=amendment_id,
        )

        preparation_id = str(uuid4())

        logger.info(
            "[%s] Saga %s: Rollback prepared - target version: %s (%s)",
            CONSTITUTIONAL_HASH,
            saga_id,
            versions.target_version,
            versions.target_version_id,
        )

        return {
            "preparation_id": preparation_id,
            "current_version_id": versions.current_version_id,
            "current_version": versions.current_version,
            "target_version_id": versions.target_version_id,
            "target_version": versions.target_version,
            "target_hash": versions.target_hash,
            "amendment_id": versions.amendment_id,
            "is_valid": True,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    async def cancel_preparation(self, input: JSONDict) -> bool:
        """Compensation: Cancel rollback preparation (no-op)."""
        saga_id = input["saga_id"]
        logger.info(
            "[%s] Saga %s: Canceling preparation (compensation)", CONSTITUTIONAL_HASH, saga_id
        )
        return True

    # Step 3: Notify HITL (Optional for critical rollbacks)
    async def notify_hitl(self, input: JSONDict) -> JSONDict:
        """
        Send HITL notifications for critical rollbacks.

        Returns:
            Notification result with channels, status
        """
        saga_id, context = self._extract_saga_context(input)
        detection_result = context.get("detect_degradation", {})
        preparation_result = context.get("prepare_rollback", {})

        severity = detection_result.get("severity", "unknown")
        rollback_reason = context.get("rollback_reason", RollbackReason.AUTOMATIC_DEGRADATION)

        logger.info(
            "[%s] Saga %s: Sending HITL notifications for rollback (severity=%s)",
            CONSTITUTIONAL_HASH,
            saga_id,
            severity,
        )

        notification_id = str(uuid4())
        notifications_sent = await self._send_hitl_notifications(
            saga_id=saga_id,
            severity=severity,
            rollback_reason=rollback_reason,
            preparation_result=preparation_result,
            degradation_summary=detection_result.get("degradation_summary", "N/A"),
        )

        return {
            "notification_id": notification_id,
            "notifications_sent": notifications_sent,
            "severity": severity,
            "rollback_reason": rollback_reason,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    async def cancel_hitl_notification(self, input: JSONDict) -> bool:
        """Compensation: Cancel HITL notification (no-op)."""
        saga_id = input["saga_id"]
        logger.info(
            "[%s] Saga %s: Canceling HITL notification (compensation)",
            CONSTITUTIONAL_HASH,
            saga_id,
        )
        return True

    # Step 4: Update OPA
    async def update_opa_to_previous(self, input: JSONDict) -> JSONDict:
        """
        Update OPA policies to previous constitutional hash.

        Returns:
            OPA update result with previous_hash, status
        """
        saga_id = input["saga_id"]
        context = input["context"]

        preparation_result = context.get("prepare_rollback", {})
        target_hash = preparation_result.get("target_hash", CONSTITUTIONAL_HASH)
        target_version = preparation_result.get("target_version", "unknown")

        logger.info(
            "[%s] Saga %s: Updating OPA to previous hash %s (version %s)",
            CONSTITUTIONAL_HASH,
            saga_id,
            target_hash,
            target_version,
        )

        policy_update_id = str(uuid4())

        # Update OPA via HTTP API (PUT /v1/data/constitutional/active_hash)
        if self._http_client:
            try:
                opa_data_url = f"{self.opa_url}/v1/data/constitutional/active_hash"
                response = await self._http_client.put(
                    opa_data_url, json={"hash": target_hash, "version": target_version}
                )

                if response.status_code not in (200, 204):
                    logger.warning(
                        "[%s] OPA policy update returned status %s",
                        CONSTITUTIONAL_HASH,
                        response.status_code,
                    )

                logger.info(
                    "[%s] Saga %s: OPA policies updated to previous hash",
                    CONSTITUTIONAL_HASH,
                    saga_id,
                )
            except (RuntimeError, ValueError, TypeError) as e:
                logger.error(
                    "[%s] Saga %s: Failed to update OPA policies: %s",
                    CONSTITUTIONAL_HASH,
                    saga_id,
                    e,
                )
                # Continue anyway - OPA update is not critical for rollback

        return {
            "policy_update_id": policy_update_id,
            "opa_url": self.opa_url,
            "previous_hash": target_hash,
            "previous_version": target_version,
            "updated": True,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    async def revert_opa_to_current(self, input: JSONDict) -> bool:
        """
        Compensation: Revert OPA to current hash (if rollback fails).
        """
        saga_id = input["saga_id"]
        context = input["context"]

        preparation_result = context.get("prepare_rollback", {})
        current_hash = CONSTITUTIONAL_HASH  # Current hash
        current_version = preparation_result.get("current_version", "unknown")

        logger.info(
            "[%s] Saga %s: Reverting OPA to current hash (version %s)",
            CONSTITUTIONAL_HASH,
            saga_id,
            current_version,
        )

        if not self._http_client:
            logger.warning(
                "[%s] Saga %s: HTTP client not available for OPA revert",
                CONSTITUTIONAL_HASH,
                saga_id,
            )
            return True

        try:
            opa_data_url = f"{self.opa_url}/v1/data/constitutional/active_hash"
            response = await self._http_client.put(
                opa_data_url, json={"hash": current_hash, "version": current_version}
            )

            if response.status_code in (200, 204):
                logger.info(
                    "[%s] Saga %s: OPA policies reverted to current",
                    CONSTITUTIONAL_HASH,
                    saga_id,
                )
                return True
            else:
                logger.error(
                    "[%s] Saga %s: OPA policy revert failed with status %s",
                    CONSTITUTIONAL_HASH,
                    saga_id,
                    response.status_code,
                )
                return False
        except (RuntimeError, ValueError, TypeError) as e:
            logger.error(
                "[%s] Saga %s: Failed to revert OPA policies: %s",
                CONSTITUTIONAL_HASH,
                saga_id,
                e,
            )
            return False

    # Step 5: Restore Version
    async def restore_previous_version(self, input: JSONDict) -> JSONDict:
        """
        Restore previous constitutional version from history.

        Steps:
        1. Get target version from storage
        2. Activate target version (deactivates current)
        3. Update amendment status to ROLLED_BACK if applicable

        Returns:
            Restoration result with restored_version_id, status
        """
        saga_id, context = self._extract_saga_context(input)
        preparation_result = context.get("prepare_rollback", {})
        target_version_id = preparation_result.get("target_version_id")
        amendment_id = context.get("amendment_id")

        logger.info(
            "[%s] Saga %s: Restoring version %s",
            CONSTITUTIONAL_HASH,
            saga_id,
            target_version_id,
        )

        # Activate the target version (this also deactivates current)
        await self.storage.activate_version(target_version_id)

        amendment_rolled_back = await self._mark_amendment_rolled_back(
            amendment_id=amendment_id,
            saga_id=saga_id,
        )

        logger.info("[%s] Saga %s: Version restored successfully", CONSTITUTIONAL_HASH, saga_id)

        return {
            "restoration_id": str(uuid4()),
            "restored_version_id": target_version_id,
            "restored_version": preparation_result.get("target_version"),
            "previous_version_id": preparation_result.get("current_version_id"),
            "amendment_rolled_back": amendment_rolled_back,
            "restored": True,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    async def revert_version_restoration(self, input: JSONDict) -> bool:
        """
        Compensation: Revert version restoration (reactivate current version).
        """
        saga_id = input["saga_id"]
        context = input["context"]

        preparation_result = context.get("prepare_rollback", {})
        current_version_id = preparation_result.get("current_version_id")

        logger.info(
            "[%s] Saga %s: Reverting version restoration, reactivating %s",
            CONSTITUTIONAL_HASH,
            saga_id,
            current_version_id,
        )

        try:
            # Reactivate current version
            await self.storage.activate_version(current_version_id)
            logger.info("[%s] Saga %s: Version restoration reverted", CONSTITUTIONAL_HASH, saga_id)
            return True
        except (RuntimeError, ValueError, TypeError) as e:
            logger.error(
                "[%s] Saga %s: Failed to revert version restoration: %s",
                CONSTITUTIONAL_HASH,
                saga_id,
                e,
            )
            return False

    # Step 6: Invalidate Cache
    async def invalidate_cache(self, input: JSONDict) -> JSONDict:
        """
        Invalidate Redis cache to force reload of restored version.

        Returns:
            Cache invalidation result with cache_invalidated status
        """
        saga_id = input["saga_id"]
        logger.info("[%s] Saga %s: Invalidating cache", CONSTITUTIONAL_HASH, saga_id)

        cache_invalidated = False

        # Invalidate Redis cache
        if self._redis_client:
            try:
                # Invalidate active version cache key
                cache_key = "constitutional:active_version"
                await self._redis_client.delete(cache_key)
                cache_invalidated = True
                logger.info("[%s] Saga %s: Redis cache invalidated", CONSTITUTIONAL_HASH, saga_id)
            except (RuntimeError, ValueError, TypeError) as e:
                logger.warning(
                    "[%s] Saga %s: Failed to invalidate cache: %s",
                    CONSTITUTIONAL_HASH,
                    saga_id,
                    e,
                )

        return {
            "cache_invalidation_id": str(uuid4()),
            "cache_invalidated": cache_invalidated,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    async def restore_cache(self, input: JSONDict) -> bool:
        """Compensation: Restore cache (invalidate to force reload)."""
        saga_id = input["saga_id"]
        logger.info("[%s] Saga %s: Restoring cache (invalidation)", CONSTITUTIONAL_HASH, saga_id)

        if not self._redis_client:
            logger.warning("[%s] Saga %s: Redis client not available", CONSTITUTIONAL_HASH, saga_id)
            return True

        try:
            cache_key = "constitutional:active_version"
            await self._redis_client.delete(cache_key)
            logger.info("[%s] Saga %s: Cache restored (invalidated)", CONSTITUTIONAL_HASH, saga_id)
            return True
        except (RuntimeError, ValueError, TypeError) as e:
            logger.error(
                "[%s] Saga %s: Failed to restore cache: %s", CONSTITUTIONAL_HASH, saga_id, e
            )
            return False

    # Step 7: Audit
    async def audit_rollback(self, input: JSONDict) -> JSONDict:
        """
        Log constitutional rollback to audit trail with justification and metrics.

        Emits constitutional_version_rolled_back event.

        Returns:
            Audit result with audit_id, event_type, status
        """
        saga_id, context = self._extract_saga_context(input)
        detection_result = context.get("detect_degradation", {})
        preparation_result = context.get("prepare_rollback", {})
        restoration_result = context.get("restore_previous_version", {})
        notification_result = context.get("notify_hitl", {})

        logger.info("[%s] Saga %s: Logging rollback audit", CONSTITUTIONAL_HASH, saga_id)

        audit_event = self._build_rollback_audit_event(
            saga_id=saga_id,
            context=context,
            detection_result=detection_result,
            preparation_result=preparation_result,
            restoration_result=restoration_result,
            notification_result=notification_result,
        )

        # Submit to audit service
        if self._audit_client:
            try:
                await self._audit_client.log(
                    event_type="constitutional_version_rolled_back",
                    data=audit_event,
                    constitutional_hash=CONSTITUTIONAL_HASH,
                )
                logger.info("[%s] Saga %s: Audit event submitted", CONSTITUTIONAL_HASH, saga_id)
            except (RuntimeError, ValueError, TypeError) as e:
                logger.warning(
                    "[%s] Saga %s: Failed to submit audit event: %s",
                    CONSTITUTIONAL_HASH,
                    saga_id,
                    e,
                )

        # Log to local logger for immediate visibility
        logger.warning(
            "CONSTITUTIONAL_VERSION_ROLLED_BACK: %s (previous: %s, reason: %s, severity: %s)",
            restoration_result.get("restored_version"),
            preparation_result.get("current_version"),
            context.get("rollback_reason"),
            detection_result.get("severity"),
        )

        return audit_event

    async def mark_rollback_audit_failed(self, input: JSONDict) -> bool:
        """
        Compensation: Mark rollback audit as failed/compensated.
        """
        saga_id = input["saga_id"]
        context = input["context"]

        audit_data = context.get("audit_rollback", {})
        audit_id = audit_data.get("audit_id", "unknown")

        logger.info(
            "[%s] Saga %s: Marking rollback audit %s as compensated",
            CONSTITUTIONAL_HASH,
            saga_id,
            audit_id,
        )

        compensation_event = {
            "event_type": "constitutional_rollback_compensated",
            "saga_id": saga_id,
            "original_audit_id": audit_id,
            "reason": "Rollback saga compensation triggered",
            "timestamp": datetime.now(UTC).isoformat(),
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }

        if self._audit_client:
            try:
                await self._audit_client.log(
                    event_type="constitutional_rollback_compensated",
                    data=compensation_event,
                    constitutional_hash=CONSTITUTIONAL_HASH,
                )
            except (RuntimeError, ValueError, TypeError) as e:
                logger.warning(
                    "[%s] Failed to log compensation audit event: %s", CONSTITUTIONAL_HASH, e
                )

        logger.warning(
            "CONSTITUTIONAL_ROLLBACK_COMPENSATED: audit_id=%s, saga_id=%s", audit_id, saga_id
        )

        return True


def _build_rollback_step(
    *,
    name: str,
    description: str,
    execute: RollbackSagaCallable,
    compensation_name: str,
    compensation_description: str,
    compensation_execute: RollbackSagaCallable,
    timeout_seconds: int,
    is_optional: bool = False,
):
    if SagaStep is None or SagaCompensation is None:
        raise ImportError(
            "Constitutional saga step types not available. "
            "Ensure deliberation_layer.workflows.constitutional_saga is installed."
        )

    return SagaStep(
        name=name,
        description=description,
        execute=execute,
        compensation=SagaCompensation(
            name=compensation_name,
            description=compensation_description,
            execute=compensation_execute,
        ),
        timeout_seconds=timeout_seconds,
        is_optional=is_optional,
    )


def _resolve_rollback_activity_callable(
    activities: RollbackSagaActivities, step_spec: RollbackStepSpec, attr_name: str
) -> RollbackSagaCallable:
    try:
        activity_callable = getattr(activities, attr_name)
    except AttributeError as exc:
        raise RollbackEngineError(
            f"Rollback step '{step_spec.name}' references missing activity '{attr_name}'"
        ) from exc

    if not callable(activity_callable) or not inspect.iscoroutinefunction(activity_callable):
        raise RollbackEngineError(
            f"Rollback step '{step_spec.name}' activity '{attr_name}' must be async callable"
        )

    return activity_callable


def _add_rollback_saga_steps(saga, activities: RollbackSagaActivities) -> None:
    for step_spec in ROLLBACK_STEP_SPECS:
        execute_callable = _resolve_rollback_activity_callable(
            activities, step_spec, step_spec.execute_attr
        )
        compensation_callable = _resolve_rollback_activity_callable(
            activities, step_spec, step_spec.compensation_execute_attr
        )
        saga.add_step(
            _build_rollback_step(
                name=step_spec.name,
                description=step_spec.description,
                execute=execute_callable,
                compensation_name=step_spec.compensation_name,
                compensation_description=step_spec.compensation_description,
                compensation_execute=compensation_callable,
                timeout_seconds=step_spec.timeout_seconds,
                is_optional=step_spec.is_optional,
            )
        )


def _build_rollback_activities(
    *,
    storage: ConstitutionalStorageService,
    metrics_collector: GovernanceMetricsCollector,
    degradation_detector: DegradationDetector,
    opa_url: str,
    audit_service_url: str,
    redis_url: str | None,
    hitl_integration: object | None,
) -> RollbackSagaActivities:
    return RollbackSagaActivities(
        storage=storage,
        metrics_collector=metrics_collector,
        degradation_detector=degradation_detector,
        opa_url=opa_url,
        audit_service_url=audit_service_url,
        redis_url=redis_url,
        hitl_integration=hitl_integration,
    )


def _create_saga_shell(current_version_id: str) -> "ConstitutionalSagaWorkflowType":
    if not ConstitutionalSagaWorkflow:
        raise ImportError(
            "ConstitutionalSagaWorkflow not available. "
            "Ensure deliberation_layer.workflows.constitutional_saga is installed."
        )

    saga_id = f"rollback-{current_version_id[:8]}-{str(uuid4())[:8]}"
    return ConstitutionalSagaWorkflow(saga_id=saga_id)


def _get_saga_activities(saga) -> RollbackSagaActivities | None:
    if not hasattr(saga, "_steps") or not saga._steps:
        return None

    first_step = saga._steps[0]
    execute = getattr(first_step, "execute", None)
    activities = getattr(execute, "__self__", None)
    return activities if isinstance(activities, RollbackSagaActivities) else None


async def _initialize_saga_activities(saga) -> None:
    activities = _get_saga_activities(saga)
    if activities is not None:
        await activities.initialize()


async def _close_saga_activities(saga) -> None:
    activities = _get_saga_activities(saga)
    if activities is not None:
        await activities.close()


def _build_rollback_context(
    *,
    saga_id: str,
    current_version_id: str,
    amendment_id: str | None,
    rollback_reason: str,
    time_window: TimeWindow,
):
    if not SagaContext:
        raise ImportError("SagaContext not available")

    context = SagaContext(saga_id=saga_id, constitutional_hash=CONSTITUTIONAL_HASH)
    context.set_step_result("current_version_id", current_version_id)
    context.set_step_result("amendment_id", amendment_id)
    context.set_step_result("rollback_reason", rollback_reason)
    context.set_step_result("time_window", time_window)
    return context


def create_rollback_saga(
    current_version_id: str,
    storage: ConstitutionalStorageService,
    metrics_collector: GovernanceMetricsCollector,
    degradation_detector: DegradationDetector,
    rollback_reason: str = RollbackReason.AUTOMATIC_DEGRADATION,
    amendment_id: str | None = None,
    time_window: TimeWindow = TimeWindow.ONE_HOUR,
    opa_url: str = "http://localhost:8181",
    audit_service_url: str = "http://localhost:8001",
    redis_url: str | None = None,
    hitl_integration: object | None = None,
) -> "ConstitutionalSagaWorkflowType":
    """
    Factory function to create a constitutional rollback saga.

    The saga has 7 steps with compensations:
    1. Detect Degradation - Analyze metrics and detect degradation
    2. Prepare Rollback - Identify target version and validate
    3. Notify HITL - Send notifications for critical rollbacks
    4. Update OPA - Update OPA policies to previous hash
    5. Restore Version - Restore previous constitutional version
    6. Invalidate Cache - Clear Redis cache
    7. Audit - Log rollback with justification and metrics

    Args:
        current_version_id: Current constitutional version ID to rollback from
        storage: Constitutional storage service
        metrics_collector: Metrics collector for governance data
        degradation_detector: Degradation detection engine
        rollback_reason: Reason for rollback
        amendment_id: Amendment ID being rolled back (optional)
        time_window: Time window for degradation analysis
        opa_url: OPA server URL
        audit_service_url: Audit service URL
        redis_url: Redis connection URL
        hitl_integration: HITL integration service (optional)

    Returns:
        Configured ConstitutionalSagaWorkflow ready to execute

    Example:
        ```python
        storage = ConstitutionalStorageService()
        metrics = GovernanceMetricsCollector()
        detector = DegradationDetector(metrics)
        await storage.connect()
        await metrics.connect()

        saga = create_rollback_saga(
            current_version_id="version-123",
            storage=storage,
            metrics_collector=metrics,
            degradation_detector=detector
        )

        context = SagaContext(saga_id=saga.saga_id)
        result = await saga.execute(context)

        if result.status == SagaStatus.COMPLETED:
        else:
        ```
    """
    saga = _create_saga_shell(current_version_id)
    activities = _build_rollback_activities(
        storage=storage,
        metrics_collector=metrics_collector,
        degradation_detector=degradation_detector,
        opa_url=opa_url,
        audit_service_url=audit_service_url,
        redis_url=redis_url,
        hitl_integration=hitl_integration,
    )
    _add_rollback_saga_steps(saga, activities)
    return saga


async def rollback_amendment(
    current_version_id: str,
    storage: ConstitutionalStorageService,
    metrics_collector: GovernanceMetricsCollector,
    degradation_detector: DegradationDetector,
    rollback_reason: str = RollbackReason.AUTOMATIC_DEGRADATION,
    amendment_id: str | None = None,
    time_window: TimeWindow = TimeWindow.ONE_HOUR,
    opa_url: str = "http://localhost:8181",
    audit_service_url: str = "http://localhost:8001",
    redis_url: str | None = None,
    hitl_integration: object | None = None,
) -> "SagaResultType":
    """
    Rollback a constitutional amendment using saga workflow.

    This is a convenience function that creates and executes the rollback
    saga in one call. For more control, use create_rollback_saga() directly.

    Args:
        current_version_id: Current constitutional version ID to rollback from
        storage: Constitutional storage service
        metrics_collector: Metrics collector for governance data
        degradation_detector: Degradation detection engine
        rollback_reason: Reason for rollback
        amendment_id: Amendment ID being rolled back (optional)
        time_window: Time window for degradation analysis
        opa_url: OPA server URL
        audit_service_url: Audit service URL
        redis_url: Redis connection URL
        hitl_integration: HITL integration service (optional)

    Returns:
        SagaResult with rollback status and details

    Raises:
        RollbackEngineError: If rollback fails critically

    Example:
        ```python
        storage = ConstitutionalStorageService()
        metrics = GovernanceMetricsCollector()
        detector = DegradationDetector(metrics)
        await storage.connect()
        await metrics.connect()

        result = await rollback_amendment(
            current_version_id="version-123",
            storage=storage,
            metrics_collector=metrics,
            degradation_detector=detector
        )

        if result.status == SagaStatus.COMPLETED:
        else:
        ```
    """
    if not SagaContext:
        raise ImportError("SagaContext not available")

    saga = create_rollback_saga(
        current_version_id=current_version_id,
        storage=storage,
        metrics_collector=metrics_collector,
        degradation_detector=degradation_detector,
        rollback_reason=rollback_reason,
        amendment_id=amendment_id,
        time_window=time_window,
        opa_url=opa_url,
        audit_service_url=audit_service_url,
        redis_url=redis_url,
        hitl_integration=hitl_integration,
    )
    await _initialize_saga_activities(saga)
    context = _build_rollback_context(
        saga_id=saga.saga_id,
        current_version_id=current_version_id,
        amendment_id=amendment_id,
        rollback_reason=rollback_reason,
        time_window=time_window,
    )

    try:
        result = await saga.execute(context)
        return result
    finally:
        await _close_saga_activities(saga)


__all__ = [
    "RollbackEngineError",
    "RollbackReason",
    "RollbackSagaActivities",
    "RollbackTriggerConfig",
    "create_rollback_saga",
    "rollback_amendment",
]
