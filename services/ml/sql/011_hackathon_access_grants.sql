-- =============================================================================
-- DRISHTI migration 011 — hackathon access mode: RLS-disabled re-verification
--                          + browser/PostgREST grant hardening (API-only path)
-- Target: PostgreSQL 15+ (live: AWS RDS PostgreSQL 17.10, db "drishti",
--         owner/app role "drishti_admin"; read-only role "drishti_readonly")
-- Depends on: 001_readonly_role.sql, 005_security_rls_audit.sql (RLS helper fns)
-- =============================================================================
--
-- HACKATHON MODE (prompt2.md Prompt 3 + Global Execution Contract §16/§17):
--   * RLS stays DISABLED + NO FORCE on every DRISHTI application table. This
--     migration re-runs the idempotent disable + assertion from migration 005
--     so the guarantee is owned by a numbered migration and re-checkable, and
--     FAILS if any later migration accidentally enabled RLS.
--   * NO RLS policies are created (deferred to post-hackathon production).
--
-- API-ONLY DATA PATH (Browser -> FastAPI -> PostgreSQL/S3):
--   The browser never talks to the database directly. There is no PostgREST /
--   Supabase auto-API in front of the AWS RDS instance. As defence in depth we
--   revoke the browser/PostgREST-style DML privileges (INSERT, UPDATE, DELETE,
--   TRUNCATE, REFERENCES, TRIGGER) from the PUBLIC pseudo-role and — only if
--   they exist — from the Supabase anon/authenticated/service_role roles. On
--   the AWS RDS target these Supabase roles do not exist, so those revokes are
--   defensive no-ops; the check still guarantees the end state.
--
--   IMPORTANT: revoking these grants is NOT a substitute for RLS and must not be
--   confused with it. RLS remains DISABLED by design for the hackathon.
--
-- LEAST PRIVILEGE (documented, not enforced here):
--   The FastAPI service currently connects as the RDS master role
--   "drishti_admin". A post-hackathon hardening task is to create a dedicated
--   least-privilege login role (CRUD on application tables, no DDL/superuser)
--   and point DATABASE_URL at it. That requires provisioning a new secret and
--   is therefore intentionally left out of this additive migration.
--
-- Additive + idempotent: safe to run repeatedly. No data is dropped or altered.
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- 1. Re-assert RLS disabled + NO FORCE on every application table (idempotent).
--    fn_disable_rls_all_app() / fn_assert_rls_disabled() are defined in 005.
-- -----------------------------------------------------------------------------
SELECT fn_disable_rls_all_app();
SELECT fn_assert_rls_disabled();

-- -----------------------------------------------------------------------------
-- 2. Revoke browser/PostgREST-style DML from PUBLIC + Supabase roles (if any),
--    and keep drishti_readonly strictly SELECT-only.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_revoke_browser_grants()
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    t RECORD;
    r TEXT;
    browser_roles TEXT[] := ARRAY['anon', 'authenticated', 'service_role'];
    n INTEGER := 0;
BEGIN
    FOR t IN SELECT schemaname, tablename FROM fn_drishti_app_tables() LOOP
        -- PUBLIC pseudo-role: strip any DML-ish privilege (usually none).
        EXECUTE format(
            'REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON %I.%I FROM PUBLIC',
            t.schemaname, t.tablename);

        -- Supabase browser-facing roles: revoke DML + SELECT, ONLY if the role
        -- exists (the browser does not use PostgREST, so it needs no grants).
        FOREACH r IN ARRAY browser_roles LOOP
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
                EXECUTE format(
                    'REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER, SELECT '
                    'ON %I.%I FROM %I', t.schemaname, t.tablename, r);
            END IF;
        END LOOP;

        -- drishti_readonly must remain SELECT-only: strip any DML if present
        -- (SELECT was granted by 001_readonly_role.sql and is preserved).
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'drishti_readonly') THEN
            EXECUTE format(
                'REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON %I.%I FROM drishti_readonly',
                t.schemaname, t.tablename);
        END IF;

        n := n + 1;
    END LOOP;
    RETURN n;
END;
$$;
COMMENT ON FUNCTION fn_revoke_browser_grants() IS
    'Hackathon API-only path: revoke browser/PostgREST DML from PUBLIC + Supabase roles (if present); keep drishti_readonly SELECT-only. Not a substitute for RLS.';

-- -----------------------------------------------------------------------------
-- 3. Verification: no browser/public DML remains on any application table.
--    Fails the migration (and any re-run) if a grant regresses.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_assert_no_browser_dml()
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
    bad TEXT;
BEGIN
    SELECT string_agg(DISTINCT grantee || ':' || privilege_type, ', ')
    INTO bad
    FROM information_schema.role_table_grants
    WHERE table_schema = 'public'
      AND grantee IN ('anon', 'authenticated', 'service_role', 'PUBLIC')
      AND privilege_type IN
          ('INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER');

    IF bad IS NOT NULL THEN
        RAISE EXCEPTION
            'HACKATHON GRANT CHECK FAILED: browser/public DML still present: %', bad;
    END IF;
    RAISE NOTICE
        'HACKATHON GRANT CHECK PASSED: no anon/authenticated/service_role/PUBLIC DML on public tables.';
END;
$$;
COMMENT ON FUNCTION fn_assert_no_browser_dml() IS
    'Hackathon check: raise if anon/authenticated/service_role/PUBLIC hold any DML on a public application table.';

-- -----------------------------------------------------------------------------
-- 4. Execute the hardening + verify the end state.
-- -----------------------------------------------------------------------------
SELECT fn_revoke_browser_grants();
SELECT fn_assert_no_browser_dml();
SELECT fn_assert_rls_disabled();   -- RLS is still disabled after grant changes

-- Record the hackathon access-mode marker (non-secret) for audit/admin display.
INSERT INTO "synthetic_meta" ("Key", "Value", "Detail") VALUES
    ('hackathon_access_mode', 'api_only',
     '{"browser_db_access":"forbidden","postgrest":"n/a on RDS","rls":"disabled by design","grants":"browser DML revoked"}'::jsonb)
ON CONFLICT ("Key") DO UPDATE
    SET "Value" = EXCLUDED."Value",
        "Detail" = EXCLUDED."Detail",
        "UpdatedAt" = now();

COMMIT;

-- =============================================================================
-- DEFERRED PRODUCTION SECURITY (DO NOT implement in the hackathon):
--   * Re-enable + FORCE Row Level Security and author per-table RLS policies
--     scoped to unit/case/role once real authentication (Supabase Auth/Cognito
--     JWT) is in place.
--   * Replace the editable X-Role/X-Demo-Actor headers with verified identity.
--   * Provision a dedicated least-privilege FastAPI DB login role and rotate
--     DATABASE_URL to it.
--   * Retire / pause the legacy Supabase project (its anon/authenticated roles
--     still hold broad DML there); it is no longer the source of truth.
-- End of migration 011.
-- =============================================================================
