"""
ACGS-2 Enhanced Agent Bus - OPA Policy Updater Service
Constitutional Hash: cdd01ef066bc6cf2

Service to dynamically update OPA policies when constitutional amendments are activated.
Provides atomic policy updates with validation, rollback, and health checking.

Key Features:
    - Upload new OPA policy bundles via OPA API
    - Verify policy compilation and syntax before activation
    - Atomic policy updates with fallback to previous version
    - Health check OPA after policy update
    - Emit policy_updated event with version info
"""

import json
import os
import tempfile
from datetime import UTC, datetime, timezone
from enum import Enum
from uuid import uuid4

import httpx
from pydantic import BaseModel, Field

try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH  # noqa: E402
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from src.core.shared.types import JSONDict  # noqa: E402
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

try:
    import aiofiles

    AIOFILES_AVAILABLE = True
except ImportError:
    AIOFILES_AVAILABLE = False

try:
    from ..audit_client import AuditClient
    from ..opa_client import OPAClient
except ImportError:
    AuditClient = None  # type: ignore[assignment]
    OPAClient = None  # type: ignore[assignment]

logger = get_logger(__name__)


class PolicyUpdateStatus(str, Enum):  # noqa: UP042
    """Status of OPA policy update operations."""

    PENDING = "pending"
    VALIDATING = "validating"
    COMPILING = "compiling"
    UPLOADING = "uploading"
    ACTIVATING = "activating"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class PolicyValidationResult(BaseModel):
    """Result of OPA policy validation."""

    is_valid: bool = Field(description="Whether policy is valid")
    errors: list[str] = Field(default_factory=list, description="Validation errors")
    warnings: list[str] = Field(default_factory=list, description="Validation warnings")
    policy_id: str = Field(description="Policy identifier")
    syntax_check: bool = Field(default=False, description="Syntax check passed")
    compile_check: bool = Field(default=False, description="Compilation check passed")
    metadata: JSONDict = Field(default_factory=dict, description="Additional metadata")


class PolicyUpdateRequest(BaseModel):
    """Request to update OPA policies."""

    policy_id: str = Field(description="Unique policy identifier")
    policy_content: str = Field(description="Rego policy content")
    version: str = Field(description="Policy version (e.g., v1.2.0)")
    constitutional_hash: str = Field(
        default=CONSTITUTIONAL_HASH, description="Constitutional hash for validation"
    )
    metadata: JSONDict = Field(default_factory=dict, description="Additional metadata")
    dry_run: bool = Field(default=False, description="Validate only, don't activate")


class PolicyUpdateResult(BaseModel):
    """Result of OPA policy update operation."""

    update_id: str = Field(description="Unique update operation identifier")
    policy_id: str = Field(description="Policy identifier")
    version: str = Field(description="Policy version")
    status: PolicyUpdateStatus = Field(description="Update operation status")
    validation: PolicyValidationResult | None = Field(default=None, description="Validation result")
    previous_version: str | None = Field(
        default=None, description="Previous policy version (for rollback)"
    )
    health_check_passed: bool = Field(default=False, description="OPA health check after update")
    cache_invalidated: bool = Field(default=False, description="OPA cache invalidation status")
    rolled_back: bool = Field(default=False, description="Whether update was rolled back")
    error_message: str | None = Field(default=None, description="Error message if failed")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="Timestamp of operation",
    )
    metadata: JSONDict = Field(default_factory=dict, description="Additional metadata")


