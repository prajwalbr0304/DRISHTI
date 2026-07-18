-- =============================================================================
-- DRISHTI migration 021 — retarget the approved TabFM workload task to the
--                          DISTRICT (area) level (Phase 13)
-- Target: PostgreSQL 15+ / AWS RDS PostgreSQL (ap-south-1)
-- Depends on: 020 (tabfm-workload-band schema + wl_* FeatureDefinitions)
-- =============================================================================
--
-- Evidence-driven retarget. A read-only signal audit of the synthetic data
-- showed the STATION-level next-quarter case count is pure Poisson noise around
-- a near-constant per-station rate (recent-quarter vs next-quarter correlation
-- ~= 0.00; station 5-year-total CV ~= 0.10), i.e. NOT responsibly predictable —
-- the leakage/quality gate would (correctly) refuse to promote a model on it.
-- The DISTRICT-level workload, by contrast, carries strong, persistent signal
-- (recent-quarter vs next-quarter correlation ~= 0.98; district 5-year-total
-- CV ~= 0.83) because districts are heterogeneous and station-level Poisson
-- noise averages out. 32 districts x ~16 quarterly cutoffs is also precisely the
-- SMALL-tabular regime where TabFM / TabPFN are designed to excel.
--
-- So the single approved aggregate task becomes ``area_workload_band``: the
-- ordinal band of a police DISTRICT's next-quarter case-review workload, for
-- supervisory review-queue / resource planning. The same non-protected,
-- strictly-pre-cutoff ``wl_*`` FeatureDefinitions apply unchanged (they are
-- area/period aggregates); only the task label + subject level change. This is
-- distinct from Phase 12 (a spatial incident FORECAST); Phase 13 is a governed
-- ordinal WORKLOAD-BAND classification with a model card, calibration/abstention
-- and a baseline-benchmarked model lifecycle.
--
-- Aggregate area/period decision support only. RLS stays DISABLED + NO FORCE.
-- Additive + idempotent: safe to re-run.
-- =============================================================================

BEGIN;

-- 1. Retarget the wl_* feature definitions to the area task (idempotent).
UPDATE "FeatureDefinition"
   SET "AllowedTasks" = ARRAY['area_workload_band']
 WHERE "Name" LIKE 'wl\_%' ESCAPE '\'
   AND "AllowedTasks" <> ARRAY['area_workload_band'];

-- 2. Retarget the approved schema (keep its name + version + approval).
UPDATE "FeatureSchemaVersion"
   SET "Task" = 'area_workload_band'
 WHERE "SchemaName" = 'tabfm-workload-band' AND "Version" = '1'
   AND "Task" <> 'area_workload_band';

-- 3. RLS disabled/NO FORCE + verification (hackathon).
SELECT fn_disable_rls_all_app();
SELECT fn_assert_rls_disabled();

COMMIT;

-- =============================================================================
-- End of migration 021.
-- =============================================================================
