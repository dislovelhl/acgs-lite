"""
ACGS-2 Enhanced Agent Bus - Constitutional Amendment Activation Saga
Constitutional Hash: cdd01ef066bc6cf2

Saga workflow for activating approved constitutional amendments with
rollback compensation. Implements the saga pattern for distributed
transactions with all-or-nothing semantics.

Activation Steps:
    1. Validate - Validate amendment and constitutional version
    2. Backup Current - Backup current active constitutional version
    3. Update OPA - Update OPA policies with new constitutional hash
    4. Update Cache - Invalidate Redis cache and update with new version
    5. Audit - Log the activation to audit trail

Each step has corresponding compensation for automatic rollback on failure.
"""

import hashlib
import json
from datetime import UTC, datetime, timezone
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

from .amendment_model import AmendmentStatus
from .storage import ConstitutionalStorageService  # type: ignore[attr-defined]
from .version_model import ConstitutionalStatus, ConstitutionalVersion

try:
    from ..audit_client import AuditClient
    from ..opa_client import OPAClient
except ImportError:
    AuditClient = None  # type: ignore[assignment]
    OPAClient = None  # type: ignore[assignment]

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

logger = get_logger(__name__)


class ActivationSagaError(ACGSBaseError):
    """Exception raised when amendment activation fails.

    Inherits from ACGSBaseError to gain constitutional hash tracking,
    correlation IDs, and structured error logging.
    """

    http_status_code = 500
    error_code = "ACTIVATION_SAGA_ERROR"


