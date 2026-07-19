"""Disaster Response Data Store schema (Prompt 17 §B).

Single source of truth for the Data Store-native disaster tables' columns,
types, indexes, search columns and append-only flags. Dependency-free (stdlib
only) so it can be imported by the AppSail service AND loaded by path from the
``infra/catalyst/ds-schema`` provisioning generator (same pattern as
``board_schema.py`` / ``mapping.py``).

These tables are created DIRECTLY in Catalyst Data Store and populated by the
disaster service at runtime. Catalyst Data Store is the AUTHORITATIVE operational
store for the submitted app. The OPTIONAL AWS PostGIS/pgRouting analytics MIRROR
(``services/ml/sql/023_disaster_response.sql``) is reconstructable and keyed by
the SAME ExternalIDs; it is never the browser CRUD path and carries no RLS policy.

Every hazard/reading/forecast/resource/route record carries a stable
``ExternalID`` (``<prefix>:<pk>``) so writes are idempotent and cross-table
references survive.

Column ``type`` vocabulary -> Catalyst Data Store column type:
    "int"       -> bigint (identity PK / numeric FK / counter)
    "text"      -> varchar (<= 255; searchable/indexable label/enum/code/actor)
    "bigtext"   -> text    (descriptions, notes)
    "bool"      -> boolean
    "numeric"   -> double  (lon/lat, value, probability, score, distance)
    "json"      -> text    (validated GeoJSON / factors / reason — size-limited)
    "timestamp" -> datetime (ISO-8601, UTC)
"""
from __future__ import annotations

from dataclasses import dataclass

SCHEMA_VERSION = "2026.07.19-1"

# Hard size limits validated at the API boundary before any JSON/GeoJSON stored.
MAX_JSON_BYTES = 16_384          # per Factors / Reason / ExpectedImpact field
MAX_GEOJSON_BYTES = 65_536       # per validated GeoJSON geometry field
MAX_LABEL_LEN = 255
MAX_NOTES_LEN = 4_000

# Canonical hazard codes (mirror of the HazardType lookup).
HAZARD_CODES = (
    "flood", "urban_flood", "landslide", "drought", "heatwave", "cyclone",
    "forest_fire", "dam_breach", "lightning",
)
HAZARD_STATUSES = ("predicted", "watch", "warning", "active", "recovery", "closed")
HAZARD_SEVERITIES = ("minor", "moderate", "severe", "extreme")
HYDROMET_METRICS = (
    "rainfall", "river_level", "reservoir_level", "temperature", "wind", "humidity",
)
RESOURCE_TYPES = (
    "personnel", "vehicle", "boat", "ambulance", "relief_material", "equipment", "medical",
)
RESOURCE_STATUSES = ("available", "deployed", "maintenance")
ALLOCATION_STATUSES = (
    "proposed", "approved", "dispatched", "enroute", "onsite", "released", "rejected",
)
RISK_LEVELS = ("low", "medium", "high", "critical")
QUALITY_STATES = ("ok", "low_confidence", "stale", "superseded", "rejected")
READING_QUALITY = ("valid", "suspect", "missing", "superseded", "late")


@dataclass(frozen=True)
class Column:
    name: str
    type: str
    nullable: bool = True
    note: str = ""


@dataclass(frozen=True)
class Index:
    name: str
    columns: tuple[str, ...]
    unique: bool = False


@dataclass(frozen=True)
class DisasterTable:
    name: str                       # Data Store table name (== mapping.datastore_table)
    external_id_prefix: str         # ExternalID = "<prefix>:<pk>"
    pk: str
    columns: tuple[Column, ...]
    indexes: tuple[Index, ...] = ()
    search_columns: tuple[str, ...] = ()
    append_only: bool = False       # readings/predictions/activity: block UPDATE/DELETE

    def column_names(self) -> list[str]:
        return [c.name for c in self.columns]


def _c(name, type, nullable=True, note=""):
    return Column(name=name, type=type, nullable=nullable, note=note)


