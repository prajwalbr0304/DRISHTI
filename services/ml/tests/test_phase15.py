"""Phase 15 — admin/governance console, notifications, reports, optional RAG.

Covers the prompt's Test list:
  * admin health/status values + RLS-disabled status check;
  * Catalyst identity/role mapping + API authorization matrix;
  * audit search;
  * retention/legal-hold NON-DESTRUCTIVE behavior (+ CHECK rejects delete);
  * notification preference/escalation/delivery status + data minimization;
  * model drift/review-due view;
  * synthetic report watermark/audit + Data Store metadata + Stratus hash/expiry
    + reproducible snapshot;
  * optional RAG citations/refusal + graceful disabled state;
  * SmartBrowz report (or documented AppSail fallback);
  * Signals/Mail/Push data minimization when enabled;
  * proof that no voice/OCR/extraction dependency is needed.

DB-integrated tests use ``rw_rollback`` (owner connection that ALWAYS rolls back)
via the internal ``_fn(conn, ...)`` helpers / raw SQL, so nothing persists to the
synthetic development database.
"""
import datetime as dt
import json
import pathlib

import pytest

from conftest import requires_db


# ===========================================================================
# Authorization matrix (identity/role mapping) — pure
# ===========================================================================
def test_authorization_matrix_role_permissions():
    from app.admin import permissions
    m = permissions.authorization_matrix()
    # INTERIM ("all roles have access to everything"): every command role holds
    # every permission. The matrix still covers exactly the canonical roles.
    assert set(m) == set(permissions.ROLES)
    for role, grants in m.items():
        assert all(grants.values()), role
        assert set(grants) == set(permissions.PERMISSIONS)


def test_permission_gate_helpers():
    from app.admin import permissions
    for role in permissions.ROLES:
        assert permissions.has_permission(role, "admin_write"), role
    # A role outside the canonical set holds nothing and clamps to the default.
    assert not permissions.has_permission("wizard", "admin_write")
    assert permissions.resolve_role("bogus") in permissions.ROLES  # clamps to default


# ===========================================================================
# Signals — data minimization + enabled gating
# ===========================================================================
def test_signals_minimization_and_gating():
    from app import signals
    pub = signals.InMemorySignals(enabled=True)
    ev = pub.publish(signals.EVENT_NOTIFICATION_CREATED,
                     {"notification_message_id": 7, "recipient": "io.x",
                      "phone": "9999999999", "narrative": "sensitive facts"})
    assert ev.published is True
    assert ev.payload["notification_message_id"] == 7
    assert "phone" not in ev.payload and "narrative" not in ev.payload  # data-minimized
    # disabled -> recorded but NOT published.
    off = signals.InMemorySignals(enabled=False)
    ev2 = off.publish(signals.EVENT_REPORT_READY, {"report_snapshot_id": 3})
    assert ev2.published is False
    # unknown event is rejected.
    with pytest.raises(ValueError):
        pub.publish("bogus.event", {})


# ===========================================================================
# Mail/Push — data minimization + suppress-when-disabled
# ===========================================================================
def test_mail_push_minimize_and_suppress():
    from app import notify_channels as nc
    mail = nc.InMemoryMail(enabled=True)
    r = mail.send(to_actor="io.x", subject="s" * 300, summary="b" * 1000, resource="work_task")
    assert r.status == "sent" and r.provider == "catalyst_mail"
    assert len(mail.sent[0]["subject"]) <= 120 and len(mail.sent[0]["summary"]) <= 400
    off = nc.InMemoryMail(enabled=False)
    assert off.send(to_actor="io.x", subject="s", summary="b").status == "suppressed"
    assert off.sent == []
    push = nc.InMemoryPush(enabled=True)
    assert push.send(to_actor="io.x", title="t", summary="b").status == "sent"


# ===========================================================================
# Optional RAG — citations / refusal / graceful disabled state
# ===========================================================================
def test_rag_retrieve_cites_and_refuses():
    from app.rag import knowledge
    ans = knowledge.retrieve("How should an FIR be registered for a cognizable offence?")
    assert ans["refused"] is False
    assert any(c["source"] == "SOP-FIR-001" for c in ans["citations"])
    ref = knowledge.retrieve("what is the accused's home address in case 1234")
    assert ref["refused"] is True and ref["citations"] == []


def test_rag_evaluation_fixed_set_passes():
    from app.rag import service as rag_service
    r = rag_service.evaluate()
    assert r["total"] >= 5
    assert r["passed"] == r["total"] and r["failed"] == 0  # citation + refusal both correct


