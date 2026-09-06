"""Video-analytics detector adapters.

WHAT THIS SERVICE DOES AND DOES NOT DO — read this before extending it.

DRISHTI's reviewed Bedrock allow-list (``config.APPROVED_CHINESE_BEDROCK_MODELS``)
is TEXT-ONLY, and ``services/gpu-worker`` serves tabular/time-series foundation
models with no vision path. So this service does **not** run frame inference. It
never claims to. Instead it exposes a detector SEAM with two implementations, and
every persisted detection records which one produced it (``DetectorKind`` +
``DetectorLabel``) so provenance is never ambiguous on the review card:

  ``SyntheticSceneDetector``  (``synthetic_replay``)
      A deterministic scene generator for the demo estate. Given a camera and a
      time window it derives a reproducible incident roll from a keyed hash — the
      same camera and window always yield the same detection, which is what makes
      the ingest idempotent and the demo repeatable. It is labelled synthetic on
      every row and in every API response. It is NOT a model and must never be
      presented as one.

  ``ExternalAnalyticsDetector``  (``external_analytics``)
      The real integration path. An external/edge video-analytics service (the
      place where actual frame inference belongs — on the camera, on an NVR, or
      in a purpose-built CV service) POSTs detections to
      ``POST /cctv/detections/ingest`` with a shared secret. This adapter runs no
      inference of its own; ``analyse()`` returns nothing because detections
      arrive by push, not pull.

Adding a genuine in-house vision model is a POLICY change, not just a code
change: it needs an entry in ``APPROVED_CHINESE_BEDROCK_MODELS`` (or a reviewed
gpu-worker task) plus adapter-side review. ``capability_report()`` states the
current posture honestly so the UI can surface it rather than implying a
capability that is not there.

Confidence is never invented as certainty: a candidate below
``cctv_low_confidence_threshold`` is flagged ``low_confidence``, and one below
``cctv_min_alert_confidence`` is recorded as a detection but raises no reviewable
alert at all.
"""
from __future__ import annotations

import hashlib
import struct
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from ..config import get_settings
from ..datastore import cctv_schema as cs

# Bumping either version string makes previously-generated detections
# distinguishable from new ones in the audit trail.
SYNTHETIC_DETECTOR_LABEL = "synthetic-scene-replay@1.1.0"
EXTERNAL_DETECTOR_LABEL = "external-video-analytics@ingest-v1"

# Length of the analysis window in seconds. A detection's idempotency key is
# (camera, type, window index), so re-running the pass inside the same window is
# a no-op instead of a duplicate alert.
ANALYSIS_WINDOW_SECONDS = 30

# Per-class relative likelihood in the synthetic estate. Deliberately skewed to
# the mundane: traffic blocks are common, weapons are rare. A demo where every
# camera screams "weapon" would be dishonest about how review queues behave.
_CLASS_WEIGHTS: dict[str, int] = {
    "traffic_block": 26,
    "road_rage": 14,
    "fight": 12,
    "crowd_surge": 9,
    "vehicle_accident": 8,
    "abandoned_object": 8,
    "trespass": 7,
    "person_down": 6,
    "fire_smoke": 4,
    "weapon_suspected": 2,
}

# Typical count of involved objects (people/vehicles) per class, as (min, max).
_OBJECT_COUNTS: dict[str, tuple[int, int]] = {
    "fight": (2, 8),
    "road_rage": (2, 5),
    "traffic_block": (6, 24),
    "crowd_surge": (12, 60),
    "vehicle_accident": (2, 4),
    "fire_smoke": (1, 2),
    "weapon_suspected": (1, 3),
    "abandoned_object": (1, 1),
    "trespass": (1, 3),
    "person_down": (1, 2),
}

# The box label the detector attaches per class (what the tracker thinks it saw).
_BOX_LABEL: dict[str, str] = {
    "fight": "person",
    "road_rage": "person",
    "traffic_block": "vehicle",
    "crowd_surge": "person",
    "vehicle_accident": "vehicle",
    "fire_smoke": "smoke",
    "weapon_suspected": "object",
    "abandoned_object": "bag",
    "trespass": "person",
    "person_down": "person",
}


