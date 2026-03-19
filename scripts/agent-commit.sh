#!/usr/bin/env bash
# Wrap git commit to inject ACGS agent identity trailers.
#
# Usage:
#   ACGS_AGENT_ID=claude-code ACGS_MACI_ROLE=validator scripts/agent-commit.sh -m "feat: description"
#   make agent-commit MSG="feat: description" AGENT=codex ROLE=proposer
#
# Environment:
#   ACGS_AGENT_ID    agent identifier: claude-code | codex | tdd-guide | code-reviewer |
#                    security-reviewer | planner | build-error-resolver
#   ACGS_MACI_ROLE   MACI role:        proposer | validator | executor
#
# Git trailer format added to commit message:
#   Agent-Id: claude-code
#   MACI-Role: validator
#
# Requires git 2.38+ for --trailer flag.
set -euo pipefail

AGENT_ID="${ACGS_AGENT_ID:-unknown}"
MACI_ROLE="${ACGS_MACI_ROLE:-unknown}"

if [[ "$AGENT_ID" == "unknown" || "$MACI_ROLE" == "unknown" ]]; then
    echo "WARNING: ACGS_AGENT_ID or ACGS_MACI_ROLE not set. Trailers will show 'unknown'." >&2
    echo "  Set them: export ACGS_AGENT_ID=claude-code ACGS_MACI_ROLE=validator" >&2
fi

exec git commit \
    --trailer "Agent-Id: ${AGENT_ID}" \
    --trailer "MACI-Role: ${MACI_ROLE}" \
    "$@"
