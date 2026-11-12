#!/usr/bin/env bash
# Local / docker-compose entrypoint (fixed internal port 8741).
set -euo pipefail

echo "Running migrations..."
alembic upgrade head

echo "Starting API on 0.0.0.0:8741"
exec uvicorn app.main:app --host 0.0.0.0 --port 8741
