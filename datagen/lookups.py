"""Populate lookup / organisational tables and build the shared Context.

Runs single-process (these tables are small). Explicit primary keys are assigned
in Python so the resulting id maps can drive foreign keys in the parallel case
phase without any round-trips.
"""
from __future__ import annotations

import datetime as dt
from typing import List

import numpy as np

from . import reference as ref
from .config import GenConfig
from .context import Context
from .db import copy_rows
from .names import person_name
from .rng import RNG


def load_reference(cur, cfg: GenConfig) -> Context:
    rng = RNG(cfg.seed)
    ctx = Context(state_id=1, n_firs=cfg.n_firs)

    _load_state(cur, ctx)
    _load_districts(cur, cfg, ctx)
    unit_type_ids = _load_unit_types(cur)
    _load_units(cur, cfg, ctx, rng, unit_type_ids)
    rank_ids = _load_ranks(cur)
    desig_ids = _load_designations(cur)
    _load_employees(cur, cfg, ctx, rng, rank_ids, desig_ids)
    _load_courts(cur, cfg, ctx, rng)
    _load_case_lookups(cur, ctx)
    crime_head_ids, crime_sub_ids = _load_crime_taxonomy(cur, ctx)
    _load_person_lookups(cur, ctx)
    _load_acts_sections(cur)
    _load_crimehead_actsection(cur, crime_head_ids)
    _resolve_profiles(ctx, crime_head_ids, crime_sub_ids)
    _build_offenders(cfg, ctx, rng)
    _build_gangs(cfg, ctx, rng)
    return ctx


# ---------------------------------------------------------------------------
def _load_state(cur, ctx: Context):
    copy_rows(cur, "State", ["StateID", "StateName", "NationalityID", "Active"],
              [(1, "Karnataka", 1, True)])
    ctx.state_id = 1


def _load_districts(cur, cfg: GenConfig, ctx: Context):
    rows = []
    n = min(cfg.n_districts, len(ref.KARNATAKA_DISTRICTS))
    for i in range(n):
        name, lat, lon, tags, w = ref.KARNATAKA_DISTRICTS[i]
        did = i + 1
        rows.append((did, name, ctx.state_id, True))
        ctx.districts.append(
            {"id": did, "name": name, "lat": lat, "lon": lon,
             "tags": tags, "pop_weight": w})
        ctx.district_weights.append(w)
    copy_rows(cur, "District",
              ["DistrictID", "DistrictName", "StateID", "Active"], rows)


def _load_unit_types(cur) -> dict:
    rows, ids = [], {}
    for i, (name, level, hier) in enumerate(ref.UNIT_TYPES, start=1):
        rows.append((i, name, level, hier, True))
        ids[name] = i
    copy_rows(cur, "UnitType",
              ["UnitTypeID", "UnitTypeName", "CityDistState", "Hierarchy", "Active"],
              rows)
    return ids


def _load_units(cur, cfg: GenConfig, ctx: Context, rng: RNG, unit_type_ids: dict):
    ps_type = unit_type_ids["Police Station"]
    hq_type = unit_type_ids["District HQ"]
    comm_type = unit_type_ids["Commissionerate"]

    rows = []
    uid = 0
    # One HQ / Commissionerate unit per district (acts as ParentUnit).
    for d in ctx.districts:
        uid += 1
        is_metro = "metro" in d["tags"]
        rows.append((uid, f"{d['name']} {'Commissionerate' if is_metro else 'District HQ'}",
                     comm_type if is_metro else hq_type, None,
                     1, ctx.state_id, d["id"], True))
        ctx.district_hq_unit[d["id"] - 1] = uid

    # Distribute stations across districts proportional to population weight.
    weights = np.array(ctx.district_weights, dtype=float)
    weights = weights / weights.sum()
    alloc = np.floor(weights * cfg.n_stations).astype(int)
    # distribute remainder
    while alloc.sum() < cfg.n_stations:
        alloc[int(rng.weighted_index(weights))] += 1

    for di, d in enumerate(ctx.districts):
        count = int(alloc[di])
        spread = 0.04 if "metro" in d["tags"] else (0.18 if "rural" in d["tags"] else 0.10)
        hq = ctx.district_hq_unit[di]
        st_idx_list = []
        for k in range(count):
            uid += 1
            clat = d["lat"] + float(rng.gaussian(0, spread))
            clon = d["lon"] + float(rng.gaussian(0, spread))
            radius = 0.008 if "metro" in d["tags"] else 0.02
            rows.append((uid, f"{d['name']} PS-{k + 1}", ps_type, hq,
                         1, ctx.state_id, d["id"], True))
            st_index = len(ctx.stations)
            ctx.stations.append({"id": uid, "district_idx": di,
                                 "lat": clat, "lon": clon, "radius": radius})
            st_idx_list.append(st_index)
        ctx.stations_by_district[di] = st_idx_list

    copy_rows(cur, "Unit",
              ["UnitID", "UnitName", "TypeID", "ParentUnit", "NationalityID",
               "StateID", "DistrictID", "Active"], rows,
              chunk=cfg.copy_chunk)


