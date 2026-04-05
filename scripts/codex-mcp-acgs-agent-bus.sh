#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -x "${ROOT_DIR}/.venv/bin/python" ]]; then
  PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
else
  PYTHON_BIN="$(command -v python)"
fi

pythonpath_entries=(
  "${ROOT_DIR}/packages/enhanced_agent_bus"
  "${ROOT_DIR}/packages/acgs-lite/src"
  "${ROOT_DIR}/packages/acgs-deliberation/src"
  "${ROOT_DIR}/packages/constitutional_swarm/src"
  "${ROOT_DIR}/packages/mhc/src"
  "${ROOT_DIR}/src"
  "${ROOT_DIR}"
)

PYTHONPATH_PREFIX=""
for entry in "${pythonpath_entries[@]}"; do
  if [[ -d "${entry}" ]]; then
    if [[ -n "${PYTHONPATH_PREFIX}" ]]; then
      PYTHONPATH_PREFIX="${PYTHONPATH_PREFIX}:"
    fi
    PYTHONPATH_PREFIX="${PYTHONPATH_PREFIX}${entry}"
  fi
done

export PYTHONPATH="${PYTHONPATH_PREFIX}"

export PYTHONUNBUFFERED=1
export ACGS_ENV="${ACGS_ENV:-development}"
export LOG_LEVEL="${LOG_LEVEL:-INFO}"

exec "${PYTHON_BIN}" -m enhanced_agent_bus.mcp_server.cli "$@"
