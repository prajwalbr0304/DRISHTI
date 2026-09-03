"""Schema-grounding catalogue + role scoping policy for NL->SQL (doc 02 §6).

This is the single source of truth the LLM is shown (so it can only reference
columns that exist) AND the independent policy the executor enforces. The two
uses are deliberately separate: the prompt gets a role-FILTERED schema, but the
scope guard re-checks the final SQL against the SAME forbidden-table sets — a
model can never prompt its way past access because enforcement is in SQL, not
the prompt (see scope.py).

Column names/casing mirror police_fir_schema.sql / *_extensions.sql /
*_intelligence.sql exactly.
"""
from __future__ import annotations

import re

from ..roles import FUNCTIONAL_ROLES

# --- Table catalogue: only these are ever exposed to NL->SQL -----------------
# Each: (description, {column: note}, [join hints]).
TABLES: dict[str, dict] = {
    "CaseMaster": {
        "desc": "FIRs / crimes — one row per registered case.",
        "columns": {
            "CaseMasterID": "PK", "CrimeNo": "18-digit crime number", "CaseNo": "case number",
            "CrimeRegisteredDate": "registration date", "IncidentFromDate": "", "IncidentToDate": "",
            "BriefFacts": "free text", "latitude": "", "longitude": "",
            "PoliceStationID": "-> Unit.UnitID", "CrimeMajorHeadID": "-> CrimeHead.CrimeHeadID",
            "CrimeMinorHeadID": "-> CrimeSubHead.CrimeSubHeadID",
            "GravityOffenceID": "-> GravityOffence.GravityOffenceID",
            "CaseStatusID": "-> CaseStatusMaster.CaseStatusID",
        },
        "joins": ['JOIN "Unit" u ON u."UnitID"=cm."PoliceStationID"',
                  'JOIN "District" d ON d."DistrictID"=u."DistrictID"'],
    },
    "District": {"desc": "Districts (top geo unit).",
                 "columns": {"DistrictID": "PK", "DistrictName": ""}, "joins": []},
    "Unit": {"desc": "Police stations / units.",
             "columns": {"UnitID": "PK", "UnitName": "", "DistrictID": "-> District.DistrictID"},
             "joins": []},
    "CrimeHead": {"desc": "Major crime head / group.",
                  "columns": {"CrimeHeadID": "PK", "CrimeGroupName": "e.g. Cyber, Property"}, "joins": []},
    "CrimeSubHead": {"desc": "Crime sub-head (specific offence).",
                     "columns": {"CrimeSubHeadID": "PK", "CrimeHeadName": "e.g. Theft, Murder"}, "joins": []},
    "GravityOffence": {"desc": "Offence gravity lookup.",
                       "columns": {"GravityOffenceID": "PK", "LookupValue": "Petty/Serious/Heinous"}, "joins": []},
    "CaseStatusMaster": {"desc": "Case status lookup.",
                         "columns": {"CaseStatusID": "PK", "CaseStatusName": "e.g. Under Investigation"}, "joins": []},
    "Act": {"desc": "Legal acts.", "columns": {"ActCode": "PK", "ShortName": "e.g. IPC"}, "joins": []},
    "Section": {"desc": "Legal sections.",
                "columns": {"SectionCode": "PK", "SectionDescription": ""}, "joins": []},
    "ActSectionAssociation": {"desc": "Charges on a case (act+section).",
                              "columns": {"CaseMasterID": "-> CaseMaster", "ActID": "-> Act.ActCode",
                                          "SectionID": "-> Section.SectionCode"}, "joins": []},
    "ArrestSurrender": {"desc": "Arrests / surrenders.",
                        "columns": {"ArrestSurrenderID": "PK", "CaseMasterID": "-> CaseMaster",
                                    "AccusedMasterID": "-> Accused", "ArrestSurrenderDate": ""}, "joins": []},
    "ChargesheetDetails": {"desc": "Chargesheets (cstype A/B/C).",
                           "columns": {"CSID": "PK", "CaseMasterID": "-> CaseMaster", "csdate": "",
                                       "cstype": "A=chargesheet,B=false,C=undetected"}, "joins": []},
    # --- individual / PII (excluded for aggregate-only roles) ---
    "Victim": {"desc": "Victims (PII).",
               "columns": {"VictimMasterID": "PK", "CaseMasterID": "-> CaseMaster",
                           "VictimName": "PII", "AgeYear": "", "GenderID": ""}, "joins": [], "pii": True},
    "Accused": {"desc": "Accused persons (PII).",
                "columns": {"AccusedMasterID": "PK", "CaseMasterID": "-> CaseMaster",
                            "AccusedName": "PII", "AgeYear": "", "PersonID": ""}, "joins": [], "pii": True},
    "ComplainantDetails": {"desc": "Complainants (PII).",
                           "columns": {"ComplainantID": "PK", "CaseMasterID": "-> CaseMaster",
                                       "ComplainantName": "PII", "AgeYear": ""}, "joins": [], "pii": True},
    "Employee": {"desc": "Police officers (PII).",
                 "columns": {"EmployeeID": "PK", "FirstName": "PII"}, "joins": [], "pii": True},
    # --- derived intelligence ---
    "CrimeRiskScore": {"desc": "Risk scores (area/offender).",
                       "columns": {"RiskScoreID": "PK", "CaseMasterID": "", "DistrictID": "-> District",
                                   "AccusedMasterID": "", "RiskScore": "0..1", "RiskLevel": "low/medium/high/critical",
                                   "ValidFrom": ""}, "joins": []},
    "CrimePrediction": {"desc": "Forecasts by area/head/window.",
                        "columns": {"PredictionID": "PK", "DistrictID": "-> District", "CrimeHeadID": "-> CrimeHead",
                                    "PredictionStart": "", "PredictionEnd": "", "PredictedCount": "",
                                    "Confidence": "0..1"}, "joins": []},
    "CrimeHotspot": {"desc": "Spatial hotspots (KDE/DBSCAN).",
                     "columns": {"HotspotID": "PK", "Name": "", "DistrictID": "-> District",
                                 "CrimeHeadID": "-> CrimeHead", "Intensity": "", "CaseCount": "",
                                 "IsActive": "bool"}, "joins": []},
    "CrimePattern": {"desc": "Detected patterns (serial/MO/spatial/...).",
                     "columns": {"PatternID": "PK", "PatternType": "", "Name": "", "Description": "",
                                 "CrimeHeadID": "-> CrimeHead", "Confidence": "0..1", "IsActive": "bool"}, "joins": []},
    "CrimePatternCase": {"desc": "Cases evidencing a pattern.",
                         "columns": {"PatternID": "-> CrimePattern", "CaseMasterID": "-> CaseMaster",
                                     "Relevance": "0..1"}, "joins": []},
    "EntityGraph": {"desc": "Graph nodes (persons/gangs/vehicles).",
                    "columns": {"EntityID": "PK", "EntityType": "person/gang/...", "Label": "",
                                "RefTable": "", "RefID": ""}, "joins": []},
    "GangMembership": {"desc": "Gang affiliations.",
                       "columns": {"GangMembershipID": "PK", "GangEntityID": "-> EntityGraph",
                                   "MemberEntityID": "-> EntityGraph", "Role": "", "IsActive": "bool"}, "joins": []},
    "AlertHistory": {"desc": "Alerts raised by the models.",
                     "columns": {"AlertID": "PK", "AlertType": "", "Severity": "info/low/medium/high/critical",
                                 "Title": "", "CaseMasterID": "", "DistrictID": "-> District",
                                 "Status": "", "CreatedAt": ""}, "joins": []},
    "SocialIndicator": {"desc": "District social indicators (monthly).",
                        "columns": {"DistrictID": "-> District", "ObservedDate": "", "Population": "",
                                    "LiteracyRate": "", "UnemploymentRate": "", "YouthRatio": ""}, "joins": []},
    "EconomicIndicator": {"desc": "District economic indicators.",
                          "columns": {"DistrictID": "-> District", "PeriodStart": "", "PerCapitaIncome": "",
                                      "UnemploymentRate": "", "PovertyIndex": ""}, "joins": []},
    "WeatherIndicator": {"desc": "District weather (monthly sample).",
                         "columns": {"DistrictID": "-> District", "ObservedAt": "", "TemperatureC": "",
                                     "RainfallMm": ""}, "joins": []},
    "ModelVersion": {"desc": "Registered model versions.",
                     "columns": {"ModelVersionID": "PK", "ModelName": "", "Version": "", "ModelType": "",
                                 "Status": ""}, "joins": []},
}

