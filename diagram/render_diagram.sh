#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

INPUT="sdlc.mmd"
OUTPUT="sdlc.svg"

if ! command -v npx >/dev/null 2>&1; then
  echo "npx not found. Install Node.js (>=16) to render Mermaid diagrams." >&2
  exit 0
fi

# Render using Mermaid CLI (downloaded on demand)
npx --yes @mermaid-js/mermaid-cli -i "$INPUT" -o "$OUTPUT" --backgroundColor transparent >/dev/null 2>&1 || {
  echo "Mermaid render failed (mmdc)." >&2
  exit 1
}

echo "Rendered $OUTPUT"
