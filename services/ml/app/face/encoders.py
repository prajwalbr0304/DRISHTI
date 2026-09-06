"""Face encoder interface for 1:N biometric search (mirrors cases/embeddings.py).

Three backends behind one contract, resolved the same way the similar-case
embedder is (explicit env choice -> real model when available -> honest fallback):

  * ``OnnxArcFaceEncoder`` — the PRIMARY, and the accuracy answer. SCRFD-10GF
    finds and 5-point aligns every face; ArcFace ``w600k_r50`` maps each aligned
    crop to a 512-dim unit-norm descriptor. ArcFace's additive-angular-margin
    loss is what makes 1:N search work at all: same-person cosine lands ~0.5-0.9
    while different-person pairs cluster near 0.0, so one global threshold holds
    across a large gallery. Encoding costs ~60-120 ms on CPU and single-digit ms
    on GPU; the gallery side is an HNSW index, so lookup stays sub-millisecond as
    records grow. Precomputed gallery vectors + ANN is exactly what makes a scan
    feel instantaneous. Runs on plain ``onnxruntime`` — no OpenCV, no Cython.

  * ``InsightFaceEncoder`` — the same models via the upstream ``insightface``
    package, for hosts that already have it. Selected with
    ``DRISHTI_FACE_ENCODER=insightface``.

  * ``PhotoDescriptorEncoder`` — a dependency-free FALLBACK so the feature
    degrades honestly instead of erroring when the ONNX weights are absent. It is
    duplicate-PHOTOGRAPH detection (low-frequency DCT + gradient-orientation
    histograms over a centre crop), NOT face recognition: no detector, no
    identity training. It matches the same photo re-submitted (survives
    re-encoding and rescaling) and nothing else, so its threshold is set at
    near-identity. ``biometric`` is False and the API surfaces that to the UI so
    a degraded deployment can never be mistaken for recognition.

Every encoder returns L2-normalised float32 vectors of :data:`FACE_EMBED_DIM`
dims so pgvector cosine distance (``<=>``, the HNSW op class on
PersonFaceEmbedding) is well-behaved, and each declares its own thresholds.
Descriptors are only ever compared within one ModelVersionID — see face/store.py.
"""
from __future__ import annotations

import io
import math
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional

import numpy as np

from . import modelfiles

# Must match PersonFaceEmbedding."Embedding" vector(512) and the registered
# ModelVersion.EmbeddingDim. ArcFace is natively 512-dim.
FACE_EMBED_DIM = 512

# Decode limits. A biometric probe is attacker-reachable input, so cap the
# decoded pixel count (decompression bombs) and the accepted source formats.
MAX_DECODE_PIXELS = 40_000_000          # ~40 MP
MAX_SIDE_PIXELS = 8_000                 # reject absurd single dimensions
ALLOWED_FORMATS = ("JPEG", "PNG", "WEBP", "BMP")

# Detector working resolution ceiling. Full-resolution frames buy no accuracy at
# portrait face scale and cost real latency.
DETECT_LONG_EDGE = 1600


class FaceEncodeError(RuntimeError):
    """The image could not be decoded, or was rejected by a safety limit."""


class FaceEncoderUnavailable(RuntimeError):
    """The requested encoder's model/dependency is not installed."""


@dataclass(frozen=True)
class FaceBox:
    """Detector geometry in SOURCE-image pixel coordinates."""
    x: int
    y: int
    w: int
    h: int

    def as_dict(self) -> dict:
        return {"x": self.x, "y": self.y, "w": self.w, "h": self.h}


@dataclass
class DetectedFace:
    """One detected face and its descriptor."""
    embedding: np.ndarray               # (FACE_EMBED_DIM,) float32, unit norm
    box: Optional[FaceBox] = None
    detector_score: Optional[float] = None   # detector confidence, 0..1
    quality: Optional[float] = None           # composite usability score, 0..1
    landmarks: list[list[float]] = field(default_factory=list)


@dataclass(frozen=True)
class DecodedImage:
    """A decoded, EXIF-corrected RGB image."""
    rgb: np.ndarray                     # (h, w, 3) uint8
    width: int
    height: int
    fmt: str
    size_bytes: int


