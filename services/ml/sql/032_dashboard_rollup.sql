-- DRISHTI migration 032: pre-aggregated case rollup for role-scoped dashboards.
--
-- WHY
-- Every KPI card reads base tables live. /performance/overview alone costs seven
-- sequential aggregate round trips over CaseMaster JOIN Unit JOIN CaseStatusMaster,
-- and with no unit_id/district_id each is a full scan. That is survivable for ten
-- demo seats and not survivable for 1,046 command and station seats plus ~10,700
-- IO seats. The three existing materialized views (mv_crime_stats,
-- mv_district_risk_profile, mv_active_hotspots) are refreshed but read by no KPI
-- endpoint.
--
-- GRAIN
-- One row per (unit, crime head, registered date, case status). Bounded by the
-- case count, not by the cartesian product of its keys: each case contributes to
-- exactly one group, so 100k FIRs produce at most 100k rows. district_id is
-- carried denormalised because CaseMaster has no district column — district is
-- only reachable as PoliceStationID -> Unit.DistrictID, which is why every
-- existing aggregate repeats that join.
--
-- ANALYTICS-ELIGIBILITY POLICY — LOAD-BEARING
-- The predicate below is the SQL emitted by
-- app/cases/analytics_policy.py::analytics_eligible_sql, reproduced inline. It is
-- fail-closed: a case needs a current CaseVersion, and is excluded if that version
-- is public-source curated, flagged out of derived analytics, or carries malformed
-- policy metadata. Omitting it here would make dashboard numbers disagree with
-- /performance/overview for exactly the records the policy exists to exclude.
--
-- Because the predicate reads CaseVersion.SnapshotAttributes, this view is a
-- DERIVED ARTIFACT under that policy: it can go stale when a CaseVersion changes,
-- not only when a case is registered. mv_refresh_state records the policy
-- attestation each refresh was computed under so the serving layer can refuse a
-- rollup built under a superseded policy, mirroring analytics_policy.require_current.

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. Refresh + attestation ledger.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "mv_refresh_state" (
    "matview_name"      VARCHAR PRIMARY KEY,
    "refreshed_at"      TIMESTAMPTZ,
    "policy_version"    VARCHAR,
    "policy_sha256"     VARCHAR,
    "source_row_count"  BIGINT,
    "refresh_seconds"   NUMERIC(10,3),
    "refreshed_by"      VARCHAR,
    CONSTRAINT "chk_mv_refresh_sha" CHECK (
        "policy_sha256" IS NULL OR "policy_sha256" ~ '^[0-9a-f]{64}$')
);

COMMENT ON TABLE "mv_refresh_state" IS
    'Per-materialized-view refresh ledger. policy_version/policy_sha256 record the analytics-policy attestation (app/cases/analytics_policy.py) the refresh ran under; a rollup whose attestation is not current must not be served.';

-- ---------------------------------------------------------------------------
-- 2. mv_case_daily
-- ---------------------------------------------------------------------------
CREATE MATERIALIZED VIEW IF NOT EXISTS "mv_case_daily" AS
SELECT
    cm."PoliceStationID"                      AS unit_id,
    u."DistrictID"                            AS district_id,
    COALESCE(cm."CrimeMajorHeadID", 0)        AS crime_head_id,
    cm."CrimeRegisteredDate"                  AS registered_date,
    COALESCE(cm."CaseStatusID", 0)            AS case_status_id,
    CASE
        WHEN st."CaseStatusName" IN ('Under Investigation', 'Pending Trial',
                                     'Missing - Under Trace') THEN 'open'
        ELSE 'closed'
    END                                       AS status_bucket,
    count(*)                                  AS case_count,
    count(*) FILTER (WHERE cm."GravityOffenceID" = 1) AS heinous_count
