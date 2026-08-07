#!/bin/sh

set -e

echo "Starting Parts Orders API..."

echo "DATABASE_URL présente: ${DATABASE_URL:+oui}"
echo "SECRET_KEY présente: ${SECRET_KEY:+oui}"

echo "Running database migrations..."
alembic upgrade head

echo "Starting FastAPI..."
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}"