@dataclass
class DetectionCandidate:
    """One proposed detection, before it is persisted or turned into an alert."""
    camera_id: int
    detection_type: str
    confidence: float
    severity: str
    detected_at: datetime
    window_seconds: float = float(ANALYSIS_WINDOW_SECONDS)
    object_count: Optional[int] = None
    boxes: list[dict[str, Any]] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)
    frame_object_key: Optional[str] = None
    clip_object_key: Optional[str] = None
    source_record_id: str = ""
    detector_kind: str = "synthetic_replay"
    detector_label: str = SYNTHETIC_DETECTOR_LABEL

    def quality_flag(self) -> str:
        """Honest quality read-out driven by the configured thresholds."""
        s = get_settings()
        if self.confidence < s.cctv_low_confidence_threshold:
            return "low_confidence"
        return "valid"


# ---------------------------------------------------------------------------
# deterministic keyed pseudo-randomness (no global random state)
# ---------------------------------------------------------------------------
def _digest(*parts: Any) -> bytes:
    key = "|".join(str(p) for p in parts).encode("utf-8")
    return hashlib.blake2b(key, digest_size=32).digest()


def _unit(dig: bytes, offset: int = 0) -> float:
    """A stable float in [0,1) drawn from an 8-byte slice of the digest."""
    chunk = dig[offset % 24: (offset % 24) + 8]
    if len(chunk) < 8:
        chunk = (chunk + dig)[:8]
    (val,) = struct.unpack(">Q", chunk)
    return val / float(1 << 64)


def _pick_weighted(dig: bytes, weights: dict[str, int], offset: int = 0) -> str:
    total = sum(weights.values()) or 1
    roll = _unit(dig, offset) * total
    acc = 0.0
    for key, w in weights.items():
        acc += w
        if roll < acc:
            return key
    return next(iter(weights))


def window_index(when: datetime, window_seconds: int = ANALYSIS_WINDOW_SECONDS) -> int:
    """Index of the analysis window containing ``when`` (UTC epoch buckets)."""
    epoch = int(when.replace(tzinfo=when.tzinfo or timezone.utc).timestamp())
    return epoch // max(1, window_seconds)


# ---------------------------------------------------------------------------
# detector interface
# ---------------------------------------------------------------------------
class VisionDetector(ABC):
    """A source of CCTV detections.

    ``analyse`` is a PULL interface used by ``POST /cctv/analytics/run``. A push
    detector (external analytics) legitimately returns nothing here.
    """

    kind: str = "synthetic_replay"
    label: str = SYNTHETIC_DETECTOR_LABEL

    @abstractmethod
    def analyse(self, camera: dict, *, now: datetime,
                window_seconds: int = ANALYSIS_WINDOW_SECONDS) -> list[DetectionCandidate]:
        ...

    def describe(self) -> dict:
        return {"kind": self.kind, "label": self.label}


