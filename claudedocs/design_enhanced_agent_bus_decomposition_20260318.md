# Enhanced Agent Bus Decomposition Design

**Date:** 2026-03-18 | **Status:** Proposed | **Constitutional Hash:** 608508a9bd224290

## Proposed 9-Package Decomposition

| # | Package | Current Dirs | Est. LoC | Dependencies |
|---|---------|-------------|----------|--------------|
| K | `acgs-bus-types` (Kernel) | enums, models, interfaces, exceptions, bus_types | ~8K | None (leaf) |
| 1 | `acgs-observability` | observability/, profiling/, monitoring/ | ~15K | Kernel only |
| 2 | `acgs-bus-core` | bus/, components/, message_processor, config | ~35K | Kernel + Observability |
| 3 | `acgs-maci` | maci/, maci_enforcement, middlewares/batch/governance | ~12K | Kernel + Observability |
| 4 | `acgs-constitutional` | constitutional/, verification_layer/ | ~20K | Kernel + MACI |
| 5 | `acgs-deliberation` | deliberation_layer/, governance/ | ~18K | Kernel + Observability |
| 6 | `acgs-adaptive-governance` | adaptive_governance/, online_learning_infra/, drift_monitoring/ | ~25K | Kernel + Deliberation |
| 7 | `acgs-enterprise` | enterprise_sso/, multi_tenancy/, compliance_layer/, security/ | ~30K | Kernel + Observability |
| 8 | `acgs-agent-features` | agents/, agent_health/, collaboration/, llm_adapters/ | ~35K | Kernel + Bus Core |
| 9 | `acgs-integrations` | mcp_*, api/, routes/, _ext_*.py, webhooks/ | ~40K | Bus Core + varies |

## Migration Order (Shim-First Strategy)

| Phase | Package | Weeks | Risk |
|-------|---------|-------|------|
| 0 | acgs-bus-types (Kernel) | 1-2 | Low |
| 1 | acgs-observability | 2-3 | Medium (140+ importers) |
| 2 | acgs-maci | 3-4 | Medium (security-critical) |
| 3 | acgs-deliberation | 4-5 | Low-Medium |
| 4 | acgs-constitutional | 5-6 | High (governance-critical) |
| 5 | acgs-bus-core | 6-8 | High (gravitational center) |
| 6 | Remaining 4 packages | 8-12 | Medium |

## Key Design Decisions

1. **9 packages** (not 3, not 15) — aligns with natural domain boundaries
2. **Types-only shared kernel** — zero runtime deps, no I/O, no logging
3. **Shim-first migration** — backward-compatible re-exports at each step
4. **Leaf-to-root order** — least coupled packages extracted first

## Success Criteria Per Phase

- `make test` passes with zero new failures
- `make lint` passes
- New package has its own `pyproject.toml` and isolated test suite
- No circular dependencies
- Performance targets hold: P99 < 0.103ms, throughput > 5,066 RPS
- Constitutional hash preserved in all validation paths
