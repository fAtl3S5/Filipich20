#!/usr/bin/env bash
set -euo pipefail
# Usage: ./scripts/restore.sh backups/filippych-....sql.gz
FILE="${1:?path to .sql.gz required}"
gunzip -c "$FILE" | docker compose exec -T db psql -U filippych -d filippych
echo "Restored from $FILE"
