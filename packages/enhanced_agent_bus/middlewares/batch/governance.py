"""
Batch Governance Middleware for ACGS-2 Pipeline.

MACI and governance validation for batches.
Extracted from: batch_processor_infra/governance.py

Constitutional Hash: 608508a9bd224290
"""

import time
from typing import cast

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.validators import ValidationResult

from ...batch_models import BatchRequestItem
from ...maci_enforcement import MACIAction, MACIEnforcer
from ...pipeline.context import PipelineContext
from ...pipeline.middleware import BaseMiddleware, MiddlewareConfig
from .context import BatchPipelineContext
from .exceptions import BatchGovernanceException

BATCH_MACI_VALIDATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
)
BATCH_TENANT_VALIDATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
)


class BatchGovernanceMiddleware(BaseMiddleware):
    """MACI and governance validation for batches.

    Enforces Multi-Agent Constitutional Intelligence principles:
    - Validates MACI roles across all items
    - Calculates batch impact score
    - Ensures constitutional compliance
    - Prevents self-validation scenarios

    Example:
        middleware = BatchGovernanceMiddleware(
            maci_registry=role_registry,
        )
        context = await middleware.process(batch_context)

    Constitutional Hash: 608508a9bd224290
    """

    # Impact thresholds for governance decisions
    IMPACT_LOW = 0.3
    IMPACT_MEDIUM = 0.5
    IMPACT_HIGH = 0.7
    IMPACT_CRITICAL = 0.9

    def __init__(
        self,
        config: MiddlewareConfig | None = None,
        maci_registry: object | None = None,
        maci_enforcer: MACIEnforcer | None = None,
    ):
        """Initialize batch governance middleware.

        Args:
            config: Middleware configuration (timeout, fail_closed, etc.)
            maci_registry: Optional MACI role registry for validation (deprecated, use maci_enforcer)
            maci_enforcer: Optional MACI enforcer for validation
        """
        super().__init__(config)
        self._maci_registry = maci_registry
        # Initialize enforcer with provided registry or create new one
        if maci_enforcer:
            self._maci_enforcer = maci_enforcer
        elif maci_registry:
            self._maci_enforcer = MACIEnforcer(
                registry=maci_registry, strict_mode=config.fail_closed if config else True
            )
        else:
            self._maci_enforcer = MACIEnforcer(strict_mode=config.fail_closed if config else True)

        # Metrics tracking for cache performance
        self._maci_cache_hits = 0
        self._maci_cache_misses = 0
        self._tenant_cache_hits = 0
        self._tenant_cache_misses = 0

    async def process(self, context: PipelineContext) -> PipelineContext:
        """Process batch governance validation.

        Steps:
        1. Check MACI roles for all items
        2. Calculate batch impact score
        3. Validate constitutional compliance
        4. Apply governance decisions

        Args:
            context: Batch pipeline context containing items

        Returns:
            Context with governance validation results

        Raises:
            BatchGovernanceException: If validation fails and fail_closed is True
        """
        context = cast(BatchPipelineContext, context)
        start_time = time.perf_counter()

        # Skip if no items
        if not context.batch_items:
            return await self._call_next(context)

        # Execute MACI validation
        if not await self._execute_maci_validation(context):
            return context

        # Execute tenant validation
        if not await self._execute_tenant_validation(context):
            return context

        # Execute impact validation
        if not await self._execute_impact_validation(context):
            return context

        # Execute constitutional validation
        if not await self._execute_constitutional_validation(context):
            return context

        # Finalize governance decision
        self._finalize_governance_decision(context, start_time)

        return await self._call_next(context)

    async def _execute_maci_validation(self, context: BatchPipelineContext) -> bool:
        """Execute MACI role validation and handle results.

        Returns:
            True if validation passes or can continue, False if early exit needed
        """
        # Check MACI roles with request-scope memoization
        maci_cache: dict[tuple[str, str, str, str], bool] = {}
        maci_valid, maci_metrics = self._check_maci_roles(context.batch_items, cache=maci_cache)

        # Store MACI metrics on context for observability
        context.metadata["maci_cache_hits"] = maci_metrics["cache_hits"]
        context.metadata["maci_cache_misses"] = maci_metrics["cache_misses"]
        context.metadata["maci_items_checked"] = maci_metrics["items_checked"]

        if not maci_valid:
            return self._handle_maci_validation_failure(context, maci_metrics, maci_cache)

        return True

    async def _execute_tenant_validation(self, context: BatchPipelineContext) -> bool:
        """Execute tenant access validation and handle results.

        Returns:
            True if validation passes or can continue, False if early exit needed
        """
        # Check tenant access with request-scope memoization
        tenant_cache: dict[tuple[str, str], bool] = {}
        tenant_valid, tenant_metrics = self._validate_tenant_access(
            context.batch_items, cache=tenant_cache
        )

        # Store tenant metrics on context
        context.metadata["tenant_cache_hits"] = tenant_metrics["cache_hits"]
        context.metadata["tenant_cache_misses"] = tenant_metrics["cache_misses"]
        context.metadata["tenant_batch_tenant"] = tenant_metrics["batch_tenant"]
        context.batch_tenant_id = tenant_metrics["batch_tenant"]

        if not tenant_valid:
            return self._handle_tenant_validation_failure(context, tenant_metrics, tenant_cache)

        return True

    async def _execute_impact_validation(self, context: BatchPipelineContext) -> bool:
        """Execute impact score validation and handle results.

        Returns:
            True if validation passes or can continue, False if early exit needed
        """
        # Calculate impact score
        impact_score = self._calculate_batch_impact(context.batch_items)
        context.impact_score = impact_score

        # Check if impact exceeds threshold
        if impact_score >= self.IMPACT_CRITICAL:
            error_msg = f"Batch impact score {impact_score:.2f} exceeds critical threshold"
            if self.config.fail_closed:
                raise BatchGovernanceException(
                    message=error_msg,
                    impact_score=impact_score,
                )
            # Log warning but continue in non-fail-closed mode
            context.warnings.append(error_msg)

        return True

    async def _execute_constitutional_validation(self, context: BatchPipelineContext) -> bool:
        """Execute constitutional compliance validation and handle results.

        Returns:
            True if validation passes or can continue, False if early exit needed
        """
        constitutional_valid = self._validate_constitutional_compliance(context.batch_items)
        if not constitutional_valid:
            error_msg = "Constitutional compliance validation failed"
            if self.config.fail_closed:
                raise BatchGovernanceException(
                    message=error_msg,
                    maci_violation="constitutional_compliance",
                )
            context.set_early_result(
                ValidationResult(
                    is_valid=False,
                    errors=[error_msg],
                    metadata={"validation_stage": "constitutional"},
                )
            )
            return False

        return True

    def _finalize_governance_decision(
        self, context: BatchPipelineContext, start_time: float
    ) -> None:
        """Finalize governance decision and record metrics."""
        # Store governance decision on context
        context.governance_allowed = True
        context.governance_reasoning = self._generate_governance_reasoning(
            context.impact_score, len(context.batch_items)
        )

        # Record metrics
        duration_ms = (time.perf_counter() - start_time) * 1000
        context.batch_latency_ms += duration_ms

    def _handle_maci_validation_failure(
        self,
        context: BatchPipelineContext,
        maci_metrics: dict,
        maci_cache: dict,
    ) -> bool:
        """Handle MACI validation failure."""
        error_msg = "MACI role validation failed for batch items"
        if maci_metrics["violations"]:
            error_msg += f": {maci_metrics['violations'][0]['reason']}"

        if self.config.fail_closed:
            raise BatchGovernanceException(
                message=error_msg,
                maci_violation="role_validation_failed",
            )

        context.set_early_result(
            ValidationResult(
                is_valid=False,
                errors=[error_msg],
                metadata={
                    "validation_stage": "maci_roles",
                    "maci_violations": maci_metrics["violations"],
                    "maci_cache_size": len(maci_cache),
                },
            )
        )
        return False

    def _handle_tenant_validation_failure(
        self,
        context: BatchPipelineContext,
        tenant_metrics: dict,
        tenant_cache: dict,
    ) -> bool:
        """Handle tenant validation failure."""
        error_msg = "Tenant validation failed for batch items"
        if tenant_metrics["violations"]:
            error_msg += f": {tenant_metrics['violations'][0]['reason']}"

        if self.config.fail_closed:
            raise BatchGovernanceException(
                message=error_msg,
                maci_violation="tenant_validation_failed",
            )

        context.set_early_result(
            ValidationResult(
                is_valid=False,
                errors=[error_msg],
                metadata={
                    "validation_stage": "tenant_access",
                    "tenant_violations": tenant_metrics["violations"],
                    "tenant_cache_size": len(tenant_cache),
                },
            )
        )
        return False

    def _check_maci_roles(
        self,
        items: list[BatchRequestItem],
        cache: dict[tuple[str, str, str, str], bool] | None = None,
    ) -> tuple[bool, JSONDict]:
        """Check MACI roles for all batch items with request-scope memoization.

        Validates that agents have appropriate roles for their actions.
        Prevents self-validation scenarios. Uses decision key caching for performance.

        Decision key format: (tenant_id, agent_id, action_type, message_type)

        Args:
            items: List of batch items to validate
            cache: Optional cache dictionary for memoization (created if not provided)

        Returns:
            Tuple of (success: bool, metadata: dict with metrics and details)
        """
        # Initialize cache if not provided
        if cache is None:
            cache = {}

        metrics: JSONDict = {
            "cache_hits": 0,
            "cache_misses": 0,
            "items_checked": 0,
            "violations": [],
        }

        for idx, item in enumerate(items):
            if not self._validate_single_maci_role(item, idx, cache, metrics):
                return False, metrics

        return True, metrics

    def _build_maci_decision_key(self, item: BatchRequestItem) -> tuple[str, str, str, str]:
        """Build a MACI decision key for request-scope memoization."""
        tenant_id = item.tenant_id or "default"
        agent_id = item.from_agent or ""
        action_type = item.message_type or "unknown"
        content_type = item.content.get("type", "unknown") if item.content else "unknown"
        return (tenant_id, agent_id, action_type, content_type)

    def _validate_single_maci_role(
        self,
        item: BatchRequestItem,
        idx: int,
        cache: dict[tuple[str, str, str, str], bool],
        metrics: JSONDict,
    ) -> bool:
        """Validate MACI role permissions for a single batch item."""
        agent_id = item.from_agent
        if not agent_id:
            return True

        # Build decision key for caching
        decision_key = self._build_maci_decision_key(item)

        # Check cache first
        if self._check_maci_cache(decision_key, cache, metrics, idx, agent_id):
            return cache[decision_key]

        # Update cache metrics
        self._update_maci_cache_metrics(metrics)

        # Map message_type to MACI action
        maci_action = self._map_message_type_to_action(item.message_type)

        try:
            # Validate agent and permissions
            agent_record = self._get_agent_record(agent_id)
            if not self._validate_agent_registration(
                agent_record, cache, decision_key, metrics, idx, agent_id
            ):
                return False

            # Check basic permissions
            can_perform = agent_record.can_perform(maci_action)

            # Apply additional constraints for validation actions
            if maci_action == MACIAction.VALIDATE:
                can_perform = self._apply_validation_constraints(
                    item, idx, agent_record, cache, metrics, can_perform
                )
                if can_perform is None:  # Early return due to constraint failure
                    return False

            # Cache and validate final permission
            return self._finalize_maci_permission(
                can_perform, cache, decision_key, metrics, idx, agent_id, maci_action, agent_record
            )

        except BATCH_MACI_VALIDATION_ERRORS as e:
            return self._handle_maci_validation_error(
                cache, decision_key, metrics, idx, agent_id, e
            )

    def _check_maci_cache(
        self,
        decision_key: tuple[str, str, str, str],
        cache: dict[tuple[str, str, str, str], bool],
        metrics: JSONDict,
        idx: int,
        agent_id: str,
    ) -> bool:
        """Check MACI cache for existing decision."""
        if decision_key in cache:
            metrics["cache_hits"] += 1
            self._maci_cache_hits += 1
            if not cache[decision_key]:
                metrics["violations"].append(
                    {
                        "index": idx,
                        "agent_id": agent_id,
                        "reason": "cached_maci_denial",
                        "decision_key": decision_key,
                    }
                )
            return True
        return False

    def _update_maci_cache_metrics(self, metrics: JSONDict) -> None:
        """Update MACI cache metrics for cache miss."""
        metrics["cache_misses"] += 1
        self._maci_cache_misses += 1
        metrics["items_checked"] += 1

    def _get_agent_record(self, agent_id: str) -> object | None:
        """Get agent record from MACI enforcer registry."""
        return self._maci_enforcer.registry._agents.get(agent_id)  # type: ignore[no-any-return]

    def _validate_agent_registration(
        self,
        agent_record: object | None,
        cache: dict[tuple[str, str, str, str], bool],
        decision_key: tuple[str, str, str, str],
        metrics: JSONDict,
        idx: int,
        agent_id: str,
    ) -> bool:
        """Validate agent is registered in MACI system."""
        if not agent_record:
            if self.config.fail_closed:
                cache[decision_key] = False
                metrics["violations"].append(
                    {
                        "index": idx,
                        "agent_id": agent_id,
                        "reason": "unregistered_agent",
                    }
                )
                return False
            cache[decision_key] = True
        return True

    def _apply_validation_constraints(
        self,
        item: BatchRequestItem,
        idx: int,
        agent_record: object,
        cache: dict[tuple[str, str, str, str], bool],
        metrics: JSONDict,
        can_perform: bool,
    ) -> bool | None:
        """Apply additional constraints for VALIDATE actions. Returns None if early exit needed."""
        constraints_ok, constrained_permission = self._check_validation_action_constraints(
            item, idx, agent_record, cache, metrics
        )
        if not constraints_ok:
            return None  # Signal early return
        return can_perform and constrained_permission

    def _finalize_maci_permission(
        self,
        can_perform: bool,
        cache: dict[tuple[str, str, str, str], bool],
        decision_key: tuple[str, str, str, str],
        metrics: JSONDict,
        idx: int,
        agent_id: str,
        maci_action: MACIAction,
        agent_record: object,
    ) -> bool:
        """Finalize MACI permission decision and handle failures."""
        cache[decision_key] = can_perform

        if not can_perform and self.config.fail_closed:
            metrics["violations"].append(
                {
                    "index": idx,
                    "agent_id": agent_id,
                    "reason": "action_not_permitted",
                    "action": maci_action.value,
                    "role": agent_record.role.value,
                }
            )
            return False

        return True

    def _handle_maci_validation_error(
        self,
        cache: dict[tuple[str, str, str, str], bool],
        decision_key: tuple[str, str, str, str],
        metrics: JSONDict,
        idx: int,
        agent_id: str,
        error: Exception,
    ) -> bool:
        """Handle MACI validation errors."""
        cache[decision_key] = False
        metrics["violations"].append(
            {
                "index": idx,
                "agent_id": agent_id,
                "reason": "validation_error",
                "error": str(error),
            }
        )
        return not self.config.fail_closed

    def _check_validation_action_constraints(
        self,
        item: BatchRequestItem,
        idx: int,
        agent_record: object,
        cache: dict[tuple[str, str, str, str], bool],
        metrics: JSONDict,
    ) -> tuple[bool, bool]:
        """Validate self-validation and cross-role constraints for VALIDATE actions."""
        agent_id = item.from_agent
        if not agent_id:
            return True, True

        decision_key = self._build_maci_decision_key(item)
        content = item.content or {}
        target_agent = content.get("target_agent_id")

        if target_agent and target_agent == agent_id:
            # Check self-validation
            cache[decision_key] = False
            metrics["violations"].append(
                {
                    "index": idx,
                    "agent_id": agent_id,
                    "reason": "self_validation",
                    "target_agent": target_agent,
                }
            )
            if self.config.fail_closed:
                return False, False
            return True, False

        if target_agent:
            # Check cross-role validation constraints
            target_record = self._maci_enforcer.registry._agents.get(target_agent)
            if target_record and not agent_record.can_validate_role(target_record.role):
                cache[decision_key] = False
                metrics["violations"].append(
                    {
                        "index": idx,
                        "agent_id": agent_id,
                        "reason": "cross_role_validation",
                        "target_agent": target_agent,
                        "target_role": target_record.role.value,
                    }
                )
                if self.config.fail_closed:
                    return False, False
                return True, False

        return True, True

    def _map_message_type_to_action(self, message_type: str | None) -> MACIAction:
        """Map message type to MACI action.

        Args:
            message_type: The message type string

        Returns:
            Corresponding MACIAction
        """
        message_type = message_type or "unknown"

        mapping = {
            "governance_request": MACIAction.QUERY,
            "constitutional_validation": MACIAction.VALIDATE,
            "propose": MACIAction.PROPOSE,
            "audit": MACIAction.AUDIT,
            "monitor": MACIAction.MONITOR_ACTIVITY,
            "enforce": MACIAction.ENFORCE_CONTROL,
            "extract_rules": MACIAction.EXTRACT_RULES,
            "synthesize": MACIAction.SYNTHESIZE,
            "manage_policy": MACIAction.MANAGE_POLICY,
        }

        return mapping.get(message_type, MACIAction.QUERY)  # type: ignore[no-any-return]

    def _validate_tenant_access(
        self,
        items: list[BatchRequestItem],
        cache: dict[tuple[str, str], bool] | None = None,
    ) -> tuple[bool, JSONDict]:
        """Validate tenant access for all batch items with request-scope memoization.

        Performs two-level validation:
        1. Batch-level: Check all items belong to same tenant (single-tenant invariant)
        2. Item-level: Validate agent has access to the item's tenant

        Decision key format: (agent_id, tenant_id)

        Args:
            items: List of batch items to validate
            cache: Optional cache dictionary for memoization (created if not provided)

        Returns:
            Tuple of (success: bool, metadata: dict with metrics and details)
        """
        if cache is None:
            cache = {}

        metrics: JSONDict = {
            "cache_hits": 0,
            "cache_misses": 0,
            "items_checked": 0,
            "batch_tenant": None,
            "violations": [],
        }

        if not items:
            return True, metrics

        if not self._validate_tenant_formats(items, metrics):
            return False, metrics

        if not self._check_batch_tenant_consistency(items, metrics):
            return False, metrics

        if not self._validate_item_tenant_access(items, cache, metrics):
            return False, metrics

        return True, metrics

    def _validate_tenant_formats(self, items: list[BatchRequestItem], metrics: JSONDict) -> bool:
        """Level 1 validation: ensure each item's tenant identifier has a valid format."""
        from ...security.tenant_validator import TenantValidator

        for item in items:
            tenant = item.tenant_id or "default"
            # Validate tenant format
            _, is_valid = TenantValidator.sanitize_and_validate(tenant)
            if not is_valid and tenant != "default":
                metrics["violations"].append(
                    {
                        "level": "batch",
                        "reason": "invalid_tenant_format",
                        "tenant": tenant,
                    }
                )
                if self.config.fail_closed:
                    return False

        return True

    def _check_batch_tenant_consistency(
        self, items: list[BatchRequestItem], metrics: JSONDict
    ) -> bool:
        """Level 1 validation: enforce single-tenant invariant across the batch."""
        non_default_tenants = [
            item.tenant_id for item in items if item.tenant_id and item.tenant_id != "default"
        ]

        if non_default_tenants:
            first_tenant = non_default_tenants[0]
            for tenant in non_default_tenants[1:]:
                if tenant != first_tenant:
                    metrics["violations"].append(
                        {
                            "level": "batch",
                            "reason": "cross_tenant_batch",
                            "tenants": list(set(non_default_tenants)),
                        }
                    )
                    if self.config.fail_closed:
                        return False
            metrics["batch_tenant"] = first_tenant
        else:
            metrics["batch_tenant"] = "default"

        return True

    def _validate_item_tenant_access(
        self,
        items: list[BatchRequestItem],
        cache: dict[tuple[str, str], bool],
        metrics: JSONDict,
    ) -> bool:
        """Level 2 validation: authorize each agent-to-tenant access decision."""
        for idx, item in enumerate(items):
            agent_id = item.from_agent
            if not agent_id:
                continue

            tenant_id = item.tenant_id or "default"
            decision_key = (agent_id, tenant_id)

            # Check cache first
            if self._check_tenant_cache(decision_key, cache, metrics, idx, agent_id, tenant_id):
                continue

            # Update cache metrics
            self._update_tenant_cache_metrics(metrics)

            # Validate tenant access for this item
            if not self._validate_single_item_tenant_access(
                idx, agent_id, tenant_id, decision_key, cache, metrics
            ):
                return False

        return True

    def _check_tenant_cache(
        self,
        decision_key: tuple[str, str],
        cache: dict[tuple[str, str], bool],
        metrics: JSONDict,
        idx: int,
        agent_id: str,
        tenant_id: str,
    ) -> bool:
        """Check tenant cache for existing decision."""
        if decision_key in cache:
            metrics["cache_hits"] += 1
            self._tenant_cache_hits += 1
            if not cache[decision_key]:
                metrics["violations"].append(
                    {
                        "level": "item",
                        "index": idx,
                        "agent_id": agent_id,
                        "reason": "cached_tenant_denial",
                        "tenant": tenant_id,
                    }
                )
                if self.config.fail_closed:
                    return False
            return True
        return False

    def _update_tenant_cache_metrics(self, metrics: JSONDict) -> None:
        """Update tenant cache metrics for cache miss."""
        metrics["cache_misses"] += 1
        self._tenant_cache_misses += 1
        metrics["items_checked"] += 1

    def _validate_single_item_tenant_access(
        self,
        idx: int,
        agent_id: str,
        tenant_id: str,
        decision_key: tuple[str, str],
        cache: dict[tuple[str, str], bool],
        metrics: JSONDict,
    ) -> bool:
        """Validate tenant access for a single item."""
        try:
            # Get agent record
            agent_record = self._maci_enforcer.registry._agents.get(agent_id)

            # Handle unregistered agent
            if not agent_record:
                return self._handle_unregistered_agent_tenant_access(
                    idx, agent_id, decision_key, cache, metrics
                )

            # Check tenant permissions
            has_access = self._check_agent_tenant_permissions(agent_record, tenant_id)

            # Cache and handle result
            return self._finalize_tenant_access_decision(
                has_access, idx, agent_id, tenant_id, decision_key, cache, metrics, agent_record
            )

        except BATCH_TENANT_VALIDATION_ERRORS as e:
            return self._handle_tenant_validation_error(
                idx, agent_id, decision_key, cache, metrics, e
            )

    def _handle_unregistered_agent_tenant_access(
        self,
        idx: int,
        agent_id: str,
        decision_key: tuple[str, str],
        cache: dict[tuple[str, str], bool],
        metrics: JSONDict,
    ) -> bool:
        """Handle unregistered agent in tenant access validation."""
        # Unregistered agent — deny in fail-closed mode
        if self.config.fail_closed:
            cache[decision_key] = False
            metrics["violations"].append(
                {
                    "index": idx,
                    "agent_id": agent_id,
                    "reason": "unregistered_agent_tenant_access",
                }
            )
            return False
        cache[decision_key] = True
        return True

    def _check_agent_tenant_permissions(self, agent_record: object, tenant_id: str) -> bool:
        """Check if agent has access to the specified tenant."""
        allowed_tenants = agent_record.metadata.get("allowed_tenants", ["default"])
        agent_tenant = agent_record.metadata.get("tenant_id", "default")

        # Allow if:
        # 1. Tenant is in allowed_tenants list, OR
        # 2. Tenant matches agent's registered tenant
        return tenant_id in allowed_tenants or tenant_id == agent_tenant or tenant_id == "default"

    def _finalize_tenant_access_decision(
        self,
        has_access: bool,
        idx: int,
        agent_id: str,
        tenant_id: str,
        decision_key: tuple[str, str],
        cache: dict[tuple[str, str], bool],
        metrics: JSONDict,
        agent_record: object,
    ) -> bool:
        """Finalize tenant access decision and handle denial."""
        # Cache result
        cache[decision_key] = has_access

        if not has_access:
            allowed_tenants = agent_record.metadata.get("allowed_tenants", ["default"])
            metrics["violations"].append(
                {
                    "level": "item",
                    "index": idx,
                    "agent_id": agent_id,
                    "reason": "tenant_access_denied",
                    "tenant": tenant_id,
                    "allowed_tenants": allowed_tenants,
                }
            )
            if self.config.fail_closed:
                return False

        return True

    def _handle_tenant_validation_error(
        self,
        idx: int,
        agent_id: str,
        decision_key: tuple[str, str],
        cache: dict[tuple[str, str], bool],
        metrics: JSONDict,
        error: Exception,
    ) -> bool:
        """Handle tenant validation errors."""
        cache[decision_key] = False
        metrics["violations"].append(
            {
                "level": "item",
                "index": idx,
                "agent_id": agent_id,
                "reason": "tenant_validation_error",
                "error": str(error),
            }
        )
        return not self.config.fail_closed

    def get_cache_metrics(self) -> dict[str, int]:
        """Get cache hit/miss metrics for observability.

        Returns:
            Dictionary with cache metrics
        """
        return {
            "maci_cache_hits": self._maci_cache_hits,
            "maci_cache_misses": self._maci_cache_misses,
            "tenant_cache_hits": self._tenant_cache_hits,
            "tenant_cache_misses": self._tenant_cache_misses,
        }

    def reset_cache_metrics(self) -> None:
        """Reset cache metrics."""
        self._maci_cache_hits = 0
        self._maci_cache_misses = 0
        self._tenant_cache_hits = 0
        self._tenant_cache_misses = 0

    def _calculate_batch_impact(self, items: list[BatchRequestItem]) -> float:
        """Calculate aggregate impact score for the batch.

        Factors:
        - Number of items (more items = higher impact)
        - Priority distribution (higher priority = higher impact)
        - Content risk indicators

        Args:
            items: List of batch items

        Returns:
            Impact score between 0.0 and 1.0
        """
        if not items:
            return 0.0

        # Base impact from item count (normalized to ~100 items = 0.5)
        count_factor = min(len(items) / 200.0, 0.5)

        # Priority impact (higher priority = higher impact)
        priority_sum = sum(item.priority or 1 for item in items)
        priority_avg = priority_sum / len(items) if items else 1
        priority_factor = (priority_avg / 3.0) * 0.3  # Max 0.3 from priority

        # Content risk indicators
        risk_score = self._calculate_content_risk(items)
        risk_factor = risk_score * 0.2  # Max 0.2 from risk

        # Combine factors
        total_impact = count_factor + priority_factor + risk_factor
        return min(total_impact, 1.0)

    def _calculate_content_risk(self, items: list[BatchRequestItem]) -> float:
        """Calculate content-based risk score.

        Args:
            items: List of batch items

        Returns:
            Risk score between 0.0 and 1.0
        """
        if not items:
            return 0.0

        risk_keywords = [
            "delete",
            "drop",
            "remove",
            "purge",
            "clear",
            "admin",
            "root",
            "system",
            "config",
            "password",
            "secret",
            "key",
            "token",
        ]

        risky_items = 0
        for item in items:
            content = item.content or {}
            content_str = str(content).lower()

            if any(kw in content_str for kw in risk_keywords):
                risky_items += 1

        return risky_items / len(items) if items else 0.0

    def _validate_constitutional_compliance(
        self,
        items: list[BatchRequestItem],
    ) -> bool:
        """Validate constitutional compliance for all items.

        Args:
            items: List of batch items

        Returns:
            True if all items are compliant, False otherwise
        """
        from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

        for item in items:
            # Check per-item constitutional hash if present
            if item.constitutional_hash:
                if item.constitutional_hash != CONSTITUTIONAL_HASH:
                    return False

        return True

    def _generate_governance_reasoning(
        self,
        impact_score: float,
        item_count: int,
    ) -> str:
        """Generate human-readable governance reasoning.

        Args:
            impact_score: Calculated impact score
            item_count: Number of items in batch

        Returns:
            Reasoning string
        """
        if impact_score >= self.IMPACT_CRITICAL:
            level = "CRITICAL"
        elif impact_score >= self.IMPACT_HIGH:
            level = "HIGH"
        elif impact_score >= self.IMPACT_MEDIUM:
            level = "MEDIUM"
        else:
            level = "LOW"

        return f"Batch governance: {level} impact (score={impact_score:.2f}, items={item_count})"

    def get_impact_level(self, impact_score: float) -> str:
        """Get impact level name from score.

        Args:
            impact_score: Impact score

        Returns:
            Impact level string
        """
        if impact_score >= self.IMPACT_CRITICAL:
            return "CRITICAL"
        elif impact_score >= self.IMPACT_HIGH:
            return "HIGH"
        elif impact_score >= self.IMPACT_MEDIUM:
            return "MEDIUM"
        elif impact_score >= self.IMPACT_LOW:
            return "LOW"
        return "MINIMAL"
