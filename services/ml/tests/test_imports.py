"""Phase 8 tests — digital + financial template-driven imports and money alerts.

Pure-logic tests (no DB) cover the parser/validator and the money detectors on
small fixtures. DB write-path tests drive the real SQL against the live schema
through the ``rw_rollback`` fixture and ROLL BACK (nothing is persisted). They
cover the Phase-8 checklist: template versions, malformed/duplicate/partial
batches, idempotent retry, invalid-template/unapproved + commit-state guards,
reviewed vs unreviewed graph links, structuring/fan-in/layering fixtures, and
rollback/supersession. API tests assert the role/permission gates.
"""
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.imports import analytics, parse as P
from app.imports import schemas as S
from app.imports import service as svc
from app.imports.service import ImportConflict, ImportNotFound, ImportValidationError
from app.money import detection

requires_db = pytest.mark.skipif(not get_settings().database_url,
                                 reason="DATABASE_URL not configured")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _tvid(conn, code, version="v1"):
    with conn.cursor() as cur:
        cur.execute(
            'SELECT v."ImportTemplateVersionID" FROM "ImportTemplateVersion" v '
            'JOIN "ImportTemplate" t ON t."ImportTemplateID"=v."ImportTemplateID" '
            'WHERE t."Code"=%s AND v."Version"=%s', (code, version))
        return int(cur.fetchone()[0])


def _any_case(conn):
    with conn.cursor() as cur:
        cur.execute('SELECT "CaseMasterID" FROM "CaseMaster" ORDER BY "CaseMasterID" LIMIT 1')
        return int(cur.fetchone()[0])


def _req(tvid, content, fmt="csv", **kw):
    return S.CreateBatchRequest(import_template_version_id=tvid, content=content,
                                source_format=fmt, **kw)


CDR_MIXED = (  # 1 valid, 1 exact duplicate, 1 rejected (missing endpoint_b)
    "caller_msisdn,callee_msisdn,event_time,duration_sec,call_type\n"
    "SYN-A,SYN-B,2025-01-02 10:00:00,120,call\n"
    "SYN-A,SYN-B,2025-01-02 10:00:00,120,call\n"
    "SYN-C,,2025-01-02 11:00:00,30,call\n"
)


def _txn(tid, s, d, amt, day=0):
    import datetime as dt
    ts = dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc) + dt.timedelta(days=day)
    return (tid, s, d, float(amt), ts, None, None)


# ===========================================================================
# PURE: parser / validator (no DB)
# ===========================================================================
def test_parse_csv_and_json_equivalent():
    csv_rows = P.parse_csv("a,b\n1,2\n3,4\n")
    assert csv_rows == [{"a": "1", "b": "2"}, {"a": "3", "b": "4"}]
    assert P.parse_json('[{"a":1}]') == [{"a": 1}]
    assert P.parse_json('{"rows":[{"a":1}]}') == [{"a": 1}]
    with pytest.raises(P.ParseError):
        P.parse_json("not json")


def test_map_and_validate_marks_valid_rejected_duplicate():
    mapping = {"target_table": "CommunicationEvent", "comm_type": "call", "fields": [
        {"canonical": "endpoint_a", "source": "a", "required": True, "type": "string"},
        {"canonical": "endpoint_b", "source": "b", "required": True, "type": "string"},
        {"canonical": "occurred_at", "source": "t", "required": True, "type": "datetime"},
    ]}
    rows = [
        {"a": "X", "b": "Y", "t": "2025-01-01 10:00:00"},   # valid
        {"a": "X", "b": "Y", "t": "2025-01-01 10:00:00"},   # duplicate
        {"a": "Z", "b": "", "t": "2025-01-01 10:00:00"},    # rejected (b required)
        {"a": "Z", "b": "W", "t": "not-a-date"},             # rejected (bad datetime)
    ]
    rep = P.map_and_validate(rows, mapping, ["endpoint_a", "endpoint_b", "occurred_at"])
    assert rep["totals"] == {"parsed": 4, "valid": 1, "rejected": 2, "duplicate": 1}


def test_map_and_validate_rejects_self_transfer():
    mapping = {"target_table": "FinancialTransaction", "fields": [
        {"canonical": "source_account_no", "source": "s", "required": True, "type": "string"},
        {"canonical": "destination_account_no", "source": "d", "required": True, "type": "string"},
        {"canonical": "amount", "source": "amt", "required": True, "type": "decimal"},
        {"canonical": "txn_timestamp", "source": "t", "required": True, "type": "datetime"},
    ]}
    rep = P.map_and_validate([{"s": "A", "d": "A", "amt": "100", "t": "2025-01-01 10:00:00"}],
                             mapping, ["source_account_no", "destination_account_no"])
    assert rep["totals"]["rejected"] == 1
    assert "identical" in rep["rows"][0]["reject_reason"]


