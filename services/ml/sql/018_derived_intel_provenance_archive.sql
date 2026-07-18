-- =============================================================================
-- DRISHTI migration 018 — derived-intelligence provenance, candidate/confirmed
--                          review state, and legacy-graph archival/isolation
-- Target: PostgreSQL 15+ / AWS RDS PostgreSQL (ap-south-1)
-- Depends on: 002 (drishti_hidden_associations), 007 (canonical identity +
--             NetworkEdge.ProvenanceStatus + EntityGraph.CanonicalEntityID),
--             police_fir_intelligence.sql (EntityGraph/NetworkEdge/CrimeEmbedding/
--             CrimePattern/GangMembership)
-- =============================================================================
--
-- Phase 11 rebuilds derived intelligence (embeddings, similar cases, graph,
-- hidden associations, patterns, money) from VERIFIED CANONICAL data only. This
-- migration adds the columns that let the runtime:
--   1. ISOLATE/ARCHIVE the old synthetic identity-graph rows (a non-canonical
--      EntityGraph node, a NULL-provenance NetworkEdge, a legacy embedding) so
--      the old and new canonical graph spaces are never mixed — WITHOUT deleting
--      (IsArchived/ArchivedAt/ArchiveReason);
--   2. distinguish CANDIDATE vs CONFIRMED graph edges + hidden associations with
--      a reviewer disposition (ReviewStatus + reviewer + timestamp);
--   3. attach source-record provenance + versioned rule params to detected
--      patterns; and record the INDEPENDENT EVIDENCE KINDS behind a hidden
--      association.
-- Two views (vw_canonical_graph_node / vw_canonical_graph_edge) expose only the
-- canonical, provenanced, non-archived graph the analytics must read.
--
-- HACKATHON SCOPE. RLS stays DISABLED + NO FORCE. No RLS policies. Additive +
-- idempotent: safe to re-run.
-- =============================================================================

BEGIN;

-- =============================================================================
-- 1. Archival columns on every derived-intelligence table (isolate, never drop)
-- =============================================================================
DO $$
DECLARE t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'EntityGraph','NetworkEdge','CrimeEmbedding','CrimePattern',
        'drishti_hidden_associations','GangMembership'
    ] LOOP
        EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS "IsArchived" BOOLEAN NOT NULL DEFAULT FALSE', t);
        EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS "ArchivedAt" TIMESTAMPTZ', t);
        EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS "ArchiveReason" VARCHAR', t);
    END LOOP;
END$$;

-- =============================================================================
-- 2. Candidate/confirmed review state on graph edges.
-- =============================================================================
ALTER TABLE "NetworkEdge" ADD COLUMN IF NOT EXISTS "ReviewStatus"   VARCHAR NOT NULL DEFAULT 'candidate';
ALTER TABLE "NetworkEdge" ADD COLUMN IF NOT EXISTS "ReviewedByActor" VARCHAR;
ALTER TABLE "NetworkEdge" ADD COLUMN IF NOT EXISTS "ReviewedAt"     TIMESTAMPTZ;

-- =============================================================================
-- 3. Hidden associations: reviewer disposition + independent EVIDENCE kinds.
-- =============================================================================
ALTER TABLE "drishti_hidden_associations" ADD COLUMN IF NOT EXISTS "ReviewStatus"   VARCHAR NOT NULL DEFAULT 'candidate';
ALTER TABLE "drishti_hidden_associations" ADD COLUMN IF NOT EXISTS "ReviewerActor"  VARCHAR;
ALTER TABLE "drishti_hidden_associations" ADD COLUMN IF NOT EXISTS "ReviewedAt"     TIMESTAMPTZ;
ALTER TABLE "drishti_hidden_associations" ADD COLUMN IF NOT EXISTS "IndependentEvidenceKinds" TEXT[] NOT NULL DEFAULT '{}';

-- =============================================================================
-- 4. Patterns: source-record provenance + versioned rule params + review state.
-- =============================================================================
ALTER TABLE "CrimePattern" ADD COLUMN IF NOT EXISTS "ReviewStatus"   VARCHAR NOT NULL DEFAULT 'candidate';
ALTER TABLE "CrimePattern" ADD COLUMN IF NOT EXISTS "ReviewerActor"  VARCHAR;
ALTER TABLE "CrimePattern" ADD COLUMN IF NOT EXISTS "ReviewedAt"     TIMESTAMPTZ;
ALTER TABLE "CrimePattern" ADD COLUMN IF NOT EXISTS "SourceRecordIDs" JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE "CrimePattern" ADD COLUMN IF NOT EXISTS "RuleParams"     JSONB NOT NULL DEFAULT '{}'::jsonb;

