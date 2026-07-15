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

from ..config import get_settings
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


# crime keyword -> (target, ILIKE pattern). target: 'group' (CrimeHead) or 'sub' (CrimeSubHead)
_CRIME_KEYWORDS: list[tuple[str, str, str]] = [
    (r"cyber|ಸೈಬರ್", "group", "%cyber%"),
    (r"economic", "group", "%economic%"),
    (r"vehicle\s*theft|ವಾಹನ", "sub", "%vehicle theft%"),
    (r"burglar|ಮನೆಗಳ್ಳತನ", "sub", "%burglar%"),
    (r"theft|ಕಳ್ಳತನ", "sub", "%theft%"),
    (r"robbery|ದರೋಡೆ", "sub", "%robbery%"),
    (r"dacoit|ಡಕಾಯಿತಿ", "sub", "%dacoit%"),
    (r"murder|homicide|ಕೊಲೆ", "sub", "%murder%"),
    (r"assault|hurt|ಹಲ್ಲೆ", "sub", "%assault%"),
    (r"rape|sexual|ಅತ್ಯಾಚಾರ", "sub", "%rape%"),
    (r"kidnap|abduct|ಅಪಹರಣ", "sub", "%kidnap%"),
    (r"narcotic|drug|ಮಾದಕ", "sub", "%narcotic%"),
    (r"riot|ಗಲಭೆ", "sub", "%riot%"),
    (r"extortion|ಸುಲಿಗೆ", "sub", "%extortion%"),
    (r"cheat|fraud|ವಂಚನೆ", "sub", "%cheat%"),
    (r"missing|ನಾಪತ್ತೆ", "sub", "%missing%"),
]

# common Kannada district cues -> English name fragment for ILIKE
_KN_DISTRICTS = {
    "ಬೆಂಗಳೂರ": "Bengaluru", "ಮೈಸೂರ": "Mysuru", "ಕಲಬುರಗಿ": "Kalaburagi",
    "ಬಳ್ಳಾರಿ": "Ballari", "ಮಂಗಳೂರ": "Mangaluru", "ಹುಬ್ಬಳ್ಳಿ": "Hubballi",
    "ಬೆಳಗಾವಿ": "Belagavi", "ತುಮಕೂರು": "Tumakuru", "ಶಿವಮೊಗ್ಗ": "Shivamogga",
    "ದಾವಣಗೆರೆ": "Davanagere", "ವಿಜಯಪುರ": "Vijayapura", "ಉಡುಪಿ": "Udupi",
    "ಹಾಸನ": "Hassan", "ಮಂಡ್ಯ": "Mandya", "ಚಿತ್ರದುರ್ಗ": "Chitradurga",
    "ಕೋಲಾರ": "Kolar", "ರಾಯಚೂರು": "Raichur", "ಬೀದರ್": "Bidar",
}

_PLACE_RE = re.compile(
    r"\bin\s+([A-Za-z][\w .]*?)(?=\s+(?:this|last|during|for|over|in|by|with|and|the|between)\b|[?.,;]|$)",
    re.IGNORECASE,
)
_TOP_RE = re.compile(r"(?:\btop\b|ಟಾಪ್)\s*(\d{1,3})", re.IGNORECASE)
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
    # place (English "in <place>", then Kannada cues)
    m = _PLACE_RE.search(q)
    if m:
        place = m.group(1).strip()
        if place and place.lower() not in {"the", "this", "state", "india", "karnataka"}:
            out["place"] = place
    if "place" not in out:
        for cue, name in _KN_DISTRICTS.items():
            if cue in q:
                out["place"] = name
                break
    # gravity / status
    if re.search(r"heinous|ಘೋರ", ql):
        out["gravity_cond"] = "g.\"LookupValue\" = 'Heinous'"
    if re.search(r"under investigation|pending|open case|ತನಿಖೆ", ql):
        out["status_cond"] = 'stt."CaseStatusName" ILIKE \'%investigation%\''
    m2 = _TOP_RE.search(q)
    if m2:
        out["top_n"] = max(1, min(100, int(m2.group(1))))
    return out


def _carry_context(question: str, current: dict, history: list[Turn]) -> dict:
    """Multi-turn memory: if the follow-up omits place/crime but refers back
    ('how many THERE?', 'his other cases'), reuse the last user turn's entities."""
    if current.get("place") and current.get("crime_cond"):
        return current
    followup = bool(_PRONOUN_RE.search(question)) or len(question.split()) <= 4
    if not followup:
        return current
    for turn in reversed(history):
        if turn.sender != "user":
            continue
        prior = _extract(turn.text)
        if "place" not in current and prior.get("place"):
            current["place"] = prior["place"]
        if "crime_cond" not in current and prior.get("crime_cond"):
            current["crime_cond"] = prior["crime_cond"]
            current["crime_label"] = prior.get("crime_label")
        break
    return current


