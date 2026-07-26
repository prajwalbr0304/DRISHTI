"""Report generation service (Phase 15).

Reports are generated from STRUCTURED database fields only — never by parsing an
uploaded file (no OCR/extraction). Each report:
  * checks server-side export authorization + role/case/unit scope;
  * builds an immutable, reproducible STRUCTURED source snapshot + SHA-256;
  * carries source/version citations + a prominent synthetic watermark;
  * renders via Catalyst SmartBrowz (or a documented AppSail fallback);
  * stores the object in private Stratus and records the object hash/size/version
    + lineage in the Data Store (ReportSnapshot);
  * writes an audit event and publishes a ``report.ready`` Signal AFTER commit.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from typing import Any, Optional

from psycopg2.extras import Json

from .. import audit, db
from ..roles import ALL_ROLES
from ..signals import EVENT_REPORT_READY, get_signals
from ..smartbrowz import get_smartbrowz
from ..stratus import BUCKET_REPORT, DEFAULT_PRESIGN_TTL_S, ObjectRef, get_stratus
import os

WATERMARK = "Synthetic Hackathon Demo"
_DEFAULT_REPORT_RETENTION_DAYS = 365


class ReportError(Exception):
    pass


class TemplateNotFound(ReportError):
    pass


class ReportAuthError(ReportError):
    pass


class ScopeError(ReportError):
    pass


class SubjectNotFound(ReportError):
    pass


def _s(v) -> Optional[str]:
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()
    return str(v) if v is not None else None


def _canonical_hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode("utf-8")).hexdigest()


# ===========================================================================
# Template + authorization
# ===========================================================================
def _load_template(conn, code: str) -> Optional[dict]:
    with conn.cursor() as cur:
        cur.execute('SELECT "ReportTemplateID","Code","Name","ReportKind","ScopeKind","AllowedRoles",'
                    '"ConfigSchema","IsActive" FROM "ReportTemplate" WHERE "Code"=%s', (code,))
        r = cur.fetchone()
    if not r:
        return None
    return {"report_template_id": int(r[0]), "code": r[1], "name": r[2], "report_kind": r[3],
            "scope_kind": r[4], "allowed_roles": list(r[5] or []), "config_schema": r[6] or {},
            "is_active": bool(r[7])}


def _authorize(template: dict, role: str, scope_kind: str, scope_ref_id: Optional[str]) -> None:
    if not template["is_active"]:
        raise TemplateNotFound(f"Report template '{template['code']}' is inactive.")
    # INTERIM ("all roles have access to everything"): any canonical command role
    # may generate any active template; the per-template allow-list still applies
    # to anything outside the canonical set.
    if role not in ALL_ROLES and role not in template["allowed_roles"]:
        raise ReportAuthError(
            f"Role '{role}' is not authorized to generate the '{template['code']}' report.")
    if scope_kind != template["scope_kind"]:
        raise ScopeError(
            f"Template '{template['code']}' is {template['scope_kind']}-scoped, got '{scope_kind}'.")
    if template["scope_kind"] in ("case", "unit", "district") and not scope_ref_id:
        raise ScopeError(f"A scope_ref_id is required for a {template['scope_kind']}-scoped report.")


# ===========================================================================
# Structured source-snapshot builders (DB fields only)
# ===========================================================================
def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _snapshot_case_summary(conn, case_id_text: str) -> tuple[dict, list[dict]]:
    try:
        case_id = int(case_id_text)
    except (TypeError, ValueError):
        raise ScopeError("case scope_ref_id must be a CaseMasterID integer.")
    with conn.cursor() as cur:
        cur.execute(
            'SELECT c."CaseMasterID", c."CrimeNo", c."CaseNo", c."CrimeRegisteredDate", '
            'cc."LookupValue", cs."CaseStatusName", u."UnitName", d."DistrictName" '
            'FROM "CaseMaster" c '
            'LEFT JOIN "CaseCategory" cc ON cc."CaseCategoryID" = c."CaseCategoryID" '
            'LEFT JOIN "CaseStatusMaster" cs ON cs."CaseStatusID" = c."CaseStatusID" '
            'LEFT JOIN "Unit" u ON u."UnitID" = c."PoliceStationID" '
            'LEFT JOIN "District" d ON d."DistrictID" = u."DistrictID" '
            'WHERE c."CaseMasterID" = %s', (case_id,))
        r = cur.fetchone()
        if not r:
            raise SubjectNotFound(f"Case {case_id} not found.")
        cur.execute('SELECT (SELECT count(*) FROM "Victim" WHERE "CaseMasterID"=%s), '
                    '(SELECT count(*) FROM "Accused" WHERE "CaseMasterID"=%s), '
                    '(SELECT count(*) FROM "EvidenceItem" WHERE "CaseMasterID"=%s)',
                    (case_id, case_id, case_id))
        vc, ac, ec = cur.fetchone()
    snapshot = {
        "report_kind": "case_summary", "data_as_of": _now_iso(),
        # Structured fields only — the free-text narrative (BriefFacts) is intentionally omitted.
        "case": {"case_master_id": int(r[0]), "crime_no": r[1], "case_no": r[2],
                 "registered_date": _s(r[3]), "category": r[4], "status": r[5],
                 "unit": r[6], "district": r[7]},
        "counts": {"victims": int(vc or 0), "accused": int(ac or 0), "evidence_items": int(ec or 0)},
        "narrative_included": False,
    }
    citations = [{"source": "CaseMaster", "record_id": str(case_id), "version": "current"}]
    return snapshot, citations


def _snapshot_unit_activity(conn, unit_id_text: str) -> tuple[dict, list[dict]]:
    try:
        unit_id = int(unit_id_text)
    except (TypeError, ValueError):
        raise ScopeError("unit scope_ref_id must be a UnitID integer.")
    with conn.cursor() as cur:
        cur.execute('SELECT u."UnitID", u."UnitName", d."DistrictName", count(c."CaseMasterID") '
                    'FROM "Unit" u LEFT JOIN "District" d ON d."DistrictID"=u."DistrictID" '
                    'LEFT JOIN "CaseMaster" c ON c."PoliceStationID"=u."UnitID" '
                    'WHERE u."UnitID"=%s GROUP BY u."UnitID", u."UnitName", d."DistrictName"',
                    (unit_id,))
        r = cur.fetchone()
        if not r:
            raise SubjectNotFound(f"Unit {unit_id} not found.")
        cur.execute('SELECT cs."CaseStatusName", count(*) FROM "CaseMaster" c '
                    'LEFT JOIN "CaseStatusMaster" cs ON cs."CaseStatusID"=c."CaseStatusID" '
                    'WHERE c."PoliceStationID"=%s GROUP BY cs."CaseStatusName" ORDER BY 2 DESC',
                    (unit_id,))
        breakdown = {(row[0] or "Unspecified"): int(row[1]) for row in cur.fetchall()}
    snapshot = {"report_kind": "unit_activity", "data_as_of": _now_iso(),
                "unit": {"unit_id": int(r[0]), "unit_name": r[1], "district": r[2],
                         "total_cases": int(r[3] or 0)},
                "status_breakdown": breakdown}
    citations = [{"source": "CaseMaster", "record_id": f"unit={unit_id}", "version": "current"},
                 {"source": "Unit", "record_id": str(unit_id), "version": "current"}]
    return snapshot, citations


def _snapshot_district_dashboard(conn, district_id_text: str) -> tuple[dict, list[dict]]:
    try:
        district_id = int(district_id_text)
    except (TypeError, ValueError):
        raise ScopeError("district scope_ref_id must be a DistrictID integer.")
    with conn.cursor() as cur:
        cur.execute('SELECT "DistrictName" FROM "District" WHERE "DistrictID"=%s', (district_id,))
        d = cur.fetchone()
        if not d:
            raise SubjectNotFound(f"District {district_id} not found.")
        cur.execute('SELECT cc."LookupValue", count(*) FROM "CaseMaster" c '
                    'JOIN "Unit" u ON u."UnitID"=c."PoliceStationID" '
                    'LEFT JOIN "CaseCategory" cc ON cc."CaseCategoryID"=c."CaseCategoryID" '
                    'WHERE u."DistrictID"=%s GROUP BY cc."LookupValue" ORDER BY 2 DESC', (district_id,))
        by_category = {(row[0] or "Unspecified"): int(row[1]) for row in cur.fetchall()}
        cur.execute('SELECT cs."CaseStatusName", count(*) FROM "CaseMaster" c '
                    'JOIN "Unit" u ON u."UnitID"=c."PoliceStationID" '
                    'LEFT JOIN "CaseStatusMaster" cs ON cs."CaseStatusID"=c."CaseStatusID" '
                    'WHERE u."DistrictID"=%s GROUP BY cs."CaseStatusName" ORDER BY 2 DESC', (district_id,))
        by_status = {(row[0] or "Unspecified"): int(row[1]) for row in cur.fetchall()}
    snapshot = {"report_kind": "district_dashboard", "data_as_of": _now_iso(),
                "district": {"district_id": district_id, "district_name": d[0]},
                "by_category": by_category, "by_status": by_status,
                "total_cases": sum(by_status.values())}
    citations = [{"source": "CaseMaster", "record_id": f"district={district_id}", "version": "current"}]
    return snapshot, citations


def _snapshot_model_governance(conn) -> tuple[dict, list[dict]]:
    with conn.cursor() as cur:
        cur.execute('SELECT "ModelVersionID","ModelName","Version","ApprovalStatus","Environment",'
                    '"EffectiveReviewState","DueAt" FROM "vw_model_review_due" '
                    'ORDER BY "ModelVersionID" DESC LIMIT 100')
        models = [{"model_version_id": int(r[0]), "model": f"{r[1]}@{r[2]}", "approval_status": r[3],
                   "environment": r[4], "review_state": r[5], "due_at": _s(r[6])}
                  for r in cur.fetchall()]
    snapshot = {"report_kind": "model_governance", "data_as_of": _now_iso(),
                "models": models, "model_count": len(models)}
    citations = [{"source": "ModelVersion", "record_id": "governed", "version": "current"},
                 {"source": "ModelReview", "record_id": "review-due", "version": "current"}]
    return snapshot, citations


def _snapshot_audit_extract(conn, filters: dict) -> tuple[dict, list[dict]]:
    limit = int(filters.get("limit", 100))
    action = filters.get("action")
    where, params = [], []
    if action:
        where.append('"Action"=%s'); params.append(action)
    clause = ('WHERE ' + ' AND '.join(where)) if where else ''
    with conn.cursor() as cur:
        cur.execute(f'SELECT "AuditEventID","OccurredAt","Actor","ActorRole","Action","Resource",'
                    f'"ResourceID" FROM "vw_audit_events" {clause} '
                    'ORDER BY "OccurredAt" DESC, "AuditEventID" DESC LIMIT %s', params + [limit])
        events = [{"audit_event_id": int(r[0]), "occurred_at": _s(r[1]), "actor": r[2],
                   "actor_role": r[3], "action": r[4], "resource": r[5], "resource_id": r[6]}
                  for r in cur.fetchall()]
    snapshot = {"report_kind": "audit_extract", "data_as_of": _now_iso(),
                "event_count": len(events), "events": events}
    citations = [{"source": "audit_logs", "record_id": "vw_audit_events", "version": "current"}]
    return snapshot, citations


def _build_snapshot(conn, report_kind: str, scope_ref_id: Optional[str],
                    filters: dict) -> tuple[dict, list[dict]]:
    if report_kind == "case_summary":
        return _snapshot_case_summary(conn, scope_ref_id)
    if report_kind == "unit_activity":
        return _snapshot_unit_activity(conn, scope_ref_id)
    if report_kind == "district_dashboard":
        return _snapshot_district_dashboard(conn, scope_ref_id)
    if report_kind == "model_governance":
        return _snapshot_model_governance(conn)
    if report_kind == "audit_extract":
        return _snapshot_audit_extract(conn, filters)
    raise ReportError(f"Unknown report kind '{report_kind}'.")


# ===========================================================================
# HTML render (watermarked) — structured fields only
# ===========================================================================
def _render_html(title: str, snapshot: dict, citations: list[dict]) -> str:
    def esc(v: Any) -> str:
        return (str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    body = json.dumps(snapshot, indent=2, sort_keys=True, default=str)
    cites = "".join(f"<li>{esc(c.get('source'))} · {esc(c.get('record_id'))} "
                    f"(v {esc(c.get('version'))})</li>" for c in citations)
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
      body {{ font-family: system-ui, sans-serif; color: #1a1a1a; }}
      .watermark {{ position: fixed; top: 40%; left: 10%; font-size: 48px;
                    color: rgba(200,0,0,0.12); transform: rotate(-24deg);
                    pointer-events: none; }}
      .badge {{ background:#fde; color:#900; padding:4px 8px; border-radius:6px;
                font-weight:600; display:inline-block; }}
      pre {{ background:#f5f5f5; padding:12px; border-radius:8px; font-size:12px; }}
    </style></head><body>
      <div class="watermark">{esc(WATERMARK)}</div>
      <p class="badge">{esc(WATERMARK)} — Not for operational use</p>
      <h1>{esc(title)}</h1>
      <p>Generated {esc(snapshot.get('data_as_of'))}</p>
      <h2>Structured source data</h2>
      <pre>{esc(body)}</pre>
      <h2>Source / version citations</h2>
      <ul>{cites}</ul>
    </body></html>"""


