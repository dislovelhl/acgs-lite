---
scenario_count: 3
scenarios:
  - name: standard
    description: >
      Typical ACGS deployment with a representative set of constitutional rules,
      validation actions, audit trail entries, clinical records, compliance
      framework mappings, and user accounts. Covers all four platform surfaces
      (acgs-lite governance server, API gateway, ClinicalGuard, landing site).
    entity_count: 68
    entity_types:
      - constitutional_rule
      - validation_action
      - audit_entry
      - clinical_record
      - compliance_framework_mapping
      - user_account
  - name: empty
    description: >
      Fresh installation with no user-created data. Only built-in defaults exist.
      Tests empty-state rendering, zero-count responses, and first-use flows.
    entity_count: 4
    entity_types:
      - constitutional_rule
      - validation_action
      - audit_entry
      - clinical_record
  - name: large
    description: >
      Stress scenario with high-volume data exceeding pagination thresholds.
      Tests pagination, filtering under load, audit chain verification at scale,
      and rule engine performance with a large constitution.
    entity_count: 1137
    entity_types:
      - constitutional_rule
      - validation_action
      - audit_entry
      - clinical_record
      - compliance_framework_mapping
      - user_account
entity_types:
  - constitutional_rule
  - validation_action
  - audit_entry
  - clinical_record
  - compliance_framework_mapping
  - user_account
---

# Test Data Scenarios

Three test data environments for E2E testing of the ACGS platform. Every value
in the **standard** scenario is a hard assertion target in generated tests.

---

## Scenario: `standard`

A typical deployment with representative data across all entity types. Provides
enough variety to exercise every filter, category, severity level, and skill.

### Constitutional Rules (10 rules)

| # | id | text | severity | keywords | patterns | category | subcategory | workflow_action | enabled | tags | priority |
|---|-----|------|----------|----------|----------|----------|-------------|-----------------|---------|------|----------|
| 1 | `SAFE-001` | Reject actions that could cause physical harm to humans | `critical` | `["harm", "injure", "kill", "weapon", "attack"]` | `[]` | `safety` | `` | `block` | `true` | `["core", "eu-ai-act"]` | `10` |
| 2 | `PRIV-001` | Block unauthorized access to personal data | `high` | `["personal data", "PII", "SSN", "social security"]` | `["\\b\\d{3}-\\d{2}-\\d{4}\\b"]` | `privacy` | `pii-detection` | `block` | `true` | `["gdpr", "hipaa", "ccpa"]` | `8` |
| 3 | `BIAS-001` | Flag decisions that discriminate based on protected characteristics | `high` | `["race", "gender", "religion", "disability", "age"]` | `[]` | `fairness` | `protected-class` | `block` | `true` | `["eu-ai-act", "nyc-ll144"]` | `7` |
| 4 | `TRANS-001` | Require explanation for consequential automated decisions | `medium` | `["reject", "deny", "terminate", "suspend"]` | `[]` | `transparency` | `` | `warn` | `true` | `["eu-ai-act"]` | `5` |
| 5 | `OVER-001` | Escalate high-impact decisions for human review | `medium` | `["approve", "authorize", "deploy", "release"]` | `[]` | `oversight` | `` | `require_human_review` | `true` | `["soc2"]` | `5` |
| 6 | `FIN-001` | No financial advice or investment recommendations | `critical` | `["invest", "buy stocks", "financial advice"]` | `[]` | `safety` | `financial` | `block` | `true` | `["compliance"]` | `9` |
| 7 | `SEC-001` | Never expose API keys, secrets, or credentials in output | `critical` | `["api_key", "secret", "password", "credential"]` | `["(?i)(api[_-]?key|secret|password)\\s*[:=]\\s*\\S+"]` | `security` | `credential-leak` | `block_and_notify` | `true` | `["soc2", "nist"]` | `10` |
| 8 | `DEPR-001` | Legacy rule replaced by SAFE-001 | `low` | `["deprecated-keyword"]` | `[]` | `general` | `` | `warn` | `false` | `[]` | `0` |
| 9 | `COND-001` | Block production deployments without approval | `high` | `["deploy", "release"]` | `[]` | `oversight` | `deployment` | `block` | `true` | `["soc2"]` | `6` |
| 10 | `TEMP-001` | Temporary holiday freeze on model updates | `medium` | `["model update", "retrain"]` | `[]` | `oversight` | `change-freeze` | `warn` | `true` | `[]` | `3` |

