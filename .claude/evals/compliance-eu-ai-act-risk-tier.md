# EVAL: compliance-eu-ai-act-risk-tier

> **Type**: Capability | **Severity**: HIGH | **Date**: 2026-03-29
> **Commit**: `a360d907` (merge feat/compliance-evidence-cli-risk-tier)

Capability eval for `infer_risk_tier()` — EU AI Act Annex III auto-detection.

---

## Success Criteria

- pass@1 ≥ 90% per grader
- Conservative default never silently under-applies regulation

---

## Graders

### G5 — 9 Annex III high-risk domains → "high"

```bash
python -c "
from acgs_lite.compliance.eu_ai_act import infer_risk_tier
cases = [
  ('healthcare','high'),('hiring','high'),('education','high'),
  ('credit_scoring','high'),('law_enforcement','high'),('biometrics','high'),
  ('migration','high'),('justice','high'),('critical_infrastructure','high'),
]
failed=[f'{d}→{infer_risk_tier({\"domain\":d})}' for d,e in cases if infer_risk_tier({'domain':d})!=e]
print('PASS' if not failed else 'FAIL: '+str(failed))
"
```
**Result**: ✅ PASS

---

### G6 — Limited-risk domains → "limited"

```bash
python -c "
from acgs_lite.compliance.eu_ai_act import infer_risk_tier
cases=[('chatbot','limited'),('customer_service','limited'),('content_generation','limited')]
failed=[f'{d}→{infer_risk_tier({\"domain\":d})}' for d,e in cases if infer_risk_tier({'domain':d})!=e]
print('PASS' if not failed else 'FAIL: '+str(failed))
"
```
**Result**: ✅ PASS

---

### G7 — Conservative default: no domain → "high"

```bash
python -c "
from acgs_lite.compliance.eu_ai_act import infer_risk_tier
r1=infer_risk_tier({})
r2=infer_risk_tier({'domain':'unknown_domain_xyz'})
ok = r1=='high' and r2=='high'
print('PASS' if ok else f'FAIL: empty={r1} unknown={r2}')
"
```
**Result**: ✅ PASS

---

### G8 — Explicit risk_tier overrides domain inference

```bash
python -c "
from acgs_lite.compliance.eu_ai_act import infer_risk_tier
r=infer_risk_tier({'risk_tier':'minimal','domain':'healthcare'})
print('PASS' if r=='minimal' else f'FAIL: got {r}')
"
```
**Result**: ✅ PASS

---

### G9 — High-risk checklist > limited-risk checklist

```bash
python -c "
from acgs_lite.compliance.eu_ai_act import EUAIActFramework
fw=EUAIActFramework()
hi=len(fw.get_checklist({'risk_tier':'high'}))
lo=len(fw.get_checklist({'risk_tier':'limited'}))
print('PASS' if hi > lo else f'FAIL: high={hi} limited={lo}')
"
```
**Result**: ✅ PASS

---

### G10 — Exported from acgs_lite.compliance

```bash
python -c "
from acgs_lite.compliance import infer_risk_tier
r=infer_risk_tier({'domain':'education'})
print('PASS' if r=='high' else f'FAIL: {r}')
"
```
**Result**: ✅ PASS

---

## Baseline (2026-03-29)

| Domain | Expected tier | Actual |
|--------|--------------|--------|
| `healthcare` | `high` | `high` ✅ |
| `hiring` | `high` | `high` ✅ |
| `chatbot` | `limited` | `limited` ✅ |
| `customer_service` | `limited` | `limited` ✅ |
| *(empty)* | `high` (default) | `high` ✅ |
| `unknown_xyz` | `high` (default) | `high` ✅ |
| explicit `minimal` + `domain=healthcare` | `minimal` (override) | `minimal` ✅ |

## Design Notes

- 42 Annex III high-risk terms (9 domain groups from Annex III points 1-8 + healthcare)
- 8 limited-risk terms (Art. 50 transparency-only systems)
- Conservative default: unknown domain → "high" (fail-safe: prefer over-regulation)
- `risk_tier` key always wins — enables manual override for edge cases

## Regression Triggers

Re-run when `eu_ai_act.py` is modified, especially `_HIGH_RISK_DOMAINS` / `_LIMITED_RISK_DOMAINS`.
