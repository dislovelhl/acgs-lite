#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

ok() {
  echo "OK: $1"
}

cd "${ROOT_DIR}"

[[ -f "${ROOT_DIR}/AGENTS.md" ]] || fail "Missing AGENTS.md"
ok "AGENTS.md present"

[[ -f "${ROOT_DIR}/PLANS.md" ]] || fail "Missing PLANS.md"
ok "PLANS.md present"

CONFIG_PATH=""
for candidate in ".codex/config.toml" ".codex-home/.codex/config.toml" "${HOME}/.codex/config.toml"; do
  if [[ -f "${candidate}" ]]; then
    CONFIG_PATH="${candidate}"
    break
  fi
done

[[ -n "${CONFIG_PATH}" ]] || fail "No Codex config found in .codex/, .codex-home/.codex/, or ~/.codex/"
ok "Codex config detected at ${CONFIG_PATH}"

if [[ -x "${ROOT_DIR}/.venv/bin/python" ]]; then
  PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
else
  PYTHON_BIN="$(command -v python)"
fi

PROJECT_CONFIG="${ROOT_DIR}/.codex/config.toml"
if [[ -f "${PROJECT_CONFIG}" ]]; then
  "${PYTHON_BIN}" - <<'PY' "${PROJECT_CONFIG}" || fail "Project Codex config is not valid TOML"
from pathlib import Path
import sys
import tomllib

with Path(sys.argv[1]).open("rb") as fh:
    tomllib.load(fh)
PY
  ok "Project Codex config parses as TOML"

  rg -q '^\[mcp_servers\.acgs_governance\]$' "${PROJECT_CONFIG}" \
    || fail "Project Codex config is missing mcp_servers.acgs_governance"
  rg -q '^\[mcp_servers\.acgs_agent_bus\]$' "${PROJECT_CONFIG}" \
    || fail "Project Codex config is missing mcp_servers.acgs_agent_bus"
  ok "Project MCP server entries present"
fi

for launcher in \
  "${ROOT_DIR}/scripts/codex-mcp-acgs-governance.sh" \
  "${ROOT_DIR}/scripts/codex-mcp-acgs-agent-bus.sh"; do
  [[ -f "${launcher}" ]] || fail "Missing launcher ${launcher}"
done
ok "Repo-local MCP launcher scripts present"

LITE_PYTHONPATH="${ROOT_DIR}/packages/acgs-lite/src:${ROOT_DIR}/src:${ROOT_DIR}"
PYTHONPATH="${LITE_PYTHONPATH}" "${PYTHON_BIN}" - <<'PY' "${ROOT_DIR}" \
  || fail "acgs-lite import precedence check failed"
import importlib.util
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
expected_prefix = root / "packages/acgs-lite/src"
spec = importlib.util.find_spec("acgs_lite.integrations.mcp_server")
if spec is None or spec.origin is None:
    raise SystemExit("acgs_lite.integrations.mcp_server is not importable")
origin = Path(spec.origin).resolve()
if not str(origin).startswith(str(expected_prefix.resolve())):
    raise SystemExit(
        f"acgs_lite.integrations.mcp_server resolved to {origin}, "
        f"expected under {expected_prefix.resolve()}"
    )
print(f"OK: acgs_lite.integrations.mcp_server -> {origin}")

mcp_spec = importlib.util.find_spec("mcp")
if mcp_spec is None or mcp_spec.origin is None:
    raise SystemExit("third-party mcp package is not importable")
mcp_origin = Path(mcp_spec.origin).resolve()
if str(mcp_origin).startswith(str((root / "packages/enhanced_agent_bus").resolve())):
    raise SystemExit(f"mcp resolved to repo-local shadow package at {mcp_origin}")
print(f"OK: mcp -> {mcp_origin}")
PY

BUS_PYTHONPATH="${ROOT_DIR}/packages/enhanced_agent_bus:${ROOT_DIR}/packages/acgs-lite/src:${ROOT_DIR}/packages/acgs-deliberation/src:${ROOT_DIR}/packages/constitutional_swarm/src:${ROOT_DIR}/packages/mhc/src:${ROOT_DIR}/src:${ROOT_DIR}"
PYTHONPATH="${BUS_PYTHONPATH}" "${PYTHON_BIN}" - <<'PY' "${ROOT_DIR}" \
  || fail "enhanced-agent-bus import precedence check failed"
import importlib.util
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
expected_prefix = root / "packages/enhanced_agent_bus"
spec = importlib.util.find_spec("enhanced_agent_bus.mcp_server.cli")
if spec is None or spec.origin is None:
    raise SystemExit("enhanced_agent_bus.mcp_server.cli is not importable")
origin = Path(spec.origin).resolve()
if not str(origin).startswith(str(expected_prefix.resolve())):
    raise SystemExit(
        f"enhanced_agent_bus.mcp_server.cli resolved to {origin}, "
        f"expected under {expected_prefix.resolve()}"
    )
print(f"OK: enhanced_agent_bus.mcp_server.cli -> {origin}")
PY

make lint
ok "make lint"
ok "codex-doctor complete"
