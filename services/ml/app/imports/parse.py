"""Parse + map + validate structured import content into staging rows.

Pure logic (no DB) so it is fully unit-testable:
  * parse_csv / parse_json      — dependency-free readers (mirror the frontend).
  * map_and_validate            — apply a template version's column mapping to the
                                  raw rows, coerce/validate types, compute a dedupe
                                  hash over the template's dedupe keys, and mark
                                  each row valid / rejected / duplicate.

Nothing here mutates the database. The service persists the resulting staging
rows and, only after approval, writes canonical rows.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Optional

from . import templates as T


class ParseError(ValueError):
    """Raised when the source content cannot be parsed at all."""


# --- readers ----------------------------------------------------------------
def parse_csv(text: str) -> list[dict[str, str]]:
    """Parse simple CSV (quoted fields, comma-separated) into row dicts."""
    rows: list[list[str]] = []
    field = ""
    row: list[str] = []
    in_quotes = False
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if in_quotes:
            if c == '"':
                if i + 1 < n and text[i + 1] == '"':
                    field += '"'
                    i += 1
                else:
                    in_quotes = False
            else:
                field += c
        elif c == '"':
            in_quotes = True
        elif c == ",":
            row.append(field)
            field = ""
        elif c in ("\n", "\r"):
            if c == "\r" and i + 1 < n and text[i + 1] == "\n":
                i += 1
            row.append(field)
            field = ""
            if any(v.strip() != "" for v in row):
                rows.append(row)
            row = []
        else:
            field += c
        i += 1
    if field != "" or row:
        row.append(field)
        if any(v.strip() != "" for v in row):
            rows.append(row)
    if not rows:
        return []
    header = [h.strip() for h in rows[0]]
    out: list[dict[str, str]] = []
    for r in rows[1:]:
        obj: dict[str, str] = {}
        for idx, h in enumerate(header):
            obj[h] = (r[idx] if idx < len(r) else "").strip()
        out.append(obj)
    return out


def parse_json(text: str) -> list[dict[str, Any]]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ParseError(f"invalid JSON: {exc}") from exc
    if isinstance(data, list):
        return [d for d in data if isinstance(d, dict)]
    if isinstance(data, dict):
        # allow {"rows": [...]} or a single object
        if isinstance(data.get("rows"), list):
            return [d for d in data["rows"] if isinstance(d, dict)]
        return [data]
    raise ParseError("JSON must be an array of row objects (or {\"rows\": [...]}).")


def parse_content(text: str, fmt: str) -> list[dict[str, Any]]:
    if fmt == "json":
        return parse_json(text)
    if fmt == "csv":
        return parse_csv(text)
    raise ParseError(f"unsupported source format '{fmt}' (use csv|json)")


# --- mapping + validation ---------------------------------------------------
def _row_hash(mapped: dict[str, Any], dedupe_keys: list[str]) -> str:
    keys = dedupe_keys or sorted(mapped.keys())
    basis = "|".join(f"{k}={mapped.get(k)!r}" for k in keys)
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def effective_mapping(template_mapping: dict, override: Optional[dict]) -> dict:
    """Merge a per-batch source-column override onto the template mapping.

    ``override`` is {canonical_field: source_column}; it only re-points which raw
    column feeds a canonical field (it cannot change types/required-ness).
    """
    if not override:
        return template_mapping
    merged = dict(template_mapping)
    fields = []
    for f in T.template_fields(template_mapping):
        f = dict(f)
        canon = f.get("canonical")
        if canon in override and override[canon]:
            f["source"] = override[canon]
        fields.append(f)
    merged["fields"] = fields
    return merged


def map_and_validate(raw_rows: list[dict[str, Any]], mapping: dict,
                     dedupe_keys: list[str],
                     seen_hashes: Optional[set[str]] = None) -> dict:
    """Map raw rows to canonical fields, coerce/validate, and mark each row.

    Returns {rows: [ {row_number, raw, mapped, row_hash, status, reject_reason} ],
             totals: {...}, error_summary: {reason: count}, mapping_report: {...}}.
    Rows with a required-field or coercion error are 'rejected'; rows whose hash
    was already seen (within this batch or in ``seen_hashes`` from prior committed
    rows) are 'duplicate'; the rest are 'valid'.
    """
    fields = T.template_fields(mapping)
    if not fields:
        raise ParseError("template version has no field mapping")
    seen: set[str] = set(seen_hashes or set())
    within_batch: set[str] = set()
    comm_default = T.comm_type_default(mapping)

    out_rows: list[dict[str, Any]] = []
    errors: dict[str, int] = {}
    counts = {"parsed": len(raw_rows), "valid": 0, "rejected": 0, "duplicate": 0}
    mapping_report = {f["canonical"]: f.get("source") for f in fields}

    for idx, raw in enumerate(raw_rows, start=1):
        mapped: dict[str, Any] = {}
        row_errors: list[str] = []
        for f in fields:
            canon = f["canonical"]
            src = f.get("source")
            required = bool(f.get("required"))
            ftype = f.get("type", "string")
            default = f.get("default")
            raw_val = raw.get(src) if src else None
            try:
                val = T.coerce(raw_val, ftype)
            except T.CoercionError as exc:
                row_errors.append(f"{canon}: {exc}")
                continue
            if val is None and default is not None:
                val = default
            if val is None and canon == "comm_type":
                val = comm_default
            if required and (val is None or val == ""):
                row_errors.append(f"{canon}: required (source column '{src}')")
            mapped[canon] = val

        # domain sanity: a transaction cannot move money to itself
        if ("source_account_no" in mapped and "destination_account_no" in mapped
                and mapped.get("source_account_no")
                and mapped.get("source_account_no") == mapped.get("destination_account_no")):
            row_errors.append("source and destination account are identical")

        status = "valid"
        reason: Optional[str] = None
        row_hash = _row_hash(mapped, dedupe_keys)
        if row_errors:
            status, reason = "rejected", "; ".join(row_errors)
        elif row_hash in seen or row_hash in within_batch:
            status, reason = "duplicate", "duplicate of an earlier/committed row"
        else:
            within_batch.add(row_hash)

        if status == "rejected":
            counts["rejected"] += 1
            # bucket the first error code for the summary
            code = reason.split(":")[0] if reason else "rejected"
            errors[code] = errors.get(code, 0) + 1
        elif status == "duplicate":
            counts["duplicate"] += 1
            errors["duplicate"] = errors.get("duplicate", 0) + 1
        else:
            counts["valid"] += 1

        out_rows.append({
            "row_number": idx, "raw": raw, "mapped": mapped, "row_hash": row_hash,
            "status": status, "reject_reason": reason,
        })

    return {"rows": out_rows, "totals": counts, "error_summary": errors,
            "mapping_report": mapping_report}
