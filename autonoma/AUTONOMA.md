---
app_name: ACGS (AI Constitutional Governance System)
app_description: >
  ACGS is an AI governance infrastructure platform that validates AI agent actions
  against constitutional rules, produces tamper-evident audit trails, and maps
  decisions to 9 regulatory compliance frameworks. It consists of a Python SDK
  (acgs-lite), a FastAPI API gateway, a Svelte marketing/landing site
  (acgs.ai), and a healthcare-specific A2A agent (ClinicalGuard).
core_flows:
  - feature: Governance Validation
    description: Submit an action to the governance engine and receive an ALLOW or DENY decision with rule attribution and audit trail entry
    core: true
  - feature: Constitution Management (Rules CRUD)
    description: Create, read, update, and delete constitutional rules that define what AI agents are allowed to do
    core: true
  - feature: ClinicalGuard Clinical Validation
    description: Send a clinical action (medication order, care plan change) to the healthcare A2A agent and receive a safety decision with drug interaction checks and HIPAA compliance
    core: true
  - feature: Audit Trail Inspection
    description: Query the tamper-evident audit log for past decisions, verify chain integrity, and retrieve entry counts
    core: true
feature_count: 24
skill_count: 12
---

# ACGS Knowledge Base for Autonoma E2E Test Planning

## Application Overview

ACGS (AI Constitutional Governance System) is a governance infrastructure platform for AI agents. It provides constitutional validation (checking agent actions against a set of rules), tamper-evident audit trails, and compliance mapping to regulatory frameworks such as EU AI Act, GDPR, HIPAA, NIST AI RMF, and SOC 2.

The platform has four main surfaces:

1. **acgs-lite Governance Server** -- a FastAPI service exposing validation, rules CRUD, and audit endpoints
2. **ACGS-2 API Gateway** -- a production FastAPI gateway with SSO, rate limiting, compliance, data subject rights, and x402 pay-per-call governance endpoints
3. **ClinicalGuard** -- a Starlette-based A2A (Agent-to-Agent) healthcare agent that validates clinical actions
4. **Propriety AI Landing Site** -- a SvelteKit marketing website with home, pricing, demo, and resources pages

## User Roles

| Role | Description |
|------|-------------|
| Developer | Integrates acgs-lite SDK into their AI agent, uses the GovernedAgent wrapper, writes YAML constitutions |
| Platform Admin | Manages the API gateway, configures SSO providers, sets autonomy tiers, monitors health |
| Compliance Officer | Runs compliance assessments, reviews audit trails, generates erasure certificates |
| Healthcare Integrator | Uses ClinicalGuard to validate clinical decisions, runs HIPAA checks, queries audit trails |
| Visitor | Browses the Propriety AI landing site, views pricing, downloads resources |

## Navigation Structure

### Propriety AI Landing Site (SvelteKit)

| Destination | URL Path | Description |
|-------------|----------|-------------|
| Home | `/` | Hero section ("HTTPS for AI"), problem statement, code examples, compliance receipt stats, observability, regulatory frameworks table, architecture features, pricing teaser |
| Pricing | `/pricing` | Four tiers: Community (Free), Pro ($299/mo), Team ($999/mo), Enterprise (Custom) |
| Demo | `/demo` | Entry page with "LAUNCH PLAYWRIGHT DEMO" button |
| Playwright Demo | `/demo/playwright` | Placeholder page for the E2E demonstration suite |
| Resources | `/resources` | Video downloads (intro, MACI architecture) and presentation downloads (crypto, trust) |

**Navigation bar** (visible on all pages): ACGS logo (links to home), FRAMEWORKS (anchor link to `/#frameworks`), HOW IT WORKS (anchor link to `/#works`), PRICING (links to `/pricing`), RESOURCES (links to `/resources`). Right side shows a countdown: "N DAYS TO EU AI ACT".

**Footer** (visible on all pages): Large "pip install acgs" link to PyPI, constitutional hash display, local time clock, links to PyPI and GitHub.

