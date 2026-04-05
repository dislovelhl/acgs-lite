---
total_tests: 74
total_folders: 7
folders:
  - name: governance-validation
    test_count: 16
    description: Core flow tests for POST /validate -- action validation against constitutional rules including keyword matching, regex patterns, conditional rules, input validation errors, and cross-scenario coverage
  - name: rules-crud
    test_count: 13
    description: Core flow tests for constitutional rule lifecycle -- list, get, create, update, delete rules with error handling for duplicates, missing IDs, and rule-change-affects-validation cross-flow
  - name: clinicalguard
    test_count: 15
    description: Core flow tests for ClinicalGuard A2A agent -- clinical validation (drug interactions, guideline concordance, step therapy), HIPAA compliance checks, audit trail queries, auth, and JSON-RPC error handling
  - name: audit-trail
    test_count: 10
    description: Core flow tests for tamper-evident audit trail -- entry listing, agent filtering, pagination, SHA-256 chain integrity verification, count endpoint, and validation-creates-entry cross-flow
  - name: landing-site
    test_count: 8
    description: Non-core tests for the Propriety AI SvelteKit landing site -- home hero section, scroll sections, pricing page tiers, resources page, demo page, footer, and navigation links
  - name: compliance
    test_count: 5
    description: Non-core tests for compliance and GDPR features -- EU AI Act assessment, governance vector schema, data subject access requests, erasure lifecycle, and PII classification
  - name: health-checks
    test_count: 7
    description: Non-core tests for health and readiness probes across all three services -- acgs-lite health and stats, API Gateway health/live/startup probes, ClinicalGuard health, and empty-scenario health
coverage_correlation: >
  The feature inventory lists 24 features across 4 packages. Core flows (governance-validation,
  rules-crud, clinicalguard, audit-trail) received 54 tests (73% of total), reflecting their
  critical importance as the product's primary value proposition. Non-core flows (landing-site,
  compliance, health-checks) received 20 tests (27% of total). The 54/20 core/non-core split
  aligns with the recommended 50-60% Tier 1 / 25-30% Tier 2 / 15-20% Tier 3 test budget.
  Each of the 24 features has at least one test, with core features averaging 4-5 tests per
  feature to cover happy paths, validation errors, empty-state, and large-scale scenarios.
---

# ACGS E2E Test Index

## Test Distribution

| Folder | Flow Type | Tests | Features Covered |
|--------|-----------|-------|------------------|
| governance-validation | core | 16 | Governance Validation (POST /validate) |
| rules-crud | core | 13 | Constitution Management (GET/POST/PUT/DELETE /rules) |
| clinicalguard | core | 15 | ClinicalGuard Clinical Validation, HIPAA, Audit |
| audit-trail | core | 10 | Audit Trail Inspection (/audit/entries, /chain, /count) |
| landing-site | non-core | 8 | Landing Page Home, Pricing, Resources, Demo |
| compliance | non-core | 5 | Compliance Assessment, Governance Vector, GDPR Rights |
| health-checks | non-core | 7 | Health Probes across all 3 services |
| **Total** | | **74** | **24 features** |

## Scenario Coverage

| Scenario | Tests |
|----------|-------|
| standard | 58 |
| empty | 8 |
| large | 8 |

## Criticality Distribution

| Criticality | Tests |
|-------------|-------|
| critical | 36 |
| high | 28 |
| mid | 10 |

## Category Coverage

| Category | Tests |
|----------|-------|
| happy-path | 46 |
| validation | 14 |
| state-persistence | 3 |
| multi-entity | 3 |
| navigation | 2 |
| async-patterns | 2 |
| happy-path (empty) | 4 |

## Core Flow Breakdown

### Governance Validation (16 tests)
- GV-001 through GV-010: Happy path tests for each validation action in the standard scenario
- GV-011 through GV-013: Input validation error cases (empty action, wrong types)
- GV-014: Constitutional hash consistency across responses
- GV-015: Empty scenario validation
- GV-016: Large scenario stress test

### Rules CRUD (13 tests)
- RC-001 through RC-002: List and get rules
- RC-003: Non-existent rule 404
- RC-004: Create rule
- RC-005 through RC-006: Duplicate and empty ID validation
- RC-007 through RC-008: Update rule and non-existent update
- RC-009 through RC-010: Delete rule and non-existent delete
- RC-011: Rule changes affect validation (cross-flow test)
- RC-012 through RC-013: Empty and large scenario

### ClinicalGuard (15 tests)
- CG-001 through CG-003: Clinical validation happy paths (drug interaction, approved, step therapy)
- CG-004 through CG-005: HIPAA compliance check (compliant and non-compliant)
- CG-006: Audit trail query
- CG-007 through CG-012: Error cases (auth, size limits, invalid JSON, unknown method/skill)
- CG-013: Agent card discovery
- CG-014: JSON-RPC 2.0 format compliance
- CG-015: Empty scenario audit query

### Audit Trail (10 tests)
- AT-001: List all entries
- AT-002 through AT-003: Agent ID filtering
- AT-004: Pagination
- AT-005 through AT-006: Chain integrity and count
- AT-007: Constitutional hash in entries
- AT-008: Empty scenario
- AT-009: Large scenario pagination
- AT-010: Validation creates audit entry (cross-flow test)
