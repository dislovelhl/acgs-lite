# CLAUDE.md

Compatibility note for tools that still read `CLAUDE.md`.

`AGENTS.md` is the canonical repo guide. Start there first, then read the nearest scoped
`AGENTS.md` for the package you are changing.

## Documentation Entry Points

Use the shortest path to the docs for the directory you are changing:

- [docs/README.md](docs/README.md) - repo-wide documentation map
- [docs/repo-map.md](docs/repo-map.md) - directory-by-directory map of repo-owned docs
- [packages/acgs-core/README.md](packages/acgs-core/README.md) - `acgs` namespace package and audit/policy layer
- [packages/acgs-lite/README.md](packages/acgs-lite/README.md) - public Python package entry point
- [packages/acgs-lite/docs/index.md](packages/acgs-lite/docs/index.md) - package guides and CLI/compliance docs
- [packages/acgs.ai/README.md](packages/acgs.ai/README.md) - SvelteKit frontend package
- [packages/acgs-dashboard/README.md](packages/acgs-dashboard/README.md) - governance dashboard package
- [packages/enhanced_agent_bus/README.md](packages/enhanced_agent_bus/README.md) - bus service overview and operations
- [packages/acgs_auth0/README.md](packages/acgs_auth0/README.md) - Auth0 Token Vault governance bridge
- [packages/clinicalguard/README.md](packages/clinicalguard/README.md) - healthcare A2A demo/service
- [packages/constitutional_swarm/README.md](packages/constitutional_swarm/README.md) - governed multi-agent package
- [packages/mhc/README.md](packages/mhc/README.md) - short-import alias package
- [src/core/services/api_gateway/README.md](src/core/services/api_gateway/README.md) - API gateway service
- [workers/governance-proxy/README.md](workers/governance-proxy/README.md) - Cloudflare Worker governance proxy
- [hackathon-demo/README.md](hackathon-demo/README.md) and [demo/README.md](demo/README.md) - demos and submission assets
- [rust/README.md](rust/README.md) - Rust/PyO3 engine notes

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
  - Svelte: `cd packages/acgs.ai && npm run check && npm run lint`
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

## CI/CD Debugging

- Always reproduce the failure locally before pushing a fix
- Never iterate via CI. Run `make lint && make test-quick` locally first
- If local passes but CI fails, the delta is environment (Python version, deps, import mode)
- Single push only per fix attempt. Do not enter commit-push-wait-fix loops
- Narrow test scope incrementally: failing test file first, then package, then full suite
- When fixing CI failures, identify the root cause before applying ANY fix
- Do not skip or exclude tests without explicit user approval

## Python Packaging

Before publishing to PyPI:
1. No duplicate keys in pyproject.toml
2. All URLs are valid and point to correct repos
3. _compat/shim packages are included
4. Run `python -m build` locally before publishing
5. Check git history for large files: `git rev-list --objects --all | git cat-file --batch-check='%(objecttype) %(objectsize) %(rest)' | awk '/^blob/ && $2>1048576 {print $2,$3}' | head -5`
6. Verify ruff auto-fixes don't introduce untracked module imports

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
