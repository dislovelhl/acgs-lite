# EVAL: compliance-evidence-collectors

> **Type**: Capability | **Severity**: HIGH | **Date**: 2026-03-29
> **Commit**: `a360d907` (merge feat/compliance-evidence-cli-risk-tier)

Capability eval for `evidence.py` — live compliance evidence collection.

---

## Success Criteria

- pass@1 = 100% (data model + collector correctness)
- `EvidenceCollector` Protocol runtime-checkable

---

## Graders

### G11 — EvidenceItem / EvidenceBundle data model

```bash
python -c "
from acgs_lite.compliance.evidence import EvidenceItem, EvidenceBundle
i=EvidenceItem('gdpr',('GDPR Art.5(2)',),'import:X','desc',0.9)
b=EvidenceBundle('s','2026-01-01T00:00:00+00:00',(i,))
ok=(b.for_framework('gdpr')==[i] and b.for_ref('GDPR Art.5(2)')==[i] and b.summary()=={'gdpr':1})
print('PASS' if ok else 'FAIL')
"
```
**Result**: ✅ PASS

---

### G12 — ACGSLiteImportCollector detects acgs_lite

```bash
python -c "
from acgs_lite.compliance.evidence import ACGSLiteImportCollector
items=ACGSLiteImportCollector().collect({})
has_acgs=any('import:acgs_lite' in i.source for i in items)
print('PASS' if has_acgs else 'FAIL — no acgs_lite components detected')
"
```
**Result**: ✅ PASS

---

### G13 — FileSystemCollector finds rules.yaml

```bash
python -c "
import tempfile,pathlib
from acgs_lite.compliance.evidence import FileSystemCollector
with tempfile.TemporaryDirectory() as d:
    pathlib.Path(d,'rules.yaml').write_text('rules: []')
    items=FileSystemCollector(pathlib.Path(d)).collect({})
    found=any('rules.yaml' in i.source for i in items)
    print('PASS' if found else 'FAIL')
"
```
**Result**: ✅ PASS

---

### G14 — EnvironmentVarCollector reads ACGS_AUDIT_ENABLED=true

```bash
python -c "
import os
os.environ['ACGS_AUDIT_ENABLED']='true'
from acgs_lite.compliance.evidence import EnvironmentVarCollector
items=EnvironmentVarCollector().collect({})
ok=any('ACGS_AUDIT_ENABLED' in i.source for i in items)
del os.environ['ACGS_AUDIT_ENABLED']
print('PASS' if ok else 'FAIL')
"
```
**Result**: ✅ PASS

---

### G15 — ComplianceEvidenceEngine with empty collectors returns empty bundle

```bash
python -c "
from acgs_lite.compliance.evidence import ComplianceEvidenceEngine
b=ComplianceEvidenceEngine(collectors=[]).collect({'system_id':'t'})
print('PASS' if b.items==() else f'FAIL — got {len(b.items)} items')
"
```
**Result**: ✅ PASS
> Key fix: `collectors is None` check (not `collectors or [...]` — empty list is falsy).

---

### G16 — collect_evidence() convenience function

```bash
python -c "
from acgs_lite.compliance.evidence import EvidenceBundle, collect_evidence
b=collect_evidence({'system_id':'test'})
print('PASS' if isinstance(b,EvidenceBundle) else 'FAIL')
"
```
**Result**: ✅ PASS

---

### G17 — EvidenceCollector Protocol runtime_checkable

```bash
python -c "
from acgs_lite.compliance.evidence import EvidenceCollector, ACGSLiteImportCollector
print('PASS' if isinstance(ACGSLiteImportCollector(),EvidenceCollector) else 'FAIL')
"
```
**Result**: ✅ PASS

---

### G18 — All evidence symbols exported from compliance __init__

```bash
python -c "
from acgs_lite.compliance import (EvidenceItem,EvidenceBundle,EvidenceCollector,
  ACGSLiteImportCollector,FileSystemCollector,EnvironmentVarCollector,
  ComplianceEvidenceEngine,collect_evidence)
print('PASS')
"
```
**Result**: ✅ PASS

---

## Baseline (2026-03-29)

| Collector | Items in clean env | Key mappings |
|-----------|-------------------|-------------|
| `ACGSLiteImportCollector` | ≥ 45 (6 components × ~8 frameworks) | AuditLog→EU AI Act Art.12, GDPR Art.5(2); GovernanceEngine→NIST GOVERN 1.1 |
| `FileSystemCollector` | 0 in tmp dir / ≥1 with rules.yaml | rules.yaml→nist_ai_rmf+eu_ai_act; fria.*→EU-AIA Art.26(9) |
| `EnvironmentVarCollector` | 0 when no env vars set | ACGS_AUDIT_ENABLED=true→EU AI Act Art.12 |

## Component Coverage Map

| acgs_lite Component | Frameworks covered |
|--------------------|--------------------|
| `AuditLog` | 17 (all except China AI which uses CN-ARS Art.11) |
| `GovernanceEngine` | 14 |
| `HumanOversightGateway` | 13 |
| `TransparencyDisclosure` | 14 |
| `RiskClassifier` | 8 |
| `MACIEnforcer` | 7 |

## Regression Triggers

Re-run when `evidence.py` is modified. Re-run G12 when new acgs_lite components are added.
