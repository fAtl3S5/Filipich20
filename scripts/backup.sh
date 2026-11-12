#!/usr/bin/env bash
set -euo pipefail
# Usage: ./scripts/backup.sh [output_dir]
OUT_DIR="${1:-./backups}"
mkdir -p "$OUT_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
FILE="$OUT_DIR/filippych-$STAMP.sql.gz"
echo "Writing $FILE"
docker compose exec -T db pg_dump -U filippych filippych | gzip > "$FILE"
echo "Done"