def test_rag_ask_graceful_disabled(monkeypatch):
    from app.rag import service as rag_service
    monkeypatch.setattr(rag_service, "assistant_available", lambda: False)
    out = rag_service.ask("investigating_officer", "anything at all")
    assert out["enabled"] is False and out["refused"] is True and out["citations"] == []


def test_rag_ask_enabled_cites(monkeypatch):
    from app.rag import service as rag_service
    monkeypatch.setattr(rag_service, "assistant_available", lambda: True)
    monkeypatch.setattr(rag_service, "_log_interaction", lambda *a, **k: None)  # no DB write
    out = rag_service.ask("investigating_officer",
                          "How is digital evidence integrity verified (chain of custody)?")
    assert out["enabled"] is True and out["refused"] is False
    assert any(c["source"] == "SOP-EVID-003" for c in out["citations"])


def test_rag_ask_case_scope_refuses_only_case_read_denied_roles(monkeypatch):
    from app.cases import permissions as case_perms
    from app.rag import service as rag_service
    monkeypatch.setattr(rag_service, "assistant_available", lambda: True)
    monkeypatch.setattr(rag_service, "_log_interaction", lambda *a, **k: None)
    # INTERIM: no command role is denied case scope, so the assistant answers.
    out = rag_service.ask("dgp_state_command", "How is evidence handled?", case_scope_ref_id="1")
    assert out["refused"] is False
    # The case-scope gate itself still refuses a role on the deny list.
    monkeypatch.setattr(rag_service, "CASE_READ_DENY", {"wizard"})
    monkeypatch.setattr(case_perms, "CASE_READ_DENY", {"wizard"})
    out = rag_service.ask("wizard", "How is evidence handled?", case_scope_ref_id="1")
    assert out["refused"] is True and "aggregate" in out["answer"].lower()


def test_rag_status_structure():
    from app.rag import service as rag_service
    s = rag_service.status()
    assert s["approved_sources"] >= 5
    assert s["provider"] in ("disabled", "offline", "quickml")
    if not s["enabled"]:
        assert s["reason"]  # graceful disabled state explains how to enable


# ===========================================================================
# Reports — authorization / watermark / hash (pure) + SmartBrowz fallback
# ===========================================================================
def test_report_authorization_matrix():
    from app.reports import service as rep
    tpl = {"code": "CASE_SUMMARY", "report_kind": "case_summary", "scope_kind": "case",
           "allowed_roles": ["investigating_officer", "sho", "system_admin"], "is_active": True}
    # INTERIM: any canonical command role may generate any active template, even
    # one whose per-template allow-list predates the command roles.
    rep._authorize(tpl, "dgp_state_command", "case", "1")
    rep._authorize(tpl, "senior_command", "case", "1")
    # A role outside the canonical set still needs the template's allow-list.
    with pytest.raises(rep.ReportAuthError):
        rep._authorize(tpl, "wizard", "case", "1")
    with pytest.raises(rep.ScopeError):
        rep._authorize(tpl, "investigating_officer", "unit", "1")     # scope mismatch
    with pytest.raises(rep.ScopeError):
        rep._authorize(tpl, "investigating_officer", "case", None)    # missing scope ref
    rep._authorize(tpl, "investigating_officer", "case", "1")         # ok
    rep._authorize(tpl, "system_admin", "case", "1")          # system_admin always ok


def test_report_render_has_watermark_and_hash_reproducible():
    from app.reports import service as rep
    html = rep._render_html("Demo", {"data_as_of": "x", "k": 1},
                            [{"source": "CaseMaster", "version": "current", "record_id": "1"}])
    assert rep.WATERMARK in html
    render = rep.get_smartbrowz().render_pdf(html, watermark=rep.WATERMARK)
    assert rep.WATERMARK in render.data.decode("utf-8", "ignore")  # watermark carried into object
    assert render.sha256 and render.size > 0
    snap = {"a": 1, "b": [1, 2], "c": "x"}
    assert rep._canonical_hash(snap) == rep._canonical_hash(dict(snap))  # deterministic


def test_report_render_backend_label():
    from app.reports import service as rep
    # No DRISHTI_USE_CATALYST_SMARTBROWZ -> documented AppSail fallback renderer.
    assert rep._render_backend() in ("smartbrowz", "appsail_fallback")


