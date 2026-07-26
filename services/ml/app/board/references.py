"""Board object & provenance contract (Prompt 16 §B).

A board node is a REFERENCE to a canonical DRISHTI object, never a detached copy.
This module owns:

  * the server-side WHITELIST of supported ``RefTable`` object kinds — an
    arbitrary client-supplied table name is NEVER interpolated into SQL;
  * read-only hydration of the live object (label + a bounded, sanitised
    ``Snapshot`` with a source version + integrity hash) from the operational
    PostgreSQL store — using column INTROSPECTION so a schema variation degrades
    gracefully instead of erroring;
  * live-vs-snapshot diffing + broken/superseded reference detection;
  * best-effort deep links back to the authoritative DRISHTI detail page.

Hard rules:
  * uploaded file BYTES are never read, parsed or copied into a snapshot — only
    metadata/provenance (kind, mime, size, hash, status) is ever exposed;
  * sensitive / raw / narrative / secret columns are dropped from every snapshot;
  * the PG table for a ref comes only from the server-side spec and is still
    validated as a plain identifier before it is quoted.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from .. import db
from ..datastore.board_schema import MAX_SNAPSHOT_BYTES

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Columns whose NAME marks the value as sensitive/raw — always dropped from a
# snapshot even if a spec accidentally lists them (defence in depth).
_SENSITIVE_COL_PARTS = (
    "password", "secret", "token", "apikey", "api_key", "credential", "raw",
    "content", "narrative", "brief", "facts", "statement_text", "prompt",
    "bytes", "blob", "payload", "aadhaar", "aadhar", "passport", "biometric",
    "identifiervalue", "contactvalue", "addresstext", "geom",
)
_MAX_STR = 240
_MAX_SNAPSHOT_KEYS = 24


@dataclass(frozen=True)
class RefSpec:
    """How to hydrate one whitelisted canonical object kind."""
    ref_table: str                 # logical name clients send (== Data Store table)
    pg_table: str                  # actual PG table (server-controlled, never client)
    pk_col: str
    node_kind: str                 # default NodeKind for this reference
    label_cols: tuple[str, ...]    # ordered label candidates (first non-null wins)
    summary_cols: tuple[str, ...]  # candidate snapshot columns (existing ones kept)
    entity_col: Optional[str] = None   # column holding a CanonicalEntityID
    version_cols: tuple[str, ...] = ("UpdatedAt", "CreatedAt")
    open_in_source: Optional[str] = None   # frontend route template, {id} placeholder
    note: str = ""


# ---------------------------------------------------------------------------
# The whitelist (Prompt 16 §B.3). news_event is intentionally ABSENT until the
# governed OSINT module exists; a synthetic map extract / note carries its own
# client-provided bounded snapshot and has no DB ref.
# ---------------------------------------------------------------------------
_SPECS: tuple[RefSpec, ...] = (
    RefSpec("CaseMaster", "CaseMaster", "CaseMasterID", "case",
            label_cols=("CrimeNo", "FIRNo"),
            summary_cols=("CrimeNo", "FIRNo", "CaseStatusID", "CaseCategoryID",
                          "CrimeRegisteredDate", "IncidentFromDate", "PoliceStationID"),
            open_in_source="/cases/{id}",
            note="Case/FIR header; narrative (BriefFacts) is never snapshotted."),
    RefSpec("CanonicalPerson", "CanonicalPerson", "CanonicalPersonID", "entity",
            label_cols=("DisplayLabel", "PublicRef"),
            summary_cols=("PublicRef", "DisplayLabel", "ResolutionStatus", "IsUnknown"),
            open_in_source="/people/canonical/{id}",
            note="Protected attributes (birth year, gender, juvenile) are excluded."),
    RefSpec("CanonicalOrganisation", "CanonicalOrganisation", "CanonicalOrganisationID",
            "entity", label_cols=("Name", "PublicRef"),
            summary_cols=("PublicRef", "Name", "OrgType"),
            open_in_source="/network?entity={id}"),
    RefSpec("CanonicalEntity", "CanonicalEntity", "CanonicalEntityID", "entity",
            label_cols=("Label", "PublicRef"),
            summary_cols=("PublicRef", "EntityKind", "Label"),
            entity_col="CanonicalEntityID",
            open_in_source="/network?entity={id}"),
    RefSpec("CasePartyRole", "CasePartyRole", "CasePartyRoleID", "accused",
            label_cols=("PartyLabel", "RoleType"),
            summary_cols=("RoleType", "PartyLabel", "CaseMasterID",
                          "CanonicalPersonID", "CanonicalOrganisationID",
                          "IsUnknownParty", "LegacyRefTable", "LegacyRefID",
                          "SequenceNo"),
            note="Case party appearance; role type drives the specific NodeKind."),
    RefSpec("Victim", "Victim", "VictimMasterID", "victim",
            label_cols=("VictimName",),
            summary_cols=("CaseMasterID", "VictimPolice", "GenderID",
                          "CanonicalPersonID"),
            note="Case-linked victim appearance. Age and other protected attributes "
                 "are intentionally excluded from the board snapshot."),
    RefSpec("Accused", "Accused", "AccusedMasterID", "accused",
            label_cols=("AccusedName", "PersonID"),
            summary_cols=("CaseMasterID", "PersonID", "GenderID",
                          "CanonicalPersonID", "CasePartyRoleID"),
            note="Case-linked accused appearance. Age and other protected attributes "
                 "are intentionally excluded from the board snapshot."),
    RefSpec("ComplainantDetails", "ComplainantDetails", "ComplainantID",
            "complainant", label_cols=("ComplainantName",),
            summary_cols=("CaseMasterID", "GenderID", "CanonicalPersonID"),
            note="Case-linked complainant appearance. Protected demographic details "
                 "are intentionally excluded from the board snapshot."),
    RefSpec("EntityGraph", "EntityGraph", "EntityID", "entity",
            label_cols=("Label",),
            summary_cols=("EntityType", "Label", "RefTable", "RefID", "CanonicalEntityID"),
            entity_col="CanonicalEntityID",
            open_in_source="/people/{id}",
            note="Curated graph node; size may encode centrality on the canvas."),
    RefSpec("FinancialAccount", "FinancialAccount", "AccountID", "account",
            label_cols=("SyntheticReference", "AccountNo"),
            summary_cols=("SyntheticReference", "Currency", "OwnerReviewStatus",
                          "OwnerCanonicalPersonID", "CanonicalEntityID"),
            entity_col="CanonicalEntityID",
            open_in_source="/network?mode=money&account={id}"),
    RefSpec("FinancialTransaction", "FinancialTransaction", "TransactionID", "account",
            label_cols=("SyntheticReference",),
            summary_cols=("Amount", "Currency", "Direction", "TxnTimestamp",
                          "SourceAccountID", "DestinationAccountID", "DestAccountID",
                          "Channel", "IsFlagged", "ReviewStatus"),
            open_in_source="/network?mode=money"),
    RefSpec("EvidenceItem", "EvidenceItem", "EvidenceItemID", "document",
            label_cols=("Title", "OriginalFilename", "EvidenceType"),
            summary_cols=("EvidenceType", "Category", "State", "MimeType", "ByteSize",
                          "Sha256", "Status", "CaseMasterID", "SyntheticReference",
                          "CapturedAt", "ReceivedAt"),
            note="METADATA/PROVENANCE ONLY — file bytes are never read or parsed."),
    RefSpec("Statement", "Statement", "StatementID", "note",
            label_cols=("StatementType",),
            summary_cols=("StatementType", "State", "AccessClassification",
                          "CaseMasterID", "CanonicalPersonID"),
            note="Statement TEXT is never snapshotted (restricted/redacted)."),
    RefSpec("PropertyItem", "PropertyItem", "PropertyItemID", "vehicle",
            label_cols=("SyntheticIdentifier", "ItemType", "Description"),
            summary_cols=("ItemType", "SyntheticIdentifier", "Status", "CaseMasterID"),
            note="Vehicle/property/seizure item metadata."),
    RefSpec("ArrestSurrender", "ArrestSurrender", "ArrestSurrenderID", "note",
            label_cols=("ArrestSurrenderDate", "ArrestSurrenderTypeID"),
            summary_cols=("CaseMasterID", "ArrestSurrenderTypeID",
                          "ArrestSurrenderDate", "PoliceStationID", "CourtID",
                          "AccusedMasterID", "IsAccused"),
            note="Arrest or surrender lifecycle record linked to the case."),
    RefSpec("ChargesheetDetails", "ChargesheetDetails", "CSID", "document",
            label_cols=("cstype", "csdate"),
            summary_cols=("CaseMasterID", "csdate", "cstype", "PolicePersonID"),
            note="Chargesheet/final-report metadata linked to the case."),
    RefSpec("CaseEvent", "CaseEvent", "CaseEventID", "note",
            label_cols=("EventType", "EventCategory"),
            summary_cols=("CaseMasterID", "EventType", "EventCategory", "SequenceNo",
                          "OccurredAt", "RecordedAt", "FromStatus", "ToStatus",
                          "ActorRole"),
            note="Append-only case lifecycle event."),
    RefSpec("Seizure", "Seizure", "SeizureID", "note",
            label_cols=("SeizureType", "SeizedAt"),
            summary_cols=("CaseMasterID", "CaseEventID", "SeizureType", "SeizedAt",
                          "Place", "MemoEvidenceItemID"),
            note="Case-linked seizure event metadata."),
    RefSpec("Device", "Device", "DeviceID", "phone",
            label_cols=("Label", "SyntheticIdentifier", "DeviceType"),
            summary_cols=("CaseMasterID", "DeviceType", "SyntheticIdentifier",
                          "CanonicalEntityID", "SourceRecordID"),
            entity_col="CanonicalEntityID",
            note="Synthetic device reference linked to the case."),
    RefSpec("DeviceArtifact", "DeviceArtifact", "DeviceArtifactID", "document",
            label_cols=("SyntheticReference", "ArtifactType"),
            summary_cols=("DeviceID", "ArtifactType", "SyntheticReference",
                          "EvidenceItemID"),
            note="Metadata for an artifact reviewed from a case-linked device."),
    RefSpec("CommunicationEvent", "CommunicationEvent", "CommunicationEventID",
            "phone", label_cols=("CommType", "OccurredAt"),
            summary_cols=("CaseMasterID", "CommType", "OccurredAt", "DurationSec",
                          "SyntheticEndpointA", "SyntheticEndpointB", "ReviewStatus",
                          "FromCanonicalEntityID", "ToCanonicalEntityID"),
            note="Reviewed synthetic communication metadata linked to the case."),
    RefSpec("LocationObservation", "LocationObservation", "LocationObservationID",
            "location", label_cols=("Source", "ObservedAt"),
            summary_cols=("CaseMasterID", "CanonicalEntityID", "ObservedAt",
                          "DistrictID", "Source", "SourceRecordID"),
            entity_col="CanonicalEntityID",
            note="Case-linked location observation; exact geometry is not copied "
                 "into the board snapshot."),
    RefSpec("CourtEvent", "CourtEvent", "CourtEventID", "note",
            label_cols=("EventType", "ScheduledAt"),
            summary_cols=("CaseMasterID", "CourtID", "EventType", "ScheduledAt",
                          "OccurredAt", "Outcome"),
            note="Append-only court lifecycle event."),
    RefSpec("BailEvent", "BailEvent", "BailEventID", "note",
            label_cols=("BailType", "Status"),
            summary_cols=("CaseMasterID", "CanonicalPersonID", "BailType", "Status",
                          "DecidedAt", "CourtID"),
            note="Case-linked bail decision metadata."),
    RefSpec("CaseDisposition", "CaseDisposition", "CaseDispositionID", "document",
            label_cols=("DispositionType", "DispositionDate"),
            summary_cols=("CaseMasterID", "DispositionType", "DispositionDate",
                          "CourtEventID", "IsFinal"),
            note="Final or interim case disposition metadata."),
    RefSpec("LabResult", "LabResult", "LabResultID", "document",
            label_cols=("SyntheticReference", "TestType", "Status"),
            summary_cols=("CaseMasterID", "PropertyItemID", "SeizureID", "TestType",
                          "Status", "LabName", "RequestedAt", "ResultAt",
                          "ReportEvidenceItemID"),
            note="Forensic/laboratory result metadata; report content is excluded."),
    RefSpec("CrimeHotspot", "CrimeHotspot", "HotspotID", "hotspot",
            label_cols=("Name",),
            summary_cols=("Name", "DistrictID", "Method", "Score", "WindowStart",
                          "WindowEnd"),
            open_in_source="/map?hotspot={id}",
            note="Aggregate area hotspot (not an individual location)."),
    RefSpec("CrimePrediction", "CrimePrediction", "PredictionID", "note",
            label_cols=("CrimeHeadID",),
            summary_cols=("DistrictID", "CrimeHeadID", "WindowStart", "WindowEnd",
                          "PredictedCount", "ModelVersionID"),
            open_in_source="/analytics",
            note="Area-level forecast result; carries its model version."),
    RefSpec("ModelInference", "ModelInference", "InferenceID", "note",
            label_cols=("RefTable",),
            summary_cols=("ModelVersionID", "RefTable", "RefID", "Confidence",
                          "LatencyMs", "CreatedAt"),
            note="Prediction/result provenance (FeatureSnapshot reference)."),
    RefSpec("ChatMessage", "ChatMessage", "ChatMessageID", "chat_answer",
            label_cols=("Role",),
            summary_cols=("Role", "ModelVersion", "Citations", "SourceRecordIDs",
                          "ChatSessionID"),
            note="Cited assistant answer — approved sources only; RawPrompt excluded."),
    # --- Emergency Response (Prompt 17) — Data Store-native objects ---------
    # These hydrate from the Catalyst Data Store disaster repo (not PostgreSQL).
    # They remain LIVE references with a pin-time snapshot; allocation reasoning
    # added on the board is a hypothesis/annotation, never source evidence.
    RefSpec("HazardEvent", "HazardEvent", "HazardEventID", "hazard_event",
            label_cols=("Description", "HazardCode"),
            summary_cols=("HazardCode", "Status", "Severity", "DistrictID",
                          "OnsetAt", "PredictedPeakAt", "Source", "SourceVersion"),
            open_in_source="/er/live?event={id}",
            note="Hazard event (Data Store-native). Area/time-level; not person-level."),
    RefSpec("HazardPrediction", "HazardPrediction", "HazardPredictionID", "hazard_prediction",
            label_cols=("ModelVersionLabel", "HazardCode"),
            summary_cols=("HazardCode", "DistrictID", "Probability", "PredictedSeverity",
                          "Confidence", "QualityState", "ForecastStart", "ForecastEnd",
                          "ModelVersionLabel", "FeatureSnapshotID"),
            open_in_source="/er/forecast?prediction={id}",
            note="Reproducible forecast row; carries model/rule version + confidence."),
    RefSpec("HazardRiskZone", "HazardRiskZone", "HazardRiskZoneID", "hazard_risk_zone",
            label_cols=("Name", "HazardCode"),
            summary_cols=("HazardCode", "ZoneKind", "RiskLevel", "Score", "DistrictID"),
            open_in_source="/er/live?zone={id}",
            note="Susceptibility / dynamic risk zone (aggregate area, not a person)."),
    RefSpec("Resource", "Resource", "ResourceID", "resource",
            label_cols=("Name",),
            summary_cols=("ResourceType", "Quantity", "Unit", "Status", "Capacity",
                          "DistrictID", "HomeUnitID"),
            open_in_source="/er/resources?resource={id}",
            note="Deployable resource."),
    RefSpec("ReliefShelter", "ReliefShelter", "ReliefShelterID", "shelter",
            label_cols=("Name",),
            summary_cols=("Capacity", "CurrentOccupancy", "Status", "DistrictID"),
            open_in_source="/er/resources?shelter={id}",
            note="Relief shelter capacity/occupancy."),
    RefSpec("ResourceAllocation", "ResourceAllocation", "ResourceAllocationID", "allocation",
            label_cols=("Status",),
            summary_cols=("HazardEventID", "ResourceID", "QuantityAllocated", "Status",
                          "Score", "DistrictID"),
            open_in_source="/er/resources?allocation={id}",
            note="Allocation reasoning on the board is a hypothesis/annotation, "
                 "not source evidence."),
    RefSpec("EvacuationRoute", "EvacuationRoute", "EvacuationRouteID", "evacuation_route",
            label_cols=("Status",),
            summary_cols=("HazardEventID", "FromZoneID", "ToShelterID", "DistanceKm",
                          "EstMinutes", "Status", "RoadGraphVersion"),
            open_in_source="/er/plans?route={id}",
            note="Evacuation route; never described as guaranteed safe."),
)

# Ref tables that live in the Catalyst Data Store disaster repo (Prompt 17),
# hydrated from Data Store instead of the operational PostgreSQL store.
_DATASTORE_REF_TABLES = {
    "HazardEvent", "HazardPrediction", "HazardRiskZone", "Resource",
    "ReliefShelter", "ResourceAllocation", "EvacuationRoute",
}

SPECS: dict[str, RefSpec] = {s.ref_table: s for s in _SPECS}

# NodeKind enum (doc 06 §3) — the client-selectable node kinds. Content kinds
# (note/image/document/map_extract) may carry a self-supplied bounded snapshot.
NODE_KINDS = (
    "entity", "case", "accused", "victim", "complainant", "vehicle", "phone",
    "account", "location", "hotspot", "news_event", "chat_answer", "note",
    "image", "document", "map_extract", "prediction",
    # Prompt 17 — Emergency Response object kinds (sent to a board for review).
    "hazard_event", "hazard_prediction", "hazard_risk_zone", "resource",
    "shelter", "allocation", "evacuation_route",
)

# Kinds that DON'T resolve to a whitelisted DB ref (client carries a bounded
# snapshot: a sticky note, a bounded map extract's bbox, a plain label). Never
# file bytes.
_SELF_SNAPSHOT_KINDS = {"note", "map_extract", "news_event"}

# Party role -> concrete NodeKind refinement for CasePartyRole references.
_PARTY_KIND = {"accused": "accused", "victim": "victim", "complainant": "complainant",
               "organisation": "entity", "witness": "note", "informant": "note"}


@dataclass
class HydratedRef:
    ref_table: Optional[str]
    ref_id: Optional[str]
    node_kind: str
    exists: Optional[bool]                 # True | False (broken) | None (unavailable)
    label: str = ""
    canonical_entity_id: Optional[int] = None
    snapshot: dict[str, Any] = field(default_factory=dict)
    source_version: Optional[str] = None
    source_hash: Optional[str] = None
    open_in_source: Optional[str] = None
    detail: Optional[str] = None

    def as_dict(self) -> dict:
        return {
            "ref_table": self.ref_table, "ref_id": self.ref_id,
            "node_kind": self.node_kind, "exists": self.exists, "label": self.label,
            "canonical_entity_id": self.canonical_entity_id, "snapshot": self.snapshot,
            "source_version": self.source_version, "source_hash": self.source_hash,
            "open_in_source": self.open_in_source, "detail": self.detail,
        }


def supported_kinds() -> list[str]:
    return list(NODE_KINDS)


def supported_ref_tables() -> list[str]:
    return list(SPECS.keys())


def is_whitelisted(ref_table: Optional[str]) -> bool:
    return bool(ref_table) and ref_table in SPECS


def spec_for(ref_table: str) -> Optional[RefSpec]:
    return SPECS.get(ref_table)


# ---------------------------------------------------------------------------
# Snapshot hashing + sanitisation
# ---------------------------------------------------------------------------
def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def snapshot_hash(snapshot: dict[str, Any]) -> str:
    """Stable SHA-256 of a snapshot projection (integrity / supersede detection)."""
    return hashlib.sha256(_canonical_json(snapshot).encode("utf-8")).hexdigest()


def _is_sensitive_col(name: str) -> bool:
    n = name.lower()
    return any(part in n for part in _SENSITIVE_COL_PARTS)


def _sanitise_value(v: Any) -> Any:
    if isinstance(v, str):
        s = v.replace("\r", " ").replace("\n", " ")
        return s[:_MAX_STR] + ("…" if len(s) > _MAX_STR else "")
    if isinstance(v, (int, float, bool)) or v is None:
        return v
    return _sanitise_value(str(v))


def sanitise_snapshot(raw: dict[str, Any]) -> dict[str, Any]:
    """Drop sensitive/raw columns, truncate strings, cap key count + total size."""
    out: dict[str, Any] = {}
    for i, (k, v) in enumerate(raw.items()):
        if i >= _MAX_SNAPSHOT_KEYS:
            break
        if _is_sensitive_col(str(k)):
            continue
        out[str(k)] = _sanitise_value(v)
    # hard size cap (bytes) — trim keys until under the limit
    while len(_canonical_json(out).encode("utf-8")) > MAX_SNAPSHOT_BYTES and out:
        out.pop(next(reversed(out)))
    return out


# ---------------------------------------------------------------------------
# Column introspection (cached per PG table)
# ---------------------------------------------------------------------------
_COLS_CACHE: dict[str, set[str]] = {}


def _table_columns(conn, pg_table: str) -> set[str]:
    if pg_table in _COLS_CACHE:
        return _COLS_CACHE[pg_table]
    cols: set[str] = set()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name=%s", (pg_table,))
        cols = {r[0] for r in cur.fetchall()}
    _COLS_CACHE[pg_table] = cols
    return cols


def _resolve_kind(spec: RefSpec, row: dict[str, Any], requested_kind: Optional[str]) -> str:
    if requested_kind and requested_kind in NODE_KINDS:
        return requested_kind
    if spec.ref_table == "CasePartyRole":
        rt = str(row.get("RoleType", "")).lower()
        return _PARTY_KIND.get(rt, "accused")
    if spec.ref_table == "CanonicalEntity":
        ek = str(row.get("EntityKind", "")).lower()
        return {"phone": "phone", "vehicle": "vehicle", "account": "account",
                "location": "location", "device": "phone",
                "organisation": "entity"}.get(ek, "entity")
    return spec.node_kind


def hydrate(ref_table: Optional[str], ref_id: Optional[str], *,
            requested_kind: Optional[str] = None) -> HydratedRef:
    """Hydrate a canonical object reference into a live label + pinned snapshot.

    Returns ``exists=None`` when the operational store is unavailable, ``False``
    when the reference is broken (row gone), and ``True`` with a snapshot when
    it resolves. NEVER raises into the request path.
    """
    # Self-snapshot/content nodes have no DB reference. A whitelisted source
    # record may legitimately render as a ``note`` (Statement, CaseEvent,
    # Seizure, etc.) and must still be hydrated rather than mistaken for a
    # free-form sticky.
    if not ref_table:
        kind = requested_kind if requested_kind in NODE_KINDS else "note"
        return HydratedRef(ref_table=ref_table, ref_id=ref_id, node_kind=kind,
                           exists=True, label="", detail="content node (no source ref)")

    if not is_whitelisted(ref_table):
        return HydratedRef(ref_table=ref_table, ref_id=ref_id,
                           node_kind=requested_kind or "note", exists=False,
                           detail="ref_table not in the supported object whitelist")

    # Emergency Response objects are Data Store-native (Prompt 17): hydrate from
    # the disaster repo, not PostgreSQL. Live reference + bounded pin-time snapshot.
    if ref_table in _DATASTORE_REF_TABLES:
        return _hydrate_datastore(SPECS[ref_table], ref_table, ref_id, requested_kind)

    spec = SPECS[ref_table]
    if not _IDENT_RE.match(spec.pg_table):        # server-controlled, but double-check
        return HydratedRef(ref_table=ref_table, ref_id=ref_id, node_kind=spec.node_kind,
                           exists=False, detail="invalid source table identifier")

    try:
        with db.ro_conn() as conn:
            available = _table_columns(conn, spec.pg_table)
            if not available:
                return HydratedRef(ref_table=ref_table, ref_id=ref_id,
                                   node_kind=spec.node_kind, exists=None,
                                   detail="source table not present in this environment")
            wanted: list[str] = []
            for c in (spec.pk_col, *spec.label_cols, *spec.summary_cols,
                      *spec.version_cols):
                if c in available and c not in wanted:
                    wanted.append(c)
            if spec.entity_col and spec.entity_col in available and spec.entity_col not in wanted:
                wanted.append(spec.entity_col)
            col_sql = ", ".join(f'"{c}"' for c in wanted)
            with conn.cursor() as cur:
                cur.execute(
                    f'SELECT {col_sql} FROM "{spec.pg_table}" '
                    f'WHERE "{spec.pk_col}"::text = %s LIMIT 1', (str(ref_id),))
                row = cur.fetchone()
                if row is None:
                    return HydratedRef(ref_table=ref_table, ref_id=ref_id,
                                       node_kind=spec.node_kind, exists=False,
                                       detail="referenced object not found (broken/removed)")
                record = {wanted[i]: row[i] for i in range(len(wanted))}
    except Exception as exc:  # noqa: BLE001 — hydration must never break the request
        return HydratedRef(ref_table=ref_table, ref_id=ref_id, node_kind=spec.node_kind,
                           exists=None, detail=f"source unavailable ({type(exc).__name__})")

    label = ""
    for c in spec.label_cols:
        if record.get(c):
            label = str(record[c])
            break
    if not label:
        label = f"{spec.ref_table} {ref_id}"

    version = None
    for c in spec.version_cols:
        if record.get(c) is not None:
            version = str(record[c])
            break

    entity_id = None
    if spec.entity_col and record.get(spec.entity_col) is not None:
        try:
            entity_id = int(record[spec.entity_col])
        except (TypeError, ValueError):
            entity_id = None
    if entity_id is None and spec.ref_table == "EntityGraph":
        try:
            entity_id = int(ref_id)  # an EntityGraph node IS a graph entity
        except (TypeError, ValueError):
            entity_id = None

    snapshot = sanitise_snapshot({c: record.get(c) for c in spec.summary_cols
                                  if c in record})
    open_src = (spec.open_in_source.format(id=ref_id)
                if spec.open_in_source and ref_id is not None else None)

    return HydratedRef(
        ref_table=ref_table, ref_id=str(ref_id),
        node_kind=_resolve_kind(spec, record, requested_kind),
        exists=True, label=label[:_MAX_STR], canonical_entity_id=entity_id,
        snapshot=snapshot, source_version=version, source_hash=snapshot_hash(snapshot),
        open_in_source=open_src, detail=spec.note or None)


def _hydrate_datastore(spec: RefSpec, ref_table: str, ref_id: Optional[str],
                       requested_kind: Optional[str]) -> HydratedRef:
    """Hydrate a Data Store-native Emergency Response object (Prompt 17).

    Reads the disaster repo (Catalyst Data Store), builds a bounded sanitised
    snapshot + source version/hash. Never raises into the request path."""
    try:
        from ..disaster.repo import disaster_repo
        pk = int(ref_id)
    except (TypeError, ValueError):
        return HydratedRef(ref_table=ref_table, ref_id=ref_id, node_kind=spec.node_kind,
                           exists=False, detail="invalid Data Store reference id")
    try:
        row = disaster_repo().get(ref_table, pk)
    except Exception as exc:  # noqa: BLE001 — hydration must never break the request
        return HydratedRef(ref_table=ref_table, ref_id=ref_id, node_kind=spec.node_kind,
                           exists=None, detail=f"Data Store unavailable ({type(exc).__name__})")
    if row is None or row.get("DeletedAt"):
        return HydratedRef(ref_table=ref_table, ref_id=ref_id, node_kind=spec.node_kind,
                           exists=False, detail="referenced object not found (broken/removed)")
    label = ""
    for c in spec.label_cols:
        if row.get(c):
            label = str(row[c])
            break
    if not label:
        label = f"{spec.ref_table} {ref_id}"
    version = None
    for c in ("UpdatedAt", "CreatedAt", "Version"):
        if row.get(c) is not None:
            version = str(row[c])
            break
    snapshot = sanitise_snapshot({c: row.get(c) for c in spec.summary_cols if c in row})
    open_src = (spec.open_in_source.format(id=ref_id)
                if spec.open_in_source and ref_id is not None else None)
    return HydratedRef(
        ref_table=ref_table, ref_id=str(ref_id),
        node_kind=(requested_kind if requested_kind in NODE_KINDS else spec.node_kind),
        exists=True, label=label[:_MAX_STR], snapshot=snapshot, source_version=version,
        source_hash=snapshot_hash(snapshot), open_in_source=open_src, detail=spec.note or None)


# ---------------------------------------------------------------------------
# Live-vs-snapshot diff (Prompt 16 §B.6)
# ---------------------------------------------------------------------------
def diff_reference(pinned_snapshot: dict[str, Any], pinned_hash: Optional[str],
                   ref_table: Optional[str], ref_id: Optional[str]) -> dict[str, Any]:
    """Compare a node's pin-time snapshot against the live object.

    status: ``live`` (unchanged), ``changed`` (superseded — hash differs),
    ``broken`` (source gone), ``unavailable`` (store unreachable / content node).
    """
    live = hydrate(ref_table, ref_id)
    if live.exists is None:
        return {"status": "unavailable", "changed_fields": [], "detail": live.detail}
    if live.exists is False:
        return {"status": "broken", "changed_fields": [], "detail": live.detail}
    live_hash = live.source_hash
    if pinned_hash and live_hash and pinned_hash == live_hash:
        return {"status": "live", "changed_fields": [], "live_snapshot": live.snapshot}
    changed = sorted({
        k for k in set(pinned_snapshot) | set(live.snapshot)
        if pinned_snapshot.get(k) != live.snapshot.get(k)
    })
    if not changed and pinned_hash == live_hash:
        return {"status": "live", "changed_fields": [], "live_snapshot": live.snapshot}
    return {"status": "changed", "changed_fields": changed,
            "live_snapshot": live.snapshot, "live_version": live.source_version}
