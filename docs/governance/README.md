# Governance Policy Map

This document maps ACGS-Lite maintainer rules to executable checks and review evidence. It is intentionally lightweight: every rule should have a corresponding policy test, CI signal, or review artifact that an external contributor can reproduce locally.

## Rules -> Tests -> Evidence

| Rule ID | Maintainer rule | Enforced by | Evidence |
|---|---|---|---|
| R-001 | Sensitive material must not be introduced in a contribution. | `tests/policy/test_no_secrets_in_diff.py` | Policy CI log showing no findings. |
| R-002 | Public API removals or breaking signature changes require a migration note. | `tests/policy/test_api_breaking_changes_require_notice.py` | Changed `docs/migrations/<version>.md` file or an explicit non-breaking diff. |
| R-003 | PRs must provide structured governance evidence: risk, verification, rule mapping, and rollback. | `.github/pull_request_template.md`; `tests/policy/test_governance_tags_present.py` | Completed PR body and passing policy CI. |
| R-004 | Contributors must certify contribution rights and license compatibility before merge. | PR rights checkboxes; `docs/governance/CLA.md`; policy CI | Checked contribution-rights attestations in the PR body. |
| R-005 | Maintainers and contributors must be able to reproduce the quality gates locally. | `make policy`; `docs/contributing/repro.md`; existing lint/type/test targets | Local command transcript or CI artifacts. |

## Maintainer policy

ACGS-Lite uses a fail-closed governance posture for both runtime behavior and maintainer workflow. A contribution that cannot provide evidence should not be merged until the evidence gap is closed or explicitly documented by a maintainer.

Policy tests are not a replacement for human review. They create a minimum evidence floor so reviewers can focus on design, compatibility, security posture, and runtime governance semantics.

## Evidence retention

For each merged PR, keep the following evidence in the GitHub PR record:

1. Completed PR template.
2. Passing CI checks, including the policy job.
3. Reviewer approval for code-owned paths.
4. Any migration notes, audit logs, screenshots, benchmarks, or reproduction transcripts referenced by the PR.

## ACGS-Lite runtime alignment

These development-time rules are designed to mirror the same properties ACGS-Lite enforces at runtime:

- deterministic gates before execution,
- fail-closed behavior for missing or malformed evidence,
- separation between proposer and reviewer responsibilities,
- auditable records for later inspection.
