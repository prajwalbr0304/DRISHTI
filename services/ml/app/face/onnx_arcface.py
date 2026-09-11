"""SCRFD detection + ArcFace recognition on raw onnxruntime (numpy + Pillow only).

Why not just import ``insightface``? Because that package pulls a Cython
extension that needs a C toolchain, plus OpenCV, scikit-image and albumentations
— a heavy, frequently-broken install for what is ultimately two ONNX graphs and
about 200 lines of tensor plumbing. Running the same graphs directly keeps the
dependency surface at ``onnxruntime`` and drops in on any host, GPU or CPU.
(``FACE_ENCODER=insightface`` still uses the upstream package when it is present.)

The pipeline is the standard, published one and is bit-compatible with upstream's
pre/post-processing, so the descriptors live in the same ArcFace space:

  1. letterbox the frame to the detector's square input, scale to
     ``(px - 127.5) / 128`` in RGB NCHW;
  2. SCRFD emits per-stride (8/16/32) centre-offset boxes + 5 keypoints; decode
     against the anchor grid, threshold, then NMS;
  3. similarity-transform (Umeyama) the 5 keypoints onto ArcFace's canonical
     112x112 landmark template and bilinearly resample — alignment is what makes
     the embedding pose-stable, and skipping it costs far more accuracy than any
     model choice;
  4. ArcFace maps the aligned crop to 512 floats; L2-normalise so cosine
     similarity is just a dot product and pgvector's ``<=>`` is exact.
"""
from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from typing import Optional

import numpy as np

# ArcFace's canonical 5-point template for a 112x112 crop (left eye, right eye,
# nose tip, left mouth corner, right mouth corner). Fixed by the trained model —
# every ArcFace variant expects crops aligned to exactly these coordinates.
ARCFACE_TEMPLATE_112 = np.array([
    [38.2946, 51.6963],
    [73.5318, 51.5014],
    [56.0252, 71.7366],
    [41.5493, 92.3655],
    [70.7299, 92.2041],
], dtype=np.float64)

RECOGNISER_INPUT = 112


