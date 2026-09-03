"""NL->SQL planner (doc 02 §6). Pluggable behind an interface.

  * LLMPlanner    — an OpenAI-compatible chat model (any base_url), given the
                    REAL role-scoped schema + the police glossary; it returns a
                    single read-only SELECT or a clarifying question, as JSON.
  * FallbackPlanner — a deterministic, role-aware intent matcher used when no LLM
                    is configured, so Ask DRISHTI works offline. It emits safe,
                    parameter-escaped SELECTs for common intents and asks a
                    clarifying question otherwise (never guesses).

Whatever produces the SQL, the executor + scope guard enforce read-only + role
scope independently — the planner is never trusted.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Optional

from ..cases import casedata
from ..config import get_settings
from .executor import authorize_case_aggregate
from .glossary import glossary_text
from .schema import requires_aggregate, schema_text


@dataclass
class Turn:
    sender: str          # user | assistant
    text: str


@dataclass
class Plan:
    sql: Optional[str] = None
    needs_clarification: bool = False
    clarifying_question: Optional[str] = None
    intent: str = "unknown"
    confidence: float = 0.6
    language: str = "en"
    source: str = "fallback"
    filters: dict = field(default_factory=dict)   # extracted entities (for memory/UX)


# ===========================================================================
# Deterministic offline planner
# ===========================================================================
def _lit(s: str) -> str:
    """Safely embed a string literal (single-quote escaped)."""
    return "'" + s.replace("'", "''") + "'"


# crime keyword -> (target, ILIKE pattern). target: 'group' (CrimeHead) or 'sub'
# (CrimeSubHead). Each pattern matches English, Kannada script AND common
# transliterated (Latin-script Kannada) forms — meaning, not literal substitution.
_CRIME_KEYWORDS: list[tuple[str, str, str]] = [
    (r"cyber|ಸೈಬರ್|saibar", "group", "%cyber%"),
    (r"economic", "group", "%economic%"),
    (r"vehicle\s*theft|ವಾಹನ|vahana", "sub", "%vehicle theft%"),
    (r"burglar|ಮನೆಗಳ್ಳತನ|manegall?atana", "sub", "%burglar%"),
    (r"theft|ಕಳ್ಳತನ|kalla?tana|kalathana", "sub", "%theft%"),
    (r"robbery|ದರೋಡೆ|darod[ei]", "sub", "%robbery%"),
    (r"dacoit|ಡಕಾಯಿತಿ|dakayiti", "sub", "%dacoit%"),
    (r"murder|homicide|ಕೊಲೆ|kole", "sub", "%murder%"),
    (r"assault|hurt|ಹಲ್ಲೆ|halle", "sub", "%assault%"),
    (r"rape|sexual|ಅತ್ಯಾಚಾರ|atyachara", "sub", "%rape%"),
    (r"kidnap|abduct|ಅಪಹರಣ|apaharana", "sub", "%kidnap%"),
    (r"narcotic|drug|ಮಾದಕ|madaka", "sub", "%narcotic%"),
    (r"riot|ಗಲಭೆ|galabhe", "sub", "%riot%"),
    (r"extortion|ಸುಲಿಗೆ|sulige", "sub", "%extortion%"),
    (r"cheat|fraud|ವಂಚನೆ|vanchane", "sub", "%cheat%"),
    (r"missing|ನಾಪತ್ತೆ|napatte", "sub", "%missing%"),
]

# Common Kannada district cues -> canonical DistrictName values.
_KN_DISTRICTS = {
    "ಬೆಂಗಳೂರ": "Bengaluru City", "ಮೈಸೂರ": "Mysuru", "ಕಲಬುರಗಿ": "Kalaburagi",
    "ಬಳ್ಳಾರಿ": "Ballari", "ಮಂಗಳೂರ": "Dakshina Kannada", "ಹುಬ್ಬಳ್ಳಿ": "Dharwad",
    "ಬೆಳಗಾವಿ": "Belagavi", "ತುಮಕೂರು": "Tumakuru", "ಶಿವಮೊಗ್ಗ": "Shivamogga",
    "ದಾವಣಗೆರೆ": "Davanagere", "ವಿಜಯಪುರ": "Vijayapura", "ಉಡುಪಿ": "Udupi",
    "ಹಾಸನ": "Hassan", "ಮಂಡ್ಯ": "Mandya", "ಚಿತ್ರದುರ್ಗ": "Chitradurga",
    "ಕೋಲಾರ": "Kolar", "ರಾಯಚೂರು": "Raichur", "ಬೀದರ್": "Bidar",
}

# Canonical names plus common current, historical and city-name aliases used by
# citizens and browser speech recognition. Values always match DistrictName.
_DISTRICT_ALIASES: dict[str, tuple[str, ...]] = {
    "Bagalkot": ("Bagalkot",),
    "Ballari": ("Ballari", "Bellary"),
    "Belagavi": ("Belagavi", "Belgaum"),
    "Bengaluru City": ("Bengaluru City", "Bangalore City", "Bengaluru", "Bangalore"),
    "Bengaluru Rural": ("Bengaluru Rural", "Bangalore Rural"),
    "Bengaluru Urban": ("Bengaluru Urban", "Bangalore Urban"),
    "Bidar": ("Bidar",),
    "Chamarajanagar": ("Chamarajanagar", "Chamaraja Nagar"),
    "Chikkaballapur": ("Chikkaballapur", "Chikballapur"),
    "Chikkamagaluru": ("Chikkamagaluru", "Chikmagalur", "Chickmagalur"),
    "Chitradurga": ("Chitradurga",),
    "Dakshina Kannada": ("Dakshina Kannada", "South Canara", "Mangaluru", "Mangalore"),
    "Davanagere": ("Davanagere", "Davangere"),
    "Dharwad": ("Dharwad", "Hubballi", "Hubli"),
    "Gadag": ("Gadag",),
    "Hassan": ("Hassan",),
    "Haveri": ("Haveri",),
    "Kalaburagi": ("Kalaburagi", "Gulbarga"),
    "Kodagu": ("Kodagu", "Coorg"),
    "Kolar": ("Kolar",),
    "Koppal": ("Koppal",),
    "Mandya": ("Mandya",),
    "Mysuru": ("Mysuru", "Mysore"),
    "Raichur": ("Raichur",),
    "Ramanagara": ("Ramanagara", "Ramanagaram"),
    "Shivamogga": ("Shivamogga", "Shimoga"),
    "Tumakuru": ("Tumakuru", "Tumkur"),
    "Udupi": ("Udupi",),
    "Uttara Kannada": ("Uttara Kannada", "North Canara", "Karwar"),
    "Vijayanagara": ("Vijayanagara", "Vijayanagar", "Hosapete", "Hospet"),
    "Vijayapura": ("Vijayapura", "Bijapur"),
    "Yadgir": ("Yadgir", "Yadgiri"),
}

# Operational grouping used when a user asks for North Karnataka. Keeping the
# membership explicit makes the answer reproducible and visible in executed SQL.
_REGION_DISTRICTS: dict[str, tuple[str, ...]] = {
    "North Karnataka": (
        "Bagalkot", "Ballari", "Belagavi", "Bidar", "Dharwad", "Gadag",
        "Haveri", "Kalaburagi", "Koppal", "Raichur", "Uttara Kannada",
        "Vijayanagara", "Vijayapura", "Yadgir",
    ),
}
_REGION_ALIASES = {
    "North Karnataka": ("north karnataka", "northern karnataka", "uttara karnataka", "ಉತ್ತರ ಕರ್ನಾಟಕ"),
}

_ALIAS_INDEX: tuple[tuple[str, str], ...] = tuple(sorted(
    ((alias, canonical) for canonical, aliases in _DISTRICT_ALIASES.items() for alias in aliases),
    key=lambda item: len(item[0]), reverse=True,
))

_PLACE_RE = re.compile(
    r"\bin\s+([A-Za-z][\w .]*?)(?=\s+(?:this|last|during|for|over|in|by|with|and|the|between)\b|[?.,;]|$)",
    re.IGNORECASE,
)
_TOP_RE = re.compile(r"(?:\btop\b|ಟಾಪ್)\s*(\d{1,3})", re.IGNORECASE)
_CASE_REF_RE = re.compile(
    r"\b(?:case|fir|crime)\s*(?:details?|file|record|number|no\.?|#)?\s*(?:of|for|:)?\s*(\d{6,24})\b",
    re.IGNORECASE,
)
# follow-up cues (EN word-bounded + KN) that make a short turn resolve from memory
_PRONOUN_RE = re.compile(
    r"\b(there|that|those|them|these|it|its|his|her|their|same|again)\b|(ಅಲ್ಲಿ|ಅದೇ|ಅವರ|ಅವು|ಅದು|ಇದೇ)",
    re.IGNORECASE,
)

_BASE_FROM = (
    'FROM "CaseMaster" cm '
    'JOIN "Unit" u ON u."UnitID"=cm."PoliceStationID" '
    'JOIN "District" d ON d."DistrictID"=u."DistrictID" '
    'LEFT JOIN "CrimeHead" ch ON ch."CrimeHeadID"=cm."CrimeMajorHeadID" '
    'LEFT JOIN "CrimeSubHead" csh ON csh."CrimeSubHeadID"=cm."CrimeMinorHeadID" '
    'LEFT JOIN "GravityOffence" g ON g."GravityOffenceID"=cm."GravityOffenceID" '
    'LEFT JOIN "CaseStatusMaster" stt ON stt."CaseStatusID"=cm."CaseStatusID"'
)


def _analytics_where(where: str) -> str:
    """Add current analytics policy only to deterministic aggregate branches."""
    eligible = casedata.analytics_eligible_sql("cm")
    return f"{where} AND {eligible}" if where else f" WHERE {eligible}"


def _extract(question: str) -> dict:
    q = question.strip()
    ql = q.lower()
    out: dict = {}
    # crime keyword
    for pat, target, ilike in _CRIME_KEYWORDS:
        if re.search(pat, ql, re.IGNORECASE):
            col = 'ch."CrimeGroupName"' if target == "group" else 'csh."CrimeHeadName"'
            out["crime_cond"] = f"{col} ILIKE {_lit(ilike)}"
            out["crime_label"] = ilike.strip("%")
            break
    # Resolve named regions and every district mention, including historical
    # spellings (Mysore/Belgaum/Bellary) and multiple locations joined by "and".
    for region, aliases in _REGION_ALIASES.items():
        if any(alias in ql for alias in aliases):
            out["region"] = region
            out["region_districts"] = list(_REGION_DISTRICTS[region])
            out["jurisdiction_resolved"] = True
            break

    places: list[str] = []
    occupied: list[tuple[int, int]] = []
    candidates: list[tuple[int, int, str, str]] = []
    for alias, canonical in _ALIAS_INDEX:
        for match in re.finditer(rf"(?<!\w){re.escape(alias)}(?!\w)", q, re.IGNORECASE):
            candidates.append((match.start(), match.end(), alias, canonical))
    # Textual order first; when aliases overlap at the same location, prefer the
    # longest ("Bengaluru Rural" over bare "Bengaluru").
    for start, end, alias, canonical in sorted(
            candidates, key=lambda item: (item[0], -(item[1] - item[0]))):
        if any(start < used_end and used_start < end for used_start, used_end in occupied):
            continue
        occupied.append((start, end))
        if canonical not in places:
            places.append(canonical)
        if alias.casefold() != canonical.casefold():
            out["jurisdiction_alias_used"] = True

    for cue, canonical in _KN_DISTRICTS.items():
        if cue in q and canonical not in places:
            places.append(canonical)
            out["jurisdiction_alias_used"] = True

    if places:
        out["places"] = places
        out["place"] = places[0]  # backwards-compatible single-place context
        out["jurisdiction_resolved"] = True
    elif "region" not in out:
        # Preserve useful free-form locations for the semantic planner/fallback,
        # but only canonical names above are trusted for exact multi-place SQL.
        m = _PLACE_RE.search(q)
        if m:
            place = m.group(1).strip()
            if place and place.lower() not in {"the", "this", "state", "india", "karnataka"}:
                out["place"] = place
    # gravity / status
    if re.search(r"heinous|ಘೋರ", ql):
        out["gravity_cond"] = "g.\"LookupValue\" = 'Heinous'"
    if re.search(r"under investigation|pending|open case|ತನಿಖೆ", ql):
        out["status_cond"] = 'stt."CaseStatusName" ILIKE \'%investigation%\''
    m2 = _TOP_RE.search(q)
    if m2:
        out["top_n"] = max(1, min(100, int(m2.group(1))))
    m3 = _CASE_REF_RE.search(q)
    if m3:
        out["case_ref"] = m3.group(1)
    return out


def _carry_context(question: str, current: dict, history: list[Turn]) -> dict:
    """Multi-turn memory: if the follow-up omits place/crime but refers back
    ('how many THERE?', 'his other cases'), reuse the last user turn's entities."""
    if (current.get("place") or current.get("region")) and current.get("crime_cond"):
        return current
    followup = bool(_PRONOUN_RE.search(question)) or len(question.split()) <= 4
    if not followup:
        return current
    for turn in reversed(history):
        if turn.sender != "user":
            continue
        prior = _extract(turn.text)
        if "place" not in current and "region" not in current:
            for key in ("place", "places", "region", "region_districts",
                        "jurisdiction_resolved", "jurisdiction_alias_used"):
                if key in prior:
                    current[key] = prior[key]
        if "crime_cond" not in current and prior.get("crime_cond"):
            current["crime_cond"] = prior["crime_cond"]
            current["crime_label"] = prior.get("crime_label")
        break
    return current


