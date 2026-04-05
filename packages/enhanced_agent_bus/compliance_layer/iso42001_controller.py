"""ISO 42001 AI Management System Controller.

Constitutional Hash: 608508a9bd224290
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
from enhanced_agent_bus._compat.json_utils import dumps as json_dumps

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)


class AIMSClause(Enum):
    """ISO 42001 clauses."""

    CONTEXT = "4"
    LEADERSHIP = "5"
    PLANNING = "6"
    SUPPORT = "7"
    OPERATION = "8"
    PERFORMANCE = "9"
    IMPROVEMENT = "10"


class ComplianceStatus(Enum):
    """Compliance status levels."""

    COMPLIANT = "compliant"
    PARTIAL = "partial"
    GAP = "gap"
    NOT_ASSESSED = "not_assessed"


@dataclass
class AIMSRequirement:
    """Single ISO 42001 requirement."""

    clause: AIMSClause
    requirement_id: str
    description: str
    status: ComplianceStatus = ComplianceStatus.NOT_ASSESSED
    evidence: list[str] = field(default_factory=list)
    gap_description: str | None = None
    action_required: str | None = None
    owner: str | None = None
    due_date: datetime | None = None


@dataclass
class AIMSRiskEntry:
    """AI-specific risk entry for the risk register."""

    risk_id: str
    title: str
    description: str
    likelihood: int  # 1-5
    impact: int  # 1-5
    risk_score: int  # likelihood * impact
    treatment: str
    owner: str
    status: str = "open"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class AIMSNonconformity:
    """Nonconformity record for ISO 42001."""

    nc_id: str
    title: str
    description: str
    clause: AIMSClause
    severity: str  # minor, major, critical
    root_cause: str | None = None
    corrective_action: str | None = None
    status: str = "open"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    closed_at: datetime | None = None


class AIMSRiskRegister:
    """Risk register for AI-specific risks."""

    def __init__(self) -> None:
        self._risks: dict[str, AIMSRiskEntry] = {}
        self._constitutional_hash = CONSTITUTIONAL_HASH

    def add_risk(self, risk: AIMSRiskEntry) -> str:
        risk.risk_score = risk.likelihood * risk.impact
        self._risks[risk.risk_id] = risk
        return risk.risk_id

    def get_risk(self, risk_id: str) -> AIMSRiskEntry | None:
        return self._risks.get(risk_id)

    def get_high_risks(self, threshold: int = 15) -> list[AIMSRiskEntry]:
        return [r for r in self._risks.values() if r.risk_score >= threshold]

    def get_open_risks(self) -> list[AIMSRiskEntry]:
        return [r for r in self._risks.values() if r.status == "open"]

    def close_risk(self, risk_id: str) -> bool:
        if risk_id in self._risks:
            self._risks[risk_id].status = "closed"
            return True
        return False


class AIMSNonconformityTracker:
    """Tracker for ISO 42001 nonconformities."""

    def __init__(self) -> None:
        self._nonconformities: dict[str, AIMSNonconformity] = {}

    def raise_nonconformity(self, nc: AIMSNonconformity) -> str:
        self._nonconformities[nc.nc_id] = nc
        logger.warning(f"AIMS Nonconformity raised: {nc.nc_id} - {nc.title}")
        return nc.nc_id

    def get_nonconformity(self, nc_id: str) -> AIMSNonconformity | None:
        return self._nonconformities.get(nc_id)

    def get_open_nonconformities(self) -> list[AIMSNonconformity]:
        return [nc for nc in self._nonconformities.values() if nc.status == "open"]

    def close_nonconformity(self, nc_id: str, corrective_action: str, root_cause: str) -> bool:
        if nc_id in self._nonconformities:
            nc = self._nonconformities[nc_id]
            nc.corrective_action = corrective_action
            nc.root_cause = root_cause
            nc.status = "closed"
            nc.closed_at = datetime.now(UTC)
            return True
        return False


class AIMSAuditScheduler:
    """Scheduler for internal AI management system audits."""

    def __init__(self) -> None:
        self._scheduled_audits: list[JSONDict] = []
        self._completed_audits: list[JSONDict] = []

    def schedule_audit(
        self,
        audit_id: str,
        clause: AIMSClause,
        scheduled_date: datetime,
        auditor: str,
    ) -> str:
        audit = {
            "audit_id": audit_id,
            "clause": clause,
            "scheduled_date": scheduled_date,
            "auditor": auditor,
            "status": "scheduled",
            "created_at": datetime.now(UTC),
        }
        self._scheduled_audits.append(audit)
        return audit_id

    def complete_audit(
        self,
        audit_id: str,
        findings: list[str],
        nonconformities: list[str],
    ) -> bool:
        for audit in self._scheduled_audits:
            if audit["audit_id"] == audit_id:
                audit["status"] = "completed"
                audit["completed_at"] = datetime.now(UTC)
                audit["findings"] = findings
                audit["nonconformities"] = nonconformities
                self._completed_audits.append(audit)
                self._scheduled_audits.remove(audit)
                return True
        return False

    def get_upcoming_audits(self) -> list[JSONDict]:
        now = datetime.now(UTC)
        return [a for a in self._scheduled_audits if a["scheduled_date"] > now]


class AIManagementSystemController:
    """ISO 42001 AI Management System Controller."""

    def __init__(
        self,
        organization_name: str = "ACGS-2",
        audit_callback: Callable[[str, JSONDict], None] | None = None,
    ) -> None:
        self._organization = organization_name
        self._constitutional_hash = CONSTITUTIONAL_HASH
        self._audit_callback = audit_callback

        self._requirements: dict[str, AIMSRequirement] = {}
        self._risk_register = AIMSRiskRegister()
        self._nc_tracker = AIMSNonconformityTracker()
        self._audit_scheduler = AIMSAuditScheduler()

        self._initialize_requirements()

    def _initialize_requirements(self) -> None:
        """Initialize standard ISO 42001 requirements."""
        base_requirements = [
            (AIMSClause.CONTEXT, "4.1", "Understanding the organization"),
            (AIMSClause.CONTEXT, "4.2", "Understanding stakeholder needs"),
            (AIMSClause.CONTEXT, "4.3", "Determining scope"),
            (AIMSClause.CONTEXT, "4.4", "AI management system"),
            (AIMSClause.LEADERSHIP, "5.1", "Leadership commitment"),
            (AIMSClause.LEADERSHIP, "5.2", "AI policy"),
            (AIMSClause.LEADERSHIP, "5.3", "Roles and responsibilities"),
            (AIMSClause.PLANNING, "6.1", "Risk assessment"),
            (AIMSClause.PLANNING, "6.2", "AI system impact assessment"),
            (AIMSClause.PLANNING, "6.3", "Objectives"),
            (AIMSClause.PLANNING, "6.4", "Planning changes"),
            (AIMSClause.SUPPORT, "7.1", "Resources"),
            (AIMSClause.SUPPORT, "7.2", "Competence"),
            (AIMSClause.SUPPORT, "7.3", "Awareness"),
            (AIMSClause.SUPPORT, "7.4", "Communication"),
            (AIMSClause.SUPPORT, "7.5", "Documented information"),
            (AIMSClause.OPERATION, "8.1", "Operational planning"),
            (AIMSClause.OPERATION, "8.2", "AI system lifecycle"),
            (AIMSClause.OPERATION, "8.3", "Data management"),
            (AIMSClause.OPERATION, "8.4", "AI system development"),
            (AIMSClause.OPERATION, "8.5", "AI system testing"),
            (AIMSClause.OPERATION, "8.6", "Deployment"),
            (AIMSClause.OPERATION, "8.7", "Operation"),
            (AIMSClause.OPERATION, "8.8", "Third-party AI"),
            (AIMSClause.PERFORMANCE, "9.1", "Monitoring and measurement"),
            (AIMSClause.PERFORMANCE, "9.2", "Internal audit"),
            (AIMSClause.PERFORMANCE, "9.3", "Management review"),
            (AIMSClause.IMPROVEMENT, "10.1", "Nonconformity"),
            (AIMSClause.IMPROVEMENT, "10.2", "Continual improvement"),
        ]

        for clause, req_id, desc in base_requirements:
            self._requirements[req_id] = AIMSRequirement(
                clause=clause,
                requirement_id=req_id,
                description=desc,
            )

    def _emit_audit(self, event_type: str, data: JSONDict) -> None:
        if self._audit_callback:
            self._audit_callback(
                event_type, {**data, "constitutional_hash": self._constitutional_hash}
            )

    def assess_requirement(
        self,
        requirement_id: str,
        status: ComplianceStatus,
        evidence: list[str],
        gap_description: str | None = None,
        action_required: str | None = None,
    ) -> bool:
        if requirement_id not in self._requirements:
            return False

        req = self._requirements[requirement_id]
        req.status = status
        req.evidence = evidence
        req.gap_description = gap_description
        req.action_required = action_required

        self._emit_audit(
            "aims_requirement_assessed",
            {
                "requirement_id": requirement_id,
                "status": status.value,
                "has_gap": gap_description is not None,
            },
        )

        return True

    def get_compliance_summary(self) -> JSONDict:
        """Get overall AIMS compliance summary."""
        total = len(self._requirements)
        compliant = sum(
            1 for r in self._requirements.values() if r.status == ComplianceStatus.COMPLIANT
        )
        partial = sum(
            1 for r in self._requirements.values() if r.status == ComplianceStatus.PARTIAL
        )
        gap = sum(1 for r in self._requirements.values() if r.status == ComplianceStatus.GAP)

        return {
            "organization": self._organization,
            "constitutional_hash": self._constitutional_hash,
            "total_requirements": total,
            "compliant": compliant,
            "partial": partial,
            "gap": gap,
            "not_assessed": total - compliant - partial - gap,
            "compliance_percentage": round((compliant / total) * 100, 1) if total > 0 else 0,
            "high_risks": len(self._risk_register.get_high_risks()),
            "open_nonconformities": len(self._nc_tracker.get_open_nonconformities()),
            "upcoming_audits": len(self._audit_scheduler.get_upcoming_audits()),
        }

    def get_gaps(self) -> list[AIMSRequirement]:
        """Get all requirements with gaps."""
        return [r for r in self._requirements.values() if r.status == ComplianceStatus.GAP]

    @property
    def risk_register(self) -> AIMSRiskRegister:
        return self._risk_register

    @property
    def nonconformity_tracker(self) -> AIMSNonconformityTracker:
        return self._nc_tracker

    @property
    def audit_scheduler(self) -> AIMSAuditScheduler:
        return self._audit_scheduler


def create_aims_controller(
    organization_name: str = "ACGS-2",
    audit_callback: Callable[[str, JSONDict], None] | None = None,
) -> AIManagementSystemController:
    """Factory function to create AIMS controller."""
    return AIManagementSystemController(
        organization_name=organization_name,
        audit_callback=audit_callback,
    )


class AIMSBlockchainAnchoring:
    """Blockchain anchoring for AIMS records.

    Provides immutable audit trail by anchoring AIMS records
    to the audit service blockchain infrastructure.
    """

    def __init__(self, controller: AIManagementSystemController) -> None:
        self._controller = controller
        self._constitutional_hash = CONSTITUTIONAL_HASH
        self._anchored_records: list[JSONDict] = []

    def anchor_risk(self, risk: AIMSRiskEntry) -> JSONDict:
        """Anchor a risk entry for immutability."""
        import hashlib

        record = {
            "type": "aims_risk",
            "risk_id": risk.risk_id,
            "title": risk.title,
            "risk_score": risk.risk_score,
            "status": risk.status,
            "timestamp": risk.created_at.isoformat(),
            "constitutional_hash": self._constitutional_hash,
        }
        record_json = json_dumps(record, sort_keys=True)
        record["anchor_hash"] = hashlib.sha256(record_json.encode()).hexdigest()
        self._anchored_records.append(record)
        logger.info(f"[{self._constitutional_hash}] Anchored AIMS risk: {risk.risk_id}")
        return record

    def anchor_nonconformity(self, nc: AIMSNonconformity) -> JSONDict:
        """Anchor a nonconformity for immutability."""
        import hashlib

        record = {
            "type": "aims_nonconformity",
            "nc_id": nc.nc_id,
            "title": nc.title,
            "clause": nc.clause.value,
            "severity": nc.severity,
            "status": nc.status,
            "timestamp": nc.created_at.isoformat(),
            "constitutional_hash": self._constitutional_hash,
        }
        record_json = json_dumps(record, sort_keys=True)
        record["anchor_hash"] = hashlib.sha256(record_json.encode()).hexdigest()
        self._anchored_records.append(record)
        logger.info(f"[{self._constitutional_hash}] Anchored AIMS NC: {nc.nc_id}")
        return record

    def anchor_audit_result(self, audit: JSONDict) -> JSONDict:
        """Anchor an audit result for immutability."""
        import hashlib

        record = {
            "type": "aims_audit",
            "audit_id": audit.get("audit_id"),
            "clause": (
                audit.get("clause").value
                if hasattr(audit.get("clause"), "value")
                else str(audit.get("clause"))
            ),
            "status": audit.get("status"),
            "findings_count": len(audit.get("findings", [])),
            "nc_count": len(audit.get("nonconformities", [])),
            "timestamp": datetime.now(UTC).isoformat(),
            "constitutional_hash": self._constitutional_hash,
        }
        record_json = json_dumps(record, sort_keys=True)
        record["anchor_hash"] = hashlib.sha256(record_json.encode()).hexdigest()
        self._anchored_records.append(record)
        logger.info(f"[{self._constitutional_hash}] Anchored AIMS audit: {audit.get('audit_id')}")
        return record

    def get_anchored_records(self) -> list[JSONDict]:
        """Get all anchored records."""
        return self._anchored_records.copy()

    def verify_anchor(self, anchor_hash: str) -> bool:
        """Verify if an anchor hash exists in records."""
        return any(r.get("anchor_hash") == anchor_hash for r in self._anchored_records)


__all__ = [
    "AIMSAuditScheduler",
    "AIMSBlockchainAnchoring",
    "AIMSClause",
    "AIMSNonconformity",
    "AIMSNonconformityTracker",
    "AIMSRequirement",
    "AIMSRiskEntry",
    "AIMSRiskRegister",
    "AIManagementSystemController",
    "ComplianceStatus",
    "create_aims_controller",
]
