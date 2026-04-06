# ACGS Repo Map

This file is the directory-level map for the repo-owned parts of `acgs-clean`.

Use it when you know the part of the system you want to touch, but not the best entry document for
that directory yet.

## Top-Level Directories

| Directory | Start here | Purpose |
| --- | --- | --- |
| `.` | [../README.md](../README.md) | Product-level overview and public quickstart |
| `.agents/` | [../.agents/skills/README.md](../.agents/skills/README.md) | Repo-local Codex skills and archived internal skill material |
| `.learnings/` | [../.learnings/LEARNINGS.md](../.learnings/LEARNINGS.md) | Session learnings and retained observations |
| `.remember/` | [../.remember/now.md](../.remember/now.md) | Local scratch memory and session carry-forward notes |
| `autonoma/` | [../autonoma/AUTONOMA.md](../autonoma/AUTONOMA.md) | E2E planning knowledge base, skill flows, and scenario fixtures |
| `autoresearch/` | [../autoresearch/AGENTS.md](../autoresearch/AGENTS.md) | Experiment-loop work for autoresearch and training methodology |
| `claudedocs/` | [../claudedocs/INDEX.md](../claudedocs/INDEX.md) | Consolidated API, research, and architecture reference docs |
| `constitutional-sentinel-demo/` | [../constitutional-sentinel-demo/README.md](../constitutional-sentinel-demo/README.md) | Demo harness for the constitutional sentinel flow |
| `demo/` | [../demo/README.md](../demo/README.md) | GitLab hackathon demo assets and recording workflow |
| `docs/` | [README.md](README.md) | Main engineering docs, strategy, launch, and reference guides |
| `eval_results/` | [../eval_results/summary.md](../eval_results/summary.md) | Eval output summaries |
| `examples/` | [../examples/governed_agents_web/README.md](../examples/governed_agents_web/README.md) | Standalone example applications |
| `generated-hooks/` | [../generated-hooks/validate-tasks-down-with-codex/README.md](../generated-hooks/validate-tasks-down-with-codex/README.md) | Generated workflow hooks and installation notes |
| `gitlab-duo/` | [../gitlab-duo/AGENTS.md](../gitlab-duo/AGENTS.md) | GitLab Duo-specific guidance and chat rules |
| `hackathon-demo/` | [../hackathon-demo/README.md](../hackathon-demo/README.md) | Governed Agent Vault demo using `acgs-auth0` |
| `memory/` | [../memory/2026-03-30.md](../memory/2026-03-30.md) | Archived project memory snapshots |
| `packages/` | [README.md](README.md) | Monorepo packages and deployable services |
| `plans/` | [../plans/openai-cookbook-integration-plan.md](../plans/openai-cookbook-integration-plan.md) | One-off plan artifacts |
| `research/` | [../research/README.md](../research/README.md) | Focused research documents |
| `rust/` | [../rust/README.md](../rust/README.md) | Rust/PyO3 governance engine notes |
| `src/` | [README.md](README.md) | Core services and shared runtime code |
| `workers/` | [../workers/governance-proxy/README.md](../workers/governance-proxy/README.md) | Edge worker surfaces |

## Packages and Services

