#!/usr/bin/env bash
set -euo pipefail

echo "Running migrations..."
alembic upgrade head

echo "Starting API on :8741"
exec uvicorn app.main:app --host 0.0.0.0 --port 8741
