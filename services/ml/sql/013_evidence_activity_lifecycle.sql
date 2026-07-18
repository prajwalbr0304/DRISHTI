-- =============================================================================
-- DRISHTI migration 013 — evidence activity lifecycle vocabulary + indexes
-- Target: PostgreSQL 15+ / AWS RDS (live PG 17.x)
-- Depends on: 006_ingestion_evidence.sql, 007_identity_case_workflow.sql,
--             005_security_rls_audit.sql
-- =============================================================================
--
-- Phase 5 (digital-evidence upload to S3) drives EvidenceItem through
-- draft -> uploading -> available | failed -> archived and needs a few extra
-- append-only EvidenceActivityEvent verbs the Phase-1 vocabulary lacked
-- (upload-url issuance, object made available, failed upload, restore, demo
-- reset). This migration widens the EventType allow-list and adds indexes that
-- support the evidence list (by case + recency) and the fixture uploader
-- (by storage status). It stores NO file bytes and adds NO OCR/extraction.
--
-- RLS stays DISABLED + NO FORCE (hackathon). No RLS policies. Additive +
-- idempotent: safe to run repeatedly.
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. Widen the EvidenceActivityEvent.EventType allow-list (superset of the old
--    set, so existing rows always satisfy the new constraint).
-- ---------------------------------------------------------------------------
ALTER TABLE "EvidenceActivityEvent"
    DROP CONSTRAINT IF EXISTS "chk_evidenceactivity_type";

ALTER TABLE "EvidenceActivityEvent"
    ADD CONSTRAINT "chk_evidenceactivity_type" CHECK ("EventType" IN (
        -- Phase 1 verbs (unchanged)
        'created','metadata_updated','version_added','linked','unlinked',
        'archived','access_attempt','download','custody_transfer',
        -- Phase 5 lifecycle verbs
        'upload_url_issued','uploaded','failed','restored','reset'
    ));

-- ---------------------------------------------------------------------------
-- 2. Indexes for the evidence list + the fixture uploader.
-- ---------------------------------------------------------------------------
-- Evidence list is scoped by case and ordered by recency.
CREATE INDEX IF NOT EXISTS "idx_evidenceitem_case_created"
    ON "EvidenceItem" ("CaseMasterID", "CreatedAt" DESC);
-- Current-object lookup per item (details view + download of the live version).
CREATE INDEX IF NOT EXISTS "idx_evidenceobject_item_current"
    ON "EvidenceObject" ("EvidenceItemID", "IsCurrent");
-- Fixture uploader scans pending objects by storage status.
CREATE INDEX IF NOT EXISTS "idx_evidenceobject_status"
    ON "EvidenceObject" ("StorageStatus");
-- Activity timeline is read per item, newest first.
CREATE INDEX IF NOT EXISTS "idx_evidenceactivity_item_created"
    ON "EvidenceActivityEvent" ("EvidenceItemID", "CreatedAt" DESC);

-- ---------------------------------------------------------------------------
-- 3. RLS disabled + NO FORCE everywhere (hackathon) + verification.
-- ---------------------------------------------------------------------------
SELECT fn_disable_rls_all_app();
SELECT fn_assert_rls_disabled();

COMMIT;

-- =============================================================================
-- End of migration 013.
-- =============================================================================