| Directory | Start here | Purpose |
| --- | --- | --- |
| `packages/acgs-core/` | [../packages/acgs-core/README.md](../packages/acgs-core/README.md) | `acgs` namespace package and persistent audit/policy layer |
| `packages/acgs-dashboard/` | [../packages/acgs-dashboard/README.md](../packages/acgs-dashboard/README.md) | React + Vite governance dashboard |
| `packages/acgs-deliberation/` | [../packages/acgs-deliberation/README.md](../packages/acgs-deliberation/README.md) | Deliberation package plus scoped agent guidance |
| `packages/acgs-lite/` | [../packages/acgs-lite/README.md](../packages/acgs-lite/README.md) | Main public governance package |
| `packages/acgs-lite/design/` | [../packages/acgs-lite/design/README.md](../packages/acgs-lite/design/README.md) | Design and product decision notes for `acgs-lite` |
| `packages/acgs-lite/docs/` | [../packages/acgs-lite/docs/index.md](../packages/acgs-lite/docs/index.md) | `acgs-lite` deep-dive docs |
| `packages/acgs-lite/examples/` | [../packages/acgs-lite/examples/README.md](../packages/acgs-lite/examples/README.md) | Example projects for `acgs-lite` |
| `packages/acgs-lite/hackathon/` | [../packages/acgs-lite/hackathon/README.md](../packages/acgs-lite/hackathon/README.md) | Hackathon assets and submission docs |
| `packages/acgs.ai/` | [../packages/acgs.ai/README.md](../packages/acgs.ai/README.md) | SvelteKit frontend for the public site and demos |
| `packages/acgs_auth0/` | [../packages/acgs_auth0/README.md](../packages/acgs_auth0/README.md) | Auth0 Token Vault governance bridge |
| `packages/clinicalguard/` | [../packages/clinicalguard/README.md](../packages/clinicalguard/README.md) | Healthcare A2A agent/service |
| `packages/clinicalguard/docs/` | [../packages/clinicalguard/docs/README.md](../packages/clinicalguard/docs/README.md) | ClinicalGuard one-pager and deployment docs |
| `packages/constitutional_swarm/` | [../packages/constitutional_swarm/README.md](../packages/constitutional_swarm/README.md) | Governed multi-agent package |
| `packages/enhanced_agent_bus/` | [../packages/enhanced_agent_bus/README.md](../packages/enhanced_agent_bus/README.md) | Bus service and platform runtime |
| `packages/enhanced_agent_bus/docs/` | [../packages/enhanced_agent_bus/docs/README.md](../packages/enhanced_agent_bus/docs/README.md) | Bus architecture and cleanup-plan docs |
| `packages/enhanced_agent_bus/agent_health/` | [../packages/enhanced_agent_bus/agent_health/README.md](../packages/enhanced_agent_bus/agent_health/README.md) | Agent health API surface |
| `packages/enhanced_agent_bus/collaboration/` | [../packages/enhanced_agent_bus/collaboration/README.md](../packages/enhanced_agent_bus/collaboration/README.md) | Collaboration module docs |
| `packages/enhanced_agent_bus/rust/` | [../packages/enhanced_agent_bus/rust/README.md](../packages/enhanced_agent_bus/rust/README.md) | Rust lane inside the bus package |
| `packages/mhc/` | [../packages/mhc/README.md](../packages/mhc/README.md) | Short-import alias package for `constitutional-swarm` |

## Core Services and Shared Code

| Directory | Start here | Purpose |
| --- | --- | --- |
| `src/core/services/api_gateway/` | [../src/core/services/api_gateway/README.md](../src/core/services/api_gateway/README.md) | API gateway service |
| `src/core/shared/` | [../src/core/shared/AGENTS.md](../src/core/shared/AGENTS.md) | Shared types, helpers, and cross-service guidance |
| `src/core/shared/security/` | [../src/core/shared/security/AGENTS.md](../src/core/shared/security/AGENTS.md) | Shared security-specific guidance |
| `src/core/shared/utilities/` | [../src/core/shared/utilities/MIGRATION_GUIDE.md](../src/core/shared/utilities/MIGRATION_GUIDE.md) | Utility migration notes |

## Docs and Reference Areas

| Directory | Start here | Purpose |
| --- | --- | --- |
| `docs/architecture/` | [architecture/2026-03-30-governed-flywheel-integration-design.md](architecture/2026-03-30-governed-flywheel-integration-design.md) | Architecture design docs |
| `docs/launch/` | [launch/README.md](launch/README.md) | Launch assets, marketplace materials, and outreach copy |
| `docs/strategy/` | [strategy/README.md](strategy/README.md) | Strategy, pricing, and GTM docs |
| `docs/superpowers/plans/` | [superpowers/plans/2026-03-19-sveltekit-migration.md](superpowers/plans/2026-03-19-sveltekit-migration.md) | Implementation plans |
| `docs/superpowers/specs/` | [superpowers/specs/2026-03-19-sveltekit-migration-design.md](superpowers/specs/2026-03-19-sveltekit-migration-design.md) | Design/spec docs |
| `docs/generated/` | [generated/README.md](generated/README.md) | Generated long-form artifacts |
| `docs/test-plans/` | [test-plans/01-governance-core.md](test-plans/01-governance-core.md) | Test-planning docs |
| `claudedocs/archive/` | [../claudedocs/INDEX.md](../claudedocs/INDEX.md) | Archived reference snapshots |

## Automation and Test Knowledge

| Directory | Start here | Purpose |
| --- | --- | --- |
| `autonoma/skills/` | [../autonoma/skills/README.md](../autonoma/skills/README.md) | Human-readable navigation and API skill flows |
| `autonoma/qa-tests/` | [../autonoma/qa-tests/README.md](../autonoma/qa-tests/README.md) | End-to-end test cases by surface |
| `.claude/evals/` | [../.claude/evals/README.md](../.claude/evals/README.md) | Eval harness commands and eval definitions |

## Notes

- This map intentionally excludes `node_modules`, cache directories, generated worktrees, and
  other transient/vendor trees.
- When a directory gains a dedicated README or index, update this file and
  [docs/README.md](README.md) together.