def _where(filters: dict) -> str:
    conds = [filters[k] for k in ("crime_cond", "gravity_cond", "status_cond") if k in filters]
    jurisdiction: list[str] = []
    if filters.get("places"):
        values = ", ".join(_lit(v) for v in filters["places"])
        jurisdiction.append(f'd."DistrictName" IN ({values})')
    if filters.get("region_districts"):
        values = ", ".join(_lit(v) for v in filters["region_districts"])
        jurisdiction.append(f'd."DistrictName" IN ({values})')
    if jurisdiction:
        conds.append("(" + " OR ".join(jurisdiction) + ")")
    elif filters.get("place"):
        conds.append(f'd."DistrictName" ILIKE {_lit("%" + filters["place"] + "%")}')
    return (" WHERE " + " AND ".join(conds)) if conds else ""


def sql_covers_resolved_jurisdictions(sql: Optional[str], filters: dict) -> bool:
    """Whether semantic SQL contains every server-resolved district value."""
    if not sql:
        return False
    required = list(filters.get("places") or []) + list(filters.get("region_districts") or [])
    folded = sql.casefold()
    return bool(required) and all(name.casefold() in folded for name in required)


class FallbackPlanner:
    name = "deterministic-fallback"

    def plan(self, question: str, role: str, language: str, history: list[Turn]) -> Plan:
        f = _carry_context(question, _extract(question), list(history or []))
        ql = question.lower()
        where = _where(f)
        aggregate_where = _analytics_where(where)
        agg_role = requires_aggregate(role)

        if f.get("case_ref"):
            ref = f["case_ref"]
            if agg_role:
                return Plan(
                    needs_clarification=True,
                    clarifying_question=(
                        "This role can only view aggregate results. Ask for case counts by district, crime type or time window."
                        if language != "kn"
                        else "ಈ ಪಾತ್ರವು ಸಮಗ್ರ ಫಲಿತಾಂಶಗಳನ್ನು ಮಾತ್ರ ನೋಡಬಹುದು. ಜಿಲ್ಲೆ, ಅಪರಾಧ ಪ್ರಕಾರ ಅಥವಾ ಕಾಲಾವಧಿ ಪ್ರಕಾರ ಪ್ರಕರಣ ಎಣಿಕೆ ಕೇಳಿ."),
                    intent="case_lookup_denied", confidence=0.35, language=language, filters=f)
            ref_cond = f'(cm."CrimeNo" = {_lit(ref)} OR cm."CaseNo" = {_lit(ref)}'
            if len(ref) <= 10:
                ref_cond += f' OR cm."CaseMasterID" = {int(ref)}'
            ref_cond += ")"
            sql = (
                'SELECT cm."CaseMasterID", cm."CrimeNo", cm."CaseNo", '
                'cm."CrimeRegisteredDate", d."DistrictName", u."UnitName", '
                'ch."CrimeGroupName", csh."CrimeHeadName", g."LookupValue" AS "Gravity", '
                'stt."CaseStatusName", cm."BriefFacts" '
                f'{_BASE_FROM} WHERE {ref_cond} '
                'ORDER BY cm."CrimeRegisteredDate" DESC NULLS LAST LIMIT 1'
            )
            return Plan(sql=sql, intent="case_details", confidence=0.82, language=language, filters=f)

        # intent: top -> trend -> count -> list -> clarify. Cue sets match English,
        # Kannada script and common transliterated (Latin-script Kannada) forms.
        if f.get("top_n") or re.search(
            r"\btop\b|ಟಾಪ್|most|highest|ranking|which districts|ಅತಿ ಹೆಚ್ಚು|ಹೆಚ್ಚು|"
            r"hecchu|adhika|jaasti", ql):
            n = f.get("top_n", 5)
            sql = (f'SELECT d."DistrictName", COUNT(*) AS case_count {_BASE_FROM}{aggregate_where} '
                   f'GROUP BY d."DistrictName" ORDER BY case_count DESC LIMIT {n}')
            return Plan(sql=authorize_case_aggregate(sql), intent="top_districts",
                        confidence=0.72, language=language, filters=f)

        if re.search(r"trend|over time|monthly|per month|by month|each month|ಪ್ರವೃತ್ತಿ|ತಿಂಗಳ|"
                     r"pravrutti|tingala|maasika|maasa", ql):
            sql = (f'SELECT to_char(date_trunc(\'month\', cm."CrimeRegisteredDate"), \'YYYY-MM\') AS month, '
                   f'COUNT(*) AS case_count {_BASE_FROM}{aggregate_where} GROUP BY month ORDER BY month')
            return Plan(sql=authorize_case_aggregate(sql), intent="trend",
                        confidence=0.7, language=language, filters=f)

        if re.search(r"how many|count|number of|total|how much|ಎಷ್ಟು|ಸಂಖ್ಯೆ|"
                     r"\beshtu\b|\bestu\b|sankhye", ql):
            # --- reference-entity counts (stations, districts, officers) -----
            # A question that NAMES cases/FIRs/crimes is a case count even when it
            # also names a station or district ("how many FIRs in Mysuru district"),
            # so the reference-entity branches must not claim it.
            counts_cases = bool(re.search(
                r"case|\bfirs?\b|f\.i\.r|crime|offence|offense|complaint|"
                r"ಪ್ರಕರಣ|ಅಪರಾಧ|ದೂರು|prakarana|apradha|dooru", ql))
            if not counts_cases and re.search(r"station|ಠಾಣೆ|thane|unit|ಘಟಕ", ql):
                place_cond = (f' WHERE d."DistrictName" ILIKE {_lit("%" + f["place"] + "%")}'
                              if f.get("place") else "")
                sql = (f'SELECT COUNT(*) AS station_count FROM "Unit" u '
                       f'JOIN "District" d ON d."DistrictID"=u."DistrictID"{place_cond}')
                return Plan(sql=sql, intent="count_stations", confidence=0.78, language=language, filters=f)
            if (not counts_cases and re.search(r"\bdistrict|ಜಿಲ್ಲೆ|jille\b", ql)
                    and not re.search(r"by district|per district|each district|across district", ql)):
                sql = 'SELECT COUNT(*) AS district_count FROM "District"'
                return Plan(sql=sql, intent="count_districts", confidence=0.78, language=language, filters=f)
            # --- end reference-entity counts ---------------------------------
            if re.search(r"by district|per district|each district|across districts", ql) or (
                not f.get("place") and re.search(r"district", ql)
            ) or (len(f.get("places") or []) > 1 and not re.search(
                r"combined|together|grand total|total across|ಒಟ್ಟು ಸೇರಿ", ql)):
                sql = (f'SELECT d."DistrictName", COUNT(*) AS case_count {_BASE_FROM}{aggregate_where} '
                       f'GROUP BY d."DistrictName" ORDER BY case_count DESC')
                return Plan(sql=authorize_case_aggregate(sql), intent="count_by_district",
                            confidence=0.7, language=language, filters=f)
            sql = f'SELECT COUNT(*) AS case_count {_BASE_FROM}{aggregate_where}'
            return Plan(sql=authorize_case_aggregate(sql), intent="count",
                        confidence=0.72, language=language, filters=f)

        if re.search(r"list|show|which|recent|latest|display|give me|ತೋರಿಸಿ|ಪಟ್ಟಿ|ಇತ್ತೀಚಿನ|"
                     r"torisi|pattilist|ittichina|itichina", ql):
            has_recency = bool(re.search(r"recent|latest|ಇತ್ತೀಚಿನ|ittichina|itichina", ql))
            # Prompt 19 §C.5: a completely unconstrained list ("show cases") is
            # ambiguous about place/crime/time/subject — ask, don't dump the DB.
            if not agg_role and not where and not has_recency:
                return Plan(
                    needs_clarification=True,
                    clarifying_question=(
                        "Which cases would you like to see? Narrow it by district, crime "
                        "type or time window — e.g. “robbery FIRs in Mysuru last month”."
                        if language != "kn"
                        else "ಯಾವ ಪ್ರಕರಣಗಳನ್ನು ನೋಡಬೇಕು? ಜಿಲ್ಲೆ, ಅಪರಾಧ ಪ್ರಕಾರ ಅಥವಾ ಕಾಲಾವಧಿಯಿಂದ "
                        "ಸ್ಪಷ್ಟಪಡಿಸಿ — ಉದಾ: “ಮೈಸೂರಿನಲ್ಲಿ ಕಳೆದ ತಿಂಗಳ ದರೋಡೆ ಪ್ರಕರಣಗಳು”."),
                    intent="clarify", confidence=0.3, language=language, filters=f)
            if agg_role:
                # aggregate-only role: no case list -> aggregate by district instead
                sql = (f'SELECT d."DistrictName", COUNT(*) AS case_count {_BASE_FROM}{aggregate_where} '
                       f'GROUP BY d."DistrictName" ORDER BY case_count DESC')
                return Plan(sql=authorize_case_aggregate(sql), intent="count_by_district",
                            confidence=0.6, language=language, filters=f)
            sql = (f'SELECT cm."CaseMasterID", cm."CrimeNo", cm."CrimeRegisteredDate", '
                   f'd."DistrictName", ch."CrimeGroupName", csh."CrimeHeadName", stt."CaseStatusName" '
                   f'{_BASE_FROM}{where} ORDER BY cm."CrimeRegisteredDate" DESC NULLS LAST')
            return Plan(sql=sql, intent="list_cases", confidence=0.68, language=language, filters=f)

        # nothing matched -> clarify (never guess)
        return Plan(
            needs_clarification=True,
            clarifying_question=(
                "I can answer questions about FIRs, districts, crime types, trends and forecasts. "
                "Try e.g. “how many cyber-crime FIRs in Bengaluru City”, “top 5 districts by theft”, "
                "or “monthly trend of robbery”."
                if language != "kn"
                else "ನಾನು ಪ್ರಕರಣಗಳು, ಜಿಲ್ಲೆಗಳು, ಅಪರಾಧ ಪ್ರಕಾರಗಳು ಮತ್ತು ಪ್ರವೃತ್ತಿಗಳ ಬಗ್ಗೆ ಉತ್ತರಿಸಬಲ್ಲೆ. "
                "ಉದಾ: “ಬೆಂಗಳೂರಿನಲ್ಲಿ ಎಷ್ಟು ಸೈಬರ್ ಪ್ರಕರಣಗಳು”, “ಕಳ್ಳತನದಲ್ಲಿ ಟಾಪ್ 5 ಜಿಲ್ಲೆಗಳು”."
            ),
            intent="clarify", confidence=0.3, language=language, filters=f,
        )