class OPAPolicyUpdater:
    """
    Service to dynamically update OPA policies when constitutional amendments are activated.

    Provides atomic policy updates with validation, compilation checks, rollback on failure,
    and comprehensive audit logging.

    Example:
        ```python
        updater = OPAPolicyUpdater(opa_url="http://localhost:8181")
        await updater.connect()

        # Update policy
        request = PolicyUpdateRequest(
            policy_id="constitutional",
            policy_content=new_rego_content,
            version="v1.1.0"
        )

        result = await updater.update_policy(request)

        if result.status == PolicyUpdateStatus.COMPLETED:
        else:

        await updater.disconnect()
        ```
    """

    def __init__(
        self,
        opa_url: str = "http://localhost:8181",
        audit_service_url: str = "http://localhost:8001",
        enable_health_checks: bool = True,
        enable_cache_invalidation: bool = True,
        enable_rollback: bool = True,
        health_check_timeout: float = 5.0,
        policy_backup_dir: str | None = None,
    ):
        """Initialize OPA Policy Updater Service.

        Args:
            opa_url: OPA server URL
            audit_service_url: Audit service URL for event logging
            enable_health_checks: Enable health checks after policy updates
            enable_cache_invalidation: Enable cache invalidation after updates
            enable_rollback: Enable automatic rollback on failure
            health_check_timeout: Timeout for health checks in seconds
            policy_backup_dir: Directory to store policy backups (for rollback)
        """
        self.opa_url = opa_url.rstrip("/")
        self.audit_service_url = audit_service_url
        self.enable_health_checks = enable_health_checks
        self.enable_cache_invalidation = enable_cache_invalidation
        self.enable_rollback = enable_rollback
        self.health_check_timeout = health_check_timeout
        self.policy_backup_dir = policy_backup_dir or tempfile.gettempdir()

        self._http_client: httpx.AsyncClient | None = None
        self._opa_client: object | None = None
        self._audit_client: object | None = None
        self._policy_backups: dict[str, JSONDict] = {}

    async def connect(self) -> None:
        """Initialize connections to OPA and audit service."""
        # HTTP client for OPA API
        self._http_client = httpx.AsyncClient(
            timeout=30.0,
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
        )

        # OPA client for health checks and cache invalidation
        if OPAClient:
            try:
                self._opa_client = OPAClient(opa_url=self.opa_url)
                await self._opa_client.initialize()
                logger.info("OPA client initialized successfully")
            except (RuntimeError, ValueError, TypeError) as e:
                logger.warning("Failed to initialize OPA client: %s", e)
                self._opa_client = None

        # Audit client for event logging
        if AuditClient:
            try:
                self._audit_client = AuditClient(service_url=self.audit_service_url)
                await self._audit_client.start()
                logger.info("Audit client initialized successfully")
            except (RuntimeError, ValueError, TypeError) as e:
                logger.warning("Failed to initialize audit client: %s", e)
                self._audit_client = None

    async def disconnect(self) -> None:
        """Close all connections."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

        if self._opa_client:
            await self._opa_client.close()
            self._opa_client = None

        if self._audit_client:
            await self._audit_client.stop()
            self._audit_client = None

    async def update_policy(self, request: PolicyUpdateRequest) -> PolicyUpdateResult:
        """
        Update OPA policy with atomic rollback on failure.

        Workflow:
        1. Validate policy syntax and compilation
        2. Backup current policy (if exists)
        3. Upload new policy to OPA
        4. Health check OPA
        5. Invalidate cache
        6. Emit policy_updated event
        7. Rollback if any step fails

        Args:
            request: Policy update request

        Returns:
            PolicyUpdateResult with operation status
        """
        update_id = str(uuid4())
        logger.info(
            "Update %s: Starting policy update for %s version %s",
            update_id,
            request.policy_id,
            request.version,
        )

        result = PolicyUpdateResult(
            update_id=update_id,
            policy_id=request.policy_id,
            version=request.version,
            status=PolicyUpdateStatus.PENDING,
        )

        try:
            # Step 1: Validate policy
            result.status = PolicyUpdateStatus.VALIDATING
            validation = await self._validate_policy(request)
            result.validation = validation

            if not validation.is_valid:
                result.status = PolicyUpdateStatus.FAILED
                result.error_message = f"Policy validation failed: {', '.join(validation.errors)}"
                await self._emit_policy_event(result, "policy_validation_failed")
                return result

            if request.dry_run:
                logger.info("Update %s: Dry run - validation passed, skipping upload", update_id)
                result.status = PolicyUpdateStatus.COMPLETED
                return result

            # Step 2: Backup current policy
            previous_version = await self._backup_current_policy(request.policy_id)
            result.previous_version = previous_version

            # Step 3: Upload policy to OPA
            result.status = PolicyUpdateStatus.UPLOADING
            upload_success = await self._upload_policy_to_opa(request)

            if not upload_success:
                result.status = PolicyUpdateStatus.FAILED
                result.error_message = "Failed to upload policy to OPA"
                await self._rollback_policy(request.policy_id, previous_version, result)
                return result

            # Step 4: Health check OPA
            if self.enable_health_checks:
                health_ok = await self._health_check_opa()
                result.health_check_passed = health_ok

                if not health_ok:
                    result.status = PolicyUpdateStatus.FAILED
                    result.error_message = "OPA health check failed after policy update"
                    await self._rollback_policy(request.policy_id, previous_version, result)
                    return result

            # Step 5: Invalidate cache
            if self.enable_cache_invalidation:
                cache_invalidated = await self._invalidate_cache(request.policy_id)
                result.cache_invalidated = cache_invalidated

            # Step 6: Update status and emit event
            result.status = PolicyUpdateStatus.COMPLETED
            result.metadata.update(
                {
                    "constitutional_hash": request.constitutional_hash,
                    "dry_run": request.dry_run,
                    "validation_warnings": validation.warnings,
                }
            )

            await self._emit_policy_event(result, "policy_updated")

            logger.info(
                "Update %s: Policy %s updated successfully to version %s",
                update_id,
                request.policy_id,
                request.version,
            )

            return result

        except (RuntimeError, ValueError, TypeError) as e:
            logger.error("Update %s: Policy update failed with exception: %s", update_id, e)
            result.status = PolicyUpdateStatus.FAILED
            result.error_message = str(e)

            # Rollback on exception
            if result.previous_version:
                await self._rollback_policy(request.policy_id, result.previous_version, result)

            await self._emit_policy_event(result, "policy_update_failed")
            return result

    async def _validate_policy(self, request: PolicyUpdateRequest) -> PolicyValidationResult:
        """
        Validate OPA policy syntax and compilation.

        Uses OPA's compile API to check policy without activating it.

        Args:
            request: Policy update request

        Returns:
            PolicyValidationResult with validation status
        """
        logger.info("Validating policy %s", request.policy_id)

        validation = PolicyValidationResult(
            policy_id=request.policy_id,
            is_valid=False,
        )

        if not self._http_client:
            validation.errors.append("HTTP client not initialized")
            return validation

        try:
            # Use OPA compile API to validate syntax
            compile_url = f"{self.opa_url}/v1/compile"

            # Prepare compile request
            compile_request = {
                "query": "data",  # Compile entire policy
                "input": {},
                "unknowns": [],
            }

            # First, upload policy temporarily for compilation check
            policy_url = f"{self.opa_url}/v1/policies/{request.policy_id}_validate"

            response = await self._http_client.put(
                policy_url,
                content=request.policy_content,
                headers={"Content-type": "text/plain"},
            )

            # Check for syntax errors in response
            if response.status_code >= 400:
                validation.syntax_check = False
                error_data = (
                    response.json()
                    if response.headers.get("content-type", "").startswith("application/json")
                    else {}
                )
                error_msg = error_data.get("message", f"HTTP {response.status_code}")
                validation.errors.append(f"Syntax error: {error_msg}")

                # Clean up temporary policy
                await self._http_client.delete(policy_url)
                return validation

            validation.syntax_check = True

            # Compile check
            compile_response = await self._http_client.post(
                compile_url,
                json=compile_request,
            )

            if compile_response.status_code == 200:
                validation.compile_check = True
                validation.is_valid = True
                logger.info("Policy %s validation passed", request.policy_id)
            else:
                validation.compile_check = False
                compile_data = (
                    compile_response.json()
                    if compile_response.headers.get("content-type", "").startswith(
                        "application/json"
                    )
                    else {}
                )
                compile_error = compile_data.get(
                    "message", f"Compilation failed with status {compile_response.status_code}"
                )
                validation.errors.append(f"Compilation error: {compile_error}")

            # Clean up temporary policy
            await self._http_client.delete(policy_url)

            return validation

        except httpx.HTTPError as e:
            logger.error("HTTP error during policy validation: %s", e)
            validation.errors.append(f"HTTP error: {e!s}")
            return validation
        except (RuntimeError, ValueError, TypeError) as e:
            logger.error("Unexpected error during policy validation: %s", e)
            validation.errors.append(f"Validation error: {e!s}")
            return validation

    async def _backup_current_policy(self, policy_id: str) -> str | None:
        """
        Backup current policy from OPA for rollback capability.

        Args:
            policy_id: Policy identifier to backup

        Returns:
            Previous policy version identifier or None if no backup exists
        """
        if not self.enable_rollback:
            return None

        logger.info("Backing up current policy %s", policy_id)

        if not self._http_client:
            logger.warning("HTTP client not available for policy backup")
            return None

        try:
            # Get current policy from OPA
            policy_url = f"{self.opa_url}/v1/policies/{policy_id}"
            response = await self._http_client.get(policy_url)

            if response.status_code == 200:
                policy_data = response.json()
                backup_id = f"{policy_id}_backup_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"

                # Store backup
                self._policy_backups[policy_id] = {
                    "backup_id": backup_id,
                    "policy_data": policy_data,
                    "timestamp": datetime.now(UTC).isoformat(),
                }

                # Also write to disk for persistence
                backup_path = os.path.join(self.policy_backup_dir, f"{backup_id}.json")
                if AIOFILES_AVAILABLE:
                    async with aiofiles.open(backup_path, "w") as f:
                        await f.write(json.dumps(policy_data, indent=2))
                else:
                    logger.warning("aiofiles not available, using sync I/O fallback")
                    with open(backup_path, "w") as f:
                        json.dump(policy_data, f, indent=2)

                logger.info("Policy %s backed up as %s", policy_id, backup_id)
                return backup_id

            elif response.status_code == 404:
                logger.info("No existing policy %s to backup (new policy)", policy_id)
                return None
            else:
                logger.warning(
                    "Failed to backup policy %s: HTTP %s", policy_id, response.status_code
                )
                return None

        except (RuntimeError, ValueError, TypeError) as e:
            logger.error("Error backing up policy %s: %s", policy_id, e)
            return None

    async def _upload_policy_to_opa(self, request: PolicyUpdateRequest) -> bool:
        """
        Upload policy to OPA via PUT /v1/policies/{id}.

        Args:
            request: Policy update request

        Returns:
            True if upload succeeded, False otherwise
        """
        logger.info("Uploading policy %s to OPA", request.policy_id)

        if not self._http_client:
            logger.error("HTTP client not initialized")
            return False

        try:
            policy_url = f"{self.opa_url}/v1/policies/{request.policy_id}"

            response = await self._http_client.put(
                policy_url,
                content=request.policy_content,
                headers={"Content-type": "text/plain"},
            )

            if response.status_code in (200, 204):
                logger.info("Policy %s uploaded successfully", request.policy_id)
                return True
            else:
                logger.error(
                    "Failed to upload policy %s: HTTP %s",
                    request.policy_id,
                    response.status_code,
                )
                return False

        except (RuntimeError, ValueError, TypeError) as e:
            logger.error("Error uploading policy %s: %s", request.policy_id, e)
            return False

    async def _health_check_opa(self) -> bool:
        """
        Health check OPA after policy update.

        Returns:
            True if OPA is healthy, False otherwise
        """
        logger.info("Performing OPA health check")

        if self._opa_client:
            try:
                health_result = await self._opa_client.health_check()
                is_healthy = health_result.get("status") == "healthy"
                logger.info("OPA health check: %s", "passed" if is_healthy else "failed")
                return is_healthy  # type: ignore[no-any-return]
            except (RuntimeError, ValueError, TypeError) as e:
                logger.error("OPA health check failed: %s", e)
                return False

        # Fallback to direct HTTP health check
        if not self._http_client:
            logger.warning("No HTTP client for health check")
            return False

        try:
            health_url = f"{self.opa_url}/health"
            response = await self._http_client.get(health_url, timeout=self.health_check_timeout)
            is_healthy = response.status_code == 200
            logger.info("OPA health check: %s", "passed" if is_healthy else "failed")
            return is_healthy  # type: ignore[no-any-return]
        except (RuntimeError, ValueError, TypeError) as e:
            logger.error("OPA health check failed: %s", e)
            return False

    async def _invalidate_cache(self, policy_id: str) -> bool:
        """
        Invalidate OPA policy cache after update.

        Args:
            policy_id: Policy identifier

        Returns:
            True if cache invalidated, False otherwise
        """
        logger.info("Invalidating cache for policy %s", policy_id)

        if not self._opa_client:
            logger.warning("OPA client not available for cache invalidation")
            return False

        try:
            # Clear cache for specific policy path
            policy_path = policy_id.replace("_", ".")
            await self._opa_client.clear_cache(policy_path=policy_path)
            logger.info("Cache invalidated for policy %s", policy_id)
            return True
        except (RuntimeError, ValueError, TypeError) as e:
            logger.error("Failed to invalidate cache for policy %s: %s", policy_id, e)
            return False

    async def _rollback_policy(
        self, policy_id: str, backup_id: str | None, result: PolicyUpdateResult
    ) -> bool:
        """
        Rollback policy to previous version on failure.

        Args:
            policy_id: Policy identifier to rollback
            backup_id: Backup identifier to restore
            result: Update result to update with rollback status

        Returns:
            True if rollback succeeded, False otherwise
        """
        if not self.enable_rollback:
            logger.warning("Rollback disabled, not rolling back policy %s", policy_id)
            return False

        if not backup_id:
            logger.warning("No backup available for policy %s, cannot rollback", policy_id)
            return False

        logger.warning("Rolling back policy %s to backup %s", policy_id, backup_id)

        try:
            # Restore from memory backup
            backup = self._policy_backups.get(policy_id)

            if not backup:
                # Try loading from disk
                backup_path = os.path.join(self.policy_backup_dir, f"{backup_id}.json")
                if os.path.exists(backup_path):
                    if AIOFILES_AVAILABLE:
                        async with aiofiles.open(backup_path) as f:
                            content = await f.read()
                            backup = {"policy_data": json.loads(content)}
                    else:
                        logger.warning("aiofiles not available, using sync I/O fallback")
                        with open(backup_path) as f:
                            backup = {"policy_data": json.load(f)}
                else:
                    logger.error("Backup %s not found in memory or disk", backup_id)
                    return False

            # Upload backed up policy
            if self._http_client and backup:
                policy_url = f"{self.opa_url}/v1/policies/{policy_id}"
                policy_content = backup["policy_data"].get("result", {}).get("raw", "")

                if not policy_content:
                    logger.error("No policy content in backup %s", backup_id)
                    return False

                response = await self._http_client.put(
                    policy_url,
                    content=policy_content,
                    headers={"Content-type": "text/plain"},
                )

                if response.status_code in (200, 204):
                    logger.info("Policy %s rolled back successfully to %s", policy_id, backup_id)
                    result.rolled_back = True
                    result.status = PolicyUpdateStatus.ROLLED_BACK
                    await self._emit_policy_event(result, "policy_rolled_back")
                    return True
                else:
                    logger.error(
                        "Failed to rollback policy %s: HTTP %s", policy_id, response.status_code
                    )
                    return False

            return False

        except (RuntimeError, ValueError, TypeError) as e:
            logger.error("Error rolling back policy %s: %s", policy_id, e)
            return False

    async def _emit_policy_event(self, result: PolicyUpdateResult, event_type: str) -> None:
        """
        Emit policy update event to audit service.

        Args:
            result: Policy update result
            event_type: Event type (policy_updated, policy_validation_failed, etc.)
        """
        logger.info("Emitting policy event: %s", event_type)

        event_data = {
            "update_id": result.update_id,
            "policy_id": result.policy_id,
            "version": result.version,
            "status": result.status.value,
            "event_type": event_type,
            "constitutional_hash": CONSTITUTIONAL_HASH,
            "timestamp": result.timestamp,
            "metadata": {
                **result.metadata,
                "health_check_passed": result.health_check_passed,
                "cache_invalidated": result.cache_invalidated,
                "rolled_back": result.rolled_back,
            },
        }

        if result.error_message:
            event_data["error"] = result.error_message

        if result.validation:
            event_data["validation"] = {
                "is_valid": result.validation.is_valid,
                "errors": result.validation.errors,
                "warnings": result.validation.warnings,
            }

        # Submit to audit service
        if self._audit_client:
            try:
                await self._audit_client.log(
                    event_type=event_type, data=event_data, constitutional_hash=CONSTITUTIONAL_HASH
                )
                logger.info("Policy event %s submitted to audit service", event_type)
            except (RuntimeError, ValueError, TypeError) as e:
                logger.warning("Failed to submit policy event to audit service: %s", e)

        # Also log locally
        logger.info(
            "POLICY_EVENT: %s - policy_id=%s, version=%s, status=%s",
            event_type,
            result.policy_id,
            result.version,
            result.status.value,
        )


__all__ = [
    "OPAPolicyUpdater",
    "PolicyUpdateRequest",
    "PolicyUpdateResult",
    "PolicyUpdateStatus",
    "PolicyValidationResult",
]
