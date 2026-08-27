-- Run as a PostgreSQL administrator before Alembic migrations.
-- Passwords are intentionally not stored here. Set LOGIN passwords out of band.
DO $bootstrap$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'system_a_owner') THEN
        CREATE ROLE system_a_owner LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'system_a_generator') THEN
        CREATE ROLE system_a_generator LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'system_a_api') THEN
        CREATE ROLE system_a_api LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'system_a_evaluator') THEN
        CREATE ROLE system_a_evaluator LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
    END IF;
    EXECUTE format(
        'GRANT CONNECT ON DATABASE %I TO system_a_owner, system_a_generator, system_a_api, system_a_evaluator',
        current_database()
    );
    EXECUTE format('GRANT CREATE ON DATABASE %I TO system_a_owner', current_database());
END
$bootstrap$;

GRANT USAGE, CREATE ON SCHEMA public TO system_a_owner;