Additional `Rule` field values for selected rules:

- `SAFE-001`: `hardcoded: false`, `deprecated: false`, `replaced_by: ""`, `condition: {}`, `valid_from: ""`, `valid_until: ""`
- `DEPR-001`: `deprecated: true`, `replaced_by: "SAFE-001"`, `enabled: false`
- `COND-001`: `condition: {"env": "production"}` (only fires when context `env` equals `"production"`)
- `TEMP-001`: `valid_from: "2026-12-20"`, `valid_until: "2027-01-05"` (active only during holiday freeze window)

**Assertions:**
- `GET /rules` returns exactly **10** rules
- Rule with `id: "SAFE-001"` has `severity: "critical"` and `category: "safety"`
- Rule with `id: "DEPR-001"` has `enabled: false` and `deprecated: true`
- Rule with `id: "COND-001"` has a non-empty `condition` field

### Validation Actions (12 actions)

These are POST `/validate` requests and their expected outcomes.

| # | action | agent_id | context | expected_valid | expected_violations | description |
|---|--------|----------|---------|----------------|---------------------|-------------|
| 1 | `check the weather forecast` | `test-agent` | `{}` | `true` | `[]` | Benign action, no rules fire |
| 2 | `harm the user by deleting their data` | `test-agent` | `{}` | `false` | `["SAFE-001"]` | Triggers SAFE-001 keyword "harm" |
| 3 | `access personal data without consent` | `test-agent` | `{}` | `false` | `["PRIV-001"]` | Triggers PRIV-001 keyword "personal data" |
| 4 | `recommend buying stocks in Tesla` | `finance-agent` | `{}` | `false` | `["FIN-001"]` | Triggers FIN-001 keyword "buy stocks" |
| 5 | `summarize the quarterly report` | `analyst-agent` | `{}` | `true` | `[]` | Benign action |
| 6 | `deploy the model to production` | `deploy-agent` | `{"env": "production"}` | `false` | `["COND-001"]` | Triggers COND-001 with production context |
| 7 | `deploy the model to staging` | `deploy-agent` | `{"env": "staging"}` | `true` | `[]` | COND-001 does not fire in staging context |
| 8 | `SSN is 123-45-6789` | `data-agent` | `{}` | `false` | `["PRIV-001"]` | Triggers PRIV-001 regex pattern |
| 9 | `output includes api_key: sk-abc123` | `leaky-agent` | `{}` | `false` | `["SEC-001"]` | Triggers SEC-001 keyword + pattern |
| 10 | `testing security controls for credential leaks` | `auditor-agent` | `{}` | `true` | `[]` | Positive-verb context: "testing" suppresses false positive |
| 11 | `reject the insurance claim without explanation` | `claims-agent` | `{}` | `false` | `["TRANS-001"]` | Triggers TRANS-001 keyword "reject" |
| 12 | `` (empty string) | `test-agent` | `{}` | N/A (HTTP 422) | N/A | Validation error: empty action |

**Assertions:**
- Actions 1, 5, 7, 10 return `valid: true` with empty `violations`
- Actions 2, 3, 4, 6, 8, 9, 11 return `valid: false` with specific violation IDs
- Action 12 returns HTTP 422 with `"'action' must be a non-empty string"`
- Every successful response (HTTP 200) includes `constitutional_hash: "608508a9bd224290"` and an `audit_id` field

### Audit Entries (8 entries)

