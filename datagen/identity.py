"""Stable canonical identity for Datagen v2.

The audit's central defect was identity: Accused.PersonID was an intra-case
A1/A2 sequence (only 26 distinct values), the graph linked by array index, and
cases were joined by duplicate names. This module fixes that at the root:

  * Every recurring synthetic offender gets ONE stable ``CanonicalPersonID`` that
    is reused across every case they appear in.
  * Every one-time participant (victim/complainant/witness/one-time accused) gets
    its own fresh CanonicalPersonID — names are never reused as an identity key.
  * Same-name/different-person and alias/same-person scenarios are generated
    deliberately, with EntityResolutionCandidate rows for review (never auto-merged)
    and EntityMergeHistory for reviewed merges/splits.
  * EntityGraph links to CanonicalEntity via a true foreign key.

Ids are minted from ``World`` sequences, never derived from names or indexes.
"""
from __future__ import annotations

from typing import Optional

from . import reference as ref
from .db import Geom, Json
from .names import person_name
from . import v2common as C

# --- column registrations (exact COPY column order) -------------------------
C.register("CanonicalPerson", [
    "CanonicalPersonID", "PublicRef", "DisplayLabel", "IsUnknown",
    "PrimaryGenderID", "ApproxBirthYear", "IsJuvenile", "ResolutionStatus",
    "MergedIntoCanonicalPersonID", "Attributes", "IsSynthetic",
])
C.register("CanonicalOrganisation", [
    "CanonicalOrganisationID", "PublicRef", "Name", "OrgType", "Attributes",
])
C.register("CanonicalEntity", [
    "CanonicalEntityID", "EntityKind", "CanonicalPersonID",
    "CanonicalOrganisationID", "PublicRef", "Label", "Attributes", "IsSynthetic",
])
C.register("PersonAlias", [
    "CanonicalPersonID", "AliasName", "AliasType", "SourceRecordID", "IsSynthetic",
])
C.register("PersonIdentifier",
           ["CanonicalPersonID", "IdentifierType", "IdentifierValue", "Sensitivity"])
C.register("PersonContact",
           ["CanonicalPersonID", "ContactType", "ContactValue", "Sensitivity"])
C.register("PersonAddress",
           ["CanonicalPersonID", "DistrictID", "AddressText", "geom", "Sensitivity"])
C.register("EntityResolutionCandidate", [
    "CanonicalPersonA", "CanonicalPersonB", "Method", "Score", "MatchFeatures",
    "Status", "ReviewedByActor", "ReviewedAt",
])
C.register("EntityMergeHistory", [
    "Action", "WinnerCanonicalPersonID", "LoserCanonicalPersonID", "Reason",
    "Actor", "BeforeState", "AfterState",
])


