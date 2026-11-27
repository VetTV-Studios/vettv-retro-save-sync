#!/usr/bin/env bash
# Launch the GUI against a local dummy fixture (no real user saves).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEMO="${RSS_DEMO:-$ROOT/demo-data}"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
exec "$ROOT/.venv/bin/python" -m retro_save_sync gui --root "$DEMO" --platform linux --demo "$@"
