#!/usr/bin/env bash
set -euo pipefail
if [ "${SENTINEL_DB_CREATE_ALL:-true}" = "false" ]; then
  echo "Running migrations..."
  alembic upgrade head
fi
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers "${WEB_CONCURRENCY:-4}"
