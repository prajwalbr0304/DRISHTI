"""Model / version / feature lineage -> Catalyst Data Store rows (Prompt 14 G item 5).

"Store model/version/feature lineage and validated predictions in Data Store. The
AWS runtime never writes to the browser and does not become the authoritative
application database." This module builds the Data Store rows that carry that
lineage, keyed by a stable ``ExternalID`` so persistence is idempotent (an
upsert-by-ExternalID updates in place, never duplicates).

The rows are:
  * ``FeatureSnapshot`` — the immutable, hashed input the model saw.
  * ``PredictionRequest`` — the governed request (idempotency key + the fields
    ``validation.ResultExpectation`` needs to re-validate an async result).
  * ``PredictionResult`` — the VALIDATED result written back as a NEW record. Its
    provenance says ``authoritative_store = catalyst_data_store`` and
    ``result_source = aws_model_plane`` so it is unambiguous that AWS produced a
    result record, not an authoritative edit.

Nothing here calls AWS or the browser; it only shapes dicts for the Data Store
repository (``datastore/repository.py``).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Optional

from .envelope import PredictionResultEnvelope

# Deployed operational tables (Catalyst Data Store). Same names as the retained
# AWS RDS analytics schema so the mapping/import configs line up.
FEATURE_SNAPSHOT_TABLE = "FeatureSnapshot"
PREDICTION_REQUEST_TABLE = "PredictionRequest"
PREDICTION_RESULT_TABLE = "PredictionResult"

AUTHORITATIVE_STORE = "catalyst_data_store"
RESULT_SOURCE = "aws_model_plane"


def _short_hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def content_hash(obj: Any) -> str:
    """Stable content hash of an arbitrary JSON-able object (sorted keys)."""
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def subject_token(subject_kind: str, subject_ids: list[str]) -> str:
    """A compact, stable token identifying the subject(s) of a snapshot."""
    ids = [str(x) for x in subject_ids]
    if len(ids) == 1:
        return f"{subject_kind}:{ids[0]}"
    return f"{subject_kind}:batch:{_short_hash(','.join(sorted(ids)))}:{len(ids)}"


@dataclass(frozen=True)
class PredictionLineage:
    """The full lineage carried on every governed prediction record."""
    request_id: str
    idempotency_key: str
    task: str
    subject_kind: str
    subject_ids: tuple[str, ...]
    feature_schema_version: str
    feature_schema_digest: str
    model_version: str
    observation_cutoff: str
    source_version_hash: str
    dispatch_mode: str
    requested_backend: str
    envelope_version: str
    model_artifact_digest: Optional[str] = None
    context_version: Optional[str] = None
    context_digest: Optional[str] = None
    training_dataset_snapshot: Optional[str] = None
    actual_backend: Optional[str] = None
    actual_device: Optional[str] = None
    extra: dict[str, Any] = field(default_factory=dict)

    # -- ExternalIDs (stable, idempotent) -----------------------------------
    def feature_snapshot_external_id(self) -> str:
        key = "|".join((self.task, subject_token(self.subject_kind, list(self.subject_ids)),
                        self.observation_cutoff, self.feature_schema_version,
                        self.source_version_hash))
        return f"fs:{_short_hash(key)}"

    def prediction_request_external_id(self) -> str:
        return f"pr:{_short_hash(self.idempotency_key)}"

    def prediction_result_external_id(self) -> str:
        return f"res:{_short_hash(self.idempotency_key)}"

    def supersession_key(self) -> str:
        """Groups all predictions for the same subject + feature schema (G.4).

        Independent of ``source_version_hash`` and ``model_version`` so that a
        corrected input (new source version) for the same subject supersedes the
        prior prediction, while historical predictions are preserved."""
        return "|".join((self.task, subject_token(self.subject_kind, list(self.subject_ids)),
                         self.feature_schema_version))

    def as_provenance(self) -> dict:
        return {
            "task": self.task,
            "subject_kind": self.subject_kind,
            "subject_ids": list(self.subject_ids),
            "feature_schema_version": self.feature_schema_version,
            "feature_schema_digest": self.feature_schema_digest,
            "model_version": self.model_version,
            "model_artifact_digest": self.model_artifact_digest,
            "context_version": self.context_version,
            "training_dataset_snapshot": self.training_dataset_snapshot,
            "observation_cutoff": self.observation_cutoff,
            "source_version_hash": self.source_version_hash,
            "dispatch_mode": self.dispatch_mode,
            "requested_backend": self.requested_backend,
            "actual_backend": self.actual_backend,
            "actual_device": self.actual_device,
        }


def feature_snapshot_row(lin: PredictionLineage, *, values: dict,
                         quality_status: str = "ok") -> dict:
    """The immutable FeatureSnapshot Data Store row (the exact input the model saw)."""
    ext = lin.feature_snapshot_external_id()
    row = {
        "ExternalID": ext,
        "Task": lin.task,
        "SubjectKind": lin.subject_kind,
        "SubjectRefID": subject_token(lin.subject_kind, list(lin.subject_ids)),
        "SubjectIDs": list(lin.subject_ids),
        "ObservationCutoff": lin.observation_cutoff,
        "FeatureSchemaVersion": lin.feature_schema_version,
        "FeatureSchemaDigest": lin.feature_schema_digest,
        "SourceVersionHash": lin.source_version_hash,
        "Values": values,
        "QualityStatus": quality_status,
        "IsImmutable": True,
        "ContentHash": content_hash({"schema": lin.feature_schema_version,
                                     "subject": lin.subject_ids, "cutoff": lin.observation_cutoff,
                                     "values": values}),
    }
    return row


def prediction_request_row(lin: PredictionLineage, *, feature_snapshot_external_id: str,
                           state: str = "dispatched", n_query_rows: int = 0,
                           adapter_request_id: str = "") -> dict:
    """The governed PredictionRequest row. Carries exactly the fields
    ``validation.ResultExpectation.from_request_row`` needs to re-validate."""
    return {
        "ExternalID": lin.prediction_request_external_id(),
        "RequestID": lin.request_id,
        "IdempotencyKey": lin.idempotency_key,
        "Task": lin.task,
        "RequestedBackend": lin.requested_backend,
        "FeatureSchemaDigest": lin.feature_schema_digest,
        "QueryRowCount": int(n_query_rows),
        "EnvelopeVersion": lin.envelope_version,
        "FeatureSnapshotExternalID": feature_snapshot_external_id,
        "ModelVersion": lin.model_version,
        "DispatchMode": lin.dispatch_mode,
        "AdapterRequestID": adapter_request_id,
        "Status": state,
        # Supersession grouping (G.4): same subject+schema, any source version.
        "SupersessionKey": lin.supersession_key(),
        "SourceVersionHash": lin.source_version_hash,
        "Provenance": lin.as_provenance(),
    }


def prediction_result_row(lin: PredictionLineage, res: PredictionResultEnvelope, *,
                          request_external_id: str,
                          feature_snapshot_external_id: str) -> dict:
    """The VALIDATED PredictionResult row, written back as a NEW record. The AWS
    plane is the *source* of this record, never the authoritative store."""
    return {
        "ExternalID": lin.prediction_result_external_id(),
        "PredictionRequestExternalID": request_external_id,
        "FeatureSnapshotExternalID": feature_snapshot_external_id,
        "RequestID": res.request_id,
        "IdempotencyKey": res.idempotency_key,
        "Task": lin.task,
        "State": res.state.value,
        "ActualBackend": res.actual_backend.value if res.actual_backend else None,
        "ActualDevice": res.actual_device.value if res.actual_device else None,
        "ModelVersion": lin.model_version,
        "ModelArtifactDigest": res.model_artifact_digest,
        "FeatureSchemaDigest": res.feature_schema_digest or lin.feature_schema_digest,
        "Predictions": res.predictions,
        "Confidence": res.confidence,
        "Abstained": res.abstained,
        "RuntimeMs": res.runtime_ms,
        "GpuName": res.gpu_name,
        "Warnings": res.warnings,
        "Provenance": lin.as_provenance(),
        # Supersession + staleness (G.4). A fresh result starts live; a later
        # corrected input marks it stale (preserved, never deleted).
        "SupersessionKey": lin.supersession_key(),
        "SourceVersionHash": lin.source_version_hash,
        "IsStale": False,
        "StaleReason": None,
        "SupersededByExternalID": None,
        # Unambiguous ownership: Data Store is authoritative; AWS only produced it.
        "AuthoritativeStore": AUTHORITATIVE_STORE,
        "ResultSource": RESULT_SOURCE,
        "Validated": True,
    }