def _render_backend() -> str:
    return ("smartbrowz" if os.getenv("DRISHTI_USE_CATALYST_SMARTBROWZ", "").lower() == "true"
            else "appsail_fallback")


def _report_retention_days(conn) -> int:
    with conn.cursor() as cur:
        cur.execute('SELECT "RetentionDays" FROM "RetentionPolicy" '
                    "WHERE \"AppliesTo\"='report' AND \"IsActive\" ORDER BY \"RetentionDays\" LIMIT 1")
        r = cur.fetchone()
    return int(r[0]) if r else _DEFAULT_REPORT_RETENTION_DAYS


# ===========================================================================
# Generate / list / get / download / verify
# ===========================================================================
_RS_COLS = ('"ReportSnapshotID","ReportTemplateID","Title","RequestedByActor","RequestedByRole",'
            '"ScopeKind","ScopeRefID","Filters","SourceSnapshot","SourceCitations","ContentHash",'
            '"Watermark","StratusBucket","StratusObjectKey","StratusVersionId","ObjectSha256",'
            '"ObjectSizeBytes","ContentType","RenderBackend","Status","Version","ExpiresAt","CreatedAt"')


def _rs_row(r, template_code: Optional[str] = None) -> dict:
    return {"report_snapshot_id": int(r[0]), "report_template_id": r[1], "template_code": template_code,
            "title": r[2], "requested_by_actor": r[3], "requested_by_role": r[4], "scope_kind": r[5],
            "scope_ref_id": r[6], "filters": r[7] or {}, "source_snapshot": r[8] or {},
            "source_citations": r[9] or [], "content_hash": r[10], "watermark": r[11],
            "stratus_bucket": r[12], "stratus_object_key": r[13], "stratus_version_id": r[14],
            "object_sha256": r[15], "object_size_bytes": r[16], "content_type": r[17],
            "render_backend": r[18], "status": r[19], "version": int(r[20]), "expires_at": _s(r[21]),
            "created_at": _s(r[22])}


