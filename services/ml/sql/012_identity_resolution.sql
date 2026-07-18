-- =============================================================================
-- DRISHTI migration 012 — canonical-identity backfill, graph-link verification,
--                          canonical case-link views, resolution-inbox seed
-- Target: PostgreSQL 15+ (live: AWS RDS PostgreSQL 17.10)
-- Depends on: 005_security_rls_audit.sql, 007_identity_case_workflow.sql
-- =============================================================================
--
-- Phase 4 (canonical identity + entity resolution). The datagen v2 load already
-- minted stable CanonicalPersonID/CanonicalEntityID and linked every EntityGraph
-- person node + CasePartyRole. This migration:
--   1. backfills the legacy Accused/Victim/Complainant CanonicalPersonID columns
--      from CasePartyRole (canonical linkage — NEVER from names);
--   2. adds fn_assert_graph_persons_linked() so the "every graph-person node is
--      canonically linked or explicitly unverified" guarantee is checkable;
--   3. adds canonical case-link views that replace name-equality joins;
--   4. seeds a few PENDING EntityResolutionCandidate rows (same-name/different-
--      person) for the review inbox — proposals only, NEVER auto-merged.
--
-- RLS stays DISABLED + NO FORCE (hackathon). Additive + idempotent.
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- 1. Backfill legacy person FKs from CasePartyRole (canonical, not names).
--    Accused carries a direct CasePartyRoleID; Victim/Complainant are matched
--    through CasePartyRole.LegacyRefTable/LegacyRefID. Unknown-party rows keep a
--    NULL CanonicalPersonID (they are genuinely unidentified — no invented id).
-- -----------------------------------------------------------------------------
UPDATE "Accused" a
SET "CanonicalPersonID" = r."CanonicalPersonID"
FROM "CasePartyRole" r
WHERE r."CasePartyRoleID" = a."CasePartyRoleID"
  AND r."CanonicalPersonID" IS NOT NULL
  AND a."CanonicalPersonID" IS NULL;

UPDATE "Victim" v
SET "CanonicalPersonID" = r."CanonicalPersonID"
FROM "CasePartyRole" r
WHERE r."LegacyRefTable" = 'Victim' AND r."LegacyRefID" = v."VictimMasterID"
  AND r."CanonicalPersonID" IS NOT NULL
  AND v."CanonicalPersonID" IS NULL;

UPDATE "ComplainantDetails" c
SET "CanonicalPersonID" = r."CanonicalPersonID"
FROM "CasePartyRole" r
WHERE r."LegacyRefTable" = 'ComplainantDetails' AND r."LegacyRefID" = c."ComplainantID"
  AND r."CanonicalPersonID" IS NOT NULL
  AND c."CanonicalPersonID" IS NULL;

-- -----------------------------------------------------------------------------
-- 2. Verification: every EntityGraph person node is canonically linked.
--    Non-person nodes (phone/vehicle/...) and explicit unverified nodes are ok.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_assert_graph_persons_linked()
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
    unlinked BIGINT;
BEGIN
    SELECT count(*) INTO unlinked
    FROM "EntityGraph"
    WHERE "EntityType"::text = 'person'
      AND "CanonicalEntityID" IS NULL
      AND COALESCE("Attributes"->>'provenance_status', '') <> 'synthetic_unverified';
    IF unlinked > 0 THEN
        RAISE EXCEPTION
            'IDENTITY CHECK FAILED: % graph-person node(s) are neither linked to a '
            'CanonicalEntity nor marked synthetic_unverified.', unlinked;
    END IF;
    RAISE NOTICE 'IDENTITY CHECK PASSED: all graph-person nodes are canonically linked or explicitly unverified.';
END;
$$;
COMMENT ON FUNCTION fn_assert_graph_persons_linked() IS
    'Phase 4: raise unless every EntityGraph person node links to a CanonicalEntity (or is explicitly synthetic_unverified).';

CREATE OR REPLACE FUNCTION fn_identity_link_stats()
RETURNS JSONB
LANGUAGE sql
STABLE
AS $$
    SELECT jsonb_build_object(
        'canonical_person',       (SELECT count(*) FROM "CanonicalPerson"),
        'canonical_person_merged',(SELECT count(*) FROM "CanonicalPerson" WHERE "ResolutionStatus"='merged'),
        'canonical_organisation', (SELECT count(*) FROM "CanonicalOrganisation"),
        'canonical_entity',       (SELECT count(*) FROM "CanonicalEntity"),
        'case_party_role',        (SELECT count(*) FROM "CasePartyRole"),
        'graph_person_nodes',     (SELECT count(*) FROM "EntityGraph" WHERE "EntityType"::text='person'),
        'graph_person_linked',    (SELECT count(*) FROM "EntityGraph" WHERE "EntityType"::text='person' AND "CanonicalEntityID" IS NOT NULL),
        'accused_total',          (SELECT count(*) FROM "Accused"),
        'accused_canonical',      (SELECT count(*) FROM "Accused" WHERE "CanonicalPersonID" IS NOT NULL),
        'network_edges',          (SELECT count(*) FROM "NetworkEdge"),
        'network_edges_provenanced', (SELECT count(*) FROM "NetworkEdge" WHERE "ProvenanceStatus" IS NOT NULL),
        'resolution_candidates_pending', (SELECT count(*) FROM "EntityResolutionCandidate" WHERE "Status"='pending'),
        'merge_history',          (SELECT count(*) FROM "EntityMergeHistory")
    );
