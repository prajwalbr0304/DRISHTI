-- =============================================================================
-- DRISHTI ML service — read-only DB role for guarded/NL->SQL access
-- Target: PostgreSQL 15+ / Supabase
-- =============================================================================
--
-- Creates a NOLOGIN role that holds ONLY SELECT + schema USAGE. The ML service
-- connects with the normal application login (DATABASE_URL) and, on its
-- read-only connection layer, immediately `SET ROLE drishti_readonly` and runs
-- the transaction READ ONLY. Two independent guards therefore block writes:
--   1. Privilege: the role was never granted INSERT/UPDATE/DELETE/DDL.
--   2. Transaction: default_transaction_read_only = on for that connection.
--
-- The Phase 2-3 NL->SQL executor MUST use only this role.
--
-- Idempotent: safe to run repeatedly.
-- =============================================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'drishti_readonly') THEN
        CREATE ROLE drishti_readonly NOLOGIN;
    END IF;
END$$;

-- Exact grants ---------------------------------------------------------------
-- Schema visibility (needed to resolve objects) but NOT create:
GRANT USAGE ON SCHEMA public TO drishti_readonly;
REVOKE CREATE ON SCHEMA public FROM drishti_readonly;

-- Read-only data access on every existing table/view/matview in public:
GRANT SELECT ON ALL TABLES IN SCHEMA public TO drishti_readonly;

-- Future tables created by the current owner are auto-granted SELECT:
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT ON TABLES TO drishti_readonly;

-- Explicitly ensure NO write/DDL leaks in (defensive; these are not default):
-- (No INSERT/UPDATE/DELETE/TRUNCATE/REFERENCES/TRIGGER grants are issued.)

-- Allow the application login role to assume the read-only role via SET ROLE.
-- (drishti_readonly is NOLOGIN, so it is only ever entered through SET ROLE.)
DO $$
BEGIN
    EXECUTE format('GRANT drishti_readonly TO %I', current_user);
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'Could not grant drishti_readonly to %: %', current_user, SQLERRM;
END$$;

-- Verification hints (run manually):
--   SET ROLE drishti_readonly;
--   SELECT COUNT(*) FROM "CaseMaster";            -- OK
--   INSERT INTO "State"("StateName") VALUES ('x'); -- ERROR: permission denied / read-only
--   RESET ROLE;