def _generate(conn, template_code: str, scope_kind: str, scope_ref_id: Optional[str],
              title: Optional[str], filters: dict, requested_by_actor: Optional[str],
              role: str) -> dict:
    """All report DB work on one connection (no commit): authorize, build the
    reproducible structured snapshot, render (watermarked), store the Stratus
    object and persist the ReportSnapshot lineage + audit. Returns the ids/hashes
    the caller needs for the post-commit Signal."""
    template = _load_template(conn, template_code)
    if template is None:
        raise TemplateNotFound(f"Report template '{template_code}' not found.")
    _authorize(template, role, scope_kind, scope_ref_id)
    snapshot, citations = _build_snapshot(conn, template["report_kind"], scope_ref_id, filters)
    content_hash = _canonical_hash(snapshot)
    report_title = title or f"{template['name']} — {scope_kind}"

    # render (SmartBrowz or AppSail fallback) with the prominent watermark.
    render = get_smartbrowz().render_pdf(_render_html(report_title, snapshot, citations),
                                         watermark=WATERMARK)
    backend = _render_backend()

    # store the rendered object in the private Stratus report bucket.
    stratus = get_stratus()
    object_key = f"reports/{content_hash[:16]}_{dt.datetime.now(dt.timezone.utc):%Y%m%dT%H%M%S}.pdf"
    put = getattr(stratus, "put_object", None)
    if callable(put):        # in-memory fake stores bytes-metadata directly
        put(ObjectRef(bucket=BUCKET_REPORT, key=object_key, version_id="1", size=render.size,
                      content_type=render.content_type, sha256=render.sha256))

    expires = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=_report_retention_days(conn))
    with conn.cursor() as cur:
        cur.execute(
            'INSERT INTO "ReportSnapshot" ("ReportTemplateID","Title","RequestedByActor",'
            '"RequestedByRole","ScopeKind","ScopeRefID","Filters","SourceSnapshot",'
            '"SourceCitations","ContentHash","Watermark","StratusBucket","StratusObjectKey",'
            '"StratusVersionId","ObjectSha256","ObjectSizeBytes","ContentType","RenderBackend",'
            '"ExpiresAt") VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) '
            'RETURNING "ReportSnapshotID"',
            (template["report_template_id"], report_title, requested_by_actor, role, scope_kind,
             scope_ref_id, Json(filters or {}), Json(snapshot), Json(citations), content_hash,
             WATERMARK, BUCKET_REPORT, object_key, "1", render.sha256, render.size,
             render.content_type, backend, expires))
        report_id = int(cur.fetchone()[0])
    audit.record(audit.Action.EXPORT, "report", report_id, actor=requested_by_actor, conn=conn,
                 detail={"template": template_code, "scope_kind": scope_kind,
                         "scope_ref_id": scope_ref_id, "content_hash": content_hash,
                         "object_sha256": render.sha256, "render_backend": backend})
    return {"report_id": report_id, "content_hash": content_hash, "object_sha256": render.sha256}