# ===========================================================================
# PURE: structuring / fan-in / layering rule fixtures
# ===========================================================================
def test_structuring_fixture_flagged():
    # 5 sub-threshold deposits into one dest within the window -> structuring
    txns = [_txn(i, i + 1, 900, 45000, day=i % 5) for i in range(5)]
    flagged, hubs = detection.detect_structuring(txns, 50000, 5, 14)
    assert 900 in hubs and set(range(5)) <= flagged


def test_fan_in_is_structuring_shaped_consolidation():
    # many small credits from distinct sources consolidating into one account
    txns = [_txn(i, 100 + i, 42, 30000, day=0) for i in range(6)]
    flagged, hubs = detection.detect_structuring(txns, 50000, 5, 14)
    assert 42 in hubs and len(flagged) >= 5


def test_layering_conduit_fixture_flagged():
    # 1 -> conduit 2 (in) -> 3 (out ~ in): 2 is a pass-through layering conduit
    txns = [_txn(1, 1, 2, 200000), _txn(2, 2, 3, 190000)]
    flagged, conduits, chains = detection.detect_layering(txns, 50000, 100000, 0.6)
    assert 2 in conduits and {1, 2} <= flagged


# ===========================================================================
# DB write-path (rolled back)
# ===========================================================================
@requires_db
def test_template_versions_use_distinct_mappings(rw_rollback):
    conn = rw_rollback
    v1 = _tvid(conn, "cdr_call_events", "v1")
    v2 = _tvid(conn, "cdr_call_events", "v2")
    assert v1 != v2
    # v1 uses caller_msisdn/callee_msisdn/event_time
    b1 = svc._create_batch(conn, _req(v1,
        "caller_msisdn,callee_msisdn,event_time\nSYN-A,SYN-B,2025-01-02 10:00:00\n"), "io")
    r1 = svc._serialize_batch(conn, b1)
    assert r1["totals"]["valid"] == 1 and r1["domain"] == "cdr"
    # v2 uses a_party/b_party/start_ts — same canonical fields, different source columns
    b2 = svc._create_batch(conn, _req(v2,
        "a_party,b_party,start_ts\nSYN-A,SYN-B,2025-01-02 10:00:00\n"), "io")
    r2 = svc._serialize_batch(conn, b2)
    assert r2["totals"]["valid"] == 1
    assert r1["mapping"]["fields"][0]["source"] == "caller_msisdn"
    assert r2["mapping"]["fields"][0]["source"] == "a_party"


@requires_db
def test_malformed_duplicate_partial_batch(rw_rollback):
    conn = rw_rollback
    tv = _tvid(conn, "cdr_call_events")
    bid = svc._create_batch(conn, _req(tv, CDR_MIXED, case_master_id=_any_case(conn)), "io")
    rep = svc._serialize_batch(conn, bid)
    assert rep["totals"] == {"parsed": 3, "valid": 1, "rejected": 1, "duplicate": 1}
    # commit -> partial (some rows rejected/duplicate), 1 canonical row
    res = svc._commit_batch(conn, bid, "sup")
    assert res["status"] == "partial" and res["committed"] == 1
    assert res["source_records_created"] == 1 and res["candidate_entity_links"] >= 1


@requires_db
def test_idempotent_retry_returns_same_batch(rw_rollback):
    conn = rw_rollback
    tv = _tvid(conn, "cdr_call_events")
    a = svc._create_batch(conn, _req(tv, CDR_MIXED, idempotency_key="dup-key-1"), "io")
    b = svc._create_batch(conn, _req(tv, CDR_MIXED, idempotency_key="dup-key-1"), "io")
    assert a == b


@requires_db
def test_invalid_template_and_unapproved_version(rw_rollback):
    conn = rw_rollback
    with pytest.raises(ImportNotFound):
        svc._create_batch(conn, _req(999_999_999, "a,b\n1,2\n"), "io")
    # an unapproved (draft) template version cannot be used
    with conn.cursor() as cur:
        cur.execute(
            'INSERT INTO "ImportTemplateVersion" ("ImportTemplateID","Version","ColumnMapping","Status") '
            'SELECT "ImportTemplateID", \'vdraft\', \'{"fields":[]}\'::jsonb, \'draft\' '
            'FROM "ImportTemplate" WHERE "Code"=\'cdr_call_events\' RETURNING "ImportTemplateVersionID"')
        draft_tv = int(cur.fetchone()[0])
    with pytest.raises(ImportValidationError):
        svc._create_batch(conn, _req(draft_tv, "a\n1\n"), "io")


