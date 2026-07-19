-- =============================================================================
-- DRISHTI migration 023 — Disaster Response OPTIONAL AWS analytics mirror
--                          (PostGIS / pgRouting) + AlertHistory hazard reuse
-- Target: PostgreSQL 15+ / AWS RDS PostgreSQL (ap-south-1), PostGIS + pgRouting
-- Depends on: 005 (RLS helpers), police_fir_schema.sql (District/Unit/Employee),
--             police_fir_intelligence.sql (AlertHistory + alert_type_enum),
--             008 (ModelVersion), fn_set_updated_at()
-- =============================================================================
--
-- Prompt 17 (Disaster Response). The SUBMITTED application's authoritative
-- operational store for hazards/readings/forecasts/resources/routes is the
-- Catalyst Data Store (Data Store-native tables — see
-- services/ml/app/datastore/disaster_schema.py). This migration is the OPTIONAL,
-- RECONSTRUCTABLE AWS analytics/geospatial MIRROR used ONLY when a measured
-- spatial/routing workload needs PostGIS/pgRouting (impact overlay, hazard-
-- aware evacuation routing). It is keyed by the SAME stable ExternalIDs so it
-- can be rebuilt from Data Store at any time. It is never the browser CRUD path.
--
-- Safety / posture:
--   * Everything here is SYNTHETIC-DEMO data (IsSynthetic default TRUE).
--   * RLS + FORCE RLS stay DISABLED and NO RLS POLICY is created (Prompt 17 B.14).
--   * Additive + idempotent: CREATE ... IF NOT EXISTS / ADD COLUMN IF NOT EXISTS /
--     enum-value guards. Nothing is dropped; re-running is safe.
--   * GiST spatial indexes exist ONLY on this AWS mirror (Prompt 17 B.13).
--   * No forecast/alert is auto-published here; approval/lifecycle is enforced in
--     the API. Rows are analytics projections, not a warning/dispatch system.
-- =============================================================================

BEGIN;

-- =============================================================================
-- 0. Extensions (mirror only — no-op if already present; ignore if unavailable)
-- =============================================================================
DO $$
BEGIN
    BEGIN
        CREATE EXTENSION IF NOT EXISTS postgis;
    EXCEPTION WHEN OTHERS THEN
        RAISE NOTICE 'postgis not available; geometry columns will be skipped by the mirror loader';
    END;
    BEGIN
        CREATE EXTENSION IF NOT EXISTS pgrouting;
    EXCEPTION WHEN OTHERS THEN
        RAISE NOTICE 'pgrouting not available; routing runs via the protected AWS adapter only';
    END;
END$$;

-- =============================================================================
-- 1. Enum types (guarded — created only if missing)
-- =============================================================================
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname='hazard_severity_enum') THEN
        CREATE TYPE hazard_severity_enum AS ENUM ('minor','moderate','severe','extreme');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname='hazard_status_enum') THEN
        CREATE TYPE hazard_status_enum AS ENUM
            ('predicted','watch','warning','active','recovery','closed');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname='hydromet_metric_enum') THEN
        CREATE TYPE hydromet_metric_enum AS ENUM
            ('rainfall','river_level','reservoir_level','temperature','wind','humidity');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname='resource_type_enum') THEN
        CREATE TYPE resource_type_enum AS ENUM
            ('personnel','vehicle','boat','ambulance','relief_material','equipment','medical');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname='resource_status_enum') THEN
        CREATE TYPE resource_status_enum AS ENUM ('available','deployed','maintenance');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname='allocation_status_enum') THEN
        CREATE TYPE allocation_status_enum AS ENUM
            ('proposed','approved','dispatched','enroute','onsite','released','rejected');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname='risk_level_enum') THEN
        -- reuse the crime risk_level vocabulary if it does not already exist
        CREATE TYPE risk_level_enum AS ENUM ('low','medium','high','critical');
    END IF;
END$$;

-- Extend the EXISTING alert_type_enum with hazard values (idempotent).
-- Do NOT create a competing alert system — hazard alerts reuse AlertHistory.
DO $$
DECLARE
    v TEXT;