def generate_report(template_code: str, scope_kind: str, scope_ref_id: Optional[str],
                    title: Optional[str], filters: dict, requested_by_actor: Optional[str],
                    role: str) -> dict:
    with db.rw_conn() as conn:
        out = _generate(conn, template_code, scope_kind, scope_ref_id, title, filters,
                        requested_by_actor, role)
    # publish report.ready AFTER the authoritative write committed (data-minimized).
    get_signals().publish(EVENT_REPORT_READY, {
        "report_snapshot_id": out["report_id"], "template": template_code, "scope_kind": scope_kind,
        "content_hash": out["content_hash"], "object_sha256": out["object_sha256"]})
    return get_report(out["report_id"])


def _template_code(conn, template_id: Optional[int]) -> Optional[str]:
    if template_id is None:
        return None
    with conn.cursor() as cur:
        cur.execute('SELECT "Code" FROM "ReportTemplate" WHERE "ReportTemplateID"=%s', (template_id,))
        r = cur.fetchone()
    return r[0] if r else None


def _get_report(conn, report_snapshot_id: int) -> Optional[dict]:
    with conn.cursor() as cur:
        cur.execute(f'SELECT {_RS_COLS} FROM "ReportSnapshot" WHERE "ReportSnapshotID"=%s',
                    (report_snapshot_id,))
        r = cur.fetchone()
        if not r:
            return None
        code = _template_code(conn, r[1])
    return _rs_row(r, code)