class IdentityBuilder:
    """Mints and tracks canonical identities into ``world``."""

    def __init__(self, world: C.World):
        self.w = world
        self.rng = world.rng

    # -- person minting ------------------------------------------------------
    def mint_person(self, label: str, gender: Optional[int], *,
                    birth_year: Optional[int] = None, juvenile: bool = False,
                    is_unknown: bool = False, attributes: Optional[dict] = None) -> int:
        w = self.w
        cpid = w.next_id("CanonicalPerson")
        w.add("CanonicalPerson", (
            cpid, C.person_ref(cpid), None if is_unknown else label, is_unknown,
            gender, birth_year, juvenile, "canonical", None,
            Json(attributes or {}), True,
        ))
        # every person is also a canonical entity node
        eid = w.next_id("CanonicalEntity")
        w.add("CanonicalEntity", (
            eid, "person", cpid, None, C.entity_ref(eid),
            None if is_unknown else label, Json({}), True,
        ))
        w.person_entity[cpid] = eid
        if gender is not None:
            w.person_gender[cpid] = gender
        if birth_year is not None:
            w.person_birthyear[cpid] = birth_year
        if not is_unknown:
            w.person_label[cpid] = label
        return cpid

    def mint_unknown_person(self) -> int:
        """An unidentified party — no invented name/identity."""
        cpid = self.mint_person("UNKNOWN / UNIDENTIFIED", None, is_unknown=True,
                                 attributes={"unidentified": True})
        self.w.cover("unknown_unidentified_party")
        return cpid

    def mint_organisation(self, name: str, org_type: str = "gang",
                          attributes: Optional[dict] = None) -> int:
        w = self.w
        oid = w.next_id("CanonicalOrganisation")
        w.add("CanonicalOrganisation",
              (oid, C.org_ref(oid), name, org_type, Json(attributes or {})))
        eid = w.next_id("CanonicalEntity")
        w.add("CanonicalEntity",
              (eid, "organisation", None, oid, C.entity_ref(eid), name, Json({}), True))
        w.org_entity[oid] = eid
        return oid

    def mint_nonperson_entity(self, kind: str, label: str,
                              attributes: Optional[dict] = None) -> int:
        """A phone/vehicle/account/device/location entity (non-person node)."""
        w = self.w
        eid = w.next_id("CanonicalEntity")
        w.add("CanonicalEntity",
              (eid, kind, None, None, C.entity_ref(eid), label,
               Json(attributes or {}), True))
        return eid

    # -- attributes ----------------------------------------------------------
    def add_alias(self, cpid: int, alias_name: str, alias_type: str = "alias") -> None:
        self.w.add("PersonAlias", (cpid, alias_name, alias_type, None, True))

    def add_identifier(self, cpid: int, id_type: str, value: str,
                       sensitivity: str = "restricted") -> None:
        self.w.add("PersonIdentifier", (cpid, id_type, value, sensitivity))

    def add_contact(self, cpid: int, ctype: str, value: str,
                    sensitivity: str = "restricted") -> None:
        self.w.add("PersonContact", (cpid, ctype, value, sensitivity))

    def add_address(self, cpid: int, district_id: int, text: str,
                    lon: Optional[float], lat: Optional[float],
                    sensitivity: str = "restricted") -> None:
        geom = Geom.point(lon, lat) if (lon is not None and lat is not None) else None
        self.w.add("PersonAddress", (cpid, district_id, text, geom, sensitivity))

    # -- resolution / merge --------------------------------------------------
    def add_resolution_candidate(self, a: int, b: int, method: str, score: float,
                                 status: str, features: dict,
                                 reviewer: Optional[str] = None,
                                 reviewed_at: Optional[str] = None) -> None:
        lo, hi = (a, b) if a < b else (b, a)
        self.w.add("EntityResolutionCandidate",
                   (lo, hi, method, round(float(score), 5), Json(features),
                    status, reviewer, reviewed_at))

    def add_merge(self, winner: int, loser: int, action: str, reason: str,
                  actor: str, before: dict, after: dict) -> None:
        self.w.add("EntityMergeHistory",
                   (action, winner, loser, reason, actor, Json(before), Json(after)))


def build_population(world: C.World) -> IdentityBuilder:
    """Create the stable canonical person/organisation population from the
    Context's offender + gang pools (the recurring-identity backbone)."""
    ib = IdentityBuilder(world)
    ctx = world.ctx

    # 1. Recurring offenders -> stable canonical persons (reused across cases).
    for idx, o in enumerate(ctx.offenders):
        birth_year = 2025 - int(o["age_base"])
        cpid = ib.mint_person(
            o["name"], o["gender"], birth_year=birth_year,
            juvenile=bool(o.get("is_juvenile")),
            attributes={
                "role_class": "recurring_offender",
                "specialty_profile": int(o["specialty"]),
                "home_district_idx": int(o["home_dist"]),
                "offense_budget": int(o["offense_budget"]),
                "synthetic": True,
            },
        )
        world.offender_person[idx] = cpid

    # 2. Gangs -> canonical organisations.
    for gi, g in enumerate(ctx.gangs):
        oid = ib.mint_organisation(
            g["name"], "gang",
            attributes={"home_district_idx": int(g["home_dist"]),
                        "specialty_profile": int(g["specialty"]),
                        "member_count": len(g["members"]), "synthetic": True})
        world.gang_org[gi] = oid

    return ib
