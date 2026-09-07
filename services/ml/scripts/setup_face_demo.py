#!/usr/bin/env python3
"""Set up the face-recognition demo on a SYNTHETIC persona.

Why a synthetic persona and not the accused from the curated case: 1:N face search
is biometric identification. The accused in that case is an undertrial with no
conviction, so enrolling his likeness into a police gallery would assert exactly
what the case record is built to deny. It would also be a meaningless measurement —
descriptors taken from an AI-generated likeness of a person do not correspond to
that person's real descriptors, so a "match" would prove only that a fabricated
face matches itself while LOOKING like a real identification. The curated case
therefore holds no biometric material at all (asserted by the loader and checked
after ingestion), and the face pipeline is exercised here instead.

What this proves, which is the whole point of the capability:

    detect -> 512-d ArcFace descriptor -> 1:N over the live gallery ->
    ranked candidates with calibrated similarity -> HUMAN decision -> audit row

The probe is deliberately NOT the enrolled bytes. The portrait is re-encoded into
two different variants (different resolution, different JPEG quantisation), so the
retrieval is a real descriptor comparison against 15k+ gallery entries rather than a
hash match on identical input.

Usage:
    python scripts/setup_face_demo.py                  # build + run the demo
    python scripts/setup_face_demo.py --source <path>  # override the portrait
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path
from typing import Any, Optional

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
load_dotenv(REPO / ".env")

DEFAULT_API = "https://dhristi-60075362708.development.catalystserverless.in/api"
DEFAULT_SOURCE = Path.home() / "Desktop" / "86a51a30-9711-4106-9313-5a902031e6cd.png"
ASSET_DIR = REPO / "research" / "renukaswamy-case-evidence" / "assets"
GALLERY_IMG = ASSET_DIR / "synthetic-persona-gallery.jpg"
PROBE_IMG = ASSET_DIR / "synthetic-persona-probe.jpg"

# The persona. Named in the same style as the rest of the synthetic corpus
# (SYN-PERSON-*) and marked synthetic in three places: the public ref, the display
# label, and IsSynthetic. Nothing about this record refers to a real person.
PERSONA_REF = "SYN-PERSON-9000001"
PERSONA_LABEL = "Anil Kumar Gowda (SYNTHETIC PERSONA)"
PERSONA_ATTRS = {
    "is_synthetic": True,
    "not_a_real_person": True,
    "portrait_provenance": (
        "AI-generated portrait supplied for demonstration. Not a photograph of any "
        "real individual and not a likeness held for identification purposes."
    ),
    "demo_purpose": (
        "Exercises the face-search pipeline (detect, descriptor, 1:N retrieval, "
        "human review, audit) without enrolling any real person's biometric."
    ),
}
TIMEOUT = 120


def build_variants(source: Path) -> dict[str, Any]:
    """Re-encode the portrait into a gallery image and a DIFFERENT probe image.

    The service caps an upload at ~1.2 MB and recommends a 1280px long edge, so the
    source PNG has to be re-encoded anyway. Producing two variants at different
    sizes turns that into something useful: the probe is not the bytes that were
    enrolled, so the search has to succeed on descriptor similarity.
    """
    from PIL import Image

    if not source.exists():
        raise SystemExit(
            f"source portrait not found: {source}\n"
            "The demo portraits are git-ignored on purpose (see .gitignore: this is a "
            "public repository and they depict real people). Pass any portrait with "
            "--source <path>; the persona is a demo identity, so any face works.")
    ASSET_DIR.mkdir(parents=True, exist_ok=True)

    img = Image.open(source).convert("RGB")
    out: dict[str, Any] = {"source": str(source), "source_size": img.size}

    for path, long_edge, quality in ((GALLERY_IMG, 1280, 92), (PROBE_IMG, 640, 78)):
        v = img.copy()
        scale = long_edge / max(v.size)
        if scale < 1:
            v = v.resize((round(v.width * scale), round(v.height * scale)),
                         Image.LANCZOS)
        v.save(path, "JPEG", quality=quality, optimize=True)
        out[path.stem] = {"path": str(path.relative_to(REPO)),
                          "size": v.size, "bytes": path.stat().st_size}
    return out


def b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def ensure_persona() -> int:
    """Create (or reuse) the synthetic persona in the shared operational database."""
    from app import db

    with db.rw_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT "CanonicalPersonID" FROM "CanonicalPerson" WHERE "PublicRef"=%s',
                (PERSONA_REF,))
            row = cur.fetchone()
            if row:
                cur.execute(
                    'UPDATE "CanonicalPerson" SET "DisplayLabel"=%s, "Attributes"=%s, '
                    '"IsSynthetic"=TRUE WHERE "CanonicalPersonID"=%s',
                    (PERSONA_LABEL, json.dumps(PERSONA_ATTRS), int(row[0])))
                return int(row[0])
            cur.execute(
                'INSERT INTO "CanonicalPerson" ("PublicRef","DisplayLabel","IsUnknown",'
                '"ResolutionStatus","Attributes","IsSynthetic") '
                'VALUES (%s,%s,FALSE,%s,%s,TRUE) RETURNING "CanonicalPersonID"',
                (PERSONA_REF, PERSONA_LABEL, "canonical", json.dumps(PERSONA_ATTRS)))
            return int(cur.fetchone()[0])


class FaceApi:
    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self.s = requests.Session()

    def _call(self, method: str, path: str, body: Optional[dict] = None) -> dict:
        r = self.s.request(method, f"{self.base}{path}", json=body, timeout=TIMEOUT)
        if r.status_code >= 400:
            raise SystemExit(f"{method} {path} -> {r.status_code}\n{r.text[:800]}")
        return r.json()

    def status(self) -> dict:
        return self._call("GET", "/face/status")

    def enrol(self, cpid: int, image: Path, label: str) -> dict:
        return self._call("POST", "/face/enrol", {
            "image_base64": b64(image), "canonical_person_id": cpid,
            "image_label": label, "make_primary": True,
            "capture_mode": "upload", "actor": "demo.face.setup",
        })

    def search(self, image: Path, top_k: int = 5) -> dict:
        return self._call("POST", "/face/search", {
            "image_base64": b64(image), "top_k": top_k,
            "capture_mode": "upload", "origin": "standalone",
            "actor": "demo.face.setup",
        })

    def decide(self, probe_ref: str, cpid: int) -> dict:
        return self._call("POST", f"/face/probes/{probe_ref}/decision", {
            "decision": "confirmed", "canonical_person_id": cpid,
            # Off on purpose: enrolling a probe is a deliberate act, not a side
            # effect of accepting a shortlist entry.
            "enrol_probe": False,
            "note": "Synthetic persona demo — reviewer accepted the top candidate.",
            "actor": "demo.face.review",
        })

    def probes(self, limit: int = 5) -> dict:
        return self._call("GET", f"/face/probes?limit={limit}")

    def faces_for(self, cpid: int) -> dict:
        return self._call("GET", f"/face/persons/{cpid}/faces")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default=DEFAULT_API)
    ap.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    args = ap.parse_args()

    api = FaceApi(args.api)
    st = api.status()
    if not st.get("search_ready"):
        raise SystemExit(f"face search not ready: {st.get('unavailable_reason')}")
    print(f"engine   : {st['engine']['name']} ({st['engine']['dim']}-d, "
          f"biometric={st['engine']['biometric']}, pack={st['engine']['pack']})")
    print(f"threshold: match>={st['engine']['recommended_threshold']} "
          f"strong>={st['engine']['strong_threshold']}")
    print(f"gallery  : {st['gallery']['face_count']} faces / "
          f"{st['gallery']['person_count']} persons\n")

    variants = build_variants(args.source)
    print("image variants (probe is NOT the enrolled bytes):")
    for key in ("synthetic-persona-gallery", "synthetic-persona-probe"):
        v = variants[key]
        print(f"  {key:<30} {v['size']}  {v['bytes']:,} bytes")

    cpid = ensure_persona()
    print(f"\npersona  : CanonicalPersonID={cpid} {PERSONA_LABEL} ({PERSONA_REF})")

    enrolled = api.enrol(cpid, GALLERY_IMG, "Synthetic persona — AI-generated portrait")
    face = enrolled["face"]
    print(f"enrol    : created={enrolled['created']} face_id="
          f"{face['person_face_embedding_id']} detector={enrolled.get('detector_score')} "
          f"quality={enrolled.get('quality')} gallery_for_person="
          f"{enrolled['gallery_face_count']}")

    res = api.search(PROBE_IMG, top_k=5)
    print(f"\nsearch   : matched={res['matched']} threshold={res['threshold']} "
          f"over {res['gallery_face_count']} faces / {res['gallery_person_count']} "
          f"persons in {res['latency_ms']}ms")
    print(f"probe_ref: {res['probe']['probe_ref']}")
    print("ranked candidates:")
    for i, m in enumerate(res.get("matches") or [], start=1):
        print(f"  {i}. cpid={m.get('canonical_person_id'):<8} "
              f"sim={m.get('similarity'):.4f} band={m.get('band')!r} "
              f"{str(m.get('display_label'))[:44]}")
    print(f"\ndisclaimer: {res['disclaimer']}")

    decision = api.decide(res["probe"]["probe_ref"], cpid)
    print(f"\nreview   : decision={decision['decision']} "
          f"cpid={decision.get('canonical_person_id')} "
          f"enrolled_face_id={decision.get('enrolled_face_id')}")

    trail = api.probes(limit=3)
    print("\naudit trail (most recent probes):")
    for p in (trail.get("items") or trail.get("probes") or [])[:3]:
        print(f"  {p.get('probe_ref')} decision={p.get('decision')!r} "
              f"origin={p.get('origin')!r} actor={p.get('actor')!r} "
              f"at={p.get('created_at')}")

    print("\n" + json.dumps({
        "persona_canonical_person_id": cpid,
        "persona_public_ref": PERSONA_REF,
        "probe_ref": res["probe"]["probe_ref"],
        "matched": res["matched"],
        "top_similarity": (res.get("matches") or [{}])[0].get("similarity"),
        "real_person_biometrics_enrolled": False,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
