"""
Constitutional Gap Analysis Module
Constitutional Hash: 608508a9bd224290

Phase 10 Task 10: Constitutional Gap Analysis

Provides:
- Legacy policy scanning for compliance gaps
- Gap severity scoring (critical, high, medium, low)
- Remediation recommendation generation with code snippets
- Gap closure tracking dashboard
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from enum import Enum
from typing import ClassVar, cast

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

# ============================================================================
# Enums
# ============================================================================


class GapSeverity(Enum):
    """Severity levels for constitutional gaps."""

    CRITICAL = "critical"  # Immediate action required
    HIGH = "high"  # High priority
    MEDIUM = "medium"  # Should be addressed
    LOW = "low"  # Nice to have
    INFO = "info"  # Informational only


class GapCategory(Enum):
    """Categories of constitutional gaps."""

    MISSING_HASH = "missing_hash"  # No constitutional hash
    INVALID_HASH = "invalid_hash"  # Wrong constitutional hash
    MISSING_AUDIT = "missing_audit"  # No audit trail
    MISSING_VALIDATION = "missing_validation"  # No input validation
    PERMISSION_LEAK = "permission_leak"  # Overly permissive
    NO_MACI_ROLE = "no_maci_role"  # Missing MACI role check
    SELF_VALIDATION = "self_validation"  # Agent validates own output
    NO_CONSTITUTIONAL_CHECK = "no_constitutional_check"  # No constitutional compliance
    INSECURE_DEFAULT = "insecure_default"  # Default allows too much


class GapStatus(Enum):
    """Status of a gap remediation."""

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    WONT_FIX = "wont_fix"
    FALSE_POSITIVE = "false_positive"


class RemediationType(Enum):
    """Type of remediation action."""

    ADD_CODE = "add_code"
    MODIFY_CODE = "modify_code"
    ADD_POLICY = "add_policy"
    CONFIGURATION = "configuration"
    MANUAL_REVIEW = "manual_review"


# ============================================================================
# Data Classes
# ============================================================================


@dataclass
class PolicyLocation:
    """Location of a policy or code that was scanned."""

    file_path: str
    line_number: int | None = None
    column_number: int | None = None
    policy_name: str | None = None


@dataclass
class ConstitutionalGap:
    """A gap in constitutional compliance."""

    gap_id: str
    category: GapCategory
    severity: GapSeverity
    location: PolicyLocation
    description: str
    detected_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    status: GapStatus = GapStatus.OPEN
    assigned_to: str | None = None
    resolution_notes: str | None = None
    resolved_at: datetime | None = None
    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass
class RemediationSuggestion:
    """Suggested remediation for a gap."""

    suggestion_id: str
    gap_id: str
    remediation_type: RemediationType
    title: str
    description: str
    code_snippet: str | None = None
    priority: int = 1
    effort_estimate: str = "low"  # low, medium, high
    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass
class ScanResult:
    """Result of a policy scan."""

    scan_id: str
    tenant_id: str
    policies_scanned: int = 0
    gaps_found: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    info_count: int = 0
    gaps: list = field(default_factory=list)
    scan_start: datetime | None = None
    scan_end: datetime | None = None
    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass
class GapTrackingDashboard:
    """Dashboard data for gap closure tracking."""

    tenant_id: str
    total_gaps: int = 0
    open_gaps: int = 0
    in_progress_gaps: int = 0
    resolved_gaps: int = 0
    closure_rate: float = 0.0
    mean_time_to_resolution_hours: float = 0.0
    gaps_by_severity: dict = field(default_factory=dict)
    gaps_by_category: dict = field(default_factory=dict)
    last_updated: datetime = field(default_factory=lambda: datetime.now(UTC))
    constitutional_hash: str = CONSTITUTIONAL_HASH


# ============================================================================
# Implementation Classes
# ============================================================================


class ConstitutionalPolicyScanner:
    """Scans policies for constitutional compliance gaps."""

    CONSTITUTIONAL_RULES: ClassVar[dict] = {
        "require_hash": {
            "description": "All policies must include constitutional hash",
            "severity": GapSeverity.CRITICAL,
            "category": GapCategory.MISSING_HASH,
        },
        "valid_hash": {
            "description": "Constitutional hash must match system hash",
            "severity": GapSeverity.CRITICAL,
            "category": GapCategory.INVALID_HASH,
        },
        "no_self_validation": {
            "description": "Agents must not validate their own outputs",
            "severity": GapSeverity.CRITICAL,
            "category": GapCategory.SELF_VALIDATION,
        },
        "require_audit": {
            "description": "All decisions must be auditable",
            "severity": GapSeverity.HIGH,
            "category": GapCategory.MISSING_AUDIT,
        },
        "require_maci_role": {
            "description": "All agent actions must have MACI role checks",
            "severity": GapSeverity.HIGH,
            "category": GapCategory.NO_MACI_ROLE,
        },
        "no_insecure_defaults": {
            "description": "Default policies must be deny-by-default",
            "severity": GapSeverity.MEDIUM,
            "category": GapCategory.INSECURE_DEFAULT,
        },
        "require_validation": {
            "description": "All inputs must be validated",
            "severity": GapSeverity.MEDIUM,
            "category": GapCategory.MISSING_VALIDATION,
        },
    }

    def __init__(self, constitutional_hash: str = CONSTITUTIONAL_HASH):
        self.constitutional_hash = constitutional_hash
        self._scans: dict[str, ScanResult] = {}

    def scan_policy(
        self, policy_content: str, file_path: str, tenant_id: str
    ) -> list[ConstitutionalGap]:
        """Scan a single policy for constitutional gaps."""
        gaps = []

        # Check for constitutional hash
        if "constitutional_hash" not in policy_content.lower():
            gaps.append(
                ConstitutionalGap(
                    gap_id=str(uuid.uuid4()),
                    category=GapCategory.MISSING_HASH,
                    severity=GapSeverity.CRITICAL,
                    location=PolicyLocation(file_path=file_path, policy_name=file_path),
                    description="Policy does not include constitutional hash validation",
                )
            )
        elif self.constitutional_hash not in policy_content:
            # Has a hash reference but might be wrong
            if "cdd01ef" not in policy_content:  # Partial match check
                gaps.append(
                    ConstitutionalGap(
                        gap_id=str(uuid.uuid4()),
                        category=GapCategory.INVALID_HASH,
                        severity=GapSeverity.CRITICAL,
                        location=PolicyLocation(file_path=file_path),
                        description="Policy has incorrect constitutional hash",
                    )
                )

        # Check for self-validation patterns
        if "validate_self" in policy_content.lower() or "self.validate" in policy_content:
            gaps.append(
                ConstitutionalGap(
                    gap_id=str(uuid.uuid4()),
                    category=GapCategory.SELF_VALIDATION,
                    severity=GapSeverity.CRITICAL,
                    location=PolicyLocation(file_path=file_path),
                    description="Policy allows self-validation which violates separation of powers",
                )
            )

        # Check for audit requirements
        if "audit" not in policy_content.lower() and "log" not in policy_content.lower():
            gaps.append(
                ConstitutionalGap(
                    gap_id=str(uuid.uuid4()),
                    category=GapCategory.MISSING_AUDIT,
                    severity=GapSeverity.HIGH,
                    location=PolicyLocation(file_path=file_path),
                    description="Policy does not include audit trail requirements",
                )
            )

        # Check for MACI role checks
        if "maci" not in policy_content.lower() and "role" not in policy_content.lower():
            gaps.append(
                ConstitutionalGap(
                    gap_id=str(uuid.uuid4()),
                    category=GapCategory.NO_MACI_ROLE,
                    severity=GapSeverity.HIGH,
                    location=PolicyLocation(file_path=file_path),
                    description="Policy does not include MACI role validation",
                )
            )

        # Check for insecure defaults
        if "default allow" in policy_content.lower() or 'default: "allow"' in policy_content:
            gaps.append(
                ConstitutionalGap(
                    gap_id=str(uuid.uuid4()),
                    category=GapCategory.INSECURE_DEFAULT,
                    severity=GapSeverity.MEDIUM,
                    location=PolicyLocation(file_path=file_path),
                    description="Policy uses insecure default-allow pattern",
                )
            )

        # Check for input validation
        if "validate" not in policy_content.lower() and "check" not in policy_content.lower():
            gaps.append(
                ConstitutionalGap(
                    gap_id=str(uuid.uuid4()),
                    category=GapCategory.MISSING_VALIDATION,
                    severity=GapSeverity.MEDIUM,
                    location=PolicyLocation(file_path=file_path),
                    description="Policy does not include input validation",
                )
            )

        return gaps

    def scan_policies_batch(
        self,
        policies: list[tuple[str, str]],  # (content, file_path)
        tenant_id: str,
    ) -> ScanResult:
        """Scan multiple policies and aggregate results."""
        scan_id = str(uuid.uuid4())
        result = ScanResult(scan_id=scan_id, tenant_id=tenant_id, scan_start=datetime.now(UTC))

        all_gaps = []
        for content, file_path in policies:
            result.policies_scanned += 1
            gaps = self.scan_policy(content, file_path, tenant_id)
            all_gaps.extend(gaps)

        result.gaps = all_gaps
        result.gaps_found = len(all_gaps)

        # Count by severity
        for gap in all_gaps:
            if gap.severity == GapSeverity.CRITICAL:
                result.critical_count += 1
            elif gap.severity == GapSeverity.HIGH:
                result.high_count += 1
            elif gap.severity == GapSeverity.MEDIUM:
                result.medium_count += 1
            elif gap.severity == GapSeverity.LOW:
                result.low_count += 1
            else:
                result.info_count += 1

        result.scan_end = datetime.now(UTC)
        self._scans[scan_id] = result
        return result

    def get_scan_result(self, scan_id: str) -> ScanResult | None:
        """Get a scan result by ID."""
        return self._scans.get(scan_id)


class GapClassifier:
    """Classifies and prioritizes constitutional gaps."""

    SEVERITY_WEIGHTS: ClassVar[dict] = {
        GapSeverity.CRITICAL: 100,
        GapSeverity.HIGH: 75,
        GapSeverity.MEDIUM: 50,
        GapSeverity.LOW: 25,
        GapSeverity.INFO: 10,
    }

    CATEGORY_MULTIPLIERS: ClassVar[dict] = {
        GapCategory.SELF_VALIDATION: 2.0,  # Most dangerous
        GapCategory.INVALID_HASH: 1.8,
        GapCategory.MISSING_HASH: 1.5,
        GapCategory.PERMISSION_LEAK: 1.5,
        GapCategory.NO_MACI_ROLE: 1.3,
        GapCategory.MISSING_AUDIT: 1.2,
        GapCategory.INSECURE_DEFAULT: 1.1,
        GapCategory.MISSING_VALIDATION: 1.0,
        GapCategory.NO_CONSTITUTIONAL_CHECK: 1.0,
    }

    def __init__(self, constitutional_hash: str = CONSTITUTIONAL_HASH):
        self.constitutional_hash = constitutional_hash

    def calculate_priority_score(self, gap: ConstitutionalGap) -> float:
        """Calculate a priority score for a gap."""
        base_score = self.SEVERITY_WEIGHTS.get(gap.severity, 10)
        multiplier = self.CATEGORY_MULTIPLIERS.get(gap.category, 1.0)
        return base_score * multiplier  # type: ignore[no-any-return]

    def prioritize_gaps(self, gaps: list[ConstitutionalGap]) -> list[ConstitutionalGap]:
        """Sort gaps by priority score (highest first)."""
        scored_gaps = [(gap, self.calculate_priority_score(gap)) for gap in gaps]
        scored_gaps.sort(key=lambda x: x[1], reverse=True)
        return [gap for gap, _ in scored_gaps]

    def get_severity_for_category(self, category: GapCategory) -> GapSeverity:
        """Get the default severity for a gap category."""
        severity_map = {
            GapCategory.MISSING_HASH: GapSeverity.CRITICAL,
            GapCategory.INVALID_HASH: GapSeverity.CRITICAL,
            GapCategory.SELF_VALIDATION: GapSeverity.CRITICAL,
            GapCategory.MISSING_AUDIT: GapSeverity.HIGH,
            GapCategory.NO_MACI_ROLE: GapSeverity.HIGH,
            GapCategory.PERMISSION_LEAK: GapSeverity.HIGH,
            GapCategory.INSECURE_DEFAULT: GapSeverity.MEDIUM,
            GapCategory.MISSING_VALIDATION: GapSeverity.MEDIUM,
            GapCategory.NO_CONSTITUTIONAL_CHECK: GapSeverity.MEDIUM,
        }
        return severity_map.get(category, GapSeverity.LOW)


class RemediationEngine:
    """Generates remediation suggestions for gaps."""

    REMEDIATION_TEMPLATES: ClassVar[dict] = {
        GapCategory.MISSING_HASH: {
            "title": "Add Constitutional Hash Validation",
            "type": RemediationType.ADD_CODE,
            "effort": "low",
            "snippet": '''CONSTITUTIONAL_HASH = CONSTITUTIONAL_HASH

def validate_constitutional_compliance(action: dict) -> bool:
    """Validate action against constitutional principles."""
    return action.get("constitutional_hash") == CONSTITUTIONAL_HASH''',
        },
        GapCategory.INVALID_HASH: {
            "title": "Fix Constitutional Hash",
            "type": RemediationType.MODIFY_CODE,
            "effort": "low",
            "snippet": """# Replace incorrect hash with valid constitutional hash