def _load_ranks(cur) -> List[int]:
    rows, ids = [], []
    for i, (name, hier) in enumerate(ref.RANKS, start=1):
        rows.append((i, name, hier, True))
        ids.append(i)
    copy_rows(cur, "Rank", ["RankID", "RankName", "Hierarchy", "Active"], rows)
    return ids


def _load_designations(cur) -> List[int]:
    rows, ids = [], []
    for i, (name, order) in enumerate(ref.DESIGNATIONS, start=1):
        rows.append((i, name, True, order))
        ids.append(i)
    copy_rows(cur, "Designation",
              ["DesignationID", "DesignationName", "Active", "SortOrder"], rows)
    return ids


def _load_employees(cur, cfg: GenConfig, ctx: Context, rng: RNG,
                    rank_ids: List[int], desig_ids: List[int]):
    n = cfg.n_officers
    rank_w = np.array(ref.RANK_STAFFING, dtype=float)
    rank_w = rank_w / rank_w.sum()

    # Assign officers to stations (roughly even, min ~4 per station).
    n_stations = len(ctx.stations)
    base = max(1, n // max(1, n_stations))
    for st in ctx.stations:
        ctx.officers_by_station[st["id"]] = []

    rows = []
    today = dt.date.today()
    for eid in range(1, n + 1):
        st_index = (eid - 1) % n_stations
        st = ctx.stations[st_index]
        district_id = ctx.districts[st["district_idx"]]["id"]
        rank_i = int(rng.weighted_index(rank_w))
        rank_id = rank_ids[rank_i]
        desig_id = int(rng.choice(desig_ids))
        gender = ref.GENDER_MALE if rng.bernoulli(0.88) else ref.GENDER_FEMALE
        name = person_name(rng, gender)
        # age 22..58 -> DOB
        age = int(rng.clipped_gaussian(38, 9, 22, 59))
        dob = today - dt.timedelta(days=age * 365 + int(rng.integers(0, 365)))
        service_years = int(rng.clipped_gaussian(min(age - 21, 20), 6, 0, 38))
        appt = today - dt.timedelta(days=service_years * 365 + int(rng.integers(0, 365)))
        kgid = f"KG{eid:07d}"
        phys = rng.bernoulli(0.01)
        blood = int(rng.choice(ref.BLOOD_GROUPS))
        rows.append((eid, district_id, st["id"], rank_id, desig_id, kgid,
                     name, dob.isoformat(), gender, blood, bool(phys),
                     appt.isoformat()))
        ctx.officers_by_station[st["id"]].append(eid)

    # Guarantee every station has at least one officer (wrap-around already
    # helps, but stations beyond n get none -> assign nearest by reusing).
    for st in ctx.stations:
        if not ctx.officers_by_station[st["id"]]:
            donor = ctx.stations[int(rng.integers(0, n_stations))]["id"]
            src = ctx.officers_by_station[donor]
            ctx.officers_by_station[st["id"]] = [src[0]] if src else [1]

    copy_rows(cur, "Employee",
              ["EmployeeID", "DistrictID", "UnitID", "RankID", "DesignationID",
               "KGID", "FirstName", "EmployeeDOB", "GenderID", "BloodGroupID",
               "PhysicallyChallenged", "AppointmentDate"], rows,
              chunk=cfg.copy_chunk)


def _load_courts(cur, cfg: GenConfig, ctx: Context, rng: RNG):
    n = cfg.n_courts
    weights = np.array(ctx.district_weights, dtype=float)
    weights = weights / weights.sum()
    alloc = np.floor(weights * n).astype(int)
    while alloc.sum() < n:
        alloc[int(rng.weighted_index(weights))] += 1

    rows = []
    cid = 0
    court_kinds = ["JMFC", "Sessions Court", "District Court", "Special Court",
                   "CJM Court", "Fast Track Court"]
    for di, d in enumerate(ctx.districts):
        ids = []
        for k in range(int(alloc[di])):
            cid += 1
            kind = court_kinds[k % len(court_kinds)]
            rows.append((cid, f"{d['name']} {kind} - {k + 1}",
                         d["id"], ctx.state_id, True))
            ids.append(cid)
        ctx.courts_by_district[di] = ids or [1]
    copy_rows(cur, "Court",
              ["CourtID", "CourtName", "DistrictID", "StateID", "Active"], rows)


def _load_case_lookups(cur, ctx: Context):
    # Case categories
    rows = []
    for i, name in enumerate(ref.CASE_CATEGORIES, start=1):
        rows.append((i, name))
        ctx.category_id[name] = i
        ctx.category_code[name] = ref.CATEGORY_CODE.get(name, 1)
    copy_rows(cur, "CaseCategory", ["CaseCategoryID", "LookupValue"], rows)

    # Gravity
    rows = []
    for i, name in enumerate(ref.GRAVITY_LEVELS, start=1):
        rows.append((i, name))
        ctx.gravity_id[name] = i
    copy_rows(cur, "GravityOffence", ["GravityOffenceID", "LookupValue"], rows)

    # Statuses
    rows = []
    for i, name in enumerate(ref.CASE_STATUSES, start=1):
        rows.append((i, name))
        ctx.status_ids.append(i)
    copy_rows(cur, "CaseStatusMaster", ["CaseStatusID", "CaseStatusName"], rows)


def _load_crime_taxonomy(cur, ctx: Context):
    # Unique major heads
    heads = []
    for p in ref.CRIME_PROFILES:
        if p["head"] not in heads:
            heads.append(p["head"])
    head_ids = {}
    rows = []
    for i, h in enumerate(heads, start=1):
        rows.append((i, h, True))
        head_ids[h] = i
    copy_rows(cur, "CrimeHead", ["CrimeHeadID", "CrimeGroupName", "Active"], rows)

    # Sub-heads (one per crime profile subhead, unique within head)
    sub_ids = {}
    rows = []
    seq = 0
    sid = 0
    seen = set()
    for p in ref.CRIME_PROFILES:
        key = (p["head"], p["sub"])
        if key in seen:
            continue
        seen.add(key)
        sid += 1
        seq += 1
        rows.append((sid, head_ids[p["head"]], p["sub"], seq))
        sub_ids[p["sub"]] = sid
    copy_rows(cur, "CrimeSubHead",
              ["CrimeSubHeadID", "CrimeHeadID", "CrimeHeadName", "SeqID"], rows)
    return head_ids, sub_ids


def _load_person_lookups(cur, ctx: Context):
    rows = []
    for i, name in enumerate(ref.CASTES, start=1):
        rows.append((i, name))
        ctx.caste_ids.append(i)
    copy_rows(cur, "CasteMaster", ["caste_master_id", "caste_master_name"], rows)

    rows = []
    for i, name in enumerate(ref.RELIGIONS, start=1):
        rows.append((i, name))
        ctx.religion_ids.append(i)
        ctx.religion_weights.append(ref.RELIGION_WEIGHTS[i - 1])
    copy_rows(cur, "ReligionMaster", ["ReligionID", "ReligionName"], rows)

    rows = []
    for i, name in enumerate(ref.OCCUPATIONS, start=1):
        rows.append((i, name))
        ctx.occupation_ids.append(i)
    copy_rows(cur, "OccupationMaster", ["OccupationID", "OccupationName"], rows)


def _load_acts_sections(cur):
    copy_rows(cur, "Act", ["ActCode", "ActDescription", "ShortName", "Active"],
              [(code, desc, short, True) for code, desc, short in ref.ACTS])
    rows = [(sc, ac, desc, True) for sc, ac, desc in ref.all_sections()]
    copy_rows(cur, "Section",
              ["SectionCode", "ActCode", "SectionDescription", "Active"], rows)


def _load_crimehead_actsection(cur, head_ids: dict):
    seen = set()
    rows = []
    for p in ref.CRIME_PROFILES:
        hid = head_ids[p["head"]]
        for act, nums in p["acts"]:
            for num in nums:
                sc = ref.section_code(act, num)
                key = (hid, act, sc)
                if key in seen:
                    continue
                seen.add(key)
                rows.append((hid, act, sc))
    if rows:
        copy_rows(cur, "CrimeHeadActSection",
                  ["CrimeHeadID", "ActCode", "SectionCode"], rows)


def _resolve_profiles(ctx: Context, head_ids: dict, sub_ids: dict):
    for p in ref.CRIME_PROFILES:
        rp = dict(p)
        rp["crime_head_id"] = head_ids[p["head"]]
        rp["crime_sub_id"] = sub_ids[p["sub"]]
        rp["gravity_id"] = ctx.gravity_id[p["gravity"]]
        # pre-expand act/section codes to (actcode, sectioncode) pairs
        pairs = []
        for act, nums in p["acts"]:
            for num in nums:
                pairs.append((act, ref.section_code(act, num)))
        rp["section_pairs"] = pairs
        ctx.crime_profiles.append(rp)
        ctx.crime_weights.append(p["weight"])


def _build_offenders(cfg: GenConfig, ctx: Context, rng: RNG):
    """Recurring criminal identities. Offense counts follow a power law:
    a few career criminals commit many crimes, most only a handful."""
    n = cfg.n_repeat_offenders
    n_profiles = len(ctx.crime_profiles)
    prof_w = np.array(ctx.crime_weights, dtype=float)
    prof_w = prof_w / prof_w.sum()
    dist_w = np.array(ctx.district_weights, dtype=float)
    dist_w = dist_w / dist_w.sum()

    for i in range(n):
        gender = ref.GENDER_MALE if rng.bernoulli(0.92) else ref.GENDER_FEMALE
        specialty = int(rng.weighted_index(prof_w))
        home = int(rng.weighted_index(dist_w))
        juvenile = bool(rng.bernoulli(0.06))
        age_base = int(rng.integers(15, 18)) if juvenile else int(
            rng.clipped_gaussian(30, 9, 18, 65))
        # career length / offense propensity (power law, heavy tail)
        offenses = int(rng.truncated_power_law_int(2, 40, alpha=2.3))
        ctx.offenders.append({
            "name": person_name(rng, gender),
            "gender": gender,
            "home_dist": home,
            "age_base": age_base,
            "specialty": specialty,
            "is_juvenile": juvenile,
            "offense_budget": offenses,
        })


def _build_gangs(cfg: GenConfig, ctx: Context, rng: RNG):
    from .names import gang_name, vehicle_plate
    n = cfg.n_gangs
    # gangs specialise in organised crime types
    gang_specialties = [i for i, p in enumerate(ctx.crime_profiles)
                        if p["gang"] >= 0.3]
    if not gang_specialties:
        gang_specialties = list(range(len(ctx.crime_profiles)))
    dist_w = np.array(ctx.district_weights, dtype=float)
    dist_w = dist_w / dist_w.sum()

    # index offenders by home district for roster building
    by_dist = {}
    for idx, o in enumerate(ctx.offenders):
        by_dist.setdefault(o["home_dist"], []).append(idx)

    for gi in range(n):
        home = int(rng.weighted_index(dist_w))
        specialty = int(rng.choice(gang_specialties))
        pool = by_dist.get(home, [])
        if len(pool) < 6:
            # borrow from neighbouring districts
            pool = pool + [int(rng.integers(0, len(ctx.offenders)))
                           for _ in range(8)]
        size = int(rng.clipped_gaussian(9, 4, 4, 22))
        members = list({int(rng.choice(pool)) for _ in range(size)})
        vehicles = [vehicle_plate(rng) for _ in range(int(rng.integers(1, 4)))]
        ctx.gangs.append({
            "name": gang_name(rng),
            "home_dist": home,
            "specialty": specialty,
            "members": members,
            "vehicles": vehicles,
        })
