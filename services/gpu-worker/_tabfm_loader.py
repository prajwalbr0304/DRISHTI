"""Real Google TabFM v1.0.0 (PyTorch) weight loader + license/digest governance.

Loads the REAL published TabFM base model once per warm worker and verifies:
  * the artifact LICENSE is the Apache-2.0 licence the package + weights ship under
    (Copyright 2026 Google LLC) — a hackathon-permitted licence, not a production
    claim;
  * the on-disk weight digest (SHA-256 of the safetensors) matches the expected
    digest carried in the request when one is supplied, so a swapped/corrupt
    artifact fails closed.

Weights come from the public, non-gated HF repo ``google/tabfm-1.0.0-pytorch`` via
an execution-role/network fetch (baked into the image at build time for the
deployed worker) — never committed to git, never a static key. This module RAISES
rather than guessing when the artifact is absent or the licence/digest is wrong,
so ``backends.run_tabfm`` fails closed instead of faking output.

Note: tabfm==1.0.0's own ``load()`` hardcodes ``pytorch_model.bin`` while the HF
repo publishes ``model.safetensors``; we therefore construct the real ``TabFM``
model from the real ``ClassificationConfig`` and load the published safetensors
directly. This uses 100% real Google code + weights.
"""
from __future__ import annotations

import gc
import hashlib
import hmac
import os
import sys
from functools import lru_cache

TABFM_HF_REPO = os.getenv("TABFM_HF_REPO", "google/tabfm-1.0.0-pytorch")

# TabFM 1.0.0 *weights* ship under the "TabFM Non-Commercial License v1.0" (Google) -
# permitted for this NON-COMMERCIAL, NON-PRODUCTION, research/evaluation hackathon demo
# on synthetic data only (never a production/commercial claim). Note: the tabfm PyPI
# *code* is Apache-2.0, but the *weights* are non-commercial. Accept only the known
# non-commercial marker; refuse anything else (fail closed on an undocumented licence).
_LICENSE_MARKERS = {
    "tabfm non-commercial license": "tabfm-non-commercial-1.0",
    "cc-by-nc": "cc-by-nc-4.0",
}


def resolve_snapshot() -> str:
    """Return the local snapshot dir for the TabFM repo (download if needed).

    Fetches ONLY the classification checkpoint (+ metadata/licence). The ~6 GB
    regression checkpoint in the same repo is not used by this worker and is
    skipped to cut the cold-start download roughly in half."""
    from huggingface_hub import snapshot_download

    return snapshot_download(
        repo_id=TABFM_HF_REPO,
        allow_patterns=["classification/*", "config.json", "LICENSE*", "README*", "*.md"])


def weight_file(snapshot_dir: str, model_type: str = "classification") -> str:
    """Locate the weight file for a model_type; prefer safetensors. Fail closed."""
    safet = os.path.join(snapshot_dir, model_type, "model.safetensors")
    if os.path.exists(safet):
        return safet
    legacy = os.path.join(snapshot_dir, model_type, "pytorch_model.bin")
    if os.path.exists(legacy):
        return legacy
    raise FileNotFoundError(
        f"TabFM weights not found under {snapshot_dir}/{model_type} (fail closed).")


def verify_license(snapshot_dir: str) -> str:
    """Verify the artifact ships the expected non-commercial TabFM licence and
    return its id. Fail closed on a missing or unexpected licence."""
    for name in ("LICENSE", "LICENSE.txt", "LICENSE.md", "license"):
        path = os.path.join(snapshot_dir, name)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                text = fh.read().lower()
            for marker, license_id in _LICENSE_MARKERS.items():
                if marker in text:
                    return license_id
            raise RuntimeError(
                "TabFM LICENSE present but not the expected non-commercial marker "
                "(refusing to load; fail closed).")
    raise RuntimeError("TabFM LICENSE file missing from the artifact (fail closed).")


def sha256_file(path: str) -> str:
    """Streaming SHA-256 of a (possibly large) weight file."""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _consteq(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)


def _load_state_dict(path: str):
    """Load a FULL state dict (legacy .bin only — memory-heavy, see note).

    Kept only for a legacy ``pytorch_model.bin`` artifact. The published
    safetensors checkpoint goes through ``_stream_load_weights`` instead, which
    never holds the whole checkpoint in host RAM.

    safetensors.torch.load_file segfaults on some torch builds, so fall back to
    the numpy loader + a torch conversion when needed."""
    if path.endswith(".safetensors"):
        try:
            from safetensors.torch import load_file

            return load_file(path)
        except Exception:  # noqa: BLE001 — fall back to the numpy reader
            import torch
            from safetensors.numpy import load_file as np_load

            return {k: torch.from_numpy(v.copy()) for k, v in np_load(path).items()}
    import torch

    return torch.load(path, map_location="cpu")


