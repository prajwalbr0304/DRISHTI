"""Ephemeral board presence (Prompt 16 §G.5).

Presence cursors/selections are EPHEMERAL, throttled and stored in NoSQL with a
short TTL — never in the append-only BoardActivity history. One NoSQL document
per board holds an actor->presence map (stored as a JSON string so it round-trips
through both the in-memory fake and the Catalyst SDK). Stale entries are pruned
on read; heartbeats are rate-limited via Catalyst Cache.
"""
from __future__ import annotations

import json
import time
from typing import Any, Optional

from ..cache import SEG_RATE_LIMIT, get_cache
from ..nosql import SEGMENT_PRESENCE, get_nosql

PRESENCE_TTL_S = 30          # an entry older than this is considered gone
_DOC_TTL_S = 60              # NoSQL document TTL (refreshed on each heartbeat)
_MIN_INTERVAL_S = 2          # per-actor heartbeat throttle


def _key(board_id: int) -> str:
    return f"board:{board_id}"


def _load(board_id: int) -> dict[str, Any]:
    try:
        doc = get_nosql().get(SEGMENT_PRESENCE, _key(board_id))
    except Exception:  # noqa: BLE001
        doc = None
    if not doc:
        return {}
    raw = doc.get("data")
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except ValueError:
            return {}
    return raw if isinstance(raw, dict) else {}


def _active(presence: dict[str, Any]) -> dict[str, Any]:
    now = time.time()
    return {a: p for a, p in presence.items()
            if isinstance(p, dict) and (now - float(p.get("ts", 0))) < PRESENCE_TTL_S}


def heartbeat(board_id: int, actor: str, *, cursor: Optional[dict] = None,
              selection: Optional[dict] = None) -> dict[str, Any]:
    """Record/refresh this actor's presence (throttled). Returns the active roster."""
    cache = get_cache()
    window = int(time.time() // _MIN_INTERVAL_S)
    throttle_key = f"presence:{board_id}:{actor}:{window}"
    fresh = True
    try:
        fresh = cache.add_if_absent(SEG_RATE_LIMIT, throttle_key, "1", ttl_s=_MIN_INTERVAL_S)
    except Exception:  # noqa: BLE001
        fresh = True
    presence = _active(_load(board_id))
    if fresh:
        presence[actor] = {
            "ts": time.time(),
            "cursor": (cursor or {}) if cursor else None,
            "selection": selection or None,
        }
        try:
            get_nosql().put(SEGMENT_PRESENCE, _key(board_id),
                            {"data": json.dumps(presence)}, ttl_s=_DOC_TTL_S)
        except Exception:  # noqa: BLE001
            pass
    return roster(board_id, presence)


def roster(board_id: int, presence: Optional[dict] = None) -> dict[str, Any]:
    p = _active(presence if presence is not None else _load(board_id))
    return {
        "board_id": board_id,
        "count": len(p),
        "actors": [
            {"actor": a, "selection": v.get("selection"), "cursor": v.get("cursor"),
             "age_s": round(time.time() - float(v.get("ts", 0)), 1)}
            for a, v in sorted(p.items())
        ],
    }
