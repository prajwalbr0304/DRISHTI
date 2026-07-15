-- =============================================================================
-- Police FIR System — Phase 3: AI / Intelligence & Analytics Layer
-- Karnataka Police Department
-- Target: PostgreSQL 15+ / Supabase
-- Depends on: police_fir_schema.sql  (run that FIRST)
-- =============================================================================
--
-- This layer turns the operational FIR database into an analytics/intelligence
-- database. It adds the tables the problem statement implies but the ER diagram
-- does not contain: AI inference, crime prediction, risk scoring, entity/gang
-- networks, embeddings (semantic search), summaries, alerts, hotspots, patterns,
-- officer recommendations, and external social/weather/economic signals.
--
-- Capabilities enabled:
--   * PostGIS          - spatial storage + indexes (already enabled in base)
--   * pgvector         - semantic embeddings + ANN search (HNSW)
--   * pg_trgm          - fuzzy text / trigram search
--   * Full Text Search - generated tsvector columns + GIN indexes
--   * pgRouting        - OPTIONAL graph routing over the entity network
--
-- SECURITY NOTICE: consistent with the base schema, RLS is DISABLED on every
-- table here. On Supabase these tables are reachable through the public API
-- with default anon/authenticated grants. Keep this on a private/trusted
-- network, or re-enable RLS + policies and revoke anon grants before exposing.
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- 0. Extensions
-- -----------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS postgis;      -- spatial (base already enables)
CREATE EXTENSION IF NOT EXISTS vector;       -- pgvector: embeddings + ANN
CREATE EXTENSION IF NOT EXISTS pg_trgm;      -- trigram fuzzy search / GIN text

-- pgRouting is OPTIONAL and not available on every managed platform. Attempt it
-- but never fail the migration if it is unavailable.
DO $$
BEGIN
    BEGIN
        CREATE EXTENSION IF NOT EXISTS pgrouting;
        RAISE NOTICE 'pgRouting enabled.';
    EXCEPTION WHEN OTHERS THEN
        RAISE NOTICE 'pgRouting not available (%). Graph routing helper will be skipped.', SQLERRM;
    END;
END$$;

-- -----------------------------------------------------------------------------
-- 1. Enum types (idempotent)
-- -----------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname='model_type_enum') THEN
        CREATE TYPE model_type_enum AS ENUM
            ('classification','regression','clustering','embedding','nlp','forecasting','anomaly_detection','graph');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname='model_status_enum') THEN
        CREATE TYPE model_status_enum AS ENUM ('training','staged','active','shadow','retired');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname='risk_level_enum') THEN
        CREATE TYPE risk_level_enum AS ENUM ('low','medium','high','critical');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname='pattern_type_enum') THEN
        CREATE TYPE pattern_type_enum AS ENUM ('serial','spree','modus_operandi','temporal','spatial','network','repeat_offender');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname='entity_type_enum') THEN
        CREATE TYPE entity_type_enum AS ENUM
            ('person','accused','complainant','victim','gang','organization','phone','vehicle','bank_account','location','weapon');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname='relationship_type_enum') THEN
        CREATE TYPE relationship_type_enum AS ENUM
            ('co_accused','family','associate','gang_member','financial','communication','same_location','vehicle_link','rival');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname='gang_role_enum') THEN
        CREATE TYPE gang_role_enum AS ENUM ('leader','core','associate','financier','suspect');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname='embedding_source_enum') THEN
        CREATE TYPE embedding_source_enum AS ENUM ('case','brief_facts','accused','victim','pattern','document','summary');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname='summary_type_enum') THEN
        CREATE TYPE summary_type_enum AS ENUM ('case_brief','investigation','pattern','daily_briefing','entity_profile');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname='alert_type_enum') THEN
        CREATE TYPE alert_type_enum AS ENUM ('risk_threshold','hotspot','pattern_match','prediction','anomaly','network');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname='alert_severity_enum') THEN
        CREATE TYPE alert_severity_enum AS ENUM ('info','low','medium','high','critical');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname='alert_status_enum') THEN
        CREATE TYPE alert_status_enum AS ENUM ('open','acknowledged','resolved','dismissed');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname='recommendation_status_enum') THEN
        CREATE TYPE recommendation_status_enum AS ENUM ('suggested','accepted','rejected','expired');
    END IF;
END$$;

-- -----------------------------------------------------------------------------
-- Shared updated-at trigger function
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW."UpdatedAt" := now();
    RETURN NEW;
END;
$$;

-- =============================================================================
-- 2. MODEL REGISTRY & INFERENCE LOG
-- =============================================================================

-- NOTE on embedding dimension: pgvector index columns need a FIXED dimension.
-- 768 matches common sentence-transformer / mpnet models. Change the vector(768)
-- declarations below (and "EmbeddingDim") to match your production model
-- (e.g. 384 for MiniLM, 1536 for OpenAI text-embedding-3-small).