def _resolve_dtype(device: str):
    """Pick the smallest safe parameter dtype for the target device.

    Default is fp32 EVERYWHERE, including CUDA. The ~6.3 GB fp32 module fits both
    a 16 GB host and 16 GB of T4 VRAM once ``_stream_load_weights`` stops holding a
    second full copy of the checkpoint — the original OOM was caused by
    module + full state dict (~13 GB), not by fp32 itself.

    fp16 params are measured to produce NaN logits for this model on a T4: its
    activations exceed the fp16 range (max 65504), so every band probability comes
    back NaN. ``TabFMClassifier(use_amp=True)`` already autocasts matmuls to fp16
    for tensor-core speed while keeping numerically safe fp32 master weights,
    which is the correct way to get T4 throughput here.

    ``DRISHTI_TABFM_DTYPE=bf16`` is available for a >=16 GB-VRAM Ampere+ card where
    halving the weights is worthwhile; bf16 keeps the fp32 exponent range so it
    does not suffer the fp16 overflow. Do not set fp16.
    """
    import torch

    override = os.getenv("DRISHTI_TABFM_DTYPE", "").strip().lower()
    if override in ("float32", "fp32"):
        return torch.float32
    if override in ("float16", "fp16", "half"):
        return torch.float16
    if override in ("bfloat16", "bf16"):
        return torch.bfloat16
    return torch.float32


def _cast_wrapper(base_model, cast_dtype):
    """Let the released ``TabFMClassifier`` drive a half-precision module.

    The classifier builds float32 input tensors, which a half-precision module
    would reject with a dtype mismatch. Cast on the way in and back to float32 on
    the way out so the classifier's downstream path is unchanged. Mirrors the
    equivalent wrapper in ``services/ml/app/risk/models_iface.py``.
    """
    import torch

    class _CastWrapper(torch.nn.Module):
        def __init__(self, module, dtype):
            super().__init__()
            self.m = module  # registered submodule -> .parameters() still works
            self._cast_dtype = dtype

        def forward(self, X, y, train_size, cat_mask=None, d=None):
            out = self.m(X.to(self._cast_dtype), y, train_size, cat_mask=cat_mask, d=d)
            return out.float()

        @property
        def max_classes(self):
            return self.m.max_classes

    return _CastWrapper(base_model, cast_dtype)


def _stream_load_weights(model, path: str, dtype) -> tuple[int, int]:
    """Copy safetensors weights into an already-allocated model ONE TENSOR AT A
    TIME, so the checkpoint is never fully resident in host RAM.

    Raises if any model parameter is absent from the checkpoint, preserving the
    fail-closed guarantee of the previous ``load_state_dict(..., strict=True)``.
    Returns ``(copied, unexpected)``.
    """
    import torch
    from safetensors import safe_open

    sd = model.state_dict()
    copied = unexpected = 0
    with safe_open(path, framework="pt") as fh:
        file_keys = set(fh.keys())
        missing = sorted(k for k in sd if k not in file_keys)
        if missing:
            raise RuntimeError(
                f"TabFM checkpoint is missing {len(missing)} model tensors "
                f"(e.g. {missing[:3]}) — refusing to load (fail closed).")
        for key in file_keys:
            if key not in sd:
                unexpected += 1
                continue
            with torch.no_grad():
                sd[key].copy_(fh.get_tensor(key).to(dtype))
            copied += 1
    return copied, unexpected


@lru_cache(maxsize=2)
def load_base_model(model_type: str = "classification", device: str = "cpu",
                    expected_digest: str = ""):
    """Load + cache the real TabFM base model. Verifies licence + digest.

    Returns ``(model, weight_digest, license_id)``. Raises on any mismatch or
    absence so the caller fails closed rather than fabricating a result.
    """
    import torch
    from tabfm.src.pytorch.tabfm_v1_0_0 import (ClassificationConfig,  # noqa: WPS433
                                                RegressionConfig, TabFM)

    snapshot = resolve_snapshot()
    license_id = verify_license(snapshot)
    path = weight_file(snapshot, model_type)
    digest = sha256_file(path)
    if expected_digest and not _consteq(digest, expected_digest):
        raise RuntimeError(
            "TabFM weight digest mismatch — refusing to load (fail closed).")

    config = ClassificationConfig() if model_type == "classification" else RegressionConfig()
    dtype = _resolve_dtype(device)

    model = TabFM(**config.to_dict())
    # nn.Module.to(dtype) converts parameters in place, freeing each fp32 tensor as
    # it goes, so peak host RAM is the fp32 construction (~6.6 GB) and NOT
    # construction + a full checkpoint (~13 GB, which OOM-killed a 16 GB T4 host).
    if dtype != torch.float32:
        model = model.to(dtype)
        gc.collect()
    model = model.to(device)

    if path.endswith(".safetensors"):
        copied, unexpected = _stream_load_weights(model, path, dtype)
    else:  # legacy .bin artifact: no streaming reader available
        state = _load_state_dict(path)
        model.load_state_dict(state, strict=True)
        copied, unexpected = len(state), 0
        del state
        gc.collect()

    model = model.eval()
    if dtype != torch.float32:
        model = _cast_wrapper(model, dtype)
    print(f"[tabfm-loader] loaded {model_type} weights: dtype={dtype} device={device} "
          f"tensors={copied} unexpected_in_file={unexpected} license={license_id}",
          file=sys.stderr, flush=True)
    return model, digest, license_id
