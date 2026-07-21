"""Reference/option lookups + workflow metadata for the intake wizard.

Read-only (ro_conn). Everything the wizard renders — units, districts,
categories, statuses, gravity, crime taxonomy, acts/sections, party roles, and
the category-specific transition table — comes from here so the UI never
hard-codes a single lifecycle (DoD §C/§D).
"""
from __future__ import annotations

from typing import Optional

from .. import db
from ..config import get_settings
from ..datastore import seed as ds_seed
from . import workflow as wf


def _rows(cur, sql, params=None):
    cur.execute(sql, params or ())
    return cur.fetchall()


def _ds_ref(table: str, where: Optional[dict] = None, limit: int = 5000) -> list[dict]:
    return ds_seed.reference_repo().query(table, where=where, limit=limit)


def _reference_lookups_datastore(unit_id: Optional[int], officer_limit: int) -> dict:
    """Deployed operational reference reads from Catalyst Data Store (seeded from
    the serving-export subset) — used when no RDS ``DATABASE_URL`` is configured.
    Mirrors the RDS projection's output shape (Prompt 21 §B)."""
    def _n(row, *keys, default=None):
        for k in keys:
            if row.get(k) is not None:
                return row[k]
        return default

    categories = [{"id": r.get("CaseCategoryID"), "name": _n(r, "LookupValue", "CategoryName")}
                  for r in _ds_ref("CaseCategory")]
    gravities = [{"id": r.get("GravityOffenceID"), "name": _n(r, "LookupValue", "Name")}
                 for r in _ds_ref("GravityOffence")]
    districts = [{"id": r.get("DistrictID"), "name": r.get("DistrictName")}
                 for r in _ds_ref("District")]
    units = [{"id": r.get("UnitID"), "name": r.get("UnitName"), "parent_id": r.get("DistrictID")}
             for r in _ds_ref("Unit", limit=2000)]
    crime_heads = [{"id": r.get("CrimeHeadID"), "name": _n(r, "CrimeGroupName", "HeadName")}
                   for r in _ds_ref("CrimeHead")]
    crime_subheads = [{"id": r.get("CrimeSubHeadID"), "name": _n(r, "CrimeHeadName", "Name"),
                       "parent_id": r.get("CrimeHeadID")} for r in _ds_ref("CrimeSubHead")]
    statuses = [{"id": r.get("CaseStatusID"), "name": r.get("CaseStatusName")}
                for r in _ds_ref("CaseStatusMaster")]
    officers = [{"id": r.get("EmployeeID"), "name": _n(r, "FirstName", "EmployeeName"),
                 "parent_id": r.get("UnitID")}
                for r in _ds_ref("Employee", where=({"UnitID": unit_id} if unit_id else None),
                                 limit=officer_limit)]
    acts = [{"act_code": r.get("ActCode"), "short_name": r.get("ShortName"),
             "description": r.get("ActDescription")} for r in _ds_ref("Act")]
    sections = [{"section_code": r.get("SectionCode"), "act_code": r.get("ActCode"),
                 "description": r.get("SectionDescription")} for r in _ds_ref("Section")]
    party_roles = [{"value": v, "label": wf.PARTY_ROLE_LABELS.get(v, v.title())}
                   for v in wf.PARTY_ROLES]
    return {
        "categories": categories, "gravities": gravities, "districts": districts,
        "units": units, "crime_heads": crime_heads, "crime_subheads": crime_subheads,
        "statuses": statuses, "officers": officers, "courts": [],
        "acts": acts, "sections": sections, "party_roles": party_roles,
    }


def reference_lookups(unit_id: Optional[int] = None, officer_limit: int = 500) -> dict:
    # Deployed AppSail has no DATABASE_URL: serve operational reference data from
    # Catalyst Data Store (§B). The RDS path below is used only when an analytics
    # DATABASE_URL is configured (dev / the DB test pass) — byte-identical.
    if get_settings().database_url:
        try:
            return _reference_lookups_rds(unit_id, officer_limit)
        except Exception:  # noqa: BLE001 — RDS unreachable/over-quota -> Data Store
            pass
    return _reference_lookups_datastore(unit_id, officer_limit)


def _reference_lookups_rds(unit_id: Optional[int], officer_limit: int) -> dict:
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
    transitions_by_category: dict[str, list[dict]] = {cat: [] for cat in categories}
    # Kinds/statuses/party-roles are static (in code). Per-category transitions
    # come from the operational store: RDS when configured (dev / DB pass), else
    # the Data Store-native workflow (deployed AppSail has no DATABASE_URL).
    if get_settings().database_url:
        try:
            with db.ro_conn() as conn:
                for cat in categories:
                    transitions_by_category[cat] = wf.load_transitions(conn, cat)
        except Exception:  # noqa: BLE001 — RDS unreachable -> empty transitions offline
            transitions_by_category = {cat: [] for cat in categories}
    return {
        "kinds": kinds,
        "statuses": statuses,
        "party_roles": party_roles,
        "transitions_by_category": transitions_by_category,
        "event_labels": wf.EVENT_LABELS,
    }
