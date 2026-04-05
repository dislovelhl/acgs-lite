# EVAL: compliance-cli-module

> **Type**: Capability | **Severity**: HIGH | **Date**: 2026-03-29
> **Commit**: `a360d907` (merge feat/compliance-evidence-cli-risk-tier)

Capability eval for `python -m acgs_lite.compliance` CLI.

---

## Success Criteria

- All subcommands exit 0
- JSON output is always valid JSON with expected schema
- Conditional flags (--risk-tier, --is-gpai, etc.) change assessment output
- pass@1 = 100%

---

## Graders

### G19 — frameworks: lists 18 frameworks

```bash
python -m acgs_lite.compliance frameworks | grep -q "18" && echo PASS || echo FAIL
```
**Result**: ✅ PASS

---

### G20 — frameworks --json: 18 rows with required fields

```bash
python -c "
import json,subprocess,sys
r=subprocess.run([sys.executable,'-m','acgs_lite.compliance','frameworks','--json'],
  capture_output=True,text=True)
rows=json.loads(r.stdout)
print('PASS' if len(rows)==18 else f'FAIL — {len(rows)} rows')
"
```
**Result**: ✅ PASS

---

### G21 — assess --format json: valid schema

```bash
python -c "
import json,subprocess,sys
r=subprocess.run([sys.executable,'-m','acgs_lite.compliance','assess',
  '--system-id','eval-test','--format','json'],capture_output=True,text=True)
d=json.loads(r.stdout)
ok=all(k in d for k in ('system_id','overall_score','frameworks_assessed','by_framework'))
print('PASS' if ok else f'FAIL — keys={list(d)}')
"
```
**Result**: ✅ PASS

---

### G22 — assess --domain hiring shows "auto-inferred from domain"

```bash
python -c "
import subprocess,sys
r=subprocess.run([sys.executable,'-m','acgs_lite.compliance','assess',
  '--framework','eu_ai_act','--domain','hiring'],capture_output=True,text=True)
ok='auto-inferred' in r.stdout and 'high' in r.stdout
print('PASS' if ok else f'FAIL — stdout={r.stdout[:200]}')
"
```
**Result**: ✅ PASS

---

### G23 — assess --domain chatbot: limited tier (no Art.9 in items)

```bash
python -c "
import json,subprocess,sys
r=subprocess.run([sys.executable,'-m','acgs_lite.compliance','assess',
  '--framework','eu_ai_act','--domain','chatbot','--format','json'],
  capture_output=True,text=True)
d=json.loads(r.stdout)
refs={i['ref'] for i in d['by_framework']['eu_ai_act']['items']}
no_art9='EU-AIA Art.9(1)' not in refs
print('PASS' if no_art9 else f'FAIL — Art.9 leaked into limited checklist')
"
```
**Result**: ✅ PASS

---

### G24 — assess --is-gpai: Art.53(1) appears in EU AI Act items

```bash
python -c "
import json,subprocess,sys
r=subprocess.run([sys.executable,'-m','acgs_lite.compliance','assess',
  '--framework','eu_ai_act','--risk-tier','high','--is-gpai','--format','json'],
  capture_output=True,text=True)
d=json.loads(r.stdout)
refs={i['ref'] for i in d['by_framework']['eu_ai_act']['items']}
print('PASS' if 'EU-AIA Art.53(1)' in refs else f'FAIL')
"
```
**Result**: ✅ PASS

---

### G25 — evidence --json: valid bundle schema

```bash
python -c "
import json,subprocess,sys
r=subprocess.run([sys.executable,'-m','acgs_lite.compliance','evidence',
  '--system-id','ev-test','--json'],capture_output=True,text=True)
d=json.loads(r.stdout)
ok=all(k in d for k in ('system_id','items','item_count'))
print('PASS' if ok else f'FAIL — keys={list(d)}')
"
```
**Result**: ✅ PASS

---

### G26 — --help exits 0

```bash
python -m acgs_lite.compliance --help > /dev/null 2>&1 && echo PASS || echo FAIL
```
**Result**: ✅ PASS

---

### G27 — Makefile mypy compliance scope: 0 errors

```bash
python -m mypy \
  packages/acgs-lite/src/acgs_lite/compliance/__init__.py \
  packages/acgs-lite/src/acgs_lite/compliance/base.py \
  packages/acgs-lite/src/acgs_lite/compliance/multi_framework.py \
  packages/acgs-lite/src/acgs_lite/compliance/evidence.py \
  packages/acgs-lite/src/acgs_lite/compliance/report_exporter.py \
  packages/acgs-lite/src/acgs_lite/compliance/__main__.py \
  --ignore-missing-imports --follow-imports skip 2>&1 | grep -q "Success" && echo PASS || echo FAIL
```
**Result**: ✅ PASS

---

## Baseline (2026-03-29)

| Subcommand | Exit code | Output schema | Notes |
|-----------|-----------|--------------|-------|
| `frameworks` | 0 | Table with 18 rows | |
| `frameworks --json` | 0 | `[{id,name,jurisdiction,status,enforcement_date}]` × 18 | |
| `assess` | 0 | Text with tier, score, bar chart, verdict | |
| `assess --format json` | 0 | `{system_id, overall_score, frameworks_assessed, by_framework}` | |
| `assess --format markdown` | 0 | GFM with `#` headers | |
| `evidence --json` | 0 | `{system_id, item_count, items, collected_at}` | |

## Conditional Flag Behavior

| Flag | Effect |
|------|--------|
| `--risk-tier minimal` | EU AI Act checklist → Art.5 + Art.50 only |
| `--risk-tier high` | EU AI Act checklist → full 23-item track |
| `--domain chatbot` | Infers limited tier (chatbot ∈ `_LIMITED_RISK_DOMAINS`) |
| `--domain hiring` | Infers high tier (hiring ∈ `_HIGH_RISK_DOMAINS`) |
| `--is-gpai` | Adds Art.53(1), Art.53(2), Art.55(1) to EU AI Act items |
| `--is-significant-entity` | DORA TLPT Art.25 not marked N/A |
| `--is-significant-data-fiduciary` | India DPDP §16 items not marked N/A |

## Regression Triggers

Re-run when `compliance/__main__.py` is modified, or when `eu_ai_act.py` tier logic changes.
