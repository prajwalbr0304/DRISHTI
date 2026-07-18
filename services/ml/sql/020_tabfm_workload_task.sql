-- =============================================================================
-- DRISHTI migration 020 — approved TabFM AGGREGATE task + retire synthetic
--                          individual offender-risk (Phase 13)
-- Target: PostgreSQL 15+ / AWS RDS PostgreSQL (ap-south-1)
-- Depends on: 008 (FeatureDefinition/FeatureSchemaVersion/TrainingDatasetSnapshot/
--             PredictionRequest/Result/Review + ModelVersion governance columns),
--             police_fir_intelligence.sql (ModelVersion, CrimeRiskScore,
--             ModelInference)
-- =============================================================================
--
-- Phase 13 replaces the synthetic per-offender "crime risk" score with an
-- APPROVED AGGREGATE / review-support task: a STATION case-review WORKLOAD BAND.
-- The target is the banded count of cases a police station (Unit) will register
-- in a forward label window — an area/period resource-planning signal, never a
-- person-level criminal-justice judgement. TabFM/TabPFN are candidate models for
-- this tabular classification; XGBoost/HistGradientBoosting + a prior-period rule
-- are the baselines (see app/workload/*). This migration:
--
--   1. Seeds the non-protected, aggregate, strictly-pre-cutoff FeatureDefinitions
--      and an APPROVED FeatureSchemaVersion ("tabfm-workload-band" v1, task
--      "station_workload_band") so the task binds to the governed
--      FeatureSnapshot -> PredictionRequest -> PredictionResult contract exactly
--      like any other model (Phase 10). No protected attribute is included.
--   2. Creates "ModelBenchmark" — a typed record of the small/medium/full
--      (500 / 5,000 / full-row) runtime, memory, latency/throughput, cost and
--      metric-vs-baseline benchmark runs the phase requires.
--   3. ARCHIVES / LABELS the existing synthetic individual offender-risk outputs
--      as synthetic-demo-only: retires the per-offender classification
--      ModelVersions and adds a "SyntheticDemoOnly" marker to CrimeRiskScore and
--      to the individual-risk ModelInference rows, so no per-person score can be
--      mistaken for operational truth.
--
-- Aggregate area/period decision support only. RLS stays DISABLED + NO FORCE
-- (hackathon). No RLS policies. Additive + idempotent: safe to re-run.
-- =============================================================================

BEGIN;

-- =============================================================================
-- 1. Governed workload feature schema (approved, non-protected, pre-cutoff)
-- =============================================================================
-- Aggregate, STATION-level, strictly-pre-cutoff features. All Sensitivity =
-- 'normal' (no caste/religion/gender/juvenile/protected attribute enters the
-- workload schema). AllowedTasks pins each to the single approved task.
INSERT INTO "FeatureDefinition"
    ("Name","ValueType","Description","SourceTable","SourceField","Transformation",
     "WindowSpec","ObservationCutoffBehavior","Sensitivity","AllowedTasks",
     "MissingPolicy","StalePolicy","Owner","ApprovalStatus")
VALUES
    ('wl_recent_case_volume','numeric','Cases registered at the station in the trailing 90 days (pre-cutoff).',
     'CaseMaster','CrimeRegisteredDate','count_over_window','trailing_90d','strict_pre_cutoff','normal',
     ARRAY['station_workload_band'],'null_ok','invalidate_on_source_change','workload','approved'),
    ('wl_prev_quarter_volume','numeric','Cases registered at the station in the prior 90-180 day window (pre-cutoff).',
     'CaseMaster','CrimeRegisteredDate','count_over_window','trailing_90_180d','strict_pre_cutoff','normal',
     ARRAY['station_workload_band'],'null_ok','invalidate_on_source_change','workload','approved'),
    ('wl_trailing_year_volume','numeric','Cases registered at the station in the trailing 365 days (pre-cutoff).',
     'CaseMaster','CrimeRegisteredDate','count_over_window','trailing_365d','strict_pre_cutoff','normal',
     ARRAY['station_workload_band'],'null_ok','invalidate_on_source_change','workload','approved'),
    ('wl_trend_slope','numeric','OLS slope of the station monthly case series over the trailing 12 months (pre-cutoff).',
     'CaseMaster','CrimeRegisteredDate','ols_slope','trailing_12m','strict_pre_cutoff','normal',
     ARRAY['station_workload_band'],'null_ok','invalidate_on_source_change','workload','approved'),
    ('wl_seasonal_index','numeric','Upcoming-quarter seasonal factor from the station history (pre-cutoff, multiplicative).',
     'CaseMaster','CrimeRegisteredDate','seasonal_factor','trailing_24m','strict_pre_cutoff','normal',
     ARRAY['station_workload_band'],'null_ok','invalidate_on_source_change','workload','approved'),
    ('wl_prioryear_same_quarter','numeric','Cases registered at the station in the same quarter one year before the cutoff.',
     'CaseMaster','CrimeRegisteredDate','lag_12m_window','quarter_lag_12m','strict_pre_cutoff','normal',
     ARRAY['station_workload_band'],'null_ok','invalidate_on_source_change','workload','approved'),
    ('wl_chargesheet_trailing_year','numeric','Charge sheets FILED at the station in the trailing 365 days by charge-sheet date (pre-cutoff throughput).',
     'ChargesheetDetails','csdate','count_over_window','trailing_365d','strict_pre_cutoff','normal',
     ARRAY['station_workload_band'],'null_ok','invalidate_on_source_change','workload','approved'),
    ('wl_backlog_ratio','numeric','Trailing-year registered cases not yet charge-sheeted by the cutoff, as a share of trailing-year registrations (backlog proxy).',
     'CaseMaster','CrimeRegisteredDate','backlog_ratio','trailing_365d','strict_pre_cutoff','normal',
     ARRAY['station_workload_band'],'null_ok','invalidate_on_source_change','workload','approved'),
    ('wl_history_months','numeric','Observed months of station history available at the cutoff (data sufficiency for abstention).',
     'CaseMaster','CrimeRegisteredDate','count_months','all','strict_pre_cutoff','normal',
     ARRAY['station_workload_band'],'null_ok','invalidate_on_source_change','workload','approved'),
    ('wl_active_months_share','numeric','Share of the trailing 12 months in which the station registered at least one case (pre-cutoff).',
     'CaseMaster','CrimeRegisteredDate','active_share','trailing_12m','strict_pre_cutoff','normal',
     ARRAY['station_workload_band'],'null_ok','invalidate_on_source_change','workload','approved')
ON CONFLICT ("Name") DO NOTHING;

-- Approved schema binding those definitions (idempotent on SchemaName+Version).
DO $$
DECLARE
    v_ids JSONB;
BEGIN
    SELECT to_jsonb(array_agg("FeatureDefinitionID" ORDER BY "FeatureDefinitionID"))
      INTO v_ids
    FROM "FeatureDefinition"
    WHERE "Name" IN ('wl_recent_case_volume','wl_prev_quarter_volume','wl_trailing_year_volume',
                     'wl_trend_slope','wl_seasonal_index','wl_prioryear_same_quarter',
                     'wl_chargesheet_trailing_year','wl_backlog_ratio','wl_history_months',
                     'wl_active_months_share');

    IF NOT EXISTS (SELECT 1 FROM "FeatureSchemaVersion"
                   WHERE "SchemaName" = 'tabfm-workload-band' AND "Version" = '1') THEN
        INSERT INTO "FeatureSchemaVersion"
            ("SchemaName","Version","FeatureDefinitionIDs","Task","Status","ApprovedByActor","ApprovedAt")
        VALUES ('tabfm-workload-band','1', COALESCE(v_ids, '[]'::jsonb),
                'station_workload_band','approved','datagen-system', now());
    END IF;
END$$;

-- =============================================================================
-- 2. Model benchmark record (500 / 5,000 / full-row runtime + cost + metrics)
-- =============================================================================
CREATE TABLE IF NOT EXISTS "ModelBenchmark" (
    "ModelBenchmarkID" BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    "ModelVersionID"   INTEGER REFERENCES "ModelVersion" ("ModelVersionID"),
    "ModelName"        VARCHAR NOT NULL,
    "ModelFamily"      VARCHAR,                     -- foundation|baseline
    "Task"             VARCHAR NOT NULL,
    "RowScale"         INTEGER NOT NULL,            -- rows actually used (500/5000/full)
    "ScaleLabel"       VARCHAR,                     -- small|medium|full
    "Device"           VARCHAR,                     -- cpu|cuda
    "FitSeconds"       NUMERIC,
    "PredictSeconds"   NUMERIC,
    "TotalSeconds"     NUMERIC,
    "LatencyMsPerRow"  NUMERIC,
    "ThroughputRowsPerSec" NUMERIC,
    "PeakRssMB"        NUMERIC,
    "GpuMemMB"         NUMERIC,                     -- NULL when CPU-only
    "Accuracy"         NUMERIC,
    "MacroF1"          NUMERIC,
    "QWK"              NUMERIC,                     -- quadratic weighted kappa (ordinal)
    "ECE"              NUMERIC,                     -- expected calibration error
    "CostEstimate"     JSONB NOT NULL DEFAULT '{}'::jsonb,
    "Metrics"          JSONB NOT NULL DEFAULT '{}'::jsonb,
    "Available"        BOOLEAN NOT NULL DEFAULT TRUE,   -- FALSE = deferred (e.g. CPU-infeasible TabFM)
    "Note"             TEXT,
    "Actor"            VARCHAR,
    "CreatedAt"        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT "chk_modelbenchmark_scale" CHECK ("RowScale" >= 1)
);
COMMENT ON TABLE "ModelBenchmark" IS
    'Small/medium/full (500/5,000/full-row) benchmark of a model on a task: runtime, CPU/GPU memory, latency/throughput, cost estimate and held-out metrics vs baselines. Phase 13 evidence.';

CREATE INDEX IF NOT EXISTS "idx_modelbenchmark_model" ON "ModelBenchmark" ("ModelVersionID");
CREATE INDEX IF NOT EXISTS "idx_modelbenchmark_task"  ON "ModelBenchmark" ("Task");
CREATE INDEX IF NOT EXISTS "idx_modelbenchmark_time"  ON "ModelBenchmark" ("CreatedAt");

-- =============================================================================
-- 3. Archive / label the synthetic individual offender-risk outputs
-- =============================================================================
-- 3a. Marker columns. CrimeRiskScore is the legacy per-offender/area risk store;
--     every row is a synthetic demo artefact -> default TRUE. ModelInference is a
--     shared audit table (forecast/nlp/etc.), so default FALSE and mark only the
--     retired individual-risk model rows below.
ALTER TABLE "CrimeRiskScore"  ADD COLUMN IF NOT EXISTS "SyntheticDemoOnly" BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE "ModelInference"  ADD COLUMN IF NOT EXISTS "SyntheticDemoOnly" BOOLEAN NOT NULL DEFAULT FALSE;
COMMENT ON COLUMN "CrimeRiskScore"."SyntheticDemoOnly" IS
    'Phase 13: the per-offender/area risk score is a retired synthetic demo artefact and must NOT be presented as operational truth.';

-- 3b. Retire the per-offender risk classification ModelVersions (Phase 9
--     synthetic offender-risk). Matched by the exact legacy model names AND
--     ModelType='classification' so the new aggregate workload models (distinct
--     names) are never touched. Idempotent.
UPDATE "ModelVersion"
   SET "ApprovalStatus" = 'retired',
       "Environment"    = 'synthetic_demo_only',
       "EvaluationReport" = COALESCE("EvaluationReport", '{}'::jsonb)
           || jsonb_build_object(
                'retired_by', 'migration_020',
                'reason', 'Synthetic individual offender-risk target retired in Phase 13; '
                          'replaced by the approved aggregate station_workload_band task.',
                'operational_use', false)
 WHERE "ModelName" IN ('drishti-tabfm','drishti-tabpfn','drishti-tabfm-incontext',
                       'drishti-xgboost','drishti-histgbm')
   AND "ModelType" = 'classification';

-- 3c. Flag the individual-risk inference/score rows (0 today, but idempotent and
--     future-proof: any accused-level score or its inference audit is marked).
UPDATE "ModelInference" mi
   SET "SyntheticDemoOnly" = TRUE
  FROM "ModelVersion" mv
 WHERE mv."ModelVersionID" = mi."ModelVersionID"
   AND mv."ModelName" IN ('drishti-tabfm','drishti-tabpfn','drishti-tabfm-incontext',
                          'drishti-xgboost','drishti-histgbm')
   AND mv."ModelType" = 'classification'
   AND mi."SyntheticDemoOnly" = FALSE;

-- =============================================================================
-- 4. Grants + RLS disabled/NO FORCE + verification (hackathon).
-- =============================================================================
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'drishti_readonly') THEN
        EXECUTE 'GRANT SELECT ON "ModelBenchmark" TO drishti_readonly';
    END IF;
END$$;

SELECT fn_disable_rls_all_app();
SELECT fn_assert_rls_disabled();

COMMIT;

-- =============================================================================
-- End of migration 020.
-- =============================================================================
