#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONFIG="$ROOT/.gemini/settings.json"
LOCAL_CONFIG="$ROOT/.gemini/settings.local.json"
DOC="$ROOT/docs/ai-workspace.md"
EXAMPLE_LOCAL_CONFIG="$ROOT/.gemini/settings.local.json.example"
CONSTITUTIONAL_HASH="608508a9bd224290"

cd "$ROOT"

require_file() {
  local path="$1"
  local label="$2"
  if [ ! -f "$path" ]; then
    echo "Missing ${label}: $path" >&2
    exit 1
  fi
}

validate_json() {
  local path="$1"
  python3 - <<'PY' "$path"
import json
import sys
from pathlib import Path
json.loads(Path(sys.argv[1]).read_text())
PY
}

find_gemini_cli() {
  if [ -n "${GEMINI_BIN:-}" ]; then
    printf '%s\n' "$GEMINI_BIN"
    return 0
  fi

  local candidate
  for candidate in gemini gemini-cli; do
    if command -v "$candidate" >/dev/null 2>&1; then
      command -v "$candidate"
      return 0
    fi
  done
  return 1
}

print_workspace_info() {
  echo "ROOT=$ROOT"
  echo "CONFIG=$CONFIG"
  echo "LOCAL_CONFIG=$LOCAL_CONFIG"
  echo "LOCAL_CONFIG_PRESENT=$( [ -f "$LOCAL_CONFIG" ] && echo yes || echo no )"
  echo "EXAMPLE_LOCAL_CONFIG=$EXAMPLE_LOCAL_CONFIG"
  echo "DOC=$DOC"
  echo "CONSTITUTIONAL_HASH=$CONSTITUTIONAL_HASH"
}

run_doctor() {
  require_file "$CONFIG" "Gemini workspace config"
  require_file "$DOC" "AI workspace doc"
  validate_json "$CONFIG"
  if [ -f "$LOCAL_CONFIG" ]; then
    validate_json "$LOCAL_CONFIG"
  fi

  echo "OK: workspace config present"
  echo "OK: workspace docs present"
  if [ -f "$EXAMPLE_LOCAL_CONFIG" ]; then
    validate_json "$EXAMPLE_LOCAL_CONFIG"
    echo "OK: local config example present"
  else
    echo "WARN: local config example missing"
  fi

  if GEMINI_CLI="$(find_gemini_cli)"; then
    echo "OK: Gemini CLI resolved to $GEMINI_CLI"
    return 0
  fi

  echo "ERROR: Gemini CLI is not installed or not on PATH." >&2
  echo "Set GEMINI_BIN=/path/to/gemini to override detection." >&2
  return 1
}

require_file "$CONFIG" "Gemini workspace config"
validate_json "$CONFIG"
if [ -f "$LOCAL_CONFIG" ]; then
  validate_json "$LOCAL_CONFIG"
fi

case "${1:-}" in
  --workspace-info)
    print_workspace_info
    exit 0
    ;;
  --doctor)
    run_doctor
    exit $?
    ;;
  "")
    ;;
  *)
    ;;
esac

if ! GEMINI_CLI="$(find_gemini_cli)"; then
  echo "Gemini CLI is not installed or not on PATH." >&2
  echo "Workspace config: $CONFIG" >&2
  echo "Local override: $LOCAL_CONFIG" >&2
  echo "Example override: $EXAMPLE_LOCAL_CONFIG" >&2
  echo "See: $DOC" >&2
  echo "Tip: set GEMINI_BIN=/path/to/gemini to override detection." >&2
  exit 127
fi

export ACGS_CONSTITUTIONAL_HASH="$CONSTITUTIONAL_HASH"
export GEMINI_WORKSPACE_ROOT="$ROOT"
export GEMINI_WORKSPACE_CONFIG="$CONFIG"
export GEMINI_WORKSPACE_DOC="$DOC"
export GEMINI_WORKSPACE_LOCAL_CONFIG="$LOCAL_CONFIG"

exec "$GEMINI_CLI" "$@"