# ---------------------------------------------------------------------------
# Decoding
# ---------------------------------------------------------------------------
def decode_image(data: bytes) -> DecodedImage:
    """Decode image bytes to an EXIF-corrected RGB array.

    Raises FaceEncodeError for anything that is not a plain, sanely sized image in
    an allowed format. Pillow's bomb guard is tightened explicitly rather than
    relying on its warning-only default.
    """
    if not data:
        raise FaceEncodeError("The image is empty.")
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:  # pragma: no cover - Pillow ships with the service
        raise FaceEncodeError(
            "Pillow is required to decode face images (pip install Pillow).") from exc

    Image.MAX_IMAGE_PIXELS = MAX_DECODE_PIXELS
    try:
        with Image.open(io.BytesIO(data)) as probe:
            fmt = (probe.format or "").upper()
            width, height = probe.size
    except Exception as exc:  # noqa: BLE001 — never leak decoder internals
        raise FaceEncodeError("That file could not be read as an image.") from exc

    if fmt not in ALLOWED_FORMATS:
        raise FaceEncodeError(
            f"Unsupported image format '{fmt or 'unknown'}'. "
            f"Use {', '.join(f.lower() for f in ALLOWED_FORMATS)}.")
    if width <= 0 or height <= 0:
        raise FaceEncodeError("The image has no pixels.")
    if width > MAX_SIDE_PIXELS or height > MAX_SIDE_PIXELS:
        raise FaceEncodeError(
            f"The image is {width}x{height}px; each side must be under {MAX_SIDE_PIXELS}px.")
    if width * height > MAX_DECODE_PIXELS:
        raise FaceEncodeError(
            f"The image is {width * height / 1e6:.1f} MP; the limit is "
            f"{MAX_DECODE_PIXELS / 1e6:.0f} MP.")

    try:
        with Image.open(io.BytesIO(data)) as img:
            img = ImageOps.exif_transpose(img)      # honour camera orientation
            rgb = np.asarray(img.convert("RGB"), dtype=np.uint8)
    except Exception as exc:  # noqa: BLE001
        raise FaceEncodeError("That image could not be decoded.") from exc

    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise FaceEncodeError("That image could not be converted to RGB.")
    return DecodedImage(rgb=rgb, width=int(rgb.shape[1]), height=int(rgb.shape[0]),
                        fmt=fmt, size_bytes=len(data))


# ---------------------------------------------------------------------------
# Shared numeric helpers
# ---------------------------------------------------------------------------
def l2_normalise(vec: np.ndarray) -> np.ndarray:
    """Unit-norm a 1-D vector (zero vectors are returned unchanged)."""
    v = np.asarray(vec, dtype=np.float32).ravel()
    norm = float(np.linalg.norm(v))
    return v if norm == 0.0 else (v / norm).astype(np.float32)


def _to_gray(rgb: np.ndarray) -> np.ndarray:
    """ITU-R BT.601 luma, float32 in 0..255."""
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    return (0.299 * r + 0.587 * g + 0.114 * b).astype(np.float32)


def _resize_gray(gray: np.ndarray, size: int) -> np.ndarray:
    """Area-average downscale to (size, size) via integer bucketing.

    Deterministic and dependency-free: identical input always yields an identical
    descriptor, which is what makes the fallback's duplicate matching exact.
    """
    h, w = gray.shape
    ys = (np.arange(size + 1) * h) // size
    xs = (np.arange(size + 1) * w) // size
    # Sum-area table -> exact block means without a Python loop per cell.
    cum = np.zeros((h + 1, w + 1), dtype=np.float64)
    np.cumsum(np.cumsum(gray, axis=0), axis=1, out=cum[1:, 1:])
    y0 = ys[:-1]
    y1 = np.maximum(ys[:-1] + 1, ys[1:])
    x0 = xs[:-1]
    x1 = np.maximum(xs[:-1] + 1, xs[1:])
    total = (cum[np.ix_(y1, x1)] - cum[np.ix_(y0, x1)]
             - cum[np.ix_(y1, x0)] + cum[np.ix_(y0, x0)])
    counts = np.outer(y1 - y0, x1 - x0).astype(np.float64)
    return (total / counts).astype(np.float32)


def _sharpness(gray: np.ndarray) -> float:
    """Normalised Laplacian energy, 0..1 — low means blurred/out of focus."""
    if gray.shape[0] < 3 or gray.shape[1] < 3:
        return 0.0
    lap = (gray[:-2, 1:-1] + gray[2:, 1:-1] + gray[1:-1, :-2] + gray[1:-1, 2:]
           - 4.0 * gray[1:-1, 1:-1])
    return float(min(1.0, math.sqrt(max(0.0, float(np.var(lap)))) / 14.0))