BEGIN
    FOREACH v IN ARRAY ARRAY[
        'flood_warning','urban_flood_warning','landslide_warning','drought_warning',
        'heatwave_warning','cyclone_warning','forest_fire_warning','dam_breach_warning',
        'lightning_warning'
    ] LOOP
        IF NOT EXISTS (
            SELECT 1 FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid
            WHERE t.typname='alert_type_enum' AND e.enumlabel = v
        ) THEN
            EXECUTE format('ALTER TYPE alert_type_enum ADD VALUE %L', v);
        END IF;
    END LOOP;
END$$;

-- Reuse AlertHistory: additive nullable HazardEventID (Prompt 17 B.11).
ALTER TABLE "AlertHistory"
    ADD COLUMN IF NOT EXISTS "HazardEventID" BIGINT;
COMMENT ON COLUMN "AlertHistory"."HazardEventID" IS
    'Nullable link to a HazardEvent (Prompt 17). Reuses AlertHistory; hazard alerts inherit the existing lifecycle/ack/pulse. No competing alert system.';

-- =============================================================================
-- 2. HazardType lookup
-- =============================================================================
CREATE TABLE IF NOT EXISTS "HazardType" (
    "HazardTypeID"   INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    "ExternalID"     VARCHAR NOT NULL UNIQUE,
    "Code"           VARCHAR NOT NULL UNIQUE,
    "Name"           VARCHAR NOT NULL,
    "Category"       VARCHAR,
    "DefaultLeadTimeHours" INTEGER CHECK ("DefaultLeadTimeHours" IS NULL OR "DefaultLeadTimeHours" >= 0),
    "Active"         BOOLEAN NOT NULL DEFAULT TRUE,
    "IsSynthetic"    BOOLEAN NOT NULL DEFAULT TRUE,
    "CreatedAt"      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT "chk_hazardtype_code" CHECK ("Code" IN
        ('flood','urban_flood','landslide','drought','heatwave','cyclone',
         'forest_fire','dam_breach','lightning'))
);
COMMENT ON TABLE "HazardType" IS
    'Hazard lookup (mirror of the Catalyst Data Store lookup). flood/urban_flood/landslide/drought/heatwave/cyclone/forest_fire/dam_breach/lightning.';

-- Idempotent lookup seed (mirror of the Data Store lookup rows).
INSERT INTO "HazardType" ("ExternalID","Code","Name","Category","DefaultLeadTimeHours") VALUES
    ('haztype:flood','flood','Riverine / basin flood','hydro',48),
    ('haztype:urban_flood','urban_flood','Urban flooding','hydro',12),
    ('haztype:landslide','landslide','Landslide / slope failure','geo',24),
    ('haztype:drought','drought','Drought / rainfall deficit','climate',720),
    ('haztype:heatwave','heatwave','Heatwave','climate',72),
    ('haztype:cyclone','cyclone','Cyclone / severe storm','met',96),
    ('haztype:forest_fire','forest_fire','Forest fire','fire',24),
    ('haztype:dam_breach','dam_breach','Dam / reservoir breach','hydro',6),
    ('haztype:lightning','lightning','Lightning / thunderstorm','met',3)
ON CONFLICT ("ExternalID") DO NOTHING;

