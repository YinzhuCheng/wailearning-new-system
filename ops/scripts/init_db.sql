\echo 'CourseEval PostgreSQL bootstrap: create or update the login role, create the database if missing, and grant schema defaults.'
\echo 'Required psql variables: -v db_name=<database> -v db_user=<role> -v db_password=<strong-password>'
\if :{?db_name}
\else
\echo 'Missing required variable: db_name'
\quit 1
\endif
\if :{?db_user}
\else
\echo 'Missing required variable: db_user'
\quit 1
\endif
\if :{?db_password}
\else
\echo 'Missing required variable: db_password'
\quit 1
\endif
\set ON_ERROR_STOP on

SELECT format(
    'CREATE ROLE %I LOGIN PASSWORD %L',
    :'db_user',
    :'db_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'db_user') \gexec

SELECT format(
    'ALTER ROLE %I WITH LOGIN PASSWORD %L',
    :'db_user',
    :'db_password'
)
WHERE EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'db_user') \gexec

SELECT format(
    'CREATE DATABASE %I OWNER %I ENCODING ''UTF8'' TEMPLATE template0',
    :'db_name',
    :'db_user'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'db_name') \gexec

GRANT ALL PRIVILEGES ON DATABASE :"db_name" TO :"db_user";
\connect :db_name
ALTER SCHEMA public OWNER TO :"db_user";
GRANT ALL ON SCHEMA public TO :"db_user";
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO :"db_user";
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO :"db_user";
