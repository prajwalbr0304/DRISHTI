"""Briefing / overview composer for Ask DRISHTI.

A single SELECT can't answer "give me a briefing for my scope" — a briefing is
several metrics at once. This runs a small, curated set of role-scoped AGGREGATE
queries through the SAME guarded executor (validate -> scope -> drishti_readonly
-> row cap) and composes a grounded, cited overview from the ACTUAL returned
rows. No LLM, no invention: every number traces to a query that really ran.

Panels that a role may not query (scope guard) or that reference a table not yet
present (e.g. the disaster mirror before migration 023) are skipped gracefully,
so the briefing degrades to whatever the role can actually see.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from .executor import ExecutionError, execute_select
from .guard import GuardError
from .scope import ScopeError

# --- briefing intent (EN word-bounded + KN cues) ----------------------------
# Deliberately narrow so specific questions ("brief facts of case 12") don't
# trigger a full overview.
_BRIEFING_RE = re.compile(
    r"\b(briefing|brief me|brief for|overview|sitrep|situation report|"
    r"situation overview|status report|status update|daily brief)\b"
    r"|for my scope|what'?s happening|whats happening"
    r"|ಬ್ರೀಫಿಂಗ್|ಸಾರಾಂಶ|ಅವಲೋಕನ|ಪರಿಸ್ಥಿತಿ ವರದಿ|ಸ್ಥಿತಿ ವರದಿ",
    re.IGNORECASE,
)


def is_briefing_request(question: str) -> bool:
    q = (question or "").strip()
    return bool(q) and bool(_BRIEFING_RE.search(q))


@dataclass
class BriefingResult:
    reply: str
    citations: list[str] = field(default_factory=list)
    sql_display: Optional[str] = None
    metrics: list[list[Any]] = field(default_factory=list)   # [[label, value], ...]
    confidence: float = 0.0
    ran: int = 0


# --- scalar panels: (key, EN label, KN label, sql, source table) ------------
_SCALAR_PANELS: list[tuple[str, str, str, str, str]] = [
    ("firs", "FIRs on record", "ದಾಖಲಾದ ಎಫ್‌ಐಆರ್",
     'SELECT COUNT(*) AS n FROM "CaseMaster"', "CaseMaster"),
    ("hotspots", "Active hotspots", "ಸಕ್ರಿಯ ಹಾಟ್‌ಸ್ಪಾಟ್‌ಗಳು",
     'SELECT COUNT(*) AS n FROM "CrimeHotspot" WHERE "IsActive" = true', "CrimeHotspot"),
    ("alerts", "Alerts on record", "ಎಚ್ಚರಿಕೆಗಳು",
     'SELECT COUNT(*) AS n FROM "AlertHistory"', "AlertHistory"),
    ("forecasts", "Forecasts on record", "ಮುನ್ಸೂಚನೆಗಳು",
     'SELECT COUNT(*) AS n FROM "CrimePrediction"', "CrimePrediction"),
]

_TOP_DISTRICTS_SQL = (
    'SELECT d."DistrictName", COUNT(*) AS n FROM "CaseMaster" cm '
    'JOIN "Unit" u ON u."UnitID"=cm."PoliceStationID" '
    'JOIN "District" d ON d."DistrictID"=u."DistrictID" '
    'GROUP BY d."DistrictName" ORDER BY n DESC LIMIT 3'
)
_TOP_CRIMES_SQL = (
    'SELECT ch."CrimeGroupName", COUNT(*) AS n FROM "CaseMaster" cm '
    'JOIN "CrimeHead" ch ON ch."CrimeHeadID"=cm."CrimeMajorHeadID" '
    'GROUP BY ch."CrimeGroupName" ORDER BY n DESC LIMIT 3'
)


def _scalar(role: str, sql: str) -> Optional[Any]:
    try:
        _, _cols, rows = execute_select(sql, role)
    except (GuardError, ScopeError, ExecutionError):
        return None
    return rows[0][0] if rows and rows[0] else None


def _grouped(role: str, sql: str) -> Optional[list[list[Any]]]:
    try:
        _, _cols, rows = execute_select(sql, role)
    except (GuardError, ScopeError, ExecutionError):
        return None
    return rows or None


def build_briefing(role: str, language: str) -> BriefingResult:
    """Compose a grounded briefing for the role from the panels it can see."""
    kn = language == "kn"
    metrics: list[list[Any]] = []
    citations: list[str] = []
    sqls: list[str] = []

    for _key, en, kn_label, sql, table in _SCALAR_PANELS:
        val = _scalar(role, sql)
        if val is None:
            continue
        metrics.append([kn_label if kn else en, val])
        sqls.append(sql)
        tag = f"{table}(aggregated)"
        if tag not in citations:
            citations.append(tag)

    top_districts = _grouped(role, _TOP_DISTRICTS_SQL)
    if top_districts:
        sqls.append(_TOP_DISTRICTS_SQL)
    top_crimes = _grouped(role, _TOP_CRIMES_SQL)
    if top_crimes:
        sqls.append(_TOP_CRIMES_SQL)

    ran = len(metrics) + (1 if top_districts else 0) + (1 if top_crimes else 0)
    if ran == 0:
        return BriefingResult(
            reply=("ಈ ಪಾತ್ರಕ್ಕೆ ಸಾರಾಂಶ ರಚಿಸಲು ಸಾಧ್ಯವಾಗಲಿಲ್ಲ." if kn
                   else "I couldn't assemble a briefing for this role's scope."),
            confidence=0.3, ran=0)

    # --- compose the narrative ---
    header = ("ನಿಮ್ಮ ವ್ಯಾಪ್ತಿಗೆ ಅನುಗುಣವಾಗಿ DRISHTI ಸಾರಾಂಶ:" if kn
              else "Here's your DRISHTI briefing, scoped to your role:")
    lines = [header]
    for label, val in metrics:
        lines.append(f"• {label}: {val}")
    if top_districts:
        parts = ", ".join(f"{r[0]} ({r[1]})" for r in top_districts if r[0] is not None)
        if parts:
            lines.append((f"ಎಫ್‌ಐಆರ್ ಪ್ರಕಾರ ಪ್ರಮುಖ ಜಿಲ್ಲೆಗಳು: {parts}." if kn
                          else f"Top districts by FIRs: {parts}."))
    if top_crimes:
        parts = ", ".join(f"{r[0]} ({r[1]})" for r in top_crimes if r[0] is not None)
        if parts:
            lines.append((f"ಪ್ರಮುಖ ಅಪರಾಧ ಪ್ರಕಾರಗಳು: {parts}." if kn
                          else f"Leading crime types: {parts}."))

    return BriefingResult(
        reply="\n".join(lines),
        citations=citations,
        sql_display=";\n".join(sqls),
        metrics=metrics,
        confidence=0.9,
        ran=ran,
    )
