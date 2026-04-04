-- =============================================================================
-- Repository Analysis — admin-only privileges (PostgreSQL)
-- =============================================================================
-- Run as a role that can GRANT (superuser, or owner of schema repository_analysis).
-- Do NOT run as the application user.
--
-- Before this script:
--   1. Apply sql/repository_analysis_schema.sql (same privileged session is fine).
--
-- Then edit the two variables in the DO block below:
--   app_role   = login name used in DATABASE_URL (the DML-only user)
--   ddl_owner  = role that owns the tables in repository_analysis (usually the
--                same session user that ran repository_analysis_schema.sql)
--
-- The application user receives only:
--   USAGE on schema repository_analysis
--   SELECT, INSERT, UPDATE, DELETE on all existing and future tables in that schema
--   USAGE, SELECT on sequences in that schema (none today; safe for future SERIAL/identity)
--
-- It does NOT receive CREATE, ALTER, DROP, TRUNCATE, or REFERENCES unless you add them.
-- =============================================================================

DO $body$
DECLARE
  app_role   text := 'postgres';   -- <<< change to your DATABASE_URL username
  ddl_owner  text := current_user; -- <<< set explicitly if tables are owned by another role
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = app_role) THEN
    RAISE EXCEPTION 'Role % does not exist. Create it first (CREATE ROLE ... LOGIN) or fix app_role.', app_role;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = ddl_owner) THEN
    RAISE EXCEPTION 'Role % does not exist. Fix ddl_owner to match the owner of repository_analysis objects.', ddl_owner;
  END IF;

  -- Schema: app may use objects but not create new ones in this schema
  EXECUTE format('GRANT USAGE ON SCHEMA repository_analysis TO %I', app_role);
  EXECUTE format('REVOKE CREATE ON SCHEMA repository_analysis FROM %I', app_role);

  -- Existing tables
  EXECUTE format(
    'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA repository_analysis TO %I',
    app_role
  );

  -- Existing sequences (if any)
  EXECUTE format(
    'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA repository_analysis TO %I',
    app_role
  );

  -- Future objects created by ddl_owner in this schema
  EXECUTE format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA repository_analysis GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO %I',
    ddl_owner,
    app_role
  );
  EXECUTE format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA repository_analysis GRANT USAGE, SELECT ON SEQUENCES TO %I',
    ddl_owner,
    app_role
  );
END
$body$;

-- Optional: tighten public access (review before running in shared clusters)
-- REVOKE ALL ON SCHEMA repository_analysis FROM PUBLIC;
