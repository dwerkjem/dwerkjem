#!/usr/bin/bash
# Update charts; load .env so PAT/flags are available. Ensure deps are installed.

set -euo pipefail

# Load .env if present (exports all variables defined there)
if [ -f .env ]; then
	set -a
	# shellcheck disable=SC1091
	. ./.env
	set +a
fi

# Install dependencies quietly (safe to re-run)
python3 -m pip install -q -r requirements.txt >/dev/null 2>&1 || true

python3 language_charts.py

