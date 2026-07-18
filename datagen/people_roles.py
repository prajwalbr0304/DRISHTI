"""Case-party roles + canonically-linked legacy person tables.

Every appearance of a person in a case becomes a ``CasePartyRole`` row bound to a
stable ``CanonicalPersonID`` (or an explicit unknown party). The legacy
``Accused`` / ``Victim`` / ``ComplainantDetails`` rows are still written for
backward compatibility, but each now carries ``CanonicalPersonID`` (and Accused
also ``CasePartyRoleID``). The old ``PersonID`` A1/A2 field is preserved ONLY as a
display sort key attribute — it is no longer an identity key.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np

from . import reference as ref
from .db import Json
from .identity import IdentityBuilder
from .names import person_name
from . import v2common as C

C.register("CasePartyRole", [
    "CasePartyRoleID", "CaseMasterID", "CanonicalPersonID", "CanonicalOrganisationID",
    "RoleType", "IsUnknownParty", "LegacyRefTable", "LegacyRefID", "PartyLabel",
    "SequenceNo", "Provenance",
])
C.register("Accused", [
    "AccusedMasterID", "CaseMasterID", "AccusedName", "AgeYear", "GenderID",
    "PersonID", "CanonicalPersonID", "CasePartyRoleID",
])
C.register("Victim", [
    "VictimMasterID", "CaseMasterID", "VictimName", "AgeYear", "GenderID",
    "VictimPolice", "CanonicalPersonID",
])
C.register("ComplainantDetails", [
    "ComplainantID", "CaseMasterID", "ComplainantName", "AgeYear", "OccupationID",
    "ReligionID", "CasteID", "GenderID", "CanonicalPersonID",
])


@dataclass
class PartySpec:
    """All party decisions made by the planner; materialised here into rows."""
    kind: str
    profile: dict
    known_accused_cpids: List[int] = field(default_factory=list)  # canonical ids (offenders/one-time known)
    n_unknown_accused: int = 0
    victim_genders: List[int] = field(default_factory=list)       # explicit victim genders
    n_complainants: int = 1
    n_witnesses: int = 0
    informant: bool = False
    guardian: bool = False
    org_id: Optional[int] = None       # CanonicalOrganisationID (gang) participating
    district_id: int = 1


@dataclass
class AccusedRef:
    accused_master_id: int
    canonical_person_id: Optional[int]
    gender: Optional[int]


def _age_for(world: C.World, cpid: int, fallback_mu=30, fallback_sigma=9) -> int:
    by = world.person_birthyear.get(cpid)
    if by:
        return max(10, min(85, 2025 - by))
    return int(np.clip(world.rng.g.normal(fallback_mu, fallback_sigma), 12, 80))


def build_case_parties(world: C.World, ib: IdentityBuilder, *, case_id: int,
                       spec: PartySpec) -> List[AccusedRef]:
    w = world
    rng = w.rng
    profile = spec.profile
    accused_out: List[AccusedRef] = []
    seq_attr = 0  # A1/A2 display attribute counter (NOT identity)

    def add_role(role, cpid=None, org=None, unknown=False, legacy_table=None,
                 legacy_id=None, label=None, seqno=None) -> int:
        rid = w.next_id("CasePartyRole")
        w.add("CasePartyRole", (
            rid, case_id, cpid, org, role, unknown, legacy_table, legacy_id,
            label, seqno, Json({"synthetic": True}),
        ))
        if cpid is not None:
            w.person_case_count[cpid] = w.person_case_count.get(cpid, 0) + 1
        return rid

    # ---- accused (known canonical persons) --------------------------------
    if spec.kind not in ("udr",) and profile is not None:
        for cpid in spec.known_accused_cpids:
            seq_attr += 1
            gender = w.person_gender.get(cpid, ref.GENDER_MALE)
            name = w.person_label.get(cpid, "Accused")
            age = _age_for(world, cpid, *(profile.get("age") or (30, 9)))
            am_id = w.next_id("Accused")
            rid = add_role("accused", cpid=cpid, legacy_table="Accused",
                           legacy_id=am_id, label=name, seqno=seq_attr)
            w.add("Accused", (am_id, case_id, name, age, gender,
                              f"A{seq_attr}", cpid, rid))
            accused_out.append(AccusedRef(am_id, cpid, gender))
            w.cover("known_accused")

    # ---- accused (unknown / unidentified) ---------------------------------
    for _ in range(spec.n_unknown_accused):
        seq_attr += 1
        am_id = w.next_id("Accused")
        rid = add_role("accused", unknown=True, legacy_table="Accused",
                       legacy_id=am_id, label="Unknown / Unidentified",
                       seqno=seq_attr)
        w.add("Accused", (am_id, case_id, "Unknown / Unidentified", None,
                          None, f"A{seq_attr}", None, rid))
        accused_out.append(AccusedRef(am_id, None, None))
        w.cover("unknown_accused")
        w.cover("unknown_unidentified_party")

    # ---- organisation party (gang) ----------------------------------------
    if spec.org_id is not None:
        add_role("organisation", org=spec.org_id, label="Organised group")
        w.cover("organisation_party")

    # ---- victims (one-time canonical persons) -----------------------------
    for g in spec.victim_genders:
        age = int(np.clip(rng.g.normal(30, 14), 1, 95))
        by = 2025 - age
        name = person_name(rng, g if g in (ref.GENDER_MALE, ref.GENDER_FEMALE) else ref.GENDER_MALE)
        cpid = ib.mint_person(name, g, birth_year=by,
                              attributes={"role_class": "victim"})
        is_police = "1" if rng.bernoulli(0.02) else "0"
        vm_id = w.next_id("Victim")
        add_role("victim", cpid=cpid, legacy_table="Victim", legacy_id=vm_id, label=name)
        w.add("Victim", (vm_id, case_id, name, age, g, is_police, cpid))

    # ---- complainants ------------------------------------------------------
    for _ in range(spec.n_complainants):
        g = ref.GENDER_MALE if rng.bernoulli(0.6) else ref.GENDER_FEMALE
        age = int(np.clip(rng.g.normal(38, 13), 15, 90))
        name = person_name(rng, g)
        cpid = ib.mint_person(name, g, birth_year=2025 - age,
                              attributes={"role_class": "complainant"})
        occ = int(rng.choice(w.ctx.occupation_ids))
        relw = np.array(w.ctx.religion_weights)
        rel = int(w.ctx.religion_ids[int(rng.weighted_index(relw))])
        caste = int(rng.choice(w.ctx.caste_ids))
        cm_id = w.next_id("ComplainantDetails")
        add_role("complainant", cpid=cpid, legacy_table="ComplainantDetails",
                 legacy_id=cm_id, label=name)
        w.add("ComplainantDetails", (cm_id, case_id, name, age, occ, rel, caste, g, cpid))

    # ---- witnesses / informant / guardian ---------------------------------
    for _ in range(spec.n_witnesses):
        g = ref.GENDER_MALE if rng.bernoulli(0.55) else ref.GENDER_FEMALE
        age = int(np.clip(rng.g.normal(35, 12), 15, 85))
        name = person_name(rng, g)
        cpid = ib.mint_person(name, g, birth_year=2025 - age,
                              attributes={"role_class": "witness"})
        add_role("witness", cpid=cpid, label=name)
        w.cover("witness_role")

    if spec.informant:
        g = ref.GENDER_MALE if rng.bernoulli(0.7) else ref.GENDER_FEMALE
        name = person_name(rng, g)
        cpid = ib.mint_person(name, g, birth_year=1985,
                              attributes={"role_class": "informant"})
        add_role("informant", cpid=cpid, label=name)
        w.cover("informant_role")

    if spec.guardian:
        g = ref.GENDER_FEMALE if rng.bernoulli(0.5) else ref.GENDER_MALE
        name = person_name(rng, g)
        cpid = ib.mint_person(name, g, birth_year=1975,
                              attributes={"role_class": "guardian"})
        add_role("guardian", cpid=cpid, label=name)
        w.cover("guardian_role")

    return accused_out
