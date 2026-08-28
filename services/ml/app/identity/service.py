"""Canonical identity + entity-resolution service (Phase 4).

Design mirrors the intake service for testability + safety:
  * Internal ``_fn(conn, ...)`` helpers do the work on an OPEN connection and
    never commit, so tests can drive full create -> merge -> unmerge flows inside
    a transaction and ROLL BACK (nothing persisted to the synthetic dev DB).
  * Public functions open app.db.rw_conn()/ro_conn() and delegate; rw_conn
    commits on clean exit.

Identity rules (non-negotiable):
  * Names/phones are ATTRIBUTES, never identity keys.
  * Entity resolution proposes candidates for HUMAN review; it NEVER auto-merges.
  * Merges are recorded in EntityMergeHistory with the exact repointed references
    so they are fully REVERSIBLE (split/unmerge).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from psycopg2.extras import Json

from .. import audit, db
from . import schemas as S


# ---------------------------------------------------------------------------
# Typed errors (router translates to HTTP)
# ---------------------------------------------------------------------------
class IdentityError(Exception):
    pass


class IdentityNotFound(IdentityError):
    pass


class IdentityConflict(IdentityError):
    pass


class IdentityValidationError(IdentityError):
    pass


def _s(v) -> Optional[str]:
    return str(v) if v is not None else None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# Tables whose CanonicalPersonID (or owner) FK is repointed on merge, with their
# primary-key column (for exact, reversible repointing). Unknown tables/columns
# are skipped gracefully via a per-table savepoint.
_PERSON_FK_TABLES: tuple[tuple[str, str, str], ...] = (
    ("CasePartyRole", "CanonicalPersonID", "CasePartyRoleID"),
    ("CanonicalEntity", "CanonicalPersonID", "CanonicalEntityID"),
    ("Accused", "CanonicalPersonID", "AccusedMasterID"),
    ("Victim", "CanonicalPersonID", "VictimMasterID"),
    ("ComplainantDetails", "CanonicalPersonID", "ComplainantID"),
    ("PersonAlias", "CanonicalPersonID", "PersonAliasID"),
    ("PersonIdentifier", "CanonicalPersonID", "PersonIdentifierID"),
    ("PersonContact", "CanonicalPersonID", "PersonContactID"),
    ("PersonAddress", "CanonicalPersonID", "PersonAddressID"),
    ("Statement", "CanonicalPersonID", "StatementID"),
    ("BailEvent", "CanonicalPersonID", "BailEventID"),
    ("PropertyItem", "OwnerCanonicalPersonID", "PropertyItemID"),
    ("GangMembership", "MemberCanonicalPersonID", "GangMembershipID"),
)

_PUBLIC_SOURCE_CURATED = "public_source_curated"
_RESERVED_IDENTITY_ATTRIBUTE_KEYS = frozenset({
    "record_origin", "is_synthetic", "source", "provenance",
    "created_via", "idempotency_key",
})
_RESERVED_IDENTITY_ATTRIBUTE_PREFIXES = ("source_", "public_source_")
_PERSON_ATTRIBUTE_TARGETS = {
    "PersonAlias": "PersonAliasID",
    "PersonIdentifier": "PersonIdentifierID",
    "PersonContact": "PersonContactID",
    "PersonAddress": "PersonAddressID",
}


def _reject_reserved_identity_attributes(attributes) -> None:
    """Keep provenance and origin metadata under server-side control."""
    reserved = sorted({
        str(key) for key in (attributes or {})
        if str(key) in _RESERVED_IDENTITY_ATTRIBUTE_KEYS
        or str(key).startswith(_RESERVED_IDENTITY_ATTRIBUTE_PREFIXES)
    })
    if reserved:
        raise IdentityValidationError(
            "Identity attributes cannot set service-managed provenance keys: "
            + ", ".join(reserved) + "."
        )


def _target_ids(values) -> list[int]:
    return sorted({int(value) for value in values if value is not None})


def _require_mutable_identity_targets(
    conn, *, person_ids=(), case_ids=(), role_ids=(),
) -> None:
    """Reject identity writes when persisted provenance marks a target curated.

    Direct targets are locked before classification. Role-linked parents are
    classified from the locked role's persisted foreign keys; they are not
    independently locked, avoiding a role/person lock-order inversion with the
    merge repoint loop.
    """
    direct_person_ids = _target_ids(person_ids)
    direct_case_ids = _target_ids(case_ids)
    target_role_ids = _target_ids(role_ids)
    linked_person_ids: set[int] = set()
    linked_case_ids: set[int] = set()

    with conn.cursor() as cur:
        if direct_person_ids:
            cur.execute(
                'SELECT "CanonicalPersonID" FROM "CanonicalPerson" '
                'WHERE "CanonicalPersonID"=ANY(%s) ORDER BY "CanonicalPersonID" FOR UPDATE',
                (direct_person_ids,),
            )
            found = {int(row[0]) for row in cur.fetchall()}
            missing = next((pid for pid in direct_person_ids if pid not in found), None)
            if missing is not None:
                raise IdentityNotFound(f"CanonicalPerson {missing} not found.")

        if direct_case_ids:
            cur.execute(
                'SELECT "CaseMasterID" FROM "CaseMaster" '
                'WHERE "CaseMasterID"=ANY(%s) ORDER BY "CaseMasterID" FOR UPDATE',
                (direct_case_ids,),
            )
            found = {int(row[0]) for row in cur.fetchall()}
            missing = next((cid for cid in direct_case_ids if cid not in found), None)
            if missing is not None:
                raise IdentityNotFound(f"Case {missing} not found.")

        if target_role_ids:
            cur.execute(
                'SELECT "CasePartyRoleID","CanonicalPersonID","CaseMasterID",'
                'COALESCE("Provenance"->>\'record_origin\'=%s,FALSE) '
                'FROM "CasePartyRole" WHERE "CasePartyRoleID"=ANY(%s) '
                'ORDER BY "CasePartyRoleID" FOR UPDATE',
                (_PUBLIC_SOURCE_CURATED, target_role_ids),
            )
            role_rows = cur.fetchall()
            found = {int(row[0]) for row in role_rows}
            missing = next((rid for rid in target_role_ids if rid not in found), None)
            if missing is not None:
                raise IdentityNotFound(f"CasePartyRole {missing} not found.")
            for role_id, person_id, case_id, is_curated in role_rows:
                if is_curated:
                    raise IdentityConflict(
                        f"Public-source curated CasePartyRole {int(role_id)} is immutable."
                    )
                if person_id is not None:
                    linked_person_ids.add(int(person_id))
                linked_case_ids.add(int(case_id))

        all_person_ids = sorted(set(direct_person_ids) | linked_person_ids)
        if all_person_ids:
            cur.execute(
                'SELECT p."CanonicalPersonID",('
                'COALESCE(p."Attributes"->>\'record_origin\'=%s,FALSE) OR EXISTS ('
                'SELECT 1 FROM "CanonicalEntity" e '
                'WHERE e."CanonicalPersonID"=p."CanonicalPersonID" '
                'AND e."Attributes"->>\'record_origin\'=%s) OR EXISTS ('
                'SELECT 1 FROM "CasePartyRole" r '
                'WHERE r."CanonicalPersonID"=p."CanonicalPersonID" '
                'AND r."Provenance"->>\'record_origin\'=%s) OR EXISTS ('
                'SELECT 1 FROM "PersonAlias" a JOIN "SourceRecord" sr '
                'ON sr."SourceRecordID"=a."SourceRecordID" '
                'WHERE a."CanonicalPersonID"=p."CanonicalPersonID" '
                'AND sr."Payload"->>\'record_origin\'=%s)) '
                'FROM "CanonicalPerson" p WHERE p."CanonicalPersonID"=ANY(%s) '
                'ORDER BY p."CanonicalPersonID"',
                (_PUBLIC_SOURCE_CURATED, _PUBLIC_SOURCE_CURATED,
                 _PUBLIC_SOURCE_CURATED, _PUBLIC_SOURCE_CURATED, all_person_ids),
            )
            person_rows = cur.fetchall()
            found = {int(row[0]) for row in person_rows}
            missing = next((pid for pid in all_person_ids if pid not in found), None)
            if missing is not None:
                raise IdentityNotFound(f"CanonicalPerson {missing} not found.")
            curated = next((int(row[0]) for row in person_rows if row[1]), None)
            if curated is not None:
                raise IdentityConflict(
                    f"Public-source curated CanonicalPerson {curated} is immutable."
                )

        all_case_ids = sorted(set(direct_case_ids) | linked_case_ids)
        if all_case_ids:
            cur.execute(
                'SELECT cm."CaseMasterID",(EXISTS ('
                'SELECT 1 FROM "CaseVersion" cv '
                'WHERE cv."CaseMasterID"=cm."CaseMasterID" '
                'AND cv."SnapshotAttributes"->>\'record_origin\'=%s) OR EXISTS ('
                'SELECT 1 FROM "CaseSource" cs JOIN "SourceRecord" sr '
                'ON sr."SourceRecordID"=cs."SourceRecordID" '
                'WHERE cs."CaseMasterID"=cm."CaseMasterID" '
                'AND sr."Payload"->>\'record_origin\'=%s) OR EXISTS ('
                'SELECT 1 FROM "CasePartyRole" r '
                'WHERE r."CaseMasterID"=cm."CaseMasterID" '
                'AND r."Provenance"->>\'record_origin\'=%s)) '
                'FROM "CaseMaster" cm WHERE cm."CaseMasterID"=ANY(%s) '
                'ORDER BY cm."CaseMasterID"',
                (_PUBLIC_SOURCE_CURATED, _PUBLIC_SOURCE_CURATED,
                 _PUBLIC_SOURCE_CURATED, all_case_ids),
            )
            case_rows = cur.fetchall()
            found = {int(row[0]) for row in case_rows}
            missing = next((cid for cid in all_case_ids if cid not in found), None)
            if missing is not None:
                raise IdentityNotFound(f"Case {missing} not found.")
            curated = next((int(row[0]) for row in case_rows if row[1]), None)
            if curated is not None:
                raise IdentityConflict(f"Public-source curated case {curated} is immutable.")


# ===========================================================================
# Person read
# ===========================================================================
def _person_row(conn, cpid: int) -> Optional[tuple]:
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "CanonicalPersonID","PublicRef","DisplayLabel","IsUnknown",'
            '"PrimaryGenderID","ApproxBirthYear","IsJuvenile","ResolutionStatus",'
            '"MergedIntoCanonicalPersonID","Attributes" '
            'FROM "CanonicalPerson" WHERE "CanonicalPersonID"=%s', (cpid,))
        return cur.fetchone()


def _summary_from_row(r: tuple, case_count=None, alias_count=None) -> S.PersonSummary:
    return S.PersonSummary(
        canonical_person_id=int(r[0]), public_ref=r[1], display_label=r[2],
        is_unknown=bool(r[3]), primary_gender_id=r[4], approx_birth_year=r[5],
        is_juvenile=bool(r[6]), resolution_status=r[7], merged_into=r[8],
        case_count=case_count, alias_count=alias_count)


def _case_count(conn, cpid: int) -> int:
    with conn.cursor() as cur:
        cur.execute('SELECT COUNT(*) FROM "CasePartyRole" WHERE "CanonicalPersonID"=%s', (cpid,))
        return int(cur.fetchone()[0])


def _detail(conn, cpid: int) -> S.PersonDetail:
    r = _person_row(conn, cpid)
    if r is None:
        raise IdentityNotFound(f"CanonicalPerson {cpid} not found.")
    with conn.cursor() as cur:
        cur.execute('SELECT "CanonicalEntityID" FROM "CanonicalEntity" '
                    'WHERE "CanonicalPersonID"=%s ORDER BY "CanonicalEntityID" LIMIT 1', (cpid,))
        ce = cur.fetchone()
        cur.execute('SELECT "PersonAliasID","AliasName","AliasType" FROM "PersonAlias" '
                    'WHERE "CanonicalPersonID"=%s ORDER BY "PersonAliasID"', (cpid,))
        aliases = [S.AliasOut(person_alias_id=int(x[0]), alias_name=x[1], alias_type=x[2])
                   for x in cur.fetchall()]
        cur.execute('SELECT "PersonIdentifierID","IdentifierType","IdentifierValue","Sensitivity" '
                    'FROM "PersonIdentifier" WHERE "CanonicalPersonID"=%s ORDER BY "PersonIdentifierID"', (cpid,))
        idents = [S.IdentifierOut(person_identifier_id=int(x[0]), identifier_type=x[1],
                                  identifier_value=x[2], sensitivity=x[3]) for x in cur.fetchall()]
        cur.execute('SELECT "PersonContactID","ContactType","ContactValue","Sensitivity" '
                    'FROM "PersonContact" WHERE "CanonicalPersonID"=%s ORDER BY "PersonContactID"', (cpid,))
        contacts = [S.ContactOut(person_contact_id=int(x[0]), contact_type=x[1],
                                 contact_value=x[2], sensitivity=x[3]) for x in cur.fetchall()]
        cur.execute('SELECT "PersonAddressID","DistrictID","AddressText",'
                    'ST_Y("geom")::float, ST_X("geom")::float,"Sensitivity" '
                    'FROM "PersonAddress" WHERE "CanonicalPersonID"=%s ORDER BY "PersonAddressID"', (cpid,))
        addresses = [S.AddressOut(person_address_id=int(x[0]), district_id=x[1], address_text=x[2],
                                  latitude=x[3], longitude=x[4], sensitivity=x[5]) for x in cur.fetchall()]
        cur.execute(
            'SELECT r."CasePartyRoleID", r."CaseMasterID", '
            'COALESCE(NULLIF(cv.attrs #>> \'{official_references,police_crime_no}\', \'\'), '
            'cm."CrimeNo"), r."RoleType", r."IsUnknownParty", r."PartyLabel", r."SequenceNo" '
            'FROM "CasePartyRole" r LEFT JOIN "CaseMaster" cm ON cm."CaseMasterID"=r."CaseMasterID" '
            'LEFT JOIN LATERAL (SELECT cv0."SnapshotAttributes" AS attrs FROM "CaseVersion" cv0 '
            'WHERE cv0."CaseMasterID"=r."CaseMasterID" AND cv0."IsCurrent"=TRUE '
            'ORDER BY cv0."VersionNo" DESC LIMIT 1) cv ON TRUE '
            'WHERE r."CanonicalPersonID"=%s ORDER BY r."CasePartyRoleID" LIMIT 200', (cpid,))
        roles = [S.CaseRoleOut(case_party_role_id=int(x[0]), case_master_id=int(x[1]), crime_no=x[2],
                               role_type=x[3], is_unknown=bool(x[4]), party_label=x[5], sequence_no=x[6])
                 for x in cur.fetchall()]
        cur.execute(
            'SELECT "EntityMergeHistoryID","Action","WinnerCanonicalPersonID",'
            '"LoserCanonicalPersonID","Reason","Actor","CreatedAt"::text '
            'FROM "EntityMergeHistory" WHERE "WinnerCanonicalPersonID"=%s OR "LoserCanonicalPersonID"=%s '
            'ORDER BY "EntityMergeHistoryID" DESC LIMIT 50', (cpid, cpid))
        history = [S.MergeHistoryOut(entity_merge_history_id=int(x[0]), action=x[1],
                                     winner_canonical_person_id=x[2], loser_canonical_person_id=x[3],
                                     reason=x[4], actor=x[5], created_at=x[6]) for x in cur.fetchall()]
    base = _summary_from_row(r, case_count=len(roles), alias_count=len(aliases))
    return S.PersonDetail(**base.model_dump(), attributes=r[9] or {},
                          canonical_entity_id=int(ce[0]) if ce else None,
                          aliases=aliases, identifiers=idents, contacts=contacts,
                          addresses=addresses, case_roles=roles, merge_history=history)


def _search_persons(conn, q, gender_id, juvenile, status, page, page_size) -> S.PersonSearchResponse:
    clauses, params = [], []
    if q:
        # Pre-resolve alias matches through the PersonAlias trigram index (fast),
        # then filter persons by the trigram-indexed DisplayLabel / exact PublicRef
        # / alias-id set. Avoids a correlated per-row subquery over 200k+ persons.
        with conn.cursor() as cur:
            cur.execute('SELECT DISTINCT "CanonicalPersonID" FROM "PersonAlias" '
                        'WHERE "AliasName" ILIKE %s LIMIT 500', (f"%{q}%",))
            alias_ids = [int(r[0]) for r in cur.fetchall()]
        clauses.append('(p."DisplayLabel" ILIKE %s OR p."PublicRef" = %s OR p."CanonicalPersonID" = ANY(%s))')
        params += [f"%{q}%", q, alias_ids]
    if gender_id is not None:
        clauses.append('"PrimaryGenderID"=%s'); params.append(gender_id)
    if juvenile is not None:
        clauses.append('"IsJuvenile"=%s'); params.append(juvenile)
    if status:
        clauses.append('"ResolutionStatus"=%s'); params.append(status)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    offset = (page - 1) * page_size
    with conn.cursor() as cur:
        cur.execute(f'SELECT COUNT(*) FROM "CanonicalPerson" p{where}', params)
        total = int(cur.fetchone()[0])
        cur.execute(
            f'SELECT p."CanonicalPersonID",p."PublicRef",p."DisplayLabel",p."IsUnknown",'
            f'p."PrimaryGenderID",p."ApproxBirthYear",p."IsJuvenile",p."ResolutionStatus",'
            f'p."MergedIntoCanonicalPersonID",'
            f'(SELECT COUNT(*) FROM "CasePartyRole" r WHERE r."CanonicalPersonID"=p."CanonicalPersonID"),'
            f'(SELECT COUNT(*) FROM "PersonAlias" al WHERE al."CanonicalPersonID"=p."CanonicalPersonID") '
            f'FROM "CanonicalPerson" p{where} '
            f'ORDER BY p."CanonicalPersonID" DESC LIMIT %s OFFSET %s', params + [page_size, offset])
        items = [_summary_from_row(x[:9], case_count=int(x[9]), alias_count=int(x[10]))
                 for x in cur.fetchall()]
    return S.PersonSearchResponse(items=items, total=total, page=page, page_size=page_size)


# ===========================================================================
# Person write
# ===========================================================================
def _create_person(conn, req: S.CreatePersonRequest) -> int:
    _reject_reserved_identity_attributes(req.attributes)
    if req.idempotency_key:
        with conn.cursor() as cur:
            cur.execute('SELECT "CanonicalPersonID" FROM "CanonicalPerson" '
                        'WHERE "Attributes"->>\'idempotency_key\'=%s LIMIT 1', (req.idempotency_key,))
            r = cur.fetchone()
        if r:
            return int(r[0])
    attrs = dict(req.attributes or {})
    if req.idempotency_key:
        attrs["idempotency_key"] = req.idempotency_key
    attrs.setdefault("created_via", "identity_api")
    ref = "SYN-PERSON-" + uuid.uuid4().hex[:12].upper()
    label = None if req.is_unknown else (req.display_label or None)
    with conn.cursor() as cur:
        cur.execute(
            'INSERT INTO "CanonicalPerson" ("PublicRef","DisplayLabel","IsUnknown",'
            '"PrimaryGenderID","ApproxBirthYear","IsJuvenile","ResolutionStatus","Attributes","IsSynthetic") '
            'VALUES (%s,%s,%s,%s,%s,%s,\'canonical\',%s,TRUE) RETURNING "CanonicalPersonID"',
            (ref, label, req.is_unknown, req.primary_gender_id, req.approx_birth_year,
             req.is_juvenile, Json(attrs)))
        cpid = int(cur.fetchone()[0])
        # every person is also a canonical entity node (person kind)
        eref = "SYN-ENT-" + uuid.uuid4().hex[:12].upper()
        cur.execute(
            'INSERT INTO "CanonicalEntity" ("EntityKind","CanonicalPersonID","PublicRef","Label","IsSynthetic") '
            'VALUES (\'person\',%s,%s,%s,TRUE)', (cpid, eref, label))
    audit.record(audit.Action.ENTITY_CHANGE, "canonical_person", cpid, actor=req.actor, conn=conn,
                 detail={"op": "create", "public_ref": ref, "is_unknown": req.is_unknown})
    return cpid


def _update_person(conn, cpid: int, req: S.UpdatePersonRequest) -> None:
    r = _person_row(conn, cpid)
    if r is None:
        raise IdentityNotFound(f"CanonicalPerson {cpid} not found.")
    _require_mutable_identity_targets(conn, person_ids=(cpid,))
    r = _person_row(conn, cpid)
    if r is None:  # defensive: the guard holds this row lock until transaction end
        raise IdentityNotFound(f"CanonicalPerson {cpid} not found.")
    _reject_reserved_identity_attributes(req.attributes)
    sets, params = [], []
    if req.display_label is not None:
        sets.append('"DisplayLabel"=%s'); params.append(req.display_label)
    if req.primary_gender_id is not None:
        sets.append('"PrimaryGenderID"=%s'); params.append(req.primary_gender_id)
    if req.approx_birth_year is not None:
        sets.append('"ApproxBirthYear"=%s'); params.append(req.approx_birth_year)
    if req.is_juvenile is not None:
        sets.append('"IsJuvenile"=%s'); params.append(req.is_juvenile)
    if req.attributes is not None:
        merged = dict(r[9] or {}); merged.update(req.attributes)
        sets.append('"Attributes"=%s'); params.append(Json(merged))
    if not sets:
        return
    params.append(cpid)
    with conn.cursor() as cur:
        cur.execute(f'UPDATE "CanonicalPerson" SET {", ".join(sets)} WHERE "CanonicalPersonID"=%s', params)
    audit.record(audit.Action.ENTITY_CHANGE, "canonical_person", cpid, actor=req.actor, conn=conn,
                 detail={"op": "update", "fields": [s.split('"')[1] for s in sets]})


# ===========================================================================
# Organisations
# ===========================================================================
def _create_org(conn, req: S.CreateOrgRequest) -> int:
    if req.idempotency_key:
        with conn.cursor() as cur:
            cur.execute('SELECT "CanonicalOrganisationID" FROM "CanonicalOrganisation" '
                        'WHERE "Attributes"->>\'idempotency_key\'=%s LIMIT 1', (req.idempotency_key,))
            r = cur.fetchone()
        if r:
            return int(r[0])
    attrs = dict(req.attributes or {})
    if req.idempotency_key:
        attrs["idempotency_key"] = req.idempotency_key
    ref = "SYN-ORG-" + uuid.uuid4().hex[:12].upper()
    with conn.cursor() as cur:
        cur.execute(
            'INSERT INTO "CanonicalOrganisation" ("PublicRef","Name","OrgType","Attributes","IsSynthetic") '
            'VALUES (%s,%s,%s,%s,TRUE) RETURNING "CanonicalOrganisationID"',
            (ref, req.name, req.org_type, Json(attrs)))
        oid = int(cur.fetchone()[0])
        eref = "SYN-ENT-" + uuid.uuid4().hex[:12].upper()
        cur.execute(
            'INSERT INTO "CanonicalEntity" ("EntityKind","CanonicalOrganisationID","PublicRef","Label","IsSynthetic") '
            'VALUES (\'organisation\',%s,%s,%s,TRUE)', (oid, eref, req.name))
    audit.record(audit.Action.ENTITY_CHANGE, "canonical_organisation", oid, actor=req.actor, conn=conn,
                 detail={"op": "create", "public_ref": ref})
    return oid


def _search_orgs(conn, q, page, page_size) -> S.OrgSearchResponse:
    clauses, params = [], []
    if q:
        clauses.append('("Name" ILIKE %s OR "PublicRef" ILIKE %s)')
        params += [f"%{q}%", f"%{q}%"]
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    offset = (page - 1) * page_size
    with conn.cursor() as cur:
        cur.execute(f'SELECT COUNT(*) FROM "CanonicalOrganisation"{where}', params)
        total = int(cur.fetchone()[0])
        cur.execute(f'SELECT "CanonicalOrganisationID","PublicRef","Name","OrgType" '
                    f'FROM "CanonicalOrganisation"{where} ORDER BY "CanonicalOrganisationID" DESC '
                    f'LIMIT %s OFFSET %s', params + [page_size, offset])
        items = [S.OrgSummary(canonical_organisation_id=int(x[0]), public_ref=x[1], name=x[2], org_type=x[3])
                 for x in cur.fetchall()]
    return S.OrgSearchResponse(items=items, total=total, page=page, page_size=page_size)


# ===========================================================================
# Attributes (alias/identifier/contact/address) with sensitivity
# ===========================================================================
def _require_person(conn, cpid: int) -> None:
    if _person_row(conn, cpid) is None:
        raise IdentityNotFound(f"CanonicalPerson {cpid} not found.")


def _add_alias(conn, cpid: int, a: S.AliasInput) -> int:
    _require_person(conn, cpid)
    _require_mutable_identity_targets(conn, person_ids=(cpid,))
    with conn.cursor() as cur:
        cur.execute('SELECT "PersonAliasID" FROM "PersonAlias" '
                    'WHERE "CanonicalPersonID"=%s AND lower("AliasName")=lower(%s) AND "AliasType"=%s',
                    (cpid, a.alias_name, a.alias_type))
        dup = cur.fetchone()
        if dup:
            return int(dup[0])
        cur.execute('INSERT INTO "PersonAlias" ("CanonicalPersonID","AliasName","AliasType","IsSynthetic") '
                    'VALUES (%s,%s,%s,TRUE) RETURNING "PersonAliasID"', (cpid, a.alias_name, a.alias_type))
        aid = int(cur.fetchone()[0])
    audit.record(audit.Action.ENTITY_CHANGE, "person_alias", aid, actor=a.actor, conn=conn,
                 detail={"op": "add_alias", "canonical_person_id": cpid, "alias_type": a.alias_type})
    return aid


def _add_identifier(conn, cpid: int, i: S.IdentifierInput) -> int:
    _require_person(conn, cpid)
    _require_mutable_identity_targets(conn, person_ids=(cpid,))
    if i.sensitivity not in S.SENSITIVITIES:
        raise IdentityValidationError(f"Invalid sensitivity '{i.sensitivity}'.")
    with conn.cursor() as cur:
        cur.execute('INSERT INTO "PersonIdentifier" ("CanonicalPersonID","IdentifierType",'
                    '"IdentifierValue","Sensitivity","IsSynthetic") VALUES (%s,%s,%s,%s,TRUE) '
                    'RETURNING "PersonIdentifierID"',
                    (cpid, i.identifier_type, i.identifier_value, i.sensitivity))
        rid = int(cur.fetchone()[0])
    audit.record(audit.Action.ENTITY_CHANGE, "person_identifier", rid, actor=i.actor, conn=conn,
                 detail={"op": "add_identifier", "canonical_person_id": cpid,
                         "identifier_type": i.identifier_type, "sensitivity": i.sensitivity})
    return rid


def _add_contact(conn, cpid: int, c: S.ContactInput) -> int:
    _require_person(conn, cpid)
    _require_mutable_identity_targets(conn, person_ids=(cpid,))
    if c.sensitivity not in S.SENSITIVITIES:
        raise IdentityValidationError(f"Invalid sensitivity '{c.sensitivity}'.")
    with conn.cursor() as cur:
        cur.execute('INSERT INTO "PersonContact" ("CanonicalPersonID","ContactType","ContactValue",'
                    '"Sensitivity","IsSynthetic") VALUES (%s,%s,%s,%s,TRUE) RETURNING "PersonContactID"',
                    (cpid, c.contact_type, c.contact_value, c.sensitivity))
        rid = int(cur.fetchone()[0])
    audit.record(audit.Action.ENTITY_CHANGE, "person_contact", rid, actor=c.actor, conn=conn,
                 detail={"op": "add_contact", "canonical_person_id": cpid, "contact_type": c.contact_type})
    return rid


def _add_address(conn, cpid: int, ad: S.AddressInput) -> int:
    _require_person(conn, cpid)
    _require_mutable_identity_targets(conn, person_ids=(cpid,))
    geom = None
    if ad.latitude is not None and ad.longitude is not None:
        geom = f"SRID=4326;POINT({ad.longitude} {ad.latitude})"
    with conn.cursor() as cur:
        cur.execute('INSERT INTO "PersonAddress" ("CanonicalPersonID","DistrictID","AddressText",'
                    '"geom","Sensitivity","IsSynthetic") VALUES (%s,%s,%s,%s,%s,TRUE) '
                    'RETURNING "PersonAddressID"',
                    (cpid, ad.district_id, ad.address_text, geom, ad.sensitivity))
        rid = int(cur.fetchone()[0])
    audit.record(audit.Action.ENTITY_CHANGE, "person_address", rid, actor=ad.actor, conn=conn,
                 detail={"op": "add_address", "canonical_person_id": cpid})
    return rid


def _delete_attr(conn, table: str, pk_col: str, cpid: int, row_id: int, actor) -> None:
    if _PERSON_ATTRIBUTE_TARGETS.get(table) != pk_col:
        raise IdentityValidationError("Unsupported person attribute target.")
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT "{pk_col}" FROM "{table}" '
            f'WHERE "CanonicalPersonID"=%s AND "{pk_col}"=%s',
            (cpid, row_id),
        )
        if cur.fetchone() is None:
            raise IdentityNotFound(f"{table} {row_id} not found for person {cpid}.")
    _require_mutable_identity_targets(conn, person_ids=(cpid,))
    with conn.cursor() as cur:
        cur.execute(f'DELETE FROM "{table}" WHERE "{pk_col}"=%s AND "CanonicalPersonID"=%s',
                    (row_id, cpid))
        if cur.rowcount == 0:
            raise IdentityNotFound(f"{table} {row_id} not found for person {cpid}.")
    audit.record(audit.Action.ENTITY_CHANGE, table.lower(), row_id, actor=actor, conn=conn,
                 detail={"op": "delete", "canonical_person_id": cpid})


# ===========================================================================
# Case-party roles
# ===========================================================================
def _add_party(conn, case_id: int, req: S.AddPartyRequest) -> S.PartyMutationResponse:
    if req.role_type not in S.PARTY_ROLES:
        raise IdentityValidationError(f"Unknown role_type '{req.role_type}'.")
    if not (req.canonical_person_id or req.canonical_organisation_id or req.is_unknown):
        raise IdentityValidationError("A party must link a canonical person/organisation or be unknown.")
    with conn.cursor() as cur:
        cur.execute('SELECT 1 FROM "CaseMaster" WHERE "CaseMasterID"=%s', (case_id,))
        if cur.fetchone() is None:
            raise IdentityNotFound(f"Case {case_id} not found.")
        if req.canonical_person_id:
            _require_person(conn, req.canonical_person_id)
        _require_mutable_identity_targets(
            conn,
            person_ids=((req.canonical_person_id,) if req.canonical_person_id else ()),
            case_ids=(case_id,),
        )
        cur.execute(
            'INSERT INTO "CasePartyRole" ("CaseMasterID","CanonicalPersonID","CanonicalOrganisationID",'
            '"RoleType","IsUnknownParty","PartyLabel","SequenceNo","Provenance") '
            'VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING "CasePartyRoleID"',
            (case_id, req.canonical_person_id, req.canonical_organisation_id, req.role_type,
             req.is_unknown, req.party_label, req.sequence_no,
             Json({"source": "identity_api"})))
        rid = int(cur.fetchone()[0])
    audit.record(audit.Action.ENTITY_CHANGE, "case_party_role", rid, actor=req.actor, conn=conn,
                 detail={"op": "add_party", "case_master_id": case_id, "role_type": req.role_type})
    return S.PartyMutationResponse(
        case_party_role_id=rid, case_master_id=case_id,
        canonical_person_id=req.canonical_person_id,
        canonical_organisation_id=req.canonical_organisation_id,
        role_type=req.role_type, is_unknown=req.is_unknown)


def _update_party(conn, role_id: int, req: S.UpdatePartyRequest) -> S.PartyMutationResponse:
    with conn.cursor() as cur:
        cur.execute('SELECT "CaseMasterID","CanonicalPersonID","CanonicalOrganisationID","RoleType","IsUnknownParty" '
                    'FROM "CasePartyRole" WHERE "CasePartyRoleID"=%s', (role_id,))
        row = cur.fetchone()
        if row is None:
            raise IdentityNotFound(f"CasePartyRole {role_id} not found.")
        _require_mutable_identity_targets(conn, role_ids=(role_id,))
        sets, params = [], []
        if req.role_type is not None:
            if req.role_type not in S.PARTY_ROLES:
                raise IdentityValidationError(f"Unknown role_type '{req.role_type}'.")
            sets.append('"RoleType"=%s'); params.append(req.role_type)
        if req.sequence_no is not None:
            sets.append('"SequenceNo"=%s'); params.append(req.sequence_no)
        if sets:
            params.append(role_id)
            cur.execute(f'UPDATE "CasePartyRole" SET {", ".join(sets)} WHERE "CasePartyRoleID"=%s', params)
        cur.execute('SELECT "CaseMasterID","CanonicalPersonID","CanonicalOrganisationID","RoleType","IsUnknownParty" '
                    'FROM "CasePartyRole" WHERE "CasePartyRoleID"=%s', (role_id,))
        row = cur.fetchone()
    audit.record(audit.Action.ENTITY_CHANGE, "case_party_role", role_id, actor=req.actor, conn=conn,
                 detail={"op": "update_party"})
    return S.PartyMutationResponse(case_party_role_id=role_id, case_master_id=int(row[0]),
                                   canonical_person_id=row[1], canonical_organisation_id=row[2],
                                   role_type=row[3], is_unknown=bool(row[4]))


def _remove_party(conn, role_id: int, actor) -> int:
    with conn.cursor() as cur:
        cur.execute('SELECT "CaseMasterID" FROM "CasePartyRole" WHERE "CasePartyRoleID"=%s', (role_id,))
        row = cur.fetchone()
        if row is None:
            raise IdentityNotFound(f"CasePartyRole {role_id} not found.")
        _require_mutable_identity_targets(conn, role_ids=(role_id,))
        case_id = int(row[0])
        # keep legacy child rows consistent (unlink the CasePartyRole ref)
        cur.execute('UPDATE "Accused" SET "CasePartyRoleID"=NULL WHERE "CasePartyRoleID"=%s', (role_id,))
        cur.execute('DELETE FROM "CasePartyRole" WHERE "CasePartyRoleID"=%s', (role_id,))
    audit.record(audit.Action.ENTITY_CHANGE, "case_party_role", role_id, actor=actor, conn=conn,
                 detail={"op": "remove_party", "case_master_id": case_id})
    return case_id


# ===========================================================================
# Entity resolution — candidate generation (NO auto-merge)
# ===========================================================================
def _candidate_ref(conn, cpid: int) -> S.CandidatePersonRef:
    r = _person_row(conn, cpid)
    return S.CandidatePersonRef(
        canonical_person_id=cpid, public_ref=r[1] if r else str(cpid),
        display_label=r[2] if r else None, case_count=_case_count(conn, cpid),
        alias_count=None)


def _candidate_out(conn, row: tuple) -> S.CandidateOut:
    return S.CandidateOut(
        entity_resolution_candidate_id=int(row[0]),
        person_a=_candidate_ref(conn, int(row[1])),
        person_b=_candidate_ref(conn, int(row[2])),
        method=row[3], score=float(row[4]) if row[4] is not None else None,
        match_features=row[5] or {}, status=row[6],
        reviewed_by_actor=row[7], reviewed_at=_s(row[8]), created_at=_s(row[9]))


def _list_candidates(conn, status, page, page_size) -> S.CandidateListResponse:
    clauses, params = [], []
    if status:
        clauses.append('"Status"=%s'); params.append(status)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    offset = (page - 1) * page_size
    with conn.cursor() as cur:
        cur.execute(f'SELECT COUNT(*) FROM "EntityResolutionCandidate"{where}', params)
        total = int(cur.fetchone()[0])
        cur.execute(
            f'SELECT "EntityResolutionCandidateID","CanonicalPersonA","CanonicalPersonB","Method",'
            f'"Score","MatchFeatures","Status","ReviewedByActor","ReviewedAt","CreatedAt" '
            f'FROM "EntityResolutionCandidate"{where} ORDER BY "Status"=\'pending\' DESC, '
            f'"Score" DESC NULLS LAST, "EntityResolutionCandidateID" DESC LIMIT %s OFFSET %s',
            params + [page_size, offset])
        rows = cur.fetchall()
    return S.CandidateListResponse(items=[_candidate_out(conn, r) for r in rows],
                                   total=total, page=page, page_size=page_size)


def _candidate_pairs_for_person(conn, cpid: int, limit: int) -> list[tuple]:
    """Similar-label candidates for ONE person (targeted; uses the DisplayLabel
    trigram index). Returns (lo, hi, method, score, label_a, label_b)."""
    with conn.cursor() as cur:
        cur.execute('SELECT "DisplayLabel","ResolutionStatus" FROM "CanonicalPerson" '
                    'WHERE "CanonicalPersonID"=%s', (cpid,))
        r = cur.fetchone()
        if r is None:
            raise IdentityNotFound(f"CanonicalPerson {cpid} not found.")
        label = r[0]
        if not label:
            return []
        out: list[tuple] = []
        try:
            cur.execute(
                'SELECT b."CanonicalPersonID", b."DisplayLabel", '
                " CASE WHEN lower(b.\"DisplayLabel\")=lower(%s) THEN 'deterministic' ELSE 'fuzzy' END, "
                ' CASE WHEN lower(b."DisplayLabel")=lower(%s) THEN 0.95 '
                '      ELSE round(similarity(b."DisplayLabel", %s)::numeric, 5) END '
                'FROM "CanonicalPerson" b '
                'WHERE b."CanonicalPersonID" <> %s AND b."ResolutionStatus"=\'canonical\' '
                '  AND b."IsUnknown"=FALSE AND b."DisplayLabel" %% %s '
                'ORDER BY (lower(b."DisplayLabel")=lower(%s)) DESC, 4 DESC LIMIT %s',
                (label, label, label, cpid, label, label, limit))
            rows = cur.fetchall()
        except Exception:  # noqa: BLE001 — trigram unavailable -> exact-label only
            conn.rollback()
            with conn.cursor() as cur2:
                cur2.execute('SELECT b."CanonicalPersonID", b."DisplayLabel", \'deterministic\', 0.60 '
                             'FROM "CanonicalPerson" b WHERE b."DisplayLabel"=%s '
                             'AND b."CanonicalPersonID" <> %s AND b."ResolutionStatus"=\'canonical\' '
                             'AND b."IsUnknown"=FALSE LIMIT %s', (label, cpid, limit))
                rows = cur2.fetchall()
        for cpid_b, lb, method, score in rows:
            b = int(cpid_b)
            lo, hi = (cpid, b) if cpid < b else (b, cpid)
            out.append((lo, hi, method, score, label, lb))
    return out


def _candidate_pairs_duplicate_labels(conn, limit: int) -> list[tuple]:
    """Untargeted: exact duplicate-label pairs only (bounded set of duplicated
    labels), avoiding a trigram cross-join over the whole population."""
    with conn.cursor() as cur:
        cur.execute(
            'WITH dup AS (SELECT "DisplayLabel" FROM "CanonicalPerson" '
            '  WHERE "DisplayLabel" IS NOT NULL AND "ResolutionStatus"=\'canonical\' AND "IsUnknown"=FALSE '
            '  GROUP BY "DisplayLabel" HAVING COUNT(*) > 1 LIMIT 50) '
            'SELECT LEAST(a."CanonicalPersonID", b."CanonicalPersonID"), '
            '       GREATEST(a."CanonicalPersonID", b."CanonicalPersonID"), '
            "       'deterministic', 0.60, a.\"DisplayLabel\", b.\"DisplayLabel\" "
            'FROM "CanonicalPerson" a JOIN dup ON dup."DisplayLabel"=a."DisplayLabel" '
            'JOIN "CanonicalPerson" b ON b."DisplayLabel"=a."DisplayLabel" '
            '   AND b."CanonicalPersonID" > a."CanonicalPersonID" '
            '   AND b."ResolutionStatus"=\'canonical\' AND b."IsUnknown"=FALSE '
            'WHERE a."ResolutionStatus"=\'canonical\' AND a."IsUnknown"=FALSE LIMIT %s', (limit,))
        return [(int(x[0]), int(x[1]), x[2], x[3], x[4], x[5]) for x in cur.fetchall()]


def _generate_candidates(conn, req: S.GenerateCandidatesRequest) -> S.GenerateCandidatesResponse:
    """Propose person-match candidates from deterministic (exact display label)
    and fuzzy (trigram similarity) features. NEVER merges automatically."""
    if req.canonical_person_id:
        pairs = _candidate_pairs_for_person(conn, req.canonical_person_id, req.limit)
    else:
        pairs = _candidate_pairs_duplicate_labels(conn, req.limit)

    created_ids: list[int] = []
    for lo, hi, method, score, la, lb in pairs:
        if score is not None and float(score) < req.min_score:
            continue
        with conn.cursor() as cur:
            cur.execute('SELECT 1 FROM "EntityResolutionCandidate" '
                        'WHERE "CanonicalPersonA"=%s AND "CanonicalPersonB"=%s', (lo, hi))
            if cur.fetchone():
                continue
            features = {"label_a": la, "label_b": lb,
                        "feature": "display_label_similarity", "method": method,
                        "note": "Proposal for human review only; NOT auto-merged."}
            cur.execute(
                'INSERT INTO "EntityResolutionCandidate" ("CanonicalPersonA","CanonicalPersonB",'
                '"Method","Score","MatchFeatures","Status") VALUES (%s,%s,%s,%s,%s,\'pending\') '
                'RETURNING "EntityResolutionCandidateID"',
                (lo, hi, method, round(float(score), 5) if score is not None else None, Json(features)))
            created_ids.append(int(cur.fetchone()[0]))
    if created_ids:
        audit.record(audit.Action.ENTITY_CHANGE, "entity_resolution_candidate", None, actor=req.actor,
                     conn=conn, detail={"op": "generate_candidates", "created": len(created_ids)})
        with conn.cursor() as cur:
            cur.execute('SELECT "EntityResolutionCandidateID","CanonicalPersonA","CanonicalPersonB","Method",'
                        '"Score","MatchFeatures","Status","ReviewedByActor","ReviewedAt","CreatedAt" '
                        'FROM "EntityResolutionCandidate" WHERE "EntityResolutionCandidateID"=ANY(%s) '
                        'ORDER BY "EntityResolutionCandidateID"', (created_ids,))
            rows = cur.fetchall()
    else:
        rows = []
    return S.GenerateCandidatesResponse(created=len(created_ids),
                                        candidates=[_candidate_out(conn, r) for r in rows])


# ===========================================================================
# Merge / unmerge (reversible) + candidate review
# ===========================================================================
def _repoint_person_refs(conn, loser: int, winner: int) -> dict[str, list[int]]:
    """Move every loser->winner reference, returning {table: [pk ids moved]} so
    the merge is exactly reversible. Missing tables/cols are skipped."""
    moved: dict[str, list[int]] = {}
    for table, fk_col, pk_col in _PERSON_FK_TABLES:
        with conn.cursor() as cur:
            try:
                cur.execute("SAVEPOINT sp_repoint")
                cur.execute(f'SELECT "{pk_col}" FROM "{table}" WHERE "{fk_col}"=%s', (loser,))
                ids = [int(x[0]) for x in cur.fetchall()]
                if ids:
                    cur.execute(f'UPDATE "{table}" SET "{fk_col}"=%s WHERE "{pk_col}"=ANY(%s)',
                                (winner, ids))
                    moved[table] = ids
                cur.execute("RELEASE SAVEPOINT sp_repoint")
            except Exception:  # noqa: BLE001
                cur.execute("ROLLBACK TO SAVEPOINT sp_repoint")
    return moved


def _restore_person_refs(conn, moved: dict[str, list[int]], loser: int) -> None:
    pk_by_table = {t: pk for t, _fk, pk in _PERSON_FK_TABLES}
    fk_by_table = {t: fk for t, fk, _pk in _PERSON_FK_TABLES}
    for table, ids in (moved or {}).items():
        if not ids or table not in pk_by_table:
            continue
        with conn.cursor() as cur:
            try:
                cur.execute("SAVEPOINT sp_restore")
                cur.execute(f'UPDATE "{table}" SET "{fk_by_table[table]}"=%s WHERE "{pk_by_table[table]}"=ANY(%s)',
                            (loser, [int(i) for i in ids]))
                cur.execute("RELEASE SAVEPOINT sp_restore")
            except Exception:  # noqa: BLE001
                cur.execute("ROLLBACK TO SAVEPOINT sp_restore")


def _merge(conn, winner: int, loser: int, reason, actor) -> S.MergeResult:
    if winner == loser:
        raise IdentityValidationError("Cannot merge a person into itself.")
    wr, lr = _person_row(conn, winner), _person_row(conn, loser)
    if wr is None:
        raise IdentityNotFound(f"Winner CanonicalPerson {winner} not found.")
    if lr is None:
        raise IdentityNotFound(f"Loser CanonicalPerson {loser} not found.")
    _require_mutable_identity_targets(conn, person_ids=(winner, loser))
    # Re-read merge state after acquiring the target locks in the guard.
    wr, lr = _person_row(conn, winner), _person_row(conn, loser)
    if wr is None:
        raise IdentityNotFound(f"Winner CanonicalPerson {winner} not found.")
    if lr is None:
        raise IdentityNotFound(f"Loser CanonicalPerson {loser} not found.")
    if wr[7] == 'merged':
        raise IdentityConflict(f"Winner {winner} is itself merged; choose a canonical winner.")
    if lr[7] == 'merged':
        raise IdentityConflict(f"Loser {loser} is already merged.")

    moved = _repoint_person_refs(conn, loser, winner)
    added_alias_id = None
    if lr[2]:  # keep the loser's label as an alias on the winner
        with conn.cursor() as cur:
            cur.execute('INSERT INTO "PersonAlias" ("CanonicalPersonID","AliasName","AliasType","IsSynthetic") '
                        'VALUES (%s,%s,\'merged_alias\',TRUE) RETURNING "PersonAliasID"', (winner, lr[2]))
            added_alias_id = int(cur.fetchone()[0])
            moved.setdefault("PersonAlias", []).append(added_alias_id)
    with conn.cursor() as cur:
        cur.execute('UPDATE "CanonicalPerson" SET "ResolutionStatus"=\'merged\', '
                    '"MergedIntoCanonicalPersonID"=%s WHERE "CanonicalPersonID"=%s', (winner, loser))
        before = {"moved": {k: v for k, v in moved.items()}, "added_alias_id": added_alias_id}
        cur.execute(
            'INSERT INTO "EntityMergeHistory" ("Action","WinnerCanonicalPersonID","LoserCanonicalPersonID",'
            '"Reason","Actor","BeforeState","AfterState") VALUES (\'merge\',%s,%s,%s,%s,%s,%s) '
            'RETURNING "EntityMergeHistoryID"',
            (winner, loser, reason, actor, Json(before),
             Json({"winner": winner, "loser": loser, "moved_counts": {k: len(v) for k, v in moved.items()}})))
        emh_id = int(cur.fetchone()[0])
    audit.record(audit.Action.ENTITY_CHANGE, "canonical_person", winner, actor=actor, conn=conn,
                 detail={"op": "merge", "loser": loser, "moved_counts": {k: len(v) for k, v in moved.items()}})
    return S.MergeResult(action="merge", winner_canonical_person_id=winner,
                         loser_canonical_person_id=loser,
                         moved_references={k: len(v) for k, v in moved.items()},
                         entity_merge_history_id=emh_id, reversible=True)


def _unmerge(conn, winner: int, loser: int, reason, actor) -> S.MergeResult:
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "EntityMergeHistoryID","BeforeState" FROM "EntityMergeHistory" '
            'WHERE "Action"=\'merge\' AND "WinnerCanonicalPersonID"=%s AND "LoserCanonicalPersonID"=%s '
            'ORDER BY "EntityMergeHistoryID" DESC LIMIT 1', (winner, loser))
        row = cur.fetchone()
    if row is None:
        raise IdentityNotFound(f"No merge of {loser} into {winner} to reverse.")
    wr, lr = _person_row(conn, winner), _person_row(conn, loser)
    if wr is None:
        raise IdentityNotFound(f"Winner CanonicalPerson {winner} not found.")
    if lr is None:
        raise IdentityNotFound(f"Loser CanonicalPerson {loser} not found.")
    _require_mutable_identity_targets(conn, person_ids=(winner, loser))
    lr = _person_row(conn, loser)
    if lr is None:  # defensive: the guard holds this row lock until transaction end
        raise IdentityNotFound(f"Loser CanonicalPerson {loser} not found.")
    if lr[7] != 'merged' or lr[8] != winner:
        raise IdentityConflict(f"Person {loser} is not currently merged into {winner}.")
    before = row[1] or {}
    moved = before.get("moved", {})
    added_alias_id = before.get("added_alias_id")
    # remove the alias added during the merge first, then restore other refs
    if added_alias_id and "PersonAlias" in moved:
        moved = {**moved, "PersonAlias": [i for i in moved["PersonAlias"] if i != added_alias_id]}
        with conn.cursor() as cur:
            cur.execute('DELETE FROM "PersonAlias" WHERE "PersonAliasID"=%s', (added_alias_id,))
    _restore_person_refs(conn, moved, loser)
    with conn.cursor() as cur:
        cur.execute('UPDATE "CanonicalPerson" SET "ResolutionStatus"=\'canonical\', '
                    '"MergedIntoCanonicalPersonID"=NULL WHERE "CanonicalPersonID"=%s', (loser,))
        cur.execute(
            'INSERT INTO "EntityMergeHistory" ("Action","WinnerCanonicalPersonID","LoserCanonicalPersonID",'
            '"Reason","Actor","BeforeState","AfterState") VALUES (\'split\',%s,%s,%s,%s,%s,%s) '
            'RETURNING "EntityMergeHistoryID"',
            (winner, loser, reason, actor, Json(before), Json({"restored": loser})))
        emh_id = int(cur.fetchone()[0])
    audit.record(audit.Action.ENTITY_CHANGE, "canonical_person", loser, actor=actor, conn=conn,
                 detail={"op": "unmerge", "winner": winner})
    return S.MergeResult(action="split", winner_canonical_person_id=winner,
                         loser_canonical_person_id=loser,
                         moved_references={k: len(v) for k, v in moved.items()},
                         entity_merge_history_id=emh_id, reversible=True)


def _review_candidate(conn, cand_id: int, req: S.ReviewCandidateRequest):
    with conn.cursor() as cur:
        cur.execute('SELECT "CanonicalPersonA","CanonicalPersonB","Status" '
                    'FROM "EntityResolutionCandidate" WHERE "EntityResolutionCandidateID"=%s', (cand_id,))
        row = cur.fetchone()
    if row is None:
        raise IdentityNotFound(f"EntityResolutionCandidate {cand_id} not found.")
    a, b, status = int(row[0]), int(row[1]), row[2]
    if status != 'pending':
        raise IdentityConflict(f"Candidate {cand_id} is already '{status}'.")

    merge_result = None
    if req.action == "accept":
        winner = req.winner_canonical_person_id or min(a, b)
        loser = b if winner == a else a
        if winner not in (a, b):
            raise IdentityValidationError("winner_canonical_person_id must be one of the candidate pair.")
        merge_result = _merge(conn, winner, loser, req.reason or "resolution: accepted match", req.actor)
        new_status = "accepted"
    elif req.action == "reject":
        new_status = "rejected"
    else:  # create_new -> the two are confirmed distinct persons
        new_status = "new"
    with conn.cursor() as cur:
        cur.execute('UPDATE "EntityResolutionCandidate" SET "Status"=%s, "ReviewedByActor"=%s, '
                    '"ReviewedAt"=now() WHERE "EntityResolutionCandidateID"=%s',
                    (new_status, req.actor, cand_id))
    audit.record(audit.Action.PREDICTION_REVIEW, "entity_resolution_candidate", cand_id, actor=req.actor,
                 conn=conn, detail={"op": "review", "action": req.action, "status": new_status})
    return {"entity_resolution_candidate_id": cand_id, "status": new_status,
            "merge": merge_result.model_dump() if merge_result else None}


# ===========================================================================
# Public API (open connections; rw_conn commits on clean exit)
# ===========================================================================
def search_persons(q, gender_id, juvenile, status, page, page_size):
    with db.ro_conn() as conn:
        return _search_persons(conn, q, gender_id, juvenile, status, page, page_size)


def get_person(cpid: int):
    with db.ro_conn() as conn:
        return _detail(conn, cpid)


def create_person(req: S.CreatePersonRequest):
    with db.rw_conn() as conn:
        cpid = _create_person(conn, req)
        return _detail(conn, cpid)


def update_person(cpid: int, req: S.UpdatePersonRequest):
    with db.rw_conn() as conn:
        _update_person(conn, cpid, req)
        return _detail(conn, cpid)


def search_orgs(q, page, page_size):
    with db.ro_conn() as conn:
        return _search_orgs(conn, q, page, page_size)


def create_org(req: S.CreateOrgRequest):
    with db.rw_conn() as conn:
        oid = _create_org(conn, req)
        with conn.cursor() as cur:
            cur.execute('SELECT "CanonicalOrganisationID","PublicRef","Name","OrgType" '
                        'FROM "CanonicalOrganisation" WHERE "CanonicalOrganisationID"=%s', (oid,))
            x = cur.fetchone()
        return S.OrgSummary(canonical_organisation_id=int(x[0]), public_ref=x[1], name=x[2], org_type=x[3])


def add_alias(cpid: int, a: S.AliasInput):
    with db.rw_conn() as conn:
        _add_alias(conn, cpid, a)
        return _detail(conn, cpid)


def add_identifier(cpid: int, i: S.IdentifierInput):
    with db.rw_conn() as conn:
        _add_identifier(conn, cpid, i)
        return _detail(conn, cpid)


def add_contact(cpid: int, c: S.ContactInput):
    with db.rw_conn() as conn:
        _add_contact(conn, cpid, c)
        return _detail(conn, cpid)


def add_address(cpid: int, ad: S.AddressInput):
    with db.rw_conn() as conn:
        _add_address(conn, cpid, ad)
        return _detail(conn, cpid)


def delete_alias(cpid: int, row_id: int, actor=None):
    with db.rw_conn() as conn:
        _delete_attr(conn, "PersonAlias", "PersonAliasID", cpid, row_id, actor)
        return _detail(conn, cpid)


def delete_identifier(cpid: int, row_id: int, actor=None):
    with db.rw_conn() as conn:
        _delete_attr(conn, "PersonIdentifier", "PersonIdentifierID", cpid, row_id, actor)
        return _detail(conn, cpid)


def delete_contact(cpid: int, row_id: int, actor=None):
    with db.rw_conn() as conn:
        _delete_attr(conn, "PersonContact", "PersonContactID", cpid, row_id, actor)
        return _detail(conn, cpid)


def delete_address(cpid: int, row_id: int, actor=None):
    with db.rw_conn() as conn:
        _delete_attr(conn, "PersonAddress", "PersonAddressID", cpid, row_id, actor)
        return _detail(conn, cpid)


def add_party(case_id: int, req: S.AddPartyRequest):
    with db.rw_conn() as conn:
        return _add_party(conn, case_id, req)


def update_party(role_id: int, req: S.UpdatePartyRequest):
    with db.rw_conn() as conn:
        return _update_party(conn, role_id, req)


def remove_party(role_id: int, actor=None):
    with db.rw_conn() as conn:
        case_id = _remove_party(conn, role_id, actor)
        return {"case_party_role_id": role_id, "case_master_id": case_id, "removed": True}


def list_candidates(status, page, page_size):
    with db.ro_conn() as conn:
        return _list_candidates(conn, status, page, page_size)


def generate_candidates(req: S.GenerateCandidatesRequest):
    with db.rw_conn() as conn:
        return _generate_candidates(conn, req)


def review_candidate(cand_id: int, req: S.ReviewCandidateRequest):
    with db.rw_conn() as conn:
        return _review_candidate(conn, cand_id, req)


def merge_persons(winner: int, req: S.MergeRequest):
    with db.rw_conn() as conn:
        result = _merge(conn, winner, req.loser_canonical_person_id, req.reason, req.actor)
        return result


def unmerge_persons(winner: int, req: S.UnmergeRequest):
    with db.rw_conn() as conn:
        return _unmerge(conn, winner, req.loser_canonical_person_id, req.reason, req.actor)


def link_stats():
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT fn_identity_link_stats()")
            return cur.fetchone()[0]
