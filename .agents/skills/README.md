## Active Repo Skills

This directory is the active repo-local Codex skill surface for `acgs-clean`.

Retained skills:
- `acgs-codex-bootstrap/`
  Repo-local Codex readiness checks and workspace sanity validation.
- `package-health-governance/`
  Package health manifest maintenance and reporting for ACGS packages.

Rules:
- Keep active skills repo-specific and narrowly scoped.
- Keep one skill = one job.
- Prefer instruction-only skills. Add scripts only when they provide deterministic checks or
  integrate with checked-in tooling.
- Archive retired experiments or third-party bundles under `.agents/archive/`; do not leave them
  active in `.agents/skills/`.