-- =============================================================================
-- 5. Review-status CHECK constraints (idempotent via pg_constraint guard).
-- =============================================================================
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_networkedge_review') THEN
        ALTER TABLE "NetworkEdge" ADD CONSTRAINT "chk_networkedge_review"
            CHECK ("ReviewStatus" IN ('candidate','confirmed','rejected'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_hidden_review') THEN
        ALTER TABLE "drishti_hidden_associations" ADD CONSTRAINT "chk_hidden_review"
            CHECK ("ReviewStatus" IN ('candidate','confirmed','rejected'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_crimepattern_review') THEN
        ALTER TABLE "CrimePattern" ADD CONSTRAINT "chk_crimepattern_review"
            CHECK ("ReviewStatus" IN ('candidate','confirmed','rejected'));
    END IF;
END$$;

-- =============================================================================
-- 6. Backfill: a provenance-verified edge is a CONFIRMED edge (synthetic_
--    unverified stays candidate). Only touches still-default rows (idempotent).
-- =============================================================================
UPDATE "NetworkEdge" SET "ReviewStatus" = 'confirmed'
 WHERE "ProvenanceStatus" = 'verified' AND "ReviewStatus" = 'candidate';

-- =============================================================================
-- 7. Canonical, provenanced, non-archived graph views (the ONLY graph the
--    analytics reads — old/new spaces never mix).
-- =============================================================================
CREATE OR REPLACE VIEW "vw_canonical_graph_node" AS
SELECT g.*
FROM "EntityGraph" g
WHERE g."CanonicalEntityID" IS NOT NULL AND g."IsArchived" = FALSE;
COMMENT ON VIEW "vw_canonical_graph_node" IS
    'Graph nodes that are canonical entities and not archived (excludes the old synthetic identity graph).';

CREATE OR REPLACE VIEW "vw_canonical_graph_edge" AS
SELECT e.*
FROM "NetworkEdge" e
JOIN "EntityGraph" s ON s."EntityID" = e."Source"
JOIN "EntityGraph" t ON t."EntityID" = e."Target"
WHERE e."IsArchived" = FALSE
  AND e."ProvenanceStatus" IS NOT NULL
  AND s."CanonicalEntityID" IS NOT NULL AND s."IsArchived" = FALSE
  AND t."CanonicalEntityID" IS NOT NULL AND t."IsArchived" = FALSE;
COMMENT ON VIEW "vw_canonical_graph_edge" IS
    'Edges between canonical, non-archived nodes that carry a provenance status (no NULL-provenance legacy edges).';

-- =============================================================================
-- 8. Indexes for the archived/live split + review queues.
-- =============================================================================
CREATE INDEX IF NOT EXISTS "idx_entitygraph_live"  ON "EntityGraph" ("CanonicalEntityID") WHERE "IsArchived" = FALSE;
CREATE INDEX IF NOT EXISTS "idx_networkedge_live"   ON "NetworkEdge" ("ProvenanceStatus") WHERE "IsArchived" = FALSE;
CREATE INDEX IF NOT EXISTS "idx_networkedge_review" ON "NetworkEdge" ("ReviewStatus");
CREATE INDEX IF NOT EXISTS "idx_crimeembedding_live" ON "CrimeEmbedding" ("ModelVersionID","SourceType") WHERE "IsArchived" = FALSE;
CREATE INDEX IF NOT EXISTS "idx_hidden_review"      ON "drishti_hidden_associations" ("ReviewStatus");

-- =============================================================================
-- 9. Grants + RLS disabled/NO FORCE + global verification (hackathon).
-- =============================================================================
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'drishti_readonly') THEN
        GRANT SELECT ON "vw_canonical_graph_node" TO drishti_readonly;
        GRANT SELECT ON "vw_canonical_graph_edge" TO drishti_readonly;
    END IF;
END$$;

SELECT fn_disable_rls_all_app();
SELECT fn_assert_rls_disabled();

COMMIT;

-- =============================================================================
-- End of migration 018.
-- =============================================================================
