"""FIR planning (single-process) and child expansion (parallel).

Design
------
1. ``plan_firs`` runs in the main process. It draws every FIR's scalar fields
   from the crime-type behavioural profiles (district -> crime type -> date ->
   hour -> station -> officer -> disposition) and assigns a globally-unique,
   18-digit ``CrimeNo`` using per-(station, category, year) serial counters.
   It also decides the *criminal composition* (which recurring offenders / gang
   are involved) so the intelligence layer can rebuild co-offending networks.

2. ``load_casemaster`` writes CaseMaster in the main process (100k rows; the
   BEFORE-INSERT trigger validates CrimeNo and derives CaseNo).

3. ``run_chunk`` runs in worker processes. Each worker owns a disjoint id block
   (chunk_id * ID_BLOCK) and expands children (accused, victims, complainants,
   act-sections, arrests, chargesheets, occurrence rows) for its slice of FIRs,
   then COPY-loads them in FK-dependency order inside one transaction.

Per-FIR content is generated from an RNG seeded by (seed, case_id), so the data
is reproducible for a given seed regardless of the number of workers (only the
arbitrary surrogate id values depend on chunking).
"""
from __future__ import annotations

import datetime as dt
from typing import List, Tuple

import numpy as np

from . import boundaries as B
from . import reference as ref
from .config import GenConfig, ID_BLOCK
from .context import Context
from .db import connect, copy_rows
from .names import person_name, phone_number
from .rng import RNG

# ---- FIR plan tuple layout --------------------------------------------------
(F_ID, F_CRIMENO, F_REGDATE, F_OFFICER, F_STATION, F_DISTRICT, F_CATEGORY,
 F_GRAVITY, F_HEAD, F_SUB, F_STATUS, F_COURT, F_INCFROM, F_INCTO, F_INFO,
 F_LAT, F_LON, F_PROFILE, F_GANG, F_OFFREFS, F_NONETIME, F_ARREST,
 F_CHARGESHEET) = range(23)


# ===========================================================================
# Planning
# ===========================================================================
class Planner:
    def __init__(self, cfg: GenConfig, ctx: Context):
        self.cfg = cfg
        self.ctx = ctx
        self.rng = RNG(cfg.seed * 31 + 7)

        # Real-geography incident placement. Each station carries its SHO
        # jurisdiction ring; rebuild it into a prepared Region once and cache a
        # clustering sigma so incidents sit near the station yet inside the ring.
        self.bnd = B.load_boundaries()
        self._sho_cache: dict = {}
        self._sho_sigma: dict = {}

        # date axis
        self.dates = _date_range(cfg.start_date, cfg.end_date)
        self.date_dow = np.array([d.weekday() for d in self.dates])
        self.date_mon = np.array([d.month for d in self.dates])

        # district selection cdf (population weighted)
        dw = np.array(ctx.district_weights, dtype=float)
        self.dist_cdf = np.cumsum(dw / dw.sum())

        # per-district crime-profile cdf (base weight * tag affinity)
        base_w = np.array(ctx.crime_weights, dtype=float)
        self.prof_cdf = []
        for d in ctx.districts:
            w = base_w.copy()
            for pi, p in enumerate(ctx.crime_profiles):
                mult = 1.0
                for tag, m in p["affinity"].items():
                    if tag in d["tags"]:
                        mult *= m
                w[pi] *= mult
            self.prof_cdf.append(np.cumsum(w / w.sum()))

        # per-profile date cdf and hour cdf
        self.date_cdf = []
        self.hour_cdf = []
        for p in ctx.crime_profiles:
            mon_tpl = np.array(ref.MONTH_TEMPLATES[p["season"]])
            dow_tpl = np.array(ref.WEEKDAY_TEMPLATES[p["weekday"]])
            dwt = mon_tpl[self.date_mon] * dow_tpl[self.date_dow]
            self.date_cdf.append(np.cumsum(dwt / dwt.sum()))
            hw = np.array(ref.HOUR_TEMPLATES[p["hours"]], dtype=float)
            self.hour_cdf.append(np.cumsum(hw / hw.sum()))

        # offenders grouped by specialty (offense_budget weighted -> recurrence)
        self.spec_idx: dict = {}
        self.spec_cdf: dict = {}
        buckets: dict = {}
        for idx, o in enumerate(ctx.offenders):
            buckets.setdefault(o["specialty"], []).append(idx)
        all_idx = np.arange(len(ctx.offenders))
        all_budget = np.array([o["offense_budget"] for o in ctx.offenders], float)
        self._all_idx = all_idx
        self._all_cdf = np.cumsum(all_budget / all_budget.sum()) if len(all_idx) else None
        for pi in range(len(ctx.crime_profiles)):
            ids = np.array(buckets.get(pi, []), dtype=int)
            if len(ids) == 0:
                self.spec_idx[pi] = all_idx
                self.spec_cdf[pi] = self._all_cdf
            else:
                b = np.array([ctx.offenders[i]["offense_budget"] for i in ids], float)
                self.spec_idx[pi] = ids
                self.spec_cdf[pi] = np.cumsum(b / b.sum())

        # gangs by specialty
        self.gang_by_spec: dict = {}
        for gi, g in enumerate(ctx.gangs):
            self.gang_by_spec.setdefault(g["specialty"], []).append(gi)

        # category / status cdfs
        self.cat_names = ref.CASE_CATEGORIES
        self.cat_cdf = np.cumsum(np.array(ref.CATEGORY_WEIGHTS) /
                                 sum(ref.CATEGORY_WEIGHTS))
        self.crimeno_serial: dict = {}

    # ---- helpers -----------------------------------------------------------
    def _pick(self, cdf) -> int:
        return int(np.searchsorted(cdf, self.rng.g.random()))

    def _pick_offender(self, pi: int) -> int:
        cdf = self.spec_cdf[pi]
        ids = self.spec_idx[pi]
        return int(ids[int(np.searchsorted(cdf, self.rng.g.random()))])

    def _incident_point(self, station: dict) -> Tuple[float, float]:
        """One incident coordinate: clustered around the station but guaranteed
        inside its SHO jurisdiction (hence on real Karnataka land). Returns
        ``(lat, lon)``."""
        sid = station["id"]
        region = self._sho_cache.get(sid)
        if region is None:
            ring = station.get("sho_ring")
            if ring and len(ring) >= 4:
                region = B.region_from_ring(f"sho-{sid}", ring)
            else:  # defensive: fall back to the whole district
                d = self.ctx.districts[station["district_idx"]]
                region = self.bnd.district(d["name"])
            self._sho_cache[sid] = region
            self._sho_sigma[sid] = B.sigma_for_area(region.area)
        lon, lat = B.sample_near(region, station["lon"], station["lat"],
                                 self._sho_sigma[sid], self.rng.g)
        return lat, lon

    def plan(self) -> List[tuple]:
        cfg, ctx, rng = self.cfg, self.ctx, self.rng
        plans: List[tuple] = []
        status_map = _status_index_map(ctx)

        for case_id in range(1, cfg.n_firs + 1):
            di = self._pick(self.dist_cdf)
            district = ctx.districts[di]
            pi = self._pick(self.prof_cdf[di])
            profile = ctx.crime_profiles[pi]

            date_i = self._pick(self.date_cdf[pi])
            inc_date = self.dates[date_i]
            hour = self._pick(self.hour_cdf[pi])
            minute = int(rng.g.integers(0, 60))
            inc_from = dt.datetime(inc_date.year, inc_date.month, inc_date.day,
                                   hour, minute)
            dur_min = int(rng.clipped_gaussian(40, 60, 1, 600))
            inc_to = inc_from + dt.timedelta(minutes=dur_min)
            report_delay_h = float(rng.g.exponential(18.0))
            info_dt = inc_from + dt.timedelta(hours=report_delay_h)
            reg_date = info_dt.date()
            if reg_date > cfg.end_date:
                reg_date = cfg.end_date

            # station within district (uniform over jurisdiction geography)
            st_list = ctx.stations_by_district[di]
            st_index = st_list[int(rng.g.integers(0, len(st_list)))]
            station = ctx.stations[st_index]
            station_id = station["id"]
            # incident coordinate inside the station's SHO jurisdiction (real land)
            lat, lon = self._incident_point(station)

            # officer (zipf -> some officers handle many FIRs)
            officers = ctx.officers_by_station[station_id]
            officer_id = officers[_zipf_index(rng, len(officers))]

            # category / court / gravity
            cat_name = self.cat_names[int(np.searchsorted(self.cat_cdf, rng.g.random()))]
            category_id = ctx.category_id[cat_name]
            courts = ctx.courts_by_district[di]
            court_id = int(courts[int(rng.g.integers(0, len(courts)))])
            gravity_id = profile["gravity_id"]

            # disposition
            has_arrest = bool(rng.bernoulli(min(0.95, profile["arrest"])))
            has_cs = bool(rng.bernoulli(cfg.chargesheet_rate))
            status_id = _pick_status(rng, status_map, has_arrest, has_cs)

            # criminal composition
            gang_idx = -1
            offrefs: list = []
            n_accused = int(rng.poisson(profile["accused_mean"] * cfg.accused_scale)) \
                if profile["accused_mean"] > 0 else 0
            n_accused = min(n_accused, 40)
            if n_accused > 0 and rng.bernoulli(profile["gang"]):
                cand = self.gang_by_spec.get(pi) or (list(range(len(ctx.gangs))) or None)
                if cand:
                    gang_idx = int(rng.choice(cand))
                    members = ctx.gangs[gang_idx]["members"]
                    take = min(n_accused, len(members))
                    if take > 0:
                        offrefs = list(rng.choice(members, size=take, replace=False)) \
                            if take < len(members) else list(members)[:take]
            if not offrefs:
                for _ in range(n_accused):
                    if rng.bernoulli(profile["repeat"]) and len(ctx.offenders):
                        offrefs.append(self._pick_offender(pi))
            offrefs = offrefs[:n_accused]
            n_onetime = max(0, n_accused - len(offrefs))

            crime_no = self._crimeno(cat_name, district["id"], station_id,
                                     inc_from.year)

            plans.append((
                case_id, crime_no, reg_date.isoformat(), officer_id, station_id,
                district["id"], category_id, gravity_id, profile["crime_head_id"],
                profile["crime_sub_id"], status_id, court_id,
                _ts(inc_from), _ts(inc_to), _ts(info_dt), round(lat, 6),
                round(lon, 6), pi, gang_idx, tuple(int(x) for x in offrefs),
                n_onetime, has_arrest, has_cs,
            ))
        return plans

    def _crimeno(self, cat_name: str, district_id: int, unit_id: int, year: int) -> str:
        ccode = self.ctx.category_code.get(cat_name, 1)
        key = (unit_id, ccode, year)
        serial = self.crimeno_serial.get(key, 0) + 1
        self.crimeno_serial[key] = serial
        return f"{ccode:1d}{district_id:04d}{unit_id:04d}{year:04d}{serial:05d}"


# ===========================================================================
# CaseMaster load (main process)
# ===========================================================================
CASEMASTER_COLS = [
    "CaseMasterID", "CrimeNo", "CrimeRegisteredDate", "PolicePersonID",
    "PoliceStationID", "CaseCategoryID", "GravityOffenceID", "CrimeMajorHeadID",
    "CrimeMinorHeadID", "CaseStatusID", "CourtID", "IncidentFromDate",
    "IncidentToDate", "InfoReceivedPSDate", "latitude", "longitude", "BriefFacts",
]


def load_casemaster(cur, cfg: GenConfig, ctx: Context, plans: List[tuple]) -> None:
    def rows():
        for p in plans:
            profile = ctx.crime_profiles[p[F_PROFILE]]
            seed = (cfg.seed, p[F_ID])
            bf = _brief_facts(RNG(seed), profile, p, ctx)
            yield (p[F_ID], p[F_CRIMENO], p[F_REGDATE], p[F_OFFICER], p[F_STATION],
                   p[F_CATEGORY], p[F_GRAVITY], p[F_HEAD], p[F_SUB], p[F_STATUS],
                   p[F_COURT], p[F_INCFROM], p[F_INCTO], p[F_INFO], p[F_LAT],
                   p[F_LON], bf)
    copy_rows(cur, "CaseMaster", CASEMASTER_COLS, rows(), chunk=cfg.copy_chunk)


# ===========================================================================
# Child expansion (worker process)
# ===========================================================================
def run_chunk(chunk_id: int, plans: List[tuple], cfg: GenConfig,
              ctx: Context, dsn: str) -> dict:
    """Expand + COPY all children for a chunk of FIRs. Returns row counts."""
    data = build_children(chunk_id, plans, cfg, ctx)
    return _copy_children(dsn, cfg, data)


def build_children(chunk_id: int, plans: List[tuple], cfg: GenConfig,
                   ctx: Context) -> dict:
    """Expand all child rows for a chunk of FIRs (no DB access)."""
    base = chunk_id * ID_BLOCK
    accused_id = base
    victim_id = base
    compl_id = base
    arrest_id = base
    cs_id = base

    accused_rows, victim_rows, compl_rows = [], [], []
    actsec_rows, arrest_rows, inv_rows, cs_rows, occ_rows = [], [], [], [], []

    for p in plans:
        case_id = p[F_ID]
        profile = ctx.crime_profiles[p[F_PROFILE]]
        rng = RNG((cfg.seed, case_id))

        # ---- Accused ------------------------------------------------------
        accused_local: List[Tuple[int, int]] = []  # (accused_id, gender)
        seq = 0
        for off_idx in p[F_OFFREFS]:
            o = ctx.offenders[off_idx]
            accused_id += 1
            seq += 1
            age = int(np.clip(o["age_base"] + rng.g.integers(-1, 4), 10, 80))
            accused_rows.append((accused_id, case_id, o["name"], age,
                                 o["gender"], f"A{seq}"))
            accused_local.append((accused_id, o["gender"]))
        for _ in range(p[F_NONETIME]):
            accused_id += 1
            seq += 1
            gender = ref.GENDER_MALE if rng.bernoulli(0.9) else ref.GENDER_FEMALE
            mu, sigma = profile["age"]
            age = int(np.clip(rng.g.normal(mu or 30, sigma or 9), 12, 80))
            accused_rows.append((accused_id, case_id, person_name(rng, gender),
                                 age, gender, f"A{seq}"))
            accused_local.append((accused_id, gender))

        # ---- Victims ------------------------------------------------------
        vmean = profile["victims_mean"]
        n_victims = int(rng.poisson(vmean * cfg.victim_scale)) if vmean > 0 else 0
        n_victims = min(n_victims, 30)
        for _ in range(n_victims):
            victim_id += 1
            gender = _victim_gender(rng, profile)
            age = int(np.clip(rng.g.normal(30, 14), 1, 95))
            is_police = "1" if rng.bernoulli(0.02) else "0"
            victim_rows.append((victim_id, case_id, person_name(rng, gender),
                                age, gender, is_police))

        # ---- Complainants -------------------------------------------------
        n_compl = max(0, int(rng.poisson(cfg.complainants_per_fir_mean)))
        n_compl = min(n_compl, 5)
        if n_compl == 0 and not profile["sub"].startswith("Missing"):
            n_compl = 1  # most FIRs have at least one complainant
        for _ in range(n_compl):
            compl_id += 1
            gender = ref.GENDER_MALE if rng.bernoulli(0.6) else ref.GENDER_FEMALE
            age = int(np.clip(rng.g.normal(38, 13), 15, 90))
            occ = int(rng.choice(ctx.occupation_ids))
            rel = int(ctx.religion_ids[int(rng.weighted_index(
                np.array(ctx.religion_weights)))])
            caste = int(rng.choice(ctx.caste_ids))
            compl_rows.append((compl_id, case_id, person_name(rng, gender), age,
                               occ, rel, caste, gender))

        # ---- Act / Section charges ---------------------------------------
        seen_pairs = set()
        ao, so = 0, 0
        for actcode, seccode in profile["section_pairs"]:
            if (actcode, seccode) in seen_pairs:
                continue
            seen_pairs.add((actcode, seccode))
            ao += 1
            so += 1
            actsec_rows.append((case_id, actcode, seccode, ao, so))

        # ---- Arrests ------------------------------------------------------
        if p[F_ARREST] and accused_local:
            n_arr = min(len(accused_local),
                        1 + int(rng.poisson(cfg.arrested_mean)))
            arrested = accused_local[:n_arr]
            io_officer = _worker_io_officer(rng, ctx, p[F_STATION])
            for (acc_id, _g) in arrested:
                arrest_id += 1
                a_date = _arrest_date(rng, p)
                a_type = 1 if rng.bernoulli(0.85) else 2  # arrest vs surrender
                arrest_rows.append((
                    arrest_id, case_id, a_type, a_date, ctx.state_id,
                    p[F_DISTRICT], p[F_STATION], io_officer, p[F_COURT], acc_id,
                    True, bool(rng.bernoulli(0.05))))
                inv_rows.append((arrest_id, acc_id))

        # ---- Chargesheet --------------------------------------------------
        if p[F_CHARGESHEET]:
            cs_id += 1
            cs_dt = _chargesheet_ts(rng, p)
            cstype = "A" if p[F_ARREST] and rng.bernoulli(0.9) else \
                ("C" if rng.bernoulli(0.5) else "B")
            cs_rows.append((cs_id, case_id, cs_dt, cstype, p[F_OFFICER]))

        # ---- 1:1 occurrence row ------------------------------------------
        occ_rows.append((case_id,))

    # Safety: ensure this chunk's ids never spilled into the next chunk's block.
    span = max(accused_id, victim_id, compl_id, arrest_id, cs_id) - base
    if span > ID_BLOCK:
        raise RuntimeError(
            f"Chunk {chunk_id} produced {span} rows in one table, exceeding "
            f"ID_BLOCK={ID_BLOCK}. Increase --workers or raise ID_BLOCK.")

    return {
        "accused": accused_rows, "victims": victim_rows,
        "complainants": compl_rows, "act_sections": actsec_rows,
        "arrests": arrest_rows, "inv": inv_rows, "chargesheets": cs_rows,
        "occurrences": occ_rows,
    }


def _copy_children(dsn, cfg, data: dict) -> dict:
    accused_rows = data["accused"]
    victim_rows = data["victims"]
    compl_rows = data["complainants"]
    actsec_rows = data["act_sections"]
    arrest_rows = data["arrests"]
    inv_rows = data["inv"]
    cs_rows = data["chargesheets"]
    occ_rows = data["occurrences"]
    conn = connect(dsn)
    try:
        cur = conn.cursor()
        copy_rows(cur, "Accused",
                  ["AccusedMasterID", "CaseMasterID", "AccusedName", "AgeYear",
                   "GenderID", "PersonID"], accused_rows, chunk=cfg.copy_chunk)
        copy_rows(cur, "Victim",
                  ["VictimMasterID", "CaseMasterID", "VictimName", "AgeYear",
                   "GenderID", "VictimPolice"], victim_rows, chunk=cfg.copy_chunk)
        copy_rows(cur, "ComplainantDetails",
                  ["ComplainantID", "CaseMasterID", "ComplainantName", "AgeYear",
                   "OccupationID", "ReligionID", "CasteID", "GenderID"],
                  compl_rows, chunk=cfg.copy_chunk)
        copy_rows(cur, "ActSectionAssociation",
                  ["CaseMasterID", "ActID", "SectionID", "ActOrderID",
                   "SectionOrderID"], actsec_rows, chunk=cfg.copy_chunk)
        copy_rows(cur, "ArrestSurrender",
                  ["ArrestSurrenderID", "CaseMasterID", "ArrestSurrenderTypeID",
                   "ArrestSurrenderDate", "ArrestSurrenderStateId",
                   "ArrestSurrenderDistrictId", "PoliceStationID", "IOID",
                   "CourtID", "AccusedMasterID", "IsAccused",
                   "IsComplainantAccused"], arrest_rows, chunk=cfg.copy_chunk)
        copy_rows(cur, "inv_arrestsurrenderaccused",
                  ["ArrestSurrenderID", "AccusedMasterID"], inv_rows,
                  chunk=cfg.copy_chunk)
        copy_rows(cur, "ChargesheetDetails",
                  ["CSID", "CaseMasterID", "csdate", "cstype", "PolicePersonID"],
                  cs_rows, chunk=cfg.copy_chunk)
        copy_rows(cur, "Inv_OccuranceTime", ["CaseMasterID"], occ_rows,
                  chunk=cfg.copy_chunk)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return {
        "accused": len(accused_rows), "victims": len(victim_rows),
        "complainants": len(compl_rows), "act_sections": len(actsec_rows),
        "arrests": len(arrest_rows), "chargesheets": len(cs_rows),
        "occurrences": len(occ_rows),
    }


# ===========================================================================
# small helpers
# ===========================================================================
def _date_range(start: dt.date, end: dt.date) -> List[dt.date]:
    n = (end - start).days + 1
    return [start + dt.timedelta(days=i) for i in range(n)]


def _ts(d: dt.datetime) -> str:
    return d.strftime("%Y-%m-%d %H:%M:%S+00")


def _zipf_index(rng: RNG, n: int, exponent: float = 1.1) -> int:
    if n <= 1:
        return 0
    w = (np.arange(1, n + 1, dtype=float)) ** (-exponent)
    cdf = np.cumsum(w / w.sum())
    return int(np.searchsorted(cdf, rng.g.random()))


def _status_index_map(ctx: Context) -> dict:
    return {name: ctx.status_ids[i] for i, name in enumerate(ref.CASE_STATUSES)}


def _pick_status(rng: RNG, smap: dict, has_arrest: bool, has_cs: bool) -> int:
    if has_cs:
        choices = [("Charge Sheeted", 5), ("Pending Trial", 3),
                   ("Closed - Convicted", 1), ("Closed - Acquitted", 1)]
    elif has_arrest:
        choices = [("Under Investigation", 5), ("Pending Trial", 3),
                   ("Charge Sheeted", 2)]
    else:
        choices = [("Under Investigation", 5), ("Undetected / B-Report", 3),
                   ("False / C-Report", 1), ("Transferred", 1)]
    names = [c[0] for c in choices]
    w = np.array([c[1] for c in choices], float)
    idx = int(np.searchsorted(np.cumsum(w / w.sum()), rng.g.random()))
    return smap[names[idx]]


def _victim_gender(rng: RNG, profile: dict) -> int:
    if profile["head"] == "Crimes Against Women":
        return ref.GENDER_FEMALE
    return ref.GENDER_MALE if rng.bernoulli(0.62) else ref.GENDER_FEMALE


def _worker_io_officer(rng: RNG, ctx: Context, station_id: int) -> int:
    officers = ctx.officers_by_station.get(station_id) or [1]
    return int(officers[_zipf_index(rng, len(officers))])


def _arrest_date(rng: RNG, p: tuple) -> str:
    reg = dt.date.fromisoformat(p[F_REGDATE])
    d = reg + dt.timedelta(days=int(rng.g.integers(0, 90)))
    return d.isoformat()


def _chargesheet_ts(rng: RNG, p: tuple) -> str:
    reg = dt.date.fromisoformat(p[F_REGDATE])
    d = reg + dt.timedelta(days=int(rng.clipped_gaussian(75, 40, 20, 300)))
    return d.strftime("%Y-%m-%d %H:%M:%S+00")


# ---- brief facts (natural-language MO summary) ------------------------------
_LOC_BY_TAG = {
    "metro": ["a tech park", "an apartment complex", "a shopping mall",
              "a metro station", "a busy junction"],
    "coastal": ["the fishing harbour", "a beachside road", "a port area"],
    "border": ["a highway checkpoint", "a border village", "a transport hub"],
    "rural": ["an agricultural field", "a village road", "a weekly market"],
    "default": ["a market area", "a bus stand", "a residential street",
                "a railway station", "a public place"],
}
_WEAPONS = ["a knife", "a machete", "an iron rod", "a wooden club",
            "a country-made pistol", "bare hands", "a sharp weapon"]


def _brief_facts(rng: RNG, profile: dict, p: tuple, ctx: Context) -> str:
    sub = profile["sub"]
    hour = int(p[F_INCFROM][11:13])
    tod = ("night" if hour >= 21 or hour < 5 else
           "early morning" if hour < 8 else
           "afternoon" if 12 <= hour < 17 else
           "evening" if hour >= 17 else "morning")
    di = p[F_DISTRICT] - 1
    tags = ctx.districts[di]["tags"] if 0 <= di < len(ctx.districts) else []
    locs = None
    for t in tags:
        if t in _LOC_BY_TAG:
            locs = _LOC_BY_TAG[t]
            break
    loc = rng.choice(locs or _LOC_BY_TAG["default"])
    parts = [f"On {p[F_REGDATE]}, a case of {sub.lower()} was reported near {loc} during the {tod}."]
    if profile["alcohol"] > 0.4 and rng.bernoulli(profile["alcohol"]):
        parts.append("The accused was reportedly under the influence of alcohol.")
    if sub in ("Murder", "Attempt to Murder", "Grievous Hurt", "Robbery", "Dacoity"):
        parts.append(f"The assailant(s) allegedly used {rng.choice(_WEAPONS)}.")
    if profile["multi_victim"]:
        parts.append("Multiple victims were affected in the incident.")
    if profile["head"] == "Economic & Cyber Crime":
        parts.append(f"The complainant reported financial loss after contact from {phone_number(rng)}.")
    if p[F_GANG] >= 0:
        parts.append("Preliminary inquiry suggests involvement of an organised group.")
    return " ".join(parts)[:900]
