"""Input-to-feature-to-model routing contract (Prompt 14 G.1).

The cardinal rule: there is NO generic "every input -> every model" path. Model
routing is decided by an approved task, FeatureSchemaVersion, subject type,
observation cutoff and data-quality state. Drafts, submissions, raw evidence
bytes and unreviewed links MUST NOT create a PredictionRequest or call AWS.

This module is pure/deterministic and has no I/O so it is trivially testable and
can be reused by the intake, evidence, import and feature-snapshot handlers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .envelope import ModelTask


class InputEvent(str, Enum):
    """The canonical lifecycle/ingestion events the app can emit."""
    FIR_DRAFT_SAVED = "fir_draft_saved"                 # create/autosave/edit
    FIR_SUBMITTED = "fir_submitted"                     # submitted for review
    FIR_APPROVED = "fir_approved"                       # supervisor-approved canonical
    CASE_CORRECTION_APPROVED = "case_correction_approved"
    STRUCTURED_RECORD_APPROVED = "structured_record_approved"  # chargesheet/court/lab/...
    EVIDENCE_UPLOADED = "evidence_uploaded"             # raw bytes to Stratus
    EVIDENCE_METADATA_REVIEWED = "evidence_metadata_reviewed"
    CSV_JSON_IMPORT_ROW_APPROVED = "csv_json_import_row_approved"
    STRUCTURED_IMPORT_REVIEWED = "structured_import_reviewed"  # CDR/device/media/financial
    CONTEXT_SOURCE_APPROVED = "context_source_approved"        # weather/holiday/event/area
    SOP_KB_RELEASED = "sop_kb_released"                 # approved policy text
    HAZARD_RESOURCE_SNAPSHOT = "hazard_resource_snapshot"      # Prompt 17


@dataclass(frozen=True)
class RoutingDecision:
    """The outcome of routing a single input event."""
    event: InputEvent
    invokes_model: bool
    tasks: tuple[ModelTask, ...] = field(default_factory=tuple)
    immediate: tuple[ModelTask, ...] = field(default_factory=tuple)   # run now (eligible)
    coalesced: tuple[ModelTask, ...] = field(default_factory=tuple)   # next approved run
    person_level_forbidden: bool = True
    reason: str = ""

    def as_dict(self) -> dict:
        return {
            "event": self.event.value,
            "invokes_model": self.invokes_model,
            "tasks": [t.value for t in self.tasks],
            "immediate": [t.value for t in self.immediate],
            "coalesced": [t.value for t in self.coalesced],
            "person_level_forbidden": self.person_level_forbidden,
            "reason": self.reason,
        }


# The single source of truth for routing. Events not present here default to
# "no model" (fail-safe): an unknown event never triggers a prediction.
_NO_MODEL = {
    InputEvent.FIR_DRAFT_SAVED: "Draft only — validate and save; no PredictionRequest, no AWS.",
    InputEvent.FIR_SUBMITTED: "Submitted, not canonical — review/audit state only; no prediction.",
    InputEvent.EVIDENCE_UPLOADED: (
        "Quarantined bytes — hash/type/size/malware only; no OCR/extraction, no prediction."),
    InputEvent.SOP_KB_RELEASED: (
        "Approved SOP/policy text routes to QuickML RAG, not the tabular model plane."),
}


@dataclass(frozen=True)
class RoutingContext:
    """Facts the router needs. All must come from APPROVED canonical state."""
    event: InputEvent
    subject_kind: str = "station"
    has_verified_geography: bool = False
    has_verified_time: bool = False
    has_verified_head: bool = False
    changed_source_fields: frozenset[str] = frozenset()
    near_repeat_eligible: bool = False
    metadata_schema_lists_fields: bool = False


def route(ctx: RoutingContext) -> RoutingDecision:
    """Decide the model route for an input event. Deterministic; no side effects."""
    ev = ctx.event

    if ev in _NO_MODEL:
        return RoutingDecision(ev, invokes_model=False, reason=_NO_MODEL[ev])

    if ev == InputEvent.FIR_APPROVED:
        # Requires verified structured geography/time/head to route at all.
        if not (ctx.has_verified_geography and ctx.has_verified_time and ctx.has_verified_head):
            return RoutingDecision(
                ev, invokes_model=False,
                reason="Approved FIR missing verified geography/time/head — no model route.")
        immediate = (ModelTask.NEAR_REPEAT_INTENSITY,) if ctx.near_repeat_eligible else ()
        coalesced = (ModelTask.STATION_WORKLOAD_BAND, ModelTask.AREA_INCIDENT_FORECAST_TABFM)
        return RoutingDecision(
            ev, invokes_model=bool(immediate or coalesced),
            tasks=immediate + coalesced, immediate=immediate, coalesced=coalesced,
            reason=("Approved canonical FIR -> aggregate near-repeat (eligible) + coalesced "
                    "workload/area-forecast. Never scores complainant/accused/victim/FIR."))

    if ev == InputEvent.CASE_CORRECTION_APPROVED:
        # Rebuild only schemas whose source fields changed.
        if not ctx.changed_source_fields:
            return RoutingDecision(
                ev, invokes_model=False,
                reason="Correction changed no model source fields — supersede snapshots only.")
        coalesced = (ModelTask.STATION_WORKLOAD_BAND,)
        return RoutingDecision(
            ev, invokes_model=True, tasks=coalesced, coalesced=coalesced,
            reason="Approved correction -> rebuild only affected schemas; supersede priors.")

    if ev == InputEvent.STRUCTURED_RECORD_APPROVED:
        coalesced = (ModelTask.STATION_WORKLOAD_BAND,)
        return RoutingDecision(
            ev, invokes_model=True, tasks=coalesced, coalesced=coalesced,
            reason=("Reviewed structured record -> workload/backlog features / graph refresh; "
                    "a later outcome is a training label only after label-window closure."))

    if ev == InputEvent.EVIDENCE_METADATA_REVIEWED:
        if not ctx.metadata_schema_lists_fields:
            return RoutingDecision(
                ev, invokes_model=False,
                reason="Reviewed metadata -> graph/index refresh only (no schema lists these fields).")
        coalesced = (ModelTask.STATION_WORKLOAD_BAND,)
        return RoutingDecision(
            ev, invokes_model=True, tasks=coalesced, coalesced=coalesced,
            reason="Reviewed metadata feeds a schema that explicitly lists these fields.")

    if ev == InputEvent.CSV_JSON_IMPORT_ROW_APPROVED:
        coalesced = (ModelTask.STATION_WORKLOAD_BAND, ModelTask.AREA_INCIDENT_FORECAST_TABFM)
        return RoutingDecision(
            ev, invokes_model=True, tasks=coalesced, coalesced=coalesced,
            reason="Accepted import rows emit the same canonical events; coalesced into bounded jobs.")

    if ev == InputEvent.STRUCTURED_IMPORT_REVIEWED:
        return RoutingDecision(
            ev, invokes_model=False,
            reason=("CDR/device/media/financial -> graph/community/similarity workflows; a "
                    "prediction model only when an approved non-person aggregate schema permits."))

    if ev == InputEvent.CONTEXT_SOURCE_APPROVED:
        coalesced = (ModelTask.TIMESFM_COUNT_FORECAST, ModelTask.STGNN_AREA_FORECAST,
                     ModelTask.FORECAST_FUSION)
        return RoutingDecision(
            ev, invokes_model=True, tasks=coalesced, coalesced=coalesced,
            reason="Approved context -> TimesFM/ST-GNN/fused forecast only; reject stale/post-cutoff.")

    if ev == InputEvent.HAZARD_RESOURCE_SNAPSHOT:
        # Owned by Prompt 17 — separate task/schema/model; never policing TabFM.
        return RoutingDecision(
            ev, invokes_model=False,
            reason="Hazard/resource routing is owned by Prompt 17 (disabled scaffold here).")

    return RoutingDecision(ev, invokes_model=False, reason="Unknown event — fail-safe: no model.")


def build_idempotency_key(task: ModelTask, subject: str, cutoff: str,
                          feature_schema_version: str, model_version: str,
                          source_version_hash: str) -> str:
    """The canonical idempotency key used across dispatch, dedup and DLQ."""
    return ":".join((task.value, subject, cutoff, feature_schema_version,
                     model_version, source_version_hash))