FROM "CaseMaster" cm
JOIN "Unit" u ON u."UnitID" = cm."PoliceStationID"
LEFT JOIN "CaseStatusMaster" st ON st."CaseStatusID" = cm."CaseStatusID"
WHERE EXISTS (
        SELECT 1 FROM "CaseVersion" cv_policy
         WHERE cv_policy."CaseMasterID" = cm."CaseMasterID"
           AND cv_policy."IsCurrent" = TRUE)
  AND NOT EXISTS (
        SELECT 1 FROM "CaseVersion" cv_policy
         WHERE cv_policy."CaseMasterID" = cm."CaseMasterID"
           AND cv_policy."IsCurrent" = TRUE
           AND (cv_policy."SnapshotAttributes"->>'record_origin' = 'public_source_curated'
                OR cv_policy."SnapshotAttributes" @> '{"excluded_from_derived_analytics":true}'::jsonb
                OR (cv_policy."SnapshotAttributes" ? 'record_origin'
                    AND jsonb_typeof(cv_policy."SnapshotAttributes"->'record_origin') <> 'string')
                OR (cv_policy."SnapshotAttributes" ? 'excluded_from_derived_analytics'
                    AND jsonb_typeof(cv_policy."SnapshotAttributes"->'excluded_from_derived_analytics') <> 'boolean')))
GROUP BY 1, 2, 3, 4, 5, 6
WITH NO DATA;

COMMENT ON MATERIALIZED VIEW "mv_case_daily" IS
    'Case counts by unit, district, crime head, registration date and status. Applies the fail-closed analytics-eligibility policy inline, so totals reconcile with /performance/overview. crime_head_id 0 = unclassified; case_status_id 0 = status not set. Refresh state and policy attestation in mv_refresh_state.';

-- Unique key for REFRESH ... CONCURRENTLY. COALESCE in the view definition keeps
-- both nullable keys non-null, because NULLs are distinct in a unique index and
-- would defeat the uniqueness the concurrent refresh depends on.
CREATE UNIQUE INDEX IF NOT EXISTS "idx_mv_case_daily_key"
    ON "mv_case_daily" (unit_id, crime_head_id, registered_date, case_status_id);

CREATE INDEX IF NOT EXISTS "idx_mv_case_daily_district_date"
    ON "mv_case_daily" (district_id, registered_date);
CREATE INDEX IF NOT EXISTS "idx_mv_case_daily_unit_date"
    ON "mv_case_daily" (unit_id, registered_date);
CREATE INDEX IF NOT EXISTS "idx_mv_case_daily_head_date"
    ON "mv_case_daily" (crime_head_id, registered_date);
CREATE INDEX IF NOT EXISTS "idx_mv_case_daily_open"
    ON "mv_case_daily" (district_id, unit_id) WHERE status_bucket = 'open';

INSERT INTO "mv_refresh_state" ("matview_name") VALUES ('mv_case_daily')
ON CONFLICT ("matview_name") DO NOTHING;

-- ---------------------------------------------------------------------------
-- 3. Indexes supporting the live queries that cannot use the rollup
--    (case lists, ageing, and any per-case drill-down).
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS "idx_casemaster_station_status_date"
    ON "CaseMaster" ("PoliceStationID", "CaseStatusID", "CrimeRegisteredDate");

CREATE INDEX IF NOT EXISTS "idx_casemaster_officer_status"
    ON "CaseMaster" ("PolicePersonID", "CaseStatusID");

-- The open-case filter is a text predicate on CaseStatusMaster."CaseStatusName"
-- with no supporting index, so every open-case aggregate seq-scans the lookup.
-- A partial index on CaseMaster is not possible here: the openness test lives in
-- the joined table, not in CaseMaster.
CREATE INDEX IF NOT EXISTS "idx_casestatusmaster_name"
    ON "CaseStatusMaster" ("CaseStatusName");

CREATE INDEX IF NOT EXISTS "idx_caseversion_current_policy"
    ON "CaseVersion" ("CaseMasterID") WHERE "IsCurrent" = TRUE;

ALTER TABLE "mv_refresh_state" DISABLE ROW LEVEL SECURITY;

COMMIT;

-- ---------------------------------------------------------------------------
-- First population (outside the transaction; CONCURRENTLY cannot run inside one
-- and the view has no data yet, so the first refresh is necessarily blocking).
-- ---------------------------------------------------------------------------
-- REFRESH MATERIALIZED VIEW "mv_case_daily";
--
-- Subsequent refreshes, once populated:
-- REFRESH MATERIALIZED VIEW CONCURRENTLY "mv_case_daily";
--
-- Register in app/matviews.py ALL_MATVIEWS so the scheduled refresh picks it up,
-- and stamp mv_refresh_state with the current policy attestation in the same
-- transaction as the refresh.
