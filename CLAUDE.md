# CLAUDE.md

Compatibility note for tools that still read `CLAUDE.md`.

`AGENTS.md` is the canonical repo guide. Start there first, then read the nearest scoped
`AGENTS.md` for the package you are changing.

## Commands

```bash
make test-quick
make lint
make format
make codex-doctor
```

Use package-specific commands when possible:
- `make test-lite`
- `make test-bus`
- `make test-gw`
- `make health-overview`

## Verification

- repository pytest runs must include `--import-mode=importlib`
- run the narrowest meaningful verification first
- expand to broader checks when shared, security-sensitive, or governance-critical paths change
- all three gates must pass before work is complete: `make lint`, `make test-quick`, package tests
- do not hand off code without reporting what you ran and what still remains unverified

## Post-Codex Fixes

When fixing code issues introduced by Codex/omx:
- run the affected package test suite **before** starting fixes (baseline)
- fix one regression at a time, re-run package tests after each fix
- run `make test-quick` after all fixes to confirm no new regressions
- never batch Codex regression fixes without test gates between them

## Refactoring

- Never batch-refactor (exception narrowing, type changes, import rewrites) across 20+ files without incremental verification
- Work in batches of 5–10 files, run the affected package tests after each batch, commit passing states
- If a batch causes >5 test failures, revert it and try a more conservative approach
- Sub-agents may explore/analyze in parallel, but mutations flow through one sequential path with test gates

## Code Quality (from insights analysis)

- After making multi-file edits, always run the full test suite before committing
  - ACGS: `make lint && make test-quick`
  - Svelte: `cd packages/propriety-ai && npm run check && npm run lint`
  - Never commit without a green test run
- When editing JSX/TSX/Svelte files, run the build after changes and fix syntax errors before considering the task complete

## ACGS-Specific Conventions (from insights analysis)

- Severity enum: use `.value` for comparisons (not `.name`)
- Violation objects: use `.rule_text` (not `.message`)
- Audit logging: use `record()` (not `append()`)
- Constitutional hash: `608508a9bd224290` — flag any other value as stale
- GovernedAgent retry: configured via `max_retries` parameter
- TemplateRegistry: built-in templates are protected from overwrite

## Constraints

- use canonical enhanced-agent-bus namespaces
- keep governance, auth, and policy behavior fail-closed
- never self-validate agent output in violation of MACI role separation
- do not rely on unchecked PM2 entries as operational truth

## Skill routing

When the user's request matches an available skill, ALWAYS invoke it using the Skill
tool as your FIRST action. Do NOT answer directly, do NOT use other tools first.
The skill has specialized workflows that produce better results than ad-hoc answers.

Key routing rules:
- Product ideas, "is this worth building", brainstorming → invoke office-hours
- Bugs, errors, "why is this broken", 500 errors → invoke investigate
- Ship, deploy, push, create PR → invoke ship
- QA, test the site, find bugs → invoke qa
- Code review, check my diff → invoke review
- Update docs after shipping → invoke document-release
- Weekly retro → invoke retro
- Design system, brand → invoke design-consultation
- Visual audit, design polish → invoke design-review
- Architecture review → invoke plan-eng-review
- Save progress, checkpoint, resume → invoke checkpoint
- Code quality, health check → invoke health
