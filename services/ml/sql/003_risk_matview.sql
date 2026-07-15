-- =============================================================================
-- DRISHTI Phase 9 — keep mv_district_risk_profile as AREA risk only
-- =============================================================================
-- Offender-level risk rows (Phase 9) set DistrictID purely to satisfy the
-- CrimeRiskScore scope CHECK. The district risk profile must reflect AREA risk,
-- not an arbitrary offender, so we redefine the matview to consider only rows
-- with no accused/case scope (i.e. genuine district/unit area scores).
-- =============================================================================

BEGIN;

DROP MATERIALIZED VIEW IF EXISTS "mv_district_risk_profile" CASCADE;

CREATE MATERIALIZED VIEW "mv_district_risk_profile" AS
SELECT DISTINCT ON (r."DistrictID")
    r."DistrictID",
    d."DistrictName",
    r."RiskScore",
    r."RiskLevel",
    r."ValidFrom"
FROM "CrimeRiskScore" r
JOIN "District" d ON d."DistrictID" = r."DistrictID"
WHERE r."DistrictID" IS NOT NULL
  AND r."AccusedMasterID" IS NULL      -- exclude offender-level rows
  AND r."CaseMasterID" IS NULL         -- exclude case-level rows -> area only
ORDER BY r."DistrictID", r."ValidFrom" DESC
WITH NO DATA;

CREATE UNIQUE INDEX "idx_mv_district_risk_key" ON "mv_district_risk_profile" ("DistrictID");

REFRESH MATERIALIZED VIEW "mv_district_risk_profile";

COMMIT;
