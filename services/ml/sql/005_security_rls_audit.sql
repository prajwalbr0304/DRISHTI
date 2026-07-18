-- =============================================================================
-- DRISHTI migration 005 — hackathon security marker, RLS-disable verification,
--                          synthetic-run metadata, and audit setup
-- Target: PostgreSQL 15+ / Supabase (live PG 17.6)
-- Depends on: police_fir_schema.sql, police_fir_intelligence.sql,
--             police_fir_extensions.sql, services/ml/sql/001_readonly_role.sql
-- =============================================================================
--
-- HACKATHON MODE (see prompt2.md Global Execution Contract §16):
--   * RLS is kept DISABLED on every DRISHTI application table.
--   * This migration provides a REPEATABLE, idempotent check that (a) disables
--     RLS + FORCE RLS on every owned public application table and (b) verifies
--     relrowsecurity=false AND relforcerowsecurity=false for all of them,
--     raising if a later migration accidentally enables RLS.
--   * No RLS policies are created (deferred to post-hackathon production).
--
-- This migration also adds the NON-SECRET synthetic-environment marker
-- (synthetic_meta.app_environment='synthetic_hackathon') that the Datagen v2
-- loader and the FastAPI startup guard (Phase 3) require, plus SyntheticDataRun
-- scenario metadata kept SEPARATE from any model feature table.
--
-- Additive + idempotent: safe to run repeatedly. No data is dropped.
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- 1. Reusable RLS-disable + verification functions (hackathon mode).
--    fn_drishti_app_tables()      -> set of owned public application tables.
--    fn_disable_rls_all_app()     -> DISABLE ROW LEVEL SECURITY + NO FORCE.
--    fn_assert_rls_disabled()     -> RAISE if any app table still has RLS/FORCE.
--    spatial_ref_sys (PostGIS) and non-owned tables are excluded.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_drishti_app_tables()
RETURNS TABLE (schemaname TEXT, tablename TEXT, rls_enabled BOOLEAN, rls_forced BOOLEAN)
LANGUAGE sql
STABLE
AS $$
    SELECT n.nspname::text, c.relname::text,
           c.relrowsecurity, c.relforcerowsecurity
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    JOIN pg_roles r ON r.oid = c.relowner
    WHERE n.nspname = 'public'
      AND c.relkind = 'r'
      AND c.relname <> 'spatial_ref_sys'          -- PostGIS catalogue, not ours
      AND r.rolname = current_user                 -- only tables we own
    ORDER BY c.relname;
$$;
COMMENT ON FUNCTION fn_drishti_app_tables() IS
    'Set of DRISHTI-owned public application tables with their RLS/FORCE flags (hackathon RLS check).';

CREATE OR REPLACE FUNCTION fn_disable_rls_all_app()
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    t RECORD;
    n INTEGER := 0;
BEGIN
    FOR t IN SELECT schemaname, tablename FROM fn_drishti_app_tables() LOOP
        BEGIN
            EXECUTE format('ALTER TABLE %I.%I DISABLE ROW LEVEL SECURITY',
                           t.schemaname, t.tablename);
            EXECUTE format('ALTER TABLE %I.%I NO FORCE ROW LEVEL SECURITY',
                           t.schemaname, t.tablename);
            n := n + 1;
        EXCEPTION WHEN OTHERS THEN
            RAISE NOTICE 'skip RLS disable on %.%: %', t.schemaname, t.tablename, SQLERRM;
        END;
    END LOOP;
    RETURN n;
END;
$$;
COMMENT ON FUNCTION fn_disable_rls_all_app() IS
    'Hackathon mode: DISABLE ROW LEVEL SECURITY + NO FORCE on every owned public application table. Returns count processed.';

CREATE OR REPLACE FUNCTION fn_assert_rls_disabled()
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
    bad TEXT;
BEGIN
    SELECT string_agg(tablename, ', ')
    INTO bad
    FROM fn_drishti_app_tables()
    WHERE rls_enabled OR rls_forced;

    IF bad IS NOT NULL THEN
        RAISE EXCEPTION
            'HACKATHON RLS CHECK FAILED: RLS/FORCE still enabled on: %', bad;
    END IF;
    RAISE NOTICE 'HACKATHON RLS CHECK PASSED: RLS disabled + NO FORCE on all app tables.';
END;
$$;
COMMENT ON FUNCTION fn_assert_rls_disabled() IS
    'Hackathon mode: raise unless relrowsecurity=false AND relforcerowsecurity=false for every app table.';

