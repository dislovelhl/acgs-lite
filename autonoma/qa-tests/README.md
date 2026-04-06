# Autonoma QA Tests

This directory contains scenario-oriented QA specifications for the ACGS surfaces covered by
Autonoma.

## Coverage Shape

The suite is organized into seven folders:

| Folder | Focus |
| --- | --- |
| `governance-validation/` | Core `POST /validate` governance behavior |
| `rules-crud/` | Constitutional rule lifecycle |
| `clinicalguard/` | ClinicalGuard validation, HIPAA, and audit flows |
| `audit-trail/` | Audit entry listing, filtering, counting, and chain verification |
| `landing-site/` | Web frontend home, pricing, resources, demo, and nav flows |
| `compliance/` | Compliance assessment and GDPR/PII-related flows |
| `health-checks/` | Health and readiness checks across the main services |

## Start Here

- [Suite index](INDEX.md) for totals, scenario distribution, and coverage rationale
- A representative governance happy-path test: [GV-001-benign-action-allowed.md](governance-validation/GV-001-benign-action-allowed.md)
- A representative landing-page test: [LS-001-home-hero-section.md](landing-site/LS-001-home-hero-section.md)

## Related Docs

- [Autonoma knowledge base](../AUTONOMA.md)
- [Autonoma skills](../skills/README.md)