DISASTER_TABLES: tuple[DisasterTable, ...] = (
    DisasterTable(
        name="HazardType", external_id_prefix="haztype", pk="HazardTypeID",
        columns=(
            _c("HazardTypeID", "int", nullable=False),
            _c("Code", "text", nullable=False, note="one of HAZARD_CODES"),
            _c("Name", "text", nullable=False),
            _c("Category", "text"),
            _c("DefaultLeadTimeHours", "int"),
            _c("Active", "bool", nullable=False),
            _c("CreatedAt", "timestamp", nullable=False),
        ),
        indexes=(Index("ix_haztype_code", ("Code",), unique=True),),
        search_columns=("Name", "Code"),
    ),
    DisasterTable(
        name="HazardEvent", external_id_prefix="hazevt", pk="HazardEventID",
        columns=(
            _c("HazardEventID", "int", nullable=False),
            _c("HazardCode", "text", nullable=False),
            _c("Status", "text", nullable=False, note="predicted|watch|warning|active|recovery|closed"),
            _c("Severity", "text", nullable=False, note="minor|moderate|severe|extreme"),
            _c("DistrictID", "int"),
            _c("UnitID", "int"),
            _c("GeoJSON", "json", note="validated point or polygon extent (EPSG:4326)"),
            _c("CanonicalCRS", "text"),
            _c("CentroidLon", "numeric"),
            _c("CentroidLat", "numeric"),
            _c("OnsetAt", "timestamp"),
            _c("PredictedPeakAt", "timestamp"),
            _c("Source", "text"),
            _c("SourceVersion", "text"),
            _c("Description", "bigtext"),
            _c("Version", "int", nullable=False, note="optimistic concurrency counter"),
            _c("CreatedAt", "timestamp", nullable=False),
            _c("UpdatedAt", "timestamp", nullable=False),
            _c("DeletedAt", "timestamp", note="soft-delete (no hard delete in DS)"),
        ),
        indexes=(
            Index("ix_hazevt_district", ("DistrictID",)),
            Index("ix_hazevt_status", ("Status",)),
            Index("ix_hazevt_code", ("HazardCode",)),
            Index("ix_hazevt_onset", ("OnsetAt",)),
        ),
        search_columns=("Description",),
    ),
    DisasterTable(
        name="HazardPrediction", external_id_prefix="hazpred", pk="HazardPredictionID",
        append_only=True,
        columns=(
            _c("HazardPredictionID", "int", nullable=False),
            _c("HazardCode", "text", nullable=False),
            _c("HazardEventID", "int"),
            _c("ModelVersionLabel", "text", note="ModelName@Version or rule@version"),
            _c("FeatureSnapshotID", "text", note="immutable input snapshot id"),
            _c("DistrictID", "int"),
            _c("UnitID", "int"),
            _c("GeoJSON", "json"),
            _c("ForecastStart", "timestamp"),
            _c("ForecastEnd", "timestamp"),
            _c("HorizonHours", "int"),
            _c("DataAsOf", "timestamp", note="observation cutoff"),
            _c("Probability", "numeric"),
            _c("PredictedSeverity", "text"),
            _c("ExpectedImpact", "json"),
            _c("Confidence", "numeric", note="calibrated confidence in [0,1]"),
            _c("Factors", "json", note="visible explanation / factor list"),
            _c("BaselineComparison", "json", note="baseline vs model skill"),
            _c("QualityState", "text", nullable=False, note="ok|low_confidence|stale|superseded|rejected"),
            _c("SupersededByID", "int"),
            _c("CreatedBy", "text"),
            _c("CreatedAt", "timestamp", nullable=False),
        ),
        indexes=(
            Index("ix_hazpred_district", ("DistrictID",)),
            Index("ix_hazpred_code", ("HazardCode",)),
            Index("ix_hazpred_window", ("ForecastStart", "ForecastEnd")),
            Index("ix_hazpred_quality", ("QualityState",)),
        ),
    ),
    DisasterTable(
        name="HazardRiskZone", external_id_prefix="riskzone", pk="HazardRiskZoneID",
        columns=(
            _c("HazardRiskZoneID", "int", nullable=False),
            _c("HazardCode", "text", nullable=False),
            _c("ZoneKind", "text", nullable=False, note="static|dynamic"),
            _c("Name", "text"),
            _c("DistrictID", "int"),
            _c("GeoJSON", "json", note="polygon (EPSG:4326)"),
            _c("CentroidLon", "numeric"),
            _c("CentroidLat", "numeric"),
            _c("RiskLevel", "text", nullable=False, note="low|medium|high|critical"),
            _c("Score", "numeric"),
            _c("Factors", "json"),
            _c("ValidFrom", "timestamp"),
            _c("ValidTo", "timestamp"),
            _c("Source", "text"),
            _c("SourceVersion", "text"),
            _c("IsActive", "bool", nullable=False),
            _c("CreatedAt", "timestamp", nullable=False),
            _c("UpdatedAt", "timestamp", nullable=False),
            _c("DeletedAt", "timestamp"),
        ),
        indexes=(
            Index("ix_riskzone_district", ("DistrictID",)),
            Index("ix_riskzone_code", ("HazardCode",)),
            Index("ix_riskzone_active", ("IsActive",)),
        ),
        search_columns=("Name",),
    ),
    DisasterTable(
        name="HydroMetReading", external_id_prefix="hydromet", pk="HydroMetReadingID",
        append_only=True,
        columns=(
            _c("HydroMetReadingID", "int", nullable=False),
            _c("StationCode", "text", nullable=False),
            _c("SourceAgency", "text"),
            _c("MetricType", "text", nullable=False, note="one of HYDROMET_METRICS"),
            _c("Value", "numeric"),
            _c("Unit", "text"),
            _c("Lon", "numeric"),
            _c("Lat", "numeric"),
            _c("DistrictID", "int"),
            _c("ObservedAt", "timestamp", nullable=False),
            _c("ReceivedAt", "timestamp", nullable=False),
            _c("QualityFlag", "text", nullable=False, note="valid|suspect|missing|superseded|late"),
            _c("SourceRecordID", "text"),
            _c("IngestionRunID", "text"),
            _c("FeedCode", "text"),
            _c("SupersededByID", "int"),
            _c("CreatedAt", "timestamp", nullable=False),
        ),
        indexes=(
            Index("ix_hydromet_station", ("StationCode", "ObservedAt")),
            Index("ix_hydromet_metric", ("MetricType", "ObservedAt")),
            Index("ix_hydromet_district", ("DistrictID",)),
        ),
    ),
    DisasterTable(
        name="Resource", external_id_prefix="resource", pk="ResourceID",
        columns=(
            _c("ResourceID", "int", nullable=False),
            _c("ResourceType", "text", nullable=False, note="one of RESOURCE_TYPES"),
            _c("Name", "text", nullable=False),
            _c("Quantity", "int", nullable=False),
            _c("Unit", "text"),
            _c("HomeUnitID", "int", note="FK->Unit (synthetic)"),
            _c("EmployeeID", "int", note="FK->Employee for deployable personnel"),
            _c("Lon", "numeric"),
            _c("Lat", "numeric"),
            _c("Capacity", "int"),
            _c("Capabilities", "json"),
            _c("Status", "text", nullable=False, note="available|deployed|maintenance"),
            _c("DistrictID", "int"),
            _c("Version", "int", nullable=False),
            _c("LastUpdatedAt", "timestamp", nullable=False),
            _c("CreatedAt", "timestamp", nullable=False),
            _c("DeletedAt", "timestamp"),
        ),
        indexes=(
            Index("ix_resource_home", ("HomeUnitID",)),
            Index("ix_resource_status", ("Status",)),
            Index("ix_resource_type", ("ResourceType",)),
        ),
        search_columns=("Name",),
    ),
    DisasterTable(
        name="ReliefShelter", external_id_prefix="shelter", pk="ReliefShelterID",
        columns=(
            _c("ReliefShelterID", "int", nullable=False),
            _c("Name", "text", nullable=False),
            _c("Lon", "numeric"),
            _c("Lat", "numeric"),
            _c("DistrictID", "int"),
            _c("Capacity", "int", nullable=False),
            _c("CurrentOccupancy", "int", nullable=False),
            _c("Facilities", "json"),
            _c("Status", "text", nullable=False, note="open|full|closed"),
            _c("Version", "int", nullable=False),
            _c("CreatedAt", "timestamp", nullable=False),
            _c("UpdatedAt", "timestamp", nullable=False),
            _c("DeletedAt", "timestamp"),
        ),
        indexes=(Index("ix_shelter_district", ("DistrictID",)),),
        search_columns=("Name",),
    ),
    DisasterTable(
        name="ResourceAllocation", external_id_prefix="alloc", pk="ResourceAllocationID",
        columns=(
            _c("ResourceAllocationID", "int", nullable=False),
            _c("HazardEventID", "int"),
            _c("ResourceID", "int"),
            _c("TargetZoneID", "int"),
            _c("QuantityAllocated", "int", nullable=False),
            _c("Status", "text", nullable=False, note="one of ALLOCATION_STATUSES"),
            _c("Score", "numeric"),
            _c("Reason", "json"),
            _c("ProposedByActor", "text"),
            _c("ApprovedByActor", "text"),
            _c("ApprovedByEmployeeID", "int"),
            _c("DistrictID", "int"),
            _c("ProposedAt", "timestamp"),
            _c("ApprovedAt", "timestamp"),
            _c("DispatchedAt", "timestamp"),
            _c("EnrouteAt", "timestamp"),
            _c("OnsiteAt", "timestamp"),
            _c("ReleasedAt", "timestamp"),
            _c("Version", "int", nullable=False),
            _c("CreatedAt", "timestamp", nullable=False),
            _c("UpdatedAt", "timestamp", nullable=False),
            _c("DeletedAt", "timestamp"),
        ),
        indexes=(
            Index("ix_alloc_event", ("HazardEventID",)),
            Index("ix_alloc_resource", ("ResourceID",)),
            Index("ix_alloc_status", ("Status",)),
            Index("ix_alloc_district", ("DistrictID",)),
        ),
    ),
    DisasterTable(
        name="EvacuationRoute", external_id_prefix="evacroute", pk="EvacuationRouteID",
        columns=(
            _c("EvacuationRouteID", "int", nullable=False),
            _c("HazardEventID", "int"),
            _c("FromZoneID", "int"),
            _c("ToShelterID", "int"),
            _c("GeoJSON", "json", note="LineString (EPSG:4326)"),
            _c("DistanceKm", "numeric"),
            _c("EstMinutes", "numeric"),
            _c("RoadGraphVersion", "text"),
            _c("HazardExclusionVersion", "text"),
            _c("Status", "text", nullable=False, note="proposed|selected|no_route"),
            _c("Notes", "bigtext"),
            _c("Version", "int", nullable=False),
            _c("CreatedAt", "timestamp", nullable=False),
            _c("UpdatedAt", "timestamp", nullable=False),
            _c("DeletedAt", "timestamp"),
        ),
        indexes=(
            Index("ix_evacroute_event", ("HazardEventID",)),
            Index("ix_evacroute_status", ("Status",)),
        ),
    ),
    DisasterTable(
        name="ResponsePlan", external_id_prefix="resplan", pk="ResponsePlanID",
        columns=(
            _c("ResponsePlanID", "int", nullable=False),
            _c("HazardEventID", "int"),
            _c("HazardCode", "text", nullable=False),
            _c("Title", "text", nullable=False),
            _c("TemplateCode", "text"),
            _c("Status", "text", nullable=False, note="active|complete|archived"),
            _c("DistrictID", "int"),
            _c("Version", "int", nullable=False),
            _c("CreatedAt", "timestamp", nullable=False),
            _c("UpdatedAt", "timestamp", nullable=False),
            _c("DeletedAt", "timestamp"),
        ),
        indexes=(
            Index("ix_resplan_event", ("HazardEventID",)),
            Index("ix_resplan_status", ("Status",)),
        ),
        search_columns=("Title",),
    ),
    DisasterTable(
        name="ResponseTask", external_id_prefix="restask", pk="ResponseTaskID",
        columns=(
            _c("ResponseTaskID", "int", nullable=False),
            _c("ResponsePlanID", "int", nullable=False),
            _c("Title", "text", nullable=False),
            _c("Sequence", "int", nullable=False),
            _c("AssignedToActor", "text"),
            _c("AssignedToEmployeeID", "int"),
            _c("Status", "text", nullable=False, note="open|in_progress|done|overdue"),
            _c("DueAt", "timestamp"),
            _c("CompletedAt", "timestamp"),
            _c("Version", "int", nullable=False),
            _c("CreatedAt", "timestamp", nullable=False),
            _c("UpdatedAt", "timestamp", nullable=False),
            _c("DeletedAt", "timestamp"),
        ),
        indexes=(Index("ix_restask_plan", ("ResponsePlanID",)),),
    ),
    DisasterTable(
        name="FeedSource", external_id_prefix="feedsrc", pk="FeedSourceID",
        columns=(
            _c("FeedSourceID", "int", nullable=False),
            _c("Code", "text", nullable=False),
            _c("Name", "text", nullable=False),
            _c("Provider", "text"),
            _c("ConnectorKind", "text", nullable=False, note="synthetic_replay|recorded_sample|live"),
            _c("Licence", "text"),
            _c("Attribution", "text"),
            _c("FreshnessSlaMinutes", "int"),
            _c("ExternalAccessRequired", "bool", nullable=False),
            _c("CreatedAt", "timestamp", nullable=False),
        ),
        indexes=(Index("ix_feedsrc_code", ("Code",), unique=True),),
        search_columns=("Name",),
    ),
    DisasterTable(
        name="FeedIngestionRun", external_id_prefix="feedrun", pk="FeedIngestionRunID",
        columns=(
            _c("FeedIngestionRunID", "int", nullable=False),
            _c("FeedSourceID", "int"),
            _c("FeedCode", "text", nullable=False),
            _c("StartedAt", "timestamp", nullable=False),
            _c("FinishedAt", "timestamp"),
            _c("Status", "text", nullable=False, note="ok|partial|failed|stale"),
            _c("AcceptedCount", "int", nullable=False),
            _c("DuplicateCount", "int", nullable=False),
            _c("RejectedCount", "int", nullable=False),
            _c("LastObservedAt", "timestamp"),
            _c("Detail", "json"),
            _c("CreatedAt", "timestamp", nullable=False),
        ),
        indexes=(Index("ix_feedrun_source", ("FeedSourceID", "StartedAt")),),
    ),
    DisasterTable(
        name="DisasterActivity", external_id_prefix="dact", pk="DisasterActivityID",
        append_only=True,
        columns=(
            _c("DisasterActivityID", "int", nullable=False, note="identity PK; monotonic"),
            _c("SubjectType", "text", nullable=False, note="hazard_event|allocation|route|plan|..."),
            _c("SubjectID", "text", nullable=False),
            _c("Actor", "text", nullable=False),
            _c("Action", "text", nullable=False),
            _c("DiffJSON", "json", note="compact before/after (data-minimised)"),
            _c("RequestID", "text"),
            _c("CreatedAt", "timestamp", nullable=False),
        ),
        indexes=(
            Index("ix_dact_subject", ("SubjectType", "SubjectID")),
            Index("ix_dact_seq", ("DisasterActivityID",)),
        ),
    ),
)