# ===========================================================================
# No OCR / voice / extraction dependency
# ===========================================================================
def test_no_ocr_voice_extraction_dependency():
    app_dir = pathlib.Path(__file__).resolve().parents[1] / "app"
    targets = ["admin", "notifications", "reports", "rag", "signals.py", "notify_channels.py"]
    forbidden = ("import pytesseract", "import whisper", "from textract", "import textract",
                 "import speech_recognition", "zia_ocr", "transcrib", "speech_to_text",
                 "ocr_", "import easyocr")
    files: list[pathlib.Path] = []
    for t in targets:
        p = app_dir / t
        if p.is_dir():
            files += list(p.rglob("*.py"))
        elif p.exists():
            files.append(p)
    assert files, "no Phase 15 module files found"
    for f in files:
        text = f.read_text(encoding="utf-8", errors="ignore").lower()
        for bad in forbidden:
            assert bad not in text, f"OCR/voice dependency {bad!r} found in {f}"


# ===========================================================================
# DB-integrated: admin status / RLS / audit / queues
# ===========================================================================
@requires_db
def test_admin_rls_status_covers_new_tables():
    from app.admin import service as adm
    s = adm.rls_status()
    assert s["rls_disabled"] is True and s["tables_checked"] > 0 and s["tables_enabled"] == 0
    names = {t["table_name"] for t in s["tables"]}
    assert {"RetentionPolicy", "ReportSnapshot", "WorkTask", "NotificationMessage",
            "ModelReview", "LegalHold", "RagInteraction"} <= names


@requires_db
def test_admin_status_values():
    from app.admin import service as adm
    s = adm.admin_status()
    assert s["hackathon_mode"] is True and s["demo_data_only"] is True
    assert s["rls_disabled"] is True
    assert s["environment_label"] == "Synthetic Hackathon Demo"
    assert set(("signals_enabled", "notify_enabled", "rag_enabled")) <= set(s["components"].keys())
    assert "cases" in s["counts"]


@requires_db
def test_admin_audit_search_structure():
    from app.admin import service as adm
    d = adm.search_audit(None, None, None, None, None, None, 1, 5)
    assert {"total", "page", "page_size", "items"} <= set(d.keys())
    assert isinstance(d["items"], list)


@requires_db
def test_admin_queues_report_intake_review_without_evidence_extraction():
    from app.admin import service as adm
    q = adm.queues()
    assert q["extraction_queue_present"] is True
    assert q["intake_scan_pending"] >= 0
    assert q["evidence_extraction_enabled"] is False
    assert {"data_quality_open", "ingestion_partial_failed", "evidence_quarantine"} <= set(q.keys())


def test_admin_usage_plan_baseline():
    from app.admin import service as adm
    u = adm.usage()
    assert u["plan_baseline"].get("envelope_inr") == 1800  # INR 1500 + 300 (report §9)
    assert u["feature_flags"]  # flags surfaced


@requires_db
def test_admin_seeds_present():
    from app.admin import service as adm
    assert len(adm.retention_overview()["policies"]) >= 4
    assert len(adm.list_report_templates("system_admin")) >= 5
    keys = {f["key"] for f in adm.list_feature_flags()}
    assert {"rag_assistant", "notifications_email", "reports_smartbrowz"} <= keys


# ===========================================================================
# DB-integrated: retention / legal hold NON-DESTRUCTIVE
# ===========================================================================
@requires_db
def test_retention_legal_hold_non_destructive(rw_rollback):
    conn = rw_rollback
    with conn.cursor() as cur:
        # an evidence item older than a 1-day retention policy -> would be expiry-flagged.
        cur.execute('INSERT INTO "EvidenceItem" ("Title","CreatedAt") '
                    "VALUES (%s, now() - interval '10 days') RETURNING \"EvidenceItemID\"",
                    ("phase15 retention test",))
        eid = int(cur.fetchone()[0])
        cur.execute('INSERT INTO "RetentionPolicy" ("Code","Name","AppliesTo","RetentionDays",'
                    '"ExpiryAction") VALUES (%s,%s,%s,%s,%s)',
                    ("EVID_TEST_1D", "test", "evidence", 1, "archive_flag"))
        cur.execute('SELECT "ExpiryFlagged","OnLegalHold" FROM "vw_evidence_retention" '
                    'WHERE "EvidenceItemID"=%s', (eid,))
        flagged, held = cur.fetchone()
        assert flagged is True and held is False   # expiry is a FLAG only (never a delete)
        # an active legal hold must suppress the expiry flag.
        cur.execute('INSERT INTO "LegalHold" ("SubjectKind","SubjectRefID","Reason") '
                    'VALUES (%s,%s,%s)', ("evidence", str(eid), "phase15 hold"))
        cur.execute('SELECT "ExpiryFlagged","OnLegalHold" FROM "vw_evidence_retention" '
                    'WHERE "EvidenceItemID"=%s', (eid,))
        flagged2, held2 = cur.fetchone()
        assert flagged2 is False and held2 is True
        # non-destructive: the evidence row still exists.
        cur.execute('SELECT count(*) FROM "EvidenceItem" WHERE "EvidenceItemID"=%s', (eid,))
        assert int(cur.fetchone()[0]) == 1
    conn.rollback()