$$;
COMMENT ON FUNCTION fn_identity_link_stats() IS 'Phase 4 canonical-identity coverage stats (for admin/report).';

-- -----------------------------------------------------------------------------
-- 3. Canonical case-link views (replace name-equality cross-case joins).
--    Two cases are related iff they share a CANONICAL accused person — never a
--    name. Used by the case-network and geo case-link reads.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW "vw_related_cases_by_person" AS
SELECT DISTINCT
    r1."CaseMasterID"        AS "CaseMasterID",
    r2."CaseMasterID"        AS "RelatedCaseMasterID",
    r1."CanonicalPersonID"   AS "CanonicalPersonID",
    p."PublicRef"            AS "PersonRef",
    p."DisplayLabel"         AS "PersonLabel"
FROM "CasePartyRole" r1
JOIN "CasePartyRole" r2
  ON r2."CanonicalPersonID" = r1."CanonicalPersonID"
 AND r2."CaseMasterID" <> r1."CaseMasterID"
 AND r2."RoleType" = 'accused'
JOIN "CanonicalPerson" p ON p."CanonicalPersonID" = r1."CanonicalPersonID"
WHERE r1."RoleType" = 'accused'
  AND r1."CanonicalPersonID" IS NOT NULL
  AND p."IsUnknown" = FALSE;
COMMENT ON VIEW "vw_related_cases_by_person" IS
    'Cases related through a SHARED CANONICAL accused person (replaces AccusedName-equality joins).';

-- -----------------------------------------------------------------------------
-- 4. Seed PENDING resolution candidates for the review inbox (proposals only).
--    Same DisplayLabel + different CanonicalPersonID => a review candidate. Name
--    similarity is a REVIEW FEATURE here, never an automatic merge. Idempotent:
--    only seeds when no pending candidates exist and the pair isn't already known.
-- -----------------------------------------------------------------------------
DO $$
DECLARE
    n_pending INTEGER;
BEGIN
    SELECT count(*) INTO n_pending FROM "EntityResolutionCandidate" WHERE "Status"='pending';
    IF n_pending = 0 THEN
        INSERT INTO "EntityResolutionCandidate"
            ("CanonicalPersonA","CanonicalPersonB","Method","Score","MatchFeatures","Status")
        SELECT
            LEAST(a."CanonicalPersonID", b."CanonicalPersonID"),
            GREATEST(a."CanonicalPersonID", b."CanonicalPersonID"),
            'deterministic',
            0.60,
            jsonb_build_object(
                'shared_display_label', a."DisplayLabel",
                'feature', 'exact_display_label_match',
                'note', 'Same synthetic name, distinct persons. Human review only; NOT auto-merged.'),
            'pending'
        FROM "CanonicalPerson" a
        JOIN "CanonicalPerson" b
          ON b."DisplayLabel" = a."DisplayLabel"
         AND b."CanonicalPersonID" > a."CanonicalPersonID"
        WHERE a."DisplayLabel" IS NOT NULL
          AND a."ResolutionStatus" = 'canonical'
          AND b."ResolutionStatus" = 'canonical'
          AND a."IsUnknown" = FALSE AND b."IsUnknown" = FALSE
          AND NOT EXISTS (
                SELECT 1 FROM "EntityResolutionCandidate" e
                WHERE e."CanonicalPersonA" = LEAST(a."CanonicalPersonID", b."CanonicalPersonID")
                  AND e."CanonicalPersonB" = GREATEST(a."CanonicalPersonID", b."CanonicalPersonID"))
        LIMIT 15;
        RAISE NOTICE 'Seeded % pending resolution candidate(s) for the review inbox.',
            (SELECT count(*) FROM "EntityResolutionCandidate" WHERE "Status"='pending');
    ELSE
        RAISE NOTICE 'Resolution inbox already has % pending candidate(s); no seed.', n_pending;
    END IF;
END$$;

-- -----------------------------------------------------------------------------
-- 4b. Indexes to keep identity search + candidate generation fast at 200k+ rows
--     (trigram on DisplayLabel powers ILIKE search + the %% similarity operator).
-- -----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS "gin_canonperson_label_trgm"
    ON "CanonicalPerson" USING GIN ("DisplayLabel" gin_trgm_ops);
CREATE INDEX IF NOT EXISTS "idx_canonperson_status"
    ON "CanonicalPerson" ("ResolutionStatus");
CREATE INDEX IF NOT EXISTS "idx_erc_pair"
    ON "EntityResolutionCandidate" ("CanonicalPersonA", "CanonicalPersonB");

-- -----------------------------------------------------------------------------
-- 5. Grants + RLS disabled/NO FORCE + verification (hackathon).
-- -----------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'drishti_readonly') THEN
        GRANT SELECT ON "vw_related_cases_by_person" TO drishti_readonly;
    END IF;
END$$;

SELECT fn_assert_graph_persons_linked();
SELECT fn_disable_rls_all_app();
SELECT fn_assert_rls_disabled();

COMMIT;

-- =============================================================================
-- End of migration 012.
-- =============================================================================
