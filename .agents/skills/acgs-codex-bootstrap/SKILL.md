---
name: acgs-codex-bootstrap
description: Validate the repo-local Codex setup for acgs-clean. Use when checking that active repo guidance, skills, and `.codex/config.toml` are present and coherent, or before deeper Codex work. Do not use for normal code changes that do not touch the Codex workspace itself.
---

# ACGS Codex Bootstrap

Use this skill for repo-local Codex readiness only.

When to use:
- the task changes `AGENTS.md`, `.codex/config.toml`, or `.agents/skills/`
- you need to verify the checked-in Codex workspace before broader work
- `make codex-doctor` should pass before continuing

When not to use:
- ordinary feature work in application code
- generic repo verification unrelated to the Codex workspace

Canonical files:
- `AGENTS.md`
- `.codex/config.toml`
- `.agents/skills/README.md`
- `.agents/skills/acgs-codex-bootstrap/SKILL.md`
- `.agents/skills/package-health-governance/SKILL.md`
- `scripts/codex-doctor.sh`

Verification:
```bash
make codex-doctor
```

Keep the doctor deterministic and local:
- no network dependency
- no broad repo lint or test sweep
- fail with a concrete missing-file or parse error
