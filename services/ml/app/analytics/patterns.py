"""Crime-pattern detections read-model (doc 01 §4.6 "Crime Patterns").

Reads the derived ``CrimePattern`` rows (serial / spree / modus_operandi /
temporal / spatial / network / repeat_offender) and, for each, the FIRs that
evidence it via ``CrimePatternCase``. Postgres remains the source of truth —
this is a pure read; nothing is written. All identifiers/casing match
police_fir_intelligence.sql exactly.

Linked cases are fetched in ONE round trip for every returned pattern (a
window-function cap per pattern) to avoid an N+1, mirroring the Case Explorer
join set (CaseMaster + Unit + District + CrimeHead + CaseStatusMaster).
"""
from __future__ import annotations

from typing import Optional

# Cases shown inline per pattern card (the rest are summarised by the count).
_CASES_PER_PATTERN = 12


def _pattern_row(r) -> dict:
    model_version = None
    if r[7] and r[8]:                      # ModelName + Version
        model_version = f"{r[7]}@{r[8]}"
    return {
        "pattern_id": int(r[0]),
        "pattern_type": r[1],
        "name": r[2],
        "description": r[3],
        "crime_head_id": int(r[4]) if r[4] is not None else None,
        "crime_group": r[5],
        "model_version_id": int(r[6]) if r[6] is not None else None,
        "model_version": model_version,
        "confidence": float(r[9]) if r[9] is not None else None,
        "attributes": r[10] or {},
        "detected_at": str(r[11]) if r[11] else None,
        "is_active": bool(r[12]),
        "linked_case_count": int(r[13] or 0),
        "cases": [],
    }


def _linked_case_row(r) -> dict:
    return {
        "case_id": int(r[1]),
        "relevance": float(r[2]) if r[2] is not None else None,
        "crime_no": r[3],
        "registered_date": str(r[4]) if r[4] else None,
        "crime_group": r[5],
        "status": r[6],
        "district": r[7],
    }


def compute(conn, pattern_type: Optional[str] = None, crime_head_id: Optional[int] = None,
            limit: int = 60) -> dict:
    """Return active crime patterns (filtered/ordered) plus their evidencing cases."""
    clauses = ['p."IsActive" = TRUE']
    params: list = []
    if pattern_type:
        clauses.append('p."PatternType" = %s')
        params.append(pattern_type)
    if crime_head_id is not None:
        clauses.append('p."CrimeHeadID" = %s')
        params.append(crime_head_id)
    where = " WHERE " + " AND ".join(clauses)

    with conn.cursor() as cur:
        # 1. the patterns themselves (+ crime head + model version + evidence count)
        cur.execute(
            'SELECT p."PatternID", p."PatternType"::text, p."Name", p."Description", '
            'p."CrimeHeadID", ch."CrimeGroupName", p."ModelVersionID", '
            'mv."ModelName", mv."Version", p."Confidence", p."Attributes", '
            'p."DetectedAt"::text, p."IsActive", '
            '(SELECT COUNT(*) FROM "CrimePatternCase" pc WHERE pc."PatternID" = p."PatternID") '
            'FROM "CrimePattern" p '
            'LEFT JOIN "CrimeHead" ch ON ch."CrimeHeadID" = p."CrimeHeadID" '
            'LEFT JOIN "ModelVersion" mv ON mv."ModelVersionID" = p."ModelVersionID"'
            + where +
            ' ORDER BY p."Confidence" DESC NULLS LAST, p."DetectedAt" DESC LIMIT %s',
            params + [limit])
        patterns = [_pattern_row(r) for r in cur.fetchall()]

        # 2. distinct pattern types present (drives the UI filter), head-scoped
        type_clauses = ['p."IsActive" = TRUE']
        type_params: list = []
        if crime_head_id is not None:
            type_clauses.append('p."CrimeHeadID" = %s')
            type_params.append(crime_head_id)
        cur.execute(
            'SELECT p."PatternType"::text, COUNT(*) FROM "CrimePattern" p WHERE '
            + " AND ".join(type_clauses) + ' GROUP BY 1 ORDER BY 2 DESC', type_params)
        by_type = {row[0]: int(row[1]) for row in cur.fetchall()}

        # 3. evidencing cases for every returned pattern, one round trip, capped
        pattern_ids = [p["pattern_id"] for p in patterns]
        if pattern_ids:
            cur.execute(
                'WITH ranked AS ('
                '  SELECT pc."PatternID", pc."CaseMasterID", pc."Relevance", '
                '         ROW_NUMBER() OVER (PARTITION BY pc."PatternID" '
                '           ORDER BY pc."Relevance" DESC NULLS LAST, pc."CaseMasterID") AS rn '
                '  FROM "CrimePatternCase" pc WHERE pc."PatternID" = ANY(%s)) '
                'SELECT r."PatternID", r."CaseMasterID", r."Relevance", '
                '       cm."CrimeNo", cm."CrimeRegisteredDate"::text, '
                '       ch."CrimeGroupName", st."CaseStatusName", d."DistrictName" '
                'FROM ranked r '
                'JOIN "CaseMaster" cm ON cm."CaseMasterID" = r."CaseMasterID" '
                'LEFT JOIN "Unit" u ON u."UnitID" = cm."PoliceStationID" '
                'LEFT JOIN "District" d ON d."DistrictID" = u."DistrictID" '
                'LEFT JOIN "CrimeHead" ch ON ch."CrimeHeadID" = cm."CrimeMajorHeadID" '
                'LEFT JOIN "CaseStatusMaster" st ON st."CaseStatusID" = cm."CaseStatusID" '
                'WHERE r.rn <= %s ORDER BY r."PatternID", r.rn',
                (pattern_ids, _CASES_PER_PATTERN))
            by_pattern: dict[int, list] = {}
            for row in cur.fetchall():
                by_pattern.setdefault(int(row[0]), []).append(_linked_case_row(row))
            for p in patterns:
                p["cases"] = by_pattern.get(p["pattern_id"], [])

    return {
        "items": patterns,
        "total": len(patterns),
        "pattern_types": list(by_type.keys()),
        "by_type": by_type,
    }
