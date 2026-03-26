#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INPUT="$ROOT_DIR/architecture.mmd"
OUT_DIR="$ROOT_DIR/docs"

mkdir -p "$OUT_DIR"

mmdc -i "$INPUT" -o "$OUT_DIR/architecture.png"
mmdc -i "$INPUT" -o "$OUT_DIR/architecture.svg"

echo "Rendered:"
echo "  $OUT_DIR/architecture.png"
echo "  $OUT_DIR/architecture.svg"
