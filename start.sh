#!/usr/bin/env bash
set -e

PORT="${PORT:-10000}"

echo "Starting CrowdVision backend on port $PORT..."

if command -v python3 >/dev/null 2>&1; then
    exec python3 -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port "$PORT"
elif command -v uvicorn >/dev/null 2>&1; then
    exec uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port "$PORT"
elif command -v python >/dev/null 2>&1; then
    exec python -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port "$PORT"
else
    echo "ERROR: Neither python3, uvicorn, nor python was found in PATH!"
    exit 1
fi
