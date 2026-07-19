"""Demo enablement for the prediction runtime (Prompt 14 G.1 + G.2 scoping).

The routing matrix and the placement map DOCUMENT every route and model, but the
hackathon demo should run only a reduced, defensible set. This module is the
single source of truth for what is actually ENABLED, so ``routing.py`` and
``placement.py`` agree and nothing has to be enabled "by accident".

Recommended enabled model set (G.2):
  * TabFM (aggregate station-workload) — primary aggregate prediction;
  * TimesFM (scheduled time-series forecast) — demo-visible;
  * XGBoost / HistGradientBoosting — CPU baseline + fallback;
  * near-repeat / graph analytics — existing CPU investigation support;
  * disaster model — enabled by Prompt 17 (deferred here).

Optional / deferred (documented, OFF by default):
  * separate TabFM AREA-forecast task;
  * ST-GNN (unless already stable + valuable to the demo);
  * forecast fusion over every model;
  * KDE / ST-DBSCAN as a separate production pipeline;
  * multiple embedding index versions;
  * QuickML RAG (unless intended for the demo).

Each item can be flipped with an env var (so a demo can turn one on without a
code change) but the defaults encode the recommended set. Enablement is a
SEPARATE axis from regional availability (see ``placement.py``): a model can be
available yet deferred, or unavailable regardless of enablement.

Imports ONLY ``envelope.ModelTask`` to stay free of import cycles (routing +
placement import this module, not the other way around).
"""
from __future__ import annotations

import os
from enum import Enum

from .envelope import ModelTask


class Enablement(str, Enum):
    ENABLED = "enabled"       # active in the demo
    OPTIONAL = "optional"     # can be turned on; OFF by default
    DEFERRED = "deferred"     # documented, not for this demo


# --- Task-level enablement (drives routing + placement) ----------------------
# task -> (default enablement, reason). Env override: DRISHTI_TASK_<NAME>_ENABLED
_MODEL_ENABLEMENT: dict[ModelTask, tuple[Enablement, str]] = {
    ModelTask.STATION_WORKLOAD_BAND: (
        Enablement.ENABLED, "TabFM primary aggregate workload prediction."),
    ModelTask.NEAR_REPEAT_INTENSITY: (
        Enablement.ENABLED, "Near-repeat CPU investigation support (existing)."),
    ModelTask.TIMESFM_COUNT_FORECAST: (
        Enablement.ENABLED, "Scheduled time-series forecast (demo-visible)."),
    ModelTask.AREA_INCIDENT_FORECAST_TABFM: (
        Enablement.DEFERRED, "Separate TabFM area-forecast task — optional/deferred."),
    ModelTask.STGNN_AREA_FORECAST: (
        Enablement.DEFERRED, "ST-GNN deferred unless already stable + valuable to the demo."),
    ModelTask.FORECAST_FUSION: (
        Enablement.DEFERRED, "Forecast fusion over every model deferred."),
    ModelTask.HOTSPOT_CLUSTERS: (
        Enablement.DEFERRED, "KDE/ST-DBSCAN not a separate production pipeline for the demo."),
}

# --- Capability-level enablement (non-task items, for the summary/report) ----
# key -> (default enablement, reason [, env var]).
_CAPABILITY_ENABLEMENT: dict[str, tuple[Enablement, str, str]] = {
    "cpu_baselines": (Enablement.ENABLED,
                      "XGBoost / HistGradientBoosting CPU baseline + fallback.", ""),
    "graph_analytics": (Enablement.ENABLED,
                        "Near-repeat / graph analytics CPU investigation support.", ""),
    "quickml_rag": (Enablement.DEFERRED,
                    "QuickML RAG deferred unless demonstrated.", "DRISHTI_QUICKML_RAG_ENABLED"),
    "disaster_model": (Enablement.DEFERRED,
                       "Disaster model enabled by Prompt 17.", "DRISHTI_DISASTER_ENABLED"),
    "multiple_embedding_index_versions": (
        Enablement.DEFERRED,
        "Single active embedding index only; multiple versions deferred.",
        "DRISHTI_MULTI_EMBEDDING_ENABLED"),
}


def _env_task_flag(task: ModelTask) -> bool | None:
    """Read DRISHTI_TASK_<NAME>_ENABLED as an override (None if unset)."""
    raw = os.getenv(f"DRISHTI_TASK_{task.name}_ENABLED")
    if raw is None:
        return None
    return raw.strip().lower() == "true"


def task_enablement(task: ModelTask) -> Enablement:
    """The effective enablement of a task (default table + env override)."""
    default, _ = _MODEL_ENABLEMENT.get(task, (Enablement.DEFERRED, ""))
    override = _env_task_flag(task)
    if override is None:
        return default
    return Enablement.ENABLED if override else Enablement.DEFERRED


def is_task_enabled(task: ModelTask) -> bool:
    return task_enablement(task) is Enablement.ENABLED


def task_reason(task: ModelTask) -> str:
    return _MODEL_ENABLEMENT.get(task, (Enablement.DEFERRED, "not in the enabled set"))[1]


def enabled_tasks(tasks) -> tuple[ModelTask, ...]:
    """Filter an iterable of tasks down to the ENABLED ones (order preserved)."""
    return tuple(t for t in tasks if is_task_enabled(t))


def deferred_tasks(tasks) -> tuple[ModelTask, ...]:
    """The tasks that were filtered OUT (deferred/optional-off) — for transparency."""
    return tuple(t for t in tasks if not is_task_enabled(t))


def capability_enablement(key: str) -> Enablement:
    """The effective enablement of a non-task capability (default + env)."""
    default, _, env = _CAPABILITY_ENABLEMENT.get(key, (Enablement.DEFERRED, "", ""))
    if env:
        raw = os.getenv(env)
        if raw is not None:
            return Enablement.ENABLED if raw.strip().lower() == "true" else Enablement.DEFERRED
    return default


def summary() -> dict:
    """Enabled/deferred overview for /predict introspection + the report."""
    tasks = {t.value: {"enablement": task_enablement(t).value, "reason": task_reason(t)}
             for t in _MODEL_ENABLEMENT}
    caps = {k: {"enablement": capability_enablement(k).value, "reason": v[1]}
            for k, v in _CAPABILITY_ENABLEMENT.items()}
    return {
        "enabled_tasks": [t.value for t in _MODEL_ENABLEMENT if is_task_enabled(t)],
        "deferred_tasks": [t.value for t in _MODEL_ENABLEMENT if not is_task_enabled(t)],
        "tasks": tasks,
        "capabilities": caps,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(summary(), indent=2))
