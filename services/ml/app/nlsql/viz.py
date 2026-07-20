"""Typed answer-visualization contract for Ask DRISHTI (Prompt 19 §F).

A grounded answer is more than a table: the engine attaches a SERVER-VALIDATED
visualization *specification* chosen DETERMINISTICALLY from the result shape and
the resolved intent. The spec is data, never code — the browser maps `kind` to an
existing, audited component (trend chart / choropleth map / bar / number / graph)
and NEVER executes model-generated JavaScript, Vega or HTML.

Every spec carries what an analyst needs to trust it: title, dimensions,
measures + units, the time/geography fields, the source record ids (citations),
an as-of timestamp + dataset marker (freshness), a suppressed-cell count, the
scope role, the confidence, and an ALWAYS-present accessible-table fallback
(rendered from the response's `columns` + `rows_preview`). Large results stay
server-capped; this module only describes how to render what was already
returned.

Pure functions, no DB, no I/O — fully unit-testable.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Optional

# Only these visualization kinds may ever be emitted (Prompt 19 §F.2). The
# renderer refuses anything outside this set.
ALLOWED_KINDS: frozenset[str] = frozenset({
    "table", "number", "bar", "line", "choropleth", "heatmap",
    "timeline", "network", "sankey", "link",
})

_COUNT_WORDS = ("count", "cnt", "total", "number", "num", "qty", "quantity",
                "tally", "cases", "n")


# --------------------------------------------------------------------------- #
def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _col_index(columns: list[str], name: str) -> int:
    try:
        return columns.index(name)
    except ValueError:
        return -1


def _first_col_where(columns: list[str], rows: list[list], *, numeric: bool,
                     exclude: int = -1) -> int:
    """Index of the first column whose first non-null value is numeric/text."""
    for i in range(len(columns)):
        if i == exclude:
            continue
        for r in rows:
            if i >= len(r):
                continue
            v = r[i]
            if v is None:
                continue
            if numeric and _is_num(v):
                return i
            if not numeric and isinstance(v, str):
                return i
            break      # first non-null decides this column's kind
    return -1


def _looks_time(col: str) -> bool:
    c = col.lower()
    return c == "month" or any(w in c for w in ("month", "date", "period", "week", "day", "year"))


def _looks_geo(col: str) -> bool:
    c = col.lower()
    return "district" in c or c in ("districtname", "unitname", "place", "taluk", "state")


def _unit_for(col: str) -> str:
    c = col.lower()
    if any(w in c for w in _COUNT_WORDS):
        return "count"
    if "rate" in c or "ratio" in c or "index" in c or "percent" in c:
        return "ratio"
    if any(w in c for w in ("income", "amount", "inr", "rupee", "value")):
        return "currency"
    if "confidence" in c or "score" in c or "intensity" in c or "risk" in c:
        return "score"
    return "count"


def _humanize(col: str) -> str:
    import re
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", col).replace("_", " ").strip()
    return s[:1].upper() + s[1:] if s else col


def _dim(columns: list[str], idx: int, role: str) -> dict:
    return {"field": columns[idx], "label": _humanize(columns[idx]), "index": idx, "role": role}


def _measure(columns: list[str], idx: int) -> dict:
    return {"field": columns[idx], "label": _humanize(columns[idx]), "index": idx,
            "unit": _unit_for(columns[idx])}


# --------------------------------------------------------------------------- #
def build_visualization(columns: list[str], rows: list[list[Any]], *, intent: str,
                        language: str, citations: list[str], confidence: float,
                        role: str, row_total: int) -> Optional[dict]:
    """Choose a typed visualization spec from result SHAPE + intent (deterministic).

    Returns a JSON-serialisable dict (validated by `validate_spec`) or None when
    there is nothing to show. The browser renders `kind` with an existing
    component and always has the accessible table as a fallback.
    """
    kn = language == "kn"
    if not columns or not rows:
        return None

    n = len(rows)
    ncols = len(columns)

    def base(kind: str, title_en: str, title_kn: str) -> dict:
        return {
            "kind": kind,
            "title": title_kn if kn else title_en,
            "dimensions": [],
            "measures": [],
            "time_field": None,
            "geo_field": None,
            "source_ids": list(citations or []),
            "as_of": _now_iso(),
            "dataset": "synthetic",           # freshness marker (synthetic corpus)
            "suppressed": 0,                   # small-cell suppression: none for synthetic aggregates
            "confidence": round(float(confidence), 4),
            "scope_role": role,
            "row_total": int(row_total),
            "language": language,
            # accessible fallback: rendered from the response columns + rows_preview
            "accessible_table": {"columns": list(columns), "row_ref": "rows_preview"},
        }

    # 1) single scalar aggregate -> a big number
    if n == 1 and ncols == 1 and _is_num(rows[0][0]):
        spec = base("number", "Total", "ಒಟ್ಟು")
        spec["measures"] = [_measure(columns, 0)]
        return validate_spec(spec)

    # 2) individual case list (has CrimeNo / CaseMasterID) -> table
    if _col_index(columns, "CrimeNo") != -1 or _col_index(columns, "CaseMasterID") != -1:
        spec = base("table", "Matching FIRs", "ಹೊಂದುವ ಎಫ್‌ಐಆರ್‌ಗಳು")
        return validate_spec(spec)

    # 3) briefing / heterogeneous metric list -> table (mixed units; not a chart)
    if intent == "briefing":
        spec = base("table", "Briefing metrics", "ಸಾರಾಂಶ ಮಾಪನಗಳು")
        return validate_spec(spec)

    num_idx = _first_col_where(columns, rows, numeric=True)
    if num_idx == -1:
        # no measure to plot -> honest table
        return validate_spec(base("table", "Results", "ಫಲಿತಾಂಶಗಳು"))

    # 4) time series (a time column + a numeric measure) -> line/trend
    time_idx = next((i for i, c in enumerate(columns) if _looks_time(c)), -1)
    if time_idx != -1 and time_idx != num_idx:
        spec = base("line", "Monthly trend", "ಮಾಸಿಕ ಪ್ರವೃತ್ತಿ")
        spec["dimensions"] = [_dim(columns, time_idx, "time")]
        spec["measures"] = [_measure(columns, num_idx)]
        spec["time_field"] = columns[time_idx]
        return validate_spec(spec)

    # 5) grouped by a label + a numeric measure
    txt_idx = _first_col_where(columns, rows, numeric=False, exclude=num_idx)
    if txt_idx != -1:
        if _looks_geo(columns[txt_idx]):
            # geographic grouping -> choropleth (map/heatmap) over districts
            spec = base("choropleth", "By district", "ಜಿಲ್ಲಾವಾರು")
            spec["geo_field"] = columns[txt_idx]
            spec["dimensions"] = [_dim(columns, txt_idx, "geo")]
            spec["measures"] = [_measure(columns, num_idx)]
            return validate_spec(spec)
        # non-geographic grouping -> bar
        spec = base("bar", "Ranked groups", "ಗುಂಪುಗಳ ಶ್ರೇಣಿ")
        spec["dimensions"] = [_dim(columns, txt_idx, "category")]
        spec["measures"] = [_measure(columns, num_idx)]
        return validate_spec(spec)

    # 6) fallback: table
    return validate_spec(base("table", "Results", "ಫಲಿತಾಂಶಗಳು"))


class VizError(ValueError):
    """Raised when a visualization spec is malformed or uses a disallowed kind."""


def validate_spec(spec: dict) -> dict:
    """Server-side validation of a visualization spec before it leaves the API.

    Guarantees only an approved `kind` is emitted, the referenced column indices
    are in range, and the accessible-table fallback is present. Raises VizError
    on any violation (so a bad spec can never reach the browser)."""
    kind = spec.get("kind")
    if kind not in ALLOWED_KINDS:
        raise VizError(f"disallowed visualization kind: {kind!r}")
    cols = spec.get("accessible_table", {}).get("columns")
    if not isinstance(cols, list):
        raise VizError("visualization spec must carry an accessible_table with columns")
    ncols = len(cols)
    for grp in ("dimensions", "measures"):
        for item in spec.get(grp, []):
            idx = item.get("index")
            if not isinstance(idx, int) or idx < 0 or idx >= ncols:
                raise VizError(f"{grp} field index out of range: {item!r}")
    return spec
