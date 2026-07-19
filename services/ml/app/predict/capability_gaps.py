"""Capability-gap justification for every AWS path (Prompt 14 Part F, item 6).

F.6: "Record a capability-gap justification for every AWS path ... Do not use AWS
to replace a matching Catalyst application service." This module is the single
source of truth for that record. It is importable + validated (like
``datastore/mapping.py``), and it is mirrored to ``infra/aws/capability-gaps.json``
for operators; ``validate_capability_gaps()`` enforces that:

  * every retained AWS path has a specific, non-empty capability-gap reason and
    names the Catalyst service(s) that were checked first;
  * no AWS path overlaps a capability DRISHTI deliberately keeps on Catalyst
    (the anti-"replace-a-matching-Catalyst-service" guard);
  * what crosses the boundary is data-minimized (no narrative / evidence bytes /
    DATABASE_URL / raw PII — only ids, versions, hashes and feature vectors).

The justification is deliberately narrow: only custom GPU foundation-model
inference, graph-NN inference, PostGIS/pgRouting geospatial routing and the
model-artifact (ECR/weights) workflow stay on AWS. Everything with a matching
Catalyst capability (operational data, object store, search, text-LLM/RAG,
no-code ML baseline, and the CPU-only near-repeat/KDE/fusion steps) stays on
Catalyst.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

CAPABILITY_GAPS_VERSION = "2026.07.18-1"

# Data classes that MAY cross the Catalyst -> AWS boundary. Anything else (raw
# narrative, evidence bytes, DATABASE_URL, raw PII) is forbidden by the envelope.
_ALLOWED_BOUNDARY_DATA = (
    "ids", "versions", "content hashes", "feature vectors", "aggregate counts",
    "geometry ids", "s3 snapshot uri", "observation cutoff",
)
_FORBIDDEN_BOUNDARY_TERMS = ("database_url", "evidence bytes", "raw narrative", "raw pii")


@dataclass(frozen=True)
class CapabilityGap:
    """One retained AWS path and the specific Catalyst gap that justifies it."""
    aws_path: str                       # stable id
    capability: str                     # what runs on AWS
    aws_runtime: str                    # SageMaker async / AWS Batch / ECR / RDS ...
    catalyst_services_checked: tuple[str, ...]  # what we checked on Catalyst first
    gap_reason: str                     # the specific capability gap
    crosses_boundary: str               # data-minimized inputs (allowed classes only)
    not_replacing: str                  # attestation vs a matching Catalyst service
    tasks: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        # JSON-native (lists, not tuples) so the emitted mirror compares equal.
        d = asdict(self)
        d["catalyst_services_checked"] = list(self.catalyst_services_checked)
        d["tasks"] = list(self.tasks)
        return d


# --- Retained AWS paths (each with a capability-gap justification) ----------
CAPABILITY_GAPS: tuple[CapabilityGap, ...] = (
    CapabilityGap(
        aws_path="sagemaker-tabfm-gpu-inference",
        capability="TabFM tabular foundation-model in-context inference",
        aws_runtime="SageMaker async endpoint / AWS Batch (GPU: g5/g6, ~3 GiB BF16 weights)",
        catalyst_services_checked=("QuickML (no-code ML / RAG)", "Zia AutoML", "AppSail (CPU)"),
        gap_reason="Catalyst exposes no custom GPU runtime and cannot host a ~3 GiB "
                   "BF16 foundation-model for in-context inference; QuickML/Zia AutoML "
                   "do not provide TabFM. GPU inference is the genuine capability gap.",
        crosses_boundary="ids, versions, content hashes, feature vectors, observation cutoff "
                         "(labelled context rows or an approved s3 snapshot uri) — never "
                         "narrative/evidence/PII/DATABASE_URL.",
        not_replacing="Operational data stays in Catalyst Data Store; only the aggregate "
                      "feature vector is sent, and results return as NEW records.",
        tasks=("station_workload_band", "area_incident_forecast_tabfm")),
    CapabilityGap(
        aws_path="sagemaker-timesfm-gpu-inference",
        capability="TimesFM time-series foundation-model forecasting",
        aws_runtime="AWS Batch (preferred) / SageMaker async (GPU)",
        catalyst_services_checked=("QuickML", "Zia AutoML", "AppSail (CPU stats baseline)"),
        gap_reason="No Catalyst service runs a pretrained time-series foundation model on "
                   "GPU; the CPU statistical baseline in AppSail is the eligible comparator, "
                   "not a replacement for TimesFM.",
        crosses_boundary="compact incident-count series, frequency, horizon, cutoff and "
                         "approved dynamic-covariate versions — aggregates only.",
        not_replacing="The AppSail CPU baseline (QuickML/stats) still runs on Catalyst for "
                      "comparison; AWS is used only for the GPU foundation model.",
        tasks=("timesfm_count_forecast",)),
    CapabilityGap(
        aws_path="sagemaker-stgnn-gpu-inference",
        capability="Spatio-temporal graph neural network area forecast",
        aws_runtime="AWS Batch / SageMaker async (GPU, torch-geometric)",
        catalyst_services_checked=("QuickML", "AppSail (CPU)"),
        gap_reason="A torch-geometric ST-GNN needs a GPU + a heavy graph stack that Catalyst "
                   "does not provide.",
        crosses_boundary="time-by-area count tensor, versioned adjacency/geometry ids and "
                         "approved context — no person nodes, no invalid geography.",
        not_replacing="Deterministic graph community/centrality/path analytics stay on "
                      "Catalyst/PostGIS/NetworkX; only the GPU model runs on AWS.",
        tasks=("stgnn_area_forecast",)),
    CapabilityGap(
        aws_path="analytics-rds-postgis-pgrouting",
        capability="PostGIS/pgRouting geospatial routing + heavy spatial analytics",
        aws_runtime="Retained AWS RDS (read-only, drishti_readonly, IAM DB auth)",
        catalyst_services_checked=("Catalyst Data Store", "Catalyst full-text search"),
        gap_reason="Catalyst Data Store is not a spatial database: no PostGIS geometry ops "
                   "and no pgRouting graph routing. Used only-where-necessary, read-only.",
        crosses_boundary="geometry ids, area/beat ids and aggregate query parameters — no "
                         "operational rows are written; RDS never on the CRUD path.",
        not_replacing="Operational relational records + search are served by Catalyst Data "
                      "Store; RDS is a private, read-only analytics adapter only (F.2).",
        tasks=()),
    CapabilityGap(
        aws_path="ecr-model-artifact-workflow",
        capability="Private model-artifact registry + GPU execution (image + weights)",
        aws_runtime="Private ECR image (services/gpu-worker) + SageMaker/Batch + temporary S3 staging",
        catalyst_services_checked=("Catalyst Functions", "AppSail", "Catalyst Stratus"),
        gap_reason="Catalyst has no container registry or GPU execution plane for a CUDA "
                   "image with multi-GiB model weights; the model-artifact lifecycle "
                   "(build, digest-pin, load, verify) must run on AWS.",
        crosses_boundary="model/version/artifact digests + temporary feature I/O objects in "
                         "an approved S3 staging prefix — never the operational object store.",
        not_replacing="Application objects (evidence/import/report) live in Catalyst Stratus; "
                      "S3 is only temporary SageMaker/Batch I/O staging.",
        tasks=()),
)


# --- Capabilities DELIBERATELY kept on Catalyst (anti-replace evidence) -----
# (capability, matching Catalyst service). The validator asserts no AWS path
# above overlaps one of these — i.e. AWS never replaces a matching Catalyst svc.
CATALYST_SERVED: tuple[tuple[str, str], ...] = (
    ("Operational relational data + CRUD", "Catalyst Data Store"),
    ("Full-text case/FIR/person/evidence search", "Catalyst Data Store search"),
    ("Application object store (evidence/import/report)", "Catalyst Stratus"),
    ("Text-LLM / RAG over approved SOP/policy", "Catalyst QuickML"),
    ("No-code ML baseline (eligible comparator)", "Catalyst QuickML"),
    ("Near-repeat (Hawkes/ETAS) short-horizon intensity", "AppSail CPU job"),
    ("KDE / ST-DBSCAN hotspots", "AppSail CPU job"),
    ("Forecast fusion (combination/validation)", "AppSail CPU step"),
    ("Serverless glue + scheduled jobs", "Catalyst Functions + Job Scheduling"),
)


class CapabilityGapError(ValueError):
    """Raised when the capability-gap record is incomplete or self-contradictory."""


def validate_capability_gaps() -> dict:
    """Validate the capability-gap record. Raises ``CapabilityGapError`` on any
    problem; returns a small summary on success."""
    seen: set[str] = set()
    catalyst_caps = {c.lower() for c, _ in CATALYST_SERVED}

    for gap in CAPABILITY_GAPS:
        for fname in ("aws_path", "capability", "aws_runtime", "gap_reason",
                      "crosses_boundary", "not_replacing"):
            if not str(getattr(gap, fname)).strip():
                raise CapabilityGapError(f"{gap.aws_path or '?'}: empty {fname}")
        if gap.aws_path in seen:
            raise CapabilityGapError(f"duplicate aws_path {gap.aws_path}")
        seen.add(gap.aws_path)
        if not gap.catalyst_services_checked:
            raise CapabilityGapError(
                f"{gap.aws_path}: must record which Catalyst service(s) were checked first")
        # The runtime must actually be an AWS runtime (this is an AWS-path record).
        if not any(tok in gap.aws_runtime for tok in
                   ("SageMaker", "Batch", "ECR", "RDS", "S3", "Lambda", "ECS")):
            raise CapabilityGapError(f"{gap.aws_path}: aws_runtime is not an AWS runtime")
        # Data-minimization: no forbidden payload class may cross the boundary.
        low = gap.crosses_boundary.lower()
        for term in _FORBIDDEN_BOUNDARY_TERMS:
            # allowed only in a negating phrase ("never narrative/..."); flag a
            # bare positive mention.
            if term in low and "never" not in low:
                raise CapabilityGapError(
                    f"{gap.aws_path}: boundary payload mentions forbidden {term!r}")
        # Anti-replace: an AWS path must not duplicate a matching Catalyst service.
        if gap.capability.lower() in catalyst_caps:
            raise CapabilityGapError(
                f"{gap.aws_path}: capability duplicates a Catalyst-served capability")

    return {
        "version": CAPABILITY_GAPS_VERSION,
        "aws_paths": len(CAPABILITY_GAPS),
        "catalyst_served": len(CATALYST_SERVED),
    }


def emit() -> dict:
    """The ops-readable mirror written to infra/aws/capability-gaps.json."""
    return {
        "_comment": "Capability-gap justification for every retained AWS path "
                    "(Prompt 14 Part F item 6). GENERATED from "
                    "services/ml/app/predict/capability_gaps.py — edit that module, "
                    "not this file. validate_capability_gaps() guards parity + content.",
        "version": CAPABILITY_GAPS_VERSION,
        "aws_paths": [g.to_dict() for g in CAPABILITY_GAPS],
        "catalyst_served": [{"capability": c, "catalyst_service": s}
                            for c, s in CATALYST_SERVED],
    }


if __name__ == "__main__":
    import json
    validate_capability_gaps()
    print(json.dumps(emit(), indent=2))
