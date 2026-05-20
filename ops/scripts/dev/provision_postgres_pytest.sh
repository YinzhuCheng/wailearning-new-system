#!/usr/bin/env bash
# Create a throwaway PostgreSQL database and role for full pytest (eliminates
# skips on tests/postgres/* and test_r3 on information_schema).
#
# Requires: local PostgreSQL with peer/sudo access for the postgres OS user
# (typical apt install on Debian/Ubuntu). Safe to re-run (idempotent).
#
# After this, either export TEST_DATABASE_URL (see printed line) or run pytest with:
#   COURSEEVAL_AUTO_PG_TESTS=1 python3 -m pytest tests/
#
set -euo pipefail

DB_NAME="${COURSEEVAL_PYTEST_DB_NAME:-courseeval_pytest_all}"
ROLE_NAME="${COURSEEVAL_PYTEST_DB_ROLE:-courseeval_test}"
ROLE_PASS="${COURSEEVAL_PYTEST_DB_PASSWORD:-courseeval_test}"

sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${ROLE_NAME}') THEN
    CREATE ROLE ${ROLE_NAME} LOGIN PASSWORD '${ROLE_PASS}';
  ELSE
    ALTER ROLE ${ROLE_NAME} WITH LOGIN PASSWORD '${ROLE_PASS}';
  END IF;
END
\$\$;

DROP DATABASE IF EXISTS ${DB_NAME} WITH (FORCE);
CREATE DATABASE ${DB_NAME} OWNER ${ROLE_NAME};
SQL

sudo -u postgres psql -v ON_ERROR_STOP=1 -d "${DB_NAME}" <<SQL
GRANT ALL ON SCHEMA public TO ${ROLE_NAME};
SQL

echo "OK. Use:"
echo "  export TEST_DATABASE_URL='postgresql+psycopg2://${ROLE_NAME}:${ROLE_PASS}@127.0.0.1:5432/${DB_NAME}'"
echo "Or auto-detect in pytest (Linux/macOS):"
echo "  COURSEEVAL_AUTO_PG_TESTS=1 python3 -m pytest tests/"
