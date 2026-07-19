#!/usr/bin/env python3
"""Seed a clean, feature-complete demo Investigation Board into the RUNNING backend.

Board records are Data Store-native and held IN THE RUNNING SERVER'S PROCESS
(in-memory in dev), so this seeds via HTTP against a live uvicorn on :8000 — NOT
via a separate TestClient (that would populate a different process).

It builds a spacious, legible board that shows every feature:
  * a case node + a suspect, then Search Around imports the suspect's verified
    network as read-only EVIDENCE, PRUNED to a clean star (the gang-clique
    cross-links are removed so it isn't a hairball);
  * diverse node kinds (case, people, financial account, crime hotspot);
  * two HYPOTHESIS links with rationale (dashed);
  * a sticky note + a frame grouping the suspect network;
  * a Supervisor makes it unit-visible and shares it with the Analyst.

Re-run after a backend restart to recreate the board:
    python services/ml/seed_demo_board.py
"""
from __future__ import annotations

import json
import math
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"
IO = {"X-Role": "investigator", "X-Demo-Actor": "demo.investigator@drishti.local"}
SUP = {"X-Role": "supervisor", "X-Demo-Actor": "demo.supervisor@drishti.local"}

CX, CY, R = 460.0, 340.0, 300.0            # suspect network centre + radius


def _req(method: str, path: str, headers: dict, body: dict | None = None,
         optional: bool = False) -> dict | None:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        if optional:
            print(f"  (skip {method} {path}: {e.code})")
            return None
        raise SystemExit(f"{method} {path} -> {e.code}: {e.read().decode()}")


def wait_health(timeout_s: int = 40) -> None:
    for _ in range(timeout_s):
        try:
            with urllib.request.urlopen(BASE + "/health/live", timeout=3) as r:
                if r.status == 200:
                    return
        except Exception:  # noqa: BLE001
            time.sleep(1)
    raise SystemExit("backend not reachable on :8000")


def pick_refs():
    """Read the synthetic DB (read-only) to choose real objects to pin."""
    from app import db
    with db.ro_conn() as conn:
        cur = conn.cursor()
        cur.execute('SELECT "Source", count(*) FROM "NetworkEdge" GROUP BY "Source" '
                    'ORDER BY count(*) DESC LIMIT 1')
        ent_id = int(cur.fetchone()[0])
        cur.execute('SELECT "Label" FROM "EntityGraph" WHERE "EntityID"=%s', (ent_id,))
        ent_label = (cur.fetchone() or [None])[0] or f"Entity {ent_id}"
        cur.execute('SELECT "CaseMasterID","CrimeNo","PoliceStationID" FROM "CaseMaster" '
                    'WHERE "CrimeNo" IS NOT NULL ORDER BY "CaseMasterID" LIMIT 1')
        c = cur.fetchone()
        case_id, crime_no, station = int(c[0]), c[1], (int(c[2]) if c[2] is not None else None)
        cur.execute('SELECT "AccountID" FROM "FinancialAccount" LIMIT 1')
        acct = cur.fetchone()
        acct_id = int(acct[0]) if acct else None
        cur.execute('SELECT "HotspotID" FROM "CrimeHotspot" LIMIT 1')
        hot = cur.fetchone()
        hotspot_id = int(hot[0]) if hot else None
    return case_id, crime_no, station, ent_id, ent_label, acct_id, hotspot_id


