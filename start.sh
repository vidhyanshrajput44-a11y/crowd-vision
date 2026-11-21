#!/usr/bin/env bash
set -e

PORT="${PORT:-10000}"

echo "Starting CrowdVision backend on port $PORT..."

# Prefer virtualenv uvicorn binary directly
if command -v uvicorn >/dev/null 2>&1; then
    exec uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port "$PORT"
elif [ -f "/opt/render/project/src/.venv/bin/uvicorn" ]; then
    exec /opt/render/project/src/.venv/bin/uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port "$PORT"
elif [ -f ".venv/bin/uvicorn" ]; then
    exec .venv/bin/uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port "$PORT"
elif command -v python3 >/dev/null 2>&1; then
    exec python3 -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port "$PORT"
elif command -v python >/dev/null 2>&1; then
    exec python -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port "$PORT"
else
    echo "ERROR: uvicorn not found in PATH or virtualenv!"
    exit 1
fi