### acgs-lite Governance Server (FastAPI)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/validate` | POST | Validate an action against the constitution. Body: `{"action": "...", "agent_id": "...", "context": {...}}`. Returns decision with `valid`, `violations`, `audit_id` |
| `/rules` | GET | List all constitutional rules with id, text, severity, keywords, patterns, category |
| `/rules/{rule_id}` | GET | Get a single rule by ID |
| `/rules` | POST | Create a new rule. Body includes id, text, severity, keywords, patterns |
| `/rules/{rule_id}` | PUT | Update an existing rule |
| `/rules/{rule_id}` | DELETE | Delete a rule |
| `/audit/entries` | GET | List audit entries. Query params: `limit`, `offset`, `agent_id` |
| `/audit/chain` | GET | Verify audit chain integrity. Returns `{"valid": bool, "entry_count": int}` |
| `/audit/count` | GET | Get total audit entry count |
| `/health` | GET | Health check. Returns `{"status": "ok", "engine": "ready"}` |
| `/stats` | GET | Engine stats including audit entry count and chain validity |

### ACGS-2 API Gateway (FastAPI, production)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Basic health check with constitutional hash |
| `/health/live` | GET | Kubernetes liveness probe |
| `/health/ready` | GET | Readiness probe with database, Redis, OPA, constitutional hash checks |
| `/health/startup` | GET | Startup probe with constitutional hash validation |
| `/api/v1/decisions/{id}/explain` | GET | Retrieve structured decision explanation with factor attribution |
| `/api/v1/decisions/explain` | POST | Generate a decision explanation from message, verdict, and context |
| `/api/v1/decisions/governance-vector/schema` | GET | Get the 7-dimensional governance vector schema |
| `/api/v1/data-subject/access` | POST | GDPR Article 15 data subject access request |
| `/api/v1/data-subject/erasure` | POST | GDPR Article 17 right-to-be-forgotten request |
| `/api/v1/data-subject/erasure/{id}` | GET | Check erasure request status |
| `/api/v1/data-subject/erasure/{id}/process` | POST | Execute an erasure request |
| `/api/v1/data-subject/erasure/{id}/certificate` | GET | Generate erasure certificate |
| `/api/v1/data-subject/classify` | POST | Classify data for PII categories |
| `/api/v1/compliance/assess` | POST | Run compliance assessment against regulatory frameworks |
| `/api/v1/gateway/feedback` | POST | Submit governance feedback |
| `/api/v1/sso/oidc/login` | GET | SSO login via OIDC |
| `/api/v1/sso/saml/login` | GET | SSO login via SAML |
| `/api/v1/admin/autonomy-tiers` | GET/POST | Manage agent autonomy tier assignments |
| `/api/v1/admin/evolution/operator-control` | GET/POST | Self-evolution pause/resume/stop |
| `/x402/validate` | POST | Pay-per-call constitutional validation |
| `/x402/pricing` | GET | x402 pricing information |
| `/x402/health` | GET | x402 subsystem health |

### ClinicalGuard A2A Agent (Starlette)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/.well-known/agent.json` | GET | Agent card (name, description, skills, capabilities) |
| `/health` | GET | Health check with rule count, audit entry count, chain validity |
| `/` | POST | A2A task handler (JSON-RPC). Method: `tasks/send`. Dispatches to skills by name prefix |

**Skills** (invoked via the POST `/` endpoint):
- `validate_clinical_action` -- Validate a medication order or care plan change against the Healthcare AI Constitution
- `check_hipaa_compliance` -- Run HIPAA checklist against an agent system description
- `query_audit_trail` -- Query audit log by ID or recent entries

## Core Flows (Detailed)

### 1. Governance Validation (Core)

This is the primary reason the product exists. A developer sends an action string to the governance engine and gets back a decision.

**Steps:**
1. Send a POST request to `/validate` with `{"action": "some action text", "agent_id": "my-agent"}`
2. The engine scans the action against all enabled constitutional rules
3. If the action matches a rule's keywords or patterns, the rule fires
4. The engine returns a result with `valid` (true/false), `violations` (list of rule IDs), and the entry is recorded in the audit trail
5. The response includes `audit_id` for traceability

**Conditional behavior:**
- If `action` is empty or missing, the server returns HTTP 422
- If `agent_id` is not a string, the server returns HTTP 422
- If `context` is not an object, the server returns HTTP 422
- Critical-severity rule violations cause the action to be blocked

### 2. Constitution Management / Rules CRUD (Core)

Users define what their AI agents are allowed to do by creating constitutional rules.

