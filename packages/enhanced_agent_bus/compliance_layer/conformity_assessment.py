"""
ACGS-2 EU AI Act Conformity Assessment
Constitutional Hash: 608508a9bd224290

Automated conformity assessment for EU AI Act compliance with
evidence collection, Z3 formal verification integration, and
report generation capabilities.
"""

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import ClassVar
from uuid import UUID, uuid4

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


class AssessmentStatus(str, Enum):
    """Conformity assessment status."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    PASSED = "passed"
    FAILED = "failed"
    REQUIRES_REMEDIATION = "requires_remediation"


class EvidenceType(str, Enum):
    """Types of compliance evidence."""

    AUDIT_LOG = "audit_log"
    TEST_RESULT = "test_result"
    POLICY_DOCUMENT = "policy_document"
    TRAINING_RECORD = "training_record"
    RISK_ASSESSMENT = "risk_assessment"
    HUMAN_OVERSIGHT_LOG = "human_oversight_log"
    TRANSPARENCY_RECORD = "transparency_record"
    Z3_PROOF = "z3_proof"


@dataclass
class ComplianceEvidence:
    """Evidence item for conformity assessment."""

    id: UUID = field(default_factory=uuid4)
    evidence_type: EvidenceType = EvidenceType.AUDIT_LOG
    source: str = ""
    collected_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    content_hash: str = ""
    content: JSONDict = field(default_factory=dict)
    article_reference: str = ""
    is_valid: bool = True

    def compute_hash(self) -> str:
        """Compute SHA-256 hash of evidence content."""
        content_bytes = json_dumps(self.content, sort_keys=True).encode()
        self.content_hash = hashlib.sha256(content_bytes).hexdigest()
        return self.content_hash


@dataclass
class ConformityRequirement:
    """EU AI Act conformity requirement."""

    article: str
    description: str
    mandatory: bool = True
    evidence_types: list[EvidenceType] = field(default_factory=list)
    status: AssessmentStatus = AssessmentStatus.PENDING
    evidence: list[ComplianceEvidence] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    remediation_actions: list[str] = field(default_factory=list)


class ConformityAssessment:
    """
    Automated conformity assessment for EU AI Act compliance.

    Implements Annex IV technical documentation requirements and
    integrates with Z3 formal verification for policy proofs.

    Constitutional Hash: 608508a9bd224290
    """

    CONSTITUTIONAL_HASH = CONSTITUTIONAL_HASH

    REQUIREMENTS: ClassVar[list[JSONDict]] = [
        {
            "article": "Article 9",
            "description": "Risk Management System",
            "evidence_types": [EvidenceType.RISK_ASSESSMENT, EvidenceType.AUDIT_LOG],
        },
        {
            "article": "Article 10",
            "description": "Data and Data Governance",
            "evidence_types": [EvidenceType.POLICY_DOCUMENT, EvidenceType.AUDIT_LOG],
        },
        {
            "article": "Article 13",
            "description": "Transparency and Information Provision",
            "evidence_types": [EvidenceType.TRANSPARENCY_RECORD, EvidenceType.POLICY_DOCUMENT],
        },
        {
            "article": "Article 14",
            "description": "Human Oversight",
            "evidence_types": [EvidenceType.HUMAN_OVERSIGHT_LOG, EvidenceType.TRAINING_RECORD],
        },
        {
            "article": "Article 15",
            "description": "Accuracy, Robustness and Cybersecurity",
            "evidence_types": [EvidenceType.TEST_RESULT, EvidenceType.Z3_PROOF],
        },
        {
            "article": "Article 17",
            "description": "Quality Management System",
            "evidence_types": [EvidenceType.POLICY_DOCUMENT, EvidenceType.AUDIT_LOG],
        },
    ]

    def __init__(
        self,
        system_id: str,
        assessment_date: datetime | None = None,
    ) -> None:
        """Initialize conformity assessment.

        Args:
            system_id: Unique identifier for the AI system
            assessment_date: Date of assessment (defaults to now)
        """
        self.system_id = system_id
        self.assessment_id = uuid4()
        self.assessment_date = assessment_date or datetime.now(UTC)
        self.requirements: list[ConformityRequirement] = []
        self.evidence_bank: list[ComplianceEvidence] = []
        self.overall_status = AssessmentStatus.PENDING
        self._initialize_requirements()
        logger.info(
            f"[{self.CONSTITUTIONAL_HASH}] ConformityAssessment initialized for {system_id}"
        )

    def _initialize_requirements(self) -> None:
        """Initialize conformity requirements from EU AI Act."""
        for req in self.REQUIREMENTS:
            self.requirements.append(
                ConformityRequirement(
                    article=req["article"],
                    description=req["description"],
                    evidence_types=req["evidence_types"],
                )
            )

    def collect_evidence_from_audit_logs(
        self,
        audit_logs: list[JSONDict],
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[ComplianceEvidence]:
        """
        Automatically collect evidence from audit logs.

        Args:
            audit_logs: List of audit log entries
            start_date: Filter start date
            end_date: Filter end date

        Returns:
            List of collected evidence items
        """
        collected: list[ComplianceEvidence] = []
        start = start_date or (datetime.now(UTC) - timedelta(days=365))
        end = end_date or datetime.now(UTC)

        for log_entry in audit_logs:
            log_time = log_entry.get("timestamp")
            if isinstance(log_time, str):
                try:
                    log_time = datetime.fromisoformat(log_time.replace("Z", "+00:00"))
                except ValueError:
                    log_time = datetime.now(UTC)

            if log_time and start <= log_time <= end:
                evidence = ComplianceEvidence(
                    evidence_type=EvidenceType.AUDIT_LOG,
                    source="audit_service",
                    collected_at=datetime.now(UTC),
                    content=log_entry,
                    article_reference=self._map_log_to_article(log_entry),
                )
                evidence.compute_hash()
                collected.append(evidence)
                self.evidence_bank.append(evidence)

        logger.info(
            f"[{self.CONSTITUTIONAL_HASH}] Collected {len(collected)} evidence items from audit logs"
        )
        return collected

    def _map_log_to_article(self, log_entry: JSONDict) -> str:
        """Map audit log entry to relevant EU AI Act article."""
        action = log_entry.get("action", "").lower()

        mapping = {
            "risk": "Article 9",
            "data": "Article 10",
            "transparency": "Article 13",
            "human_oversight": "Article 14",
            "override": "Article 14",
            "security": "Article 15",
            "test": "Article 15",
            "quality": "Article 17",
        }

        for keyword, article in mapping.items():
            if keyword in action:
                return article

        return "Article 17"

    def integrate_z3_proof(
        self,
        policy_name: str,
        z3_result: JSONDict,
    ) -> ComplianceEvidence:
        """
        Integrate Z3 formal verification proof as evidence.

        Args:
            policy_name: Name of the verified policy
            z3_result: Z3 verification result containing:
                - satisfiable: bool - whether constraints are satisfied
                - proof_hash: str - hash of the proof
                - invariants: list[str] - checked invariants

        Returns:
            Evidence item containing the proof
        """
        evidence = ComplianceEvidence(
            evidence_type=EvidenceType.Z3_PROOF,
            source="z3_verifier",
            content={
                "policy_name": policy_name,
                "verification_result": z3_result.get("satisfiable", False),
                "proof_hash": z3_result.get("proof_hash", ""),
                "constitutional_hash": self.CONSTITUTIONAL_HASH,
                "invariants_checked": z3_result.get("invariants", []),
            },
            article_reference="Article 15",
            is_valid=z3_result.get("satisfiable", False),
        )
        evidence.compute_hash()
        self.evidence_bank.append(evidence)

        for req in self.requirements:
            if req.article == "Article 15":
                req.evidence.append(evidence)
                break

        logger.info(f"[{self.CONSTITUTIONAL_HASH}] Z3 proof integrated for policy: {policy_name}")
        return evidence

    def assess_requirement(self, requirement: ConformityRequirement) -> AssessmentStatus:
        """
        Assess a single conformity requirement.

        Args:
            requirement: The requirement to assess

        Returns:
            Assessment status
        """
        relevant_evidence = [
            e
            for e in self.evidence_bank
            if e.article_reference == requirement.article and e.is_valid
        ]
        requirement.evidence = relevant_evidence

        evidence_types_found = {e.evidence_type for e in relevant_evidence}
        required_types = set(requirement.evidence_types)

        if not required_types.issubset(evidence_types_found):
            missing = required_types - evidence_types_found
            requirement.findings.append(f"Missing evidence types: {[t.value for t in missing]}")
            requirement.status = AssessmentStatus.REQUIRES_REMEDIATION
            requirement.remediation_actions.append(
                f"Collect evidence for: {[t.value for t in missing]}"
            )
        elif len(relevant_evidence) < 2:
            requirement.findings.append("Insufficient evidence quantity")
            requirement.status = AssessmentStatus.REQUIRES_REMEDIATION
        else:
            requirement.status = AssessmentStatus.PASSED
            requirement.findings.append("All evidence requirements satisfied")

        return requirement.status

    def run_full_assessment(self) -> AssessmentStatus:
        """
        Run complete conformity assessment.

        Returns:
            Overall assessment status
        """
        all_passed = True
        any_failed = False

        for req in self.requirements:
            status = self.assess_requirement(req)
            if status == AssessmentStatus.FAILED:
                any_failed = True
                all_passed = False
            elif status == AssessmentStatus.REQUIRES_REMEDIATION:
                all_passed = False

        if any_failed:
            self.overall_status = AssessmentStatus.FAILED
        elif all_passed:
            self.overall_status = AssessmentStatus.PASSED
        else:
            self.overall_status = AssessmentStatus.REQUIRES_REMEDIATION

        logger.info(
            f"[{self.CONSTITUTIONAL_HASH}] Assessment complete: {self.overall_status.value}"
        )
        return self.overall_status

    def generate_conformity_report(self, format: str = "markdown") -> str:
        """
        Generate conformity assessment report.

        Args:
            format: Output format ('markdown', 'json', 'html')

        Returns:
            Formatted report string
        """
        if format == "json":
            return self._generate_json_report()
        elif format == "html":
            return self._generate_html_report()
        return self._generate_markdown_report()

    def _generate_markdown_report(self) -> str:
        """Generate Markdown format report."""
        lines = [
            "# EU AI Act Conformity Assessment Report",
            "",
            f"**System ID:** {self.system_id}",
            f"**Assessment ID:** {self.assessment_id}",
            f"**Assessment Date:** {self.assessment_date.isoformat()}",
            f"**Constitutional Hash:** {self.CONSTITUTIONAL_HASH}",
            f"**Overall Status:** {self.overall_status.value.upper()}",
            "",
            "---",
            "",
            "## Executive Summary",
            "",
            f"This conformity assessment evaluates {len(self.requirements)} EU AI Act requirements.",
            f"Total evidence items collected: {len(self.evidence_bank)}",
            "",
            "## Requirement Assessment Results",
            "",
        ]

        for req in self.requirements:
            status_icon = "✅" if req.status == AssessmentStatus.PASSED else "⚠️"
            lines.extend(
                [
                    f"### {req.article}: {req.description}",
                    "",
                    f"**Status:** {status_icon} {req.status.value}",
                    f"**Evidence Items:** {len(req.evidence)}",
                    "",
                    "**Findings:**",
                ]
            )
            for finding in req.findings:
                lines.append(f"- {finding}")

            if req.remediation_actions:
                lines.append("")
                lines.append("**Required Remediation:**")
                for action in req.remediation_actions:
                    lines.append(f"- {action}")

            lines.append("")

        lines.extend(
            [
                "---",
                "",
                "## Evidence Summary",
                "",
                "| Type | Count | Valid |",
                "|------|-------|-------|",
            ]
        )

        evidence_summary: dict[str, dict[str, int]] = {}
        for e in self.evidence_bank:
            key = e.evidence_type.value
            if key not in evidence_summary:
                evidence_summary[key] = {"count": 0, "valid": 0}
            evidence_summary[key]["count"] += 1
            if e.is_valid:
                evidence_summary[key]["valid"] += 1

        for etype, counts in evidence_summary.items():
            lines.append(f"| {etype} | {counts['count']} | {counts['valid']} |")

        lines.extend(
            [
                "",
                "---",
                "",
                f"*Report generated: {datetime.now(UTC).isoformat()}*",
            ]
        )

        return "\n".join(lines)

    def _generate_json_report(self) -> str:
        """Generate JSON format report."""
        report = {
            "system_id": self.system_id,
            "assessment_id": str(self.assessment_id),
            "assessment_date": self.assessment_date.isoformat(),
            "constitutional_hash": self.CONSTITUTIONAL_HASH,
            "overall_status": self.overall_status.value,
            "requirements": [
                {
                    "article": req.article,
                    "description": req.description,
                    "status": req.status.value,
                    "evidence_count": len(req.evidence),
                    "findings": req.findings,
                    "remediation_actions": req.remediation_actions,
                }
                for req in self.requirements
            ],
            "evidence_count": len(self.evidence_bank),
        }
        return json_dumps(report, indent=2)  # type: ignore[no-any-return]

    def _generate_html_report(self) -> str:
        """Generate HTML format report."""
        md_content = self._generate_markdown_report()
        return f"""<!DOCTYPE html>
