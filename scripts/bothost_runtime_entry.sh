#!/usr/bin/env bash
# Prefer our FastAPI process even if Bothost overrides CMD to http_wrapper.py.
set -euo pipefail
cd /usr/src/app 2>/dev/null || cd "$(dirname "$0")/.." || true

if [[ "${1:-}" == *http_wrapper.py ]] || [[ "${2:-}" == *http_wrapper.py ]]; then
  echo "bothost_runtime_entry: ignoring platform http_wrapper CMD"
  exec python main.py
fi

if [[ $# -gt 0 ]]; then
  exec "$@"
fi

exec python main.py