Pre-seeded audit trail entries. Created by running the 11 valid actions above (action 12 is rejected before auditing).

| # | id | type | agent_id | action | valid | violations | constitutional_hash | latency_ms |
|---|-----|------|----------|--------|-------|------------|---------------------|------------|
| 1 | `AUD-STD-001` | `validation` | `test-agent` | `check the weather forecast` | `true` | `[]` | `608508a9bd224290` | `0.4` |
| 2 | `AUD-STD-002` | `validation` | `test-agent` | `harm the user by deleting their data` | `false` | `["SAFE-001"]` | `608508a9bd224290` | `0.5` |
| 3 | `AUD-STD-003` | `validation` | `test-agent` | `access personal data without consent` | `false` | `["PRIV-001"]` | `608508a9bd224290` | `0.4` |
| 4 | `AUD-STD-004` | `validation` | `finance-agent` | `recommend buying stocks in Tesla` | `false` | `["FIN-001"]` | `608508a9bd224290` | `0.3` |
| 5 | `AUD-STD-005` | `validation` | `analyst-agent` | `summarize the quarterly report` | `true` | `[]` | `608508a9bd224290` | `0.3` |
| 6 | `AUD-STD-006` | `validation` | `deploy-agent` | `deploy the model to production` | `false` | `["COND-001"]` | `608508a9bd224290` | `0.4` |
| 7 | `AUD-STD-007` | `validation` | `deploy-agent` | `deploy the model to staging` | `true` | `[]` | `608508a9bd224290` | `0.3` |
| 8 | `AUD-STD-008` | `validation` | `auditor-agent` | `testing security controls for credential leaks` | `true` | `[]` | `608508a9bd224290` | `0.3` |

**Assertions:**
- `GET /audit/entries` returns exactly **8** entries
- `GET /audit/entries?agent_id=test-agent` returns exactly **3** entries (AUD-STD-001, 002, 003)
- `GET /audit/entries?agent_id=deploy-agent` returns exactly **2** entries (AUD-STD-006, 007)
- `GET /audit/entries?agent_id=nonexistent-agent` returns `[]`
- `GET /audit/entries?limit=3&offset=0` returns exactly **3** entries
- `GET /audit/entries?limit=3&offset=3` returns exactly **3** entries with no overlap with the first page
- `GET /audit/chain` returns `{"valid": true, "entry_count": 8}`
- `GET /audit/count` returns `{"count": 8}`
- Each entry has a non-empty `timestamp` in ISO-8601 format

### Clinical Records (6 records)

ClinicalGuard A2A validation requests sent to `POST /` with `method: "tasks/send"`.

| # | skill | action_text | expected_decision | expected_risk_tier | description |
|---|-------|------------|-------------------|--------------------|----|
| 1 | `validate_clinical_action` | `Patient SYNTH-042 on Warfarin. Propose Aspirin 325mg daily.` | `CONDITIONALLY_APPROVED` or `REJECTED` | `high` | Drug interaction: Warfarin + Aspirin |
| 2 | `validate_clinical_action` | `Patient SYNTH-101 with Type 2 Diabetes. Prescribe Metformin 500mg twice daily. Evidence tier: ADA guideline.` | `APPROVED` | `low` | Standard guideline-concordant therapy |
| 3 | `validate_clinical_action` | `Patient SYNTH-099. Prescribe Adalimumab without prior Methotrexate trial. No prior treatment documented.` | `CONDITIONALLY_APPROVED` or `REJECTED` | `high` | Step therapy violation: HC-004 |
| 4 | `check_hipaa_compliance` | `This agent processes synthetic patient data, maintains an audit log, encrypts data at rest and in transit, and limits access to authorized personnel only.` | N/A (`compliant: true`) | N/A | HIPAA-compliant system description |
| 5 | `check_hipaa_compliance` | `This agent processes real patient records with no encryption and shares data freely.` | N/A (`compliant: false`) | N/A | Non-compliant system description |
| 6 | `query_audit_trail` | `recent 10` | N/A (returns entries) | N/A | Audit trail query |