<html>
<head>
    <title>EU AI Act Conformity Assessment Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; }}
        h1 {{ color: #1a365d; }}
        h2, h3 {{ color: #2c5282; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #4a5568; color: white; }}
        .passed {{ color: #38a169; }}
        .failed {{ color: #e53e3e; }}
    </style>
</head>
<body>
<pre>{md_content}</pre>
</body>
</html>"""


class ContinuousComplianceMonitor:
    """Continuous compliance monitoring for real-time assessment.

    Constitutional Hash: 608508a9bd224290
    """

    CONSTITUTIONAL_HASH = CONSTITUTIONAL_HASH

    def __init__(
        self,
        system_id: str,
        check_interval_hours: int = 24,
    ) -> None:
        """Initialize continuous compliance monitor.

        Args:
            system_id: System identifier
            check_interval_hours: Hours between checks
        """
        self.system_id = system_id
        self.check_interval = timedelta(hours=check_interval_hours)
        self.last_check: datetime | None = None
        self.compliance_history: list[JSONDict] = []
        self.alerts: list[JSONDict] = []

    def check_compliance(
        self,
        audit_logs: list[JSONDict],
    ) -> JSONDict:
        """
        Run compliance check and record results.

        Args:
            audit_logs: Recent audit logs to analyze

        Returns:
            Compliance check result
        """
        assessment = ConformityAssessment(self.system_id)
        assessment.collect_evidence_from_audit_logs(audit_logs)
        status = assessment.run_full_assessment()

        result = {
            "timestamp": datetime.now(UTC).isoformat(),
            "status": status.value,
            "requirements_passed": sum(
                1 for r in assessment.requirements if r.status == AssessmentStatus.PASSED
            ),
            "requirements_total": len(assessment.requirements),
            "evidence_count": len(assessment.evidence_bank),
        }

        self.compliance_history.append(result)
        self.last_check = datetime.now(UTC)

        for req in assessment.requirements:
            if req.status in (
                AssessmentStatus.FAILED,
                AssessmentStatus.REQUIRES_REMEDIATION,
            ):
                self.alerts.append(
                    {
                        "timestamp": datetime.now(UTC).isoformat(),
                        "severity": ("high" if req.status == AssessmentStatus.FAILED else "medium"),
                        "article": req.article,
                        "message": f"{req.description} requires attention",
                        "remediation": req.remediation_actions,
                    }
                )

        logger.info(f"[{self.CONSTITUTIONAL_HASH}] Compliance check complete: {status.value}")
        return result

    def get_dashboard_data(self) -> JSONDict:
        """Get data for compliance dashboard."""
        return {
            "system_id": self.system_id,
            "last_check": self.last_check.isoformat() if self.last_check else None,
            "compliance_trend": self.compliance_history[-30:],
            "active_alerts": [a for a in self.alerts if a.get("resolved") is not True],
            "overall_health": self._calculate_health_score(),
        }

    def _calculate_health_score(self) -> float:
        """Calculate overall compliance health score (0-100)."""
        if not self.compliance_history:
            return 0.0

        recent = self.compliance_history[-10:]
        scores = [
            (r["requirements_passed"] / r["requirements_total"]) * 100
            for r in recent
            if r["requirements_total"] > 0
        ]
        return sum(scores) / len(scores) if scores else 0.0


__all__ = [
    "AssessmentStatus",
    "ComplianceEvidence",
    "ConformityAssessment",
    "ConformityRequirement",
    "ContinuousComplianceMonitor",
    "EvidenceType",
]
