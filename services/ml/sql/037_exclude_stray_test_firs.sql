-- DRISHTI migration 037: exclude the three stray test FIRs from derived analytics.
--
-- WHY
-- Three cases (CaseMasterID 100215, 100238, 100239 — note two share CaseNo
-- '202600001', which no generated case does) were created through the intake API
-- during development and dated 2026-07-21/24/25. The generated corpus ends
-- 2025-12-31 at ~100 cases/day; these three sit seven months past it, alone.
--
-- They break every windowed metric. `as_of` is max(CrimeRegisteredDate) within
-- scope, so for any scope containing them the 90-day window opens on 2026-04-26 —
-- after the real data stops — and "new cases" reads 3 instead of ~5,700 for a DGP.
-- That looks like registrations collapsing, not like an anchor artefact.
--
-- WHY NOT DELETE
-- A DELETE would be destructive and would cascade through CaseVersion, CourtEvent,
-- CaseParty and the rest. It is also unnecessary: the codebase already HAS the
-- mechanism for "this record exists but must not enter derived analytics" — the
-- fail-closed eligibility predicate in app/cases/analytics_policy.py, keyed on
-- CaseVersion.SnapshotAttributes. Setting the flag is a one-column update that
-- every consumer already honours, because the predicate is embedded in
-- analytics_eligible_sql AND in the mv_case_daily definition. The rows stay
-- readable as case records; they simply stop skewing aggregates.
--
-- CONSEQUENCE: THE ROLLUP ATTESTATION CHANGES
-- These rows now join the exclusion cohort, which is exactly what the analytics
-- policy digest covers, so mv_case_daily's recorded attestation becomes stale and
-- /dashboard/summary will refuse to serve until it is refreshed. That is the gate
-- doing its job. Refresh after applying:
--     python -c "from app import db, matviews; \
--                conn=db.rw_conn().__enter__(); \
--                matviews.refresh_matview(conn,'mv_case_daily')"

BEGIN;

-- Targeted by DATE, not by hard-coded ids, so the migration also catches any other
-- ad-hoc record left past the generated corpus. Restricted to the current version
-- of each case, which is what the policy predicate reads.
UPDATE "CaseVersion" cv
   SET "SnapshotAttributes" =
         COALESCE(cv."SnapshotAttributes", '{}'::jsonb)
         || jsonb_build_object(
              'excluded_from_derived_analytics', TRUE,
              'exclusion_reason', 'Ad-hoc test FIR created through the intake API '
                                  'outside the generated corpus window; skews '
                                  'as-of-anchored aggregates.',
              'excluded_by', 'migration:037')
  FROM "CaseMaster" cm
 WHERE cm."CaseMasterID" = cv."CaseMasterID"
   AND cv."IsCurrent" = TRUE
   AND cm."CrimeRegisteredDate" > DATE '2025-12-31'
   -- Idempotent: leave rows that already carry the flag.
   AND NOT (cv."SnapshotAttributes" @> '{"excluded_from_derived_analytics":true}'::jsonb);

COMMIT;

-- ---------------------------------------------------------------------------
-- Verification
--   -- the three are now excluded (expect 3)
--   SELECT count(*) FROM "CaseVersion"
--    WHERE "IsCurrent" AND "SnapshotAttributes"->>'excluded_by' = 'migration:037';
--
--   -- the analytics as-of is back inside the generated corpus (expect 2025-12-31)
--   SELECT max(cm."CrimeRegisteredDate")
--     FROM "CaseMaster" cm
--    WHERE EXISTS (SELECT 1 FROM "CaseVersion" cv
--                   WHERE cv."CaseMasterID" = cm."CaseMasterID" AND cv."IsCurrent")
--      AND NOT EXISTS (
--            SELECT 1 FROM "CaseVersion" cv
--             WHERE cv."CaseMasterID" = cm."CaseMasterID" AND cv."IsCurrent"
--               AND cv."SnapshotAttributes"
--                   @> '{"excluded_from_derived_analytics":true}'::jsonb);
-- ---------------------------------------------------------------------------