# ===========================================================================
# LLM planner (OpenAI-compatible; any base_url)
# ===========================================================================
def build_system_prompt(role: str) -> str:
    rules = [
        "You translate a police analyst's question into ONE read-only PostgreSQL SELECT.",
        "Use ONLY the tables and columns listed below; never invent a column or table.",
        "Quote identifiers exactly as shown (double quotes, PascalCase).",
        "Use PostgreSQL syntax only: use LIMIT n at the end; NEVER use SELECT TOP n.",
        "Match names/values case-insensitively with ILIKE and % wildcards.",
        "NEVER write INSERT/UPDATE/DELETE/DDL or multiple statements.",
        # --- grounding rules that stop common mis-mappings -------------------
        'PLACES: a named place (e.g. "Bengaluru City", "Mysuru", "Belagavi") is a '
        'DISTRICT — filter on "District"."DistrictName" ILIKE \'%name%\', joining '
        '"CaseMaster" -> "Unit" -> "District". "Unit"."UnitName" is an individual '
        'POLICE STATION name; never use it to match a district.',
        'DISTRICT JOIN: "CaseMaster" has NO "DistrictID" column. For case-to-district '
        'analysis always join cm."PoliceStationID" -> u."UnitID", then '
        'u."DistrictID" -> d."DistrictID". Never write cm."DistrictID".',
        'PLACE NORMALIZATION: Mysore=Mysuru, Belgaum=Belagavi, Bellary=Ballari, '
        'Gulbarga=Kalaburagi, Bijapur=Vijayapura, Shimoga=Shivamogga, '
        'Tumkur=Tumakuru, Bangalore/Bengaluru=Bengaluru City. When several places '
        'are named, include every canonical district and GROUP BY DistrictName unless '
        'the user explicitly asks for one combined total.',
        'REGIONS: "North Karnataka" means exactly Bagalkot, Ballari, Belagavi, Bidar, '
        'Dharwad, Gadag, Haveri, Kalaburagi, Koppal, Raichur, Uttara Kannada, '
        'Vijayanagara, Vijayapura and Yadgir. Filter with those DistrictName values.',
        'SCOPE OF DATA: the database covers exactly ONE state (Karnataka). '
        '"in Karnataka" / "in the state" / "overall" therefore means NO place '
        'filter at all — do not ask for clarification about which state.',
        'WHAT TO COUNT: count police stations/units with COUNT(*) on "Unit"; '
        'count districts with COUNT(*) on "District"; count FIRs/cases/crimes '
        'with COUNT(*) on "CaseMaster". Never answer a station/district count '
        'from "CaseMaster".',
        'CASE REFERENCES: long FIR/crime/case numbers are TEXT identifiers. Compare '
        'them as quoted strings against "CaseMaster"."CrimeNo" or '
        '"CaseMaster"."CaseNo". "CaseMasterID" is a small internal integer and must '
        'only be used when the user explicitly asks for an internal CaseMaster ID.',
        'CRIME TYPE: "CrimeHead"."CrimeGroupName" is the broad group (e.g. Cyber, '
        'Property); "CrimeSubHead"."CrimeHeadName" is the specific offence (e.g. '
        'Theft, Murder, Robbery). Pick whichever matches the question.',
        'TIME SERIES / TREND: build the period with '
        'to_char(date_trunc(\'month\', "CrimeRegisteredDate"), \'YYYY-MM\') AS month '
        'and ORDER BY month. Never use EXTRACT(MONTH ...) alone — that merges '
        'different years into the same bucket and destroys the trend.',
        'RANKING: for "top"/"most"/"highest"/"which ... most" questions, SELECT the '
        'label AND the aggregate, then ORDER BY the aggregate DESC (add LIMIT n when '
        'a number is given). ALWAYS add ORDER BY for any grouped/ranked result so the '
        'ordering is real and not accidental.',
        'ALIASES: PostgreSQL cannot reference a SELECT alias inside WHERE/GROUP BY/'
        'HAVING — repeat the full expression there, or wrap the query in a CTE/'
        'sub-select and filter outside.',
        "If the question is ambiguous or cannot be mapped to the schema, DO NOT guess — "
        "set needs_clarification=true and give a short clarifying_question.",
    ]
    if requires_aggregate(role):
        rules.append("This role is AGGREGATE-ONLY: always use COUNT/SUM/AVG/MIN/MAX or GROUP BY; "
                     "never select individual rows, names, or PII.")
    rules.append('Respond with ONLY a JSON object: '
                 '{"sql": string|null, "needs_clarification": bool, "clarifying_question": string|null, '
                 '"confidence": number 0..1, "language": "en"|"kn"}.')
    return (
        "You are DRISHTI's grounded NL->SQL engine for the Karnataka State Police.\n"
        + "\n".join(f"- {r}" for r in rules)
        + "\n\n" + schema_text(role) + "\n\n" + glossary_text()
    )


