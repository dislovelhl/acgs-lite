#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-generic}"
SUBMISSION="${2:-review}"
TEX_ROOT="acgs_arxiv_skeleton"
WRAPPER=".${TEX_ROOT}-${MODE}-${SUBMISSION}.tex"
PDF_OUT="${TEX_ROOT}-${MODE}-${SUBMISSION}.pdf"

case "$MODE" in
  generic|neurips|icml) ;;
  *)
    echo "Unsupported mode: $MODE" >&2
    exit 1
    ;;
esac

case "$SUBMISSION" in
  review|camera-ready) ;;
  *)
    echo "Unsupported submission mode: $SUBMISSION" >&2
    exit 1
    ;;
esac

cat > "$WRAPPER" <<EOF
% Auto-generated build wrapper. Do not edit.
$( [ "$MODE" = "neurips" ] && echo '\def\buildneurips{1}' )
$( [ "$MODE" = "icml" ] && echo '\def\buildicml{1}' )
$( [ "$SUBMISSION" = "camera-ready" ] && echo '\def\buildcameraready{1}' )
\input{$TEX_ROOT.tex}
EOF

if command -v latexmk >/dev/null 2>&1; then
  latexmk -pdf -jobname="${TEX_ROOT}-${MODE}-${SUBMISSION}" "$WRAPPER"
elif command -v tectonic >/dev/null 2>&1; then
  tectonic -o . "$WRAPPER"
  TECTONIC_PDF="${WRAPPER%.tex}.pdf"
  if [ "$TECTONIC_PDF" != "$PDF_OUT" ] && [ -f "$TECTONIC_PDF" ]; then
    cp "$TECTONIC_PDF" "$PDF_OUT"
  fi
else
  echo "No supported LaTeX engine found. Install latexmk or tectonic." >&2
  exit 1
fi

mkdir -p dist
cp "$PDF_OUT" "dist/$PDF_OUT"
echo "Built dist/$PDF_OUT"