-- -----------------------------------------------------------------------------
-- 2. Non-secret synthetic-environment marker (key/value).
--    Consumed by the Datagen v2 loader and the Phase-3 FastAPI startup guard.
--    Holds NO secret values.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "synthetic_meta" (
    "Key"       VARCHAR PRIMARY KEY,
    "Value"     VARCHAR NOT NULL,
    "Detail"    JSONB NOT NULL DEFAULT '{}'::jsonb,
    "UpdatedAt" TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE "synthetic_meta" IS
    'Non-secret environment markers (app_environment, hackathon_mode, demo_data_only). Guards refuse operational use. Never stores secrets.';

INSERT INTO "synthetic_meta" ("Key", "Value", "Detail") VALUES
    ('app_environment', 'synthetic_hackathon',
        '{"purpose":"synthetic development/demo only","not_for":"operational or real PII data"}'::jsonb),
    ('hackathon_mode',  'true',
        '{"rls":"disabled by design","browser_db_access":"forbidden - API only"}'::jsonb),
    ('demo_data_only',  'true',
        '{"data":"synthetic","reset_after_event":true}'::jsonb),
    ('datagen_schema_version', '2',
        '{"migrations":"005-009","identity":"canonical"}'::jsonb)
ON CONFLICT ("Key") DO UPDATE
    SET "Value" = EXCLUDED."Value",
        "Detail" = EXCLUDED."Detail",
        "UpdatedAt" = now();

-- -----------------------------------------------------------------------------
-- 3. SyntheticDataRun — scenario/run metadata, SEPARATE from model features.
--    One row per generator run (golden/statistical/performance). Also holds the
--    backup marker the loader requires before a destructive reload.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "SyntheticDataRun" (
    "SyntheticDataRunID" BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    "RunKey"        VARCHAR NOT NULL UNIQUE,          -- caller-supplied --run-id
    "Mode"          VARCHAR NOT NULL,                 -- golden | statistical | performance
    "Seed"          BIGINT,
    "TargetFirs"    INTEGER,
    "Status"        VARCHAR NOT NULL DEFAULT 'started',-- started|validated|loaded|failed|superseded
    "IsBackupMarker" BOOLEAN NOT NULL DEFAULT FALSE,  -- set before a destructive reload
    "BackupLocation" VARCHAR,                          -- where the pg_dump/backup lives (no secrets)
    "Totals"        JSONB NOT NULL DEFAULT '{}'::jsonb,-- per-domain row counts
    "ScenarioCoverage" JSONB NOT NULL DEFAULT '{}'::jsonb, -- named-scenario -> count
    "ValidationReport" JSONB NOT NULL DEFAULT '{}'::jsonb,  -- gate -> pass/fail/count
    "GeneratorVersion" VARCHAR,
    "StartedAt"     TIMESTAMPTZ NOT NULL DEFAULT now(),
    "FinishedAt"    TIMESTAMPTZ,
    CONSTRAINT "chk_syntheticrun_mode"
        CHECK ("Mode" IN ('golden','statistical','performance')),
    CONSTRAINT "chk_syntheticrun_status"
        CHECK ("Status" IN ('started','validated','loaded','failed','superseded'))
);
COMMENT ON TABLE "SyntheticDataRun" IS
    'Datagen v2 run metadata (mode/seed/totals/scenario-coverage/validation). Backup markers gate destructive reloads. Kept separate from model feature tables.';

CREATE INDEX IF NOT EXISTS "idx_syntheticrun_mode"   ON "SyntheticDataRun" ("Mode");
CREATE INDEX IF NOT EXISTS "idx_syntheticrun_backup" ON "SyntheticDataRun" ("IsBackupMarker");
CREATE INDEX IF NOT EXISTS "gin_syntheticrun_totals" ON "SyntheticDataRun" USING GIN ("Totals");

-- -----------------------------------------------------------------------------
-- 4. Audit setup (hackathon).
--    audit_logs already exists (police_fir_extensions.sql). Add a demo-actor
--    convenience table + an append-only audit-event view used by the API/report
--    layers. No secrets, no full narratives, no file contents are ever logged.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "DemoActor" (
    "DemoActorID" INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    "ActorKey"    VARCHAR NOT NULL UNIQUE,        -- e.g. io.ramesh (matches users.username)
    "DisplayName" VARCHAR,
    "DemoRole"    VARCHAR,                          -- presentation role only, NOT security
    "IsSynthetic" BOOLEAN NOT NULL DEFAULT TRUE,
    "CreatedAt"   TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE "DemoActor" IS
    'UX-simulation demo actors for audit/display only. NOT authentication or authorization (Supabase Auth deferred).';

INSERT INTO "DemoActor" ("ActorKey", "DisplayName", "DemoRole")
SELECT u."username", u."display_name", r."role_name"
FROM "users" u JOIN "roles" r ON r."role_id" = u."role_id"
ON CONFLICT ("ActorKey") DO NOTHING;

-- Append-only audit-event view over the existing audit_logs table (read model).
CREATE OR REPLACE VIEW "vw_audit_events" AS
SELECT
    al."log_id"      AS "AuditEventID",
    al."created_at"  AS "OccurredAt",
    u."username"     AS "Actor",
    r."role_name"    AS "ActorRole",
    al."action"      AS "Action",
    al."resource"    AS "Resource",
    al."resource_id" AS "ResourceID",
    al."detail"      AS "Detail"
FROM "audit_logs" al
LEFT JOIN "users" u ON u."user_id" = al."user_id"
LEFT JOIN "roles" r ON r."role_id" = u."role_id";
COMMENT ON VIEW "vw_audit_events" IS
    'Read model over audit_logs with resolved actor/role. Never exposes secrets, full narratives, or file contents.';

-- -----------------------------------------------------------------------------
-- 5. Grants — read-only role may read the new tables. (Prompt 3 owns the full
--    anon/authenticated grant revocation; here we only add drishti_readonly.)
-- -----------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'drishti_readonly') THEN
        GRANT SELECT ON "synthetic_meta"    TO drishti_readonly;
        GRANT SELECT ON "SyntheticDataRun"  TO drishti_readonly;
        GRANT SELECT ON "DemoActor"         TO drishti_readonly;
        GRANT SELECT ON "vw_audit_events"   TO drishti_readonly;
    END IF;
END$$;

-- -----------------------------------------------------------------------------
-- 6. RLS: keep DISABLED + NO FORCE on the new tables, then verify globally.
-- -----------------------------------------------------------------------------
ALTER TABLE "synthetic_meta"   DISABLE ROW LEVEL SECURITY;
ALTER TABLE "SyntheticDataRun" DISABLE ROW LEVEL SECURITY;
ALTER TABLE "DemoActor"        DISABLE ROW LEVEL SECURITY;

SELECT fn_disable_rls_all_app();
SELECT fn_assert_rls_disabled();

COMMIT;

-- =============================================================================
-- End of migration 005.
-- =============================================================================