def _plan_messages(question: str, role: str, history: list[Turn], max_history: int) -> list[dict]:
    """Compose the DATA-MINIMISED message list for a semantic planner.

    Only the allow-listed role-scoped schema + police glossary (in the system
    prompt), the bounded prior turns and the question are ever sent. Raw evidence
    bytes, unrestricted narratives, credentials and result sets are NEVER included
    — the planner sees intent + schema, not data (Prompt 19 §B.5)."""
    messages = [{"role": "system", "content": build_system_prompt(role)}]
    for turn in (history or [])[-max_history:]:
        messages.append({"role": "assistant" if turn.sender == "assistant" else "user",
                         "content": turn.text})
    messages.append({"role": "user", "content": question})
    return messages


def _plan_from_json(content: str, language: str, source: str) -> Plan:
    """Parse a semantic planner's JSON reply into a Plan (shared by every
    provider). The guard + scope layers still validate the SQL independently.

    Some otherwise compliant models wrap the single JSON object in a Markdown
    fence. Accept that presentation noise without accepting prose or executable
    content; ``raw_decode`` still requires a real JSON object.
    """
    text = (content or "").strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        if start < 0:
            raise
        data, end = json.JSONDecoder().raw_decode(text[start:])
        trailing = text[start + end:].strip()
        if trailing and trailing.strip("` \r\n"):
            raise ValueError("semantic planner returned content after its JSON object")
    if not isinstance(data, dict):
        raise ValueError("semantic planner response must be a JSON object")
    sql = data.get("sql")
    return Plan(
        sql=sql if sql else None,
        needs_clarification=bool(data.get("needs_clarification")) or not sql,
        clarifying_question=data.get("clarifying_question"),
        intent="llm", source=source,
        confidence=float(data.get("confidence", 0.75)),
        language=(data.get("language") or language),
    )


class CatalystQuickMLServingPlanner:
    """Legacy provenance label; arbitrary QuickML serving URLs are disabled.

    The model identity behind a caller-configurable Chat Completions endpoint
    cannot be attested, so deployed semantic planning uses exact-model Bedrock.
    """
    name = "catalyst-quickml-llm"

    def __init__(self, settings):
        self._s = settings

    def plan(self, question: str, role: str, language: str,
             history: list[Turn]) -> Plan:
        raise RuntimeError("arbitrary QuickML semantic planning is disabled")


# ===========================================================================
# LLM planner (generic OpenAI-compatible; self-hosted / governed OSS runtime)
# ===========================================================================
class LLMPlanner:
    """Legacy label retained for stored provenance only.

    Arbitrary OpenAI-compatible endpoints are disabled: an endpoint URL and
    model string cannot prove that a Chinese-origin model is actually serving.
    """
    name = "openai-compatible"

    def __init__(self, settings):
        self._s = settings

    def plan(self, question: str, role: str, language: str,
             history: list[Turn]) -> Plan:
        raise RuntimeError("arbitrary OpenAI-compatible semantic planning is disabled")


class BedrockPlanner:
    """Amazon Bedrock Runtime planner using the Converse API.

    In Catalyst AppSail, Converse is sent through the already-authenticated AWS
    adapter so AWS credentials remain inside the Lambda execution role. Local AWS
    development can still use the normal boto3 profile/default credential chain.
    Both paths are restricted to the exact reviewed Chinese-model allow-list.
    """
    name = "aws-bedrock"

    def __init__(self, settings):
        self._s = settings
        if not settings.bedrock_model_allowed():
            raise ValueError("Bedrock model is not in the Chinese-model allow-list")

    def _client(self):
        import boto3
        from botocore.config import Config

        kwargs = {
            "region_name": self._s.bedrock_region,
            "config": Config(read_timeout=self._s.bedrock_timeout_s, connect_timeout=10),
        }
        profile = self._s.bedrock_aws_profile.strip()
        if profile:
            return boto3.Session(profile_name=profile).client("bedrock-runtime", **kwargs)
        return boto3.client("bedrock-runtime", **kwargs)

    def _direct_converse(self, *, system: list[dict], messages: list[dict]) -> str:
        response = self._client().converse(
            modelId=self._s.bedrock_model_id,
            system=system,
            messages=messages,
            inferenceConfig={"temperature": 0},
        )
        return "".join(
            part.get("text", "")
            for part in response.get("output", {}).get("message", {}).get("content", [])
        ).strip()

    def plan(self, question: str, role: str, language: str, history: list[Turn]) -> Plan:
        messages = _plan_messages(question, role, history, self._s.nlsql_max_history_turns)
        system = [{"text": messages[0]["content"]}]
        convo = [
            {"role": m["role"], "content": [{"text": m["content"]}]}
            for m in messages[1:]
            if m["role"] in ("user", "assistant")
        ]

        # AppSail has no AWS IAM identity. Reuse its signed adapter boundary so
        # the Bedrock permission remains on a least-privilege Lambda role.
        from ..bedrock_adapter import (BedrockAdapterError, SignedHttpsBedrockAdapter,
                                       bedrock_adapter_configured,
                                       catalyst_runtime_detected)
        if bedrock_adapter_configured():
            try:
                content = SignedHttpsBedrockAdapter(
                    timeout_s=self._s.bedrock_timeout_s).converse(
                        model_id=self._s.bedrock_model_id,
                        system=system,
                        messages=convo,
                        inference_config={"temperature": 0},
                    )
            except BedrockAdapterError:
                # A deployment may temporarily retain an older adapter while a
                # least-privilege IAM user is configured in AppSail. Direct AWS
                # failover is opt-in and keeps the exact model allow-list above.
                if not self._s.bedrock_direct_sdk_available():
                    raise
                content = self._direct_converse(system=system, messages=convo)
        else:
            if catalyst_runtime_detected() and not self._s.bedrock_direct_sdk_available():
                raise RuntimeError(
                    "signed AWS Bedrock adapter or explicit direct SDK mode is required")
            if not self._s.bedrock_direct_sdk_available():
                raise RuntimeError(
                    "signed AWS Bedrock adapter is required; direct SDK access is disabled")
            content = self._direct_converse(system=system, messages=convo)
        return _plan_from_json(content, language, source="aws-bedrock")


_FALLBACK = FallbackPlanner()


def get_planner():
    """Select a governed Chinese-model semantic planner.

    The deployed path is exact-model Bedrock through the signed AWS adapter.
    Legacy QuickML and OpenAI-compatible arbitrary endpoints are intentionally
    unreachable. Any unavailable or rejected provider is handled by the caller
    as a labelled, degraded deterministic fallback.
    """
    s = get_settings()
    provider = s.semantic_provider()
    if provider == "aws_bedrock":
        # Construct even when invalid so policy/configuration rejection is
        # surfaced as a degraded aws-bedrock turn, not hidden as offline mode.
        return BedrockPlanner(s)
    return _FALLBACK


def fallback_planner() -> FallbackPlanner:
    return _FALLBACK
