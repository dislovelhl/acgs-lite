"""Multi-framework AI compliance module for acgs-lite.

Provides compliance assessment against 18 major regulatory frameworks:

- **NIST AI RMF**: US AI Risk Management Framework (GOVERN/MAP/MEASURE/MANAGE)
- **ISO 42001**: International AI Management System standard
- **GDPR**: EU General Data Protection Regulation (automated decisions)
- **EU AI Act**: EU Artificial Intelligence Act (risk tiers, GPAI)
- **DORA**: EU Digital Operational Resilience Act (financial)
- **SOC 2 + AI**: Trust Service Criteria with AI-specific controls
- **HIPAA + AI**: Healthcare AI compliance (PHI protection)
- **US Fair Lending**: ECOA + FCRA + fair lending for credit AI
- **NYC LL144**: NYC Automated Employment Decision Tools law
- **OECD AI Principles**: International AI principles baseline (46 countries)
- **Canada AIDA**: Artificial Intelligence and Data Act (proposed)
- **Singapore MAIGF**: Model AI Governance Framework (ASEAN)
- **UK AI Framework**: Pro-innovation AI regulation framework
- **India DPDP**: Digital Personal Data Protection Act, 2023
- **Australia AI Ethics**: AI Ethics Principles (8 principles)
- **Brazil LGPD**: Lei Geral de Proteção de Dados
- **China AI**: Algorithm/DeepSynth/GenAI/Global AI regulations
- **CCPA/CPRA**: California Consumer Privacy / Privacy Rights Act

Each framework auto-populates checklist items that acgs-lite satisfies,
computing coverage and gap analysis.

Constitutional Hash: 608508a9bd224290

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

from acgs_lite.compliance.australia_ai_ethics import AustraliaAIEthicsFramework
from acgs_lite.compliance.base import (
    ChecklistItem,
    ChecklistStatus,
    ComplianceFramework,
    FrameworkAssessment,
    MultiFrameworkReport,
)
from acgs_lite.compliance.brazil_lgpd import BrazilLGPDFramework
from acgs_lite.compliance.canada_aida import CanadaAIDAFramework
from acgs_lite.compliance.ccpa_cpra import CCPACPRAFramework
from acgs_lite.compliance.china_ai import ChinaAIFramework
from acgs_lite.compliance.dora import DORAFramework
from acgs_lite.compliance.eu_ai_act import EUAIActFramework
from acgs_lite.compliance.evidence import EvidenceCollector, EvidenceRecord
from acgs_lite.compliance.gdpr import GDPRFramework
from acgs_lite.compliance.hipaa_ai import HIPAAAIFramework
from acgs_lite.compliance.india_dpdp import IndiaDPDPFramework
from acgs_lite.compliance.iso_42001 import ISO42001Framework
from acgs_lite.compliance.multi_framework import MultiFrameworkAssessor
from acgs_lite.compliance.nist_ai_rmf import NISTAIRMFFramework
from acgs_lite.compliance.nyc_ll144 import NYCLL144Framework
from acgs_lite.compliance.oecd_ai import OECDAIFramework
from acgs_lite.compliance.report_exporter import ComplianceReportExporter
from acgs_lite.compliance.singapore_maigf import SingaporeMAIGFFramework
from acgs_lite.compliance.soc2_ai import SOC2AIFramework
from acgs_lite.compliance.uk_ai_framework import UKAIFramework
from acgs_lite.compliance.us_fair_lending import USFairLendingFramework

__all__ = [
    # Base types
    "ChecklistItem",
    "ChecklistStatus",
    "ComplianceFramework",
    "FrameworkAssessment",
    "MultiFrameworkReport",
    # Frameworks (18)
    "NISTAIRMFFramework",
    "ISO42001Framework",
    "GDPRFramework",
    "EUAIActFramework",
    "DORAFramework",
    "SOC2AIFramework",
    "HIPAAAIFramework",
    "USFairLendingFramework",
    "NYCLL144Framework",
    "OECDAIFramework",
    "CanadaAIDAFramework",
    "SingaporeMAIGFFramework",
    "UKAIFramework",
    "IndiaDPDPFramework",
    "AustraliaAIEthicsFramework",
    "BrazilLGPDFramework",
    "ChinaAIFramework",
    "CCPACPRAFramework",
    # Orchestrator
    "MultiFrameworkAssessor",
    # Report exporter
    "ComplianceReportExporter",
    # Evidence collection
    "EvidenceCollector",
    "EvidenceRecord",
]