def _where(filters: dict) -> str:
    conds = [filters[k] for k in ("crime_cond", "gravity_cond", "status_cond") if k in filters]
    if filters.get("place"):
        conds.append(f'd."DistrictName" ILIKE {_lit("%" + filters["place"] + "%")}')
    return (" WHERE " + " AND ".join(conds)) if conds else ""


class FallbackPlanner:
    name = "drishti-nlsql-fallback"

    def plan(self, question: str, role: str, language: str, history: list[Turn]) -> Plan:
        f = _carry_context(question, _extract(question), list(history or []))
        ql = question.lower()
        where = _where(f)
        agg_role = requires_aggregate(role)

        # intent: top -> trend -> count -> list -> clarify
        if f.get("top_n") or re.search(
            r"\btop\b|ಟಾಪ್|most|highest|ranking|which districts|ಅತಿ ಹೆಚ್ಚು|ಹೆಚ್ಚು", ql):
            n = f.get("top_n", 5)
            sql = (f'SELECT d."DistrictName", COUNT(*) AS case_count {_BASE_FROM}{where} '
                   f'GROUP BY d."DistrictName" ORDER BY case_count DESC LIMIT {n}')
            return Plan(sql=sql, intent="top_districts", confidence=0.72, language=language, filters=f)

        if re.search(r"trend|over time|monthly|per month|by month|each month|ಪ್ರವೃತ್ತಿ|ತಿಂಗಳ", ql):
            sql = (f'SELECT to_char(date_trunc(\'month\', cm."CrimeRegisteredDate"), \'YYYY-MM\') AS month, '
                   f'COUNT(*) AS case_count {_BASE_FROM}{where} GROUP BY month ORDER BY month')
            return Plan(sql=sql, intent="trend", confidence=0.7, language=language, filters=f)

        if re.search(r"how many|count|number of|total|how much|ಎಷ್ಟು|ಸಂಖ್ಯೆ", ql):
            if re.search(r"by district|per district|each district|across districts", ql) or (
                not f.get("place") and re.search(r"district", ql)
            ):
                sql = (f'SELECT d."DistrictName", COUNT(*) AS case_count {_BASE_FROM}{where} '
                       f'GROUP BY d."DistrictName" ORDER BY case_count DESC')
                return Plan(sql=sql, intent="count_by_district", confidence=0.7, language=language, filters=f)
            sql = f'SELECT COUNT(*) AS case_count {_BASE_FROM}{where}'
            return Plan(sql=sql, intent="count", confidence=0.72, language=language, filters=f)

        if re.search(r"list|show|which|recent|latest|display|give me|ತೋರಿಸಿ|ಪಟ್ಟಿ|ಇತ್ತೀಚಿನ", ql):
            if agg_role:
                # policymaker: no case list -> aggregate by district instead
                sql = (f'SELECT d."DistrictName", COUNT(*) AS case_count {_BASE_FROM}{where} '
                       f'GROUP BY d."DistrictName" ORDER BY case_count DESC')
                return Plan(sql=sql, intent="count_by_district", confidence=0.6, language=language, filters=f)
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
        "Match names/values case-insensitively with ILIKE and % wildcards.",
        "NEVER write INSERT/UPDATE/DELETE/DDL or multiple statements.",
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


class LLMPlanner:
    name = "drishti-nlsql-llm"

    def __init__(self, settings):
        self._s = settings

    def plan(self, question: str, role: str, language: str, history: list[Turn]) -> Plan:
        import httpx  # local import: only needed on the LLM path

        messages = [{"role": "system", "content": build_system_prompt(role)}]
        for turn in (history or [])[-self._s.nlsql_max_history_turns:]:
            messages.append({"role": "assistant" if turn.sender == "assistant" else "user",
                             "content": turn.text})
        messages.append({"role": "user", "content": question})

        payload = {
            "model": self._s.llm_model,
            "temperature": 0,
            "messages": messages,
            "response_format": {"type": "json_object"},
        }
        resp = httpx.post(
            f"{self._s.llm_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {self._s.llm_api_key}",
                     "Content-Type": "application/json"},
            json=payload, timeout=self._s.llm_timeout_s,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        data = json.loads(content)
        sql = data.get("sql")
        return Plan(
            sql=sql if sql else None,
            needs_clarification=bool(data.get("needs_clarification")) or not sql,
            clarifying_question=data.get("clarifying_question"),
            intent="llm", source="llm",
            confidence=float(data.get("confidence", 0.75)),
            language=(data.get("language") or language),
        )


_FALLBACK = FallbackPlanner()


def get_planner():
    """LLM when a key is configured, else the deterministic offline planner."""
    s = get_settings()
    if s.llm_api_key:
        return LLMPlanner(s)
    return _FALLBACK


def fallback_planner() -> FallbackPlanner:
    return _FALLBACK