**Assertions:**
- Record 1 response has `result.status: "completed"` and `result.result.decision` is one of `["CONDITIONALLY_APPROVED", "REJECTED"]`
- Record 2 response has `result.result.decision: "APPROVED"` and `result.result.risk_tier: "low"`
- Record 4 response has `result.result.compliant: true`
- Record 5 response has `result.result.compliant: false`
- Record 6 response has `result.result.entries` as an array and `result.result.chain_valid` as a boolean
- All responses use JSON-RPC 2.0 format: `{"jsonrpc": "2.0", "id": 1, "result": {...}}`
- All successful clinical validation responses include an `audit_id` matching the pattern `HC-\d{8}-[A-F0-9]{6}`

### Compliance Framework Mappings (9 frameworks)

The 9 regulatory frameworks supported by ACGS, with their IDs as used in the compliance module.

| # | framework_id | framework_name | jurisdiction | sample_rule_mapping |
|---|-------------|---------------|-------------|---------------------|
| 1 | `eu_ai_act` | EU Artificial Intelligence Act (Regulation (EU) 2024/1689) | EU | `SAFE-001 -> Art.9-RiskMgmt` |
| 2 | `gdpr` | EU General Data Protection Regulation (GDPR) | EU | `PRIV-001 -> Art.5(1)(a)` |
| 3 | `hipaa` | HIPAA + AI Healthcare Compliance | US | `PRIV-001 -> §164.312(a)(1)` |
| 4 | `nist_ai_rmf` | NIST AI Risk Management Framework | US | `SAFE-001 -> GOVERN-1` |
| 5 | `soc2` | SOC 2 Type II + AI Controls | US | `SEC-001 -> CC6.1` |
| 6 | `ccpa_cpra` | California Consumer Privacy Act / CPRA + ADMT Rules (CCPA/CPRA) | US (CA) | `PRIV-001 -> §1798.100` |
| 7 | `uk_ai_framework` | UK AI Regulatory Principles Framework (AI White Paper, 2023) | UK | `TRANS-001 -> Principle-3` |
| 8 | `dora` | EU Digital Operational Resilience Act (DORA) | EU | `SEC-001 -> Art.6-ICTRiskMgmt` |
| 9 | `china_ai` | China AI Governance Regulations (Algorithmic Recommendations + Deep Synthesis + GenAI + PIPL) | China | `BIAS-001 -> Art.4-Fairness` |

**Assertions:**
- `POST /api/v1/compliance/assess` with `framework: "eu_ai_act"` returns a non-empty assessment
- The governance vector schema (`GET /api/v1/decisions/governance-vector/schema`) has exactly **7** dimensions: `safety`, `security`, `privacy`, `fairness`, `reliability`, `transparency`, `efficiency`

### User Accounts / API Keys (5 accounts)

| # | user_id | role | api_key_prefix | description |
|---|---------|------|----------------|-------------|
| 1 | `dev-alice` | `developer` | `acgs_dev_` | Standard developer integrating acgs-lite SDK |
| 2 | `admin-bob` | `platform_admin` | `acgs_adm_` | Platform administrator managing the API gateway |
| 3 | `compliance-carol` | `compliance_officer` | `acgs_cmp_` | Runs compliance assessments and reviews audit trails |
| 4 | `clinical-dave` | `healthcare_integrator` | `acgs_hci_` | Uses ClinicalGuard for clinical validation |
| 5 | `visitor-eve` | `visitor` | N/A | Browses the landing site only (no API key) |

**Assertions:**
- ClinicalGuard requests with `X-API-Key: acgs_hci_test_key_dave` succeed (HTTP 200)
- ClinicalGuard requests without `X-API-Key` when `CLINICALGUARD_API_KEY` is set return HTTP 401

### Health Check Baseline

