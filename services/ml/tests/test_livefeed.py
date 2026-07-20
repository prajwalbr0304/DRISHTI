"""Prompt 20 Part E — Live Command Center committed-FIR event flow: the
event/projection contract, idempotency, freshness, the read-only WHAT-IF delta,
and the no-person-rescore / no-auto-dispatch guarantees.

on_fir_committed / project are READ-ONLY (recompute projections; never write), so
DB tests need no rollback. The in-process ledger is reset per count-sensitive test."""
import pytest
from fastapi.testclient import TestClient

from conftest import requires_db

from app.main import app
from app.livefeed import flow

client = TestClient(app)


def _hdr(role: str) -> dict:
    return {"X-Role": role}


def _first_case() -> tuple[int, int]:
    from app import db
    with db.ro_conn() as conn:
        cur = conn.cursor()
        cur.execute('SELECT cm."CaseMasterID", u."DistrictID" FROM "CaseMaster" cm '
                    'JOIN "Unit" u ON u."UnitID"=cm."PoliceStationID" '
                    'ORDER BY cm."CaseMasterID" LIMIT 1')
        r = cur.fetchone()
        return int(r[0]), int(r[1])


# ============================ contract (offline) ===========================
def test_case_committed_is_a_valid_signal_event():
    from app import signals
    assert signals.EVENT_CASE_COMMITTED == "case.committed"
    assert signals.EVENT_CASE_COMMITTED in signals._VALID_EVENTS


def test_fir_committed_role_gated_policymaker_denied():
    body = {"case_id": 1}
    assert client.post("/livefeed/fir-committed", json=body,
                       headers=_hdr("policymaker")).status_code == 403


# ============================ projection + idempotency (DB) =================
@requires_db
def test_committed_fir_updates_the_three_projections():
    flow._LEDGER.reset()
    case_id, _ = _first_case()
    rec = flow.on_fir_committed(case_id, source_ts="2025-12-31T00:00:00+00:00")
    assert rec.status == "success"
    assert set(rec.projections) == {"district_statistic", "supervisor_workload", "hotspot_near_repeat"}
    assert rec.projections["district_statistic"]["total_cases"] >= 1
    assert "near_repeat_eligible" in rec.projections["hotspot_near_repeat"]


@requires_db
def test_duplicate_committed_event_is_idempotent():
    flow._LEDGER.reset()
    case_id, _ = _first_case()
    r1 = flow.on_fir_committed(case_id)
    r2 = flow.on_fir_committed(case_id)          # duplicate
    assert r1.processed_ts == r2.processed_ts     # same logical record
    assert flow._LEDGER.duplicate_suppressed == 1
    assert flow.freshness_state()["processed_count"] == 1


@requires_db
def test_project_shows_plus_one_delta_and_guarantees():
    _, district_id = _first_case()
    out = flow.project_committed_fir(district_id=district_id, crime_head_id=1)
    assert out["district_statistic"]["delta"] == 1
    assert out["district_statistic"]["after"] == out["district_statistic"]["before"] + 1
    assert out["supervisor_workload"]["delta"] == 1
    # a committed FIR never rescores a person or auto-dispatches staff
    assert out["guarantees"] == {"person_rescored": False, "auto_dispatch": False}


@requires_db
def test_freshness_state_tracks_projections_and_transport():
    flow._LEDGER.reset()
    case_id, _ = _first_case()
    flow.on_fir_committed(case_id, source_ts="2025-12-31T00:00:00+00:00")
    fs = flow.freshness_state()
    assert "Catalyst Signal" in fs["transport"]
    for name in ("district_statistic", "supervisor_workload", "hotspot_near_repeat"):
        st = fs["projections"][name]
        assert st["last_processed_ts"] is not None
        assert st["last_success_ts"] is not None
        assert st["processed_count"] >= 1
    assert fs["guarantees"]["person_rescored"] is False


# ============================ API (DB) =====================================
@requires_db
def test_project_endpoint_open_read():
    _, district_id = _first_case()
    r = client.post("/livefeed/project", json={"district_id": district_id, "crime_head_id": 1})
    assert r.status_code == 200
    assert r.json()["district_statistic"]["delta"] == 1


@requires_db
def test_fir_committed_endpoint_idempotent_replay_flag():
    flow._LEDGER.reset()
    case_id, _ = _first_case()
    first = client.post("/livefeed/fir-committed", json={"case_id": case_id},
                        headers=_hdr("supervisor"))
    assert first.status_code == 200 and first.json()["idempotent_replay"] is False
    again = client.post("/livefeed/fir-committed", json={"case_id": case_id},
                        headers=_hdr("supervisor"))
    assert again.status_code == 200 and again.json()["idempotent_replay"] is True
