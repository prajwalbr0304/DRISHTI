#!/usr/bin/env python3
"""End-to-end verification of the curated-case demo against the DEPLOYED gateway.

Checks the three demo surfaces and the analytics endpoints the curated load
invalidates, plus the two guarantees that matter more than any of them:

  * the case presents as a read-only, non-synthetic, analytics-excluded record
    carrying the presumption-of-innocence notices; and
  * NO real person from the case has any biometric enrolled.

Run after `load-curated-case`, the board build and the face setup.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[3] / ".env")

DEFAULT_API = "https://dhristi-60075362708.development.catalystserverless.in/api"
CASE_ID = 100545
BOARD_ID = 90023
TIMEOUT = 120

OK, BAD = "PASS", "FAIL"
results: list[tuple[str, str, str]] = []


def check(name: str, passed: bool, detail: str = "") -> None:
    results.append((OK if passed else BAD, name, detail))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default=DEFAULT_API)
    args = ap.parse_args()
    s = requests.Session()

    def get(path: str):
        r = s.get(f"{args.api}{path}", timeout=TIMEOUT)
        return r.status_code, (r.json() if r.headers.get("content-type", "").startswith(
            "application/json") else {})

    # --- 1. the case file -----------------------------------------------------
    code, d = get(f"/cases/{CASE_ID}/detail")
    check("case detail reachable", code == 200, f"HTTP {code}")
    if code == 200:
        cv = d.get("current_version") or {}
        core = d.get("core") or {}
        check("crime number assigned by the FIR path",
              bool(core.get("crime_no")), str(core.get("crime_no")))
        check("marked curated public source",
              cv.get("record_origin") == "public_source_curated",
              str(cv.get("record_origin")))
        check("flagged NOT synthetic", cv.get("is_synthetic") is False,
              str(cv.get("is_synthetic")))
        check("read-only to operational actions", cv.get("read_only") is True,
              str(cv.get("read_only")))
        check("excluded from derived analytics",
              cv.get("excluded_from_derived_analytics") is True,
              str(cv.get("excluded_from_derived_analytics")))
        codes = {n.get("code") for n in (d.get("notices") or [])}
        check("presumption-of-innocence notice present",
              "PENDING_TRIAL" in codes, ",".join(sorted(codes)))
        check("allegation-not-finding notice present",
              "ALLEGATION_NOT_FINDING" in codes, ",".join(sorted(codes)))
        check("17 accused recorded", len(d.get("accused") or []) == 17,
              f"{len(d.get('accused') or [])} accused")
        check("victim recorded", len(d.get("victims") or []) >= 1,
              f"{len(d.get('victims') or [])} victim(s)")
        srcs = d.get("sources") or []
        check("public sources surfaced", len(srcs) == 23, f"{len(srcs)} sources")
        kinds = {x.get("record_kind") for x in srcs}
        check("no excluded/nonpublic material surfaced",
              kinds <= {"public_source_reference"}, ",".join(sorted(map(str, kinds))))

    # --- 2. the investigation board ------------------------------------------
    code, b = get(f"/boards/{BOARD_ID}")
    check("board reachable", code == 200, f"HTTP {code}")
    if code == 200:
        check("board linked to the case",
              (b.get("board") or {}).get("case_master_id") == CASE_ID,
              str((b.get("board") or {}).get("case_master_id")))
        nodes, edges = b.get("nodes") or [], b.get("edges") or []
        check("board populated", len(nodes) >= 16 and len(edges) >= 11,
              f"{len(nodes)} nodes / {len(edges)} edges")
        check("every edge is a hypothesis, not an evidence assertion",
              all(e.get("edge_class") == "hypothesis" for e in edges),
              ",".join(sorted({str(e.get('edge_class')) for e in edges})))
        attributed = sum(1 for e in edges if "NOT A FINDING" in (e.get("rationale") or ""))
        check("allegation edges carry the not-a-finding caveat", attributed >= 7,
              f"{attributed}/{len(edges)} edges")

    # --- 3. face recognition -------------------------------------------------
    code, f = get("/face/status")
    check("face engine ready", code == 200 and f.get("search_ready") is True,
          f"HTTP {code}")
    if code == 200:
        g = f.get("gallery") or {}
        check("gallery populated", (g.get("face_count") or 0) > 15000,
              f"{g.get('face_count')} faces")
        check("engine reports itself biometric (so the UI can say so)",
              (f.get("engine") or {}).get("biometric") is True)

    # --- 4. the analytics endpoints the curated load invalidates -------------
    for path in ("/geo/hotspots?limit=50", "/geo/alerts?limit=50",
                 "/governance/snapshots", "/governance/predictions",
                 "/workload/models", "/workload/predictions", "/workload/evaluation",
                 "/forecast/map?layer=fused"):
        code, _ = get(path)
        check(f"analytics: {path.split('?')[0]}", code == 200, f"HTTP {code}")

    # --- 5. THE GUARANTEE: no biometric for any real person on the case ------
    from app import db
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT COUNT(*) FROM "PersonFaceEmbedding" WHERE "CanonicalPersonID" IN '
                '(SELECT "CanonicalPersonID" FROM "CasePartyRole" WHERE "CaseMasterID"=%s '
                'AND "CanonicalPersonID" IS NOT NULL)', (CASE_ID,))
            n = int(cur.fetchone()[0])
            check("NO biometric enrolled for any case party", n == 0,
                  f"{n} embeddings")
            cur.execute(
                'SELECT "DisplayLabel","IsSynthetic" FROM "CanonicalPerson" '
                'WHERE "PublicRef"=%s', ("SYN-PERSON-9000001",))
            row = cur.fetchone()
            check("face demo persona is marked synthetic",
                  bool(row) and row[1] is True, str(row[0]) if row else "missing")

    width = max(len(n) for _, n, _ in results) + 2
    print()
    for status, name, detail in results:
        print(f"  [{status}] {name:<{width}} {detail}")
    failed = [r for r in results if r[0] == BAD]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    if failed:
        print(json.dumps([{"check": n, "detail": d} for _, n, d in failed], indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