def _exposure(gray: np.ndarray) -> float:
    """1.0 for a well-exposed crop, falling off when clipped or flat."""
    mean = float(np.mean(gray)) / 255.0
    spread = float(np.std(gray)) / 255.0
    centred = 1.0 - min(1.0, abs(mean - 0.5) / 0.5)
    contrast = min(1.0, spread / 0.22)
    return float(max(0.0, min(1.0, 0.5 * centred + 0.5 * contrast)))


def face_quality(gray_crop: np.ndarray, detector_score: Optional[float],
                 relative_area: float) -> float:
    """Composite 0..1 usability score for a face crop.

    Blends detector confidence, how much of the frame the face fills (tiny faces
    carry little identity signal), focus and exposure. Used to warn on a weak
    probe and to refuse enrolling a poor gallery photo.
    """
    det = 1.0 if detector_score is None else max(0.0, min(1.0, float(detector_score)))
    # ~6% of frame area is a comfortable portrait; below ~0.5% is near-useless.
    size = max(0.0, min(1.0, math.sqrt(max(0.0, relative_area) / 0.06)))
    score = (0.40 * det + 0.25 * size
             + 0.20 * _sharpness(gray_crop) + 0.15 * _exposure(gray_crop))
    return round(max(0.0, min(1.0, score)), 5)


def _downscale_rgb(rgb: np.ndarray, scale: float) -> np.ndarray:
    h, w = rgb.shape[:2]
    nh, nw = max(1, int(round(h * scale))), max(1, int(round(w * scale)))
    try:
        from PIL import Image
        return np.asarray(Image.fromarray(rgb).resize((nw, nh), Image.BILINEAR),
                          dtype=np.uint8)
    except Exception:  # noqa: BLE001
        ys = np.linspace(0, h - 1, nh).astype(np.int32)
        xs = np.linspace(0, w - 1, nw).astype(np.int32)
        return np.ascontiguousarray(rgb[ys][:, xs])


# ---------------------------------------------------------------------------
# Encoder contract
# ---------------------------------------------------------------------------
class FaceEncoder(ABC):
    """Detect faces in an image and describe each one as a unit-norm vector."""

    name: str = "abstract"
    version: str = "1.0.0"
    family: str = "abstract"
    dim: int = FACE_EMBED_DIM
    #: True only for a real, identity-trained face recogniser. False means the
    #: backend compares IMAGES and must never be presented as recognition.
    biometric: bool = False
    #: Cosine similarity at or above which a hit is worth showing a reviewer.
    recommended_threshold: float = 0.90
    #: Similarity at/above which the top hit is labelled a strong lead.
    strong_threshold: float = 0.95
    #: Minimum crop quality accepted for a GALLERY photo (probes only warn).
    min_enrol_quality: float = 0.25
    #: Human-readable note the API surfaces alongside results.
    note: str = ""

    @abstractmethod
    def detect_and_encode(self, image: DecodedImage, *,
                          max_faces: int = 5) -> list[DetectedFace]:
        """Return detected faces, best first. Empty when no face is found."""

    def encode_primary(self, image: DecodedImage) -> DetectedFace:
        """The single most prominent face. Raises FaceEncodeError if none."""
        faces = self.detect_and_encode(image, max_faces=1)
        if not faces:
            raise FaceEncodeError(
                "No face was found in that image. Use a clear, front-facing photo "
                "where the face fills a good part of the frame.")
        return faces[0]

    def describe(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "family": self.family,
            "dim": self.dim,
            "biometric": self.biometric,
            "recommended_threshold": self.recommended_threshold,
            "strong_threshold": self.strong_threshold,
            "note": self.note,
        }


def _det_size_from_env(default: int = 640) -> int:
    """Detector input edge. 640 is the accuracy default (finds small/distant
    faces in a crowd frame). 320 is ~35% faster end-to-end and, measured on
    portrait-scale probes, gives the same same/different separation — worth
    setting when every probe is a captured headshot."""
    raw = os.getenv("DRISHTI_FACE_DET_SIZE", "").strip()
    if not raw:
        return default
    try:
        val = int(raw)
    except ValueError:
        return default
    return val if val in (256, 320, 480, 512, 640, 800, 1024) else default