class OnnxRuntimeUnavailable(RuntimeError):
    """onnxruntime is not installed."""


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------
def umeyama_similarity(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    """Least-squares similarity transform (scale + rotation + translation).

    Returns the 2x3 affine matrix mapping ``src`` points onto ``dst``. This is the
    Umeyama estimator, restricted to a similarity so the crop is never sheared or
    stretched — the recogniser was trained on rigid alignments only.
    """
    src = np.asarray(src, dtype=np.float64)
    dst = np.asarray(dst, dtype=np.float64)
    n, dim = src.shape

    src_mean = src.mean(axis=0)
    dst_mean = dst.mean(axis=0)
    src_demean = src - src_mean
    dst_demean = dst - dst_mean

    cov = (dst_demean.T @ src_demean) / n
    d = np.ones(dim, dtype=np.float64)
    if np.linalg.det(cov) < 0:
        d[dim - 1] = -1.0

    u, s, vt = np.linalg.svd(cov)
    rank = np.linalg.matrix_rank(cov)
    if rank == 0:
        raise ValueError("degenerate landmark set: cannot align this face")
    if rank == dim - 1:
        if np.linalg.det(u) * np.linalg.det(vt) > 0:
            rot = u @ vt
        else:
            saved = d[dim - 1]
            d[dim - 1] = -1.0
            rot = u @ np.diag(d) @ vt
            d[dim - 1] = saved
    else:
        rot = u @ np.diag(d) @ vt

    var = src_demean.var(axis=0).sum()
    scale = 1.0 if var == 0 else float((s @ d) / var)
    matrix = np.zeros((2, 3), dtype=np.float64)
    matrix[:, :2] = rot * scale
    matrix[:, 2] = dst_mean - scale * (rot @ src_mean)
    return matrix


def warp_affine_rgb(rgb: np.ndarray, matrix: np.ndarray, out_h: int, out_w: int) -> np.ndarray:
    """Bilinear inverse-map warp of an RGB image through a 2x3 src->dst affine."""
    lin = matrix[:, :2]
    off = matrix[:, 2]
    try:
        inv = np.linalg.inv(lin)
    except np.linalg.LinAlgError as exc:
        raise ValueError("singular alignment transform") from exc

    ys, xs = np.meshgrid(np.arange(out_h, dtype=np.float64),
                        np.arange(out_w, dtype=np.float64), indexing="ij")
    dst_pts = np.stack([xs.ravel(), ys.ravel()], axis=1) - off
    src_pts = dst_pts @ inv.T

    h, w = rgb.shape[:2]
    sx = np.clip(src_pts[:, 0], 0.0, w - 1.0)
    sy = np.clip(src_pts[:, 1], 0.0, h - 1.0)
    x0 = np.floor(sx).astype(np.int64)
    y0 = np.floor(sy).astype(np.int64)
    x1 = np.minimum(x0 + 1, w - 1)
    y1 = np.minimum(y0 + 1, h - 1)
    fx = (sx - x0)[:, None]
    fy = (sy - y0)[:, None]

    src = rgb.astype(np.float32)
    top = src[y0, x0] * (1.0 - fx) + src[y0, x1] * fx
    bottom = src[y1, x0] * (1.0 - fx) + src[y1, x1] * fx
    out = top * (1.0 - fy) + bottom * fy
    return np.clip(out, 0.0, 255.0).reshape(out_h, out_w, 3).astype(np.uint8)


def _resize_rgb(rgb: np.ndarray, new_w: int, new_h: int) -> np.ndarray:
    """High-quality resize via Pillow (bilinear), falling back to index sampling."""
    try:
        from PIL import Image
        img = Image.fromarray(rgb)
        return np.asarray(img.resize((new_w, new_h), Image.BILINEAR), dtype=np.uint8)
    except Exception:  # noqa: BLE001 — Pillow is present, but never hard-fail here
        h, w = rgb.shape[:2]
        ys = np.clip((np.arange(new_h) * h) // max(1, new_h), 0, h - 1)
        xs = np.clip((np.arange(new_w) * w) // max(1, new_w), 0, w - 1)
        return np.ascontiguousarray(rgb[ys][:, xs])


def nms(boxes: np.ndarray, scores: np.ndarray, thresh: float) -> list[int]:
    """Greedy IoU non-maximum suppression. Returns kept indices, best first."""
    if boxes.size == 0:
        return []
    x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
    areas = (x2 - x1 + 1.0) * (y2 - y1 + 1.0)
    order = scores.argsort()[::-1]
    keep: list[int] = []
    while order.size > 0:
        i = int(order[0])
        keep.append(i)
        if order.size == 1:
            break
        rest = order[1:]
        xx1 = np.maximum(x1[i], x1[rest])
        yy1 = np.maximum(y1[i], y1[rest])
        xx2 = np.minimum(x2[i], x2[rest])
        yy2 = np.minimum(y2[i], y2[rest])
        inter = np.maximum(0.0, xx2 - xx1 + 1.0) * np.maximum(0.0, yy2 - yy1 + 1.0)
        iou = inter / (areas[i] + areas[rest] - inter)
        order = rest[iou <= thresh]
    return keep


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------
def available_providers() -> list[str]:
    try:
        import onnxruntime as ort
    except ImportError as exc:
        raise OnnxRuntimeUnavailable(
            "onnxruntime is not installed. Install it with: pip install onnxruntime "
            "(or onnxruntime-gpu on a CUDA host).") from exc
    return list(ort.get_available_providers())


def preferred_providers() -> list[str]:
    """Fastest available execution provider first; CPU is always the last resort."""
    available = available_providers()
    order = ["TensorrtExecutionProvider", "CUDAExecutionProvider",
             "CoreMLExecutionProvider", "DmlExecutionProvider",
             "CPUExecutionProvider"]
    picked = [p for p in order if p in available]
    return picked or ["CPUExecutionProvider"]


def _low_memory() -> bool:
    """Whether to build sessions for a hard-capped container.

    ONNX Runtime's defaults are tuned for a workstation: the CPU BFC arena
    pre-allocates and never returns memory to the OS, memory-pattern planning
    reserves activation buffers up front, and intra-op threads are sized to the
    physical core count with per-thread scratch. On a 512 MB AppSail instance
    that overhead is the difference between serving and being OOM-killed, so it
    is switchable rather than assumed.
    """
    return os.getenv("DRISHTI_FACE_LOW_MEMORY", "").strip().lower() in (
        "1", "true", "yes", "on")


def _intra_threads() -> Optional[int]:
    """Intra-op thread cap. Each thread carries its own scratch allocation, so on
    a small instance more threads cost memory for latency we cannot use anyway."""
    raw = os.getenv("DRISHTI_FACE_ORT_INTRA_THREADS", "").strip()
    if raw:
        try:
            val = int(raw)
        except ValueError:
            return None
        return val if 1 <= val <= 64 else None
    return 1 if _low_memory() else None


def _make_session(path: str, providers: list[str]):
    import onnxruntime as ort
    opts = ort.SessionOptions()
    opts.log_severity_level = 3                      # errors only
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    # One ONNX call per HTTP request: intra-op threads help, inter-op does not.
    opts.inter_op_num_threads = 1
    threads = _intra_threads()
    if threads is not None:
        opts.intra_op_num_threads = threads
    if _low_memory():
        # Allocate per-run instead of holding a growing arena, and skip the
        # activation pre-plan. Costs some latency; keeps resident memory bounded.
        opts.enable_cpu_mem_arena = False
        opts.enable_mem_pattern = False
    return ort.InferenceSession(path, sess_options=opts, providers=providers)


@dataclass
class RawFace:
    """A detected face in SOURCE-image coordinates."""
    bbox: np.ndarray            # (4,) x1, y1, x2, y2
    score: float
    keypoints: Optional[np.ndarray]   # (5, 2) or None


# ---------------------------------------------------------------------------
# SCRFD detector
# ---------------------------------------------------------------------------
class ScrfdDetector:
    """SCRFD face detector (anchor-free, centre-offset regression per FPN stride)."""

    def __init__(self, model_path: str, providers: list[str], input_size: int = 640,
                 score_thresh: float = 0.5, nms_thresh: float = 0.4):
        self._session = _make_session(model_path, providers)
        self._input_name = self._session.get_inputs()[0].name
        self._output_names = [o.name for o in self._session.get_outputs()]
        self.input_size = int(input_size)
        self.score_thresh = float(score_thresh)
        self.nms_thresh = float(nms_thresh)
        self._lock = threading.Lock()

        # Head layout is implied by the output count (upstream SCRFD convention).
        n_out = len(self._output_names)
        if n_out == 6:
            self._fmc, self._strides, self._num_anchors, self._use_kps = 3, [8, 16, 32], 2, False
        elif n_out == 9:
            self._fmc, self._strides, self._num_anchors, self._use_kps = 3, [8, 16, 32], 2, True
        elif n_out == 10:
            self._fmc, self._strides, self._num_anchors, self._use_kps = 5, [8, 16, 32, 64, 128], 1, False
        elif n_out == 15:
            self._fmc, self._strides, self._num_anchors, self._use_kps = 5, [8, 16, 32, 64, 128], 1, True
        else:
            raise ValueError(
                f"Unrecognised SCRFD graph: {n_out} outputs. Expected 6, 9, 10 or 15.")

        # Also honour a fixed input shape baked into the graph.
        shape = self._session.get_inputs()[0].shape
        if isinstance(shape, (list, tuple)) and len(shape) == 4:
            static = [d for d in shape[2:] if isinstance(d, int) and d > 0]
            if len(static) == 2:
                self.input_size = int(min(static))

        self._anchor_cache: dict[tuple[int, int], np.ndarray] = {}

    @property
    def provides_keypoints(self) -> bool:
        return self._use_kps

    def _anchors(self, height: int, width: int, stride: int) -> np.ndarray:
        key = (height, width)
        cached = self._anchor_cache.get(key)
        if cached is not None:
            return cached
        grid = np.stack(np.mgrid[:height, :width][::-1], axis=-1).astype(np.float32)
        centres = (grid * stride).reshape(-1, 2)
        if self._num_anchors > 1:
            centres = np.stack([centres] * self._num_anchors, axis=1).reshape(-1, 2)
        self._anchor_cache[key] = centres
        return centres

    def detect(self, rgb: np.ndarray, max_faces: int = 10) -> list[RawFace]:
        size = self.input_size
        h, w = rgb.shape[:2]
        # Letterbox: preserve aspect ratio, pad bottom/right with zeros so the
        # detector never sees a distorted face.
        im_ratio = h / float(w)
        if im_ratio > 1.0:
            new_h, new_w = size, max(1, int(size / im_ratio))
        else:
            new_w, new_h = size, max(1, int(size * im_ratio))
        det_scale = new_h / float(h)

        resized = _resize_rgb(rgb, new_w, new_h)
        canvas = np.zeros((size, size, 3), dtype=np.uint8)
        canvas[:new_h, :new_w] = resized

        blob = ((canvas.astype(np.float32) - 127.5) / 128.0).transpose(2, 0, 1)[None]
        with self._lock:                     # ORT sessions are not thread-safe here
            outs = self._session.run(self._output_names, {self._input_name: blob})

        scores_all: list[np.ndarray] = []
        boxes_all: list[np.ndarray] = []
        kps_all: list[np.ndarray] = []
        for idx, stride in enumerate(self._strides):
            scores = np.asarray(outs[idx]).reshape(-1)
            bbox_preds = np.asarray(outs[idx + self._fmc]).reshape(-1, 4) * stride
            gh, gw = size // stride, size // stride
            centres = self._anchors(gh, gw, stride)
            n = min(len(centres), len(scores), len(bbox_preds))
            if n == 0:
                continue
            centres, scores, bbox_preds = centres[:n], scores[:n], bbox_preds[:n]

            keep = np.where(scores >= self.score_thresh)[0]
            if keep.size == 0:
                continue
            cx, cy = centres[keep, 0], centres[keep, 1]
            d = bbox_preds[keep]
            boxes_all.append(np.stack([cx - d[:, 0], cy - d[:, 1],
                                       cx + d[:, 2], cy + d[:, 3]], axis=-1))
            scores_all.append(scores[keep])
            if self._use_kps:
                kps_preds = np.asarray(outs[idx + self._fmc * 2]).reshape(-1, 10)[:n] * stride
                k = kps_preds[keep].reshape(-1, 5, 2)
                kps_all.append(np.stack([k[..., 0] + cx[:, None],
                                         k[..., 1] + cy[:, None]], axis=-1))

        if not boxes_all:
            return []
        boxes = np.concatenate(boxes_all, axis=0) / det_scale
        scores = np.concatenate(scores_all, axis=0)
        kpss = (np.concatenate(kps_all, axis=0) / det_scale) if kps_all else None

        order = nms(boxes, scores, self.nms_thresh)[:max(1, int(max_faces))]
        faces: list[RawFace] = []
        for i in order:
            bb = boxes[i].copy()
            bb[0] = max(0.0, min(bb[0], w - 1.0))
            bb[1] = max(0.0, min(bb[1], h - 1.0))
            bb[2] = max(0.0, min(bb[2], float(w)))
            bb[3] = max(0.0, min(bb[3], float(h)))
            if bb[2] - bb[0] < 2.0 or bb[3] - bb[1] < 2.0:
                continue
            faces.append(RawFace(bbox=bb, score=float(scores[i]),
                                 keypoints=(kpss[i] if kpss is not None else None)))
        return faces


# ---------------------------------------------------------------------------
# ArcFace recogniser
# ---------------------------------------------------------------------------
class ArcFaceRecogniser:
    """ArcFace embedding head: aligned 112x112 RGB crop -> 512-dim descriptor."""

    def __init__(self, model_path: str, providers: list[str]):
        self._session = _make_session(model_path, providers)
        inp = self._session.get_inputs()[0]
        self._input_name = inp.name
        self._output_names = [o.name for o in self._session.get_outputs()]
        self._lock = threading.Lock()

        self.input_size = RECOGNISER_INPUT
        shape = inp.shape
        if isinstance(shape, (list, tuple)) and len(shape) == 4:
            static = [d for d in shape[2:] if isinstance(d, int) and d > 0]
            if len(static) == 2:
                self.input_size = int(min(static))

        out_shape = self._session.get_outputs()[0].shape
        self.dim = int(out_shape[-1]) if isinstance(out_shape[-1], int) else 512

    def align(self, rgb: np.ndarray, face: RawFace) -> np.ndarray:
        """Canonical crop. Uses the 5-point similarity transform when keypoints
        are available; otherwise falls back to the padded bounding box."""
        size = self.input_size
        if face.keypoints is not None and len(face.keypoints) >= 5:
            ratio = size / float(RECOGNISER_INPUT)
            matrix = umeyama_similarity(
                np.asarray(face.keypoints[:5], dtype=np.float64),
                ARCFACE_TEMPLATE_112 * ratio)
            return warp_affine_rgb(rgb, matrix, size, size)

        # No landmarks: square, 1.3x-padded box crop. Measurably worse than an
        # aligned crop, which is why SCRFD's keypoint head is preferred.
        h, w = rgb.shape[:2]
        x1, y1, x2, y2 = face.bbox
        cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        half = max(x2 - x1, y2 - y1) * 0.65
        sx1 = int(max(0, round(cx - half)))
        sy1 = int(max(0, round(cy - half)))
        sx2 = int(min(w, round(cx + half)))
        sy2 = int(min(h, round(cy + half)))
        crop = rgb[sy1:max(sy1 + 1, sy2), sx1:max(sx1 + 1, sx2)]
        return _resize_rgb(crop, size, size)

    def embed(self, aligned_rgb: np.ndarray) -> np.ndarray:
        """Unit-norm descriptor for one aligned crop."""
        blob = ((aligned_rgb.astype(np.float32) - 127.5) / 127.5).transpose(2, 0, 1)[None]
        with self._lock:
            out = self._session.run(self._output_names, {self._input_name: blob})
        vec = np.asarray(out[0], dtype=np.float32).reshape(-1)
        norm = float(np.linalg.norm(vec))
        return vec if norm == 0.0 else (vec / norm).astype(np.float32)