@requires_db
def test_commit_state_guards_idempotent_and_conflict(rw_rollback):
    conn = rw_rollback
    tv = _tvid(conn, "cdr_call_events")
    bid = svc._create_batch(conn, _req(tv, CDR_MIXED), "io")
    svc._commit_batch(conn, bid, "sup")
    # committing again is an idempotent replay, not an error
    replay = svc._commit_batch(conn, bid, "sup")
    assert replay["idempotent_replay"] is True
    # after rollback, the batch cannot be committed again
    svc._rollback_batch(conn, bid, "sup", "test")
    with pytest.raises(ImportConflict):
        svc._commit_batch(conn, bid, "sup")


@requires_db
def test_reviewed_vs_unreviewed_graph_link(rw_rollback):
    conn = rw_rollback
    tv = _tvid(conn, "cdr_call_events")
    bid = svc._create_batch(conn, _req(tv,
        "caller_msisdn,callee_msisdn,event_time\nSYN-A,SYN-B,2025-01-02 10:00:00\n"), "io")
    svc._commit_batch(conn, bid, "sup")
    with conn.cursor() as cur:
        cur.execute('SELECT "EvidenceEntityLinkID","ReviewStatus" FROM "EvidenceEntityLink" '
                    'WHERE "ImportBatchID"=%s', (bid,))
        links = cur.fetchall()
    assert links and all(l[1] == "candidate" for l in links)   # created as candidates
    link_id = int(links[0][0])
    svc._review_entity_link(conn, link_id, "accept", "sup", None)
    with conn.cursor() as cur:
        cur.execute('SELECT "ReviewStatus","ReviewedByActor" FROM "EvidenceEntityLink" '
                    'WHERE "EvidenceEntityLinkID"=%s', (link_id,))
        status, actor = cur.fetchone()
    assert status == "reviewed" and actor == "sup"
    # rejecting another candidate marks it rejected (never auto-confirmed)
    if len(links) > 1:
        svc._review_entity_link(conn, int(links[1][0]), "reject", "sup", None)
        with conn.cursor() as cur:
            cur.execute('SELECT "ReviewStatus" FROM "EvidenceEntityLink" WHERE "EvidenceEntityLinkID"=%s',
                        (int(links[1][0]),))
            assert cur.fetchone()[0] == "rejected"


@requires_db
def test_rollback_deletes_canonical_rows_and_retracts_sources(rw_rollback):
    conn = rw_rollback
    tv = _tvid(conn, "cdr_call_events")
    bid = svc._create_batch(conn, _req(tv,
        "caller_msisdn,callee_msisdn,event_time\nSYN-A,SYN-B,2025-01-02 10:00:00\n"
        "SYN-A,SYN-C,2025-01-02 11:00:00\n"), "io")
    svc._commit_batch(conn, bid, "sup")
    with conn.cursor() as cur:
        cur.execute('SELECT count(*) FROM "CommunicationEvent" WHERE "ImportBatchID"=%s', (bid,))
        assert int(cur.fetchone()[0]) == 2
    rb = svc._rollback_batch(conn, bid, "sup", "revert")
    assert rb["status"] == "rolled_back" and rb["canonical_rows_deleted"] >= 2
    assert rb["source_records_retracted"] >= 2
    with conn.cursor() as cur:
        cur.execute('SELECT count(*) FROM "CommunicationEvent" WHERE "ImportBatchID"=%s', (bid,))
        assert int(cur.fetchone()[0]) == 0
        cur.execute('SELECT "Status" FROM "ImportBatch" WHERE "ImportBatchID"=%s', (bid,))
        assert cur.fetchone()[0] == "rolled_back"


@requires_db
def test_supersession_links_old_to_new(rw_rollback):
    conn = rw_rollback
    tv = _tvid(conn, "cdr_call_events")
    old = svc._create_batch(conn, _req(tv,
        "caller_msisdn,callee_msisdn,event_time\nSYN-A,SYN-B,2025-01-02 10:00:00\n"), "io")
    svc._commit_batch(conn, old, "sup")
    new_id = svc._supersede_batch(conn, old, S.SupersedeRequest(
        content="caller_msisdn,callee_msisdn,event_time\nSYN-A,SYN-B,2025-02-02 10:00:00\n",
        source_format="csv"), "sup")
    assert new_id != old
    with conn.cursor() as cur:
        cur.execute('SELECT "Status","SupersededByImportBatchID" FROM "ImportBatch" WHERE "ImportBatchID"=%s',
                    (old,))
        status, superseded_by = cur.fetchone()
    assert status == "superseded" and int(superseded_by) == new_id
    # old batch's canonical rows were rolled back as part of supersession
    with conn.cursor() as cur:
        cur.execute('SELECT count(*) FROM "CommunicationEvent" WHERE "ImportBatchID"=%s', (old,))
        assert int(cur.fetchone()[0]) == 0