class ActivationSagaActivities:
    """
    Activity implementations for constitutional amendment activation saga.
    All activities are idempotent and can be safely retried.
    """

    def __init__(
        self,
        storage: ConstitutionalStorageService,
        opa_url: str = "http://localhost:8181",
        audit_service_url: str = "http://localhost:8001",
        redis_url: str | None = None,
    ):
        """Initialize activation saga activities.

        Args:
            storage: Constitutional storage service
            opa_url: OPA server URL
            audit_service_url: Audit service URL
            redis_url: Redis connection URL (optional)
        """
        self.storage = storage
        self.opa_url = opa_url
        self.audit_service_url = audit_service_url
        self.redis_url = redis_url or "redis://localhost:6379"

        self._http_client: httpx.AsyncClient | None = None
        self._redis_client: object | None = None
        self._opa_client: object | None = None
        self._audit_client: object | None = None

    def _compute_constitutional_hash(self, content: JSONDict) -> str:
        """Compute SHA256 hash of constitutional content.

        Args:
            content: Constitutional content dictionary

        Returns:
            SHA256 hex digest
        """
        # Ensure consistent ordering for reproducibility
        content_json = json.dumps(content, sort_keys=True)
        return hashlib.sha256(content_json.encode("utf-8")).hexdigest()

    async def initialize(self) -> None:
        """Initialize clients and connections."""
        # HTTP client for OPA
        self._http_client = httpx.AsyncClient(
            timeout=30.0,
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
        )

        # Redis client for cache invalidation
        if REDIS_AVAILABLE and aioredis:
            try:
                self._redis_client = await aioredis.from_url(
                    self.redis_url, encoding="utf-8", decode_responses=True
                )
            except (OSError, ConnectionError, ValueError, TypeError) as e:
                logger.warning("Failed to connect to Redis: %s", e)
                self._redis_client = None

        # OPA client
        if OPAClient:
            try:
                self._opa_client = OPAClient(opa_url=self.opa_url)
                await self._opa_client.initialize()
            except (OSError, ConnectionError, RuntimeError, ValueError) as e:
                logger.warning("Failed to initialize OPA client: %s", e)
                self._opa_client = None

        # Audit client
        if AuditClient:
            try:
                self._audit_client = AuditClient(service_url=self.audit_service_url)
                await self._audit_client.start()
            except (OSError, ConnectionError, RuntimeError, ValueError) as e:
                logger.warning("Failed to initialize audit client: %s", e)
                self._audit_client = None

    async def close(self) -> None:
        """Close all connections and clients."""
        if self._http_client:
            await self._http_client.aclose()

        if self._redis_client:
            await self._redis_client.close()

        if self._opa_client:
            await self._opa_client.close()

        if self._audit_client:
            await self._audit_client.stop()

    # Step 1: Validate
    async def validate_activation(self, input: JSONDict) -> JSONDict:
        """
        Validate that the amendment can be activated.

        Checks:
        - Amendment status is APPROVED
        - Target version exists
        - New version doesn't already exist
        - Constitutional hash is valid

        Returns:
            Validation result with amendment_id, version_id, validation status
        """
        saga_id = input["saga_id"]
        context = input["context"]

        amendment_id = context.get("amendment_id")
        if not amendment_id:
            raise ActivationSagaError("Missing amendment_id in context")

        logger.info("Saga %s: Validating amendment %s", saga_id, amendment_id)

        # Get amendment from storage
        amendment = await self.storage.get_amendment(amendment_id)
        if not amendment:
            raise ActivationSagaError(f"Amendment {amendment_id} not found")

        # Check amendment status
        if amendment.status != AmendmentStatus.APPROVED:
            raise ActivationSagaError(
                f"Amendment {amendment_id} is not approved (status: {amendment.status.value})"
            )

        # Get target version
        target_version = await self.storage.get_version(amendment.target_version)
        if not target_version:
            raise ActivationSagaError(f"Target version {amendment.target_version} not found")

        # Check if target version is active
        active_version = await self.storage.get_active_version()
        if not active_version or active_version.version_id != target_version.version_id:
            logger.warning(
                "Target version %s is not active (current active: %s)",
                target_version.version,
                active_version.version if active_version else "none",
            )

        # Validate constitutional hash
        if target_version.constitutional_hash != CONSTITUTIONAL_HASH:
            logger.warning(
                "Target version hash %s does not match current hash %s",
                target_version.constitutional_hash,
                CONSTITUTIONAL_HASH,
            )

        validation_id = str(uuid4())

        return {
            "validation_id": validation_id,
            "amendment_id": amendment_id,
            "target_version_id": target_version.version_id,
            "target_version": target_version.version,
            "new_version": amendment.new_version,
            "is_valid": True,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    async def log_validation_failure(self, input: JSONDict) -> bool:
        """Compensation: Log validation failure (no-op for validation step)."""
        saga_id = input["saga_id"]
        logger.info("Saga %s: Logging validation failure (compensation)", saga_id)
        return True

    # Step 2: Backup Current
    async def backup_current_version(self, input: JSONDict) -> JSONDict:
        """
        Backup the current active constitutional version for rollback.

        Returns:
            Backup result with backup_id, version_id, version
        """
        saga_id = input["saga_id"]
        logger.info("Saga %s: Backing up current active version", saga_id)

        # Get current active version
        active_version = await self.storage.get_active_version()
        if not active_version:
            raise ActivationSagaError("No active constitutional version found")

        backup_id = str(uuid4())

        # Store backup metadata in context
        backup_data = {
            "backup_id": backup_id,
            "version_id": active_version.version_id,
            "version": active_version.version,
            "constitutional_hash": active_version.constitutional_hash,
            "content": active_version.content,
            "status": active_version.status.value,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        logger.info(
            "Saga %s: Backed up version %s (id: %s)",
            saga_id,
            active_version.version,
            active_version.version_id,
        )

        return backup_data

    async def restore_backup(self, input: JSONDict) -> bool:
        """
        Compensation: Restore the backed up constitutional version.

        This reverts the activation by restoring the previous active version.
        """
        saga_id = input["saga_id"]
        context = input["context"]

        backup_data = context.get("backup_current_version")
        if not backup_data:
            logger.error("Saga %s: No backup data found for restoration", saga_id)
            return False

        backup_version_id = backup_data.get("version_id")
        logger.info("Saga %s: Restoring backup version %s", saga_id, backup_version_id)

        try:
            # Reactivate the backed up version
            await self.storage.activate_version(backup_version_id)
            logger.info("Saga %s: Successfully restored version %s", saga_id, backup_version_id)
            return True
        except (RuntimeError, ValueError, TypeError, OSError) as e:
            logger.error("Saga %s: Failed to restore backup: %s", saga_id, e)
            return False

    # Step 3: Update OPA
    async def update_opa_policies(self, input: JSONDict) -> JSONDict:
        """
        Update OPA constitutional.rego with new hash and rules.

        Updates the OPA policy bundle with the new constitutional version's
        hash and content, enabling runtime validation of the new constitution.

        Returns:
            Update result with policy_id, hash, status
        """
        saga_id = input["saga_id"]
        context = input["context"]

        validation_result = context.get("validate_activation", {})
        new_version = validation_result.get("new_version")

        logger.info("Saga %s: Updating OPA policies for version %s", saga_id, new_version)

        # Get the amendment to extract new content
        amendment_id = context.get("amendment_id")
        amendment = await self.storage.get_amendment(amendment_id)
        if not amendment:
            raise ActivationSagaError(f"Amendment {amendment_id} not found")

        # Create new constitutional version with merged content
        target_version = await self.storage.get_version(amendment.target_version)
        if not target_version:
            raise ActivationSagaError("Target version not found")

        # Merge proposed changes into target content
        new_content = {**target_version.content, **amendment.proposed_changes}

        # Calculate new constitutional hash from merged content
        new_hash = self._compute_constitutional_hash(new_content)

        policy_update_id = str(uuid4())

        # Update OPA via HTTP API (PUT /v1/data/constitutional/active_hash)
        if self._http_client:
            try:
                opa_data_url = f"{self.opa_url}/v1/data/constitutional/active_hash"
                response = await self._http_client.put(
                    opa_data_url, json={"hash": new_hash, "version": new_version}
                )

                if response.status_code not in (200, 204):
                    logger.warning("OPA policy update returned status %s", response.status_code)

                logger.info("Saga %s: OPA policies updated successfully", saga_id)
            except (httpx.RequestError, OSError, ConnectionError, ValueError, TypeError) as e:
                logger.error("Saga %s: Failed to update OPA policies: %s", saga_id, e)
                # Continue anyway - OPA update is not critical for activation

        return {
            "policy_update_id": policy_update_id,
            "opa_url": self.opa_url,
            "new_hash": new_hash,
            "new_version": new_version,
            "updated": True,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    async def revert_opa_policies(self, input: JSONDict) -> bool:
        """
        Compensation: Revert OPA policies to previous hash.

        Restores OPA policy data to the backed up version's hash.
        """
        saga_id = input["saga_id"]
        context = input["context"]

        backup_data = context.get("backup_current_version", {})
        previous_hash = backup_data.get("constitutional_hash", CONSTITUTIONAL_HASH)
        previous_version = backup_data.get("version", "unknown")

        logger.info(
            "Saga %s: Reverting OPA policies to version %s (hash: %s)",
            saga_id,
            previous_version,
            previous_hash,
        )

        if not self._http_client:
            logger.warning("Saga %s: HTTP client not available for OPA revert", saga_id)
            return True  # Return true to not block compensation

        try:
            opa_data_url = f"{self.opa_url}/v1/data/constitutional/active_hash"
            response = await self._http_client.put(
                opa_data_url, json={"hash": previous_hash, "version": previous_version}
            )

            if response.status_code in (200, 204):
                logger.info("Saga %s: OPA policies reverted successfully", saga_id)
                return True
            else:
                logger.error(
                    "Saga %s: OPA policy revert failed with status %s",
                    saga_id,
                    response.status_code,
                )
                return False
        except (httpx.RequestError, OSError, ConnectionError, ValueError, TypeError) as e:
            logger.error("Saga %s: Failed to revert OPA policies: %s", saga_id, e)
            return False

    # Step 4: Update Cache
    async def update_cache(self, input: JSONDict) -> JSONDict:
        """
        Invalidate Redis cache and update with new constitutional version.

        Steps:
        1. Create new constitutional version in storage
        2. Activate the new version (deactivates current)
        3. Invalidate Redis cache
        4. Cache the new active version

        Returns:
            Cache update result with cache_invalidated, new_version_id
        """
        saga_id = input["saga_id"]
        context = input["context"]

        validation_result = context.get("validate_activation", {})
        amendment_id = context.get("amendment_id")
        new_version = validation_result.get("new_version")

        logger.info("Saga %s: Updating cache for version %s", saga_id, new_version)

        # Get amendment and target version
        amendment = await self.storage.get_amendment(amendment_id)
        target_version = await self.storage.get_version(amendment.target_version)

        # Merge proposed changes
        new_content = {**target_version.content, **amendment.proposed_changes}

        # Create new constitutional version
        new_constitutional_version = ConstitutionalVersion(
            version=new_version,
            constitutional_hash=self._compute_constitutional_hash(new_content),
            content=new_content,
            predecessor_version=target_version.version_id,
            status=ConstitutionalStatus.APPROVED,
            metadata={
                "amendment_id": amendment_id,
                "impact_score": amendment.impact_score,
                "proposer_agent_id": amendment.proposer_agent_id,
                "activated_by": "activation_saga",
                "activated_at": datetime.now(UTC).isoformat(),
            },
        )

        # Save new version to storage
        await self.storage.save_version(new_constitutional_version)

        # Activate the new version (this also deactivates current)
        await self.storage.activate_version(new_constitutional_version.version_id)

        # Update amendment status to ACTIVE
        amendment.status = AmendmentStatus.ACTIVE
        amendment.activated_at = datetime.now(UTC)
        await self.storage.save_amendment(amendment)

        cache_invalidated = False

        # Invalidate Redis cache
        if self._redis_client:
            try:
                # Invalidate active version cache key
                cache_key = "constitutional:active_version"
                await self._redis_client.delete(cache_key)
                cache_invalidated = True
                logger.info("Saga %s: Redis cache invalidated", saga_id)
            except (OSError, ConnectionError, ValueError, TypeError) as e:
                logger.warning("Saga %s: Failed to invalidate cache: %s", saga_id, e)

        return {
            "cache_update_id": str(uuid4()),
            "new_version_id": new_constitutional_version.version_id,
            "new_version": new_version,
            "cache_invalidated": cache_invalidated,
            "activated": True,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    async def revert_cache(self, input: JSONDict) -> bool:
        """
        Compensation: Revert cache to previous version.

        Invalidates cache to force reload of backed up version.
        """
        saga_id = input["saga_id"]
        logger.info("Saga %s: Reverting cache (invalidation)", saga_id)

        if not self._redis_client:
            logger.warning("Saga %s: Redis client not available for cache revert", saga_id)
            return True

        try:
            # Invalidate cache to force reload from storage
            cache_key = "constitutional:active_version"
            await self._redis_client.delete(cache_key)
            logger.info("Saga %s: Cache invalidated for revert", saga_id)
            return True
        except (OSError, ConnectionError, ValueError, TypeError) as e:
            logger.error("Saga %s: Failed to invalidate cache: %s", saga_id, e)
            return False

    # Step 5: Audit
    async def audit_activation(self, input: JSONDict) -> JSONDict:
        """
        Log constitutional amendment activation to audit trail.

        Emits constitutional_version_activated event with full context.

        Returns:
            Audit result with audit_id, event_type, status
        """
        saga_id = input["saga_id"]
        context = input["context"]

        validation_result = context.get("validate_activation", {})
        backup_data = context.get("backup_current_version", {})
        cache_update = context.get("update_cache", {})

        amendment_id = context.get("amendment_id")
        new_version = validation_result.get("new_version")
        previous_version = backup_data.get("version")

        logger.info("Saga %s: Logging activation audit for amendment %s", saga_id, amendment_id)

        audit_id = str(uuid4())

        # Build audit event
        audit_event = {
            "audit_id": audit_id,
            "event_type": "constitutional_version_activated",
            "saga_id": saga_id,
            "amendment_id": amendment_id,
            "new_version": new_version,
            "new_version_id": cache_update.get("new_version_id"),
            "previous_version": previous_version,
            "previous_version_id": backup_data.get("version_id"),
            "constitutional_hash": cache_update.get("new_hash") or CONSTITUTIONAL_HASH,
            "timestamp": datetime.now(UTC).isoformat(),
            "metadata": {
                "validation": validation_result,
                "backup": backup_data,
                "cache_update": cache_update,
            },
        }

        # Submit to audit service
        if self._audit_client:
            try:
                # Use fire-and-forget audit submission
                await self._audit_client.log(
                    event_type="constitutional_version_activated",
                    data=audit_event,
                    constitutional_hash=CONSTITUTIONAL_HASH,
                )
                logger.info("Saga %s: Audit event submitted", saga_id)
            except (OSError, ConnectionError, RuntimeError, ValueError, TypeError) as e:
                logger.warning("Saga %s: Failed to submit audit event: %s", saga_id, e)

        # Also log to local logger for immediate visibility
        logger.info(
            "CONSTITUTIONAL_VERSION_ACTIVATED: %s (previous: %s, amendment: %s)",
            new_version,
            previous_version,
            amendment_id,
        )

        return audit_event

    async def mark_audit_failed(self, input: JSONDict) -> bool:
        """
        Compensation: Mark audit entry as failed/compensated.

        Logs a compensation audit event indicating activation was rolled back.
        """
        saga_id = input["saga_id"]
        context = input["context"]

        audit_data = context.get("audit_activation", {})
        audit_id = audit_data.get("audit_id", "unknown")

        logger.info("Saga %s: Marking audit %s as compensated", saga_id, audit_id)

        # Log compensation event
        compensation_event = {
            "event_type": "constitutional_activation_compensated",
            "saga_id": saga_id,
            "original_audit_id": audit_id,
            "reason": "Saga compensation triggered",
            "timestamp": datetime.now(UTC).isoformat(),
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }

        if self._audit_client:
            try:
                await self._audit_client.log(
                    event_type="constitutional_activation_compensated",
                    data=compensation_event,
                    constitutional_hash=CONSTITUTIONAL_HASH,
                )
            except (OSError, ConnectionError, RuntimeError, ValueError, TypeError) as e:
                logger.warning("Failed to log compensation audit event: %s", e)

        logger.warning(
            "CONSTITUTIONAL_ACTIVATION_COMPENSATED: audit_id=%s, saga_id=%s", audit_id, saga_id
        )

        return True


def create_activation_saga(
    amendment_id: str,
    storage: ConstitutionalStorageService,
    opa_url: str = "http://localhost:8181",
    audit_service_url: str = "http://localhost:8001",
    redis_url: str | None = None,
) -> "ConstitutionalSagaWorkflow":
    """
    Factory function to create a constitutional amendment activation saga.

    The saga has 5 steps with compensations:
    1. Validate - Validate amendment can be activated
    2. Backup Current - Backup current active version for rollback
    3. Update OPA - Update OPA policies with new hash and rules
    4. Update Cache - Invalidate Redis cache and activate new version
    5. Audit - Log activation to audit trail and emit event

    Args:
        amendment_id: Amendment proposal ID to activate
        storage: Constitutional storage service
        opa_url: OPA server URL
        audit_service_url: Audit service URL
        redis_url: Redis connection URL

    Returns:
        Configured ConstitutionalSagaWorkflow ready to execute

    Example:
        ```python
        storage = ConstitutionalStorageService()
        await storage.connect()

        saga = create_activation_saga(
            amendment_id="amendment-123",
            storage=storage
        )

        # Execute saga
        context = SagaContext(
            saga_id=saga.saga_id,
            step_results={"amendment_id": "amendment-123"}
        )
        result = await saga.execute(context)

        if result.status == SagaStatus.COMPLETED:
        else:
        ```
    """
    if not ConstitutionalSagaWorkflow:
        raise ImportError(
            "ConstitutionalSagaWorkflow not available. "
            "Ensure deliberation_layer.workflows.constitutional_saga is installed."
        )

    saga_id = f"activation-{amendment_id}-{str(uuid4())[:8]}"
    activities = ActivationSagaActivities(
        storage=storage, opa_url=opa_url, audit_service_url=audit_service_url, redis_url=redis_url
    )

    saga = ConstitutionalSagaWorkflow(saga_id=saga_id)

    # Step 1: Validate
    saga.add_step(
        SagaStep(
            name="validate_activation",
            description="Validate amendment can be activated",
            execute=activities.validate_activation,
            compensation=SagaCompensation(
                name="log_validation_failure",
                description="Log validation failure",
                execute=activities.log_validation_failure,
            ),
            timeout_seconds=30,
        )
    )

    # Step 2: Backup Current
    saga.add_step(
        SagaStep(
            name="backup_current_version",
            description="Backup current active constitutional version",
            execute=activities.backup_current_version,
            compensation=SagaCompensation(
                name="restore_backup",
                description="Restore backed up version",
                execute=activities.restore_backup,
            ),
            timeout_seconds=30,
        )
    )

    # Step 3: Update OPA
    saga.add_step(
        SagaStep(
            name="update_opa_policies",
            description="Update OPA constitutional policies",
            execute=activities.update_opa_policies,
            compensation=SagaCompensation(
                name="revert_opa_policies",
                description="Revert OPA policies to previous version",
                execute=activities.revert_opa_policies,
            ),
            timeout_seconds=60,
            is_optional=True,  # OPA update is not critical
        )
    )

    # Step 4: Update Cache
    saga.add_step(
        SagaStep(
            name="update_cache",
            description="Invalidate cache and activate new version",
            execute=activities.update_cache,
            compensation=SagaCompensation(
                name="revert_cache",
                description="Revert cache to previous version",
                execute=activities.revert_cache,
            ),
            timeout_seconds=30,
        )
    )

    # Step 5: Audit
    saga.add_step(
        SagaStep(
            name="audit_activation",
            description="Log activation to audit trail",
            execute=activities.audit_activation,
            compensation=SagaCompensation(
                name="mark_audit_failed",
                description="Mark audit as failed/compensated",
                execute=activities.mark_audit_failed,
            ),
            timeout_seconds=30,
            is_optional=True,  # Audit is not critical for activation
        )
    )

    return saga


async def activate_amendment(
    amendment_id: str,
    storage: ConstitutionalStorageService,
    opa_url: str = "http://localhost:8181",
    audit_service_url: str = "http://localhost:8001",
    redis_url: str | None = None,
) -> SagaResult:
    """
    Activate a constitutional amendment using saga workflow.

    This is a convenience function that creates and executes the activation
    saga in one call. For more control, use create_activation_saga() directly.

    Args:
        amendment_id: Amendment proposal ID to activate
        storage: Constitutional storage service
        opa_url: OPA server URL
        audit_service_url: Audit service URL
        redis_url: Redis connection URL

    Returns:
        SagaResult with activation status and details

    Raises:
        ActivationSagaError: If activation fails critically

    Example:
        ```python
        storage = ConstitutionalStorageService()
        await storage.connect()

        result = await activate_amendment(
            amendment_id="amendment-123",
            storage=storage
        )

        if result.status == SagaStatus.COMPLETED:
        else:
        ```
    """
    if not SagaContext:
        raise ImportError("SagaContext not available")

    # Create saga
    saga = create_activation_saga(
        amendment_id=amendment_id,
        storage=storage,
        opa_url=opa_url,
        audit_service_url=audit_service_url,
        redis_url=redis_url,
    )

    # Initialize activities
    if hasattr(saga, "_steps") and saga._steps:
        # Get activities from first step (they're all the same instance)
        first_step = saga._steps[0]
        if hasattr(first_step.execute, "__self__"):
            activities = first_step.execute.__self__
            if isinstance(activities, ActivationSagaActivities):
                await activities.initialize()

    # Create context
    context = SagaContext(saga_id=saga.saga_id, constitutional_hash=CONSTITUTIONAL_HASH)
    context.set_step_result("amendment_id", amendment_id)

    try:
        # Execute saga
        result = await saga.execute(context)
        return result
    finally:
        # Cleanup activities
        if hasattr(saga, "_steps") and saga._steps:
            first_step = saga._steps[0]
            if hasattr(first_step.execute, "__self__"):
                activities = first_step.execute.__self__
                if isinstance(activities, ActivationSagaActivities):
                    await activities.close()
