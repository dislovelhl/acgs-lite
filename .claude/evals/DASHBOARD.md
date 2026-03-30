# Eval Dashboard — GitLab AI Hackathon (ACGS Constitutional Sentinel)

**Deadline**: March 25, 2026 | **Status**: Pre-build baseline

## Quick Run

```bash
# Run all automated evals (from project root)
cd /home/martin/Documents/acgs-clean
python -m pytest packages/acgs-lite/tests/ -v --import-mode=importlib -m "not slow" -x

# Run individual eval scripts
python .claude/evals/run_evals.sh  # (to be created)
```

## Eval Files

| File | Component | Criteria |
|------|-----------|----------|
| `hackathon-mcp-server.md` | MCP tools (5 tools) | pass@3 > 90%, regression pass^3 = 100% |
| `hackathon-gitlab-pipeline.md` | MR governance + MACI | pass@3 > 90%, regression pass^3 = 100% |
| `hackathon-cloud-run.md` | Cloud Run endpoints | pass@3 > 90%, regression pass^3 = 100% |
| `hackathon-demo-project.md` | End-to-end demo scenario | pass@3 > 90% |

## Pass/Fail Tracker

### MCP Server (`hackathon-mcp-server.md`)
| Eval | Status | Notes |
|------|--------|-------|
| CAP-MCP-01: violation detection | ⬜ PENDING | |
| CAP-MCP-02: clean content passes | ⬜ PENDING | |
| CAP-MCP-03: 5 tools listed | ⬜ PENDING | requires `pip install acgs-lite[mcp]` |
| CAP-MCP-04: audit log grows | ⬜ PENDING | |
| CAP-MCP-05: governance_stats | ⬜ PENDING | |
| REG-MCP-01: Constitution loads | ⬜ PENDING | |
| REG-MCP-02: module importable | ⬜ PENDING | |
| REG-MCP-03: hash stable | ⬜ PENDING | |

### GitLab Pipeline (`hackathon-gitlab-pipeline.md`)
| Eval | Status | Notes |
|------|--------|-------|
| CAP-GL-01: GovernanceReport immutable | ⬜ PENDING | |
| CAP-GL-02: report markdown sections | ⬜ PENDING | |
| CAP-GL-03: webhook rejects bad token | ⬜ PENDING | |
| CAP-GL-04: MACI self-approval | ⬜ PENDING | |
| CAP-GL-05: CI config generates | ⬜ PENDING | |
| CAP-GL-06: risk score bounded | ⬜ PENDING | |
| CAP-GL-07: diff parser | ⬜ PENDING | |
| REG-GL-01: importable | ⬜ PENDING | |
| REG-GL-02: field stability | ⬜ PENDING | |
| REG-GL-03: hash in CI config | ⬜ PENDING | |

### Cloud Run (`hackathon-cloud-run.md`)
| Eval | Status | Notes |
|------|--------|-------|
| CAP-CR-01: /health response | ⬜ PENDING | |
| CAP-CR-02: /governance/summary | ⬜ PENDING | |
| CAP-CR-03: /webhook 503 no creds | ⬜ PENDING | |
| CAP-CR-04: 3 routes only | ⬜ PENDING | |
| CAP-CR-05: starts without GCP | ⬜ PENDING | |
| CAP-CR-06: Cloud Run latency | 🔲 MANUAL | post-deploy |
| CAP-CR-07: webhook registered | 🔲 MANUAL | post-deploy |
| REG-CR-01: importable | ⬜ PENDING | |
| REG-CR-02: always healthy | ⬜ PENDING | |

### Demo Project (`hackathon-demo-project.md`)
| Eval | Status | Notes |
|------|--------|-------|
| CAP-DEMO-01: secret triggers CRITICAL | ⬜ PENDING | |
| CAP-DEMO-02: risk score HIGH | ⬜ PENDING | |
| CAP-DEMO-03: report markdown OK | ⬜ PENDING | |
| CAP-DEMO-04: diff parser line number | ⬜ PENDING | |
| CAP-DEMO-05: AGENTS.md exists | ⬜ PENDING | |
| CAP-DEMO-06: CI YAML parseable | ⬜ PENDING | |
| CAP-DEMO-07: gitlab template | ⬜ PENDING | **gap — may need implementation** |
| CAP-GREEN-01: validation count | ⬜ PENDING | |
| CAP-GREEN-02: batch efficiency | ⬜ PENDING | |

## Legend
- ✅ PASS
- ❌ FAIL
- ⬜ PENDING (not yet run)
- 🔲 MANUAL (requires human/live environment)

## Baseline Results (March 19, 2026)

11/13 PASS on first run.

| Eval | Result | Root Cause |
|------|--------|-----------|
| REG-MCP-01 | ❌ FAIL → fixed | Docs now align with `Constitution.default()` hash `608508a9bd224290` |
| CAP-GL-05 | ❌ FAIL → fixed | Same hash alignment fix applied to assertions and docs |
| All others (11) | ✅ PASS | |

**Action**: Completed — constitutional hash references updated to `608508a9bd224290`.

## Build Gaps Flagged by Evals

| Gap | Eval | Priority |
|-----|------|----------|
| `Constitution.from_template('gitlab')` not confirmed | CAP-DEMO-07 | HIGH — needed for AGENTS.md integration |
| Cloud Run deployment (gcloud commands) | CAP-CR-06/07 | HIGH — needed for Google Cloud category |
| Green Agent: CO2 estimate from token counts | (future eval) | MEDIUM — bonus category |
| GitLab Duo Custom Agent system prompt | (future eval) | HIGH — core submission artifact |

## Release Gate
All 3 regression suites must be pass^3 = 100% before submitting to Devpost.
Capability suites must be pass@3 > 90%.
