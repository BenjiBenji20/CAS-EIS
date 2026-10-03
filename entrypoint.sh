#!/bin/sh
set -e

echo "Running Alembic database migrations..."
uv run alembic upgrade head

echo "Starting FastAPI server with Uvicorn..."
exec uv run uvicorn main:app --host 0.0.0.0 --port 8000
