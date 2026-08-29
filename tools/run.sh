#!/usr/bin/env bash
# Start the application. Reads its destination from tools/deploy.env, which is
# not versioned, so this file names no host.
set -euo pipefail
cd "$(dirname "$0")/.."
CONF="tools/deploy.env"; [ -f "$CONF" ] && . "$CONF"
: "${APP_ENV_FILE:?set APP_ENV_FILE in tools/deploy.env}"
export APP_ENV_FILE
exec .venv/bin/uvicorn app.main:app \
  --host "${BIND_HOST:-127.0.0.1}" --port "${BIND_PORT:-8081}"
