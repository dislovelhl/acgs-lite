#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACKAGE_DIR_INPUT="${PACKAGE_DIR:-${ROOT_DIR}}"
if [[ "${PACKAGE_DIR_INPUT}" = /* ]]; then
    PACKAGE_DIR="${PACKAGE_DIR_INPUT}"
else
    PACKAGE_DIR="${ROOT_DIR}/${PACKAGE_DIR_INPUT}"
fi
export PACKAGE_DIR
UV_BIN="${UV:-uv}"
DIST_DIR="${ROOT_DIR}/dist"
PACKAGE_NAME="${PACKAGE_NAME:-$(python3 - <<'PY'
import tomllib
from pathlib import Path
package_dir = Path(__import__("os").environ["PACKAGE_DIR"])
with (package_dir / "pyproject.toml").open("rb") as handle:
    data = tomllib.load(handle)
print(data["project"]["name"])
PY
)}"
PACKAGE_FILE_STEM="${PACKAGE_NAME//-/_}"
VERSION="${VERSION:-$(python3 - <<'PY'
import tomllib
from pathlib import Path
package_dir = Path(__import__("os").environ["PACKAGE_DIR"])
with (package_dir / "pyproject.toml").open("rb") as handle:
    data = tomllib.load(handle)
print(data["project"]["version"])
PY
)}"
WHEEL_PATH="${DIST_DIR}/${PACKAGE_FILE_STEM}-${VERSION}-py3-none-any.whl"
SDIST_PATH="${DIST_DIR}/${PACKAGE_FILE_STEM}-${VERSION}.tar.gz"

BUILD_ONLY=0
DRY_RUN=0

usage() {
    cat <<'EOF'
Usage: scripts/publish-acgs.sh [--build-only] [--dry-run]

Builds the distribution from `PACKAGE_DIR` (defaults to the repo root) and optionally publishes it
with `uv publish`.

Environment:
  PACKAGE_DIR          Package directory containing pyproject.toml.
  UV_PUBLISH_TOKEN     PyPI token for publish mode.
  VERSION              Override package version when locating built artifacts.
  UV                   Override the uv binary path.
EOF
}

while (($# > 0)); do
    case "$1" in
        --build-only)
            BUILD_ONLY=1
            shift
            ;;
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

cd "${ROOT_DIR}"

echo "Building ${PACKAGE_NAME} ${VERSION}..."
"${UV_BIN}" build "${PACKAGE_DIR}" --no-sources --clear

if [[ ! -f "${WHEEL_PATH}" || ! -f "${SDIST_PATH}" ]]; then
    echo "Expected build artifacts not found:" >&2
    echo "  ${WHEEL_PATH}" >&2
    echo "  ${SDIST_PATH}" >&2
    exit 1
fi

if (( BUILD_ONLY == 1 )); then
    echo "Built artifacts:"
    echo "  ${WHEEL_PATH}"
    echo "  ${SDIST_PATH}"
    exit 0
fi

if (( DRY_RUN == 1 )); then
    echo "Dry-running publish for ${PACKAGE_NAME} ${VERSION}..."
    "${UV_BIN}" publish --dry-run "${WHEEL_PATH}" "${SDIST_PATH}"
    exit 0
fi

if [[ -z "${UV_PUBLISH_TOKEN:-}" && -z "${UV_PUBLISH_PASSWORD:-}" ]]; then
    echo "Set UV_PUBLISH_TOKEN (recommended) or UV_PUBLISH_PASSWORD before publishing." >&2
    exit 1
fi

echo "Publishing ${PACKAGE_NAME} ${VERSION}..."
"${UV_BIN}" publish "${WHEEL_PATH}" "${SDIST_PATH}"