-- =============================================================================
-- 3. HazardEvent (actual or forecast event; point or polygon extent)
-- =============================================================================
CREATE TABLE IF NOT EXISTS "HazardEvent" (
    "HazardEventID"  BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    "ExternalID"     VARCHAR NOT NULL UNIQUE,
    "HazardTypeID"   INTEGER REFERENCES "HazardType" ("HazardTypeID"),
    "HazardCode"     VARCHAR NOT NULL,
    "Status"         hazard_status_enum NOT NULL DEFAULT 'predicted',
    "Severity"       hazard_severity_enum NOT NULL DEFAULT 'moderate',
    "DistrictID"     INTEGER REFERENCES "District" ("DistrictID"),
    "UnitID"         INTEGER REFERENCES "Unit" ("UnitID"),
    "geom"           geometry(Geometry, 4326),
    "GeoJSON"        JSONB NOT NULL DEFAULT '{}'::jsonb,
    "CanonicalCRS"   VARCHAR NOT NULL DEFAULT 'EPSG:4326',
    "OnsetAt"        TIMESTAMPTZ,
    "PredictedPeakAt" TIMESTAMPTZ,
    "Source"         VARCHAR,
    "SourceVersion"  VARCHAR,
    "Description"    TEXT,
    "IsSynthetic"    BOOLEAN NOT NULL DEFAULT TRUE,
    "CreatedAt"      TIMESTAMPTZ NOT NULL DEFAULT now(),
    "UpdatedAt"      TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE "HazardEvent" IS
    'Actual or forecast hazard event mirror. Authoritative copy lives in Catalyst Data Store; this is a reconstructable analytics/geospatial projection.';
CREATE INDEX IF NOT EXISTS "idx_hazardevent_district" ON "HazardEvent" ("DistrictID");
CREATE INDEX IF NOT EXISTS "idx_hazardevent_status"   ON "HazardEvent" ("Status");
CREATE INDEX IF NOT EXISTS "idx_hazardevent_onset"    ON "HazardEvent" ("OnsetAt");
CREATE INDEX IF NOT EXISTS "gix_hazardevent_geom"     ON "HazardEvent" USING GIST ("geom");

-- Now that HazardEvent exists in the mirror, wire the additive AlertHistory FK.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname='fk_alerthistory_hazardevent'
    ) THEN
        ALTER TABLE "AlertHistory"
            ADD CONSTRAINT "fk_alerthistory_hazardevent"
            FOREIGN KEY ("HazardEventID") REFERENCES "HazardEvent" ("HazardEventID");
    END IF;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'AlertHistory.HazardEventID FK not added (mirror-only, non-fatal)';
END$$;
CREATE INDEX IF NOT EXISTS "idx_alerthistory_hazardevent" ON "AlertHistory" ("HazardEventID");

-- =============================================================================
-- 4. HazardPrediction (one row per model/rule run — auditable, cited)
-- =============================================================================
CREATE TABLE IF NOT EXISTS "HazardPrediction" (
    "HazardPredictionID" BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    "ExternalID"     VARCHAR NOT NULL UNIQUE,
    "HazardCode"     VARCHAR NOT NULL,
    "ModelVersionID" INTEGER REFERENCES "ModelVersion" ("ModelVersionID"),
    "ModelVersionLabel" VARCHAR,
    "FeatureSnapshotID" VARCHAR,
    "DistrictID"     INTEGER REFERENCES "District" ("DistrictID"),
    "UnitID"         INTEGER REFERENCES "Unit" ("UnitID"),
    "geom"           geometry(Geometry, 4326),
    "GeoJSON"        JSONB NOT NULL DEFAULT '{}'::jsonb,
    "ForecastStart"  TIMESTAMPTZ,
    "ForecastEnd"    TIMESTAMPTZ,
    "DataAsOf"       TIMESTAMPTZ,
    "Probability"    NUMERIC(6,5) CHECK ("Probability" IS NULL OR "Probability" BETWEEN 0 AND 1),
    "PredictedSeverity" hazard_severity_enum,
    "ExpectedImpact" JSONB NOT NULL DEFAULT '{}'::jsonb,
    "Confidence"     NUMERIC(6,5) CHECK ("Confidence" IS NULL OR "Confidence" BETWEEN 0 AND 1),
    "Factors"        JSONB NOT NULL DEFAULT '{}'::jsonb,
    "QualityState"   VARCHAR NOT NULL DEFAULT 'ok',   -- ok|low_confidence|stale|superseded|rejected
    "SupersededByID" BIGINT,
    "IsSynthetic"    BOOLEAN NOT NULL DEFAULT TRUE,
    "CreatedAt"      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT "chk_hazardpred_quality" CHECK ("QualityState" IN
        ('ok','low_confidence','stale','superseded','rejected'))
);
COMMENT ON TABLE "HazardPrediction" IS
    'Immutable forecast row: model/rule version, feature snapshot ref, window, probability, calibrated confidence, factors, quality state. A newer reading supersedes (never rewrites).';
CREATE INDEX IF NOT EXISTS "idx_hazardpred_district" ON "HazardPrediction" ("DistrictID");
CREATE INDEX IF NOT EXISTS "idx_hazardpred_window"   ON "HazardPrediction" ("ForecastStart","ForecastEnd");
CREATE INDEX IF NOT EXISTS "gix_hazardpred_geom"     ON "HazardPrediction" USING GIST ("geom");

