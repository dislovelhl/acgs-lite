# Compliance Frameworks

ACGS covers 18 regulatory frameworks through a unified `ComplianceFramework` protocol. Each framework maps rules to ACGS governance features and produces structured assessment reports.

## Supported Frameworks

| Framework | Class | Domain |
|-----------|-------|--------|
| EU AI Act | `EUAIActFramework` | High-risk AI |
| NIST AI RMF | `NISTAIRMFFramework` | Risk management |
| ISO 42001 | `ISO42001Framework` | AI management systems |
| SOC 2 | `SOC2Framework` | Security/availability |
| HIPAA AI | `HIPAAFramework` | Healthcare |
| GDPR | `GDPRFramework` | Data protection |
| ECOA/FCRA | `ECOAFCRAFramework` | Fair lending |
| NYC LL 144 | `NYCLL144Framework` | Automated employment |
| OECD AI | `OECDFramework` | AI principles |
| DORA | `DORAFramework` | Digital operational resilience |
| UK AI | `UKAIFramework` | UK AI governance |
| Canada AIDA | `CanadaAIDAFramework` | Canadian AI |
| Brazil LGPD | `BrazilLGPDFramework` | Brazilian data protection |
| India DPDP | `IndiaDPDPFramework` | Indian data protection |
| China AI | `ChinaAIFramework` | Chinese AI regulations |
| Australia AI Ethics | `AustraliaAIEthicsFramework` | AU AI principles |
| Singapore MAIGF | `SingaporeMAIGFFramework` | SG AI governance |
| CCPA/CPRA | `CCPACPRAFramework` | California privacy |

## Multi-Framework Assessor

::: acgs_lite.compliance.multi_framework.MultiFrameworkAssessor
    options:
      members:
        - assess
        - assess_all
        - export_report

## ComplianceFramework Protocol

::: acgs_lite.compliance.base.ComplianceFramework

## Examples

### Assess against a single framework

```python
from acgs_lite.compliance.eu_ai_act import EUAIActFramework
from acgs_lite.compliance.evidence import EvidenceCollector

framework = EUAIActFramework()
collector = EvidenceCollector.from_agent(governed_agent)
report = framework.assess(collector)

print(f"Score: {report.score:.0%}")
print(f"Gaps: {len(report.gaps)}")
```

### Multi-framework assessment

```python
from acgs_lite.compliance.multi_framework import MultiFrameworkAssessor

assessor = MultiFrameworkAssessor(frameworks=["eu_ai_act", "nist_ai_rmf", "iso_42001"])
results = assessor.assess_all(collector)
assessor.export_report(results, "compliance_report.pdf")
```

### CLI shortcut

```bash
acgs-lite eu-ai-act --system-id "my-system" --domain healthcare
```
