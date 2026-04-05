# Compliance

ACGS maps controls across 18 regulatory frameworks globally.

## Coverage Summary

| Framework | Auto-Coverage | What It Covers |
|---|---|---|
| **EU AI Act** | 5/9 | Risk classification, transparency, human oversight, documentation, post-market monitoring |
| **NIST AI RMF** | 7/16 | Governance, risk mapping, measurement, management functions |
| **ISO/IEC 42001** | 9/18 | AI management system, risk assessment, performance evaluation |
| **SOC 2 + AI** | 10/16 | Security, availability, processing integrity, confidentiality, privacy |
| **HIPAA + AI** | 9/15 | Administrative safeguards, technical safeguards, audit controls |
| **GDPR Art. 22** | 10/12 | Automated decision-making, right to explanation, data protection |
| **ECOA/FCRA** | 6/12 | Fair lending, adverse action notices, model documentation |
| **NYC LL 144** | 6/12 | Bias audits, candidate notification, public reporting |
| **OECD AI** | 10/15 | Transparency, accountability, robustness, human oversight |

## Running an Assessment

```python
from acgs_lite.compliance import MultiFrameworkAssessor

assessor = MultiFrameworkAssessor()
report = assessor.assess({"jurisdiction": "EU", "domain": "healthcare"})

print(report.overall_score)        # 0.62
print(report.cross_framework_gaps) # Items needing manual evidence
```

## CLI Assessment

```bash
acgs assess --jurisdiction european_union --domain healthcare
acgs report --markdown
acgs report --pdf
```

## EU AI Act One-Shot

```bash
acgs eu-ai-act --domain healthcare
```

!!! warning "Auto-coverage is not full compliance"
    The remaining items require manual evidence, organizational policies, or
    domain-specific documentation. Use `report.cross_framework_gaps` to identify
    what still needs human input.

## Targeted Framework Assessment

```python
report = assessor.assess({
    "jurisdiction": "US",
    "domain": "finance",
    "frameworks": ["SOC2", "ECOA_FCRA"],
})

for gap in report.cross_framework_gaps:
    print(f"{gap.framework}: {gap.item} -- {gap.remediation}")
```