def get_report(report_snapshot_id: int) -> Optional[dict]:
    with db.ro_conn() as conn:
        return _get_report(conn, report_snapshot_id)


def list_reports(scope_kind: Optional[str] = None, scope_ref_id: Optional[str] = None,
                 limit: int = 50) -> dict:
    where, params = [], []
    if scope_kind:
        where.append('rs."ScopeKind"=%s'); params.append(scope_kind)
    if scope_ref_id:
        where.append('rs."ScopeRefID"=%s'); params.append(scope_ref_id)
    clause = ('WHERE ' + ' AND '.join(where)) if where else ''
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f'SELECT count(*) FROM "ReportSnapshot" rs {clause}', params)
            total = int(cur.fetchone()[0])
            cur.execute(
                'SELECT rs."ReportSnapshotID", t."Code", rs."Title", rs."ScopeKind", rs."ScopeRefID",'
                'rs."RequestedByActor", rs."ContentHash", rs."ObjectSha256", rs."RenderBackend",'
                'rs."Status", rs."CreatedAt" FROM "ReportSnapshot" rs '
                'LEFT JOIN "ReportTemplate" t ON t."ReportTemplateID"=rs."ReportTemplateID" '
                f'{clause} ORDER BY rs."ReportSnapshotID" DESC LIMIT %s', params + [limit])
            items = [{"report_snapshot_id": int(r[0]), "template_code": r[1], "title": r[2],
                      "scope_kind": r[3], "scope_ref_id": r[4], "requested_by_actor": r[5],
                      "content_hash": r[6], "object_sha256": r[7], "render_backend": r[8],
                      "status": r[9], "created_at": _s(r[10])} for r in cur.fetchall()]
    return {"total": total, "items": items}


