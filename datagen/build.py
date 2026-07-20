"""Datagen v2 orchestrator: assemble a scenario-driven, canonically-linked fixture.

Reuses the proven ``cases.Planner`` for geography/offender/coordinate placement
(guaranteeing in-state, in-jurisdiction incidents) and layers the v2 canonical
model on top: stable identity, category-specific lifecycles, case-party roles,
evidence, statements, property, digital, financial, court/outcomes, provenanced
graph, governed features and leakage-safe labels.

Single-process and deterministic for a given seed.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from typing import Dict, List, Optional

import numpy as np

from . import boundaries as B
from . import cases
from . import case_events as CE
from . import court_outcomes as CO
from . import digital as DIG
from . import evidence as EV
from . import external_context as EC
from . import financial as FIN
from . import identity as ID
from . import labels as LB
from . import people_roles as PR
from . import property_seizure as PS
from . import quality_scenarios as QS
from . import reference as ref
from . import scenario_registry as SR
from . import statements as ST
from . import v2common as C
from .db import Json
from .rng import RNG

# --- operational (legacy-shape) tables the v2 fixture regenerates cleanly ----
C.register("CaseMaster", [
    "CaseMasterID", "CrimeNo", "CrimeRegisteredDate", "PolicePersonID",
    "PoliceStationID", "CaseCategoryID", "GravityOffenceID", "CrimeMajorHeadID",
    "CrimeMinorHeadID", "CaseStatusID", "CourtID", "IncidentFromDate",
    "IncidentToDate", "InfoReceivedPSDate", "latitude", "longitude", "BriefFacts",
])
C.register("ActSectionAssociation",
           ["CaseMasterID", "ActID", "SectionID", "ActOrderID", "SectionOrderID"])
C.register("ArrestSurrender", [
    "ArrestSurrenderID", "CaseMasterID", "ArrestSurrenderTypeID",
    "ArrestSurrenderDate", "ArrestSurrenderStateId", "ArrestSurrenderDistrictId",
    "PoliceStationID", "IOID", "CourtID", "AccusedMasterID", "IsAccused",
    "IsComplainantAccused",
])
C.register("inv_arrestsurrenderaccused", ["ArrestSurrenderID", "AccusedMasterID"])
C.register("ChargesheetDetails",
           ["CSID", "CaseMasterID", "csdate", "cstype", "PolicePersonID"])
C.register("Inv_OccuranceTime", ["CaseMasterID"])
# graph
C.register("EntityGraph", [
    "EntityID", "EntityType", "Label", "RefTable", "RefID", "AccusedMasterID",
    "CanonicalEntityID", "Attributes",
])
C.register("NetworkEdge", [
    "Source", "Target", "RelationshipType", "Cost", "ReverseCost", "Directed",
    "Weight", "Confidence", "Properties", "SourceRecordID",
    "EvidenceEntityLinkID", "ProvenanceStatus", "EvidenceCaseID",
])
C.register("GangMembership", [
    "GangEntityID", "MemberEntityID", "AccusedMasterID", "MemberCanonicalPersonID",
    "Role", "IsActive", "Confidence", "Source",
])


def _snap_into_district(bnd, region, rng) -> tuple:
    """Return a (lat, lon) guaranteed inside the district polygon AND the state.

    The SHO Voronoi ring is simplified independently of the district/state
    polygons, so a tiny fraction of ring-sampled points land in the sliver just
    outside the (also simplified) district/state outline. This rejects such
    points, keeping every CANONICAL coordinate strictly in its assigned
    jurisdiction (the roadmap's zero-out-of-jurisdiction gate)."""
    for _ in range(40):
        pt = B.uniform_points(region.geom, region.bounds, rng.g, 1)[0]
        lon, lat = float(pt[0]), float(pt[1])
        if bnd.in_state(lon, lat):
            return lat, lon
    rx, ry = region.representative()   # interior point of the district polygon
    return float(ry), float(rx)


def _wchoice(rng: RNG, weights: Dict[str, float]) -> str:
    keys = list(weights)
    w = np.array([weights[k] for k in keys], dtype=float)
    w = w / w.sum()
    return keys[int(np.searchsorted(np.cumsum(w), rng.g.random()))]


class _CrimeNoV2:
    """18-digit CrimeNo with the v2 category code (unit/category/year serial)."""

    def __init__(self):
        self.serial: Dict[tuple, int] = {}

    def make(self, category_code_int: int, district_id: int, unit_id: int, year: int) -> str:
        key = (unit_id, category_code_int, year)
        s = self.serial.get(key, 0) + 1
        self.serial[key] = s
        return f"{category_code_int:1d}{district_id:04d}{unit_id:04d}{year:04d}{s:05d}"


def build_fixture(cfg, ctx, *, mode: str, run_key: str, write_files: bool,
                  out_dir: str, log=print):
    rng = RNG(cfg.seed * 101 + 5)
    world = C.World(cfg, ctx, rng)
    # Golden stays fully rich (coverage). statistical/performance run "lean": the
    # per-case child volumes are trimmed so a 100k-case fixture fits a modest dev
    # database disk. All integrity gates still hold on the leaner data; only the
    # golden fixture is gated on scenario-minimum coverage.
    world.lean = mode != "golden"

    # observation cutoff / label window (feature data <= cutoff; labels after).
    end_dt = dt.datetime(cfg.end_date.year, cfg.end_date.month, cfg.end_date.day, 23, 59)
    world.observation_cutoff = end_dt - dt.timedelta(days=180)
    world.label_window_start = world.observation_cutoff
    world.label_window_end = end_dt
    world.area_stats = defaultdict(lambda: {"pre": 0, "post": 0, "night": 0,
                                            "cyber": 0, "total": 0, "prioryear": 0})
    obs_window_days = (world.observation_cutoff.date() - cfg.start_date).days

    # source systems
    for code, name, kind in [
        ("FIR_FORM", "React FIR intake form", "manual_form"),
        ("CSV_IMPORT", "CSV/JSON structured import", "csv_import"),
        ("COURT_DOC", "Court document upload", "court_document"),
        ("DIGITAL_EXPORT", "CDR/device/chat export", "digital_export"),
    ]:
        sid = world.next_id("SourceSystem")
        world.add("SourceSystem", (sid, code, name, kind, f"Synthetic {name}."))
        world.source_system[code] = sid
    fir_sys = world.source_system["FIR_FORM"]

    # canonical population (stable offenders -> persons; gangs -> orgs)
    ib = ID.build_population(world)
    # workflow metadata + jurisdiction/external context
    CE.emit_case_workflow_seed(world)
    EC.build_context_layer(world)

    # plan cases with the proven geography engine
    planner = cases.Planner(cfg, ctx)
    plans = planner.plan()
    log(f"  planned {len(plans):,} base cases")

    # boundaries + district id->name for the canonical-coordinate containment guard
    world._bnd = B.load_boundaries()
    world._id2name = {d["id"]: d["name"] for d in ctx.districts}

    evwriter = EV.EvidenceWriter.create(out_dir, write_files)
    status_id_by_name = {name: ctx.status_ids[i]
                         for i, name in enumerate(ref.CASE_STATUSES)}
    crimeno = _CrimeNoV2()

    n = len(plans)
    for i, p in enumerate(plans):
        _build_one_case(world, ib, evwriter, p, ctx, cfg, mode, i, n,
                        status_id_by_name, crimeno, obs_window_days)
        if (i + 1) % 20000 == 0:
            log(f"  built {i + 1:,}/{n:,} cases")

    # repeat-offender coverage: a canonical person appearing in >1 case
    repeat = sum(1 for c in world.person_case_count.values() if c > 1)
    world.cover("repeat_offender_multi_case", repeat)
    log(f"  repeat offenders across >1 case: {repeat:,}")

    _build_graph(world, log)
    LB.build_features_and_labels(world)
    sample_cases = [pp[cases.F_ID] for pp in plans[:25]]
    QS.build_quality_scenarios(world, ib, sample_cases)
    manifest = evwriter.flush_manifest()
    if manifest:
        log(f"  evidence fixture manifest: {manifest}")

    ops = world.to_ops(C.V2_LOAD_ORDER)
    totals = {op.table: len(op) for op in ops}
    fx = C.Fixture(mode=mode, run_key=run_key, seed=cfg.seed,
                   target_firs=cfg.n_firs, ops=ops,
                   scenario_coverage=dict(world.coverage), totals=totals)
    return fx, world


# ---------------------------------------------------------------------------
def _scenario_flags(world, mode, i, kind, profile):
    """Decide which sub-domains this case exercises. Golden mode forces coverage
    on early cases so every minimum is met; larger modes sample at LEAN rates so
    the fixture fits the dev disk while every integrity gate still holds."""
    rng = world.rng
    golden = mode == "golden"
    lean = getattr(world, "lean", not golden)
    forced = golden and i < 400
    head = profile["head"]
    is_cyber = head == "Economic & Cyber Crime"
    is_property = head == "Crimes Against Property"
    is_drug = head == "Drug Offences"
    is_women_child = head in ("Crimes Against Women",)

    # lean sampling rates keep the 100k footprint small
    r_ev = 0.08 if lean else 0.35
    r_stmt = 0.10 if lean else 0.35
    r_prop = 0.30 if lean else 1.0     # fraction of property crimes that get an item
    r_fin = 0.15 if lean else 0.5
    wit_lambda = 0.15 if lean else 0.7

    ev_types: List[str] = []
    et_all = list(EV.EVIDENCE_TYPES.keys())
    if forced:
        ev_types = [et_all[i % len(et_all)]]
        if i % 7 == 0:
            ev_types.append("image")
    elif rng.bernoulli(r_ev):
        ev_types = [rng.choice(["document", "image", "digital_export", "court_document"])]

    prop: List[str] = []
    if forced or (is_property and rng.bernoulli(r_prop)):
        prop.append("property")
    if (forced and i % 25 == 3) or (is_property and not lean and rng.bernoulli(0.2)):
        prop.append("vehicle")
    if (forced and i % 25 == 8) or (rng.bernoulli(0.05 if not lean else 0.01)):
        prop.append("weapon")
    if is_drug and (not lean or rng.bernoulli(0.5)):
        prop.append("substance")

    return {
        "ev_types": ev_types,
        "version_replace": forced and (i % 40 == 5),
        "multi_case_link": forced and (i % 45 == 7),
        "conflicting_meta": forced and (i % 60 == 11),
        "statements": (2 if forced and i % 3 == 0 else (1 if rng.bernoulli(r_stmt) else 0)),
        "restricted_stmt": is_women_child,
        "property": prop,
        "digital_comm": (4 if (forced and i % 10 == 2) else (int(rng.g.integers(1, 4)) if is_cyber and rng.bernoulli(0.15 if lean else 0.5) else 0)),
        "digital_loc": (4 if (forced and i % 10 == 4) else (int(rng.g.integers(1, 3)) if rng.bernoulli(0.05 if lean else 0.15) else 0)),
        "digital_device": (forced and i % 15 == 6) or (is_cyber and rng.bernoulli(0.05 if lean else 0.2)),
        "financial": (is_cyber and (forced or rng.bernoulli(r_fin))),
        "informant": (forced and i % 12 == 3) or rng.bernoulli(0.02 if lean else 0.05),
        "guardian": (is_women_child and rng.bernoulli(0.1 if lean else 0.3)) or (forced and i % 18 == 5),
        "unknown_accused": (1 if (forced and i % 8 == 1) else (int(rng.g.integers(1, 3)) if rng.bernoulli(0.12) else 0)),
        "witnesses": (2 if forced and i % 2 == 0 else int(rng.poisson(wit_lambda))),
    }


def _build_one_case(world, ib, evwriter, p, ctx, cfg, mode, i, n,
                    status_id_by_name, crimeno, obs_window_days):
    F = cases
    rng = world.rng
    case_id = p[F.F_ID]
    profile = ctx.crime_profiles[p[F.F_PROFILE]]
    subhead = profile["sub"]
    district_id = p[F.F_DISTRICT]
    unit_id = p[F.F_STATION]
    officer_id = p[F.F_OFFICER]
    lat, lon = p[F.F_LAT], p[F.F_LON]
    # Canonical-coordinate containment guard: keep every case strictly inside its
    # assigned district polygon and the state outline (fixes rare SHO-ring slivers).
    _region = world._bnd.district(world._id2name.get(district_id, ""))
    if _region is not None and (not _region.contains(lon, lat)
                                or not world._bnd.in_state(lon, lat)):
        lat, lon = _snap_into_district(world._bnd, _region, rng)
    reg_date = dt.date.fromisoformat(p[F.F_REGDATE])
    year = int(p[F.F_INCFROM][:4])

    # kind + lifecycle
    sampled_kind = _wchoice(rng, SR.KIND_SAMPLING_WEIGHTS)
    kind = SR.classify_kind(subhead, sampled_kind)
    kd = SR.CASE_KINDS[kind]
    category_code = kd.category
    life = CE.build_lifecycle(kind, rng, cfg, obs_window_days)
    # A final outcome is "late" if it lands after the observation cutoff DATE
    # (registration date is only known here, not inside build_lifecycle).
    if life.outcome_day_offset is not None:
        outcome_date = reg_date + dt.timedelta(days=life.outcome_day_offset)
        life.late_outcome = outcome_date > world.observation_cutoff.date()
    world.cover(f"kind_{kind}")
    world.case_meta[case_id] = {
        "kind": kind, "category": kd.category, "status": life.status_code,
        "converted": life.converted, "has_cs": life.has_chargesheet,
    }

    cat_code_int = ref.CATEGORY_CODE.get(category_code, 1)
    crime_no = crimeno.make(cat_code_int, district_id, unit_id, year)
    category_id = ctx.category_id[category_code]
    status_id = status_id_by_name[SR.STATUS_TO_LEGACY[life.status_code]]
    court_id = int(p[F.F_COURT]) if life.has_court else None

    brief = cases._brief_facts(rng, profile, p, ctx)
    if getattr(world, "lean", False):
        brief = brief[:160]   # trim narrative to shrink CaseMaster + FTS at scale
    world.add("CaseMaster", (
        case_id, crime_no, p[F.F_REGDATE], officer_id, unit_id, category_id,
        profile["gravity_id"], profile["crime_head_id"], profile["crime_sub_id"],
        status_id, court_id, p[F.F_INCFROM], p[F.F_INCTO], p[F.F_INFO],
        round(lat, 6), round(lon, 6), brief,
    ))

    # provenance source record
    src_id = world.next_id("SourceRecord")
    world.add("SourceRecord", (
        src_id, world.source_system["FIR_FORM"], crime_no, "case",
        Json({"crime_no": crime_no, "kind": kind}), None, 1, None, "committed"))
    world.add("CaseSource", (case_id, world.source_system["FIR_FORM"], src_id,
                             crime_no, "manual_form"))

    flags = _scenario_flags(world, mode, i, kind, profile)

    # ---- parties ----------------------------------------------------------
    accused_cpids: List[int] = []
    org_id = None
    if life.has_accused:
        accused_cpids = [world.offender_person[idx] for idx in p[F.F_OFFREFS]
                         if idx in world.offender_person]
        if p[F.F_GANG] >= 0 and p[F.F_GANG] in world.gang_org:
            org_id = world.gang_org[p[F.F_GANG]]

    # victim genders per profile (lean modes cap victims to shrink the footprint)
    vmean = profile["victims_mean"]
    vscale = 0.55 if getattr(world, "lean", False) else cfg.victim_scale
    vcap = 3 if getattr(world, "lean", False) else 6
    n_victims = min(vcap, int(rng.poisson(vmean * vscale))) if vmean > 0 else 0
    victim_genders = []
    for _ in range(n_victims):
        if profile["head"] == "Crimes Against Women":
            victim_genders.append(ref.GENDER_FEMALE)
        else:
            victim_genders.append(ref.GENDER_MALE if rng.bernoulli(0.62) else ref.GENDER_FEMALE)

    n_compl = 1 if kind != "missing_person" else 1
    if kind in ("udr",):
        n_compl = 1
    spec = PR.PartySpec(
        kind=kind, profile=profile, known_accused_cpids=accused_cpids,
        n_unknown_accused=flags["unknown_accused"] if life.has_accused else (
            1 if kind == "missing_person" and rng.bernoulli(0.0) else 0),
        victim_genders=victim_genders, n_complainants=n_compl,
        n_witnesses=int(flags["witnesses"]), informant=bool(flags["informant"]),
        guardian=bool(flags["guardian"]), org_id=org_id, district_id=district_id,
    )
    accused_refs = PR.build_case_parties(world, ib, case_id=case_id, spec=spec)

    # ---- case workflow (source/version/events) ----------------------------
    CE.emit_case(world, case_id=case_id, source_system_id=world.source_system["FIR_FORM"],
                 source_record_id=src_id, external_ref=crime_no,
                 category_code=category_code, lifecycle=life, reg_date=reg_date,
                 lat=lat, lon=lon, district_id=district_id, unit_id=unit_id)

    # ---- act/section charges (not for pure missing/udr unless converted) --
    if (profile["section_pairs"] and
            (kind in ("fir_standard", "zero_fir", "ncr", "par") or life.converted)):
        ao = so = 0
        seen = set()
        for actcode, seccode in profile["section_pairs"]:
            if (actcode, seccode) in seen:
                continue
            seen.add((actcode, seccode))
            ao += 1
            so += 1
            world.add("ActSectionAssociation", (case_id, actcode, seccode, ao, so))

    # ---- arrests + inv rows -----------------------------------------------
    arrested_cpids: List[int] = []
    if life.has_arrest and accused_refs:
        n_arr = min(len(accused_refs), 1 + int(rng.poisson(cfg.arrested_mean)))
        for ar in accused_refs[:n_arr]:
            as_id = world.next_id("ArrestSurrender")
            a_date = (reg_date + dt.timedelta(days=int(rng.g.integers(0, 90)))).isoformat()
            world.add("ArrestSurrender", (
                as_id, case_id, 1 if rng.bernoulli(0.85) else 2, a_date,
                ctx.state_id, district_id, unit_id, officer_id, court_id,
                ar.accused_master_id, True, bool(rng.bernoulli(0.05))))
            world.add("inv_arrestsurrenderaccused", (as_id, ar.accused_master_id))
            if ar.canonical_person_id:
                arrested_cpids.append(ar.canonical_person_id)

    # ---- chargesheet legacy row -------------------------------------------
    if life.has_chargesheet:
        cs_id = world.next_id("ChargesheetDetails")
        cs_dt = (reg_date + dt.timedelta(days=int(np.clip(rng.g.normal(75, 40), 20, 300)))
                 ).strftime("%Y-%m-%d %H:%M:%S+00")
        cstype = "A" if life.has_arrest and rng.bernoulli(0.9) else ("C" if rng.bernoulli(0.5) else "B")
        world.add("ChargesheetDetails", (cs_id, case_id, cs_dt, cstype, officer_id))

    world.add("Inv_OccuranceTime", (case_id,))

    # ---- evidence / statements / property / digital / financial ----------
    entity_ids = [world.person_entity[c] for c in accused_cpids if c in world.person_entity]
    if flags["ev_types"]:
        second = case_id - 1 if (flags["multi_case_link"] and case_id > 1) else None
        EV.build_case_evidence(
            world, evwriter, case_id=case_id,
            source_system_id=world.source_system["FIR_FORM"], source_record_id=src_id,
            uploader="io.ramesh", entity_ids=entity_ids, reg_date=reg_date,
            want_types=flags["ev_types"], allow_version_replace=flags["version_replace"],
            allow_conflicting_meta=flags["conflicting_meta"], second_case_id=second)

    speaker_pool = list(accused_cpids)
    if flags["statements"]:
        ST.build_case_statements(world, case_id=case_id,
                                 speaker_cpids=speaker_pool or [ib.mint_person("Witness", 1)],
                                 reg_date=reg_date, count=int(flags["statements"]),
                                 restricted=bool(flags["restricted_stmt"]))

    if flags["property"]:
        owner = accused_cpids[0] if accused_cpids else None
        PS.build_case_property(world, case_id=case_id, reg_date=reg_date,
                               item_types=flags["property"], owner_cpid=owner)

    if flags["digital_comm"] or flags["digital_loc"] or flags["digital_device"]:
        DIG.build_case_digital(
            world, ib, case_id=case_id, accused_cpids=accused_cpids or [],
            reg_date=reg_date, lon=lon, lat=lat, district_id=district_id,
            source_record_id=src_id, want_comm=int(flags["digital_comm"]),
            want_location=int(flags["digital_loc"]), want_device=bool(flags["digital_device"]))

    if flags["financial"]:
        _fin_pattern = rng.choice(["structuring", "fan_in", "layering"])
        FIN.build_case_financial(world, case_id=case_id,
                                 holder_cpids=accused_cpids or [],
                                 reg_date=reg_date, source_record_id=src_id,
                                 pattern=_fin_pattern)

    # ---- court / outcomes -------------------------------------------------
    CO.build_case_court_outcomes(world, case_id=case_id, lifecycle=life,
                                 reg_date=reg_date, court_id=court_id,
                                 arrested_cpids=arrested_cpids)

    # ---- area stats for leakage-safe labels -------------------------------
    st = world.area_stats[district_id]
    st["total"] += 1
    hour = int(p[F.F_INCFROM][11:13])
    if hour >= 21 or hour < 5:
        st["night"] += 1
    if profile["head"] == "Economic & Cyber Crime":
        st["cyber"] += 1
    if reg_date < world.observation_cutoff.date():
        st["pre"] += 1
        st["prioryear"] += 1
    else:
        st["post"] += 1

    # coverage flags for branch scenarios
    world.cover("case_with_arrest" if life.has_arrest else "case_without_arrest")
    world.cover("case_with_chargesheet" if life.has_chargesheet else "case_without_chargesheet")
    world.cover("case_with_court" if life.has_court else "case_without_court")
    if life.transferred and life.receiving_ack:
        world.cover("transfer_with_ack")
    if life.reopened:
        world.cover("reopened_case")
    if life.corrected:
        world.cover("corrected_case")
    if life.has_supplementary_cs:
        world.cover("supplementary_chargesheet")
    if kind == "missing_person":
        if life.status_code == SR.S_MISSING_RECOVERED:
            world.cover("missing_traced_recovered")
        elif life.status_code == SR.S_MISSING_UNTRACED:
            world.cover("missing_untraced")
    if kind == "udr":
        world.cover("udr_inquest")
        if life.converted:
            world.cover("udr_converted")
    if kind == "ncr" and life.converted:
        world.cover("ncr_converted")


def _build_graph(world: C.World, log=print):
    """Provenanced entity graph: nodes = canonical entities that appear as
    accused/gang; edges = co-accused (evidence-backed) + a few explicitly
    synthetic-unverified links. Linked to CanonicalEntity via true FK."""
    w = world
    rng = w.rng
    # nodes for recurring offenders that actually appeared in a case
    person_node: Dict[int, int] = {}   # canonical_person_id -> EntityID
    for cpid, cnt in w.person_case_count.items():
        if cnt <= 0:
            continue
        ent = w.person_entity.get(cpid)
        if ent is None:
            continue
        # only promote recurring offenders (label class) to graph nodes to bound size
        label = w.person_label.get(cpid, "Person")
        eid = w.next_id("EntityGraph")
        person_node[cpid] = eid
        w.add("EntityGraph", (
            eid, "person", label, "CanonicalEntity", str(ent), None, ent,
            Json({"canonical_person_id": cpid, "case_count": cnt}),
        ))
    # gang nodes
    gang_node: Dict[int, int] = {}
    for gi, oid in w.gang_org.items():
        ent = w.org_entity.get(oid)
        eid = w.next_id("EntityGraph")
        gang_node[gi] = eid
        w.add("EntityGraph", (
            eid, "gang", w.ctx.gangs[gi]["name"], "CanonicalEntity", str(ent),
            None, ent, Json({"canonical_org_id": oid})))
        w.cover("graph_gang_node")

    for cpid in person_node:
        w.cover("graph_person_node")

    # co-accused edges (evidence-backed by the shared case) — from planner offrefs
    # Rebuild co-appearance from offender pool: link offenders sharing a gang and
    # sampled co-offending. Provenance = synthetic case source record.
    edges = set()
    gang_members = w.ctx.gangs
    edge_budget = 0
    max_edges = min(getattr(w.cfg, "max_network_edges", 120000), 200000)
    for gi, g in enumerate(gang_members):
        members = [world.offender_person.get(m) for m in g["members"]]
        members = [m for m in members if m in person_node]
        for a_i in range(len(members)):
            for b_i in range(a_i + 1, len(members)):
                if edge_budget >= max_edges:
                    break
                a, b = person_node[members[a_i]], person_node[members[b_i]]
                lo, hi = (a, b) if a < b else (b, a)
                if (lo, hi) in edges or lo == hi:
                    continue
                edges.add((lo, hi))
                edge_budget += 1
                # 90% evidence-backed verified, 10% explicitly synthetic-unverified
                if rng.bernoulli(0.9):
                    w.add("NetworkEdge", (
                        lo, hi, "gang_member", 1.0, 1.0, False, 1.0, 0.8,
                        Json({"basis": "co-offending"}), None, None, "verified", None))
                    w.cover("graph_provenanced_edge")
                else:
                    w.add("NetworkEdge", (
                        lo, hi, "associate", 1.0, 1.0, False, 0.5, 0.4,
                        Json({"basis": "same_area"}), None, None,
                        "synthetic_unverified", None))
                    w.cover("graph_unverified_edge")
        # gang membership rows
        for m in g["members"]:
            cpid = world.offender_person.get(m)
            if cpid in person_node:
                w.add("GangMembership", (
                    gang_node[gi], person_node[cpid], None, cpid,
                    "core" if rng.bernoulli(0.3) else "associate", True,
                    round(float(rng.g.uniform(0.5, 0.95)), 5), "synthetic_co_offending"))
    log(f"  graph: {len(person_node):,} person nodes, {len(gang_node)} gang nodes, "
        f"{edge_budget:,} edges")