**Steps:**
1. GET `/rules` to see all existing rules
2. POST `/rules` with `{"id": "SAFE-001", "text": "No financial advice", "severity": "critical", "keywords": ["invest", "buy stocks"]}` to create a rule
3. GET `/rules/SAFE-001` to verify the rule was created
4. PUT `/rules/SAFE-001` with updated fields to modify the rule
5. DELETE `/rules/SAFE-001` to remove the rule

**Conditional behavior:**
- Creating a rule with an existing ID returns HTTP 409
- Getting a non-existent rule returns HTTP 404
- Deleting a non-existent rule returns HTTP 404
- Missing `id` field returns HTTP 422
- After any rule change, the engine is rebuilt automatically

### 3. ClinicalGuard Clinical Validation (Core)

Healthcare integrators validate proposed clinical actions against a 20-rule Healthcare AI Constitution.

**Steps:**
1. Send a POST to `/` with JSON-RPC body: `{"jsonrpc": "2.0", "id": 1, "method": "tasks/send", "params": {"message": {"parts": [{"text": "validate_clinical_action: Patient on Warfarin. Propose Aspirin 325mg daily."}]}}}`
2. The agent parses the skill name from the text prefix
3. The governance engine validates against healthcare-specific rules (drug interactions, PHI detection, dosing limits)
4. Returns a JSON-RPC result with decision (APPROVED/CONDITIONALLY_APPROVED/REJECTED), risk tier, reasoning, and audit ID

**Conditional behavior:**
- Missing `X-API-Key` header when `CLINICALGUARD_API_KEY` is set returns 401
- Request body larger than 64KB returns 413
- Action text longer than 10,000 characters returns 400
- Invalid JSON returns 400
- Unknown method (not `tasks/send`) returns method-not-found error
- Unknown skill name returns a helpful error with available skills list

### 4. Audit Trail Inspection (Core)

Every governance decision is recorded in a tamper-evident, SHA-256-chained audit log. Users can query entries and verify integrity.

**Steps:**
1. GET `/audit/entries?limit=50&offset=0` to list recent entries
2. GET `/audit/entries?agent_id=my-agent` to filter by agent
3. GET `/audit/chain` to verify the hash chain has not been tampered with
4. GET `/audit/count` to get total entry count

**Conditional behavior:**
- `limit` must be between 1 and 1000
- `offset` must be >= 0
- Chain verification returns `{"valid": true, "entry_count": N}` when intact, `{"valid": false, ...}` when tampered

## Common UI Patterns

### Landing Site

- **Scroll animations**: Sections fade in as they enter the viewport (IntersectionObserver with 0.15 threshold)
- **3D hero element**: A Three.js crystal rendered via `@threlte/core` Canvas, visible on all pages as a background element
- **Marquee text**: Horizontally scrolling text strips showing regulatory framework names and integration names
- **Hover effects on marquee**: Text fills from outline to solid white on hover
- **Copy-to-clipboard**: The "PIP INSTALL ACGS" button copies `pip install acgs` to clipboard
- **EU AI Act countdown**: The nav bar shows a live countdown to the EU AI Act deadline (August 2, 2026)
- **Live clock**: The footer displays the user's local time, updated every second
- **Pricing highlight**: The "Pro" tier has a blue accent border and "POPULAR" badge

### API Responses

- Every API response includes a `constitutional_hash` field (`608508a9bd224290`)
- Audit entries include SHA-256 chain hashes for tamper evidence
- Error responses follow a consistent format: `{"error": "error_code", "message": "...", "constitutional_hash": "..."}`
- ClinicalGuard uses JSON-RPC 2.0 format for all A2A communication

## Skills Index

| Skill File | Purpose |
|------------|---------|
| `navigate-landing-home.md` | Navigate to the landing page home |
| `navigate-landing-pricing.md` | Navigate to the pricing page |
| `navigate-landing-resources.md` | Navigate to the resources page |
| `navigate-landing-demo.md` | Navigate to the demo page |
| `api-validate-action.md` | Submit a governance validation request |
| `api-manage-rules.md` | Create, read, update, and delete constitutional rules |
| `api-query-audit.md` | Query the audit trail and verify chain integrity |
| `api-health-check.md` | Check service health across all endpoints |
| `clinicalguard-validate.md` | Submit a clinical validation via A2A protocol |
| `clinicalguard-hipaa-check.md` | Run a HIPAA compliance check |
| `clinicalguard-audit-query.md` | Query the ClinicalGuard audit trail |
| `api-data-subject-rights.md` | Exercise GDPR/CCPA data subject rights |
