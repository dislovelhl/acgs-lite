"""Multi-framework AI compliance module for acgs-lite.

Provides compliance assessment against eight major regulatory frameworks:

- **NIST AI RMF**: US AI Risk Management Framework (GOVERN/MAP/MEASURE/MANAGE)
- **ISO 42001**: International AI Management System standard
- **GDPR**: EU General Data Protection Regulation (automated decisions)
- **SOC 2 + AI**: Trust Service Criteria with AI-specific controls
- **HIPAA + AI**: Healthcare AI compliance (PHI protection)
- **US Fair Lending**: ECOA + FCRA + fair lending for credit AI
- **NYC LL144**: NYC Automated Employment Decision Tools law
- **OECD AI Principles**: International AI principles baseline (46 countries)

Each framework auto-populates checklist items that acgs-lite satisfies,
computing coverage and gap analysis.

Constitutional Hash: cdd01ef066bc6cf2

Usage::

    from acgs_lite.compliance import MultiFrameworkAssessor

    assessor = MultiFrameworkAssessor()
    report = assessor.assess({
        "system_id": "my-system",
        "jurisdiction": "european_union",
        "domain": "healthcare",
    })
    print(report.overall_score)
    print(report.cross_framework_gaps)
"""

from acgs_lite.compliance.base import (
    ChecklistItem,
    ChecklistStatus,
    ComplianceFramework,
    FrameworkAssessment,
    MultiFrameworkReport,
)
from acgs_lite.compliance.gdpr import GDPRFramework
from acgs_lite.compliance.hipaa_ai import HIPAAAIFramework
from acgs_lite.compliance.iso_42001 import ISO42001Framework
from acgs_lite.compliance.multi_framework import MultiFrameworkAssessor
from acgs_lite.compliance.nist_ai_rmf import NISTAIRMFFramework
from acgs_lite.compliance.nyc_ll144 import NYCLL144Framework
from acgs_lite.compliance.oecd_ai import OECDAIFramework
from acgs_lite.compliance.soc2_ai import SOC2AIFramework
from acgs_lite.compliance.us_fair_lending import USFairLendingFramework

__all__ = [
    # Base types
    "ChecklistItem",
    "ChecklistStatus",
    "ComplianceFramework",
    "FrameworkAssessment",
    "MultiFrameworkReport",
    # Frameworks
    "NISTAIRMFFramework",
    "ISO42001Framework",
    "GDPRFramework",
    "SOC2AIFramework",
    "HIPAAAIFramework",
    "USFairLendingFramework",
    "NYCLL144Framework",
    "OECDAIFramework",
    # Orchestrator
    "MultiFrameworkAssessor",
]
