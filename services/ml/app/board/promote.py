"""Hypothesis promotion (Prompt 16 §B.9 / §I).

Promoting a hypothesis edge creates a REVIEW PROPOSAL (an AlertHistory item when
the operational store is available, otherwise a board-native proposal marker). It
must NEVER silently create a confirmed NetworkEdge or a factual assertion — the
hypothesis stays a hypothesis on the board; only its promotion STATUS changes and
a review item is raised for a human to adjudicate.

Preconditions enforced here:
  * only a hypothesis edge can be promoted (an evidence edge is already sourced);
  * a rationale is REQUIRED before promotion (§B.8).
The board_promote role gate + fresh-confirmation are enforced in the router.
"""
from __future__ import annotations

from typing import Optional

from psycopg2.extras import Json

from .. import db
from .repo import board_repo
from .schemas import MutationResult, PromoteEdgeRequest
from . import service as S


def _pg_enum_labels(conn, enum_name: str) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT e.enumlabel FROM pg_enum e JOIN pg_type t ON t.oid=e.enumtypid "
            "WHERE t.typname=%s ORDER BY e.enumsortorder", (enum_name,))
        return [r[0] for r in cur.fetchall()]


def _pick(labels: list[str], prefer: tuple[str, ...], default: Optional[str]) -> Optional[str]:
    for p in prefer:
        for lab in labels:
            if p in lab.lower():
                return lab
    return labels[0] if labels else default


def _raise_alert_proposal(board_id: int, edge: dict, actor: str) -> Optional[str]:
    """Best-effort AlertHistory review item. Returns 'AlertHistory:<id>' or None.

    Enum-safe: reads the real enum labels so it works across schema variants; any
    failure (no PG / different schema) degrades to a board-native proposal marker.
    """
    try:
        with db.rw_conn() as conn:
            types = _pg_enum_labels(conn, "alert_type_enum")
            statuses = _pg_enum_labels(conn, "alert_status_enum")
            sev = _pg_enum_labels(conn, "alert_severity_enum")
            atype = _pick(types, ("anomaly", "network", "pattern", "association"), None)
            astatus = _pick(statuses, ("open", "new", "pending"), None)
            aseverity = _pick(sev, ("info", "low"), None)
            if not (atype and astatus):
                return None
            payload = Json({
                "kind": "board_hypothesis_promotion", "board_id": board_id,
                "board_edge_id": int(edge["BoardEdgeID"]),
                "relationship_type": edge.get("RelationshipType"),
                "confidence": edge.get("Confidence"), "proposed_by": actor,
                "note": "REVIEW PROPOSAL — not a confirmed edge; no NetworkEdge created."})
            with conn.cursor() as cur:
                cur.execute(
                    'INSERT INTO "AlertHistory" ("AlertType","Severity","Title",'
                    '"Message","Payload","Status") VALUES '
                    '(%s::alert_type_enum,%s::alert_severity_enum,%s,%s,%s,%s::alert_status_enum) '
                    'RETURNING "AlertID"',
                    (atype, aseverity or "info",
                     f"Board hypothesis proposed for review (board {board_id})",
                     (edge.get("Rationale") or "")[:1000], payload, astatus))
                aid = int(cur.fetchone()[0])
        return f"AlertHistory:{aid}"
    except Exception:  # noqa: BLE001 — proposal falls back to board-native marker
        return None


def promote_edge(board_id: int, edge_id: int, req: PromoteEdgeRequest,
                 actor: str, role: str, *, idem_key: Optional[str] = None) -> MutationResult:
    repo = board_repo()
    board = S._load_board(repo, board_id)
    edge = repo.get("BoardEdge", edge_id)
    if edge is None or int(edge.get("BoardID", -1)) != board_id or edge.get("DeletedAt"):
        raise S.BoardNotFound(f"Edge {edge_id} not found on board {board_id}.")
    if edge.get("EdgeClass") != "hypothesis":
        raise S.BoardValidationError(
            "Only a hypothesis edge can be promoted (evidence edges are already sourced).")
    if not (edge.get("Rationale") or "").strip():
        raise S.BoardValidationError(
            "A rationale is required before a hypothesis can be promoted for review.")
    if edge.get("PromotedStatus") == "proposed":
        raise S.BoardConflict("This hypothesis has already been proposed for review.")

    proposal_ref = _raise_alert_proposal(board_id, edge, actor) \
        or f"board-proposal:{board_id}:{edge_id}"

    def apply(b: dict):
        repo.update("BoardEdge", edge_id,
                    {"PromotedStatus": "proposed", "PromotedRef": proposal_ref})
        return "edge", edge_id, {
            "promoted": True, "proposal_ref": proposal_ref,
            "note": "review proposal raised; NO confirmed NetworkEdge was created",
            "relationship_type": edge.get("RelationshipType")}

    return S._mutate(repo, board, actor, role, action="edge.promote", apply=apply,
                     idem_key=idem_key)