def _thresholds_from_env(default_match: float, default_strong: float) -> tuple[float, float]:
    """Operator threshold overrides (tuning is deployment-specific)."""
    def _read(key: str, fallback: float) -> float:
        raw = os.getenv(key, "").strip()
        if not raw:
            return fallback
        try:
            val = float(raw)
        except ValueError:
            return fallback
        return val if 0.0 < val <= 1.0 else fallback
    match = _read("DRISHTI_FACE_MATCH_THRESHOLD", default_match)
    strong = _read("DRISHTI_FACE_STRONG_THRESHOLD", default_strong)
    return match, max(match, strong)


# ---------------------------------------------------------------------------
# Primary: SCRFD + ArcFace on raw onnxruntime
# ---------------------------------------------------------------------------
class OnnxArcFaceEncoder(FaceEncoder):
    """SCRFD detection + 5-point alignment + ArcFace 512-d, via onnxruntime."""

    family = "onnx-arcface"
    biometric = True
    # Cosine on unit-norm ArcFace descriptors. 0.36 is the widely used shortlist
    # operating point; ~0.55 is a confident same-person call. Deliberately set for
    # a shortlist a human reviews, not an automatic accept.
    recommended_threshold = 0.36
    strong_threshold = 0.55
    min_enrol_quality = 0.30

    def __init__(self, pack: str = modelfiles.DEFAULT_PACK, *,
                 det_size: Optional[int] = None):
        from . import onnx_arcface as ox

        try:
            providers = ox.preferred_providers()
        except ox.OnnxRuntimeUnavailable as exc:
            raise FaceEncoderUnavailable(str(exc)) from exc

        det_size = det_size if det_size is not None else _det_size_from_env()
        bundle = modelfiles.require(pack)   # raises FaceModelsMissing with the fix
        try:
            self._detector = ox.ScrfdDetector(
                str(bundle.detector), providers, input_size=det_size,
                score_thresh=float(os.getenv("DRISHTI_FACE_DET_THRESHOLD", "") or 0.5))
            self._recogniser = ox.ArcFaceRecogniser(str(bundle.recogniser), providers)
        except Exception as exc:  # noqa: BLE001 — surface as unavailable, not 500
            raise FaceEncoderUnavailable(
                f"Face models in {bundle.directory} could not be loaded "
                f"({type(exc).__name__}: {exc}).") from exc

        if self._recogniser.dim != FACE_EMBED_DIM:
            raise FaceEncoderUnavailable(
                f"{bundle.recogniser.name} emits {self._recogniser.dim} dims but the "
                f"gallery column is vector({FACE_EMBED_DIM}); change the model and "
                "the schema together.")

        self._bundle = bundle
        self._providers = providers
        self.name = f"drishti-face-arcface-{pack}"
        self.version = "1.0.0"
        self.dim = FACE_EMBED_DIM
        self.note = (
            f"SCRFD + ArcFace ({bundle.detector.name} + {bundle.recogniser.name}, "
            f"{FACE_EMBED_DIM}-dim, {providers[0]}). Cosine similarity on unit-norm "
            "descriptors. A hit is an investigative lead for human confirmation, "
            "never an identification.")
        self.recommended_threshold, self.strong_threshold = _thresholds_from_env(
            OnnxArcFaceEncoder.recommended_threshold,
            OnnxArcFaceEncoder.strong_threshold)

    def detect_and_encode(self, image: DecodedImage, *,
                          max_faces: int = 5) -> list[DetectedFace]:
        rgb = image.rgb
        scale = 1.0
        long_edge = max(rgb.shape[0], rgb.shape[1])
        if long_edge > DETECT_LONG_EDGE:
            scale = DETECT_LONG_EDGE / float(long_edge)
            rgb = _downscale_rgb(rgb, scale)

        try:
            raw = self._detector.detect(rgb, max_faces=max(1, int(max_faces)))
        except Exception as exc:  # noqa: BLE001
            raise FaceEncodeError(
                f"Face detection failed on that image ({type(exc).__name__}).") from exc
        if not raw:
            return []

        gray = _to_gray(rgb)
        frame_area = float(rgb.shape[0] * rgb.shape[1]) or 1.0
        inv = 1.0 / scale
        out: list[DetectedFace] = []
        for face in raw:
            try:
                aligned = self._recogniser.align(rgb, face)
                vec = self._recogniser.embed(aligned)
            except Exception as exc:  # noqa: BLE001
                raise FaceEncodeError(
                    f"Face encoding failed ({type(exc).__name__}).") from exc
            if float(np.linalg.norm(vec)) == 0.0:
                continue

            x1, y1, x2, y2 = (float(v) for v in face.bbox)
            bw, bh = max(0.0, x2 - x1), max(0.0, y2 - y1)
            cy0, cy1 = int(y1), max(int(y1) + 1, int(y2))
            cx0, cx1 = int(x1), max(int(x1) + 1, int(x2))
            crop = gray[cy0:cy1, cx0:cx1]
            if crop.size == 0:
                crop = gray

            out.append(DetectedFace(
                embedding=vec,
                box=FaceBox(x=int(round(x1 * inv)), y=int(round(y1 * inv)),
                            w=int(round(bw * inv)), h=int(round(bh * inv))),
                detector_score=round(min(1.0, max(0.0, face.score)), 5),
                quality=face_quality(crop, face.score, (bw * bh) / frame_area),
                landmarks=([[round(float(p[0]) * inv, 2), round(float(p[1]) * inv, 2)]
                            for p in face.keypoints]
                           if face.keypoints is not None else []),
            ))

        # Best first: detector confidence weighted by how much frame the face fills.
        out.sort(key=lambda d: ((d.detector_score or 0.0)
                                * ((d.box.w * d.box.h) if d.box else 1)), reverse=True)
        return out[:max(1, int(max_faces))]

    def describe(self) -> dict:
        return {**super().describe(), "providers": self._providers,
                **self._bundle.describe()}