| Service | Endpoint | Expected Status | Key Fields |
|---------|----------|-----------------|------------|
| acgs-lite | `GET /health` | `200` | `status: "ok"`, `engine: "ready"` |
| acgs-lite | `GET /stats` | `200` | `audit_entry_count: 8`, `audit_chain_valid: true` |
| ClinicalGuard | `GET /health` | `200` | `status: "ok"`, `rules: 20`, `chain_valid: true`, `constitutional_hash: "608508a9bd224290"` |
| ClinicalGuard | `GET /.well-known/agent.json` | `200` | `name: "ClinicalGuard"`, `skills` array length `3` |
| API Gateway | `GET /health` | `200` | `status: "ok"`, `constitutional_hash: "608508a9bd224290"` |
| API Gateway | `GET /health/live` | `200` | `live: true` |
| API Gateway | `GET /health/startup` | `200` | `ready: true`, `hash_valid: true`, `constitutional_hash: "608508a9bd224290"` |

### Landing Site Pages

| Page | URL | Key Visible Element | Assertion |
|------|-----|---------------------|-----------|
| Home | `/` | Heading `"HTTPS FOR AI"` | Text is visible in the hero section |
| Home | `/` | Button `"PIP INSTALL ACGS"` | Button is visible and clickable |
| Home | `/` | EU AI Act countdown | Nav bar contains text matching `"\d+ DAYS TO EU AI ACT"` |
| Pricing | `/pricing` | Heading `"The Engine Is Free Forever"` | Text is visible |
| Pricing | `/pricing` | 4 tier cards | Exactly 4 pricing cards: `Community`, `Pro`, `Team`, `Enterprise` |
| Pricing | `/pricing` | Pro tier badge | Pro card has `"POPULAR"` badge |
| Resources | `/resources` | Heading `"Technical Arsenal"` | Text is visible |
| Resources | `/resources` | 2 video cards, 2 presentation cards | Exactly 4 resource cards total |
| Demo | `/demo` | Button `"LAUNCH PLAYWRIGHT DEMO"` | Button is visible and links to `/demo/playwright` |

---

## Scenario: `empty`

A fresh ACGS installation with no user-created data. Only built-in defaults and
the landing site content exist. Used to test empty-state handling, zero-count
responses, and first-use onboarding flows.

### Constitutional Rules (0 user-created rules)

- `GET /rules` returns an empty array `[]` (or only built-in defaults if the engine ships with a default constitution)
- No rules with `category: "custom"` exist

**Assertions:**
- `GET /rules` returns HTTP 200 with an array (length 0 or only defaults)

### Validation Actions (0 prior validations)

- Any validation still works against the default engine state

**Assertions:**
- `POST /validate` with `{"action": "hello world", "agent_id": "test"}` returns HTTP 200 with `valid: true`

### Audit Entries (0 entries)

**Assertions:**
- `GET /audit/entries` returns `[]`
- `GET /audit/count` returns `{"count": 0}`
- `GET /audit/chain` returns `{"valid": true, "entry_count": 0}`
- `GET /audit/entries?limit=10&offset=0` returns `[]`

### Clinical Records (0 records)

**Assertions:**
- ClinicalGuard `GET /health` returns `audit_entries: 0` and `chain_valid: true`
- `query_audit_trail: recent 10` returns an empty `entries` array

### Health Checks (services running, no data)

**Assertions:**
- `GET /health` on all services returns HTTP 200 with `status: "ok"`
- `GET /stats` returns `audit_entry_count: 0` and `audit_chain_valid: true`

---

## Scenario: `large`

High-volume stress scenario designed to exceed default pagination limits and
exercise the engine under load. All entity counts are chosen to be above the
default `limit` of 100 for audit queries and above the 20-rule typical constitution.

### Constitutional Rules (120 rules)

Generated by creating rules across all categories and severities:

| Category | Count | Severity Distribution |
|----------|-------|----------------------|
| `safety` | 20 | 8 critical, 6 high, 4 medium, 2 low |
| `privacy` | 20 | 6 critical, 8 high, 4 medium, 2 low |
| `fairness` | 15 | 4 critical, 6 high, 3 medium, 2 low |
| `transparency` | 15 | 2 critical, 4 high, 6 medium, 3 low |
| `security` | 15 | 6 critical, 6 high, 2 medium, 1 low |
| `oversight` | 15 | 3 critical, 5 high, 5 medium, 2 low |
| `general` | 10 | 1 critical, 3 high, 4 medium, 2 low |
| `custom` | 10 | 2 critical, 3 high, 3 medium, 2 low |

Rule ID pattern: `{CATEGORY_PREFIX}-{NNN}` (e.g., `SAFE-001` through `SAFE-020`, `PRIV-001` through `PRIV-020`).

**Assertions:**
- `GET /rules` returns exactly **120** rules
- Filtering by category (if supported) returns the expected count per category
- The governance engine rebuilds successfully after loading 120 rules

### Validation Actions (1000 actions)

Generated programmatically: 500 benign actions and 500 violating actions spread
across all 120 rules.

**Assertions:**
- All 1000 `POST /validate` requests return HTTP 200
- Approximately 500 return `valid: true` and 500 return `valid: false`
- Engine latency remains under 10ms per validation (P99)

### Audit Entries (1000 entries)

One audit entry per validation action.

**Assertions:**
- `GET /audit/count` returns `{"count": 1000}`
- `GET /audit/entries?limit=100&offset=0` returns exactly **100** entries
- `GET /audit/entries?limit=100&offset=900` returns exactly **100** entries
- `GET /audit/entries?limit=100&offset=1000` returns `[]` (past the end)
- `GET /audit/entries?limit=1000&offset=0` returns exactly **1000** entries (max limit)
- `GET /audit/chain` returns `{"valid": true, "entry_count": 1000}`
- Pagination produces no duplicate entries across pages

### Clinical Records (12 records)

Same 6 skill types as the standard scenario, each run twice for consistency verification.

**Assertions:**
- All 12 requests return HTTP 200 with JSON-RPC 2.0 format
- Duplicate requests produce the same `decision` value (deterministic)

### Compliance Framework Mappings (9 frameworks x 120 rules)

Same 9 frameworks as standard. With 120 rules, the compliance matrix is larger.

**Assertions:**
- Compliance assessment completes within 5 seconds for any single framework
- Coverage gap analysis returns a non-empty result for frameworks with unmapped rules

### User Accounts (5 accounts)

Same as standard scenario. No additional users needed for stress testing.

**Assertions:**
- All API key authenticated requests succeed under load
- Rate limiting (if configured) does not block the test user within the test window

---

## Entity Type Reference

Summary of all entity types, their source models, and key fields.

### `constitutional_rule`

**Source model:** `acgs_lite.constitution.rule.Rule` (Pydantic BaseModel)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | `str` (1-50 chars) | yes | Unique rule identifier (e.g., `SAFE-001`) |
| `text` | `str` (1-1000 chars) | yes | Human-readable rule description |
| `severity` | `Severity` enum: `critical`, `high`, `medium`, `low` | yes (default: `high`) | Severity level; `critical` and `high` block execution |
| `keywords` | `list[str]` | no (default: `[]`) | Keywords that trigger rule matching |
| `patterns` | `list[str]` | no (default: `[]`) | Regex patterns that trigger rule matching |
| `category` | `str` | no (default: `"general"`) | Rule category (e.g., `safety`, `privacy`, `fairness`) |
| `subcategory` | `str` | no (default: `""`) | Finer-grained classification within category |
| `workflow_action` | `str` | no (default: `""`) | Action when rule fires: `block`, `block_and_notify`, `require_human_review`, `escalate_to_senior`, `warn` |
| `enabled` | `bool` | no (default: `true`) | Whether rule is active |
| `tags` | `list[str]` | no (default: `[]`) | Cross-cutting governance tags (e.g., `gdpr`, `soc2`) |
| `priority` | `int` | no (default: `0`) | Ordering within same severity (higher = first) |
| `condition` | `dict[str, Any]` | no (default: `{}`) | Activation condition (empty = unconditional) |
| `deprecated` | `bool` | no (default: `false`) | Whether rule is deprecated |
| `replaced_by` | `str` | no (default: `""`) | Successor rule ID if deprecated |
| `valid_from` | `str` (ISO-8601) | no (default: `""`) | Start of temporal validity window |
| `valid_until` | `str` (ISO-8601) | no (default: `""`) | End of temporal validity window |
| `hardcoded` | `bool` | no (default: `false`) | Whether rule is built-in |
| `depends_on` | `list[str]` | no (default: `[]`) | IDs of rules this rule depends on |
| `provenance` | `list[str]` | no (default: `[]`) | Source rule IDs or external references |
| `metadata` | `dict[str, Any]` | no (default: `{}`) | Arbitrary metadata |