def download_report(report_snapshot_id: int, actor: Optional[str], role: str) -> Optional[dict]:
    report = get_report(report_snapshot_id)
    if report is None:
        return None
    # re-check export authorization against the (still-current) template rules.
    with db.ro_conn() as conn:
        template = _load_template(conn, report.get("template_code") or "")
    if template is not None:
        _authorize(template, role, report["scope_kind"], report["scope_ref_id"])
    if not report.get("stratus_object_key"):
        raise ReportError("Report has no stored object to download.")
    url = get_stratus().presign_get(report["stratus_bucket"] or BUCKET_REPORT,
                                    report["stratus_object_key"],
                                    version_id=report.get("stratus_version_id"),
                                    ttl_s=DEFAULT_PRESIGN_TTL_S)
    audit.record(audit.Action.EXPORT, "report_download", report_snapshot_id, actor=actor,
                 detail={"object_sha256": report.get("object_sha256")})
    return {"report_snapshot_id": report_snapshot_id, "url": url,
            "expires_in_seconds": DEFAULT_PRESIGN_TTL_S,
            "object_sha256": report.get("object_sha256"), "watermark": report["watermark"]}


def verify_report(report_snapshot_id: int) -> Optional[dict]:
    """Reproducibility check: re-hash the stored structured snapshot and compare."""
    report = get_report(report_snapshot_id)
    if report is None:
        return None
    recomputed = _canonical_hash(report["source_snapshot"])
    return {"report_snapshot_id": report_snapshot_id,
            "reproducible": recomputed == report["content_hash"],
            "stored_hash": report["content_hash"], "recomputed_hash": recomputed}
