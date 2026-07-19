"""Notifications / work-task service (Phase 15).

Task assignments, per-actor notification preferences, escalation SLA/due state
and per-channel delivery history. In-app notifications always work; email/push
go through the Catalyst Mail/Push contracts (suppressed unless
``DRISHTI_NOTIFY_ENABLED``). A ``notification.created`` / ``task.escalated``
Signal is published AFTER the authoritative Data Store write commits.

Data minimization is enforced here: a notification/summary is clipped and
stripped of newlines, and the Signal payload carries only ids/type/severity/
resource pointers — never the free-text body, evidence content, narratives or
personal identifiers.

Testability: the DB work of every write path lives in an internal
``_fn(conn, ...)`` helper (no commit); the public wrapper opens db.rw_conn(),
commits, then performs the post-commit external send + Signal. Tests drive the
``_fn`` helpers under the ``rw_rollback`` fixture so nothing persists.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Optional

from psycopg2.extras import Json

from .. import audit, db
from ..notify_channels import get_mail, get_push
from ..signals import (EVENT_NOTIFICATION_CREATED, EVENT_TASK_ESCALATED, get_signals)

_MAX_SUMMARY = 200
_MAX_TITLE = 160


def _s(v) -> Optional[str]:
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()
    return str(v) if v is not None else None


def _minimize(text: Optional[str], cap: int) -> str:
    t = (text or "").replace("\r", " ").replace("\n", " ").strip()
    return t[:cap]


def _parse_ts(v: Optional[str]):
    if not v:
        return None
    try:
        return dt.datetime.fromisoformat(v)
    except ValueError:
        return None


# ===========================================================================
# Preferences
# ===========================================================================
def _pref_row(r) -> dict:
    return {"actor_key": r[0], "in_app": bool(r[1]), "email": bool(r[2]), "push": bool(r[3]),
            "digest_frequency": r[4], "escalation_sla_hours": int(r[5])}


def get_preference(actor_key: str) -> dict:
    with db.ro_conn() as conn:
        return _get_preference(conn, actor_key)


def _get_preference(conn, actor_key: str) -> dict:
    with conn.cursor() as cur:
        cur.execute('SELECT "ActorKey","InApp","Email","Push","DigestFrequency","EscalationSlaHours" '
                    'FROM "NotificationPreference" WHERE "ActorKey"=%s', (actor_key,))
        r = cur.fetchone()
    if r:
        return _pref_row(r)
    # sensible default when no row exists yet (in-app on, email/push off).
    return {"actor_key": actor_key, "in_app": True, "email": False, "push": False,
            "digest_frequency": "immediate", "escalation_sla_hours": 24}


def _upsert_preference(conn, actor_key, in_app, email, push, digest_frequency,
                       escalation_sla_hours) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            'INSERT INTO "NotificationPreference" ("ActorKey","InApp","Email","Push",'
            '"DigestFrequency","EscalationSlaHours") VALUES (%s,%s,%s,%s,%s,%s) '
            'ON CONFLICT ("ActorKey") DO UPDATE SET "InApp"=EXCLUDED."InApp",'
            '"Email"=EXCLUDED."Email","Push"=EXCLUDED."Push",'
            '"DigestFrequency"=EXCLUDED."DigestFrequency",'
            '"EscalationSlaHours"=EXCLUDED."EscalationSlaHours","UpdatedAt"=now() '
            'RETURNING "ActorKey","InApp","Email","Push","DigestFrequency","EscalationSlaHours"',
            (actor_key, in_app, email, push, digest_frequency, escalation_sla_hours))
        row = _pref_row(cur.fetchone())
    audit.record(audit.Action.UPDATE, "notification_preference", actor_key, actor=actor_key,
                 conn=conn, detail={"email": email, "push": push})
    return row


def upsert_preference(actor_key: str, in_app: bool, email: bool, push: bool,
                      digest_frequency: str, escalation_sla_hours: int) -> dict:
    with db.rw_conn() as conn:
        return _upsert_preference(conn, actor_key, in_app, email, push, digest_frequency,
                                  escalation_sla_hours)


# ===========================================================================
# Notifications + delivery (data-minimized)
# ===========================================================================
_ND_COLS = ('"NotificationDeliveryID","Channel","Provider","Status","Detail","CreatedAt","DeliveredAt"')


def _delivery_row(r) -> dict:
    return {"notification_delivery_id": int(r[0]), "channel": r[1], "provider": r[2],
            "status": r[3], "detail": r[4] or {}, "created_at": _s(r[5]), "delivered_at": _s(r[6])}


def _deliveries_for(conn, message_id: int) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(f'SELECT {_ND_COLS} FROM "NotificationDelivery" '
                    'WHERE "NotificationMessageID"=%s ORDER BY "NotificationDeliveryID"',
                    (message_id,))
        return [_delivery_row(r) for r in cur.fetchall()]


def _write_notification(conn, recipient_actor: str, notification_type: str, summary: str,
                        *, severity: str = "info", related_resource: Optional[str] = None,
                        related_resource_id: Optional[str] = None,
                        work_task_id: Optional[int] = None,
                        actor: Optional[str] = None) -> tuple[int, list[str]]:
    """Insert the message + queued channel deliveries + audit on ``conn`` (no
    commit). Returns (message_id, external_channels_to_send)."""
    summary = _minimize(summary, _MAX_SUMMARY)
    pref = _get_preference(conn, recipient_actor)
    with conn.cursor() as cur:
        cur.execute(
            'INSERT INTO "NotificationMessage" ("NotificationType","RecipientActor","Summary",'
            '"Severity","RelatedResource","RelatedResourceID","WorkTaskID") '
            'VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING "NotificationMessageID"',
            (notification_type, recipient_actor, summary, severity, related_resource,
             str(related_resource_id) if related_resource_id is not None else None, work_task_id))
        mid = int(cur.fetchone()[0])
        channels = [("in_app", "in_app", "sent")]
        if pref["email"]:
            channels.append(("email", "catalyst_mail", "queued"))
        if pref["push"]:
            channels.append(("push", "catalyst_push", "queued"))
        for ch, provider, status in channels:
            delivered = "now()" if status == "sent" else "NULL"
            cur.execute(
                'INSERT INTO "NotificationDelivery" ("NotificationMessageID","Channel","Provider",'
                f'"Status","DeliveredAt") VALUES (%s,%s,%s,%s,{delivered})', (mid, ch, provider, status))
    audit.record(audit.Action.CREATE, "notification", mid, actor=actor or recipient_actor,
                 conn=conn, detail={"type": notification_type, "recipient": recipient_actor,
                                    "severity": severity})
    pending = [c[0] for c in channels if c[0] != "in_app"]
    return mid, pending


def deliver_notification(recipient_actor: str, notification_type: str, summary: str,
                         *, severity: str = "info", related_resource: Optional[str] = None,
                         related_resource_id: Optional[str] = None,
                         work_task_id: Optional[int] = None, actor: Optional[str] = None) -> dict:
    """Public path: authoritative write (commit), then external send + Signal."""
    summary = _minimize(summary, _MAX_SUMMARY)
    with db.rw_conn() as conn:
        mid, pending = _write_notification(
            conn, recipient_actor, notification_type, summary, severity=severity,
            related_resource=related_resource, related_resource_id=related_resource_id,
            work_task_id=work_task_id, actor=actor)

    # external channels (suppressed unless DRISHTI_NOTIFY_ENABLED) + status update.
    if "email" in pending:
        res = get_mail().send(to_actor=recipient_actor, subject=f"DRISHTI: {notification_type}",
                              summary=summary, resource=related_resource)
        _update_delivery(mid, "email", res.status, res.provider, res.detail)
    if "push" in pending:
        res = get_push().send(to_actor=recipient_actor, title="DRISHTI", summary=summary,
                              resource=related_resource)
        _update_delivery(mid, "push", res.status, res.provider, res.detail)

    # publish the Signal AFTER commit (no free-text body in the payload).
    get_signals().publish(EVENT_NOTIFICATION_CREATED, {
        "notification_message_id": mid, "notification_type": notification_type,
        "recipient": recipient_actor, "severity": severity,
        "related_resource": related_resource, "related_resource_id": related_resource_id})

    with db.ro_conn() as conn:
        return _get_notification(conn, mid)


def _update_delivery(message_id: int, channel: str, status: str, provider: str,
                     detail: Optional[str]) -> None:
    with db.rw_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                'UPDATE "NotificationDelivery" SET "Status"=%s, "Provider"=%s, "Detail"=%s, '
                '"DeliveredAt"=CASE WHEN %s=\'sent\' THEN now() ELSE "DeliveredAt" END '
                'WHERE "NotificationMessageID"=%s AND "Channel"=%s',
                (status, provider, Json({"status": detail} if detail else {}), status,
                 message_id, channel))


def _get_notification(conn, message_id: int) -> Optional[dict]:
    with conn.cursor() as cur:
        cur.execute('SELECT "NotificationMessageID","NotificationType","RecipientActor","Summary",'
                    '"Severity","RelatedResource","RelatedResourceID","WorkTaskID","ReadAt","CreatedAt" '
                    'FROM "NotificationMessage" WHERE "NotificationMessageID"=%s', (message_id,))
        r = cur.fetchone()
    if not r:
        return None
    out = {"notification_message_id": int(r[0]), "notification_type": r[1], "recipient_actor": r[2],
           "summary": r[3], "severity": r[4], "related_resource": r[5], "related_resource_id": r[6],
           "work_task_id": r[7], "read_at": _s(r[8]), "created_at": _s(r[9])}
    out["deliveries"] = _deliveries_for(conn, message_id)
    return out


def list_notifications(recipient_actor: str, unread_only: bool = False, limit: int = 50) -> dict:
    where = ['"RecipientActor" = %s']
    params: list[Any] = [recipient_actor]
    if unread_only:
        where.append('"ReadAt" IS NULL')
    clause = 'WHERE ' + ' AND '.join(where)
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f'SELECT count(*) FROM "NotificationMessage" {clause}', params)
            total = int(cur.fetchone()[0])
            cur.execute('SELECT count(*) FROM "NotificationMessage" WHERE "RecipientActor"=%s '
                        'AND "ReadAt" IS NULL', (recipient_actor,))
            unread = int(cur.fetchone()[0])
            cur.execute('SELECT "NotificationMessageID","NotificationType","RecipientActor","Summary",'
                        '"Severity","RelatedResource","RelatedResourceID","WorkTaskID","ReadAt",'
                        f'"CreatedAt" FROM "NotificationMessage" {clause} '
                        'ORDER BY "CreatedAt" DESC, "NotificationMessageID" DESC LIMIT %s',
                        params + [limit])
            rows = cur.fetchall()
            items = []
            for r in rows:
                items.append({"notification_message_id": int(r[0]), "notification_type": r[1],
                              "recipient_actor": r[2], "summary": r[3], "severity": r[4],
                              "related_resource": r[5], "related_resource_id": r[6],
                              "work_task_id": r[7], "read_at": _s(r[8]), "created_at": _s(r[9]),
                              "deliveries": _deliveries_for(conn, int(r[0]))})
    return {"total": total, "unread": unread, "items": items}


def _mark_read(conn, message_id: int, recipient_actor: str) -> Optional[dict]:
    with conn.cursor() as cur:
        cur.execute('UPDATE "NotificationMessage" SET "ReadAt"=now() '
                    'WHERE "NotificationMessageID"=%s AND "RecipientActor"=%s AND "ReadAt" IS NULL',
                    (message_id, recipient_actor))
    return _get_notification(conn, message_id)


def mark_read(message_id: int, recipient_actor: str) -> Optional[dict]:
    with db.rw_conn() as conn:
        return _mark_read(conn, message_id, recipient_actor)


# ===========================================================================
# Work tasks
# ===========================================================================
_WT_COLS = ('"WorkTaskID","TaskType","Title","RelatedResource","RelatedResourceID","CaseMasterID",'
            '"UnitID","AssigneeActor","AssignedByActor","Priority","Status","DueAt",'
            '"EscalationSlaHours","EscalatedAt","CreatedAt"')


def _wt_row(r) -> dict:
    return {"work_task_id": int(r[0]), "task_type": r[1], "title": r[2], "related_resource": r[3],
            "related_resource_id": r[4], "case_master_id": r[5], "unit_id": r[6],
            "assignee_actor": r[7], "assigned_by_actor": r[8], "priority": r[9], "status": r[10],
            "due_at": _s(r[11]), "escalation_sla_hours": r[12], "escalated_at": _s(r[13]),
            "created_at": _s(r[14])}


def _create_task(conn, body, actor: Optional[str]) -> dict:
    title = _minimize(body.title, _MAX_TITLE)
    with conn.cursor() as cur:
        cur.execute(
            'INSERT INTO "WorkTask" ("TaskType","Title","RelatedResource","RelatedResourceID",'
            '"CaseMasterID","UnitID","AssigneeActor","AssignedByActor","Priority","DueAt",'
            f'"EscalationSlaHours") VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING {_WT_COLS}',
            (body.task_type, title, body.related_resource, body.related_resource_id,
             body.case_master_id, body.unit_id, body.assignee_actor, actor, body.priority,
             _parse_ts(body.due_at), body.escalation_sla_hours))
        row = _wt_row(cur.fetchone())
    audit.record(audit.Action.CREATE, "work_task", row["work_task_id"], actor=actor, conn=conn,
                 detail={"type": body.task_type, "assignee": body.assignee_actor,
                         "priority": body.priority})
    return row


def create_task(body, actor: Optional[str]) -> dict:
    with db.rw_conn() as conn:
        row = _create_task(conn, body, actor)
    if row["assignee_actor"]:
        deliver_notification(row["assignee_actor"], "task_assigned",
                             f"New {body.task_type.replace('_', ' ')} task assigned.",
                             severity="action_required", related_resource="work_task",
                             related_resource_id=str(row["work_task_id"]),
                             work_task_id=row["work_task_id"], actor=actor)
    return row


def list_tasks(assignee: Optional[str] = None, status: Optional[str] = None,
               case_master_id: Optional[int] = None, limit: int = 100) -> dict:
    where, params = [], []
    if assignee:
        where.append('"AssigneeActor" = %s'); params.append(assignee)
    if status:
        where.append('"Status" = %s'); params.append(status)
    if case_master_id is not None:
        where.append('"CaseMasterID" = %s'); params.append(case_master_id)
    clause = ('WHERE ' + ' AND '.join(where)) if where else ''
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f'SELECT count(*) FROM "WorkTask" {clause}', params)
            total = int(cur.fetchone()[0])
            cur.execute(f'SELECT {_WT_COLS} FROM "WorkTask" {clause} '
                        'ORDER BY "WorkTaskID" DESC LIMIT %s', params + [limit])
            items = [_wt_row(r) for r in cur.fetchall()]
    return {"total": total, "items": items}


def get_task(work_task_id: int) -> Optional[dict]:
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f'SELECT {_WT_COLS} FROM "WorkTask" WHERE "WorkTaskID"=%s', (work_task_id,))
            r = cur.fetchone()
    return _wt_row(r) if r else None


def _update_task(conn, work_task_id: int, body, actor: Optional[str]) -> Optional[dict]:
    sets, params = [], []
    if body.status is not None:
        sets.append('"Status"=%s'); params.append(body.status)
    if body.assignee_actor is not None:
        sets.append('"AssigneeActor"=%s'); params.append(body.assignee_actor)
    if body.priority is not None:
        sets.append('"Priority"=%s'); params.append(body.priority)
    if body.due_at is not None:
        sets.append('"DueAt"=%s'); params.append(_parse_ts(body.due_at))
    if not sets:
        with conn.cursor() as cur:
            cur.execute(f'SELECT {_WT_COLS} FROM "WorkTask" WHERE "WorkTaskID"=%s', (work_task_id,))
            r = cur.fetchone()
        return _wt_row(r) if r else None
    with conn.cursor() as cur:
        cur.execute(f'UPDATE "WorkTask" SET {", ".join(sets)} WHERE "WorkTaskID"=%s '
                    f'RETURNING {_WT_COLS}', params + [work_task_id])
        r = cur.fetchone()
        if not r:
            return None
        row = _wt_row(r)
    audit.record(audit.Action.UPDATE, "work_task", work_task_id, actor=actor, conn=conn,
                 detail={"status": body.status, "assignee": body.assignee_actor})
    return row


def update_task(work_task_id: int, body, actor: Optional[str]) -> Optional[dict]:
    with db.rw_conn() as conn:
        row = _update_task(conn, work_task_id, body, actor)
    if row is not None and body.assignee_actor:
        deliver_notification(body.assignee_actor, "task_assigned",
                             f"A {row['task_type'].replace('_', ' ')} task was assigned to you.",
                             severity="action_required", related_resource="work_task",
                             related_resource_id=str(work_task_id), work_task_id=work_task_id,
                             actor=actor)
    return row


# ===========================================================================
# Escalation (SLA / due state)
# ===========================================================================
def _escalate_db(conn, limit: int = 200) -> list[dict]:
    """Find overdue open/in-progress tasks and escalate them on ``conn`` (no
    commit, no notify/signal). Idempotent: an escalated task (EscalatedAt) is
    skipped. Returns the escalated rows."""
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT {_WT_COLS} FROM "WorkTask" '
            "WHERE \"Status\" IN ('open','in_progress') AND \"EscalatedAt\" IS NULL AND ("
            '  ("DueAt" IS NOT NULL AND now() > "DueAt") OR '
            '  ("EscalationSlaHours" IS NOT NULL AND now() > "CreatedAt" + '
            '     ("EscalationSlaHours" || \' hours\')::interval)) '
            'ORDER BY "WorkTaskID" LIMIT %s', (limit,))
        rows = [_wt_row(r) for r in cur.fetchall()]
        for wt in rows:
            cur.execute("UPDATE \"WorkTask\" SET \"Status\"='escalated', \"EscalatedAt\"=now() "
                        'WHERE "WorkTaskID"=%s', (wt["work_task_id"],))
    if rows:
        audit.record(audit.Action.UPDATE, "work_task_escalation", None, actor=None, conn=conn,
                     detail={"escalated": len(rows)})
    return rows


def run_escalations(actor: Optional[str] = None, limit: int = 200) -> dict:
    with db.rw_conn() as conn:
        rows = _escalate_db(conn, limit)
    # notify + signal AFTER commit.
    notifications_created = 0
    for wt in rows:
        recipient = wt["assignee_actor"] or wt["assigned_by_actor"]
        if recipient:
            deliver_notification(recipient, "task_escalated",
                                 f"A {wt['task_type'].replace('_', ' ')} task passed its SLA and was escalated.",
                                 severity="warning", related_resource="work_task",
                                 related_resource_id=str(wt["work_task_id"]),
                                 work_task_id=wt["work_task_id"], actor=actor)
            notifications_created += 1
        get_signals().publish(EVENT_TASK_ESCALATED, {
            "work_task_id": wt["work_task_id"], "task_type": wt["task_type"], "assignee": recipient})
    return {"checked": len(rows), "escalated": len(rows),
            "notifications_created": notifications_created,
            "escalated_task_ids": [wt["work_task_id"] for wt in rows]}