-- =============================================================================
-- 5. HazardRiskZone (static susceptibility + dynamic zones)
-- =============================================================================
CREATE TABLE IF NOT EXISTS "HazardRiskZone" (
    "HazardRiskZoneID" BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    "ExternalID"     VARCHAR NOT NULL UNIQUE,
    "HazardCode"     VARCHAR NOT NULL,
    "ZoneKind"       VARCHAR NOT NULL DEFAULT 'dynamic',  -- static|dynamic
    "DistrictID"     INTEGER REFERENCES "District" ("DistrictID"),
    "geom"           geometry(Polygon, 4326),
    "Centroid"       geometry(Point, 4326),
    "GeoJSON"        JSONB NOT NULL DEFAULT '{}'::jsonb,
    "RiskLevel"      risk_level_enum NOT NULL DEFAULT 'medium',
    "Score"          NUMERIC(6,5) CHECK ("Score" IS NULL OR "Score" BETWEEN 0 AND 1),
    "Factors"        JSONB NOT NULL DEFAULT '{}'::jsonb,
    "ValidFrom"      TIMESTAMPTZ,
    "ValidTo"        TIMESTAMPTZ,
    "Source"         VARCHAR,
    "SourceVersion"  VARCHAR,
    "IsActive"       BOOLEAN NOT NULL DEFAULT TRUE,
    "IsSynthetic"    BOOLEAN NOT NULL DEFAULT TRUE,
    "CreatedAt"      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT "chk_riskzone_kind" CHECK ("ZoneKind" IN ('static','dynamic'))
);
COMMENT ON TABLE "HazardRiskZone" IS
    'Static susceptibility belts (Ghats landslide, flood plains) + dynamic risk polygons with per-zone score/factors and validity period.';
CREATE INDEX IF NOT EXISTS "idx_riskzone_district" ON "HazardRiskZone" ("DistrictID");
CREATE INDEX IF NOT EXISTS "gix_riskzone_geom"     ON "HazardRiskZone" USING GIST ("geom");

-- =============================================================================
-- 6. HydroMetReading (time-series feed; complements WeatherIndicator)
-- =============================================================================
CREATE TABLE IF NOT EXISTS "HydroMetReading" (
    "HydroMetReadingID" BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    "ExternalID"     VARCHAR NOT NULL UNIQUE,       -- idempotent source key
    "StationCode"    VARCHAR NOT NULL,
    "SourceAgency"   VARCHAR,
    "MetricType"     hydromet_metric_enum NOT NULL,
    "Value"          DOUBLE PRECISION,
    "Unit"           VARCHAR,
    "geom"           geometry(Point, 4326),
    "DistrictID"     INTEGER REFERENCES "District" ("DistrictID"),
    "ObservedAt"     TIMESTAMPTZ NOT NULL,
    "ReceivedAt"     TIMESTAMPTZ NOT NULL DEFAULT now(),
    "QualityFlag"    VARCHAR NOT NULL DEFAULT 'valid',  -- valid|suspect|missing|superseded|late
    "SourceRecordID" VARCHAR,
    "IngestionRunID" VARCHAR,
    "IsSynthetic"    BOOLEAN NOT NULL DEFAULT TRUE,
    "CreatedAt"      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT "chk_hydromet_quality" CHECK ("QualityFlag" IN
        ('valid','suspect','missing','superseded','late'))
);
COMMENT ON TABLE "HydroMetReading" IS
    'Normalized hydro-met time series (rainfall/river_level/reservoir_level/temperature/wind/humidity). Observed-at vs received-at; quality flag; idempotent ExternalID.';
CREATE INDEX IF NOT EXISTS "idx_hydromet_station" ON "HydroMetReading" ("StationCode","ObservedAt");
CREATE INDEX IF NOT EXISTS "idx_hydromet_metric"  ON "HydroMetReading" ("MetricType","ObservedAt");
CREATE INDEX IF NOT EXISTS "idx_hydromet_district" ON "HydroMetReading" ("DistrictID");
CREATE INDEX IF NOT EXISTS "gix_hydromet_geom"    ON "HydroMetReading" USING GIST ("geom");

