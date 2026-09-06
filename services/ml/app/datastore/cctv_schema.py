"""CCTV monitoring Data Store schema (live video analytics review + dispatch).

Single source of truth for the Data Store-native CCTV tables' columns, types,
indexes, search columns and append-only flags. Dependency-free (stdlib only) so
it can be imported by the AppSail service AND loaded by path from the
``infra/catalyst/ds-schema`` provisioning generator (same pattern as
``disaster_schema.py`` / ``board_schema.py``).

The feature this backs: many CCTV cameras are watched by a video-analytics
detector; the detector PROPOSES an alert (fight, road rage, traffic block,
crowd surge, ...); a human analyst CONFIRMS or DISMISSES it; only a confirmed
alert may raise a nearest-station dispatch, and dispatch itself needs a second
fresh confirmation. Nothing in this pipeline auto-dispatches — the same hard
invariant the Emergency Response module carries.

Honesty rules baked into the columns (not bolted on in the UI):
  * ``CctvDetection`` is APPEND-ONLY and records ``DetectorKind`` +
    ``DetectorLabel`` so a synthetic-replay detection can never be presented as
    a real model inference;
  * every detection carries ``Confidence`` and ``QualityFlag`` so a
    low-confidence proposal reads as low-confidence in the review queue;
  * ``CctvAlert.Status`` starts at ``proposed`` and only a recorded human actor
    (``ReviewedByActor``) moves it on — a dismissal keeps its reason, which is
    the false-positive feedback trail;
  * ``CctvDispatch.Reason`` records the ranking inputs (distance, source of the
    geometry, ETA assumptions) so "nearest station" is explainable rather than
    an opaque pick.

Frames/clips are NEVER stored in these tables. A detection points at an object
key in the evidence bucket (S3 / Catalyst Stratus) exactly like
``app/evidence``; bytes stay in object storage and reach the browser through a
short-lived presigned URL.

Column ``type`` vocabulary -> Catalyst Data Store column type:
    "int"       -> bigint (identity PK / numeric FK / counter)
    "text"      -> varchar (<= 255; searchable/indexable label/enum/code/actor)
    "bigtext"   -> text    (descriptions, notes)
    "bool"      -> boolean
    "numeric"   -> double  (lon/lat, confidence, score, distance)
    "json"      -> text    (bbox / reason / attributes — size-limited)
    "timestamp" -> datetime (ISO-8601, UTC)
"""
from __future__ import annotations

from dataclasses import dataclass

SCHEMA_VERSION = "2026.09.06-1"

# Hard size limits validated at the API boundary before any JSON is stored.
MAX_JSON_BYTES = 8_192           # per BBox / Reason / Attributes field
MAX_LABEL_LEN = 255
MAX_NOTES_LEN = 2_000

# ---------------------------------------------------------------------------
# vocabularies
# ---------------------------------------------------------------------------
# What the video analytics may propose. Deliberately a CLOSED list: a detector
# cannot invent a new incident class at runtime, because each class is mapped to
# a default severity + a review SOP in the UI.
DETECTION_TYPES = (
    "fight",                 # physical altercation between two or more people
    "road_rage",             # vehicle-involved confrontation / aggressive driving
    "traffic_block",         # stalled/blocked carriageway, congestion event
    "crowd_surge",           # abnormal crowd density or sudden convergence
    "vehicle_accident",      # collision / overturned vehicle
    "fire_smoke",            # visible fire or smoke plume
    "weapon_suspected",      # suspected weapon in frame (always human-reviewed)
    "abandoned_object",      # unattended bag/package in a monitored zone
    "trespass",              # entry into a restricted/after-hours zone
    "person_down",           # a person collapsed / immobile on the ground
)

# Severity vocabulary is shared with Emergency Response (minor|moderate|severe|
# extreme) so the existing SeverityBadge / severity colour tokens apply directly.
DETECTION_SEVERITIES = ("minor", "moderate", "severe", "extreme")

# Default severity per class. The detector may raise (never silently lower) this
# based on the scene; the mapping is visible so the escalation is auditable.
DEFAULT_SEVERITY: dict[str, str] = {
    "fight": "severe",
    "road_rage": "moderate",
    "traffic_block": "minor",
    "crowd_surge": "severe",
    "vehicle_accident": "severe",
    "fire_smoke": "extreme",
    "weapon_suspected": "extreme",
    "abandoned_object": "moderate",
    "trespass": "minor",
    "person_down": "severe",
}

# Human-readable class labels for alert titles / the review queue.
DETECTION_LABELS: dict[str, str] = {
    "fight": "Fight",
    "road_rage": "Road rage",
    "traffic_block": "Traffic block",
    "crowd_surge": "Crowd surge",
    "vehicle_accident": "Vehicle accident",
    "fire_smoke": "Fire / smoke",
    "weapon_suspected": "Weapon suspected",
    "abandoned_object": "Abandoned object",
    "trespass": "Trespass",
    "person_down": "Person down",
}

# Alert lifecycle. 'proposed' is the ONLY state a detector may create.
#   proposed  --confirm-->  confirmed  --dispatch-->  dispatched --> resolved
#   proposed  --dismiss-->  dismissed (terminal; keeps DismissReason)
ALERT_STATUSES = ("proposed", "confirmed", "dismissed", "dispatched", "resolved")

# Dispatch lifecycle (a dispatch is PROPOSED first; 'dispatched' needs a fresh
# confirmation at the API, exactly like a disaster resource allocation).
DISPATCH_STATUSES = (
    "proposed", "dispatched", "acknowledged", "enroute", "onsite", "closed", "cancelled",
)

CAMERA_STATUSES = ("online", "degraded", "offline", "maintenance")

# How a camera's imagery reaches the browser. 'none' is a first-class state: a
# registered camera with no configured stream renders an explicit "no stream"
# panel rather than a fake video tile.
STREAM_KINDS = ("hls", "mp4_loop", "image_snapshot", "none")

# Who produced a detection. This is recorded on every row so the provenance of
# an alert is never ambiguous.
#   synthetic_replay    -> the in-repo deterministic scene generator (demo)
#   external_analytics  -> posted by an external/edge video-analytics service
DETECTOR_KINDS = ("synthetic_replay", "external_analytics")

# Detection quality, mirroring the disaster reading/prediction quality vocabulary.
DETECTION_QUALITY = ("valid", "low_confidence", "suspect", "superseded")

# Dispatchable responder kinds (the "nearest police station" target).
PATROL_UNIT_KINDS = ("station", "patrol_vehicle", "traffic_patrol", "control_room")
PATROL_UNIT_STATUSES = ("available", "engaged", "offline")


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
class CctvTable:
    name: str                       # Data Store table name
    external_id_prefix: str         # ExternalID = "<prefix>:<pk>"
    pk: str
    columns: tuple[Column, ...]
    indexes: tuple[Index, ...] = ()
    search_columns: tuple[str, ...] = ()
    append_only: bool = False       # detections/activity: block UPDATE/DELETE

    def column_names(self) -> list[str]:
        return [c.name for c in self.columns]


def _c(name, type, nullable=True, note=""):
    return Column(name=name, type=type, nullable=nullable, note=note)


CCTV_TABLES: tuple[CctvTable, ...] = (
    CctvTable(
        name="Camera", external_id_prefix="cam", pk="CameraID",
        columns=(
            _c("CameraID", "int", nullable=False),
            _c("Code", "text", nullable=False, note="stable operator-facing code, unique"),
            _c("Name", "text", nullable=False, note="e.g. 'Lightpost 26' / 'Outpost 19'"),
            _c("LocationLabel", "text", note="human landmark, e.g. 'MG Road x Trinity Circle'"),
            _c("Lon", "numeric", nullable=False),
            _c("Lat", "numeric", nullable=False),
            _c("BearingDegrees", "numeric", note="direction the camera faces (0=N)"),
            _c("FovDegrees", "numeric", note="horizontal field of view for the map cone"),
            _c("DistrictID", "int"),
            _c("UnitID", "int", note="FK->Unit (owning police station, synthetic)"),
            _c("StreamKind", "text", nullable=False, note="one of STREAM_KINDS"),
            _c("StreamURL", "bigtext", note="HLS manifest / looping mp4 / snapshot URL"),
            _c("PosterURL", "bigtext", note="still shown before playback starts"),
            _c("Status", "text", nullable=False, note="one of CAMERA_STATUSES"),
            _c("AnalyticsEnabled", "bool", nullable=False,
               note="per-camera kill switch for the detector"),
            _c("DetectorProfile", "text",
               note="comma-separated DETECTION_TYPES this camera is watched for"),
            _c("SceneIsContinuous", "bool",
               note=("the incident in this camera's feed is present throughout "
                     "(a looping demo clip of an actual incident), so the detector "
                     "flags it in every analysis window rather than sampling a "
                     "probability. Only meaningful for scripted/replayed feeds.")),
            _c("LastHeartbeatAt", "timestamp", note="drives the offline/degraded read-out"),
            _c("LastAnalysedAt", "timestamp"),
            _c("Notes", "bigtext"),
            _c("Version", "int", nullable=False, note="optimistic concurrency counter"),
            _c("CreatedAt", "timestamp", nullable=False),
            _c("UpdatedAt", "timestamp", nullable=False),
            _c("DeletedAt", "timestamp", note="soft-delete (no hard delete in DS)"),
        ),
        indexes=(
            Index("ix_cam_code", ("Code",), unique=True),
            Index("ix_cam_district", ("DistrictID",)),
            Index("ix_cam_unit", ("UnitID",)),
            Index("ix_cam_status", ("Status",)),
        ),
        search_columns=("Name", "Code", "LocationLabel"),
    ),
    CctvTable(
        name="PatrolUnit", external_id_prefix="patrol", pk="PatrolUnitID",
        columns=(
            _c("PatrolUnitID", "int", nullable=False),
            _c("Code", "text", nullable=False, note="callsign, e.g. 'Samson_F3'"),
            _c("Name", "text", nullable=False, note="station or patrol name"),
            _c("Kind", "text", nullable=False, note="one of PATROL_UNIT_KINDS"),
            _c("UnitID", "int", note="FK->Unit (the police station this belongs to)"),
            _c("DistrictID", "int"),
            _c("Lon", "numeric", nullable=False),
            _c("Lat", "numeric", nullable=False),
            _c("Status", "text", nullable=False, note="one of PATROL_UNIT_STATUSES"),
            _c("ContactLabel", "text", note="control-room reference (never a real number)"),
            _c("Capabilities", "json", note="e.g. ['riot_control','first_aid','traffic']"),
            _c("Version", "int", nullable=False),
            _c("LastUpdatedAt", "timestamp", nullable=False),
            _c("CreatedAt", "timestamp", nullable=False),
            _c("UpdatedAt", "timestamp", nullable=False),
            _c("DeletedAt", "timestamp"),
        ),
        indexes=(
            Index("ix_patrol_code", ("Code",), unique=True),
            Index("ix_patrol_district", ("DistrictID",)),
            Index("ix_patrol_unit", ("UnitID",)),
            Index("ix_patrol_status", ("Status",)),
        ),
        search_columns=("Name", "Code"),
    ),
    CctvTable(
        name="CctvDetection", external_id_prefix="cctvdet", pk="CctvDetectionID",
        append_only=True,
        columns=(
            _c("CctvDetectionID", "int", nullable=False),
            _c("CameraID", "int", nullable=False),
            _c("DetectionType", "text", nullable=False, note="one of DETECTION_TYPES"),
            _c("Confidence", "numeric", nullable=False, note="detector confidence in [0,1]"),
            _c("Severity", "text", nullable=False, note="one of DETECTION_SEVERITIES"),
            _c("ObjectCount", "int", note="people/vehicles involved, when counted"),
            _c("BBoxJSON", "json", note="[{x,y,w,h,label,score}] normalised to [0,1]"),
            _c("Attributes", "json", note="detector-specific extras (motion, dwell, ...)"),
            _c("DetectorKind", "text", nullable=False, note="one of DETECTOR_KINDS"),
            _c("DetectorLabel", "text", nullable=False,
               note="detector@version — provenance for the alert card"),
            _c("FrameObjectKey", "bigtext",
               note="evidence-bucket object key for the still frame (bytes never in DS)"),
            _c("ClipObjectKey", "bigtext", note="evidence-bucket object key for the clip"),
            _c("DetectedAt", "timestamp", nullable=False, note="scene time"),
            _c("ReceivedAt", "timestamp", nullable=False, note="ingestion time"),
            _c("WindowSeconds", "numeric", note="length of the analysed window"),
            _c("QualityFlag", "text", nullable=False, note="one of DETECTION_QUALITY"),
            _c("SourceRecordID", "text",
               note="idempotency key from the producer (camera:type:window)"),
            _c("DistrictID", "int"),
            _c("Lon", "numeric"),
            _c("Lat", "numeric"),
            _c("CreatedAt", "timestamp", nullable=False),
        ),
        indexes=(
            Index("ix_cctvdet_source", ("SourceRecordID",), unique=True),
            Index("ix_cctvdet_camera", ("CameraID", "DetectedAt")),
            Index("ix_cctvdet_type", ("DetectionType", "DetectedAt")),
            Index("ix_cctvdet_district", ("DistrictID",)),
            Index("ix_cctvdet_quality", ("QualityFlag",)),
        ),
    ),
    CctvTable(
        name="CctvAlert", external_id_prefix="cctvalert", pk="CctvAlertID",
        columns=(
            _c("CctvAlertID", "int", nullable=False),
            _c("CctvDetectionID", "int", nullable=False),
            _c("CameraID", "int", nullable=False),
            _c("AlertType", "text", nullable=False, note="one of DETECTION_TYPES"),
            _c("Severity", "text", nullable=False),
            _c("Title", "text", nullable=False, note="e.g. 'Fight (5 people)'"),
            _c("Message", "bigtext", note="plain-language summary shown on the card"),
            _c("Confidence", "numeric", nullable=False),
            _c("Status", "text", nullable=False, note="one of ALERT_STATUSES"),
            _c("ReviewedByActor", "text", note="the human who confirmed/dismissed"),
            _c("ReviewedAt", "timestamp"),
            _c("ReviewNote", "bigtext", note="analyst note recorded with a confirmation"),
            _c("DismissReason", "text",
               note="false_positive|duplicate|already_handled|not_actionable|other"),
            _c("DistrictID", "int"),
            _c("Lon", "numeric"),
            _c("Lat", "numeric"),
            _c("LocationLabel", "text"),
            _c("NearestUnitID", "int", note="hint only; the dispatch row is authoritative"),
            _c("Payload", "json",
               note="data-minimised card context (detector label, quality, synthetic flag)"),
            _c("Version", "int", nullable=False),
            _c("CreatedAt", "timestamp", nullable=False),
            _c("UpdatedAt", "timestamp", nullable=False),
            _c("DeletedAt", "timestamp"),
        ),
        indexes=(
            Index("ix_cctvalert_status", ("Status",)),
            Index("ix_cctvalert_camera", ("CameraID",)),
            Index("ix_cctvalert_detection", ("CctvDetectionID",), unique=True),
            Index("ix_cctvalert_district", ("DistrictID",)),
            Index("ix_cctvalert_created", ("CreatedAt",)),
        ),
        search_columns=("Title", "Message", "LocationLabel"),
    ),
    CctvTable(
        name="CctvDispatch", external_id_prefix="cctvdisp", pk="CctvDispatchID",
        columns=(
            _c("CctvDispatchID", "int", nullable=False),
            _c("CctvAlertID", "int", nullable=False),
            _c("PatrolUnitID", "int", note="Data Store responder row, when resolved there"),
            _c("UnitID", "int", note="FK->Unit (police station), when resolved via PostGIS"),
            _c("UnitName", "text", nullable=False, note="responder label shown to the analyst"),
            _c("UnitKind", "text", note="one of PATROL_UNIT_KINDS"),
            _c("DistanceKm", "numeric", nullable=False),
            _c("EtaMinutes", "numeric", note="estimate from a versioned speed assumption"),
            _c("Score", "numeric", note="ranking score (higher is better)"),
            _c("Reason", "json",
               note="explainable inputs: distance, geometry source, ETA assumption, rule"),
            _c("Status", "text", nullable=False, note="one of DISPATCH_STATUSES"),
            _c("ProposedByActor", "text"),
            _c("ApprovedByActor", "text"),
            _c("DistrictID", "int"),
            _c("ProposedAt", "timestamp"),
            _c("DispatchedAt", "timestamp"),
            _c("AcknowledgedAt", "timestamp"),
            _c("EnrouteAt", "timestamp"),
            _c("OnsiteAt", "timestamp"),
            _c("ClosedAt", "timestamp"),
            _c("CancelledAt", "timestamp"),
            _c("Notes", "bigtext"),
            _c("Version", "int", nullable=False),
            _c("CreatedAt", "timestamp", nullable=False),
            _c("UpdatedAt", "timestamp", nullable=False),
            _c("DeletedAt", "timestamp"),
        ),
        indexes=(
            Index("ix_cctvdisp_alert", ("CctvAlertID",)),
            Index("ix_cctvdisp_status", ("Status",)),
            Index("ix_cctvdisp_unit", ("UnitID",)),
            Index("ix_cctvdisp_district", ("DistrictID",)),
        ),
        search_columns=("UnitName",),
    ),
    CctvTable(
        name="CctvActivity", external_id_prefix="cctvact", pk="CctvActivityID",
        append_only=True,
        columns=(
            _c("CctvActivityID", "int", nullable=False, note="identity PK; monotonic"),
            _c("SubjectType", "text", nullable=False,
               note="camera|detection|alert|dispatch|access"),
            _c("SubjectID", "text", nullable=False),
            _c("Actor", "text", nullable=False),
            _c("Action", "text", nullable=False, note="e.g. alert.confirmed"),
            _c("DiffJSON", "json", note="compact before/after (data-minimised)"),
            _c("RequestID", "text"),
            _c("CreatedAt", "timestamp", nullable=False),
        ),
        indexes=(
            Index("ix_cctvact_subject", ("SubjectType", "SubjectID")),
            Index("ix_cctvact_seq", ("CctvActivityID",)),
        ),
    ),
)

CCTV_TABLES_BY_NAME: dict[str, CctvTable] = {t.name: t for t in CCTV_TABLES}


def table(name: str) -> CctvTable:
    return CCTV_TABLES_BY_NAME[name]


def table_names() -> list[str]:
    return [t.name for t in CCTV_TABLES]


def append_only_tables() -> list[str]:
    return [t.name for t in CCTV_TABLES if t.append_only]


def default_severity(detection_type: str) -> str:
    return DEFAULT_SEVERITY.get(detection_type, "moderate")


def detection_label(detection_type: str) -> str:
    return DETECTION_LABELS.get(detection_type, detection_type.replace("_", " ").title())


def as_provisioning_dict() -> dict:
    """Serializable schema description for the ds-schema provisioning generator."""
    return {
        "schema_version": SCHEMA_VERSION,
        "note": ("CCTV monitoring — Data Store-native tables. Video analytics "
                 "PROPOSES an alert, a human analyst confirms or dismisses it, and "
                 "only a confirmed alert may raise a nearest-station dispatch "
                 "(which needs its own fresh confirmation). Detections and activity "
                 "are append-only. Frame/clip BYTES are never stored here — only an "
                 "object key into the evidence bucket. The optional AWS PostGIS "
                 "mirror (026_cctv_monitoring.sql) is reconstructable and keyed by "
                 "the same ExternalIDs; AWS RLS/FORCE RLS remain disabled."),
        "limits": {
            "max_json_bytes": MAX_JSON_BYTES,
            "max_label_len": MAX_LABEL_LEN,
            "max_notes_len": MAX_NOTES_LEN,
        },
        "vocabularies": {
            "detection_types": list(DETECTION_TYPES),
            "detection_severities": list(DETECTION_SEVERITIES),
            "alert_statuses": list(ALERT_STATUSES),
            "dispatch_statuses": list(DISPATCH_STATUSES),
            "camera_statuses": list(CAMERA_STATUSES),
            "stream_kinds": list(STREAM_KINDS),
            "detector_kinds": list(DETECTOR_KINDS),
            "detection_quality": list(DETECTION_QUALITY),
            "patrol_unit_kinds": list(PATROL_UNIT_KINDS),
            "patrol_unit_statuses": list(PATROL_UNIT_STATUSES),
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
            for t in CCTV_TABLES
        ],
    }