def main() -> int:
    wait_health()
    case_id, crime_no, station, ent_id, ent_label, acct_id, hotspot_id = pick_refs()
    print(f"case #{case_id} ({crime_no}) · suspect #{ent_id} ({ent_label}) · "
          f"account={acct_id} · hotspot={hotspot_id}")

    board = _req("POST", "/boards", IO, {
        "title": f"Operation Nightfall — {crime_no}",
        "description": "Demo case board: suspect network, financial + geo context, "
                       "and working hypotheses (synthetic).",
        "case_master_id": case_id, "unit_id": station, "visibility": "private"})
    bid = board["board"]["board_id"]
    print(f"board #{bid} created")

    # case (top) + suspect (centre)
    case_nid = int(_req("POST", f"/boards/{bid}/nodes", IO, {
        "node_kind": "case", "ref_table": "CaseMaster", "ref_id": str(case_id),
        "pos_x": CX, "pos_y": CY - 400})["target_id"])
    focal_nid = int(_req("POST", f"/boards/{bid}/nodes", IO, {
        "node_kind": "entity", "ref_table": "EntityGraph", "ref_id": str(ent_id),
        "pos_x": CX, "pos_y": CY})["target_id"])

    # Search Around -> import the suspect's verified network as evidence
    _req("POST", f"/boards/{bid}/import/subgraph", IO,
         {"node_id": focal_nid, "hops": 1, "max_neighbors": 5})

    detail = _req("GET", f"/boards/{bid}", IO)
    # PRUNE the gang-clique cross-links: keep only edges incident to the suspect
    # (a clean star), so the board reads clearly instead of as a hairball.
    pruned = 0
    for e in detail["edges"]:
        if e["edge_class"] == "evidence" and focal_nid not in (e["source_node_id"], e["target_node_id"]):
            _req("DELETE", f"/boards/{bid}/edges/{e['board_edge_id']}", IO)
            pruned += 1
    # spread the neighbours evenly on a wide circle around the suspect
    neighbours = [n for n in detail["nodes"]
                  if n["ref_table"] == "EntityGraph" and n["board_node_id"] != focal_nid]
    for i, n in enumerate(neighbours):
        a = 2 * math.pi * i / max(1, len(neighbours))
        _req("PATCH", f"/boards/{bid}/nodes/{n['board_node_id']}", IO, {
            "pos_x": round(CX + R * math.cos(a) - 80),
            "pos_y": round(CY + R * math.sin(a) - 30), "is_move_only": True})
    print(f"evidence star: {len(neighbours)} neighbours, pruned {pruned} clique cross-links")

    # diverse node kinds — financial + geospatial context (evidence-adjacent)
    acct_nid = hotspot_nid = None
    if acct_id is not None:
        r = _req("POST", f"/boards/{bid}/nodes", IO, {
            "node_kind": "account", "ref_table": "FinancialAccount", "ref_id": str(acct_id),
            "pos_x": CX + 640, "pos_y": CY - 120}, optional=True)
        acct_nid = int(r["target_id"]) if r else None
    if hotspot_id is not None:
        r = _req("POST", f"/boards/{bid}/nodes", IO, {
            "node_kind": "hotspot", "ref_table": "CrimeHotspot", "ref_id": str(hotspot_id),
            "pos_x": CX + 640, "pos_y": CY + 180}, optional=True)
        hotspot_nid = int(r["target_id"]) if r else None

    # two+ hypothesis links with rationale (dashed)
    _req("POST", f"/boards/{bid}/edges", IO, {
        "source_node_id": case_nid, "target_node_id": focal_nid, "directed": True,
        "relationship_type": "prime suspect", "confidence": 0.6,
        "rationale": "Suspect's device pinged the crime-scene tower in the 30-min "
                     "window; named by two independent witnesses."})
    if acct_nid:
        _req("POST", f"/boards/{bid}/edges", IO, {
            "source_node_id": focal_nid, "target_node_id": acct_nid, "directed": True,
            "relationship_type": "funnels proceeds", "confidence": 0.5,
            "rationale": "Extortion transfers land in this account within minutes of "
                         "each incident; suspect is the sole login."})
    if hotspot_nid:
        _req("POST", f"/boards/{bid}/edges", IO, {
            "source_node_id": focal_nid, "target_node_id": hotspot_nid, "directed": False,
            "relationship_type": "operates in", "confidence": 0.55,
            "rationale": "Three of the crew's incidents fall inside this cluster."})

    # annotations: a sticky theory + a frame around the suspect network
    _req("POST", f"/boards/{bid}/annotations", IO, {
        "kind": "sticky", "geometry": {"x": CX - 620, "y": CY - 400},
        "content": "Working theory: suspect runs the crew; associates handle drops. "
                   "Money moves through the flagged account.", "style": {"color": "#fde68a"}})
    _req("POST", f"/boards/{bid}/annotations", IO, {
        "kind": "frame", "geometry": {"x": CX - R - 120, "y": CY - R - 40,
                                      "w": 2 * R + 240, "h": 2 * R + 200},
        "content": "Suspect network — imported evidence"})

    # supervisor widens visibility + shares with the analyst
    ver = _req("GET", f"/boards/{bid}", IO)["board"]["version"]
    _req("PATCH", f"/boards/{bid}", SUP, {"visibility": "unit", "expected_version": ver})
    _req("POST", f"/boards/{bid}/collaborators", SUP,
         {"actor": "demo.analyst@drishti.local", "role": "editor"})

    final = _req("GET", f"/boards/{bid}", IO)
    b = final["board"]
    ev = [e for e in final["edges"] if e["edge_class"] == "evidence"]
    hy = [e for e in final["edges"] if e["edge_class"] == "hypothesis"]
    kinds = sorted({n["node_kind"] for n in final["nodes"]})
    print("\n=== board ready ===")
    print(f"  #{bid}  {b['title']}  (v{b['version']}, {b['visibility']})")
    print(f"  {len(final['nodes'])} nodes across kinds: {', '.join(kinds)}")
    print(f"  edges: {len(ev)} evidence (solid star) + {len(hy)} hypothesis (dashed, with rationale)")
    print(f"  annotations: {len(final['annotations'])} (sticky + frame)  "
          f"collaborators: {len(final['collaborators'])}  activity: {final['latest_activity_id']}")
    print(f"\nOPEN -> http://localhost:5173/board/{bid}  (press F for full screen)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