-- =============================================================================
-- 7. Resource (ties deployable resources to the org graph)
-- =============================================================================
CREATE TABLE IF NOT EXISTS "Resource" (
    "ResourceID"     BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    "ExternalID"     VARCHAR NOT NULL UNIQUE,
    "ResourceType"   resource_type_enum NOT NULL,
    "Name"           VARCHAR NOT NULL,
    "Quantity"       INTEGER NOT NULL DEFAULT 1 CHECK ("Quantity" >= 0),
    "Unit"           VARCHAR,
    "HomeUnitID"     INTEGER REFERENCES "Unit" ("UnitID"),
    "EmployeeID"     INTEGER REFERENCES "Employee" ("EmployeeID"),
    "geom"           geometry(Point, 4326),
    "Capacity"       INTEGER CHECK ("Capacity" IS NULL OR "Capacity" >= 0),
    "Capabilities"   JSONB NOT NULL DEFAULT '[]'::jsonb,
    "Status"         resource_status_enum NOT NULL DEFAULT 'available',
    "IsSynthetic"    BOOLEAN NOT NULL DEFAULT TRUE,
    "LastUpdatedAt"  TIMESTAMPTZ NOT NULL DEFAULT now(),
    "CreatedAt"      TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE "Resource" IS
    'Deployable resources (personnel/vehicle/boat/ambulance/relief_material/equipment/medical). Personnel link to the existing synthetic Employee/Unit contract.';
CREATE INDEX IF NOT EXISTS "idx_resource_home" ON "Resource" ("HomeUnitID");
CREATE INDEX IF NOT EXISTS "idx_resource_status" ON "Resource" ("Status");
CREATE INDEX IF NOT EXISTS "gix_resource_geom" ON "Resource" USING GIST ("geom");

-- =============================================================================
-- 8. ReliefShelter (evacuation destinations)
-- =============================================================================
CREATE TABLE IF NOT EXISTS "ReliefShelter" (
    "ReliefShelterID" BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    "ExternalID"     VARCHAR NOT NULL UNIQUE,
    "Name"           VARCHAR NOT NULL,
    "geom"           geometry(Point, 4326),
    "DistrictID"     INTEGER REFERENCES "District" ("DistrictID"),
    "Capacity"       INTEGER NOT NULL DEFAULT 0 CHECK ("Capacity" >= 0),
    "CurrentOccupancy" INTEGER NOT NULL DEFAULT 0 CHECK ("CurrentOccupancy" >= 0),
    "Facilities"     JSONB NOT NULL DEFAULT '[]'::jsonb,
    "Status"         VARCHAR NOT NULL DEFAULT 'open',   -- open|full|closed
    "IsSynthetic"    BOOLEAN NOT NULL DEFAULT TRUE,
    "CreatedAt"      TIMESTAMPTZ NOT NULL DEFAULT now(),
    "UpdatedAt"      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT "chk_shelter_status" CHECK ("Status" IN ('open','full','closed'))
);
COMMENT ON TABLE "ReliefShelter" IS 'Relief shelters with capacity/occupancy/facilities/status.';
CREATE INDEX IF NOT EXISTS "idx_shelter_district" ON "ReliefShelter" ("DistrictID");
CREATE INDEX IF NOT EXISTS "gix_shelter_geom" ON "ReliefShelter" USING GIST ("geom");

-- =============================================================================
-- 9. ResourceAllocation (proposal + human approval + live tracking)
-- =============================================================================
CREATE TABLE IF NOT EXISTS "ResourceAllocation" (
    "ResourceAllocationID" BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    "ExternalID"     VARCHAR NOT NULL UNIQUE,
    "HazardEventID"  BIGINT REFERENCES "HazardEvent" ("HazardEventID"),
    "ResourceID"     BIGINT REFERENCES "Resource" ("ResourceID"),
    "TargetZoneID"   BIGINT REFERENCES "HazardRiskZone" ("HazardRiskZoneID"),
    "QuantityAllocated" INTEGER NOT NULL DEFAULT 1 CHECK ("QuantityAllocated" >= 0),
    "Status"         allocation_status_enum NOT NULL DEFAULT 'proposed',
    "Score"          NUMERIC(8,5),
    "Reason"         JSONB NOT NULL DEFAULT '{}'::jsonb,
    "ProposedByActor" VARCHAR,
    "ApprovedByActor" VARCHAR,
    "ApprovedByEmployeeID" INTEGER REFERENCES "Employee" ("EmployeeID"),
    "DistrictID"     INTEGER REFERENCES "District" ("DistrictID"),
    "ProposedAt"     TIMESTAMPTZ,
    "ApprovedAt"     TIMESTAMPTZ,
    "DispatchedAt"   TIMESTAMPTZ,
    "EnrouteAt"      TIMESTAMPTZ,
    "OnsiteAt"       TIMESTAMPTZ,
    "ReleasedAt"     TIMESTAMPTZ,
    "IsSynthetic"    BOOLEAN NOT NULL DEFAULT TRUE,
    "CreatedAt"      TIMESTAMPTZ NOT NULL DEFAULT now(),
    "UpdatedAt"      TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE "ResourceAllocation" IS
    'Allocation lifecycle proposed->approved->dispatched->enroute->onsite->released (or rejected). A human must approve before dispatch (never auto-dispatch).';
CREATE INDEX IF NOT EXISTS "idx_alloc_event"    ON "ResourceAllocation" ("HazardEventID");
CREATE INDEX IF NOT EXISTS "idx_alloc_resource" ON "ResourceAllocation" ("ResourceID");
CREATE INDEX IF NOT EXISTS "idx_alloc_status"   ON "ResourceAllocation" ("Status");

-- =============================================================================
-- 10. EvacuationRoute (pgRouting output; hazard-excluded LineString)
-- =============================================================================
CREATE TABLE IF NOT EXISTS "EvacuationRoute" (
    "EvacuationRouteID" BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    "ExternalID"     VARCHAR NOT NULL UNIQUE,
    "HazardEventID"  BIGINT REFERENCES "HazardEvent" ("HazardEventID"),
    "FromZoneID"     BIGINT REFERENCES "HazardRiskZone" ("HazardRiskZoneID"),
    "ToShelterID"    BIGINT REFERENCES "ReliefShelter" ("ReliefShelterID"),
    "geom"           geometry(LineString, 4326),
    "GeoJSON"        JSONB NOT NULL DEFAULT '{}'::jsonb,
    "DistanceKm"     DOUBLE PRECISION,
    "EstMinutes"     DOUBLE PRECISION,
    "RoadGraphVersion" VARCHAR,
    "HazardExclusionVersion" VARCHAR,
    "Status"         VARCHAR NOT NULL DEFAULT 'proposed',  -- proposed|selected|no_route
    "Notes"          TEXT,
    "IsSynthetic"    BOOLEAN NOT NULL DEFAULT TRUE,
    "CreatedAt"      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT "chk_evacroute_status" CHECK ("Status" IN ('proposed','selected','no_route'))
);
COMMENT ON TABLE "EvacuationRoute" IS
    'Evacuation route from a risk zone to a shelter, routed AROUND the active hazard/block geometry. Never described as guaranteed safe; no_route surfaced explicitly.';
CREATE INDEX IF NOT EXISTS "idx_evacroute_event" ON "EvacuationRoute" ("HazardEventID");
CREATE INDEX IF NOT EXISTS "gix_evacroute_geom"  ON "EvacuationRoute" USING GIST ("geom");

-- =============================================================================
-- 11. ResponsePlan / ResponseTask (per-hazard SOP checklists)
-- =============================================================================
CREATE TABLE IF NOT EXISTS "ResponsePlan" (
    "ResponsePlanID" BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    "ExternalID"     VARCHAR NOT NULL UNIQUE,
    "HazardEventID"  BIGINT REFERENCES "HazardEvent" ("HazardEventID"),
    "HazardCode"     VARCHAR NOT NULL,
    "Title"          VARCHAR NOT NULL,
    "TemplateCode"   VARCHAR,
    "Status"         VARCHAR NOT NULL DEFAULT 'active',   -- active|complete|archived
    "DistrictID"     INTEGER REFERENCES "District" ("DistrictID"),
    "IsSynthetic"    BOOLEAN NOT NULL DEFAULT TRUE,
    "CreatedAt"      TIMESTAMPTZ NOT NULL DEFAULT now(),
    "UpdatedAt"      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT "chk_responseplan_status" CHECK ("Status" IN ('active','complete','archived'))
);
COMMENT ON TABLE "ResponsePlan" IS 'Per-hazard SOP plan header (checklist template applied to an event).';

CREATE TABLE IF NOT EXISTS "ResponseTask" (
    "ResponseTaskID" BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    "ExternalID"     VARCHAR NOT NULL UNIQUE,
    "ResponsePlanID" BIGINT REFERENCES "ResponsePlan" ("ResponsePlanID"),
    "Title"          VARCHAR NOT NULL,
    "Sequence"       INTEGER NOT NULL DEFAULT 1,
    "AssignedToActor" VARCHAR,
    "AssignedToEmployeeID" INTEGER REFERENCES "Employee" ("EmployeeID"),
    "Status"         VARCHAR NOT NULL DEFAULT 'open',   -- open|in_progress|done|overdue
    "DueAt"          TIMESTAMPTZ,
    "CompletedAt"    TIMESTAMPTZ,
    "IsSynthetic"    BOOLEAN NOT NULL DEFAULT TRUE,
    "CreatedAt"      TIMESTAMPTZ NOT NULL DEFAULT now(),
    "UpdatedAt"      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT "chk_responsetask_status" CHECK ("Status" IN ('open','in_progress','done','overdue'))
);
COMMENT ON TABLE "ResponseTask" IS 'SOP checklist task with assignment, due time and lifecycle.';
CREATE INDEX IF NOT EXISTS "idx_responsetask_plan" ON "ResponseTask" ("ResponsePlanID");

-- =============================================================================
-- 12. FeedSource / FeedIngestionRun (hazard feed heartbeat + freshness)
-- =============================================================================
CREATE TABLE IF NOT EXISTS "FeedSource" (
    "FeedSourceID"   INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    "ExternalID"     VARCHAR NOT NULL UNIQUE,
    "Code"           VARCHAR NOT NULL UNIQUE,
    "Name"           VARCHAR NOT NULL,
    "Provider"       VARCHAR,
    "ConnectorKind"  VARCHAR NOT NULL,   -- synthetic_replay|recorded_sample|live
    "Licence"        VARCHAR,
    "Attribution"    VARCHAR,
    "FreshnessSlaMinutes" INTEGER,
    "ExternalAccessRequired" BOOLEAN NOT NULL DEFAULT FALSE,
    "IsSynthetic"    BOOLEAN NOT NULL DEFAULT TRUE,
    "CreatedAt"      TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE "FeedSource" IS
    'Hazard feed connector registry (synthetic_replay/recorded_sample/live) with licence/attribution and freshness SLA. ExternalAccessRequired flags a blocked live source.';

CREATE TABLE IF NOT EXISTS "FeedIngestionRun" (
    "FeedIngestionRunID" BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    "ExternalID"     VARCHAR NOT NULL UNIQUE,
    "FeedSourceID"   INTEGER REFERENCES "FeedSource" ("FeedSourceID"),
    "FeedCode"       VARCHAR NOT NULL,
    "StartedAt"      TIMESTAMPTZ NOT NULL DEFAULT now(),
    "FinishedAt"     TIMESTAMPTZ,
    "Status"         VARCHAR NOT NULL DEFAULT 'ok',   -- ok|partial|failed|stale
    "AcceptedCount"  INTEGER NOT NULL DEFAULT 0,
    "DuplicateCount" INTEGER NOT NULL DEFAULT 0,
    "RejectedCount"  INTEGER NOT NULL DEFAULT 0,
    "LastObservedAt" TIMESTAMPTZ,
    "Detail"         JSONB NOT NULL DEFAULT '{}'::jsonb,
    "IsSynthetic"    BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT "chk_feedrun_status" CHECK ("Status" IN ('ok','partial','failed','stale'))
);
COMMENT ON TABLE "FeedIngestionRun" IS
    'Per-run feed heartbeat: accepted/duplicate/rejected counts, last observed-at, status (incl. stale). Surfaced to the UI freshness banner.';
CREATE INDEX IF NOT EXISTS "idx_feedrun_source" ON "FeedIngestionRun" ("FeedSourceID","StartedAt");

-- =============================================================================
-- 13. Road graph for pgRouting (separate GEOGRAPHIC topology — NEVER the
--     entity-intelligence NetworkEdge graph). Loaded from an approved OSM
--     extract (record extract date + licence attribution).
-- =============================================================================
CREATE TABLE IF NOT EXISTS "DisasterRoadNode" (
    "DisasterRoadNodeID" BIGINT PRIMARY KEY,     -- id from the OSM/pgr topology
    "ExternalID"     VARCHAR NOT NULL UNIQUE,
    "GraphVersion"   VARCHAR NOT NULL,
    "geom"           geometry(Point, 4326),
    "DistrictID"     INTEGER REFERENCES "District" ("DistrictID"),
    "IsSynthetic"    BOOLEAN NOT NULL DEFAULT TRUE
);
COMMENT ON TABLE "DisasterRoadNode" IS
    'Geographic road-graph vertices for pgRouting evacuation routing (osm2pgrouting-derived). Separate from the entity-intelligence graph.';
CREATE INDEX IF NOT EXISTS "gix_roadnode_geom" ON "DisasterRoadNode" USING GIST ("geom");

CREATE TABLE IF NOT EXISTS "DisasterRoadEdge" (
    "DisasterRoadEdgeID" BIGINT PRIMARY KEY,
    "ExternalID"     VARCHAR NOT NULL UNIQUE,
    "GraphVersion"   VARCHAR NOT NULL,
    "Source"         BIGINT NOT NULL,
    "Target"         BIGINT NOT NULL,
    "Cost"           DOUBLE PRECISION NOT NULL,   -- minutes (or km); >=0
    "ReverseCost"    DOUBLE PRECISION,
    "LengthKm"       DOUBLE PRECISION,
    "RoadClass"      VARCHAR,
    "geom"           geometry(LineString, 4326),
    "OsmExtractDate" DATE,
    "Licence"        VARCHAR DEFAULT 'ODbL (OpenStreetMap contributors)',
    "IsSynthetic"    BOOLEAN NOT NULL DEFAULT TRUE
);
COMMENT ON TABLE "DisasterRoadEdge" IS
    'Geographic road-graph edges (pgr_dijkstra-compatible source/target/cost/reverse_cost). Records OSM extract date + ODbL attribution. Edges intersecting active hazard geometry are excluded at query time.';
CREATE INDEX IF NOT EXISTS "idx_roadedge_source" ON "DisasterRoadEdge" ("Source");
CREATE INDEX IF NOT EXISTS "idx_roadedge_target" ON "DisasterRoadEdge" ("Target");
CREATE INDEX IF NOT EXISTS "gix_roadedge_geom"   ON "DisasterRoadEdge" USING GIST ("geom");

-- =============================================================================
-- 14. updated_at triggers (reuse fn_set_updated_at from base schema)
-- =============================================================================
DO $$
DECLARE
    t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'HazardEvent','ReliefShelter','ResourceAllocation','ResponsePlan','ResponseTask'
    ] LOOP
        IF EXISTS (SELECT 1 FROM pg_proc WHERE proname='fn_set_updated_at') THEN
            EXECUTE format(
                'DROP TRIGGER IF EXISTS %I ON %I; '
                'CREATE TRIGGER %I BEFORE UPDATE ON %I '
                'FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();',
                'trg_updated_'||lower(t), t, 'trg_updated_'||lower(t), t);
        END IF;
    END LOOP;
END$$;

-- =============================================================================
-- 15. Read-only grants (retained analytics reader) + RLS-disabled verification
-- =============================================================================
DO $$
DECLARE
    t TEXT;
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='drishti_readonly') THEN
        FOREACH t IN ARRAY ARRAY[
            'HazardType','HazardEvent','HazardPrediction','HazardRiskZone',
            'HydroMetReading','Resource','ReliefShelter','ResourceAllocation',
            'EvacuationRoute','ResponsePlan','ResponseTask','FeedSource',
            'FeedIngestionRun','DisasterRoadNode','DisasterRoadEdge'
        ] LOOP
            EXECUTE format('GRANT SELECT ON %I TO drishti_readonly;', t);
        END LOOP;
    END IF;
END$$;

-- RLS + FORCE RLS stay DISABLED across every application table (hackathon).
-- No RLS policy is created for the mirror (Prompt 17 B.14). The access boundary
-- is the Catalyst-authenticated API + server-side disaster-role middleware.
SELECT fn_disable_rls_all_app();
SELECT fn_assert_rls_disabled();

COMMIT;
