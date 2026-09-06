"""Police rank / assignment -> functional role + organizational scope mapping
(Prompt 20 Part B.1).

The organizer session notes describe the command hierarchy
DGP -> IGP -> DIG -> SP -> Station Chief -> Police Officers, and require that
"each role sees only permitted data". DRISHTI's functional roles (what a seat
can DO) are the command seats in ``app/roles.py``; this module maps a police
rank / assignment (who the seat IS in the establishment) to one of those roles
plus an organizational SCOPE LEVEL (how wide the seat can see).

Everything here is pure data + pure functions (no DB, no I/O) so the mapping is
unit-testable and is the single source the API + UI surface. It is a SYNTHETIC
demo mapping; real directory/SSO/rank synchronisation is post-hackathon.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..roles import FUNCTIONAL_ROLES  # noqa: F401 — re-exported (canonical set)
from .. import roles as _roles

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
    """One row of the rank -> role/scope catalogue.

    ``scope_level`` is the ordered GEOGRAPHIC ladder that :func:`scope_covers`
    reasons over. ``scope_type`` is what the seat actually carries and is not a
    rung on that ladder: `wing` is state-wide geography narrowed by crime head,
    and `commissionerate` is a peer of `district` rather than a level of its own.
    Keeping both means containment logic stays ordered while the seat model stays
    honest about ADGP-vs-DIG and SP-vs-CP.
    """
    key: str                 # normalized lookup key
    rank: str                # human label (establishment rank / assignment)
    abbr: str                # common abbreviation
    functional_role: str     # one of FUNCTIONAL_ROLES
    scope_level: str         # one of SCOPE_LEVELS (geographic ladder)
    note: str = ""
    scope_type: str = ""     # seat scope type; defaults to scope_level

    def __post_init__(self):
        if not self.scope_type:
            object.__setattr__(self, "scope_type", self.scope_level)

    def as_dict(self) -> dict:
        return {"rank": self.rank, "abbr": self.abbr,
                "functional_role": self.functional_role,
                "scope_level": self.scope_level,
                "scope_type": self.scope_type, "note": self.note}


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
    RankMapping("dgp", "Director General of Police", "DGP", "dgp_state_command", "state",
                "State police head: state-wide operational oversight and approvals."),
    # ADGP heads a FUNCTIONAL wing; IGP/DIG command a GEOGRAPHIC range. Same
    # application role, different scope type — the distinction the previous single
    # `adgp_igp_range` role could not express.
    RankMapping("adgp", "Additional Director General of Police", "ADGP",
                "senior_command", "state",
                "State-wide oversight for a functional wing (e.g. Crime, L&O).",
                scope_type="wing"),
    RankMapping("igp", "Inspector General of Police", "IGP", "senior_command", "range",
                "Zonal/range command across several districts.", scope_type="range"),
    RankMapping("dig", "Deputy Inspector General of Police", "DIG",
                "senior_command", "range",
                "Range command; oversight of the districts in the range.",
                scope_type="range"),
    RankMapping("sp", "Superintendent of Police", "SP", "district_command", "district",
                "District police chief: workload, approvals and oversight for one district.",
                scope_type="district"),
    RankMapping("cp", "Commissioner of Police", "CP", "district_command", "district",
                "City Commissionerate chief; reports outside the range hierarchy.",
                scope_type="commissionerate"),
    RankMapping("dcp", "Deputy Commissioner of Police", "DCP", "district_command", "district",
                "City-police district equivalent of the SP.", scope_type="district"),
    RankMapping("addl sp", "Additional Superintendent of Police", "Addl. SP",
                "district_command", "district",
                "Assists the SP across the district.", scope_type="district"),
    # The sub-division tier has no Unit rows behind it (UnitType 2/3 are
    # uninstantiated), so these seats resolve to district command until it exists.
    RankMapping("dy sp", "Deputy Superintendent of Police", "Dy.SP",
                "district_command", "subdivision",
                "Sub-divisional police officer (SDPO). Sub-division is not yet modelled, "
                "so the seat is issued at district scope.", scope_type="district"),
    RankMapping("asp", "Assistant Superintendent of Police", "ASP",
                "district_command", "subdivision",
                "IPS probationary sub-divisional officer.", scope_type="district"),
    RankMapping("acp", "Assistant Commissioner of Police", "ACP",
                "district_command", "subdivision",
                "City-police sub-divisional officer.", scope_type="district"),
    RankMapping("ci", "Circle Inspector", "CI", "district_command", "subdivision",
                "Circle inspector overseeing several stations in a circle.",
                scope_type="district"),
    RankMapping("sho", "Station House Officer", "SHO", "sho", "station",
                "Station chief: owns their police station's workload and review queue."),
    RankMapping("pi", "Police Inspector", "PI", "sho", "station",
                "Inspector; commonly the SHO of a station."),
    RankMapping("io", "Investigating Officer", "IO", "investigating_officer", "assigned_case",
                "Officer investigating specific assigned cases."),
    RankMapping("psi", "Police Sub-Inspector", "PSI", "investigating_officer", "assigned_case",
                "Sub-inspector; registers and investigates assigned FIRs."),
    RankMapping("asi", "Assistant Sub-Inspector", "ASI", "investigating_officer", "assigned_case",
                "Assists investigation of assigned cases."),
    RankMapping("head constable", "Head Constable", "HC", "investigating_officer", "assigned_case",
                "Assists investigation of assigned cases."),
    RankMapping("police constable", "Police Constable", "PC", "investigating_officer",
                "assigned_case", "Assists investigation of assigned cases."),
    # Staff cells are now ADGP FUNCTIONAL WINGS rather than roles of their own, so
    # they map to senior_command at wing scope: state-wide reach, narrowed to the
    # wing's crime heads.
    RankMapping("crime analyst", "Crime Analyst (State Crime Records Bureau)", "Analyst",
                "senior_command", "state",
                "Crime & Technical Services wing: aggregate and pattern analysis.",
                scope_type="wing"),
    RankMapping("scrb", "State Crime Records Bureau", "SCRB",
                "senior_command", "state",
                "Crime & Technical Services wing: strategic trends and forecasting.",
                scope_type="wing"),
    RankMapping("cyber cell", "Cyber Crime Police Station / CEN Cell", "CEN",
                "senior_command", "state",
                "Internal Security & Cyber wing: money trail, devices and accounts.",
                scope_type="wing"),
    RankMapping("traffic", "Traffic Police Command", "Traffic",
                "senior_command", "state",
                "Traffic & Road Safety wing: road-safety hotspots and enforcement load.",
                scope_type="wing"),
    RankMapping("intelligence", "State Intelligence Wing", "INT",
                "senior_command", "state",
                "Intelligence wing: actionable intelligence across the state.",
                scope_type="wing"),
    RankMapping("system administrator", "System Administrator", "Admin",
                "system_admin", "state",
                "Platform administration: seats, roles, UI visibility and governance.",
                scope_type="platform"),
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
    "cyber": "cyber cell",
    "cen": "cyber cell",
    "cyber crime": "cyber cell",
    "traffic police": "traffic",
    "traffic command": "traffic",
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
    return _roles.scope_level_for_role(role)


def catalog() -> list[dict]:
    """The full synthetic rank -> role/scope mapping (surfaced by the API/UI)."""
    return [m.as_dict() for m in _CATALOG]
