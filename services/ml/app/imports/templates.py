"""Import template helpers: type coercion, channel normalisation, and the
canonical-field -> DB-column maps for each target table.

The column-mapping SPEC itself lives in the database
(``ImportTemplateVersion.ColumnMapping``); this module only knows how to coerce a
raw string cell into a typed value and how a canonical field name maps to a real
column on the target table when a committed row is written.

Structured input only (CSV/JSON) — no OCR / extraction.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Optional

# Target tables an import template may write to (must match migration 015).
TARGET_TABLES = {
    "CommunicationEvent", "DeviceArtifact", "LocationObservation",
    "FinancialTransaction", "FinancialAccount",
}

# Domains -> the canonical entity kind resolved from the "left/right" endpoints
# (CANDIDATE resolution only; never auto-confirmed).
DOMAIN_ENTITY_KIND = {
    "cdr": "phone", "chat": "phone", "ip_log": None,     # IP endpoints are not a canonical kind
    "device_artifact": "device", "location": None,
    "bank_txn": "account", "wallet_upi": "account", "account_kyc": "account",
}

# Normalised payment channels (FinancialTransaction.NormalizedChannel).
_CHANNEL_MAP = {
    "upi": "upi", "vpa": "upi", "bhim": "upi",
    "imps": "imps", "neft": "neft", "rtgs": "rtgs",
    "cash": "cash", "atm": "atm", "atm_withdrawal": "atm",
    "wallet": "wallet", "prepaid": "wallet",
    "card": "card", "debit": "card", "credit": "card", "pos": "card",
    "cheque": "cheque", "chq": "cheque", "dd": "cheque",
}


class CoercionError(ValueError):
    """Raised when a raw cell cannot be coerced to the declared type."""


def normalize_channel(raw: Optional[str]) -> str:
    """Map a free-text channel string to a small normalised vocabulary."""
    if not raw:
        return "unknown"
    return _CHANNEL_MAP.get(str(raw).strip().lower(), "unknown")


def _parse_datetime(raw: str) -> str:
    """Accept a handful of common synthetic datetime formats -> ISO string.

    Kept dependency-free (no dateutil). Rejects anything unrecognised so bad
    timestamps are surfaced as row errors rather than silently dropped.
    """
    s = str(raw).strip()
    if not s:
        raise CoercionError("empty datetime")
    # normalise a trailing 'Z' and a space separator
    candidate = s.replace("Z", "+00:00")
    fmts = (
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M",
        "%Y-%m-%d", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y",
        "%d-%m-%Y %H:%M:%S", "%d-%m-%Y",
    )
    # first try full ISO (handles offset)
    try:
        return dt.datetime.fromisoformat(candidate).isoformat()
    except ValueError:
        pass
    for f in fmts:
        try:
            return dt.datetime.strptime(s, f).isoformat()
        except ValueError:
            continue
    raise CoercionError(f"unrecognised datetime '{s[:40]}'")


def coerce(value: Any, type_: str) -> Any:
    """Coerce a raw cell to the declared canonical type. Raises CoercionError."""
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if value == "":
            return None
    t = (type_ or "string").lower()
    try:
        if t == "string":
            return str(value)
        if t == "int":
            return int(float(str(value)))          # tolerate "12.0"
        if t in ("float", "decimal"):
            return float(str(value))
        if t == "datetime":
            return _parse_datetime(str(value))
        if t in ("bool", "boolean"):
            return str(value).strip().lower() in ("1", "true", "yes", "y", "t")
    except CoercionError:
        raise
    except (ValueError, TypeError) as exc:
        raise CoercionError(f"cannot coerce '{str(value)[:40]}' to {t}") from exc
    # unknown type -> keep as string
    return str(value)


def template_fields(mapping: dict) -> list[dict]:
    """The ordered field specs from a template version's ColumnMapping."""
    return list(mapping.get("fields", []) or [])


def target_table(mapping: dict, fallback: Optional[str] = None) -> Optional[str]:
    return mapping.get("target_table") or fallback


def comm_type_default(mapping: dict) -> str:
    return mapping.get("comm_type", "call")