class SyntheticSceneDetector(VisionDetector):
    """Deterministic synthetic scene generator (the demo path).

    Reproducible by construction: everything is derived from
    ``blake2b(camera_code | window_index | salt)``. Re-running the pass inside the
    same window returns the identical candidate, so the ingest is naturally
    idempotent on ``SourceRecordID``.
    """

    kind = "synthetic_replay"
    label = SYNTHETIC_DETECTOR_LABEL

    def __init__(self, *, salt: str = "drishti-cctv-v1"):
        self._salt = salt

    # -- per-camera character ------------------------------------------------
    def _incident_rate(self, code: str) -> float:
        """Base per-window incident probability for a camera, in [0.04, 0.34].

        Spreading this makes some junctions genuinely busy and others quiet, which
        is what a real estate looks like and what makes the queue interesting.
        """
        return 0.04 + _unit(_digest(self._salt, "rate", code), 0) * 0.30

    @staticmethod
    def _is_continuous(camera: dict) -> bool:
        """Whether this camera's incident is present in every window.

        True for a camera backed by a looping clip of an actual incident: the
        fight or the collision is visible for the whole loop, so a detector
        watching that feed really would flag it continuously. Sampling a
        probability there would only mean the operator clicks "run analysis"
        several times waiting for the thing already on screen to be noticed.
        """
        return bool(camera.get("SceneIsContinuous"))

    def _allowed_types(self, camera: dict) -> dict[str, int]:
        """Restrict the class weights to the camera's configured profile."""
        profile = (camera.get("DetectorProfile") or "").strip()
        if not profile:
            return dict(_CLASS_WEIGHTS)
        wanted = {p.strip() for p in profile.split(",") if p.strip()}
        allowed = {k: v for k, v in _CLASS_WEIGHTS.items() if k in wanted}
        return allowed or dict(_CLASS_WEIGHTS)

    # -- scene composition ---------------------------------------------------
    def _boxes(self, dig: bytes, detection_type: str, count: int) -> list[dict[str, Any]]:
        """Plausible normalised boxes: clustered for interactions, spread for flow."""
        s = get_settings()
        n = max(1, min(count, s.cctv_max_boxes))
        label = _BOX_LABEL.get(detection_type, "object")
        clustered = detection_type in ("fight", "road_rage", "crowd_surge",
                                       "vehicle_accident", "weapon_suspected")
        # Anchor the scene somewhere in the middle band of the frame (cameras look
        # down a street, so the action is rarely at the very top or bottom).
        cx = 0.22 + _unit(dig, 3) * 0.56
        cy = 0.34 + _unit(dig, 5) * 0.42
        spread = 0.06 if clustered else 0.30
        boxes: list[dict[str, Any]] = []
        for i in range(n):
            d = _digest(dig, "box", i)
            bw = 0.05 + _unit(d, 0) * (0.07 if label == "person" else 0.14)
            bh = bw * (2.3 if label == "person" else 0.85)
            bx = cx + (_unit(d, 8) - 0.5) * 2 * spread
            by = cy + (_unit(d, 16) - 0.5) * 2 * (spread * 0.6)
            boxes.append({
                "x": round(max(0.0, min(1.0 - bw, bx)), 4),
                "y": round(max(0.0, min(1.0 - bh, by)), 4),
                "w": round(min(bw, 1.0), 4),
                "h": round(min(bh, 1.0), 4),
                "label": label,
                "score": round(0.55 + _unit(d, 24) * 0.44, 3),
            })
        return boxes

    def _confidence(self, dig: bytes, detection_type: str, camera: dict) -> float:
        """Confidence in [0.30, 0.97], degraded on a camera that is not healthy.

        A degraded camera producing a high-confidence claim would be a lie the
        analyst cannot audit, so the camera's own health caps the number.
        """
        base = 0.42 + _unit(dig, 9) * 0.55
        # Rare/hard classes are systematically less certain.
        if detection_type in ("weapon_suspected", "abandoned_object", "person_down"):
            base -= 0.12
        if camera.get("Status") == "degraded":
            base -= 0.18
        return round(max(0.30, min(0.97, base)), 4)

    def _severity(self, dig: bytes, detection_type: str) -> str:
        """Default severity for the class, escalated one step on a strong scene.

        Escalation is upward-only and visible: the default mapping lives in
        ``cctv_schema.DEFAULT_SEVERITY`` so the step is auditable.
        """
        base = cs.default_severity(detection_type)
        order = list(cs.DETECTION_SEVERITIES)
        if _unit(dig, 11) > 0.82:
            i = order.index(base) if base in order else 1
            return order[min(i + 1, len(order) - 1)]
        return base

    def analyse(self, camera: dict, *, now: datetime,
                window_seconds: int = ANALYSIS_WINDOW_SECONDS) -> list[DetectionCandidate]:
        if not camera.get("AnalyticsEnabled"):
            return []
        # An offline camera produces no frames, so it cannot produce detections.
        if camera.get("Status") in ("offline", "maintenance"):
            return []
        code = str(camera.get("Code") or camera.get("CameraID"))
        widx = window_index(now, window_seconds)
        dig = _digest(self._salt, code, widx)
        if not self._is_continuous(camera) and _unit(dig, 1) >= self._incident_rate(code):
            return []

        weights = self._allowed_types(camera)
        dtype = _pick_weighted(dig, weights, offset=2)
        lo, hi = _OBJECT_COUNTS.get(dtype, (1, 3))
        count = lo + int(_unit(dig, 7) * (hi - lo + 1))
        count = max(lo, min(hi, count))
        confidence = self._confidence(dig, dtype, camera)
        severity = self._severity(dig, dtype)
        # Place the detection at the window boundary so DetectedAt is reproducible.
        detected_at = datetime.fromtimestamp(widx * window_seconds, tz=timezone.utc)

        return [DetectionCandidate(
            camera_id=int(camera["CameraID"]),
            detection_type=dtype,
            confidence=confidence,
            severity=severity,
            detected_at=detected_at,
            window_seconds=float(window_seconds),
            object_count=count,
            boxes=self._boxes(dig, dtype, count),
            attributes={
                "generator": "deterministic-keyed-hash",
                "window_index": widx,
                "camera_status": camera.get("Status"),
                "synthetic": True,
            },
            source_record_id=f"{code}:{dtype}:{widx}",
            detector_kind=self.kind,
            detector_label=self.label,
        )]