# ---------------------------------------------------------------------------
# Alternative: the upstream insightface package, when a host already has it
# ---------------------------------------------------------------------------
class InsightFaceEncoder(FaceEncoder):
    """Same SCRFD+ArcFace models through ``insightface.app.FaceAnalysis``."""

    family = "insightface-arcface"
    biometric = True
    recommended_threshold = 0.36
    strong_threshold = 0.55
    min_enrol_quality = 0.30

    def __init__(self, pack: str = modelfiles.DEFAULT_PACK, *,
                 det_size: Optional[int] = None):
        det_size = det_size if det_size is not None else _det_size_from_env()
        try:
            from insightface.app import FaceAnalysis
        except ImportError as exc:
            raise FaceEncoderUnavailable(
                "insightface is not installed. Either `pip install insightface` or "
                "use the default onnxruntime backend (DRISHTI_FACE_ENCODER=arcface)."
            ) from exc

        from . import onnx_arcface as ox
        providers = ox.preferred_providers()
        try:
            self._app = FaceAnalysis(name=pack, providers=providers,
                                     allowed_modules=["detection", "recognition"])
            ctx = 0 if any("CUDA" in p or "Tensorrt" in p for p in providers) else -1
            env_ctx = os.getenv("DRISHTI_FACE_CTX_ID", "").strip()
            if env_ctx:
                try:
                    ctx = int(env_ctx)
                except ValueError:
                    pass
            self._app.prepare(ctx_id=ctx, det_size=(det_size, det_size))
        except Exception as exc:  # noqa: BLE001
            raise FaceEncoderUnavailable(
                f"insightface pack '{pack}' could not be loaded: "
                f"{type(exc).__name__}: {exc}") from exc

        self.name = f"drishti-face-arcface-{pack}"   # same space as the ONNX path
        self.version = "1.0.0"
        self.dim = FACE_EMBED_DIM
        self._pack = pack
        self._providers = providers
        self.note = (f"insightface {pack} (SCRFD + ArcFace, {FACE_EMBED_DIM}-dim, "
                     f"{providers[0]}). A hit is a lead for human confirmation.")
        self.recommended_threshold, self.strong_threshold = _thresholds_from_env(
            InsightFaceEncoder.recommended_threshold,
            InsightFaceEncoder.strong_threshold)

    def detect_and_encode(self, image: DecodedImage, *,
                          max_faces: int = 5) -> list[DetectedFace]:
        rgb = image.rgb
        scale = 1.0
        long_edge = max(rgb.shape[0], rgb.shape[1])
        if long_edge > DETECT_LONG_EDGE:
            scale = DETECT_LONG_EDGE / float(long_edge)
            rgb = _downscale_rgb(rgb, scale)
        bgr = np.ascontiguousarray(rgb[:, :, ::-1])      # insightface wants BGR

        try:
            faces = self._app.get(bgr, max_num=max(1, int(max_faces)))
        except Exception as exc:  # noqa: BLE001
            raise FaceEncodeError(
                f"Face detection failed on that image ({type(exc).__name__}).") from exc

        gray = _to_gray(rgb)
        frame_area = float(rgb.shape[0] * rgb.shape[1]) or 1.0
        inv = 1.0 / scale
        out: list[DetectedFace] = []
        for f in faces:
            emb = getattr(f, "normed_embedding", None)
            if emb is None:
                emb = getattr(f, "embedding", None)
            if emb is None:
                continue
            vec = l2_normalise(np.asarray(emb, dtype=np.float32))
            if vec.shape[0] != self.dim:
                raise FaceEncodeError(
                    f"insightface produced a {vec.shape[0]}-dim descriptor but the "
                    f"gallery column is vector({self.dim}).")

            bx = np.asarray(getattr(f, "bbox", [0, 0, 0, 0]), dtype=np.float32)
            x1 = max(0.0, float(bx[0]))
            y1 = max(0.0, float(bx[1]))
            x2 = min(float(rgb.shape[1]), float(bx[2]))
            y2 = min(float(rgb.shape[0]), float(bx[3]))
            bw, bh = max(0.0, x2 - x1), max(0.0, y2 - y1)
            cy0, cy1 = int(y1), max(int(y1) + 1, int(y2))
            cx0, cx1 = int(x1), max(int(x1) + 1, int(x2))
            crop = gray[cy0:cy1, cx0:cx1]
            if crop.size == 0:
                crop = gray
            det = getattr(f, "det_score", None)
            kps = getattr(f, "kps", None)
            out.append(DetectedFace(
                embedding=vec,
                box=FaceBox(x=int(round(x1 * inv)), y=int(round(y1 * inv)),
                            w=int(round(bw * inv)), h=int(round(bh * inv))),
                detector_score=(round(min(1.0, max(0.0, float(det))), 5)
                                if det is not None else None),
                quality=face_quality(crop,
                                     float(det) if det is not None else None,
                                     (bw * bh) / frame_area),
                landmarks=([[round(float(p[0]) * inv, 2), round(float(p[1]) * inv, 2)]
                            for p in np.asarray(kps, dtype=np.float32)]
                           if kps is not None else []),
            ))
        out.sort(key=lambda d: ((d.detector_score or 0.0)
                                * ((d.box.w * d.box.h) if d.box else 1)), reverse=True)
        return out[:max(1, int(max_faces))]

    def describe(self) -> dict:
        return {**super().describe(), "providers": self._providers, "pack": self._pack}


