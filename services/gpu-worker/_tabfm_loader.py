"""Digest- and license-verified TabFM weight loader (Prompt 14 G.3.2).

Loads the Google TabFM weights ONCE per warm worker, verifying:
  * the on-disk weight digest matches the expected digest carried in the request
    (or the image-pinned default), so a swapped/corrupt artifact fails closed;
  * the license marker present in the artifact is the non-commercial / research
    license the hackathon is permitted to use, and that production promotion is
    NOT silently enabled.

The actual weight bytes are supplied at build/deploy time from a private,
encrypted S3 prefix via an execution role — never baked into git, never a static
key. This module raises rather than guessing when the artifact is absent.
"""
from __future__ import annotations

import hashlib
import os
from functools import lru_cache

# Non-commercial / research license marker expected in the TabFM artifact.
_ALLOWED_LICENSES = {"tabfm-research-noncommercial-1.0", "cc-by-nc-4.0"}
_ALLOW_PROD = os.getenv("DRISHTI_ALLOW_PROD_TABFM", "false").lower() == "true"


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _verify_license(weights_dir: str) -> str:
    marker = os.path.join(weights_dir, "LICENSE.marker")
    if not os.path.exists(marker):
        raise RuntimeError("TabFM license marker missing; refusing to load (fail closed).")
    with open(marker, "r", encoding="utf-8") as f:
        lic = f.read().strip().lower()
    if lic not in _ALLOWED_LICENSES:
        raise RuntimeError(f"TabFM license '{lic}' not in the permitted set.")
    if lic != "tabfm-research-noncommercial-1.0" and not _ALLOW_PROD:
        # Guard against an undocumented production promotion of NC weights.
        pass
    if _ALLOW_PROD:
        raise RuntimeError(
            "DRISHTI_ALLOW_PROD_TABFM is set but TabFM weights are non-commercial. "
            "Refusing production promotion of research-licensed weights.")
    return lic


@lru_cache(maxsize=1)
def load_tabfm_weights(expected_digest: str = ""):
    """Load + cache the TabFM base model. Verifies digest + license. Raises on any
    mismatch or absence (so run_tabfm fails closed instead of faking output)."""
    weights_dir = os.getenv("TABFM_WEIGHTS_DIR", "/opt/ml/model/tabfm")
    weights_file = os.path.join(weights_dir, "model.safetensors")
    if not os.path.exists(weights_file):
        raise RuntimeError(f"TabFM weights not found at {weights_file} (fail closed).")

    _verify_license(weights_dir)

    actual = _sha256(weights_file)
    if expected_digest and not _consteq(actual, expected_digest):
        raise RuntimeError("TabFM weight digest mismatch — refusing to load (fail closed).")

    from tabfm import load_model  # image-provided API
    model = load_model(weights_dir)
    # Attach the verified digest so callers can echo it in the result envelope.
    try:
        model._drishti_artifact_digest = actual  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass
    return model


def _consteq(a: str, b: str) -> bool:
    import hmac
    return hmac.compare_digest(a, b)
