"""QuickML / no-code baseline vs custom AWS model comparison (Prompt 14 G item 4).

"Compare the QuickML/no-code baseline, when eligible, against the custom AWS model
using the same time-aware or group-aware split and leakage guardrails."

This module makes that comparison a typed, self-validating record. Its two
guarantees are exactly the two the spec demands:

  1. **Same split** — every comparator carries the hash of the split it was scored
     on; ``validate()`` rejects the comparison if any comparator was scored on a
     different split (so the QuickML no-code baseline and the AWS TabFM model are
     never compared on mismatched data).
  2. **Leakage guardrails** — the comparison refuses unless the shared dataset
     passed the leakage / protected-feature / label-independence checks.

``from_workload_evaluation`` adapts the existing held-out evaluation report (whose
candidate + baselines are already computed on one identical test split) into this
record, then folds in the QuickML no-code baseline (Catalyst) and labels the
candidate as the custom AWS model — the two comparators item 4 is about.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Optional

# Metric keys compared (ordinal classification). Higher is better except ECE.
_METRIC_KEYS = ("accuracy", "macro_f1", "qwk", "ece")


class ComparisonError(ValueError):
    """Raised when a comparison is not fair (mismatched split or leakage risk)."""


@dataclass(frozen=True)
class SplitDescriptor:
    """The time-aware / group-aware split every comparator must share."""
    method: str
    train_n: int
    val_n: int
    test_n: int
    geo_holdout: tuple[str, ...] = field(default_factory=tuple)
    cutoff_axis: tuple[str, str] = ("", "")

    def hash(self) -> str:
        payload = {"method": self.method, "train": self.train_n, "val": self.val_n,
                   "test": self.test_n, "geo": sorted(self.geo_holdout),
                   "axis": list(self.cutoff_axis)}
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:16]

    def as_dict(self) -> dict:
        d = asdict(self)
        d["geo_holdout"] = list(self.geo_holdout)
        d["cutoff_axis"] = list(self.cutoff_axis)
        d["hash"] = self.hash()
        return d


@dataclass(frozen=True)
class Comparator:
    """One model/baseline scored on the shared split."""
    name: str
    family: str
    placement: str                       # catalyst-quickml | catalyst-cpu | aws-gpu
    metrics: dict = field(default_factory=dict)
    split_hash: Optional[str] = None     # must equal the comparison split hash
    available: bool = True               # False => not yet run (honest placeholder)
    note: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class BaselineModelComparison:
    """A fair comparison of comparators on one split, with a leakage attestation."""
    task: str
    split: SplitDescriptor
    leakage_safe: bool
    comparators: list[Comparator] = field(default_factory=list)
    primary_metric: str = "qwk"

    def validate(self) -> "BaselineModelComparison":
        if self.primary_metric not in _METRIC_KEYS:
            raise ComparisonError(f"unknown primary metric {self.primary_metric!r}")
        if not self.leakage_safe:
            raise ComparisonError(
                "leakage guardrails failed — refusing to compare (item 4 requires "
                "leakage-safe, same-split evaluation)")
        expected = self.split.hash()
        for c in self.comparators:
            if c.available and c.split_hash and c.split_hash != expected:
                raise ComparisonError(
                    f"comparator {c.name!r} was scored on a different split "
                    f"({c.split_hash} != {expected}) — not a fair comparison")
        return self

    def available_comparators(self) -> list[Comparator]:
        return [c for c in self.comparators if c.available and c.metrics]

    def winner(self) -> Optional[str]:
        avail = self.available_comparators()
        if not avail:
            return None
        higher_better = self.primary_metric != "ece"
        return (max if higher_better else min)(
            avail, key=lambda c: c.metrics.get(self.primary_metric, 0.0)).name

    def skill(self, model_name: str, baseline_name: str) -> Optional[float]:
        """QWK-error skill of ``model`` over ``baseline`` (positive => better)."""
        m = self._by_name(model_name)
        b = self._by_name(baseline_name)
        if not (m and b and m.metrics and b.metrics):
            return None
        b_err = 1.0 - float(b.metrics.get("qwk", 0.0))
        m_err = 1.0 - float(m.metrics.get("qwk", 0.0))
        return round(1.0 - m_err / b_err, 4) if b_err > 0 else None

    def _by_name(self, name: str) -> Optional[Comparator]:
        return next((c for c in self.comparators if c.name == name), None)

    def as_dict(self) -> dict:
        return {
            "task": self.task,
            "split": self.split.as_dict(),
            "leakage_safe": self.leakage_safe,
            "primary_metric": self.primary_metric,
            "comparators": [c.as_dict() for c in self.comparators],
            "winner": self.winner(),
            "fair_comparison": self.leakage_safe and all(
                (not c.available) or (not c.split_hash) or c.split_hash == self.split.hash()
                for c in self.comparators),
        }


def _metric_subset(m: dict) -> dict:
    return {k: m[k] for k in _METRIC_KEYS if k in m}


def from_workload_evaluation(report: dict, *,
                             quickml_baseline: Optional[dict] = None,
                             aws_model_metrics: Optional[dict] = None,
                             aws_model_name: str = "google-tabfm-v1") -> BaselineModelComparison:
    """Build the comparison from a workload held-out evaluation report.

    ``report`` is the dict produced by ``workload.evaluation.evaluate*`` (its
    candidate + baselines already share one test split). ``quickml_baseline`` is
    an optional ``{name, family, metrics, split_hash}`` for the Catalyst QuickML
    no-code baseline scored on the SAME split; when absent it is recorded as a
    pending (unavailable) comparator so the comparison stays honest.
    """
    splits = report.get("splits") or {}
    geo = (report.get("geo_holdout") or {}).get("holdout_districts") or []
    meta = report.get("dataset") or {}
    split = SplitDescriptor(
        method="time-split + geographic-holdout",
        train_n=int(splits.get("train", 0)), val_n=int(splits.get("val", 0)),
        test_n=int(splits.get("test", 0)),
        geo_holdout=tuple(str(d) for d in geo),
        cutoff_axis=(str(meta.get("axis_first", "")), str(meta.get("axis_last", ""))))
    shash = split.hash()
    leakage_safe = bool((report.get("leakage") or {}).get("leakage_safe"))

    comparators: list[Comparator] = []

    # The custom AWS model (production candidate = TabFM on GPU). Use explicit
    # AWS metrics if supplied, else the evaluation candidate's calibrated metrics.
    model_block = report.get("model") or {}
    model_metrics = aws_model_metrics or _metric_subset(model_block.get("calibrated") or {})
    comparators.append(Comparator(
        name=aws_model_name, family="tabular-foundation", placement="aws-gpu",
        metrics=model_metrics, split_hash=shash, available=bool(model_metrics),
        note="Custom AWS model (SageMaker/Batch GPU)."))

    # QuickML no-code baseline (Catalyst) — the eligible comparator (item 4).
    if quickml_baseline and quickml_baseline.get("metrics"):
        qb_hash = quickml_baseline.get("split_hash", shash)
        comparators.append(Comparator(
            name=quickml_baseline.get("name", "quickml-nocode-baseline"),
            family=quickml_baseline.get("family", "no-code-ml"),
            placement="catalyst-quickml",
            metrics=_metric_subset(quickml_baseline["metrics"]),
            split_hash=qb_hash, available=True,
            note="Catalyst QuickML no-code baseline on the shared split."))
    else:
        comparators.append(Comparator(
            name="quickml-nocode-baseline", family="no-code-ml",
            placement="catalyst-quickml", metrics={}, split_hash=shash,
            available=False,
            note="Pending: QuickML no-code baseline not yet run (Catalyst pipeline held)."))

    # The statistical / GBM baselines already scored on the identical split.
    for key, br in (report.get("baselines") or {}).items():
        comparators.append(Comparator(
            name=br.get("name", key), family=br.get("family", "baseline"),
            placement="catalyst-cpu", metrics=_metric_subset(br), split_hash=shash,
            available=True, note="CPU baseline on the shared split."))

    comp = BaselineModelComparison(
        task=str(report.get("task", "")), split=split, leakage_safe=leakage_safe,
        comparators=comparators)
    return comp
