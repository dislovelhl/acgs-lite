# ACGS Docs Index

This index highlights the most useful tracked, repo-owned documentation for active engineering
work in ACGS. It is intentionally biased toward operator and coding-agent workflows rather than
strategy or paper content.

> Start here when you need the shortest path to the right README, package guide, or workflow doc.

## Scope

This index covers repo-owned documentation that is meant to guide development work:

- root entry points like `README.md`, `CLAUDE.md`, and tracked workflow docs
- package and service READMEs under `packages/`, `src/`, `workers/`, and demo directories
- guides under `docs/`, `claudedocs/`, and selected repo-owned support folders

It does not try to index vendored docs under `node_modules/`, temporary worktrees, cache
directories, or generated third-party bundles.

## Repo Entry Points

| Doc | Use when |
| --- | --- |
| [`../README.md`](../README.md) | You want the product-level overview, install path, and public quickstart |
| [`../CLAUDE.md`](../CLAUDE.md) | You need repo navigation, commands, and coding-agent workflow guidance |
| [`../AGENTS.md`](../AGENTS.md) | You need the authoritative repo operating contract and execution rules |
| [`../CONTRIBUTING.md`](../CONTRIBUTING.md) | You are checking contributor setup, pull request expectations, and release naming rules |
| [`repo-map.md`](repo-map.md) | You want the directory-by-directory map of repo-owned docs |

## Start Here

| Doc | Use when |
| --- | --- |
| [`ai-workspace.md`](ai-workspace.md) | You need the repo-local Claude/Codex/Gemini workspace setup and operator workflow |
| [`repo-guidance-layering.md`](repo-guidance-layering.md) | You are deciding where new shared guidance should live |
| [`testing-spec.md`](testing-spec.md) | You want the repository testing model, layers, and standard commands |
| [`test-plans/01-governance-core.md`](test-plans/01-governance-core.md) | You are working on governance-core or message-processor changes |

## Workflow Guides

| Doc | Focus |
| --- | --- |
| [`worktree-isolation.md`](worktree-isolation.md) | Safe parallel work with dedicated git worktrees |
| [`context-compaction.md`](context-compaction.md) | Carry-forward rules for handoff and context compression |
| [`project-memory.md`](project-memory.md) | Durable project memory, `MEMORY.md`, and `claude-mem` usage |
| [`subagent-execution.md`](subagent-execution.md) | How to delegate to sub-agents safely with evidence and verification |

## Packages and Services

| Doc | Focus |
| --- | --- |
| [`../packages/acgs-lite/README.md`](../packages/acgs-lite/README.md) | Public Python package overview and install surface |
| [`../packages/acgs-core/README.md`](../packages/acgs-core/README.md) | `acgs` namespace package and audit/policy layer |
| [`../packages/acgs-lite/docs/index.md`](../packages/acgs-lite/docs/index.md) | `acgs-lite` deep-dive docs for CLI, compliance, integrations, and architecture |
| [`../packages/acgs.ai/README.md`](../packages/acgs.ai/README.md) | SvelteKit frontend for the public site and demos |
| [`../packages/acgs-dashboard/README.md`](../packages/acgs-dashboard/README.md) | React + Vite governance dashboard |
| [`../packages/enhanced_agent_bus/README.md`](../packages/enhanced_agent_bus/README.md) | Bus service overview, deployment model, and API surface |
| [`../packages/acgs_auth0/README.md`](../packages/acgs_auth0/README.md) | Auth0 Token Vault constitutional governance bridge |
| [`../packages/clinicalguard/README.md`](../packages/clinicalguard/README.md) | Healthcare A2A demo/service entry point |
| [`../packages/constitutional_swarm/README.md`](../packages/constitutional_swarm/README.md) | Governed multi-agent package overview |
| [`../packages/mhc/README.md`](../packages/mhc/README.md) | Short-import alias package for `constitutional-swarm` |
| [`../src/core/services/api_gateway/README.md`](../src/core/services/api_gateway/README.md) | API gateway service overview and architecture |
| [`../workers/governance-proxy/README.md`](../workers/governance-proxy/README.md) | Cloudflare Worker governance proxy |
| [`../rust/README.md`](../rust/README.md) | Rust/PyO3 governance engine notes |

## Demos and Examples

| Doc | Focus |
| --- | --- |
| [`../demo/README.md`](../demo/README.md) | GitLab hackathon demo assets and recording workflow |
| [`../hackathon-demo/README.md`](../hackathon-demo/README.md) | Governed Agent Vault demo using `acgs-auth0` |
| [`../packages/acgs-lite/examples/README.md`](../packages/acgs-lite/examples/README.md) | Example projects bundled with `acgs-lite` |

## Architecture and Reference

| Doc | Focus |
| --- | --- |
| [`ai-workspace.md`](ai-workspace.md) | Repo-local AI tooling layout and verification commands |
| [`brand-architecture.md`](brand-architecture.md) | Branding/system framing |
| [`GITLAB.md`](GITLAB.md) | GitLab-specific integration/reference material |
| [`ORIGIN.md`](ORIGIN.md) | Repository background and lineage |
| [`../claudedocs/INDEX.md`](../claudedocs/INDEX.md) | Consolidated research, API, and architecture reference set |

## Strategy, Research, and Launch

These docs are valuable, but not usually the first stop for implementation sessions:
- [`strategy/`](strategy/)
- [`launch/`](launch/)
- [`papers/`](papers/)
- [`generated/`](generated/)

## Recommended Read Order for Coding Work

For most engineering tasks:
1. root `AGENTS.md`
2. root `CLAUDE.md`
3. this index
4. the nearest package/service README
5. relevant package/subdirectory `AGENTS.md`
6. the specific workflow doc(s) above
7. the relevant eval under `.claude/evals/`

## Maintenance Rule

When a new tracked workflow doc, package/service README, or high-value reference guide is added,
update this index so later sessions can discover it quickly.

## Related docs

- [`ai-workspace.md`](ai-workspace.md) — repo-local tooling and operator workflow
- [`repo-guidance-layering.md`](repo-guidance-layering.md) — where new shared guidance should live
- [`subagent-execution.md`](subagent-execution.md) — delegated implementation/review workflow
- [`repo-map.md`](repo-map.md) — repo-owned directory-by-directory documentation map
