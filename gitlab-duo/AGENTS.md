# ACGS Constitutional Governance Agent

This directory contains the GitLab Duo Agent Platform configuration for the
**acgs-lite** constitutional governance agent. The agent automatically reviews
merge requests against constitutional governance rules, enforces separation
of powers, and checks EU AI Act compliance.

## What the agent does

The ACGS governance agent attaches to your GitLab merge request workflow and
performs three categories of checks on every MR.

### 1. Constitutional Validation

Every MR diff is evaluated against the ACGS default constitution (6 rules):

| Rule     | Severity   | What it catches                                      |
|----------|------------|------------------------------------------------------|
| ACGS-001 | CRITICAL   | Self-modification of validation or governance logic   |
| ACGS-002 | HIGH       | Missing audit trail entries for new code paths        |
| ACGS-003 | CRITICAL   | Unauthorized data access or privilege escalation      |
| ACGS-004 | CRITICAL   | MACI violation: proposer == validator (self-approval) |
| ACGS-005 | HIGH       | Governance changes without constitutional hash verify |
| ACGS-006 | CRITICAL   | Hardcoded secrets, API keys, PII in source code       |

CRITICAL rules block the merge. HIGH rules require human review.
MEDIUM and LOW rules produce warnings but do not block.

The constitutional hash (`cdd01ef066bc6cf2`) is verified on every run to
ensure the ruleset has not been tampered with.

### 2. MACI Separation of Powers

MACI (Multi-Agent Constitutional Integrity) enforces that no single person
controls both proposal and approval:

- The **MR author** is the proposer.
- **Reviewers and approvers** are validators.
- If the author is also listed as a reviewer or sole approver, the agent
  flags a MACI violation (ACGS-004).

Role permissions enforced by the MACI subsystem:

| Role      | Allowed actions                    | Denied actions                |
|-----------|------------------------------------|-------------------------------|
| Proposer  | propose, draft, suggest, amend     | validate, execute, approve    |
| Validator | validate, review, audit, verify    | propose, execute, deploy      |
| Executor  | execute, deploy, apply, run        | validate, propose, approve    |
| Observer  | read, query, export, observe       | propose, validate, execute    |

### 3. EU AI Act Compliance

When MR changes involve AI/ML systems, the agent checks compliance with
the EU AI Act (high-risk provisions effective **2026-08-02**):

- **Article 6 + Annex III Risk Classification**: Determines whether the
  system falls into UNACCEPTABLE, HIGH_RISK, LIMITED, or MINIMAL risk.
  High-risk domains include employment, credit scoring, law enforcement,
  critical infrastructure, and biometric identification.

- **Article 12 (Record-Keeping)**: Verifies that AI system operations
  produce adequate logging for post-deployment auditing.

- **Article 13 (Transparency)**: Checks for transparency disclosures
  (system purpose, capabilities, limitations, contact information).

- **Article 14 (Human Oversight)**: Ensures high-impact AI decisions have
  human-in-the-loop gating mechanisms.

## How to interact with the agent

### Automatic triggers

The agent runs automatically on:
- MR creation
- MR diff updates (new commits pushed)
- Pipeline execution in the `governance` stage

### Manual triggers

- **@mention in MR comments**: Tag the agent in a comment to request a
  governance re-review or ask governance questions.
- **Assign as reviewer**: Add the agent's bot user as an MR reviewer to
  trigger a full governance review.

### Reading the governance report

The agent posts a structured report as an MR note containing:

1. **Decision**: APPROVE, FLAG, or BLOCK
2. **Rule-by-rule results**: Pass/fail for each ACGS rule
3. **MACI check**: Whether separation of powers is maintained
4. **EU AI Act status**: Risk classification and article compliance
5. **Recommended actions**: What to fix before re-review

### Decision criteria

| Decision  | Condition                                                   |
|-----------|-------------------------------------------------------------|
| APPROVE   | Zero blocking violations, MACI passes, no secrets detected  |
| FLAG      | Non-blocking warnings only (medium/low severity)            |
| BLOCK     | Any CRITICAL/HIGH violation, MACI failure, or secret found  |

