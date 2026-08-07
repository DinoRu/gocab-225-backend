#!/usr/bin/env bash
set -e
echo "DEBUG DATABASE_URL présente : ${DATABASE_URL:+yes}"
echo "DEBUG SECRET_KEY présente : ${SECRET_KEY:+yes}"
alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT"