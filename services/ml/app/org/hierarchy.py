"""Police rank / assignment -> functional role + organizational scope mapping
(Prompt 20 Part B.1).

The organizer session notes describe the command hierarchy
DGP -> IGP -> DIG -> SP -> Station Chief -> Police Officers, and require that
"each role sees only permitted data". DRISHTI keeps its SIX functional roles
(what a seat can DO) and adds this declarative mapping from a police rank /
assignment (who the seat IS in the establishment) to a functional role plus an
organizational SCOPE LEVEL (how wide the seat can see).

Everything here is pure data + pure functions (no DB, no I/O) so the mapping is
unit-testable and is the single source the API + UI surface. It is a SYNTHETIC
demo mapping; real directory/SSO/rank synchronisation is post-hackathon.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# The six functional roles kept from the existing platform (admin/permissions.py
# holds five; disaster_coordinator is the sixth, seeded idempotently in Part B).
FUNCTIONAL_ROLES = (
    "investigator", "analyst", "supervisor", "policymaker",
    "disaster_coordinator", "super_admin",
)

# Organizational scope levels, ordered BROADEST (0) -> NARROWEST. A seat may see
# its own level and everything nested below it. "assigned_case" is the tightest:
# only the specific cases assigned to that officer.
SCOPE_LEVELS = ("state", "range", "district", "subdivision", "station", "assigned_case")
SCOPE_ORDINAL = {name: i for i, name in enumerate(SCOPE_LEVELS)}


def scope_covers(holder_level: str, target_level: str) -> bool:
    """True when a seat at ``holder_level`` covers a resource classified at
    ``target_level`` (broader or equal covers narrower)."""
    return SCOPE_ORDINAL.get(holder_level, 99) <= SCOPE_ORDINAL.get(target_level, -1)


@dataclass(frozen=True)
class RankMapping:
    """One row of the synthetic rank -> role/scope catalogue."""
    key: str                 # normalized lookup key
    rank: str                # human label (establishment rank / assignment)
    abbr: str                # common abbreviation
    functional_role: str     # one of FUNCTIONAL_ROLES
    scope_level: str         # one of SCOPE_LEVELS
    note: str = ""

    def as_dict(self) -> dict:
        return {"rank": self.rank, "abbr": self.abbr,
                "functional_role": self.functional_role,
                "scope_level": self.scope_level, "note": self.note}


def _norm(text: Optional[str]) -> str:
    """Normalize a rank/designation label to a lookup key."""
    if not text:
        return ""
    out = []
    for ch in str(text).strip().lower():
        if ch.isalnum():
            out.append(ch)
        elif ch in (" ", "-", "_", "/", ".") and out and out[-1] != " ":
            out.append(" ")
    return " ".join("".join(out).split())


# ---------------------------------------------------------------------------
# The synthetic rank/assignment catalogue. Ordered senior -> junior. Mirrors the
# establishment ranks in datagen/reference.py (RANKS/DESIGNATIONS) but expressed
# as an AUTHORIZATION mapping the server enforces, not a staffing table.
# ---------------------------------------------------------------------------
_CATALOG: list[RankMapping] = [
    RankMapping("dgp", "Director General of Police", "DGP", "supervisor", "state",
                "State police head: state-wide operational oversight and approvals."),
    RankMapping("adgp", "Additional Director General of Police", "ADGP", "supervisor", "state",
                "State-wide oversight for a functional wing (e.g. Crime, L&O)."),
    RankMapping("igp", "Inspector General of Police", "IGP", "supervisor", "range",
                "Zonal/range command across several districts."),
    RankMapping("dig", "Deputy Inspector General of Police", "DIG", "supervisor", "range",
                "Range command; oversight of the districts in the range."),
    RankMapping("sp", "Superintendent of Police", "SP", "supervisor", "district",
                "District police chief: workload, approvals and oversight for one district."),
    RankMapping("dcp", "Deputy Commissioner of Police", "DCP", "supervisor", "district",
                "City-police district equivalent of the SP."),
    RankMapping("addl sp", "Additional Superintendent of Police", "Addl. SP", "supervisor", "district",
                "Assists the SP across the district."),
    RankMapping("dy sp", "Deputy Superintendent of Police", "Dy.SP", "supervisor", "subdivision",
                "Sub-divisional police officer (SDPO): oversight of a sub-division."),
    RankMapping("asp", "Assistant Superintendent of Police", "ASP", "supervisor", "subdivision",
                "IPS probationary sub-divisional officer."),
    RankMapping("acp", "Assistant Commissioner of Police", "ACP", "supervisor", "subdivision",
                "City-police sub-divisional officer."),
    RankMapping("ci", "Circle Inspector", "CI", "supervisor", "subdivision",
                "Circle inspector overseeing several stations in a circle."),
    RankMapping("sho", "Station House Officer", "SHO", "supervisor", "station",
                "Station chief: owns their police station's workload and review queue."),
    RankMapping("pi", "Police Inspector", "PI", "supervisor", "station",
                "Inspector; commonly the SHO of a station."),
    RankMapping("io", "Investigating Officer", "IO", "investigator", "assigned_case",
                "Officer investigating specific assigned cases."),
    RankMapping("psi", "Police Sub-Inspector", "PSI", "investigator", "assigned_case",
                "Sub-inspector; registers and investigates assigned FIRs."),
    RankMapping("asi", "Assistant Sub-Inspector", "ASI", "investigator", "assigned_case",
                "Assists investigation of assigned cases."),
    RankMapping("head constable", "Head Constable", "HC", "investigator", "assigned_case",
                "Assists investigation of assigned cases."),
    RankMapping("police constable", "Police Constable", "PC", "investigator", "assigned_case",
                "Assists investigation of assigned cases."),
    # Non-rank functional assignments (civilian cells / staff functions).
    RankMapping("crime analyst", "Crime Analyst (District Crime Records)", "Analyst",
                "analyst", "district",
                "District crime-records / analytics cell: aggregate + pattern analysis."),
    RankMapping("scrb", "State Crime Records Bureau / Policy Cell", "SCRB",
                "policymaker", "state",
                "Strategic aggregate-only consumer; no individual case/PII access."),
    RankMapping("ddma", "District Disaster Management Coordinator", "DDMA",
                "disaster_coordinator", "district",
                "Emergency-response coordinator for one assigned district."),
    RankMapping("system administrator", "System Administrator", "Admin",
                "super_admin", "state",
                "Platform administration: user provisioning, role assignment, governance."),
]

# key -> mapping, plus normalized full-rank-name and abbreviation aliases.
RANK_INDEX: dict[str, RankMapping] = {}
for _m in _CATALOG:
    RANK_INDEX[_m.key] = _m
    RANK_INDEX.setdefault(_norm(_m.rank), _m)
    RANK_INDEX.setdefault(_norm(_m.abbr), _m)

# Extra colloquial aliases -> canonical key.
_ALIASES = {
    "station house officer": "sho",
    "station chief": "sho",
    "inspector": "pi",
    "sub inspector": "psi",
    "investigating officer": "io",
    "superintendent of police": "sp",
    "director general": "dgp",
    "director general of police": "dgp",
    "commissioner of police": "dgp",
    "deputy commissioner": "dcp",
    "assistant commissioner": "acp",
    "circle inspector": "ci",
    "analyst": "crime analyst",
    "policy": "scrb",
    "disaster coordinator": "ddma",
    "admin": "system administrator",
}


def map_rank(rank: Optional[str], designation: Optional[str] = None) -> Optional[RankMapping]:
    """Resolve a rank (optionally refined by a designation such as SHO/IO) to its
    functional role + scope. Designation wins when it is a recognised assignment
    (e.g. a Police Inspector who is the SHO -> station-chief supervisor; a PSI who
    is the IO -> case-scoped investigator). Returns None when unrecognised."""
    for candidate in (designation, rank):
        key = _norm(candidate)
        if not key:
            continue
        if key in RANK_INDEX:
            return RANK_INDEX[key]
        if key in _ALIASES:
            return RANK_INDEX[_ALIASES[key]]
        # prefix fallback against the full normalized rank name / key, longest
        # candidate first so "deputy inspector general" beats "inspector".
        cands = sorted(_CATALOG, key=lambda c: len(_norm(c.rank)), reverse=True)
        for cat in cands:
            rank_norm = _norm(cat.rank)
            if (rank_norm.startswith(key) or key.startswith(rank_norm)
                    or key.startswith(cat.key) or cat.key.startswith(key)):
                return cat
    return None


def role_for_rank(rank: Optional[str], designation: Optional[str] = None) -> Optional[str]:
    m = map_rank(rank, designation)
    return m.functional_role if m else None


def scope_level_for_role(role: str) -> str:
    """Default (broadest) scope level a functional role may hold when no rank
    refinement is available. Used as a fallback in scope derivation."""
    return {
        "super_admin": "state",
        "policymaker": "state",
        "supervisor": "district",
        "analyst": "district",
        "disaster_coordinator": "district",
        "investigator": "assigned_case",
    }.get(role, "assigned_case")


def catalog() -> list[dict]:
    """The full synthetic rank -> role/scope mapping (surfaced by the API/UI)."""
    return [m.as_dict() for m in _CATALOG]