from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH  # Valid ACGS-2 hash""",
        },
        GapCategory.SELF_VALIDATION: {
            "title": "Implement Separation of Powers",
            "type": RemediationType.MODIFY_CODE,
            "effort": "high",
            "snippet": '''# Remove self-validation and implement cross-agent validation
async def validate_output(output_id: str, validator_agent_id: str) -> bool:
    """Outputs must be validated by a different agent with JUDICIAL role."""
    if validator_agent_id == self.agent_id:
        raise PermissionError("Self-validation is not allowed")
    return await judicial_agent.validate(output_id)''',
        },
        GapCategory.MISSING_AUDIT: {
            "title": "Add Audit Trail",
            "type": RemediationType.ADD_CODE,
            "effort": "medium",
            "snippet": '''from audit_service import AuditClient

audit = AuditClient()

async def log_decision(action: str, result: str, context: dict) -> None:
    """Log decision to audit trail."""
    await audit.log_event(
        event_type="DECISION",
        action=action,
        result=result,
        context=context,
        constitutional_hash=CONSTITUTIONAL_HASH
    )''',
        },
        GapCategory.NO_MACI_ROLE: {
            "title": "Add MACI Role Validation",
            "type": RemediationType.ADD_CODE,
            "effort": "medium",
            "snippet": '''from maci_enforcement import MACIEnforcer, MACIRole, MACIAction

enforcer = MACIEnforcer()

async def validate_maci_permission(agent_id: str, action: MACIAction) -> bool:
    """Validate agent has MACI permission for action."""
    result = await enforcer.validate_action(
        agent_id=agent_id,
        action=action,
        constitutional_hash=CONSTITUTIONAL_HASH
    )
    return result.is_permitted''',
        },
        GapCategory.INSECURE_DEFAULT: {
            "title": "Change to Deny-by-Default",
            "type": RemediationType.MODIFY_CODE,
            "effort": "low",
            "snippet": '''# Use deny-by-default pattern
default_decision = "deny"

def evaluate_policy(action: str, resource: str, context: dict) -> str:
    """Evaluate policy with deny-by-default."""
    if not _is_explicitly_allowed(action, resource, context):
        return "deny"
    return "allow"''',
        },
        GapCategory.MISSING_VALIDATION: {
            "title": "Add Input Validation",
            "type": RemediationType.ADD_CODE,
            "effort": "medium",
            "snippet": """from pydantic import BaseModel, validator

class PolicyInput(BaseModel):
    action: str
    resource: str
    actor: str

    @validator("action")
    def validate_action(cls, v):
        allowed_actions = {"read", "write", "delete", "admin"}
        if v not in allowed_actions:
            raise ValueError(f"Invalid action: {v}")
        return v""",
        },
    }

    def __init__(self, constitutional_hash: str = CONSTITUTIONAL_HASH):
        self.constitutional_hash = constitutional_hash

    def generate_suggestion(self, gap: ConstitutionalGap) -> RemediationSuggestion:
        """Generate a remediation suggestion for a gap."""
        template = self.REMEDIATION_TEMPLATES.get(gap.category)

        if not template:
            return RemediationSuggestion(
                suggestion_id=str(uuid.uuid4()),
                gap_id=gap.gap_id,
                remediation_type=RemediationType.MANUAL_REVIEW,
                title="Manual Review Required",
                description=f"No automated remediation available for {gap.category.value}",
                priority=5,
                effort_estimate="unknown",
                constitutional_hash=self.constitutional_hash,
            )

        return RemediationSuggestion(
            suggestion_id=str(uuid.uuid4()),
            gap_id=gap.gap_id,
            remediation_type=cast(RemediationType, template["type"]),
            title=str(template["title"]),
            description=f"Remediation for: {gap.description}",
            code_snippet=str(template.get("snippet", "")),
            priority=1,
            effort_estimate=str(template.get("effort", "medium")),
            constitutional_hash=self.constitutional_hash,
        )

    def generate_batch_suggestions(
        self, gaps: list[ConstitutionalGap]
    ) -> list[RemediationSuggestion]:
        """Generate suggestions for multiple gaps."""
        return [self.generate_suggestion(gap) for gap in gaps]