# Tables NL->SQL must NEVER touch, for ANY role (credentials/governance/chat).
GLOBAL_FORBIDDEN: frozenset[str] = frozenset({
    "users", "roles", "role_permissions", "audit_logs",
    "ChatSession", "ChatMessage", "VoiceTranscript", "SavedQuery",
})

# Individual-level PII. INTERIM: every command role may query these; the set is
# kept so an aggregate-only role can be re-introduced in AGGREGATE_ONLY_ROLES.
PII_TABLES: frozenset[str] = frozenset({
    "Victim", "Accused", "ComplainantDetails", "Employee",
    "FinancialAccount", "FinancialTransaction", "TransactionLink",
})

# Every table name known to Postgres that scope-checking must recognise. Used by
# the whole-SQL token scan so a forbidden table is caught wherever it appears.
KNOWN_TABLES: frozenset[str] = frozenset(TABLES) | GLOBAL_FORBIDDEN | PII_TABLES

ROLES = FUNCTIONAL_ROLES

# Roles restricted to aggregate answers (no individual rows / PII tables).
# INTERIM ("all roles have access to everything"): none.
AGGREGATE_ONLY_ROLES: frozenset[str] = frozenset()


class SchemaReferenceError(ValueError):
    """A qualified column does not belong to the table behind its alias."""


