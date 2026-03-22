#!/bin/sh
set -e

echo "FRAS: Running database migrations..."
flask db upgrade || echo "WARNING: Migration failed or no migrations to run"

echo "FRAS: Starting gunicorn..."
exec gunicorn --config gunicorn.conf.py "app:create_app()"
