"""Leakage-safe feature-snapshot builder (Phase 10).

Builds an IMMUTABLE ``FeatureSnapshot`` for a subject (e.g. a district) from
ONLY the validated canonical records that were known at the observation cutoff:

  * reads an APPROVED ``FeatureSchemaVersion`` — a draft schema cannot produce a
    prediction snapshot, so a new input never affects a model until it is
    explicitly added to an approved schema;
  * computes each feature STRICTLY from pre-cutoff data (``CrimeRegisteredDate <=
    cutoff``) — post-cutoff records (and outcome labels) can never leak in;
  * refuses to include any protected/restricted feature unless the schema's task
    is on the separately-reviewed aggregate allow-list (empty in the hackathon);
  * records the source system + observation cutoff + pre-cutoff row count in
    ``SourceVersions`` and a deterministic SHA-256 ``ContentHash`` so the exact
    snapshot is reproducible;
  * writes the row once — migration 017's trigger then makes it immutable.

Aggregate, non-protected area features only. Mirrors the feature semantics the
datagen catalogue documents (night = incident hour >= 21 or < 5; cyber =
'Economic & Cyber Crime' major head; pre = registered on/before the cutoff).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from typing import Optional

from psycopg2.extras import Json

from ..cases import analytics_policy

# Tasks for which a separately-reviewed aggregate schema may include a
# protected/restricted feature. EMPTY for the hackathon: protected attributes
# (caste/religion/gender/juvenile/...) are excluded from every prediction schema.
AGGREGATE_PROTECTED_PERMITTED_TASKS: set[str] = set()

# The area features this builder knows how to compute from canonical records.
_KNOWN_FEATURES = {
    "area_incident_count_precutoff",
    "area_night_share_precutoff",
    "area_cyber_share_precutoff",
    "area_prioryear_count",
}


class BuilderError(Exception):
    pass


class SchemaNotApproved(BuilderError):
    pass


class ProtectedFeatureError(BuilderError):
    pass


class SubjectNotFound(BuilderError):
    pass


def _hash(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def _iso(d) -> Optional[str]:
    return d.isoformat() if isinstance(d, (dt.date, dt.datetime)) else (str(d) if d is not None else None)


# ---------------------------------------------------------------------------
# Schema / feature-definition loading + the protected-feature guard
# ---------------------------------------------------------------------------
def _load_schema(conn, feature_schema_version_id: int) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "FeatureSchemaVersionID","SchemaName","Version","FeatureDefinitionIDs",'
            '"Task","Status" FROM "FeatureSchemaVersion" WHERE "FeatureSchemaVersionID"=%s',
            (feature_schema_version_id,))
        r = cur.fetchone()
    if not r:
        raise BuilderError(f"FeatureSchemaVersion {feature_schema_version_id} not found.")
    ids = r[3] if isinstance(r[3], list) else json.loads(r[3] or "[]")
    return {"id": int(r[0]), "schema_name": r[1], "version": r[2],
            "feature_definition_ids": [int(x) for x in ids], "task": r[4], "status": r[5]}


def _load_definitions(conn, feature_definition_ids: list[int]) -> list[dict]:
    if not feature_definition_ids:
        return []
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "FeatureDefinitionID","Name","Sensitivity","ApprovalStatus","MissingPolicy" '
            'FROM "FeatureDefinition" WHERE "FeatureDefinitionID" = ANY(%s)',
            (feature_definition_ids,))
        by_id = {int(r[0]): {"id": int(r[0]), "name": r[1], "sensitivity": r[2],
                             "approval_status": r[3], "missing_policy": r[4]}
                 for r in cur.fetchall()}
    # preserve the schema's declared order
    return [by_id[i] for i in feature_definition_ids if i in by_id]


def assert_no_protected_features(task: Optional[str], definitions: list[dict]) -> None:
    """Block protected/restricted features unless the task is on the reviewed
    aggregate allow-list. Raises ProtectedFeatureError otherwise."""
    if task in AGGREGATE_PROTECTED_PERMITTED_TASKS:
        return
    bad = [d["name"] for d in definitions if d["sensitivity"] in ("protected", "restricted")]
    if bad:
        raise ProtectedFeatureError(
            "Protected/restricted feature(s) may not enter a prediction schema for "
            f"task '{task}': {', '.join(bad)}.")


# ---------------------------------------------------------------------------
# Canonical pre-cutoff area aggregates (leakage-safe)
# ---------------------------------------------------------------------------
def _default_cutoff(conn) -> dt.datetime:
    from ..cases import casedata

    with conn.cursor() as cur:
        cur.execute(
            'SELECT max(cm."CrimeRegisteredDate") FROM "CaseMaster" cm '
            f'WHERE {casedata.analytics_eligible_sql("cm")}')
        r = cur.fetchone()
    latest = r[0] if r and r[0] else dt.datetime.now(dt.timezone.utc)
    if isinstance(latest, dt.date) and not isinstance(latest, dt.datetime):
        latest = dt.datetime(latest.year, latest.month, latest.day, tzinfo=dt.timezone.utc)
    return latest - dt.timedelta(days=180)


def _district_area_stats(conn, district_id: int, cutoff) -> dict:
    """Pre-cutoff canonical aggregates for one district. Reads only validated
    canonical cases (those with a current CaseVersion) registered on/before the
    observation cutoff — post-cutoff rows can never contribute (no leakage)."""
    from ..cases import casedata

    prior_start = cutoff - dt.timedelta(days=365)
    with conn.cursor() as cur:
        cur.execute(
            'WITH cyber AS (SELECT "CrimeHeadID" FROM "CrimeHead" '
            "WHERE \"CrimeGroupName\" = 'Economic & Cyber Crime') "
            'SELECT count(*) AS total_pre, '
            'count(*) FILTER (WHERE EXTRACT(HOUR FROM cm."IncidentFromDate") >= 21 '
            '                    OR EXTRACT(HOUR FROM cm."IncidentFromDate") < 5) AS night, '
            'count(*) FILTER (WHERE cm."CrimeMajorHeadID" IN (SELECT "CrimeHeadID" FROM cyber)) AS cyber, '
            'count(*) FILTER (WHERE cm."CrimeRegisteredDate" >= %s) AS prioryear '
            'FROM "CaseMaster" cm '
            'JOIN "Unit" u ON u."UnitID" = cm."PoliceStationID" '
            'WHERE u."DistrictID" = %s '
            'AND cm."CrimeRegisteredDate" IS NOT NULL '
            'AND cm."CrimeRegisteredDate" <= %s '
            f'AND {casedata.analytics_eligible_sql("cm")} '
            'AND EXISTS (SELECT 1 FROM "CaseVersion" cv '
            '            WHERE cv."CaseMasterID" = cm."CaseMasterID" AND cv."IsCurrent")',
            (prior_start, district_id, cutoff))
        total_pre, night, cyber, prioryear = cur.fetchone()
    total_pre = int(total_pre or 0)
    return {
        "total_pre": total_pre, "night": int(night or 0), "cyber": int(cyber or 0),
        "prioryear": int(prioryear or 0),
    }


def _compute_values(names: list[str], stats: dict) -> tuple[dict, list[str]]:
    """Map the schema's (non-protected) feature names to computed values.
    Returns (values, unknown_feature_names). Unknown names -> null (missing)."""
    total = stats["total_pre"] or 0
    full = {
        "area_incident_count_precutoff": total,
        "area_night_share_precutoff": round(stats["night"] / total, 4) if total else 0.0,
        "area_cyber_share_precutoff": round(stats["cyber"] / total, 4) if total else 0.0,
        "area_prioryear_count": stats["prioryear"],
    }
    values: dict = {}
    unknown: list[str] = []
    for n in names:
        if n in full:
            values[n] = full[n]
        else:
            values[n] = None
            unknown.append(n)
    return values, unknown


def _source_system_id(conn, code: str = "FIR_FORM") -> Optional[int]:
    with conn.cursor() as cur:
        cur.execute('SELECT "SourceSystemID" FROM "SourceSystem" WHERE "Code"=%s LIMIT 1', (code,))
        r = cur.fetchone()
    return int(r[0]) if r else None


# ---------------------------------------------------------------------------
# Public builder
# ---------------------------------------------------------------------------
def build_snapshot(conn, *, feature_schema_version_id: int, subject_kind: str,
                   subject_ref_id: str, observation_cutoff: Optional[dt.datetime] = None,
                   actor: Optional[str] = None) -> dict:
    """Build + persist one immutable FeatureSnapshot. Returns the row as a dict.

    Enforces: approved schema only; protected features excluded; strictly
    pre-cutoff inputs; deterministic content hash; provenance in SourceVersions.
    """
    attestation = analytics_policy.current_attestation(conn)
    schema = _load_schema(conn, feature_schema_version_id)
    if schema["status"] != "approved":
        raise SchemaNotApproved(
            f"FeatureSchemaVersion {feature_schema_version_id} is '{schema['status']}', "
            "not 'approved' — a prediction snapshot needs an approved schema.")
    definitions = _load_definitions(conn, schema["feature_definition_ids"])
    assert_no_protected_features(schema["task"], definitions)   # protected-feature guard

    cutoff = observation_cutoff or _default_cutoff(conn)

    if subject_kind != "area_district":
        raise BuilderError(f"builder supports subject_kind 'area_district' (got '{subject_kind}').")
    district_id = int(subject_ref_id)
    with conn.cursor() as cur:
        cur.execute('SELECT "DistrictName" FROM "District" WHERE "DistrictID"=%s', (district_id,))
        if cur.fetchone() is None:
            raise SubjectNotFound(f"District {district_id} not found.")

    stats = _district_area_stats(conn, district_id, cutoff)
    names = [d["name"] for d in definitions]
    values, unknown = _compute_values(names, stats)
    quality = "partial" if unknown else "ok"

    source_versions = analytics_policy.stamp({
        "canonical_layer": "CaseVersion",
        "case_source_system_id": _source_system_id(conn),
        "as_of": _iso(cutoff),
        "n_pre_cutoff_cases": stats["total_pre"],
        "feature_schema_version_id": feature_schema_version_id,
    }, attestation)
    content_hash = _hash({
        "schema": feature_schema_version_id,
        "subject": [subject_kind, subject_ref_id],
        "cutoff": _iso(cutoff),
        "values": values,
        "source_versions": source_versions,
    })
    analytics_policy.require_supplied_current(conn, attestation, "generic feature snapshot")

    with conn.cursor() as cur:
        cur.execute(
            'INSERT INTO "FeatureSnapshot" ("FeatureSchemaVersionID","SubjectKind","SubjectRefID",'
            '"ObservationCutoff","Values","SourceVersions","QualityStatus","ContentHash",'
            '"IsImmutable","BuiltByActor") '
            'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,TRUE,%s) RETURNING "FeatureSnapshotID","CreatedAt"',
            (feature_schema_version_id, subject_kind, subject_ref_id, cutoff, Json(values),
             Json(source_versions), quality, content_hash, actor))
        snap_id, created_at = cur.fetchone()

    return {
        "feature_snapshot_id": int(snap_id),
        "feature_schema_version_id": feature_schema_version_id,
        "subject_kind": subject_kind, "subject_ref_id": subject_ref_id,
        "observation_cutoff": _iso(cutoff), "values": values,
        "source_versions": source_versions, "quality_status": quality,
        "content_hash": content_hash, "is_immutable": True,
        "unknown_features": unknown, "built_by_actor": actor,
        "created_at": _iso(created_at),
    }