def _inject_structuring_hub(conn) -> int:
    """Insert a clean smurfing fixture (6 sub-threshold deposits into one hub
    within the window) so the scan is deterministic regardless of prior data.
    Returns the hub AccountID."""
    with conn.cursor() as cur:
        cur.execute('INSERT INTO "FinancialAccount" ("AccountNo","AccountType","IsSynthetic") '
                    "VALUES (%s,'mule',TRUE) RETURNING \"AccountID\"", ("SYN-HUB-TEST",))
        hub = int(cur.fetchone()[0])
        for i in range(6):
            cur.execute('INSERT INTO "FinancialAccount" ("AccountNo","IsSynthetic") '
                        'VALUES (%s,TRUE) RETURNING "AccountID"', (f"SYN-SMURF-{i}",))
            src = int(cur.fetchone()[0])
            cur.execute(
                'INSERT INTO "FinancialTransaction" ("SourceAccountID","DestinationAccountID",'
                '"Amount","TxnTimestamp","Channel","IsSynthetic") '
                "VALUES (%s,%s,%s,%s,'imps',TRUE)",
                (src, hub, 45000, f"2025-05-{i + 1:02d} 10:00:00+00"))
    return hub


@requires_db
@pytest.mark.slow
def test_money_scan_writes_reason_coded_reviewable_alerts(rw_rollback):
    conn = rw_rollback
    hub = _inject_structuring_hub(conn)
    rep = analytics._scan(conn, structuring_min_count=5, structuring_window_days=14, max_alerts=2000)
    assert rep["alerts_written"] > 0
    # every alert carries an explicit reason code; the injected hub is structuring
    assert "STRUCT_SUBTHRESHOLD_FANIN" in rep["by_reason_code"]
    with conn.cursor() as cur:
        cur.execute('SELECT "MoneyAlertID","ReasonCode","Status" FROM "MoneyAlert" '
                    'WHERE "AccountID"=%s AND "ModelVersionID"=%s', (hub, rep["model_version_id"]))
        row = cur.fetchone()
    assert row and row[1] == "STRUCT_SUBTHRESHOLD_FANIN" and row[2] == "open"
    # reviewer disposition transitions the alert + records a review
    disp = analytics._disposition(conn, int(row[0]), "false_positive", "crime_analyst", "benign")
    assert disp["status"] == "false_positive"
    with conn.cursor() as cur:
        cur.execute('SELECT count(*) FROM "MoneyAlertReview" WHERE "MoneyAlertID"=%s', (int(row[0]),))
        assert int(cur.fetchone()[0]) == 1


# ===========================================================================
# API surface + guards (no committed writes)
# ===========================================================================
from app.main import app  # noqa: E402

client = TestClient(app)


def test_templates_endpoint_lists_eight_domains():
    r = client.get("/imports/templates", headers={"X-Role": "investigating_officer"})
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 8
    codes = {t["code"] for t in body["templates"]}
    assert {"cdr_call_events", "bank_transactions", "wallet_upi", "account_kyc"} <= codes


def test_import_pipeline_open_to_every_command_role():
    # INTERIM ("all roles have access to everything"): the import pipeline read
    # gate no longer denies any command seat.
    assert client.get("/imports/templates", headers={"X-Role": "dgp_state_command"}).status_code == 200
    assert client.get("/imports/batches", headers={"X-Role": "dgp_state_command"}).status_code == 200


def test_financial_views_gated_by_money_permission():
    # INTERIM: every command seat holds money_trail; a non-canonical role is
    # refused by the same code-based gate.
    assert client.get("/imports/accounts", headers={"X-Role": "dgp_state_command"}).status_code == 200
    assert client.get("/imports/accounts", headers={"X-Role": "investigating_officer"}).status_code == 200
    assert client.get("/imports/accounts", headers={"X-Role": "wizard"}).status_code == 403
    assert client.get("/imports/transactions", headers={"X-Role": "wizard"}).status_code == 403


def test_money_scan_requires_write_permission():
    # INTERIM: every command seat holds WRITE on money_trail, so the scan gate
    # only refuses a role outside the canonical set.
    assert client.post("/imports/money/scan", headers={"X-Role": "wizard"}).status_code == 403