_RELATION = re.compile(
    r'\b(?:FROM|JOIN)\s+"([^"]+)"(?:\s+(?:AS\s+)?([A-Za-z_][A-Za-z0-9_]*))?',
    re.IGNORECASE,
)
_QUALIFIED = re.compile(r'(?:(\b[A-Za-z_][A-Za-z0-9_]*)|"([^"]+)")\s*\.\s*"([^"]+)"')
_SQL_LITERAL = re.compile(r"'(?:[^']|'')*'")
_LINE_COMMENT = re.compile(r"--[^\n\r]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_SQL_WORDS = frozenset({
    "where", "join", "left", "right", "full", "inner", "outer", "cross", "on",
    "group", "order", "having", "limit", "offset", "union", "intersect", "except",
})


def validate_qualified_columns(sql: str) -> None:
    """Reject known ``alias."Column"`` mismatches before PostgreSQL sees them.

    This deliberately validates only aliases whose source is in the allow-listed
    catalogue. CTE/result aliases remain the database parser's responsibility.
    """
    code = _LINE_COMMENT.sub(" ", _BLOCK_COMMENT.sub(" ", sql or ""))
    code = _SQL_LITERAL.sub(" '' ", code)
    aliases: dict[str, str] = {}
    for match in _RELATION.finditer(code):
        table, alias = match.groups()
        if table not in TABLES:
            continue
        if alias and alias.lower() in _SQL_WORDS:
            alias = None
        aliases[table] = table
        if alias:
            aliases[alias] = table
    errors = []
    for match in _QUALIFIED.finditer(code):
        qualifier = match.group(1) or match.group(2)
        column = match.group(3)
        table = aliases.get(qualifier)
        if table and column not in TABLES[table]["columns"]:
            errors.append(f'{qualifier}."{column}" is not a column of "{table}"')
    if errors:
        raise SchemaReferenceError("; ".join(sorted(set(errors))))


def forbidden_tables(role: str) -> frozenset[str]:
    """Tables this role may NOT query via NL->SQL (enforced in scope.py)."""
    base = GLOBAL_FORBIDDEN
    if role in AGGREGATE_ONLY_ROLES:
        return base | PII_TABLES
    return base


def requires_aggregate(role: str) -> bool:
    """True for aggregate-only roles (no individual rows / case lists)."""
    return role in AGGREGATE_ONLY_ROLES


def allowed_tables(role: str) -> list[str]:
    forbidden = forbidden_tables(role)
    return [t for t in TABLES if t not in forbidden]


def schema_text(role: str) -> str:
    """Compact, role-scoped schema shown to the LLM. PII tables are omitted for
    aggregate-only roles so the model isn't even tempted; the executor enforces it too."""
    lines: list[str] = []
    for t in allowed_tables(role):
        meta = TABLES[t]
        cols = ", ".join(f'"{c}"' for c in meta["columns"])
        pii = " [PII]" if meta.get("pii") else ""
        lines.append(f'"{t}"{pii}: {meta["desc"]} Columns: {cols}')
    joins = (
        'Common joins: CaseMaster cm JOIN "Unit" u ON u."UnitID"=cm."PoliceStationID" '
        'JOIN "District" d ON d."DistrictID"=u."DistrictID"; '
        'cm JOIN "CrimeHead" ch ON ch."CrimeHeadID"=cm."CrimeMajorHeadID"; '
        'cm JOIN "CrimeSubHead" csh ON csh."CrimeSubHeadID"=cm."CrimeMinorHeadID"; '
        'cm JOIN "GravityOffence" g ON g."GravityOffenceID"=cm."GravityOffenceID"; '
        'cm JOIN "CaseStatusMaster" st ON st."CaseStatusID"=cm."CaseStatusID".'
    )
    note = ""
    if requires_aggregate(role):
        note = ("\nSCOPE: this role is AGGREGATE-ONLY. Every query MUST use an aggregate "
                "(COUNT/SUM/AVG/MIN/MAX) or GROUP BY and MUST NOT select individual/PII rows.")
    return "TABLES (only these exist):\n" + "\n".join(lines) + "\n" + joins + note