@requires_db
def test_retention_policy_rejects_destructive_action(rw_rollback):
    conn = rw_rollback
    with pytest.raises(Exception):        # CHECK constraint forbids a destructive action
        with conn.cursor() as cur:
            cur.execute('INSERT INTO "RetentionPolicy" ("Code","Name","AppliesTo","RetentionDays",'
                        '"ExpiryAction") VALUES (%s,%s,%s,%s,%s)',
                        ("EVID_DELETE", "bad", "evidence", 10, "delete"))
    conn.rollback()


# ===========================================================================
# DB-integrated: model review-due view
# ===========================================================================
@requires_db
def test_model_review_due_overdue(rw_rollback):
    conn = rw_rollback
    with conn.cursor() as cur:
        cur.execute('INSERT INTO "ModelVersion" ("ModelName","ModelType","Version","ApprovalStatus",'
                    '"Environment") VALUES (%s,%s,%s,%s,%s) RETURNING "ModelVersionID"',
                    ("phase15_review_model", "forecasting", "t1", "approved", "disposable_test"))
        mvid = int(cur.fetchone()[0])
        cur.execute('INSERT INTO "ModelReview" ("ModelVersionID","ReviewKind","Status","DueAt") '
                    "VALUES (%s,'independent','due', now() - interval '10 days')", (mvid,))
        cur.execute('SELECT "EffectiveReviewState" FROM "vw_model_review_due" '
                    'WHERE "ModelVersionID"=%s', (mvid,))
        assert cur.fetchone()[0] == "overdue"
    conn.rollback()


@requires_db
def test_admin_model_reviews_read():
    from app.admin import service as adm
    d = adm.model_reviews()
    assert "items" in d and "total" in d


# ===========================================================================
# DB-integrated: source reconciliation repair (non-destructive)
# ===========================================================================
@requires_db
def test_source_repair_restages_rejected(rw_rollback):
    from app.admin import service as adm
    conn = rw_rollback
    with conn.cursor() as cur:
        cur.execute('INSERT INTO "SourceSystem" ("Code","Name","Kind") VALUES (%s,%s,%s) '
                    'RETURNING "SourceSystemID"', ("PH15_SRC", "test", "csv_import"))
        ssid = int(cur.fetchone()[0])
        cur.execute('INSERT INTO "SourceRecord" ("SourceSystemID","Status") VALUES (%s,%s) '
                    'RETURNING "SourceRecordID"', (ssid, "rejected"))
        srid = int(cur.fetchone()[0])
    out = adm._repair_import(conn, None, [srid], "phase15 repair", "demo.system_admin")
    assert out["source_records_restaged"] == 1
    with conn.cursor() as cur:
        cur.execute('SELECT "Status" FROM "SourceRecord" WHERE "SourceRecordID"=%s', (srid,))
        assert cur.fetchone()[0] == "staged"   # re-staged for review, not deleted
    conn.rollback()


# ===========================================================================
# DB-integrated: notifications preference / delivery / minimization / escalation
# ===========================================================================
@requires_db
def test_notification_write_minimized_and_in_app_delivered(rw_rollback):
    from app.notifications import service as notif
    conn = rw_rollback
    mid, pending = notif._write_notification(conn, "io.ph15.n", "task_assigned", "X" * 500,
                                             actor="demo.system_admin")
    assert pending == []   # default preference: email/push off
    with conn.cursor() as cur:
        cur.execute('SELECT "Summary" FROM "NotificationMessage" WHERE "NotificationMessageID"=%s',
                    (mid,))
        assert len(cur.fetchone()[0]) <= 200   # data-minimized (clipped)
        cur.execute('SELECT "Channel","Status" FROM "NotificationDelivery" '
                    'WHERE "NotificationMessageID"=%s', (mid,))
        rows = {(r[0], r[1]) for r in cur.fetchall()}
    assert ("in_app", "sent") in rows
    conn.rollback()