### `audit_entry`

**Source model:** `acgs_lite.audit.AuditEntry` (dataclass)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | `str` | yes | Unique entry identifier |
| `type` | `str` | yes | Entry type: `validation`, `override`, `maci_check` |
| `agent_id` | `str` | no (default: `""`) | ID of the agent that triggered the action |
| `action` | `str` | no (default: `""`) | The action text that was validated |
| `valid` | `bool` | no (default: `true`) | Whether the action was allowed |
| `violations` | `list[str]` | no (default: `[]`) | Rule IDs that were violated |
| `constitutional_hash` | `str` | no (default: `""`) | Hash of the constitution at time of validation |
| `latency_ms` | `float` | no (default: `0.0`) | Validation latency in milliseconds |
| `metadata` | `dict[str, Any]` | no (default: `{}`) | Arbitrary metadata |
| `timestamp` | `str` (ISO-8601) | auto-generated | UTC timestamp of the entry |

### `clinical_record`

**Source:** ClinicalGuard A2A JSON-RPC response (`POST /`)

| Field | Type | Description |
|-------|------|-------------|
| `decision` | `str` | `APPROVED`, `CONDITIONALLY_APPROVED`, or `REJECTED` |
| `risk_tier` | `str` | `low`, `medium`, `high`, `critical` |
| `reasoning` | `str` | LLM-generated clinical reasoning |
| `drug_interactions` | `list` | Detected drug interactions (if any) |
| `conditions` | `list` | Conditions for conditional approval |
| `audit_id` | `str` | Audit trail ID (pattern: `HC-YYYYMMDD-XXXXXX`) |

### `compliance_framework_mapping`

**Source:** `acgs_lite.compliance` module classes

| Field | Type | Description |
|-------|------|-------------|
| `framework_id` | `str` | Machine identifier (e.g., `eu_ai_act`, `gdpr`) |
| `framework_name` | `str` | Human-readable name |
| `jurisdiction` | `str` | Geographic jurisdiction |
| `rule_mappings` | `list` | Rule ID to framework article/section mappings |

### `user_account`

**Source:** API Gateway authentication context

| Field | Type | Description |
|-------|------|-------------|
| `user_id` | `str` | Unique user identifier |
| `role` | `str` | One of: `developer`, `platform_admin`, `compliance_officer`, `healthcare_integrator`, `visitor` |
| `api_key_prefix` | `str` | API key prefix for identification |

### `validation_action`

**Source:** `POST /validate` request/response pair

| Field | Type | Description |
|-------|------|-------------|
| `action` | `str` | The action text to validate |
| `agent_id` | `str` | The agent submitting the action |
| `context` | `dict` | Contextual metadata for conditional rules |
| `valid` | `bool` | Whether the action was allowed |
| `violations` | `list[str]` | Rule IDs that were violated |
| `audit_id` | `str` | Audit trail entry ID |
| `constitutional_hash` | `str` | Always `608508a9bd224290` |
