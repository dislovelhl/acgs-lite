#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

require_file() {
  local path="$1"
  if [[ ! -f "${path}" ]]; then
    echo "codex-doctor: missing file: ${path}" >&2
    exit 1
  fi
}

require_dir() {
  local path="$1"
  if [[ ! -d "${path}" ]]; then
    echo "codex-doctor: missing directory: ${path}" >&2
    exit 1
  fi
}

require_dir ".agents/skills"
require_file "AGENTS.md"
require_file "PLANS.md"
require_file ".agents/skills/README.md"
require_file ".agents/skills/acgs-codex-bootstrap/SKILL.md"
require_file ".agents/skills/package-health-governance/SKILL.md"

CONFIG_PATH=".codex/config.toml"
if [[ ! -f "${CONFIG_PATH}" ]]; then
  echo "codex-doctor: missing file: ${CONFIG_PATH}" >&2
  exit 1
fi

python3 - <<'PY'
from pathlib import Path
import tomllib

config_path = Path(".codex/config.toml")
data = tomllib.loads(config_path.read_text())

expected = {
    "model": "gpt-5.4",
    "approval_policy": "on-request",
    "sandbox_mode": "workspace-write",
    "web_search": "cached",
    "model_reasoning_effort": "high",
    "personality": "pragmatic",
}

for key, expected_value in expected.items():
    actual = data.get(key)
    if actual != expected_value:
        raise SystemExit(
            f"codex-doctor: expected {key}={expected_value!r}, found {actual!r}"
        )

mcp = data.get("mcp_servers", {}).get("openaiDeveloperDocs", {})
if mcp.get("url") != "https://developers.openai.com/mcp":
    raise SystemExit("codex-doctor: openaiDeveloperDocs MCP URL is missing or incorrect")
PY

echo "codex-doctor: OK"