DISASTER_TABLES_BY_NAME: dict[str, DisasterTable] = {t.name: t for t in DISASTER_TABLES}


def table(name: str) -> DisasterTable:
    return DISASTER_TABLES_BY_NAME[name]


def table_names() -> list[str]:
    return [t.name for t in DISASTER_TABLES]


def append_only_tables() -> list[str]:
    return [t.name for t in DISASTER_TABLES if t.append_only]


def as_provisioning_dict() -> dict:
    """Serializable schema description for the ds-schema provisioning generator."""
    return {
        "schema_version": SCHEMA_VERSION,
        "note": ("Prompt 17 Disaster Response — Data Store-native tables. Created "
                 "directly in Catalyst Data Store; app-populated at runtime; the "
                 "authoritative operational store. The optional AWS PostGIS/"
                 "pgRouting mirror (023_disaster_response.sql) is reconstructable "
                 "and keyed by the same ExternalIDs. AWS RLS/FORCE RLS remain "
                 "disabled (no RLS policy is created)."),
        "limits": {
            "max_json_bytes": MAX_JSON_BYTES,
            "max_geojson_bytes": MAX_GEOJSON_BYTES,
            "max_label_len": MAX_LABEL_LEN,
            "max_notes_len": MAX_NOTES_LEN,
        },
        "tables": [
            {
                "name": t.name,
                "external_id_prefix": t.external_id_prefix,
                "primary_key": t.pk,
                "append_only": t.append_only,
                "search_columns": list(t.search_columns),
                "columns": [
                    {"name": c.name, "type": c.type, "nullable": c.nullable,
                     "note": c.note} for c in t.columns
                ],
                "indexes": [
                    {"name": ix.name, "columns": list(ix.columns), "unique": ix.unique}
                    for ix in t.indexes
                ],
            }
            for t in DISASTER_TABLES
        ],
    }