## Files in this directory

| File                             | Purpose                                   |
|----------------------------------|-------------------------------------------|
| `flows/governance-agent.yaml`    | External agent flow (Docker-based)        |
| `flows/governance-review.yaml`   | AI Catalog custom flow (ambient tools)    |
| `agent-config.yml`               | Runner execution configuration            |
| `.gitlab-ci.yml`                 | CI/CD pipeline with governance stage      |
| `chat-rules.md`                  | Duo Chat custom rules                     |
| `AGENTS.md`                      | This file                                 |

## Setup

### Prerequisites

- GitLab Premium or Ultimate with Duo Enterprise enabled
- A GitLab Runner with Docker executor
- Python 3.11+ available in the runner image

### Installation

1. Copy this `gitlab-duo/` directory to your project root (or keep it as a
   subdirectory and reference the flow paths in your CI configuration).

2. Register the external agent flow:
   ```bash
   glab duo agent register --flow flows/governance-agent.yaml
   ```

3. Add the governance stage to your existing `.gitlab-ci.yml`:
   ```yaml
   include:
     - local: 'gitlab-duo/.gitlab-ci.yml'
   ```

4. (Optional) Set project-level CI/CD variables:
   - `ACGS_CONSTITUTION_PATH`: Path to a custom constitution YAML (defaults
     to the built-in ACGS default rules).
   - `ACGS_STRICT_MODE`: Set to `true` to block MR merges on any violation
     (default: `false`, which allows warnings).
   - `ACGS_EU_AI_ACT_CHECK`: Set to `true` to enable EU AI Act compliance
     checking (default: `false`).

### Custom constitutions

To use a custom constitution instead of the ACGS defaults, create a YAML
file following this schema:

```yaml
name: my-org-constitution
version: "1.0.0"
description: "Organization-specific governance rules"
rules:
  - id: ORG-001
    text: "All database migrations require DBA review"
    severity: high
    keywords: ["migration", "ALTER TABLE", "DROP TABLE"]
    category: database
    workflow_action: require_human_review
```

Set the `ACGS_CONSTITUTION_PATH` CI variable to point to your file.

## Architecture

```
MR Event
  |
  v
GitLab Duo Agent Platform
  |
  v
governance-agent.yaml (external flow)
  |
  +-- reads AI_FLOW_CONTEXT (MR metadata + diffs)
  +-- reads AI_FLOW_INPUT (user request, if @mentioned)
  +-- reads AI_FLOW_EVENT (trigger type)
  |
  v
acgs-lite GovernanceEngine
  |
  +-- Constitution.default() (6 rules, hash cdd01ef066bc6cf2)
  +-- engine.validate(action) for each diff
  +-- MACIEnforcer.check_no_self_validation(author, reviewer)
  +-- governance_decision_report(action, context, rules)
  +-- score_context_risk(context)
  |
  v
Structured Governance Report
  |
  v
MR Note (via GitLab API / glab CLI)
```

## Troubleshooting

**Agent does not trigger on MR creation:**
Verify the flow is registered (`glab duo agent list`) and the runner has
network access to the GitLab API.

**Constitutional hash mismatch error:**
The hash `cdd01ef066bc6cf2` is tied to the default ACGS constitution. If
you have modified rules, the hash will change. Update `ACGS_CONSTITUTIONAL_HASH`
in `agent-config.yml` to match.

**MACI false positive on bot accounts:**
Bot accounts that create MRs and are auto-assigned as reviewers will trigger
MACI violations. Exclude bot usernames by adding them to the `ACGS_MACI_EXEMPT`
CI variable (comma-separated list).

**EU AI Act checks not running:**
Set `ACGS_EU_AI_ACT_CHECK=true` in project CI/CD variables. The check only
activates when the MR modifies files matching AI/ML path patterns
(`models/`, `training/`, `inference/`, `scoring/`).
