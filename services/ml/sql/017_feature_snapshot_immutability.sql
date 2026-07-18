-- =============================================================================
-- DRISHTI migration 017 — feature-snapshot immutability + prediction staleness
-- Target: PostgreSQL 15+ / AWS RDS PostgreSQL (ap-south-1)
-- Depends on: 008 (feature/prediction governance tables + ModelVersion extensions)
-- =============================================================================
--
-- Phase 10 hardens the governed feature/prediction contract that migration 008
-- already created. Migration 008 gave FeatureSnapshot an "IsImmutable" flag but
-- nothing ENFORCED it. This migration:
--   1. adds staleness/audit columns (FeatureSnapshot.StaleReason/SupersededAt/
--      BuiltByActor, PredictionResult.StaleReason/StaleAt) so a source correction
--      or supersession leaves an auditable trail;
--   2. enforces FeatureSnapshot immutability with a BEFORE UPDATE OR DELETE
--      trigger — a snapshot's value/hash/schema/subject/cutoff can NEVER change;
--      only the supersession pointer + quality/stale audit columns may be set,
--      so the snapshot a prediction was computed from is reproducible forever.
--
-- Every prediction ties to an immutable FeatureSnapshot (DoD). A canonical
-- correction never edits a snapshot in place — it marks it stale + builds a new
-- one (a reviewed, versioned supersession), mirroring the "no silent move" rule.
--
-- HACKATHON SCOPE. RLS stays DISABLED + NO FORCE. No RLS policies. Additive +
-- idempotent: safe to re-run. TRUNCATE/COPY bypass row triggers, so the datagen
-- reload path is unaffected; INSERT is always allowed.
-- =============================================================================

BEGIN;

-- =============================================================================
-- 1. Staleness / audit columns (additive).
-- =============================================================================
ALTER TABLE "FeatureSnapshot" ADD COLUMN IF NOT EXISTS "StaleReason"  VARCHAR;
ALTER TABLE "FeatureSnapshot" ADD COLUMN IF NOT EXISTS "SupersededAt" TIMESTAMPTZ;
ALTER TABLE "FeatureSnapshot" ADD COLUMN IF NOT EXISTS "BuiltByActor" VARCHAR;

ALTER TABLE "PredictionResult" ADD COLUMN IF NOT EXISTS "StaleReason" VARCHAR;
ALTER TABLE "PredictionResult" ADD COLUMN IF NOT EXISTS "StaleAt"     TIMESTAMPTZ;

-- =============================================================================
-- 2. FeatureSnapshot immutability enforcement.
--    A snapshot is written once. Its identity/value/provenance columns can never
--    change; only the supersession pointer + quality/stale audit columns may be
--    updated (so a source correction can mark it stale and point to its
--    replacement). DELETE is always refused (history is preserved).
-- =============================================================================
CREATE OR REPLACE FUNCTION fn_featuresnapshot_immutable()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'FeatureSnapshot % is immutable and cannot be deleted (supersede it instead).',
            OLD."FeatureSnapshotID";
    END IF;

    -- UPDATE: the immutable columns must be byte-for-byte identical.
    IF NEW."FeatureSchemaVersionID" IS DISTINCT FROM OLD."FeatureSchemaVersionID"
       OR NEW."SubjectKind"        IS DISTINCT FROM OLD."SubjectKind"
       OR NEW."SubjectRefID"       IS DISTINCT FROM OLD."SubjectRefID"
       OR NEW."ObservationCutoff"  IS DISTINCT FROM OLD."ObservationCutoff"
       OR NEW."Values"             IS DISTINCT FROM OLD."Values"
       OR NEW."SourceVersions"     IS DISTINCT FROM OLD."SourceVersions"
       OR NEW."ContentHash"        IS DISTINCT FROM OLD."ContentHash"
       OR NEW."IsImmutable"        IS DISTINCT FROM OLD."IsImmutable"
       OR NEW."CreatedAt"          IS DISTINCT FROM OLD."CreatedAt"
    THEN
        RAISE EXCEPTION 'FeatureSnapshot % is immutable: only supersession/quality/stale columns may change.',
            OLD."FeatureSnapshotID";
    END IF;

    RETURN NEW;
END;
$$;
COMMENT ON FUNCTION fn_featuresnapshot_immutable() IS
    'Enforces FeatureSnapshot immutability: blocks DELETE and blocks UPDATE of identity/value/provenance columns; allows only supersession + quality/stale audit columns.';

DROP TRIGGER IF EXISTS "trg_featuresnapshot_immutable" ON "FeatureSnapshot";
CREATE TRIGGER "trg_featuresnapshot_immutable"
    BEFORE UPDATE OR DELETE ON "FeatureSnapshot"
    FOR EACH ROW EXECUTE FUNCTION fn_featuresnapshot_immutable();

-- =============================================================================
-- 3. Convenience index for the staleness sweep (find live snapshots by subject).
-- =============================================================================
CREATE INDEX IF NOT EXISTS "idx_featuresnapshot_live"
    ON "FeatureSnapshot" ("SubjectKind", "SubjectRefID")
    WHERE "SupersededByFeatureSnapshotID" IS NULL;

-- =============================================================================
-- 4. RLS disabled/NO FORCE + global verification (hackathon).
-- =============================================================================
SELECT fn_disable_rls_all_app();
SELECT fn_assert_rls_disabled();

COMMIT;

-- =============================================================================
-- End of migration 017.
-- =============================================================================
