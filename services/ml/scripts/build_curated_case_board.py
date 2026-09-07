#!/usr/bin/env python3
"""Build the Investigation Board for the curated public-source case.

Why this talks to the DEPLOYED API instead of the database: the board tables are
Catalyst Data Store-native (see app/datastore/board_schema.py), and outside AppSail
``get_repository()`` hands back an in-memory fake. Writing the board locally would
therefore build it into a process that exits. The gateway is the only route to the
board a browser will actually load.

Node labels and the accused numbering are read from the ingested case rather than
restated here, so the board cannot drift from the case record.

EVERY EDGE IS A HYPOTHESIS EDGE with a rationale naming its source. Nothing on this
board asserts a proven fact: charges are framed, all seventeen accused pleaded not
guilty, and the trial is pending.

Usage:
    python scripts/build_curated_case_board.py                     # build/refresh
    python scripts/build_curated_case_board.py --api <gateway-url>
    python scripts/build_curated_case_board.py --dry-run           # print the plan
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[3] / ".env")

DEFAULT_API = "https://dhristi-60075362708.development.catalystserverless.in/api"
BOARD_TITLE = "Renukaswamy homicide — curated public-source record"
CASE_EXTERNAL_ID = "PUBLIC-CURATED-RENUKASWAMY-2024"
TIMEOUT = 60

# The standing caveat carried onto the board itself, so it travels with any
# screenshot of it rather than living only on the case file.
BOARD_DESCRIPTION = (
    "CURATED PUBLIC-SOURCE RECORD. Reconstructed from published court records; "
    "read-only and excluded from derived analytics. Every relationship on this "
    "board is the PROSECUTION'S CASE or a published report, not a finding. Charges "
    "were framed on 3 Nov 2025 and all 17 accused pleaded NOT GUILTY. The trial is "
    "pending; no accused has been convicted. No biometric material is held for any "
    "person on this board."
)


def load_case_from_db() -> dict[str, Any]:
    """Read the ingested case so the board mirrors it exactly."""
    from app import db

    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT "CaseMasterID" FROM "IntakeDraft" WHERE "IdempotencyKey"=%s '
                'AND "CaseMasterID" IS NOT NULL ORDER BY "IntakeDraftID" DESC LIMIT 1',
                (CASE_EXTERNAL_ID,))
            row = cur.fetchone()
            if not row:
                raise SystemExit(
                    "curated case not found — run: python -m app.batch load-curated-case")
            case_id = int(row[0])

            cur.execute(
                'SELECT "CrimeNo" FROM "CaseMaster" WHERE "CaseMasterID"=%s', (case_id,))
            crime_no = cur.fetchone()[0]

            cur.execute(
                'SELECT r."RoleType", r."PartyLabel", r."CanonicalPersonID", cp."Attributes" '
                'FROM "CasePartyRole" r '
                'LEFT JOIN "CanonicalPerson" cp '
                'ON cp."CanonicalPersonID"=r."CanonicalPersonID" '
                'WHERE r."CaseMasterID"=%s ORDER BY r."SequenceNo" NULLS LAST', (case_id,))
            parties = [
                {"role": r[0], "label": r[1], "person_id": r[2], "attrs": r[3] or {}}
                for r in cur.fetchall()
            ]
    return {"case_master_id": case_id, "crime_no": crime_no, "parties": parties}


class BoardApi:
    def __init__(self, base: str, dry_run: bool = False):
        self.base = base.rstrip("/")
        self.dry_run = dry_run
        self.s = requests.Session()
        self._fake_id = 0

    def _post(self, path: str, body: dict) -> dict:
        if self.dry_run:
            self._fake_id += 1
            print(f"POST {path}\n     {json.dumps(body, ensure_ascii=False)[:150]}")
            return {"board": {"board_id": self._fake_id},
                    "target_id": self._fake_id}
        r = self.s.post(f"{self.base}{path}", json=body, timeout=TIMEOUT)
        if r.status_code >= 400:
            raise SystemExit(f"POST {path} -> {r.status_code}\n{r.text[:600]}")
        return r.json()

    def find_board(self, title: str) -> Optional[int]:
        if self.dry_run:
            return None
        r = self.s.get(f"{self.base}/boards", timeout=TIMEOUT)
        r.raise_for_status()
        for item in r.json().get("items", []):
            if item.get("title") == title:
                return int(item["board_id"])
        return None

    def board_detail(self, board_id: int) -> dict:
        r = self.s.get(f"{self.base}/boards/{board_id}", timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()

    def create_board(self, case_id: int) -> int:
        out = self._post("/boards", {
            "title": BOARD_TITLE,
            "description": BOARD_DESCRIPTION,
            "case_master_id": case_id,
            "visibility": "private",
        })
        # BoardDetail nests the summary; every MUTATING call instead returns a
        # MutationResult whose new object id is carried in `target_id`.
        return int(out["board"]["board_id"])

    def add_node(self, board_id: int, kind: str, label: str, x: float, y: float,
                 ref_table: Optional[str] = None, ref_id: Optional[str] = None,
                 snapshot: Optional[dict] = None) -> int:
        body: dict[str, Any] = {"node_kind": kind, "label": label[:255],
                                "pos_x": x, "pos_y": y}
        if ref_table and ref_id is not None:
            body["ref_table"] = ref_table
            body["ref_id"] = str(ref_id)
        if snapshot:
            body["snapshot"] = snapshot
        out = self._post(f"/boards/{board_id}/nodes", body)
        return int(out["target_id"])

    def add_edge(self, board_id: int, src: int, dst: int, label: str,
                 relationship: str, rationale: str, directed: bool = True) -> int:
        out = self._post(f"/boards/{board_id}/edges", {
            "source_node_id": src, "target_node_id": dst,
            "edge_class": "hypothesis",
            "label": label[:255], "relationship_type": relationship[:120],
            "directed": directed, "rationale": rationale[:4000],
        })
        return int(out["target_id"])


# Sources cited on the edges, kept short so the rationale stays readable.
CITE_SC = "Supreme Court, 2025 INSC 979 (14 Aug 2025) — bail findings only"
CITE_CS = "Charge sheet as reported (4 Sep 2024, 3,991 pages)"
CITE_FRAMED = "Charges framed 3 Nov 2025; all accused pleaded not guilty"
ALLEGED = "PROSECUTION CASE, NOT A FINDING. "


def build(api: BoardApi, case: dict) -> dict[str, Any]:
    case_id = case["case_master_id"]
    board_id = api.find_board(BOARD_TITLE)
    reused = board_id is not None
    if board_id is None:
        board_id = api.create_board(case_id)
    else:
        detail = api.board_detail(board_id)
        if detail.get("nodes"):
            return {"board_id": board_id, "reused": True,
                    "nodes": len(detail.get("nodes") or []),
                    "edges": len(detail.get("edges") or []),
                    "note": "board already populated — left untouched"}

    parties = case["parties"]
    victim = next((p for p in parties if p["role"] == "victim"), None)
    complainant = next((p for p in parties if p["role"] == "complainant"), None)
    accused = [p for p in parties if p["role"] == "accused"]
    # Named accused first; the numbered placeholders carry no identity to plot.
    named = [p for p in accused if not p["attrs"].get("name_withheld_in_pack")]

    nodes: dict[str, int] = {}

    # --- the case, centre ---
    nodes["case"] = api.add_node(
        board_id, "case", f"FIR {case['crime_no']} — Renukaswamy homicide", 0, 0,
        ref_table="CaseMaster", ref_id=case_id)

    # --- the standing caveat, pinned top-left so it is impossible to miss ---
    nodes["caveat"] = api.add_node(
        board_id, "note", "READ FIRST — status of this board", -560, -300,
        snapshot={"text": BOARD_DESCRIPTION})

    # --- victim ---
    if victim:
        nodes["victim"] = api.add_node(
            board_id, "victim", f"{victim['label']} (deceased, 33)", -300, 60,
            ref_table="CanonicalPerson", ref_id=victim["person_id"])
        api.add_edge(board_id, nodes["case"], nodes["victim"],
                     "victim in", "victim_of",
                     f"{ALLEGED}Deceased. Body recovered 9 Jun 2024. {CITE_CS}")

    # --- complainant ---
    if complainant:
        nodes["complainant"] = api.add_node(
            board_id, "complainant", complainant["label"], -300, 220,
            ref_table="CanonicalPerson", ref_id=complainant["person_id"])
        api.add_edge(board_id, nodes["case"], nodes["complainant"],
                     "complainant", "complainant_of",
                     "Next of kin of the deceased. No contact details are held.")

    # --- accused, fanned to the right ---
    for i, p in enumerate(named):
        num = p["attrs"].get("accused_number", "A?")
        key = f"accused:{num}"
        nodes[key] = api.add_node(
            board_id, "accused", f"{num} — {p['label']}", 360,
            -260 + i * 105, ref_table="CanonicalPerson", ref_id=p["person_id"])
        rationale = (
            f"{ALLEGED}Named Accused No. {num.lstrip('A')} and charged on "
            f"3 Nov 2025; pleaded NOT GUILTY and has not been convicted. {CITE_CS}"
        )
        if num == "A2":
            rationale += f" Bail cancelled: {CITE_SC}."
        if num == "A14":
            rationale += (" Permitted to turn approver on conditions (Aug 2026,"
                          " 59th City Civil and Sessions Court); an approver's"
                          " account is untested evidence.")
        api.add_edge(board_id, nodes["case"], nodes[key],
                     f"accused ({num})", "accused_in", rationale)

    # --- the three locations from the published sequence ---
    places = [
        ("abduction", "Chitradurga — alleged abduction point (7 Jun 2024)",
         -640, -60,
         f"{ALLEGED}Alleged abduction of the deceased from Chitradurga. {CITE_CS}"),
        ("scene", "Pattanagere, RR Nagar — alleged assault site (8 Jun 2024)",
         -640, 100,
         f"{ALLEGED}Shed alleged as the assault site. Locality-level reference "
         f"only (OpenStreetMap/Nominatim), NOT a verified scene coordinate. {CITE_CS}"),
        ("recovery", "Kamakshipalya, Bengaluru — body recovered (9 Jun 2024)",
         -640, 260,
         "Recovery of the body from a stormwater drain, as reported. "
         "Locality-level reference only."),
    ]
    for key, label, x, y, why in places:
        nodes[key] = api.add_node(board_id, "location", label, x, y)
        if victim and "victim" in nodes:
            api.add_edge(board_id, nodes["victim"], nodes[key],
                         key.replace("_", " "), f"location_{key}", why)

    # --- procedural notes: the facts a reviewer needs beside the network ---
    proc = [
        ("Charge sheet", "3,991 pages, 7 volumes, 10 files, filed 4 Sep 2024 before "
                         "the 24th Additional Chief Metropolitan Magistrate. 231 "
                         "witnesses; 97 independent; 27 statements under s.164 CrPC. "
                         "A supplementary charge sheet of 1,300+ pages followed in "
                         "Nov 2024. The authenticated charge sheets remain in court "
                         "custody and are NOT held here."),
        ("Charges framed", "3 Nov 2025, Sessions Court, Bengaluru. All 17 accused "
                           "charged under provisions including IPC 302, kidnapping/"
                           "abduction, IPC 120B and destruction of evidence. Every "
                           "accused pleaded NOT GUILTY. Trial pending; the Supreme "
                           "Court has directed it be expedited."),
        ("Evidence not held", "CCTV masters, forensic phone images, FSL reports, the "
                              "post-mortem, CDRs, witness depositions and exhibits "
                              "P1-P13 / MO1-MO8 / D1-D22 are in police or court "
                              "custody. This record links published references only; "
                              "graphic leaked material is excluded entirely."),
    ]
    for i, (title, text) in enumerate(proc):
        nodes[f"note:{i}"] = api.add_node(
            board_id, "note", title, 900, -240 + i * 240,
            snapshot={"text": text})

    detail = api.board_detail(board_id) if not api.dry_run else {}
    return {
        "board_id": board_id,
        "reused": reused,
        "case_master_id": case_id,
        "crime_no": case["crime_no"],
        "nodes": len(detail.get("nodes") or nodes),
        "edges": len(detail.get("edges") or []),
        "named_accused_plotted": len(named),
        "accused_total_on_case": len(accused),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default=DEFAULT_API)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    case = load_case_from_db()
    api = BoardApi(args.api, dry_run=args.dry_run)
    result = build(api, case)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