# ---------------------------------------------------------------------------
# Fallback: deterministic duplicate-photo descriptor (NOT face recognition)
# ---------------------------------------------------------------------------
@lru_cache(maxsize=8)
def _dct_basis(n: int) -> np.ndarray:
    """Orthonormal DCT-II basis matrix, so dct2(b) == M @ b @ M.T."""
    k = np.arange(n, dtype=np.float64).reshape(-1, 1)
    x = np.arange(n, dtype=np.float64).reshape(1, -1)
    m = np.cos(np.pi * (x + 0.5) * k / n)
    m[0] *= 1.0 / math.sqrt(2.0)
    return (m * math.sqrt(2.0 / n)).astype(np.float32)


class PhotoDescriptorEncoder(FaceEncoder):
    """Deterministic duplicate-PHOTO descriptor — the honest degraded mode.

    No detector and no identity model. It centre-crops (mugshots and captures
    frame the face centrally), then concatenates low-frequency DCT coefficients
    with per-cell gradient-orientation histograms. That is robust to re-encoding,
    mild rescaling and brightness shifts, so the SAME photograph re-submitted
    scores ~1.0 — but two different photos of one person will NOT match, and two
    similarly composed portraits of different people can score deceptively high.
    The threshold is therefore pinned at near-identity: this finds a photo already
    on file, not a person.
    """

    name = "drishti-face-photodesc"
    version = "1.0.0"
    family = "photo-descriptor"
    biometric = False
    # Near-exact only. Anything looser produces confident-looking false dossiers,
    # which is the worst possible failure for this feature.
    recommended_threshold = 0.995
    strong_threshold = 0.9995
    min_enrol_quality = 0.0
    note = ("DEGRADED MODE — deterministic duplicate-photo matching, NOT face "
            "recognition. It flags the same photograph already on record; it "
            "cannot recognise a person from a new photo. Install the ONNX face "
            "models (python -m app.batch face-models) to enable ArcFace "
            "recognition.")

    GRID = 4            # 4x4 spatial cells
    ORIENT_BINS = 16    # 16 orientations -> 256 dims
    DCT_BLOCK = 16      # 16x16 low-frequency coefficients -> 256 dims
    WORK_SIZE = 64      # working crop resolution

    def detect_and_encode(self, image: DecodedImage, *,
                          max_faces: int = 5) -> list[DetectedFace]:
        gray_full = _to_gray(image.rgb)
        crop, box = self._centre_crop(gray_full)
        work = _resize_gray(crop, self.WORK_SIZE)

        vec = l2_normalise(np.concatenate([self._dct_features(work),
                                           self._gradient_features(work)]))
        if vec.shape[0] != self.dim:  # pragma: no cover - guarded by construction
            raise FaceEncodeError(
                f"photo descriptor produced {vec.shape[0]} dims, expected {self.dim}.")

        frame_area = float(gray_full.shape[0] * gray_full.shape[1]) or 1.0
        # No detector exists here; cap quality so the UI can show that this
        # reading is weaker evidence than a detected, aligned face.
        quality = min(0.6, face_quality(work, 0.5, (box.w * box.h) / frame_area))
        return [DetectedFace(embedding=vec, box=box, detector_score=None,
                             quality=quality, landmarks=[])]

    @staticmethod
    def _centre_crop(gray: np.ndarray) -> tuple[np.ndarray, FaceBox]:
        h, w = gray.shape
        side = int(min(h, w) * 0.8) or min(h, w)
        y0 = max(0, (h - side) // 2)
        x0 = max(0, (w - side) // 2)
        return gray[y0:y0 + side, x0:x0 + side], FaceBox(x=x0, y=y0, w=side, h=side)

    def _dct_features(self, work: np.ndarray) -> np.ndarray:
        n = self.DCT_BLOCK
        small = _resize_gray(work, 32)
        basis = _dct_basis(32)
        block = np.array((basis @ small @ basis.T)[:n, :n], dtype=np.float32)
        block[0, 0] = 0.0          # drop DC: overall brightness is not identity
        return l2_normalise(block.ravel())

    def _gradient_features(self, work: np.ndarray) -> np.ndarray:
        gx = np.zeros_like(work)
        gy = np.zeros_like(work)
        gx[:, 1:-1] = work[:, 2:] - work[:, :-2]
        gy[1:-1, :] = work[2:, :] - work[:-2, :]
        mag = np.sqrt(gx * gx + gy * gy)
        # Unsigned orientation (0..pi): invariant to contrast polarity.
        bins = np.minimum(
            (np.mod(np.arctan2(gy, gx), np.pi) / np.pi * self.ORIENT_BINS).astype(np.int32),
            self.ORIENT_BINS - 1)

        cells = self.GRID
        step = work.shape[0] // cells
        hist = np.zeros((cells, cells, self.ORIENT_BINS), dtype=np.float32)
        for i in range(cells):
            for j in range(cells):
                b = bins[i * step:(i + 1) * step, j * step:(j + 1) * step].ravel()
                m = mag[i * step:(i + 1) * step, j * step:(j + 1) * step].ravel()
                # Per-cell normalisation -> local illumination invariance.
                hist[i, j] = l2_normalise(
                    np.bincount(b, weights=m, minlength=self.ORIENT_BINS))
        return l2_normalise(hist.ravel())


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------
_ARCFACE_PREFIX = "drishti-face-arcface-"
_ONNX_ALIASES = {"arcface", "onnx", "onnx-arcface", "real", "scrfd"}
_INSIGHTFACE_ALIASES = {"insightface", "insight"}
_FALLBACK_ALIASES = {"photodesc", "photo", "descriptor", "fallback", "hashing", "none"}


def _pack_from_env() -> str:
    pack = os.getenv("DRISHTI_FACE_MODEL_PACK", "").strip() or modelfiles.DEFAULT_PACK
    return pack if pack in modelfiles.PACKS else modelfiles.DEFAULT_PACK


def _build_encoder(choice: str) -> FaceEncoder:
    pack = _pack_from_env()
    if choice in _FALLBACK_ALIASES:
        return PhotoDescriptorEncoder()
    if choice in _INSIGHTFACE_ALIASES:
        return InsightFaceEncoder(pack=pack)         # explicit: let failures surface
    if choice in _ONNX_ALIASES:
        return OnnxArcFaceEncoder(pack=pack)         # explicit: let failures surface
    if choice in modelfiles.PACKS:
        return OnnxArcFaceEncoder(pack=choice)
    if choice:
        raise FaceEncoderUnavailable(
            f"Unknown face encoder '{choice}'. Use 'arcface', 'insightface', "
            f"'photodesc', or a pack name ({', '.join(modelfiles.PACKS)}).")
    # Auto: real recognition when the weights are installed, honest fallback if not.
    try:
        return OnnxArcFaceEncoder(pack=pack)
    except (FaceEncoderUnavailable, modelfiles.FaceModelsMissing):
        try:
            return InsightFaceEncoder(pack=pack)
        except (FaceEncoderUnavailable, Exception):  # noqa: BLE001
            return PhotoDescriptorEncoder()


@lru_cache(maxsize=4)
def get_encoder(name: Optional[str] = None) -> FaceEncoder:
    """Resolve (and cache) the face encoder.

    Order: explicit ``name`` / ``DRISHTI_FACE_ENCODER`` -> ONNX ArcFace when its
    weights are installed -> insightface if present -> deterministic
    photo-descriptor fallback. Cached because loading the ONNX graphs takes
    seconds and the models are stateless at inference time.
    """
    choice = (name or os.getenv("DRISHTI_FACE_ENCODER", "")).strip().lower()
    return _build_encoder(choice)


@lru_cache(maxsize=4)
def encoder_for_model_name(model_name: str) -> FaceEncoder:
    """Rebuild the encoder that produced a stored gallery, so a live probe is
    described in the SAME space. Raises if it cannot be reconstructed."""
    if model_name == PhotoDescriptorEncoder.name:
        return PhotoDescriptorEncoder()
    if model_name.startswith(_ARCFACE_PREFIX):
        pack = model_name[len(_ARCFACE_PREFIX):] or modelfiles.DEFAULT_PACK
        prefer_insightface = (os.getenv("DRISHTI_FACE_ENCODER", "").strip().lower()
                              in _INSIGHTFACE_ALIASES)
        builders = ([InsightFaceEncoder, OnnxArcFaceEncoder] if prefer_insightface
                    else [OnnxArcFaceEncoder, InsightFaceEncoder])
        errors: list[str] = []
        for builder in builders:
            try:
                enc = builder(pack=pack)
            except Exception as exc:  # noqa: BLE001 — try the next backend
                errors.append(f"{builder.__name__}: {exc}")
                continue
            if enc.name == model_name:
                return enc
            errors.append(f"{builder.__name__} resolved '{enc.name}'")
        raise FaceEncoderUnavailable(
            f"The gallery was built with '{model_name}' but that encoder could not "
            f"be rebuilt, so those descriptors are not searchable. "
            + " | ".join(errors))
    raise FaceEncoderUnavailable(
        f"The gallery was built with unknown face model '{model_name}'; its probe "
        "encoder cannot be rebuilt, so those descriptors are not searchable.")


def reset_encoder_cache() -> None:
    """Drop cached encoders (used after a model download or config change)."""
    get_encoder.cache_clear()
    encoder_for_model_name.cache_clear()


def encoder_status() -> dict:
    """Non-raising snapshot for /face/status."""
    pack = _pack_from_env()
    report: dict = {"requested": os.getenv("DRISHTI_FACE_ENCODER", "").strip() or "auto",
                    "models": modelfiles.status(pack)}
    try:
        from . import onnx_arcface as ox
        report["onnxruntime"] = {"installed": True,
                                 "providers": ox.available_providers()}
    except Exception as exc:  # noqa: BLE001
        report["onnxruntime"] = {"installed": False, "error": str(exc)}
    try:
        enc = get_encoder()
        report["encoder"] = enc.describe()
        report["available"] = True
    except Exception as exc:  # noqa: BLE001
        report["encoder"] = None
        report["available"] = False
        report["error"] = f"{type(exc).__name__}: {exc}"
    return report