class GapTracker:
    """Tracks gap status and closure metrics."""

    def __init__(self, constitutional_hash: str = CONSTITUTIONAL_HASH):
        self.constitutional_hash = constitutional_hash
        self._gaps: dict[str, ConstitutionalGap] = {}
        self._resolution_times: list[float] = []

    def register_gap(self, gap: ConstitutionalGap) -> None:
        """Register a new gap for tracking."""
        self._gaps[gap.gap_id] = gap

    def register_gaps(self, gaps: list[ConstitutionalGap]) -> None:
        """Register multiple gaps."""
        for gap in gaps:
            self.register_gap(gap)

    def update_status(
        self,
        gap_id: str,
        new_status: GapStatus,
        notes: str | None = None,
        assigned_to: str | None = None,
    ) -> ConstitutionalGap | None:
        """Update the status of a gap."""
        gap = self._gaps.get(gap_id)
        if not gap:
            return None

        gap.status = new_status
        if notes:
            gap.resolution_notes = notes
        if assigned_to:
            gap.assigned_to = assigned_to

        if new_status == GapStatus.RESOLVED:
            gap.resolved_at = datetime.now(UTC)
            resolution_time = (gap.resolved_at - gap.detected_at).total_seconds() / 3600
            self._resolution_times.append(resolution_time)

        return gap

    def get_gap(self, gap_id: str) -> ConstitutionalGap | None:
        """Get a gap by ID."""
        return self._gaps.get(gap_id)

    def get_gaps_by_status(self, status: GapStatus) -> list[ConstitutionalGap]:
        """Get all gaps with a specific status."""
        return [g for g in self._gaps.values() if g.status == status]

    def get_gaps_by_severity(self, severity: GapSeverity) -> list[ConstitutionalGap]:
        """Get all gaps with a specific severity."""
        return [g for g in self._gaps.values() if g.severity == severity]

    def get_dashboard(self, tenant_id: str) -> GapTrackingDashboard:
        """Get dashboard data for gap tracking."""
        all_gaps = list(self._gaps.values())

        open_count = sum(1 for g in all_gaps if g.status == GapStatus.OPEN)
        in_progress_count = sum(1 for g in all_gaps if g.status == GapStatus.IN_PROGRESS)
        resolved_count = sum(1 for g in all_gaps if g.status == GapStatus.RESOLVED)

        total = len(all_gaps)
        closure_rate = (resolved_count / total * 100) if total > 0 else 0.0
        mttr = (
            sum(self._resolution_times) / len(self._resolution_times)
            if self._resolution_times
            else 0.0
        )

        # Count by severity
        by_severity = {}
        for severity in GapSeverity:
            count = sum(1 for g in all_gaps if g.severity == severity)
            if count > 0:
                by_severity[severity.value] = count

        # Count by category
        by_category = {}
        for category in GapCategory:
            count = sum(1 for g in all_gaps if g.category == category)
            if count > 0:
                by_category[category.value] = count

        return GapTrackingDashboard(
            tenant_id=tenant_id,
            total_gaps=total,
            open_gaps=open_count,
            in_progress_gaps=in_progress_count,
            resolved_gaps=resolved_count,
            closure_rate=closure_rate,
            mean_time_to_resolution_hours=mttr,
            gaps_by_severity=by_severity,
            gaps_by_category=by_category,
            constitutional_hash=self.constitutional_hash,
        )
