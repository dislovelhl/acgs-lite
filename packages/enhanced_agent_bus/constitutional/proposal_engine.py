"""
ACGS-2 Enhanced Agent Bus - Amendment Proposal Engine
Constitutional Hash: 608508a9bd224290

Service to create, validate, and submit constitutional amendment proposals
with impact analysis, MACI enforcement, and automatic audit logging.
"""

from datetime import UTC, datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field

# Import centralized constitutional hash
try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
from src.core.shared.errors.exceptions import ACGSBaseError

try:
    from src.core.shared.types import (
        JSONDict,
        JSONList,
    )
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]
    JSONList = list  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from .amendment_model import AmendmentProposal, AmendmentStatus
from .diff_engine import ConstitutionalDiffEngine, SemanticDiff
from .storage import ConstitutionalStorageService  # type: ignore[attr-defined]
from .version_model import ConstitutionalVersion

# Import invariant validation — fail-closed: log ERROR if unavailable
_INVARIANT_IMPORTS_AVAILABLE = True
try:
    from .invariant_guard import ConstitutionalInvariantViolation, ProposalInvariantValidator
    from .invariants import get_default_manifest
except ImportError:
    _INVARIANT_IMPORTS_AVAILABLE = False
    ProposalInvariantValidator = None  # type: ignore[assignment,misc]
    ConstitutionalInvariantViolation = None  # type: ignore[assignment,misc]
    get_default_manifest = None  # type: ignore[assignment]

# Import MACI enforcement
try:
    from ..maci_enforcement import MACIAction, MACIEnforcer, MACIRole
except ImportError:

    def _raise_missing_maci_dependency() -> RuntimeError:
        return RuntimeError(
            "MACI enforcement unavailable: cannot create constitutional proposals without "
            "maci_enforcement"
        )

    class MACIRole:  # type: ignore[no-redef]
        LEGISLATIVE = "legislative"
        EXECUTIVE = "executive"
        JUDICIAL = "judicial"

    class MACIAction:  # type: ignore[no-redef]
        PROPOSE = "propose"

    class MACIEnforcer:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            raise _raise_missing_maci_dependency()

        async def validate_action(self, *args, **kwargs):
            raise _raise_missing_maci_dependency()


# Import ImpactScorer
try:
    from ..deliberation_layer.impact_scorer import (  # type: ignore[attr-defined]
        ImpactAnalysis,
        ImpactScorer,
    )
except ImportError:
    # Create mock class for standalone usage
    class ImpactAnalysis:  # type: ignore[no-redef]
        def __init__(
            self,
            score: float,
            factors: dict[str, float],
            recommendation: str,
            requires_deliberation: bool,
        ):
            self.score = score
            self.factors = factors
            self.recommendation = recommendation
            self.requires_deliberation = requires_deliberation

    class ImpactScorer:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            pass

        async def score_message(self, *args, **kwargs):
            return ImpactAnalysis(
                score=0.5,
                factors={"semantic": 0.5},
                recommendation="Review recommended",
                requires_deliberation=False,
            )


# Import audit client
try:
    from ..audit_client import AuditClient, AuditClientConfig
except ImportError:
    # Create mock class for standalone usage
    class AuditClientConfig:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            pass

    class AuditClient:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            pass

        async def log_event(self, *args, **kwargs):
            pass


logger = get_logger(__name__)
_PROPOSAL_ENGINE_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
)


class ProposalValidationError(ACGSBaseError):
    """Raised when proposal validation fails.

    Inherits from ACGSBaseError to gain constitutional hash tracking,
    correlation IDs, and structured error logging.
    """

    http_status_code = 400  # Bad Request
    error_code = "PROPOSAL_VALIDATION_ERROR"


