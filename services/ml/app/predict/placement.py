"""ML / RAG model-placement + regional-availability source of truth (Prompt 14 G.1/G.2).

Part G decides WHERE each ML/RAG capability runs, and records the verified
regional availability of the Catalyst services that could otherwise host it. It
is the companion to ``capability_gaps.py`` (which justifies every *AWS* path):
this module is the full placement map across Catalyst **and** AWS, so an operator
can see, for every model/assistant, the exact runtime and the reason.

The non-negotiable placement rules Part G enforces (validated below):

  * **QuickML** hosts every enabled text-LLM / RAG / knowledge-base capability
    AND an eligible no-code ML baseline (G item 1). RAG/no-code never go to AWS
    or a third-party service.
  * **Zia AutoML** is used ONLY if it is actually exposed in this India-DC
    project; it is currently **UNAVAILABLE** in the IN DC, recorded with evidence
    (never faked as used). The fallback is the QuickML no-code baseline + the
    justified AWS TabFM path.
  * **TabFM / TimesFM / custom GPU models** run EXTERNALLY on AWS because Catalyst
    exposes no custom GPU runtime (G item 2). Private ECR image + temporary S3
    staging only for SageMaker / AWS Batch.
  * **Near-repeat (Hawkes/ETAS), KDE/ST-DBSCAN hotspots, forecast fusion and the
    statistical / GBM baselines** run on **Catalyst CPU** (AppSail) — never on an
    AWS GPU.

Like ``capability_gaps.py`` it is importable + validated and mirrored to
``infra/catalyst/ml-placement.json``; ``validate_placements()`` guards the rules
above and cross-checks the AWS-GPU engines against the capability-gap record so
the two source-of-truth modules can never drift.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum

from . import capability_gaps as cg
from .enablement import Enablement, is_task_enabled
from .envelope import ModelTask

PLACEMENT_VERSION = "2026.07.18-1"

_MODELTASK_VALUES = {t.value for t in ModelTask}


class Placement(str, Enum):
    """Where a capability actually runs."""
    CATALYST_QUICKML = "catalyst-quickml"      # QuickML RAG / no-code ML
    CATALYST_CPU = "catalyst-cpu"              # AppSail CPU (deterministic/stats)
    AWS_GPU = "aws-gpu"                         # SageMaker / AWS Batch GPU
    AWS_ANALYTICS = "aws-analytics"            # read-only PostGIS/pgRouting RDS
    UNAVAILABLE = "unavailable-in-region"      # recorded, not used


class Availability(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE_REGION = "unavailable-in-region"


# Backends that REQUIRE a GPU (must be placed on AWS_GPU, never Catalyst).
GPU_BACKENDS: frozenset[str] = frozenset({"tabfm", "timesfm", "stgnn"})
# CPU/deterministic backends that MUST stay on Catalyst (never AWS_GPU).
CPU_BACKENDS: frozenset[str] = frozenset({"hawkes", "kde", "baseline", "incontext"})


@dataclass(frozen=True)
class ModelPlacement:
    """One capability, where it runs, and why."""
    engine: str                         # stable id / model name
    capability: str                     # human-readable capability
    placement: Placement
    availability: Availability
    reason: str                         # why this placement / gap
    runtime: str                        # concrete runtime detail
    tasks: tuple[str, ...] = field(default_factory=tuple)
    backend: str = ""                   # BackendKind value where applicable
    evidence: str = ""                  # REQUIRED when availability != available
    fallback: str = ""                  # what is used instead when unavailable

    def to_dict(self) -> dict:
        d = asdict(self)
        d["placement"] = self.placement.value
        d["availability"] = self.availability.value
        d["tasks"] = list(self.tasks)
        d["enablement"] = engine_enablement(self.engine).value
        return d


# --- Demo enablement per engine (G.2 scoping) --------------------------------
# Which engines actually run in the hackathon demo vs are documented-but-deferred.
# ENABLED: TabFM workload, TimesFM, near-repeat, CPU baselines. DEFERRED: the
# separate area-forecast model, ST-GNN, fusion, KDE. OPTIONAL: QuickML (RAG +
# no-code) — on only when demonstrated. Cross-checked against enablement.py.
_ENGINE_ENABLEMENT: dict[str, Enablement] = {
    "quickml-rag": Enablement.OPTIONAL,
    "quickml-nocode-baseline": Enablement.OPTIONAL,
    "quickml-llm-serving": Enablement.OPTIONAL,
    "zia-automl": Enablement.DEFERRED,
    "google-tabfm-v1": Enablement.ENABLED,
    "timesfm-2": Enablement.ENABLED,
    "st-gnn": Enablement.DEFERRED,
    "hawkes-near-repeat": Enablement.ENABLED,
    "kde-stdbscan-hotspots": Enablement.DEFERRED,
    "forecast-fusion": Enablement.DEFERRED,
    "statistical-gbm-baselines": Enablement.ENABLED,
}


def engine_enablement(engine: str) -> Enablement:
    """The demo enablement of a placement engine (default DEFERRED if unknown)."""
    return _ENGINE_ENABLEMENT.get(engine, Enablement.DEFERRED)


# --- The placement map -------------------------------------------------------
PLACEMENTS: tuple[ModelPlacement, ...] = (
    # --- Catalyst QuickML (RAG + no-code baseline) — item 1 ------------------
    ModelPlacement(
        engine="quickml-rag",
        capability="Text-LLM / RAG / knowledge base over approved SOP/policy",
        placement=Placement.CATALYST_QUICKML, availability=Availability.AVAILABLE,
        reason="QuickML is the preferred RAG runtime in the India DC; the KB is built "
               "only from approved SOP/policy text (no case narratives/evidence bytes).",
        runtime="Catalyst QuickML RAG endpoint (app/quickml.py), disabled until "
                "DRISHTI_QUICKML_RAG_ENABLED=true",
        tasks=("sop_policy_rag",)),
    ModelPlacement(
        engine="quickml-nocode-baseline",
        capability="No-code ML baseline (eligible aggregate comparator)",
        placement=Placement.CATALYST_QUICKML, availability=Availability.AVAILABLE,
        reason="An eligible no-code tabular baseline runs on QuickML as the "
               "Catalyst-native comparator against the custom AWS model (G item 4).",
        runtime="Catalyst QuickML no-code pipeline "
                "(infra/catalyst/quickml/nocode-experiment.json)",
        tasks=("area_workload_band_baseline",)),
    # --- Prompt 19 §B: Ask DRISHTI semantic planner on QuickML LLM Serving ----
    ModelPlacement(
        engine="quickml-llm-serving",
        capability="Semantic NL->query planner (QuickML LLM serving, governed open model)",
        placement=Placement.CATALYST_QUICKML, availability=Availability.AVAILABLE,
        reason="Catalyst QuickML LLM Serving hosts a governed open model (e.g. Qwen 2.5 "
               "Instruct) behind a deployed endpoint and is the PRIMARY Ask DRISHTI "
               "semantic planner. Only the allow-listed role-scoped schema + glossary + "
               "bounded context + data-minimised question are sent; the guard + scope "
               "layers still enforce read-only + role scope independently of the model.",
        runtime="Catalyst QuickML LLM Serving endpoint (app/nlsql/planner.py "
                "CatalystQuickMLServingPlanner); env-gated SEMANTIC_PLANNER_PROVIDER="
                "catalyst_quickml; deterministic offline planner is the labelled fallback. "
                "Live invocation verified in Prompt 23.",
        tasks=(), backend=""),
    # --- Zia AutoML — item 1: record verified regional unavailability --------
    ModelPlacement(
        engine="zia-automl",
        capability="Automated tabular training (no-code AutoML)",
        placement=Placement.UNAVAILABLE, availability=Availability.UNAVAILABLE_REGION,
        reason="Zia AutoML is not exposed in this India-DC project; used only if "
               "actually available (it is not), so its unavailability is recorded.",
        runtime="n/a (not offered in the IN DC)",
        evidence="Catalyst Zia AutoML SDK docs list it unavailable in EU/AU/IN/JP/SA/CA "
                 "(verified 2026-07-18): "
                 "https://docs.catalyst.zoho.com/en/sdk/python/v1/zia-services/automl",
        fallback="QuickML no-code baseline + the justified AWS TabFM path."),
    # --- External AWS GPU foundation/custom models — item 2 ------------------
    ModelPlacement(
        engine="google-tabfm-v1",
        capability="TabFM tabular foundation-model in-context inference",
        placement=Placement.AWS_GPU, availability=Availability.AVAILABLE,
        reason="Catalyst exposes no custom GPU runtime; QuickML/Zia AutoML do not "
               "provide TabFM. GPU in-context inference is the genuine capability gap.",
        runtime="SageMaker async / AWS Batch (GPU); private ECR image "
                "(services/gpu-worker) + temporary encrypted S3 staging",
        tasks=(ModelTask.STATION_WORKLOAD_BAND.value,
               ModelTask.AREA_INCIDENT_FORECAST_TABFM.value),
        backend="tabfm"),
    ModelPlacement(
        engine="timesfm-2",
        capability="TimesFM time-series foundation-model forecasting",
        placement=Placement.AWS_GPU, availability=Availability.AVAILABLE,
        reason="No Catalyst service runs a pretrained time-series foundation model on "
               "GPU; the CPU statistical baseline is a comparator, not a replacement.",
        runtime="AWS Batch (preferred, scale-to-zero) / SageMaker async (GPU); "
                "private ECR + temporary S3 staging",
        tasks=(ModelTask.TIMESFM_COUNT_FORECAST.value,),
        backend="timesfm"),
    ModelPlacement(
        engine="st-gnn",
        capability="Spatio-temporal graph neural network area forecast",
        placement=Placement.AWS_GPU, availability=Availability.AVAILABLE,
        reason="A torch-geometric ST-GNN needs a GPU + heavy graph stack Catalyst "
               "does not provide.",
        runtime="AWS Batch / SageMaker async (GPU, torch-geometric); private ECR",
        tasks=(ModelTask.STGNN_AREA_FORECAST.value,),
        backend="stgnn"),
    # --- Catalyst CPU (AppSail) — never AWS GPU ------------------------------
    ModelPlacement(
        engine="hawkes-near-repeat",
        capability="Near-repeat (Hawkes/ETAS) short-horizon intensity",
        placement=Placement.CATALYST_CPU, availability=Availability.AVAILABLE,
        reason="A light CPU point-process; no GPU needed, so it stays on Catalyst "
               "AppSail (never an AWS GPU) and can run near-real-time.",
        runtime="AppSail CPU job",
        tasks=(ModelTask.NEAR_REPEAT_INTENSITY.value,), backend="hawkes"),
    ModelPlacement(
        engine="kde-stdbscan-hotspots",
        capability="KDE / ST-DBSCAN hotspot clusters",
        placement=Placement.CATALYST_CPU, availability=Availability.AVAILABLE,
        reason="Deterministic CPU spatial analytics; stays on Catalyst.",
        runtime="AppSail CPU / scheduled job",
        tasks=(ModelTask.HOTSPOT_CLUSTERS.value,), backend="kde"),
    ModelPlacement(
        engine="forecast-fusion",
        capability="Forecast fusion (combination/validation of layers)",
        placement=Placement.CATALYST_CPU, availability=Availability.AVAILABLE,
        reason="Fusion is a CPU validation/combination step over compatible layer "
               "outputs, not another GPU model call.",
        runtime="AppSail CPU step",
        tasks=(ModelTask.FORECAST_FUSION.value,), backend="baseline"),
    ModelPlacement(
        engine="statistical-gbm-baselines",
        capability="Statistical / gradient-boosted baselines (eligible comparators)",
        placement=Placement.CATALYST_CPU, availability=Availability.AVAILABLE,
        reason="Prior-period / seasonal / XGBoost / HistGradientBoosting baselines "
               "run on CPU on the same split as the candidate (G item 4).",
        runtime="AppSail CPU",
        tasks=(), backend="baseline"),
)


class PlacementError(ValueError):
    """Raised when the placement map is incomplete or violates a placement rule."""


def validate_placements() -> dict:
    """Validate the placement map against the Part G rules. Raises
    ``PlacementError`` on any violation; returns a summary on success."""
    seen: set[str] = set()
    for p in PLACEMENTS:
        for fname in ("engine", "capability", "reason", "runtime"):
            if not str(getattr(p, fname)).strip():
                raise PlacementError(f"{p.engine or '?'}: empty {fname}")
        if p.engine in seen:
            raise PlacementError(f"duplicate engine {p.engine}")
        seen.add(p.engine)

        # Rule: an unavailable capability MUST carry evidence (never faked as used).
        if p.availability is Availability.UNAVAILABLE_REGION:
            if p.placement is not Placement.UNAVAILABLE:
                raise PlacementError(f"{p.engine}: unavailable-in-region must be placement=UNAVAILABLE")
            if not p.evidence.strip():
                raise PlacementError(f"{p.engine}: unavailable placement requires evidence")
            if not p.fallback.strip():
                raise PlacementError(f"{p.engine}: unavailable placement requires a fallback")

        # Rule: RAG + no-code baseline run on QuickML (item 1).
        low = p.capability.lower()
        is_rag_or_nocode = ("rag" in low or "knowledge base" in low or "no-code" in low
                            or "text-llm" in low)
        if is_rag_or_nocode and p.availability is Availability.AVAILABLE \
                and p.placement is not Placement.CATALYST_QUICKML:
            raise PlacementError(f"{p.engine}: RAG/no-code must run on Catalyst QuickML")

        # Rule: GPU foundation backends run on AWS GPU (item 2).
        if p.backend in GPU_BACKENDS and p.availability is Availability.AVAILABLE \
                and p.placement is not Placement.AWS_GPU:
            raise PlacementError(f"{p.engine}: GPU backend {p.backend} must be placed AWS_GPU")
        # Rule: CPU/deterministic backends must NOT be placed on an AWS GPU.
        if p.backend in CPU_BACKENDS and p.placement is Placement.AWS_GPU:
            raise PlacementError(f"{p.engine}: CPU backend {p.backend} must not be placed AWS_GPU")

        # Rule: an AWS_GPU runtime must actually name an AWS runtime.
        if p.placement is Placement.AWS_GPU and not any(
                tok in p.runtime for tok in ("SageMaker", "Batch", "ECR")):
            raise PlacementError(f"{p.engine}: AWS_GPU placement must name an AWS runtime")

    _cross_check_enablement()
    _cross_check_capability_gaps()
    return {
        "version": PLACEMENT_VERSION,
        "placements": len(PLACEMENTS),
        "catalyst_quickml": sum(1 for p in PLACEMENTS if p.placement is Placement.CATALYST_QUICKML),
        "catalyst_cpu": sum(1 for p in PLACEMENTS if p.placement is Placement.CATALYST_CPU),
        "aws_gpu": sum(1 for p in PLACEMENTS if p.placement is Placement.AWS_GPU),
        "unavailable": sum(1 for p in PLACEMENTS if p.placement is Placement.UNAVAILABLE),
        "enabled_engines": sum(1 for p in PLACEMENTS
                               if engine_enablement(p.engine) is Enablement.ENABLED),
        "optional_engines": sum(1 for p in PLACEMENTS
                                if engine_enablement(p.engine) is Enablement.OPTIONAL),
        "deferred_engines": sum(1 for p in PLACEMENTS
                                if engine_enablement(p.engine) is Enablement.DEFERRED),
    }


def _cross_check_enablement() -> None:
    """Every engine must have a demo-enablement, and it must agree with the
    task-level enablement in ``enablement.py`` (G.2): an ENABLED engine has at
    least one enabled task; a DEFERRED engine has none."""
    for p in PLACEMENTS:
        if p.engine not in _ENGINE_ENABLEMENT:
            raise PlacementError(f"{p.engine}: missing demo-enablement entry")
        en = engine_enablement(p.engine)
        real = [ModelTask(t) for t in p.tasks if t in _MODELTASK_VALUES]
        if not real:
            continue  # capability-level (baselines/RAG/Zia) — no ModelTask to check
        any_enabled = any(is_task_enabled(t) for t in real)
        if en is Enablement.ENABLED and not any_enabled:
            raise PlacementError(
                f"{p.engine}: marked ENABLED but no task is enabled in enablement.py")
        if en is Enablement.DEFERRED and any_enabled:
            raise PlacementError(
                f"{p.engine}: marked DEFERRED but a task is enabled in enablement.py")


def _cross_check_capability_gaps() -> None:
    """Every AWS_GPU task here must appear in the capability-gap record, and no
    Catalyst-served capability may be placed on AWS — so the two source-of-truth
    modules can never drift apart."""
    cg.validate_capability_gaps()
    gap_tasks: set[str] = set()
    for gap in cg.CAPABILITY_GAPS:
        gap_tasks.update(gap.tasks)
    for p in PLACEMENTS:
        if p.placement is Placement.AWS_GPU:
            for t in p.tasks:
                if t not in gap_tasks:
                    raise PlacementError(
                        f"{p.engine}: AWS_GPU task {t!r} has no matching capability-gap record")


def placement_for_backend(backend: str) -> ModelPlacement | None:
    """Look up the placement that owns a given model backend."""
    for p in PLACEMENTS:
        if p.backend and p.backend == backend:
            return p
    return None


def emit() -> dict:
    """The ops-readable mirror written to infra/catalyst/ml-placement.json."""
    return {
        "_comment": "ML/RAG model-placement + regional-availability (Prompt 14 Part G "
                    "items 1-2). GENERATED from services/ml/app/predict/placement.py — "
                    "edit that module, not this file. validate_placements() guards parity "
                    "+ the placement rules and cross-checks capability-gaps.json.",
        "version": PLACEMENT_VERSION,
        "placements": [p.to_dict() for p in PLACEMENTS],
    }


if __name__ == "__main__":
    import json
    validate_placements()
    print(json.dumps(emit(), indent=2))
