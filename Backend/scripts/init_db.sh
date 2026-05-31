#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ -f "$ROOT_DIR/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    . "$ROOT_DIR/.env"
    set +a
fi

DB_NAME="${POSTGRES_DB:-doom_agentic_qa}"
DB_USER="${POSTGRES_USER:-doom_agentic}"
DB_PASSWORD="${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD before initializing the database}"
DB_HOST="${POSTGRES_HOST:-localhost}"
DB_PORT="${POSTGRES_PORT:-5432}"

mkdir -p \
    "$ROOT_DIR/${WAD_STORAGE_DIR:-storage/wads}" \
    "$ROOT_DIR/${REPORT_STORAGE_DIR:-storage/reports}" \
    "$ROOT_DIR/${RECORDING_STORAGE_DIR:-storage/recordings}" \
    "$ROOT_DIR/${SCREENSHOT_STORAGE_DIR:-storage/screenshots}"

run_as_postgres() {
    sudo -u postgres "$@"
}

run_as_postgres psql -v ON_ERROR_STOP=1 -c "DO \$\$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '${DB_USER}') THEN
        CREATE ROLE ${DB_USER} LOGIN PASSWORD '${DB_PASSWORD}';
    ELSE
        ALTER ROLE ${DB_USER} WITH LOGIN PASSWORD '${DB_PASSWORD}';
    END IF;
END
\$\$;"

if ! run_as_postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname = '${DB_NAME}'" | grep -q 1; then
    run_as_postgres createdb -O "$DB_USER" "$DB_NAME"
fi

PGPASSWORD="$DB_PASSWORD" psql \
    --host "$DB_HOST" \
    --port "$DB_PORT" \
    --username "$DB_USER" \
    --dbname "$DB_NAME" \
    --file "$ROOT_DIR/sql/schema.sql" \
    --set ON_ERROR_STOP=1

echo "Database '${DB_NAME}' is ready."
