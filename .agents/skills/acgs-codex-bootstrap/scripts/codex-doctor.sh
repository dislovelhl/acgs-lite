#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../../" && pwd)"

cd "$repo_root"

echo "ACGS Codex doctor"
echo "repo_root=$repo_root"

test -f AGENTS.md
test -f PLANS.md
test -f .codex/config.toml || test -f .codex-home/.codex/config.toml || test -f "$HOME/.codex/config.toml"

make lint
