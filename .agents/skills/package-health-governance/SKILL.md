---
name: package-health-governance
description: Maintain the package health manifest and package-level health reporting for ACGS. Use when editing `package-health.manifest.json`, validating package metadata, or reporting health by package. Do not use for general lint/test work that does not touch the manifest or package-health workflow.
---

# Package Health Governance

Use this skill only for the manifest-driven package health workflow.

When to use:
- updating `package-health.manifest.json`
- checking package owner, namespace, or verification-command accuracy
- reporting package health with `make health-*` targets

When not to use:
- ordinary implementation tasks
- repo-wide verification that does not involve package-health reporting

Canonical files:
- `package-health.manifest.json`
- `scripts/package_health.py`
- `Makefile`

Required workflow:
```bash
python3 scripts/package_health.py validate
python3 scripts/package_health.py list
make health-manifest
make health-overview
```

Rules:
- update one package entry at a time
- keep paths, namespaces, and verification commands aligned with checked-in reality
- report package health first; repo-wide totals second
- use only `ready`, `transitional`, or `planned` for gate status
