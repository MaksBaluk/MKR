#!/bin/sh
set -eu
: "${POSTGRES_APP_PASSWORD:?POSTGRES_APP_PASSWORD is required}"
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --set=app_password="$POSTGRES_APP_PASSWORD" <<'SQL'
CREATE EXTENSION IF NOT EXISTS vector;
CREATE ROLE cm_app LOGIN PASSWORD :'app_password';
GRANT CONNECT ON DATABASE competencematch TO cm_app;
GRANT USAGE, CREATE ON SCHEMA public TO cm_app;
SQL