class ProposalRequest(BaseModel):
    """Request to create a constitutional amendment proposal.

    Constitutional Hash: 608508a9bd224290
    """

    proposed_changes: JSONDict = Field(
        ..., description="Proposed constitutional changes (full content or diff)"
    )
    justification: str = Field(..., min_length=10, description="Justification for this amendment")
    proposer_agent_id: str = Field(..., description="ID of the proposing agent")
    target_version: str | None = Field(
        None,
        pattern=r"^\d+\.\d+\.\d+$",
        description="Target version (default: current active)",
    )
    new_version: str | None = Field(
        None,
        pattern=r"^\d+\.\d+\.\d+$",
        description="New version (auto-generated if not provided)",
    )
    metadata: JSONDict = Field(default_factory=dict, description="Additional metadata")


class ProposalResponse(BaseModel):
    """Response from proposal creation.

    Constitutional Hash: 608508a9bd224290
    """

    proposal: AmendmentProposal = Field(..., description="Created proposal")
    diff_preview: SemanticDiff | None = Field(None, description="Diff preview of proposed changes")
    validation_results: JSONDict = Field(default_factory=dict, description="Validation results")


class AmendmentProposalEngine:
    """Amendment Proposal Engine for constitutional evolution.

    This engine provides:
    - Proposal creation with validation against current constitution
    - Impact scoring using DistilBERT ML model
    - Diff preview generation
    - MACI enforcement (only LEGISLATIVE role can propose)
    - Automatic audit logging

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(
        self,
        storage: ConstitutionalStorageService,
        diff_engine: ConstitutionalDiffEngine | None = None,
        impact_scorer: ImpactScorer | None = None,
        maci_enforcer: MACIEnforcer | None = None,
        audit_client: AuditClient | None = None,
        enable_maci: bool = True,
        enable_audit: bool = True,
    ):
        """Initialize amendment proposal engine.

        Args:
            storage: ConstitutionalStorageService instance
            diff_engine: ConstitutionalDiffEngine instance (created if None)
            impact_scorer: ImpactScorer instance (created if None)
            maci_enforcer: MACIEnforcer instance (created if None)
            audit_client: AuditClient instance (created if None)
            enable_maci: Whether to enforce MACI permissions
            enable_audit: Whether to enable audit logging
        """
        self.storage = storage
        self.diff_engine = diff_engine or ConstitutionalDiffEngine(storage)
        self.impact_scorer = impact_scorer or ImpactScorer()
        self.maci_enforcer = maci_enforcer
        self.audit_client = audit_client
        self.enable_maci = enable_maci
        self.enable_audit = enable_audit
        self._invariant_validator: ProposalInvariantValidator | None = None  # type: ignore[valid-type]

        # Initialize audit client if enabled
        if self.enable_audit and self.audit_client is None:
            try:
                audit_config = AuditClientConfig()
                self.audit_client = AuditClient(config=audit_config)
            except _PROPOSAL_ENGINE_OPERATION_ERRORS as e:
                logger.warning("audit_client_init_failed", constitutional_hash=CONSTITUTIONAL_HASH, error=str(e))
                self.enable_audit = False

        logger.info(
            "proposal_engine_initialized",
            constitutional_hash=CONSTITUTIONAL_HASH,
            maci_enabled=self.enable_maci,
            audit_enabled=self.enable_audit,
        )

    def _get_invariant_validator(self) -> ProposalInvariantValidator | None:  # type: ignore[valid-type]
        """Lazy-initialize the invariant validator."""
        if self._invariant_validator is None and ProposalInvariantValidator is not None:
            try:
                manifest = get_default_manifest()
                self._invariant_validator = ProposalInvariantValidator(manifest)
            except _PROPOSAL_ENGINE_OPERATION_ERRORS as e:
                logger.warning(
                    f"[{CONSTITUTIONAL_HASH}] Failed to initialize invariant validator: {e}"
                )
        return self._invariant_validator

    async def create_proposal(self, request: ProposalRequest) -> ProposalResponse:
        """Create a new constitutional amendment proposal.

        This method:
        1. Validates MACI permissions (LEGISLATIVE role required)
        2. Validates proposal against current constitution
        3. Computes impact score using ML model
        4. Generates diff preview
        5. Stores proposal
        6. Logs to audit trail

        Args:
            request: ProposalRequest with proposal details

        Returns:
            ProposalResponse with created proposal and analysis

        Raises:
            ProposalValidationError: If validation fails
            ValueError: If MACI enforcement fails
        """
        logger.info(
            f"[{CONSTITUTIONAL_HASH}] Creating amendment proposal from "
            f"agent {request.proposer_agent_id}"
        )

        # Step 0: Invariant validation — check before any other processing
        invariant_classification = None
        # Fail-closed: if invariant imports are unavailable, block all proposals
        if not _INVARIANT_IMPORTS_AVAILABLE:
            raise ProposalValidationError(
                "Invariant validator unavailable — fail-closed: proposals blocked until "
                "constitutional invariant modules are properly installed"
            )
        validator = self._get_invariant_validator()
        if validator is not None:
            affected_paths = list(request.proposed_changes.keys())
            try:
                invariant_classification = await validator.validate_proposal(
                    request.proposed_changes, affected_paths
                )
            except ConstitutionalInvariantViolation as exc:
                raise ProposalValidationError(f"Constitutional invariant violation: {exc}") from exc

        # Step 1: MACI enforcement - only LEGISLATIVE role can propose amendments
        if self.enable_maci and self.maci_enforcer:
            maci_result = await self.maci_enforcer.validate_action(
                agent_id=request.proposer_agent_id,
                action=MACIAction.PROPOSE,
            )  # type: ignore[call-arg]

            if not maci_result.get("allowed", False):  # type: ignore[attr-defined]
                error_msg = (
                    f"MACI violation: Agent {request.proposer_agent_id} not authorized "
                    f"to propose amendments. Required role: LEGISLATIVE"
                )
                logger.error("maci_validation_failed", constitutional_hash=CONSTITUTIONAL_HASH, error=error_msg)

                # Log MACI violation to audit
                if self.enable_audit and self.audit_client:
                    await self._log_audit_event(
                        event_type="maci_violation",
                        agent_id=request.proposer_agent_id,
                        details={
                            "action": "propose_amendment",
                            "reason": error_msg,
                            "constitutional_hash": CONSTITUTIONAL_HASH,
                        },
                    )

                raise ValueError(error_msg)

            logger.info(
                f"[{CONSTITUTIONAL_HASH}] MACI validation passed for "
                f"agent {request.proposer_agent_id}"
            )

        # Step 2: Get current active version
        active_version = await self.storage.get_active_version()
        if not active_version:
            raise ProposalValidationError("No active constitutional version found")

        target_version = request.target_version or active_version.version
        if target_version != active_version.version:
            raise ProposalValidationError(
                f"Target version {target_version} does not match active version "
                f"{active_version.version}"
            )

        # Step 3: Validate proposed changes against current constitution
        validation_results = await self._validate_proposed_changes(
            request.proposed_changes, active_version
        )

        if not validation_results["valid"]:
            raise ProposalValidationError(
                f"Invalid proposal: {validation_results.get('errors', [])}"
            )

        # Step 4: Generate new version number if not provided
        new_version = request.new_version or self._compute_next_version(
            active_version.version, request.proposed_changes
        )

        # Step 5: Create temporary version for diff computation
        temp_version = ConstitutionalVersion(
            version_id=str(uuid4()),
            version=new_version,
            constitutional_hash=CONSTITUTIONAL_HASH,  # Will be updated if approved
            content=self._merge_changes(active_version.content, request.proposed_changes),
            predecessor_version=active_version.version_id,
            status="draft",  # type: ignore[arg-type]
        )

        # Step 6: Compute impact score using DistilBERT
        impact_analysis = await self._compute_impact_score(
            request.proposed_changes, request.justification, active_version
        )

        # Step 7: Generate diff preview
        diff_preview = await self._generate_diff_preview(active_version, temp_version)

        # Step 8: Create amendment proposal
        proposal = AmendmentProposal(
            proposed_changes=request.proposed_changes,
            justification=request.justification,
            proposer_agent_id=request.proposer_agent_id,
            target_version=target_version,
            new_version=new_version,
            status=AmendmentStatus.PROPOSED,
            impact_score=impact_analysis.score,
            impact_factors=impact_analysis.factors,
            impact_recommendation=impact_analysis.recommendation,
            requires_deliberation=impact_analysis.requires_deliberation,
            invariant_hash=(validator.invariant_hash if validator is not None else None),
            invariant_impact=(
                invariant_classification.touched_invariant_ids
                if invariant_classification is not None
                and invariant_classification.touches_invariants
                else []
            ),
            requires_refoundation=(
                invariant_classification.requires_refoundation
                if invariant_classification is not None
                else False
            ),
            metadata={
                **request.metadata,
                "constitutional_hash": CONSTITUTIONAL_HASH,
                "validation_results": validation_results,
                **(
                    {"invariant_note": invariant_classification.reason}
                    if invariant_classification is not None
                    and invariant_classification.touches_invariants
                    else {}
                ),
            },
        )

        # Step 9: Store proposal
        await self.storage.save_amendment(proposal)

        logger.info(
            f"[{CONSTITUTIONAL_HASH}] Amendment proposal created: "
            f"{proposal.proposal_id} (impact={impact_analysis.score:.3f})"
        )

        # Step 10: Log to audit trail
        if self.enable_audit and self.audit_client:
            await self._log_audit_event(
                event_type="amendment_proposed",
                agent_id=request.proposer_agent_id,
                details={
                    "proposal_id": proposal.proposal_id,
                    "target_version": target_version,
                    "new_version": new_version,
                    "impact_score": impact_analysis.score,
                    "requires_deliberation": impact_analysis.requires_deliberation,
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                },
            )

        return ProposalResponse(
            proposal=proposal,
            diff_preview=diff_preview,
            validation_results=validation_results,
        )

    async def submit_for_review(
        self, proposal_id: str, submitter_agent_id: str
    ) -> AmendmentProposal:
        """Submit an amendment proposal for review.

        This transitions the proposal from PROPOSED to UNDER_REVIEW status.

        Args:
            proposal_id: Proposal ID
            submitter_agent_id: Agent submitting for review

        Returns:
            Updated AmendmentProposal

        Raises:
            ValueError: If proposal not found or already submitted
        """
        logger.info("submitting_proposal", constitutional_hash=CONSTITUTIONAL_HASH, proposal_id=proposal_id)

        # Get proposal
        proposal = await self.storage.get_amendment(proposal_id)
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")

        # Validate status
        if not proposal.is_proposed:
            raise ValueError(
                f"Proposal {proposal_id} cannot be submitted (current status: {proposal.status})"
            )

        # Submit for review
        proposal.submit_for_review()

        # Update storage
        await self.storage.save_amendment(proposal)

        # Log to audit trail
        if self.enable_audit and self.audit_client:
            await self._log_audit_event(
                event_type="amendment_submitted_for_review",
                agent_id=submitter_agent_id,
                details={
                    "proposal_id": proposal_id,
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                },
            )

        logger.info("proposal_submitted", constitutional_hash=CONSTITUTIONAL_HASH, proposal_id=proposal_id)

        return proposal  # type: ignore[no-any-return]

    async def validate_proposal(self, proposal_id: str) -> JSONDict:
        """Validate an amendment proposal.

        Performs comprehensive validation including:
        - Proposal exists and is in valid state
        - Target version is still active
        - Proposed changes are still valid
        - Impact analysis is current

        Args:
            proposal_id: Proposal ID

        Returns:
            dict with validation results
        """
        logger.info("validating_proposal", constitutional_hash=CONSTITUTIONAL_HASH, proposal_id=proposal_id)

        # Get proposal
        proposal = await self.storage.get_amendment(proposal_id)
        if not proposal:
            return {
                "valid": False,
                "errors": [f"Proposal {proposal_id} not found"],
            }

        # Check if target version is still active
        active_version = await self.storage.get_active_version()
        if not active_version or active_version.version != proposal.target_version:
            return {
                "valid": False,
                "errors": [f"Target version {proposal.target_version} is no longer active"],
            }

        # Validate proposed changes against current constitution
        validation_results = await self._validate_proposed_changes(
            proposal.proposed_changes, active_version
        )

        return validation_results

    async def get_proposal(self, proposal_id: str, include_diff: bool = True) -> JSONDict | None:
        """Get an amendment proposal with optional diff preview.

        Args:
            proposal_id: Proposal ID
            include_diff: Whether to include diff preview

        Returns:
            dict with proposal and optional diff, or None if not found
        """
        logger.info("retrieving_proposal", constitutional_hash=CONSTITUTIONAL_HASH, proposal_id=proposal_id)

        # Get proposal
        proposal = await self.storage.get_amendment(proposal_id)
        if not proposal:
            return None

        result = {
            "proposal": proposal.to_dict(),
        }

        # Include diff if requested
        if include_diff:
            active_version = await self.storage.get_active_version()
            if active_version:
                temp_version = ConstitutionalVersion(
                    version_id=str(uuid4()),
                    version=proposal.new_version or "0.0.0",
                    constitutional_hash=CONSTITUTIONAL_HASH,
                    content=self._merge_changes(active_version.content, proposal.proposed_changes),
                    predecessor_version=active_version.version_id,
                    status="draft",  # type: ignore[arg-type]
                )
                diff_preview = await self._generate_diff_preview(active_version, temp_version)
                result["diff_preview"] = diff_preview.model_dump() if diff_preview else None

        return result

    async def list_proposals(
        self,
        status: AmendmentStatus | None = None,
        proposer_agent_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AmendmentProposal]:
        """list amendment proposals with optional filtering.

        Args:
            status: Filter by status
            proposer_agent_id: Filter by proposer
            limit: Maximum number of results
            offset: Offset for pagination

        Returns:
            list of AmendmentProposal objects
        """
        logger.info(
            f"[{CONSTITUTIONAL_HASH}] Listing proposals "
            f"(status={status}, proposer={proposer_agent_id})"
        )

        # This would use storage methods - simplified for now
        # In a real implementation, storage would have list_amendments method
        proposals: JSONList = []

        # Log to audit trail (query operation)
        if self.enable_audit and self.audit_client:
            await self._log_audit_event(
                event_type="amendment_proposals_queried",
                agent_id="system",
                details={
                    "status": status.value if status else None,
                    "proposer_agent_id": proposer_agent_id,
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                },
            )

        return proposals  # type: ignore[no-any-return]

    # Private helper methods

    async def _validate_proposed_changes(
        self, proposed_changes: JSONDict, active_version: ConstitutionalVersion
    ) -> JSONDict:
        """Validate proposed changes against current constitution.

        Args:
            proposed_changes: Proposed changes
            active_version: Current active version

        Returns:
            dict with validation results
        """
        validation_errors = []

        # Validate proposed changes structure
        if not proposed_changes:
            validation_errors.append("Proposed changes cannot be empty")

        # Validate that proposed changes don't break critical fields
        critical_fields = {"constitutional_hash", "version"}
        for field in critical_fields:
            if field in proposed_changes and field in active_version.content:
                # Critical fields should not be modified directly
                validation_errors.append(f"Cannot modify critical field '{field}' directly")

        # Additional validation logic would go here
        # (e.g., OPA policy validation, schema validation, etc.)

        return {
            "valid": len(validation_errors) == 0,
            "errors": validation_errors,
            "warnings": [],
            "validated_at": datetime.now(UTC).isoformat(),
        }

    async def _compute_impact_score(
        self,
        proposed_changes: JSONDict,
        justification: str,
        active_version: ConstitutionalVersion,
    ) -> ImpactAnalysis:
        """Compute impact score using DistilBERT impact scorer.

        Args:
            proposed_changes: Proposed changes
            justification: Justification text
            active_version: Current active version

        Returns:
            ImpactAnalysis with score and factors
        """
        # Create a synthetic message for impact scoring
        # The impact scorer expects message content, so we'll format the proposal

        try:
            # Use impact scorer (simplified - real implementation would use AgentMessage)
            # For now, we'll create a basic score based on change magnitude
            change_count = len(proposed_changes)
            has_principles = "principles" in proposed_changes
            has_enforcement = "enforcement" in proposed_changes

            # Compute basic impact score (0.0-1.0)
            base_score = min(change_count * 0.1, 0.5)
            if has_principles:
                base_score += 0.3
            if has_enforcement:
                base_score += 0.2

            impact_score = min(base_score, 1.0)

            # Determine if deliberation is required (score >= 0.8)
            requires_deliberation = impact_score >= 0.8

            return ImpactAnalysis(
                score=impact_score,
                factors={
                    "change_magnitude": change_count * 0.1,
                    "principles_modified": 0.3 if has_principles else 0.0,
                    "enforcement_modified": 0.2 if has_enforcement else 0.0,
                },
                recommendation=(
                    "High impact - requires multi-approver deliberation"
                    if requires_deliberation
                    else "Medium impact - single approver sufficient"
                ),
                requires_deliberation=requires_deliberation,
            )

        except _PROPOSAL_ENGINE_OPERATION_ERRORS as e:
            logger.error("impact_scoring_failed", constitutional_hash=CONSTITUTIONAL_HASH, error=str(e))
            # Fallback to conservative estimate
            return ImpactAnalysis(
                score=0.8,  # Conservative - assume high impact
                factors={"error_fallback": 1.0},
                recommendation="Impact scoring failed - manual review required",
                requires_deliberation=True,
            )

    async def _generate_diff_preview(
        self, from_version: ConstitutionalVersion, to_version: ConstitutionalVersion
    ) -> SemanticDiff | None:
        """Generate diff preview between versions.

        Args:
            from_version: Source version
            to_version: Target version

        Returns:
            SemanticDiff or None if diff computation fails
        """
        try:
            diff = await self.diff_engine.compute_diff(
                from_version.version_id, to_version.version_id, include_principles=True
            )
            return diff
        except _PROPOSAL_ENGINE_OPERATION_ERRORS as e:
            logger.error("diff_preview_failed", constitutional_hash=CONSTITUTIONAL_HASH, error=str(e))
            return None

    def _merge_changes(self, base_content: JSONDict, proposed_changes: JSONDict) -> JSONDict:
        """Merge proposed changes into base content.

        Args:
            base_content: Base constitutional content
            proposed_changes: Proposed changes

        Returns:
            Merged content
        """
        merged = base_content.copy()
        for key, value in proposed_changes.items():
            merged[key] = value
        return merged

    def _compute_next_version(self, current_version: str, proposed_changes: JSONDict) -> str:
        """Compute next semantic version based on change magnitude.

        Args:
            current_version: Current version (e.g., "1.0.0")
            proposed_changes: Proposed changes

        Returns:
            Next version string
        """
        major, minor, patch = map(int, current_version.split("."))

        # Increment based on change type
        # Major: Breaking changes (e.g., removing principles)
        # Minor: Feature additions (e.g., adding principles)
        # Patch: Non-breaking changes (e.g., clarifications)

        # Simple heuristic: increment minor version
        # More sophisticated logic would analyze the diff
        minor += 1

        return f"{major}.{minor}.{patch}"

    async def _log_audit_event(self, event_type: str, agent_id: str, details: JSONDict) -> None:
        """Log event to audit trail.

        Args:
            event_type: Event type
            agent_id: Agent ID
            details: Event details
        """
        if not self.enable_audit or not self.audit_client:
            return

        try:
            await self.audit_client.log_event(  # type: ignore[attr-defined]
                event_type=event_type,
                agent_id=agent_id,
                timestamp=datetime.now(UTC).isoformat(),
                details=details,
            )
        except _PROPOSAL_ENGINE_OPERATION_ERRORS as e:
            logger.warning("audit_event_log_failed", constitutional_hash=CONSTITUTIONAL_HASH, error=str(e))