CREATE TABLE "ModelVersion" (
    "ModelVersionID"  INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    "ModelName"       VARCHAR NOT NULL,
    "ModelType"       model_type_enum NOT NULL,
    "Version"         VARCHAR NOT NULL,
    "Framework"       VARCHAR,                       -- e.g. pytorch, sklearn, xgboost, openai
    "ArtifactURI"     VARCHAR,                       -- storage location of the model artifact
    "EmbeddingDim"    INTEGER,                       -- populated for embedding models
    "Hyperparameters" JSONB NOT NULL DEFAULT '{}'::jsonb,
    "Metrics"         JSONB NOT NULL DEFAULT '{}'::jsonb,
    "Status"          model_status_enum NOT NULL DEFAULT 'staged',
    "TrainedAt"       TIMESTAMPTZ,
    "DeployedAt"      TIMESTAMPTZ,
    "CreatedAt"       TIMESTAMPTZ NOT NULL DEFAULT now(),
    "UpdatedAt"       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT "uq_modelversion_name_version" UNIQUE ("ModelName", "Version")
);
COMMENT ON TABLE "ModelVersion" IS 'Registry of ML/AI model versions used across the intelligence layer.';

CREATE TABLE "ModelInference" (
    "InferenceID"    BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    "ModelVersionID" INTEGER NOT NULL REFERENCES "ModelVersion" ("ModelVersionID"),
    "EntityType"     entity_type_enum,              -- what the inference is about
    "CaseMasterID"   INTEGER REFERENCES "CaseMaster" ("CaseMasterID"),
    "RefTable"       VARCHAR,                        -- source table when not a case
    "RefID"          VARCHAR,                        -- source row id when not a case
    "Input"          JSONB NOT NULL DEFAULT '{}'::jsonb,
    "Output"         JSONB NOT NULL DEFAULT '{}'::jsonb,
    "Confidence"     NUMERIC(6,5) CHECK ("Confidence" IS NULL OR "Confidence" BETWEEN 0 AND 1),
    "LatencyMs"      INTEGER CHECK ("LatencyMs" IS NULL OR "LatencyMs" >= 0),
    "InferenceAt"    TIMESTAMPTZ NOT NULL DEFAULT now(),
    "CreatedAt"      TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE "ModelInference" IS 'Audit log of every model inference call (inputs, outputs, confidence, latency).';

-- =============================================================================
-- 3. ENTITY GRAPH  (nodes + edges; edge ids are BIGINT for pgRouting)
-- =============================================================================

CREATE TABLE "EntityGraph" (
    "EntityID"    BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    "EntityType"  entity_type_enum NOT NULL,
    "Label"       VARCHAR NOT NULL,                  -- display name / identifier
    "RefTable"    VARCHAR,                           -- source table (e.g. Accused)
    "RefID"       VARCHAR,                           -- source row id
    "AccusedMasterID" INTEGER REFERENCES "Accused" ("AccusedMasterID"),  -- convenience link
    "Attributes"  JSONB NOT NULL DEFAULT '{}'::jsonb,
    "Embedding"   vector(768),                       -- optional node embedding
    "geom"        geometry(Point, 4326),             -- location nodes
    "SearchVector" tsvector GENERATED ALWAYS AS (
        to_tsvector('english', coalesce("Label",'') || ' ' || coalesce("RefTable",''))
    ) STORED,
    "CreatedAt"   TIMESTAMPTZ NOT NULL DEFAULT now(),
    "UpdatedAt"   TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE "EntityGraph" IS 'Nodes of the intelligence graph: persons, gangs, phones, vehicles, locations, etc.';

CREATE TABLE "NetworkEdge" (
    "EdgeID"           BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    "Source"           BIGINT NOT NULL REFERENCES "EntityGraph" ("EntityID"),  -- pgRouting: source
    "Target"           BIGINT NOT NULL REFERENCES "EntityGraph" ("EntityID"),  -- pgRouting: target
    "RelationshipType" relationship_type_enum NOT NULL,
    "Cost"             DOUBLE PRECISION NOT NULL DEFAULT 1.0,  -- pgRouting edge cost
    "ReverseCost"      DOUBLE PRECISION NOT NULL DEFAULT 1.0,  -- pgRouting reverse cost
    "Directed"         BOOLEAN NOT NULL DEFAULT FALSE,
    "Weight"           NUMERIC,                        -- domain weight / strength
    "Confidence"       NUMERIC(6,5) CHECK ("Confidence" IS NULL OR "Confidence" BETWEEN 0 AND 1),
    "Properties"       JSONB NOT NULL DEFAULT '{}'::jsonb,
    "ValidFrom"        TIMESTAMPTZ,
    "ValidTo"          TIMESTAMPTZ,
    "CreatedAt"        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT "chk_networkedge_no_self_loop" CHECK ("Source" <> "Target")
);
COMMENT ON TABLE "NetworkEdge" IS 'Edges between entities. EdgeID/Source/Target/Cost/ReverseCost are pgRouting-compatible.';

CREATE TABLE "GangMembership" (
    "GangMembershipID" INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    "GangEntityID"     BIGINT NOT NULL REFERENCES "EntityGraph" ("EntityID"),  -- entity of type 'gang'
    "MemberEntityID"   BIGINT REFERENCES "EntityGraph" ("EntityID"),           -- entity of type 'person'
    "AccusedMasterID"  INTEGER REFERENCES "Accused" ("AccusedMasterID"),       -- optional direct link
    "Role"             gang_role_enum NOT NULL DEFAULT 'suspect',
    "JoinedDate"       DATE,
    "LeftDate"         DATE,
    "IsActive"         BOOLEAN NOT NULL DEFAULT TRUE,
    "Confidence"       NUMERIC(6,5) CHECK ("Confidence" IS NULL OR "Confidence" BETWEEN 0 AND 1),
    "Source"           VARCHAR,
    "CreatedAt"        TIMESTAMPTZ NOT NULL DEFAULT now(),
    "UpdatedAt"        TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE "GangMembership" IS 'Gang affiliation of persons/accused with role and active window.';

-- =============================================================================
-- 4. RISK, PREDICTION, HOTSPOTS, PATTERNS
-- =============================================================================

CREATE TABLE "CrimeRiskScore" (
    "RiskScoreID"    BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    "CaseMasterID"   INTEGER REFERENCES "CaseMaster" ("CaseMasterID"),
    "UnitID"         INTEGER REFERENCES "Unit" ("UnitID"),
    "DistrictID"     INTEGER REFERENCES "District" ("DistrictID"),
    "ModelVersionID" INTEGER REFERENCES "ModelVersion" ("ModelVersionID"),
    "RiskScore"      NUMERIC(6,5) NOT NULL CHECK ("RiskScore" BETWEEN 0 AND 1),
    "RiskLevel"      risk_level_enum NOT NULL,
    "Factors"        JSONB NOT NULL DEFAULT '{}'::jsonb,   -- explainability / SHAP-style contributions
    "geom"           geometry(Point, 4326),
    "ValidFrom"      TIMESTAMPTZ NOT NULL DEFAULT now(),
    "ValidTo"        TIMESTAMPTZ,
    "CreatedAt"      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT "chk_riskscore_scope" CHECK (
        "CaseMasterID" IS NOT NULL OR "UnitID" IS NOT NULL OR "DistrictID" IS NOT NULL
    )
);
COMMENT ON TABLE "CrimeRiskScore" IS 'Risk scores for a case or an area (unit/district) with explainability factors.';

CREATE TABLE "CrimePrediction" (
    "PredictionID"    BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    "ModelVersionID"  INTEGER REFERENCES "ModelVersion" ("ModelVersionID"),
    "DistrictID"      INTEGER REFERENCES "District" ("DistrictID"),
    "UnitID"          INTEGER REFERENCES "Unit" ("UnitID"),
    "CrimeHeadID"     INTEGER REFERENCES "CrimeHead" ("CrimeHeadID"),
    "PredictionStart" TIMESTAMPTZ NOT NULL,          -- start of forecast window
    "PredictionEnd"   TIMESTAMPTZ NOT NULL,          -- end of forecast window
    "PredictedCount"  NUMERIC,                        -- expected number of incidents
    "Probability"     NUMERIC(6,5) CHECK ("Probability" IS NULL OR "Probability" BETWEEN 0 AND 1),
    "Confidence"      NUMERIC(6,5) CHECK ("Confidence" IS NULL OR "Confidence" BETWEEN 0 AND 1),
    "Features"        JSONB NOT NULL DEFAULT '{}'::jsonb,
    "geom"            geometry(Geometry, 4326),       -- predicted area (point or polygon)
    "CreatedAt"       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT "chk_prediction_window" CHECK ("PredictionEnd" >= "PredictionStart")
);
COMMENT ON TABLE "CrimePrediction" IS 'Forward-looking crime forecasts by area, crime head and time window.';

CREATE TABLE "CrimeHotspot" (
    "HotspotID"      BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    "Name"           VARCHAR,
    "DistrictID"     INTEGER REFERENCES "District" ("DistrictID"),
    "UnitID"         INTEGER REFERENCES "Unit" ("UnitID"),
    "CrimeHeadID"    INTEGER REFERENCES "CrimeHead" ("CrimeHeadID"),
    "ModelVersionID" INTEGER REFERENCES "ModelVersion" ("ModelVersionID"),
    "geom"           geometry(Geometry, 4326) NOT NULL,   -- hotspot polygon/multipolygon
    "Centroid"       geometry(Point, 4326),
    "Intensity"      NUMERIC,                              -- KDE / Getis-Ord score
    "CaseCount"      INTEGER CHECK ("CaseCount" IS NULL OR "CaseCount" >= 0),
    "PeriodStart"    DATE,
    "PeriodEnd"      DATE,
    "DetectedAt"     TIMESTAMPTZ NOT NULL DEFAULT now(),
    "IsActive"       BOOLEAN NOT NULL DEFAULT TRUE,
    "CreatedAt"      TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE "CrimeHotspot" IS 'Spatial crime clusters (KDE / hotspot analysis) with polygon geometry.';

CREATE TABLE "CrimePattern" (
    "PatternID"      BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    "PatternType"    pattern_type_enum NOT NULL,
    "Name"           VARCHAR NOT NULL,
    "Description"    TEXT,
    "CrimeHeadID"    INTEGER REFERENCES "CrimeHead" ("CrimeHeadID"),
    "ModelVersionID" INTEGER REFERENCES "ModelVersion" ("ModelVersionID"),
    "Confidence"     NUMERIC(6,5) CHECK ("Confidence" IS NULL OR "Confidence" BETWEEN 0 AND 1),
    "Attributes"     JSONB NOT NULL DEFAULT '{}'::jsonb,
    "geom"           geometry(Geometry, 4326),
    "SearchVector"   tsvector GENERATED ALWAYS AS (
        to_tsvector('english', coalesce("Name",'') || ' ' || coalesce("Description",''))
    ) STORED,
    "DetectedAt"     TIMESTAMPTZ NOT NULL DEFAULT now(),
    "IsActive"       BOOLEAN NOT NULL DEFAULT TRUE,
    "CreatedAt"      TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE "CrimePattern" IS 'Detected crime patterns: serial offences, MO matches, temporal/spatial/network patterns.';

-- Junction: which cases support a detected pattern (one FIR can back many patterns).
CREATE TABLE "CrimePatternCase" (
    "PatternID"    BIGINT NOT NULL REFERENCES "CrimePattern" ("PatternID") ON DELETE CASCADE,
    "CaseMasterID" INTEGER NOT NULL REFERENCES "CaseMaster" ("CaseMasterID"),
    "Relevance"    NUMERIC(6,5) CHECK ("Relevance" IS NULL OR "Relevance" BETWEEN 0 AND 1),
    "CreatedAt"    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY ("PatternID", "CaseMasterID")
);
COMMENT ON TABLE "CrimePatternCase" IS 'Links crime patterns to the cases that evidence them.';

-- =============================================================================
-- 5. EMBEDDINGS & AI SUMMARIES  (semantic search / RAG)
-- =============================================================================

CREATE TABLE "CrimeEmbedding" (
    "EmbeddingID"    BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    "SourceType"     embedding_source_enum NOT NULL,
    "CaseMasterID"   INTEGER REFERENCES "CaseMaster" ("CaseMasterID"),
    "RefTable"       VARCHAR,
    "RefID"          VARCHAR,
    "ModelVersionID" INTEGER REFERENCES "ModelVersion" ("ModelVersionID"),
    "Embedding"      vector(768) NOT NULL,           -- dimension must match the model
    "Content"        TEXT,                            -- source text that was embedded
    "ContentHash"    VARCHAR,                         -- dedupe key
    "CreatedAt"      TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE "CrimeEmbedding" IS 'Vector embeddings for semantic similarity search over cases/entities/documents.';

CREATE TABLE "AISummary" (
    "SummaryID"      BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    "SummaryType"    summary_type_enum NOT NULL,
    "CaseMasterID"   INTEGER REFERENCES "CaseMaster" ("CaseMasterID"),
    "RefTable"       VARCHAR,
    "RefID"          VARCHAR,
    "ModelVersionID" INTEGER REFERENCES "ModelVersion" ("ModelVersionID"),
    "SummaryText"    TEXT NOT NULL,
    "TokensUsed"     INTEGER CHECK ("TokensUsed" IS NULL OR "TokensUsed" >= 0),
    "Confidence"     NUMERIC(6,5) CHECK ("Confidence" IS NULL OR "Confidence" BETWEEN 0 AND 1),
    "SearchVector"   tsvector GENERATED ALWAYS AS (to_tsvector('english', coalesce("SummaryText",''))) STORED,
    "GeneratedAt"    TIMESTAMPTZ NOT NULL DEFAULT now(),
    "CreatedAt"      TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE "AISummary" IS 'LLM-generated summaries/briefings for cases, investigations and entities.';

-- =============================================================================
-- 6. ALERTS & OFFICER RECOMMENDATIONS
-- =============================================================================

CREATE TABLE "AlertHistory" (
    "AlertID"        BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    "AlertType"      alert_type_enum NOT NULL,
    "Severity"       alert_severity_enum NOT NULL DEFAULT 'info',
    "Title"          VARCHAR NOT NULL,
    "Message"        TEXT,
    "CaseMasterID"   INTEGER REFERENCES "CaseMaster" ("CaseMasterID"),
    "DistrictID"     INTEGER REFERENCES "District" ("DistrictID"),
    "UnitID"         INTEGER REFERENCES "Unit" ("UnitID"),
    "EntityID"       BIGINT REFERENCES "EntityGraph" ("EntityID"),
    "ModelVersionID" INTEGER REFERENCES "ModelVersion" ("ModelVersionID"),
    "Payload"        JSONB NOT NULL DEFAULT '{}'::jsonb,
    "geom"           geometry(Point, 4326),
    "Status"         alert_status_enum NOT NULL DEFAULT 'open',
    "AcknowledgedBy" INTEGER REFERENCES "Employee" ("EmployeeID"),
    "AcknowledgedAt" TIMESTAMPTZ,
    "CreatedAt"      TIMESTAMPTZ NOT NULL DEFAULT now(),
    "UpdatedAt"      TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE "AlertHistory" IS 'History of intelligence alerts (risk/hotspot/pattern/prediction/anomaly) and their lifecycle.';

CREATE TABLE "OfficerRecommendation" (
    "RecommendationID" BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    "CaseMasterID"     INTEGER NOT NULL REFERENCES "CaseMaster" ("CaseMasterID"),
    "EmployeeID"       INTEGER NOT NULL REFERENCES "Employee" ("EmployeeID"),
    "ModelVersionID"   INTEGER REFERENCES "ModelVersion" ("ModelVersionID"),
    "Score"            NUMERIC(6,5) CHECK ("Score" IS NULL OR "Score" BETWEEN 0 AND 1),
    "RankOrder"        INTEGER CHECK ("RankOrder" IS NULL OR "RankOrder" >= 1),
    "Rationale"        JSONB NOT NULL DEFAULT '{}'::jsonb,
    "Status"           recommendation_status_enum NOT NULL DEFAULT 'suggested',
    "CreatedAt"        TIMESTAMPTZ NOT NULL DEFAULT now(),
    "UpdatedAt"        TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE "OfficerRecommendation" IS 'Model-recommended officers for a case, ranked with rationale.';

-- =============================================================================
-- 7. EXTERNAL SIGNAL / INDICATOR TABLES  (features for models)
-- =============================================================================

CREATE TABLE "SocialIndicator" (
    "SocialIndicatorID" BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    "DistrictID"        INTEGER REFERENCES "District" ("DistrictID"),
    "UnitID"            INTEGER REFERENCES "Unit" ("UnitID"),
    "ObservedDate"      DATE NOT NULL,
    "Population"        BIGINT,
    "PopulationDensity" NUMERIC,
    "LiteracyRate"      NUMERIC(5,2),
    "UnemploymentRate"  NUMERIC(5,2),
    "YouthRatio"        NUMERIC(5,2),
    "MigrationIndex"    NUMERIC,
    "Metrics"           JSONB NOT NULL DEFAULT '{}'::jsonb,
    "Source"            VARCHAR,
    "geom"              geometry(Geometry, 4326),
    "CreatedAt"         TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE "SocialIndicator" IS 'Socio-demographic signals per area/time used as model features.';

CREATE TABLE "WeatherIndicator" (
    "WeatherIndicatorID" BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    "DistrictID"         INTEGER REFERENCES "District" ("DistrictID"),
    "UnitID"             INTEGER REFERENCES "Unit" ("UnitID"),
    "ObservedAt"         TIMESTAMPTZ NOT NULL,
    "TemperatureC"       NUMERIC(5,2),
    "HumidityPct"        NUMERIC(5,2),
    "RainfallMm"         NUMERIC(6,2),
    "WindSpeedKmph"      NUMERIC(6,2),
    "Condition"          VARCHAR,
    "Metrics"            JSONB NOT NULL DEFAULT '{}'::jsonb,
    "Source"             VARCHAR,
    "geom"               geometry(Point, 4326),
    "CreatedAt"          TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE "WeatherIndicator" IS 'Weather observations per area/time used as model features.';

CREATE TABLE "EconomicIndicator" (
    "EconomicIndicatorID" BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    "DistrictID"          INTEGER REFERENCES "District" ("DistrictID"),
    "UnitID"              INTEGER REFERENCES "Unit" ("UnitID"),
    "PeriodStart"         DATE NOT NULL,
    "PeriodEnd"           DATE,
    "PerCapitaIncome"     NUMERIC,
    "UnemploymentRate"    NUMERIC(5,2),
    "PovertyIndex"        NUMERIC,
    "InflationRate"       NUMERIC(5,2),
    "BusinessDensity"     NUMERIC,
    "Metrics"             JSONB NOT NULL DEFAULT '{}'::jsonb,
    "Source"              VARCHAR,
    "geom"                geometry(Geometry, 4326),
    "CreatedAt"           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT "chk_econ_period" CHECK ("PeriodEnd" IS NULL OR "PeriodEnd" >= "PeriodStart")
);
COMMENT ON TABLE "EconomicIndicator" IS 'Economic signals per area/period used as model features.';

-- =============================================================================
-- 8. FULL TEXT SEARCH augmentation of the base operational schema
--    Adds a generated tsvector over CaseMaster.BriefFacts (non-destructive).
-- =============================================================================
ALTER TABLE "CaseMaster"
    ADD COLUMN IF NOT EXISTS "BriefFactsFTS" tsvector
    GENERATED ALWAYS AS (to_tsvector('english', coalesce("BriefFacts", ''))) STORED;

-- =============================================================================
-- 9. TRIGGERS (updated_at maintenance)
-- =============================================================================
CREATE TRIGGER "trg_modelversion_updated"    BEFORE UPDATE ON "ModelVersion"          FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();
CREATE TRIGGER "trg_entitygraph_updated"     BEFORE UPDATE ON "EntityGraph"            FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();
CREATE TRIGGER "trg_gangmembership_updated"  BEFORE UPDATE ON "GangMembership"         FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();
CREATE TRIGGER "trg_alerthistory_updated"    BEFORE UPDATE ON "AlertHistory"           FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();
CREATE TRIGGER "trg_officerrec_updated"      BEFORE UPDATE ON "OfficerRecommendation"  FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

-- =============================================================================
-- 10. INDEXES
-- =============================================================================

-- ---- Foreign-key btree indexes ----------------------------------------------
CREATE INDEX "idx_modelinference_modelversion" ON "ModelInference" ("ModelVersionID");
CREATE INDEX "idx_modelinference_casemaster"   ON "ModelInference" ("CaseMasterID");
CREATE INDEX "idx_modelinference_at"           ON "ModelInference" ("InferenceAt");

CREATE INDEX "idx_entitygraph_accused"         ON "EntityGraph" ("AccusedMasterID");
CREATE INDEX "idx_entitygraph_type"            ON "EntityGraph" ("EntityType");

CREATE INDEX "idx_networkedge_source"          ON "NetworkEdge" ("Source");
CREATE INDEX "idx_networkedge_target"          ON "NetworkEdge" ("Target");
CREATE INDEX "idx_networkedge_type"            ON "NetworkEdge" ("RelationshipType");

CREATE INDEX "idx_gangmembership_gang"         ON "GangMembership" ("GangEntityID");
CREATE INDEX "idx_gangmembership_member"       ON "GangMembership" ("MemberEntityID");
CREATE INDEX "idx_gangmembership_accused"      ON "GangMembership" ("AccusedMasterID");

CREATE INDEX "idx_riskscore_casemaster"        ON "CrimeRiskScore" ("CaseMasterID");
CREATE INDEX "idx_riskscore_unit"              ON "CrimeRiskScore" ("UnitID");
CREATE INDEX "idx_riskscore_district"          ON "CrimeRiskScore" ("DistrictID");
CREATE INDEX "idx_riskscore_level"             ON "CrimeRiskScore" ("RiskLevel");

CREATE INDEX "idx_prediction_district"         ON "CrimePrediction" ("DistrictID");
CREATE INDEX "idx_prediction_unit"             ON "CrimePrediction" ("UnitID");
CREATE INDEX "idx_prediction_crimehead"        ON "CrimePrediction" ("CrimeHeadID");
CREATE INDEX "idx_prediction_window"           ON "CrimePrediction" ("PredictionStart", "PredictionEnd");

CREATE INDEX "idx_hotspot_district"            ON "CrimeHotspot" ("DistrictID");
CREATE INDEX "idx_hotspot_crimehead"           ON "CrimeHotspot" ("CrimeHeadID");

CREATE INDEX "idx_pattern_crimehead"           ON "CrimePattern" ("CrimeHeadID");
CREATE INDEX "idx_pattern_type"                ON "CrimePattern" ("PatternType");
CREATE INDEX "idx_patterncase_case"            ON "CrimePatternCase" ("CaseMasterID");

CREATE INDEX "idx_embedding_casemaster"        ON "CrimeEmbedding" ("CaseMasterID");
CREATE INDEX "idx_embedding_sourcetype"        ON "CrimeEmbedding" ("SourceType");

CREATE INDEX "idx_summary_casemaster"          ON "AISummary" ("CaseMasterID");

CREATE INDEX "idx_alert_casemaster"            ON "AlertHistory" ("CaseMasterID");
CREATE INDEX "idx_alert_district"              ON "AlertHistory" ("DistrictID");
CREATE INDEX "idx_alert_unit"                  ON "AlertHistory" ("UnitID");
CREATE INDEX "idx_alert_entity"                ON "AlertHistory" ("EntityID");
CREATE INDEX "idx_alert_status"                ON "AlertHistory" ("Status");
CREATE INDEX "idx_alert_severity"              ON "AlertHistory" ("Severity");

CREATE INDEX "idx_officerrec_case"             ON "OfficerRecommendation" ("CaseMasterID");
CREATE INDEX "idx_officerrec_employee"         ON "OfficerRecommendation" ("EmployeeID");

CREATE INDEX "idx_social_district"             ON "SocialIndicator" ("DistrictID");
CREATE INDEX "idx_weather_district"            ON "WeatherIndicator" ("DistrictID");
CREATE INDEX "idx_weather_observedat"          ON "WeatherIndicator" ("ObservedAt");
CREATE INDEX "idx_economic_district"           ON "EconomicIndicator" ("DistrictID");

-- ---- GIN indexes on JSONB ---------------------------------------------------
CREATE INDEX "gin_modelversion_hyperparams" ON "ModelVersion" USING GIN ("Hyperparameters");
CREATE INDEX "gin_modelversion_metrics"     ON "ModelVersion" USING GIN ("Metrics");
CREATE INDEX "gin_modelinference_input"     ON "ModelInference" USING GIN ("Input");
CREATE INDEX "gin_modelinference_output"    ON "ModelInference" USING GIN ("Output");
CREATE INDEX "gin_entitygraph_attrs"        ON "EntityGraph" USING GIN ("Attributes");
CREATE INDEX "gin_networkedge_props"        ON "NetworkEdge" USING GIN ("Properties");
CREATE INDEX "gin_riskscore_factors"        ON "CrimeRiskScore" USING GIN ("Factors");
CREATE INDEX "gin_prediction_features"      ON "CrimePrediction" USING GIN ("Features");
CREATE INDEX "gin_pattern_attrs"            ON "CrimePattern" USING GIN ("Attributes");
CREATE INDEX "gin_alert_payload"            ON "AlertHistory" USING GIN ("Payload");
CREATE INDEX "gin_officerrec_rationale"     ON "OfficerRecommendation" USING GIN ("Rationale");

-- ---- GIN indexes for Full Text Search (tsvector) ----------------------------
CREATE INDEX "gin_casemaster_brieffacts_fts" ON "CaseMaster" USING GIN ("BriefFactsFTS");
CREATE INDEX "gin_entitygraph_fts"           ON "EntityGraph" USING GIN ("SearchVector");
CREATE INDEX "gin_pattern_fts"               ON "CrimePattern" USING GIN ("SearchVector");
CREATE INDEX "gin_summary_fts"               ON "AISummary" USING GIN ("SearchVector");

-- ---- GIN trigram indexes for fuzzy text search ------------------------------
CREATE INDEX "gin_entitygraph_label_trgm" ON "EntityGraph" USING GIN ("Label" gin_trgm_ops);
CREATE INDEX "gin_pattern_name_trgm"      ON "CrimePattern" USING GIN ("Name" gin_trgm_ops);

-- ---- pgvector ANN indexes (HNSW, cosine distance) ---------------------------
CREATE INDEX "hnsw_crimeembedding_vec" ON "CrimeEmbedding" USING hnsw ("Embedding" vector_cosine_ops);
CREATE INDEX "hnsw_entitygraph_vec"    ON "EntityGraph"    USING hnsw ("Embedding" vector_cosine_ops);

-- ---- PostGIS spatial (GiST) indexes -----------------------------------------
CREATE INDEX "gist_entitygraph_geom"   ON "EntityGraph"     USING GIST ("geom");
CREATE INDEX "gist_riskscore_geom"     ON "CrimeRiskScore"  USING GIST ("geom");
CREATE INDEX "gist_prediction_geom"    ON "CrimePrediction" USING GIST ("geom");
CREATE INDEX "gist_hotspot_geom"       ON "CrimeHotspot"    USING GIST ("geom");
CREATE INDEX "gist_hotspot_centroid"   ON "CrimeHotspot"    USING GIST ("Centroid");
CREATE INDEX "gist_pattern_geom"       ON "CrimePattern"    USING GIST ("geom");
CREATE INDEX "gist_alert_geom"         ON "AlertHistory"    USING GIST ("geom");
CREATE INDEX "gist_social_geom"        ON "SocialIndicator" USING GIST ("geom");
CREATE INDEX "gist_weather_geom"       ON "WeatherIndicator" USING GIST ("geom");
CREATE INDEX "gist_economic_geom"      ON "EconomicIndicator" USING GIST ("geom");

-- =============================================================================
-- 11. ANALYTICS VIEWS & MATERIALIZED VIEWS
-- =============================================================================

-- Open/actionable alerts with resolved context.
CREATE OR REPLACE VIEW "vw_active_alerts" AS
SELECT
    a."AlertID",
    a."AlertType",
    a."Severity",
    a."Title",
    a."Message",
    a."Status",
    cm."CrimeNo",
    d."DistrictName",
    u."UnitName",
    a."geom",
    a."CreatedAt"
FROM "AlertHistory" a
LEFT JOIN "CaseMaster" cm ON cm."CaseMasterID" = a."CaseMasterID"
LEFT JOIN "District"   d  ON d."DistrictID"    = a."DistrictID"
LEFT JOIN "Unit"       u  ON u."UnitID"        = a."UnitID"
WHERE a."Status" IN ('open','acknowledged');

-- Latest risk level per district (most recent score per district).
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
ORDER BY r."DistrictID", r."ValidFrom" DESC
WITH NO DATA;

CREATE UNIQUE INDEX "idx_mv_district_risk_key" ON "mv_district_risk_profile" ("DistrictID");

-- Active hotspot summary by district + crime head.
CREATE MATERIALIZED VIEW "mv_active_hotspots" AS
SELECT
    h."HotspotID",
    h."DistrictID",
    d."DistrictName",
    h."CrimeHeadID",
    ch."CrimeGroupName",
    h."Intensity",
    h."CaseCount",
    h."Centroid",
    h."geom",
    h."PeriodStart",
    h."PeriodEnd"
FROM "CrimeHotspot" h
LEFT JOIN "District"  d  ON d."DistrictID"  = h."DistrictID"
LEFT JOIN "CrimeHead" ch ON ch."CrimeHeadID" = h."CrimeHeadID"
WHERE h."IsActive"
WITH NO DATA;

CREATE UNIQUE INDEX "idx_mv_active_hotspots_key" ON "mv_active_hotspots" ("HotspotID");

-- =============================================================================
-- 12. pgRouting helper (OPTIONAL — only created if pgrouting is installed)
--     Shortest path between two entities over the NetworkEdge graph.
-- =============================================================================
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pgrouting') THEN
        EXECUTE $fn$
            CREATE OR REPLACE FUNCTION fn_entity_shortest_path(
                p_source BIGINT,
                p_target BIGINT
            )
            RETURNS TABLE (seq INTEGER, node BIGINT, edge BIGINT, cost DOUBLE PRECISION, agg_cost DOUBLE PRECISION)
            LANGUAGE sql
            AS $body$
                SELECT r.seq, r.node, r.edge, r.cost, r.agg_cost
                FROM pgr_dijkstra(
                    'SELECT "EdgeID" AS id, "Source" AS source, "Target" AS target,
                            "Cost" AS cost, "ReverseCost" AS reverse_cost FROM "NetworkEdge"',
                    p_source, p_target, directed := false
                ) AS r;
            $body$;
        $fn$;
        RAISE NOTICE 'fn_entity_shortest_path created (pgRouting available).';
    ELSE
        RAISE NOTICE 'Skipped fn_entity_shortest_path (pgRouting not installed).';
    END IF;
END$$;

-- =============================================================================
-- 13. ROW LEVEL SECURITY — explicitly DISABLED on every new table
-- =============================================================================
ALTER TABLE "ModelVersion"          DISABLE ROW LEVEL SECURITY;
ALTER TABLE "ModelInference"        DISABLE ROW LEVEL SECURITY;
ALTER TABLE "EntityGraph"           DISABLE ROW LEVEL SECURITY;
ALTER TABLE "NetworkEdge"           DISABLE ROW LEVEL SECURITY;
ALTER TABLE "GangMembership"        DISABLE ROW LEVEL SECURITY;
ALTER TABLE "CrimeRiskScore"        DISABLE ROW LEVEL SECURITY;
ALTER TABLE "CrimePrediction"       DISABLE ROW LEVEL SECURITY;
ALTER TABLE "CrimeHotspot"          DISABLE ROW LEVEL SECURITY;
ALTER TABLE "CrimePattern"          DISABLE ROW LEVEL SECURITY;
ALTER TABLE "CrimePatternCase"      DISABLE ROW LEVEL SECURITY;
ALTER TABLE "CrimeEmbedding"        DISABLE ROW LEVEL SECURITY;
ALTER TABLE "AISummary"             DISABLE ROW LEVEL SECURITY;
ALTER TABLE "AlertHistory"          DISABLE ROW LEVEL SECURITY;
ALTER TABLE "OfficerRecommendation" DISABLE ROW LEVEL SECURITY;
ALTER TABLE "SocialIndicator"       DISABLE ROW LEVEL SECURITY;
ALTER TABLE "WeatherIndicator"      DISABLE ROW LEVEL SECURITY;
ALTER TABLE "EconomicIndicator"     DISABLE ROW LEVEL SECURITY;

COMMIT;

-- =============================================================================
-- USAGE EXAMPLES (reference — not executed)
-- =============================================================================
-- Semantic search (nearest cases to a query embedding):
--   SELECT "CaseMasterID", 1 - ("Embedding" <=> :query_vec) AS similarity
--   FROM "CrimeEmbedding"
--   ORDER BY "Embedding" <=> :query_vec
--   LIMIT 10;
--
-- Full text search over brief facts:
--   SELECT "CaseMasterID", "CrimeNo"
--   FROM "CaseMaster"
--   WHERE "BriefFactsFTS" @@ websearch_to_tsquery('english', 'armed robbery night market');
--
-- Fuzzy name search:
--   SELECT "EntityID", "Label", similarity("Label", 'ramesh') AS s
--   FROM "EntityGraph"
--   WHERE "Label" % 'ramesh'
--   ORDER BY s DESC;
--
-- Spatial: hotspots within 2km of a point:
--   SELECT * FROM "CrimeHotspot"
--   WHERE ST_DWithin("geom"::geography,
--                    ST_SetSRID(ST_MakePoint(:lon, :lat),4326)::geography, 2000);
--
-- Graph shortest path (requires pgRouting):
--   SELECT * FROM fn_entity_shortest_path(:source_entity, :target_entity);
-- =============================================================================
