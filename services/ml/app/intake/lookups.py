"""Reference/option lookups + workflow metadata for the intake wizard.

Read-only (ro_conn). Everything the wizard renders — units, districts,
categories, statuses, gravity, crime taxonomy, acts/sections, party roles, and
the category-specific transition table — comes from here so the UI never
hard-codes a single lifecycle (DoD §C/§D).
"""
from __future__ import annotations

from typing import Optional

from .. import db
from . import workflow as wf


def _rows(cur, sql, params=None):
    cur.execute(sql, params or ())
    return cur.fetchall()


def reference_lookups(unit_id: Optional[int] = None, officer_limit: int = 500) -> dict:
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            categories = [{"id": r[0], "name": r[1]} for r in _rows(
                cur, 'SELECT "CaseCategoryID","LookupValue" FROM "CaseCategory" ORDER BY "CaseCategoryID"')]
            gravities = [{"id": r[0], "name": r[1]} for r in _rows(
                cur, 'SELECT "GravityOffenceID","LookupValue" FROM "GravityOffence" ORDER BY "GravityOffenceID"')]
            districts = [{"id": r[0], "name": r[1]} for r in _rows(
                cur, 'SELECT "DistrictID","DistrictName" FROM "District" ORDER BY "DistrictName"')]
            units = [{"id": r[0], "name": r[1], "parent_id": r[2]} for r in _rows(
                cur, 'SELECT "UnitID","UnitName","DistrictID" FROM "Unit" ORDER BY "UnitName" LIMIT 2000')]
            crime_heads = [{"id": r[0], "name": r[1]} for r in _rows(
                cur, 'SELECT "CrimeHeadID","CrimeGroupName" FROM "CrimeHead" ORDER BY "CrimeGroupName"')]
            crime_subheads = [{"id": r[0], "name": r[1], "parent_id": r[2]} for r in _rows(
                cur, 'SELECT "CrimeSubHeadID","CrimeHeadName","CrimeHeadID" FROM "CrimeSubHead" ORDER BY "CrimeHeadName"')]
            statuses = [{"id": r[0], "name": r[1]} for r in _rows(
                cur, 'SELECT "CaseStatusID","CaseStatusName" FROM "CaseStatusMaster" ORDER BY "CaseStatusID"')]
            if unit_id:
                officers = [{"id": r[0], "name": r[1], "parent_id": r[2]} for r in _rows(
                    cur,
                    'SELECT "EmployeeID","FirstName","UnitID" FROM "Employee" '
                    'WHERE "UnitID"=%s ORDER BY "EmployeeID" LIMIT %s',
                    (unit_id, officer_limit))]
            else:
                officers = [{"id": r[0], "name": r[1], "parent_id": r[2]} for r in _rows(
                    cur,
                    'SELECT "EmployeeID","FirstName","UnitID" FROM "Employee" '
                    'ORDER BY "EmployeeID" LIMIT %s', (officer_limit,))]
            courts = [{"id": r[0], "name": r[1], "parent_id": r[2]} for r in _rows(
                cur, 'SELECT "CourtID","CourtName","DistrictID" FROM "Court" ORDER BY "CourtName" LIMIT 1000')]
            acts = [{"act_code": r[0], "short_name": r[1], "description": r[2]} for r in _rows(
                cur, 'SELECT "ActCode","ShortName","ActDescription" FROM "Act" WHERE "Active" ORDER BY "ActCode"')]
            sections = [{"section_code": r[0], "act_code": r[1], "description": r[2]} for r in _rows(
                cur, 'SELECT "SectionCode","ActCode","SectionDescription" FROM "Section" '
                     'WHERE "Active" ORDER BY "ActCode","SectionCode"')]

    party_roles = [{"value": v, "label": wf.PARTY_ROLE_LABELS.get(v, v.title())}
                   for v in wf.PARTY_ROLES]
    return {
        "categories": categories, "gravities": gravities, "districts": districts,
        "units": units, "crime_heads": crime_heads, "crime_subheads": crime_subheads,
        "statuses": statuses, "officers": officers, "courts": courts,
        "acts": acts, "sections": sections, "party_roles": party_roles,
    }


def workflow_metadata() -> dict:
    """Kinds + statuses + party roles + per-category transition table (from DB)."""
    kinds = []
    for ck in wf.CASE_KINDS.values():
        kinds.append({
            "kind": ck.name, "category": ck.category, "label": ck.label,
            "allow_accused": ck.allow_accused, "allow_arrest": ck.allow_arrest,
            "allow_chargesheet": ck.allow_chargesheet, "allow_court": ck.allow_court,
            "initial_event": ck.initial_event, "initial_status": ck.initial_status,
            "description": ck.description,
            "allowed_party_roles": wf.allowed_party_roles(ck.name),
        })
    statuses = [{"code": c, "label": wf.STATUS_LABELS.get(c, c),
                 "legacy_name": wf.STATUS_TO_LEGACY.get(c)}
                for c in wf.STATUS_LABELS]
    party_roles = [{"value": v, "label": wf.PARTY_ROLE_LABELS.get(v, v.title())}
                   for v in wf.PARTY_ROLES]

    categories = sorted({ck.category for ck in wf.CASE_KINDS.values()})
    transitions_by_category: dict[str, list[dict]] = {}
    with db.ro_conn() as conn:
        for cat in categories:
            transitions_by_category[cat] = wf.load_transitions(conn, cat)
    return {
        "kinds": kinds,
        "statuses": statuses,
        "party_roles": party_roles,
        "transitions_by_category": transitions_by_category,
        "event_labels": wf.EVENT_LABELS,
    }
