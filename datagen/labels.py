"""Governed features + leakage-safe aggregate labels (ML separation).

Implements the safe bridge between verified inputs and any model:
  * FeatureDefinition/SchemaVersion — approved, versioned, protected-attribute-free.
  * FeatureSnapshot — per-area aggregates computed ONLY from pre-cutoff data,
    with source versions + observation cutoff + content hash (immutable).
  * OutcomeLabel — the aggregate next-period incident band, derived ONLY from
    post-cutoff registrations (independent of the feature formula -> no leakage).
  * TrainingDatasetSnapshot — reproducible split metadata.

No protected/restricted attribute (caste/religion/gender/juvenile) is used.
"""
from __future__ import annotations

import hashlib
import json
from typing import Dict

import numpy as np

from .db import Arr, Json
from . import v2common as C

C.register("FeatureDefinition", [
    "FeatureDefinitionID", "Name", "ValueType", "Description", "SourceTable",
    "SourceField", "SourceEvent", "Transformation", "WindowSpec",
    "ObservationCutoffBehavior", "Sensitivity", "AllowedTasks", "MissingPolicy",
    "StalePolicy", "Owner", "ApprovalStatus",
])
C.register("FeatureSchemaVersion", [
    "FeatureSchemaVersionID", "SchemaName", "Version", "FeatureDefinitionIDs",
    "Task", "Status", "ApprovedByActor", "ApprovedAt",
])
C.register("TrainingDatasetSnapshot", [
    "TrainingDatasetSnapshotID", "Name", "FeatureSchemaVersionID", "TimeSplit",
    "GeoSplit", "RowCount", "ObservationCutoff", "LabelWindowStart",
    "LabelWindowEnd", "Exclusions", "ApprovalStatus", "ContentHash",
])
C.register("FeatureSnapshot", [
    "FeatureSchemaVersionID", "SubjectKind", "SubjectRefID", "ObservationCutoff",
    "Values", "SourceVersions", "QualityStatus", "ContentHash",
])
C.register("OutcomeLabel", [
    "CaseMasterID", "SubjectKind", "SubjectRefID", "LabelName", "LabelValue",
    "OutcomeObservationID", "ObservationCutoff", "LabelWindowStart",
    "LabelWindowEnd", "SplitTag",
])

TASK = "area_incident_forecast"

_FEATURES = [
    ("area_incident_count_precutoff", "numeric", "CaseMaster", "CaseMasterID",
     "count of registered incidents in the district up to the observation cutoff",
     "count", "[start, cutoff]"),
    ("area_night_share_precutoff", "numeric", "CaseEvent", None,
     "share of pre-cutoff incidents occurring at night", "ratio", "[start, cutoff]"),
    ("area_cyber_share_precutoff", "numeric", "CaseMaster", "CrimeMajorHeadID",
     "share of pre-cutoff incidents that are economic/cyber", "ratio", "[start, cutoff]"),
    ("area_prioryear_count", "numeric", "CaseMaster", "CaseMasterID",
     "prior full-year incident count", "count", "prior_year"),
]


def _dts(d) -> str:
    return d.strftime("%Y-%m-%d %H:%M:%S+00")


def _hash(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def build_features_and_labels(world: C.World) -> None:
    w = world
    cutoff = world.observation_cutoff
    lw_start = world.label_window_start
    lw_end = world.label_window_end

    # 1. FeatureDefinitions (approved, no protected attributes).
    fd_ids = []
    for name, vtype, stab, sfield, desc, transf, window in _FEATURES:
        fid = w.next_id("FeatureDefinition")
        fd_ids.append(fid)
        w.add("FeatureDefinition", (
            fid, name, vtype, desc, stab, sfield, None, transf, window,
            "strict_pre_cutoff", "normal", Arr([TASK, "workload_band"]),
            "null_ok", "invalidate_on_source_change", "analyst_demo", "approved",
        ))

    # 2. Approved FeatureSchemaVersion.
    fsv_id = w.next_id("FeatureSchemaVersion")
    w.add("FeatureSchemaVersion", (
        fsv_id, "area_forecast_features", "1", Json(fd_ids), TASK, "approved",
        "analyst_demo", _dts(cutoff),
    ))

    # 3. Per-district FeatureSnapshot (pre-cutoff only) + leakage-safe label.
    stats: Dict[int, dict] = world.area_stats
    post_counts = np.array([max(0, s.get("post", 0)) for s in stats.values()]) \
        if stats else np.array([0])
    if post_counts.size and post_counts.max() > 0:
        q1, q2 = np.quantile(post_counts, [0.34, 0.67])
    else:
        q1 = q2 = 0

    def band(n: int) -> str:
        if n <= q1:
            return "low"
        if n <= q2:
            return "medium"
        return "high"

    # deterministic geographic holdout: ~20% of districts
    holdout = {did for i, did in enumerate(sorted(stats)) if i % 5 == 0}

    for did, s in stats.items():
        pre = s.get("pre", 0)
        total = max(1, s.get("total", 1))
        values = {
            "area_incident_count_precutoff": pre,
            "area_night_share_precutoff": round(s.get("night", 0) / total, 4),
            "area_cyber_share_precutoff": round(s.get("cyber", 0) / total, 4),
            "area_prioryear_count": s.get("prioryear", pre),
        }
        source_versions = {"case_source_system": w.source_system.get("FIR_FORM"),
                           "as_of": _dts(cutoff)}
        w.add("FeatureSnapshot", (
            fsv_id, "area_district", str(did), _dts(cutoff), Json(values),
            Json(source_versions), "ok", _hash(values),
        ))
        split = "geo_holdout" if did in holdout else (
            "test" if did % 4 == 0 else "train")
        w.add("OutcomeLabel", (
            None, "area_district", str(did), "next_period_incident_band",
            band(s.get("post", 0)), None, _dts(cutoff), _dts(lw_start),
            _dts(lw_end), split,
        ))
        w.cover("feature_snapshot")
        w.cover("outcome_label")

    # 4. TrainingDatasetSnapshot (reproducible splits).
    w.add("TrainingDatasetSnapshot", (
        w.next_id("TrainingDatasetSnapshot"), "area_forecast_v1", fsv_id,
        Json({"train_end": _dts(cutoff), "val_frac": 0.2}),
        Json({"geo_holdout_districts": sorted(holdout)}),
        len(stats), _dts(cutoff), _dts(lw_start), _dts(lw_end),
        Json({"exclude": "protected_attributes"}), "approved",
        _hash({"schema": fsv_id, "n": len(stats)}),
    ))
    w.feature_schema_version_id = fsv_id
