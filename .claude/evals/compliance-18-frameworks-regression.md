# EVAL: compliance-18-frameworks-regression

> **Type**: Regression | **Severity**: CRITICAL | **Date**: 2026-03-29
> **Commit**: `da200826` (merge feat/compliance-frameworks-18)

Regression baseline for the 18-framework compliance registry.  
Any change to `multi_framework.py`, `__init__.py`, or a framework file must re-pass
all graders before merge.

---

## Success Criteria

- pass^3 = 100% (all attempts pass — critical registry)

---

## Graders

### G1 — Registry count equals 18

```bash
python -c "
from acgs_lite.compliance import MultiFrameworkAssessor
n = len(MultiFrameworkAssessor.available_frameworks())
print('PASS' if n == 18 else f'FAIL — expected 18, got {n}')
"
```
**Result**: ✅ PASS

---

### G2 — All 18 framework IDs present

```bash
python -c "
from acgs_lite.compliance.multi_framework import _FRAMEWORK_REGISTRY
expected = {'nist_ai_rmf','iso_42001','gdpr','soc2_ai','hipaa_ai','us_fair_lending',
            'nyc_ll144','oecd_ai','eu_ai_act','dora','canada_aida','singapore_maigf',
            'uk_ai_framework','india_dpdp','australia_ai_ethics','brazil_lgpd',
            'china_ai','ccpa_cpra'}
missing = expected - set(_FRAMEWORK_REGISTRY)
print('PASS' if not missing else f'FAIL missing={missing}')
"
```
**Result**: ✅ PASS

---

### G3 — All 18 classes satisfy ComplianceFramework Protocol

```bash
python -c "
from acgs_lite.compliance import (ComplianceFramework,
  NISTAIRMFFramework, ISO42001Framework, GDPRFramework, SOC2AIFramework,
  HIPAAAIFramework, USFairLendingFramework, NYCLL144Framework, OECDAIFramework,
  EUAIActFramework, DORAFramework, CanadaAIDAFramework, SingaporeMAIGFFramework,
  UKAIFramework, IndiaDPDPFramework, AustraliaAIEthicsFramework, BrazilLGPDFramework,
  ChinaAIFramework, CCPACPRAFramework)
classes=[NISTAIRMFFramework,ISO42001Framework,GDPRFramework,SOC2AIFramework,
         HIPAAAIFramework,USFairLendingFramework,NYCLL144Framework,OECDAIFramework,
         EUAIActFramework,DORAFramework,CanadaAIDAFramework,SingaporeMAIGFFramework,
         UKAIFramework,IndiaDPDPFramework,AustraliaAIEthicsFramework,BrazilLGPDFramework,
         ChinaAIFramework,CCPACPRAFramework]
failed=[c.__name__ for c in classes if not isinstance(c(), ComplianceFramework)]
print('PASS' if not failed else f'FAIL={failed}')
"
```
**Result**: ✅ PASS

---

### G4 — Full compliance test suite: 314 passing

```bash
python -m pytest \
  packages/acgs-lite/tests/test_compliance.py \
  packages/acgs-lite/tests/test_compliance_new_frameworks.py \
  packages/acgs-lite/tests/test_compliance_round3.py \
  packages/acgs-lite/tests/test_compliance_eu_ai_act_risk_tier.py \
  packages/acgs-lite/tests/test_compliance_evidence.py \
  packages/acgs-lite/tests/test_compliance_cli_module.py \
  --import-mode=importlib -q 2>&1 | tail -1
# Expected: "314 passed"
```
**Result**: ✅ PASS — `314 passed in 0.60s`

---

## Baseline (2026-03-29)

| Metric | Value |
|--------|-------|
| Framework count | 18 |
| Passing tests | 314 |
| mypy errors | 0 |
| Commit | `a360d907` |

## Regression Triggers

Re-run this eval when:
- Any `compliance/*.py` file is modified
- A new framework is added (update G1/G2 counts)
- `__init__.py` `__all__` is changed
- `multi_framework.py` `_FRAMEWORK_REGISTRY` is changed
