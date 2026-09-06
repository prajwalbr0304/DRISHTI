"""Resolution (and optional fetch) of the ONNX face-model files.

The face encoder needs two graphs from an InsightFace "model pack":

  * a DETECTOR   — SCRFD, which locates every face and its 5 keypoints;
  * a RECOGNISER — ArcFace, which turns an aligned 112x112 crop into a 512-dim
                   unit-norm identity descriptor.

Weights are NOT vendored (hundreds of MB) and are NEVER downloaded on the request
path — a first API call must not block on ~275 MB of network I/O, and silent
egress from a request handler is not something an operator should have to
discover. Instead:

    python -m app.batch face-models --pack buffalo_l     # explicit, one time

``GET /face/status`` reports ``models_present`` so the UI can say exactly what is
missing. Search paths are checked in order, and an existing ``~/.insightface``
download is reused so this never duplicates weights the host already has.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Pinned upstream release (deepinsight/insightface v0.7 assets). Overridable for
# air-gapped hosts that mirror the packs internally.
DEFAULT_MODEL_BASE_URL = (
    "https://github.com/deepinsight/insightface/releases/download/v0.7/")

#: pack -> (detector filename, recogniser filename, approx zip MB)
PACKS: dict[str, tuple[str, str, int]] = {
    # ArcFace ResNet-50 (w600k_r50) + SCRFD-10GF. The accuracy default.
    "buffalo_l": ("det_10g.onnx", "w600k_r50.onnx", 275),
    # MobileFaceNet (w600k_mbf) + SCRFD-500MF. ~4x faster, marginally less
    # accurate; still a 512-dim ArcFace space.
    "buffalo_s": ("det_500m.onnx", "w600k_mbf.onnx", 122),
}
DEFAULT_PACK = "buffalo_l"

# An ONNX graph smaller than this is a truncated/failed download, not a model.
_MIN_MODEL_BYTES = 512 * 1024


class FaceModelsMissing(RuntimeError):
    """The ONNX model files are not present on this host."""


@dataclass(frozen=True)
class FaceModelBundle:
    pack: str
    detector: Path
    recogniser: Path
    directory: Path

    def describe(self) -> dict:
        return {
            "pack": self.pack,
            "directory": str(self.directory),
            "detector": self.detector.name,
            "recogniser": self.recogniser.name,
        }


def _candidate_dirs(pack: str) -> list[Path]:
    """Directories to search, most specific first."""
    dirs: list[Path] = []
    explicit = os.getenv("DRISHTI_FACE_MODEL_DIR", "").strip()
    if explicit:
        p = Path(explicit).expanduser()
        # Accept either the pack directory itself or a parent holding packs.
        dirs += [p, p / pack]
    ih = os.getenv("INSIGHTFACE_HOME", "").strip()
    if ih:
        dirs.append(Path(ih).expanduser() / "models" / pack)
    dirs.append(Path.home() / ".insightface" / "models" / pack)
    dirs.append(Path.home() / ".drishti" / "face-models" / pack)
    seen: set[Path] = set()
    unique: list[Path] = []
    for d in dirs:
        if d not in seen:
            seen.add(d)
            unique.append(d)
    return unique


def _valid(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size >= _MIN_MODEL_BYTES
    except OSError:
        return False


def install_dir(pack: str = DEFAULT_PACK) -> Path:
    """Where a fetch would place the pack (the first writable candidate)."""
    explicit = os.getenv("DRISHTI_FACE_MODEL_DIR", "").strip()
    if explicit:
        return Path(explicit).expanduser() / pack
    ih = os.getenv("INSIGHTFACE_HOME", "").strip()
    if ih:
        return Path(ih).expanduser() / "models" / pack
    return Path.home() / ".drishti" / "face-models" / pack


def locate(pack: str = DEFAULT_PACK) -> Optional[FaceModelBundle]:
    """Find an already-present pack. None when it is not installed."""
    if pack not in PACKS:
        raise FaceModelsMissing(
            f"Unknown face model pack '{pack}'. Known packs: {', '.join(PACKS)}.")
    det_name, rec_name, _ = PACKS[pack]
    for d in _candidate_dirs(pack):
        det, rec = d / det_name, d / rec_name
        if _valid(det) and _valid(rec):
            return FaceModelBundle(pack=pack, detector=det, recogniser=rec, directory=d)
    return None


def require(pack: str = DEFAULT_PACK) -> FaceModelBundle:
    """Locate the pack or raise with the exact remediation command."""
    bundle = locate(pack)
    if bundle:
        return bundle
    det_name, rec_name, mb = PACKS[pack]
    searched = "\n  ".join(str(d) for d in _candidate_dirs(pack))
    raise FaceModelsMissing(
        f"Face model pack '{pack}' ({det_name} + {rec_name}, ~{mb} MB) is not "
        f"installed. Fetch it once with:\n"
        f"  python -m app.batch face-models --pack {pack}\n"
        f"or set DRISHTI_FACE_MODEL_DIR to a directory that already holds it.\n"
        f"Searched:\n  {searched}")


def fetch(pack: str = DEFAULT_PACK, *, force: bool = False,
          log=print) -> FaceModelBundle:
    """Download + extract a model pack. Explicit operator action, never implicit.

    Extraction is flattened and filtered to the two ``.onnx`` files this service
    uses, so a malicious archive cannot write outside the target directory
    (no path traversal via member names, no symlinks, no other file types).
    """
    if pack not in PACKS:
        raise FaceModelsMissing(
            f"Unknown face model pack '{pack}'. Known packs: {', '.join(PACKS)}.")
    if not force:
        existing = locate(pack)
        if existing:
            log(f"  {pack} already present at {existing.directory}")
            return existing

    import urllib.request

    det_name, rec_name, approx_mb = PACKS[pack]
    base = os.getenv("DRISHTI_FACE_MODEL_URL", "").strip() or DEFAULT_MODEL_BASE_URL
    if not base.endswith("/"):
        base += "/"
    url = f"{base}{pack}.zip"
    if not url.lower().startswith("https://"):
        raise FaceModelsMissing(
            f"Refusing to fetch face models over a non-HTTPS URL: {url}")

    target = install_dir(pack)
    target.mkdir(parents=True, exist_ok=True)
    log(f"  downloading {pack}.zip (~{approx_mb} MB) from {base} ...")

    with tempfile.TemporaryDirectory(prefix="drishti-face-") as tmp:
        archive = Path(tmp) / f"{pack}.zip"
        with urllib.request.urlopen(url, timeout=180) as resp:  # noqa: S310 (pinned https)
            if getattr(resp, "status", 200) != 200:
                raise FaceModelsMissing(f"Download failed with HTTP {resp.status}: {url}")
            with archive.open("wb") as fh:
                shutil.copyfileobj(resp, fh, length=1024 * 1024)
        log(f"  extracting {archive.stat().st_size / 1e6:.0f} MB ...")

        wanted = {det_name, rec_name}
        found: set[str] = set()
        with zipfile.ZipFile(archive) as zf:
            for member in zf.infolist():
                leaf = Path(member.filename).name
                if member.is_dir() or leaf not in wanted:
                    continue
                dest = target / leaf
                with zf.open(member) as src, dest.open("wb") as out:
                    shutil.copyfileobj(src, out, length=1024 * 1024)
                found.add(leaf)
        missing = wanted - found
        if missing:
            raise FaceModelsMissing(
                f"{pack}.zip did not contain {', '.join(sorted(missing))}.")

    bundle = locate(pack)
    if not bundle:
        raise FaceModelsMissing(
            f"Extracted {pack} to {target} but the files failed validation "
            "(truncated download?). Re-run with --force.")
    log(f"  {pack} ready at {bundle.directory}")
    return bundle


def status(pack: str = DEFAULT_PACK) -> dict:
    """Presence report for /face/status (never raises)."""
    try:
        bundle = locate(pack)
    except FaceModelsMissing:
        return {"pack": pack, "present": False, "known_pack": False,
                "install_command": None, "searched": []}
    det_name, rec_name, mb = PACKS[pack]
    return {
        "pack": pack,
        "known_pack": True,
        "present": bundle is not None,
        "directory": str(bundle.directory) if bundle else str(install_dir(pack)),
        "detector": det_name,
        "recogniser": rec_name,
        "approx_download_mb": mb,
        "install_command": None if bundle else
            f"python -m app.batch face-models --pack {pack}",
        "searched": [] if bundle else [str(d) for d in _candidate_dirs(pack)],
    }
