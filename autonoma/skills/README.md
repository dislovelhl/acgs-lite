# Autonoma Skills

This directory contains human-readable skill flows for the Autonoma planning and E2E testing
surface.

## What Is Here

The files in this directory describe how to drive key product flows in plain language so they can
be reused in scenario planning, QA, and automated test authoring.

## Skill Groups

| Group | Purpose |
| --- | --- |
| API skills | Exercise governance validation, rules CRUD, audit queries, health checks, and data-subject-rights flows |
| ClinicalGuard skills | Validate clinical actions, query the audit trail, and check HIPAA-oriented behavior |
| Landing-site skills | Walk the home, pricing, resources, and demo flows for the ACGS web frontend |

## Representative Files

| File | Use when |
| --- | --- |
| [`api-validate-action.md`](api-validate-action.md) | You need the canonical POST `/validate` governance flow |
| [`api-manage-rules.md`](api-manage-rules.md) | You are working on constitutional rule CRUD behavior |
| [`api-query-audit.md`](api-query-audit.md) | You need the audit trail query flow |
| [`clinicalguard-validate.md`](clinicalguard-validate.md) | You need the clinical validation flow |
| [`navigate-landing-home.md`](navigate-landing-home.md) | You need the main landing-page acceptance flow |
| [`navigate-landing-pricing.md`](navigate-landing-pricing.md) | You need the pricing-page flow |

## Related Docs

- [Autonoma knowledge base](../AUTONOMA.md)
- [Autonoma scenarios](../scenarios.md)
- [Autonoma QA test index](../qa-tests/README.md)