class ExternalAnalyticsDetector(VisionDetector):
    """Push-only adapter for an external/edge video-analytics service.

    Frame inference happens outside DRISHTI (on the camera, an NVR, or a
    dedicated CV service) and arrives via ``POST /cctv/detections/ingest``
    authenticated with ``CCTV_INGEST_TOKEN``. There is nothing to pull, so
    ``analyse`` returns an empty list rather than fabricating a result.
    """

    kind = "external_analytics"
    label = EXTERNAL_DETECTOR_LABEL

    def analyse(self, camera: dict, *, now: datetime,
                window_seconds: int = ANALYSIS_WINDOW_SECONDS) -> list[DetectionCandidate]:
        return []


# ---------------------------------------------------------------------------
# factory + honest capability report
# ---------------------------------------------------------------------------
def get_detector() -> VisionDetector:
    """The configured detector (``CCTV_DETECTOR=synthetic|external``)."""
    if get_settings().cctv_detector_kind() == "external":
        return ExternalAnalyticsDetector()
    return SyntheticSceneDetector()


def capability_report() -> dict:
    """What this deployment can actually do, stated plainly for the UI.

    The frontend renders this verbatim next to the wall, so a viewer is never
    left to assume the platform is running real computer vision when it is not.
    """
    s = get_settings()
    kind = s.cctv_detector_kind()
    detector = get_detector()
    return {
        "cctv_enabled": bool(s.cctv_enabled),
        "detector_kind": detector.kind,
        "detector_label": detector.label,
        "detector_selector": kind,
        "runs_frame_inference_in_service": False,
        "external_ingest_enabled": s.cctv_ingest_configured(),
        "analysis_window_seconds": ANALYSIS_WINDOW_SECONDS,
        "low_confidence_threshold": s.cctv_low_confidence_threshold,
        "min_alert_confidence": s.cctv_min_alert_confidence,
        "detection_types": list(cs.DETECTION_TYPES),
        "auto_dispatch": False,
        "requires_human_confirmation": True,
        "note": (
            "This service does not run video frame inference. Detections are "
            "either produced by the in-repo deterministic synthetic scene "
            "generator (labelled synthetic_replay) or pushed by an external "
            "video-analytics service (labelled external_analytics). No detection "
            "ever becomes an active alert or a dispatch without a recorded human "
            "confirmation."
        ),
    }