@requires_db
def test_notification_email_preference_queues_channel(rw_rollback):
    from app.notifications import service as notif
    conn = rw_rollback
    notif._upsert_preference(conn, "io.ph15.e", True, True, False, "immediate", 24)
    mid, pending = notif._write_notification(conn, "io.ph15.e", "report_ready", "hello",
                                             actor="demo.system_admin")
    assert "email" in pending
    with conn.cursor() as cur:
        cur.execute('SELECT "Channel","Status" FROM "NotificationDelivery" '
                    'WHERE "NotificationMessageID"=%s', (mid,))
        rows = {(r[0], r[1]) for r in cur.fetchall()}
    assert ("in_app", "sent") in rows and ("email", "queued") in rows
    conn.rollback()


@requires_db
def test_task_escalation_sla(rw_rollback):
    from app.notifications import service as notif
    from app.notifications.schemas import WorkTaskCreate
    conn = rw_rollback
    past = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=2)).isoformat()
    body = WorkTaskCreate(task_type="case_review", title="review overdue case",
                          due_at=past, assignee_actor="io.ph15.esc")
    row = notif._create_task(conn, body, "demo.system_admin")
    escalated = notif._escalate_db(conn)
    assert any(t["work_task_id"] == row["work_task_id"] for t in escalated)
    with conn.cursor() as cur:
        cur.execute('SELECT "Status" FROM "WorkTask" WHERE "WorkTaskID"=%s', (row["work_task_id"],))
        assert cur.fetchone()[0] == "escalated"
    # idempotent: a second pass does not re-escalate the same task.
    assert all(t["work_task_id"] != row["work_task_id"] for t in notif._escalate_db(conn))
    conn.rollback()


# ===========================================================================
# DB-integrated: report generate -> watermark / hash / Stratus / audit / reproducible
# ===========================================================================
@requires_db
def test_report_generate_watermark_hash_stratus_audit(rw_rollback):
    from app.reports import service as rep
    conn = rw_rollback
    out = rep._generate(conn, "MODEL_GOVERNANCE", "global", None, None, {},
                        "demo.system_admin", "system_admin")
    rid = out["report_id"]
    row = rep._get_report(conn, rid)
    assert row["watermark"] == "Synthetic Hackathon Demo"          # prominent synthetic watermark
    assert row["object_sha256"] and row["stratus_object_key"]       # Stratus object + hash
    assert row["stratus_bucket"] == "report"
    assert row["object_sha256"] == out["object_sha256"]
    assert row["expires_at"]                                        # retention/expiry recorded
    assert row["source_citations"]                                  # source/version citations
    assert row["render_backend"] in ("smartbrowz", "appsail_fallback")
    # reproducible: re-hashing the stored structured snapshot yields the stored hash.
    assert rep._canonical_hash(row["source_snapshot"]) == row["content_hash"]
    # audited (same transaction).
    with conn.cursor() as cur:
        cur.execute('SELECT count(*) FROM "audit_logs" WHERE "action"=%s AND "resource"=%s '
                    'AND "resource_id"=%s', ("export", "report", str(rid)))
        assert int(cur.fetchone()[0]) == 1
    conn.rollback()


@requires_db
def test_report_case_scope_refuses_a_non_canonical_role(rw_rollback):
    # INTERIM: every command role may export a case-scoped report; a role outside
    # the canonical set is still refused by the template allow-list.
    from app.reports import service as rep
    with pytest.raises(rep.ReportAuthError):
        rep._generate(rw_rollback, "CASE_SUMMARY", "case", "1", None, {}, "demo.x", "wizard")
    rw_rollback.rollback()


@requires_db
def test_report_case_summary_is_structured_only(rw_rollback):
    from app.reports import service as rep
    conn = rw_rollback
    with conn.cursor() as cur:
        cur.execute('SELECT "CaseMasterID" FROM "CaseMaster" LIMIT 1')
        r = cur.fetchone()
    if not r:
        pytest.skip("no synthetic cases seeded")
    snap, citations = rep._snapshot_case_summary(conn, str(int(r[0])))
    assert snap["narrative_included"] is False           # structured fields only, no narrative
    assert "brief" not in json.dumps(snap).lower()        # BriefFacts not exported
    assert citations and citations[0]["source"] == "CaseMaster"
    conn.rollback()
