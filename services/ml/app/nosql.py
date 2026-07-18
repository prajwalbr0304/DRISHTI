"""Catalyst NoSQL contract for flexible/ephemeral state (Prompt 14 Part B, row 7).

NoSQL holds ONLY documented semi-structured state that is a poor fit for the
relational serving layer: saved board layouts, UI preferences, presence and
flexible feed envelopes. It is NEVER a duplicate of authoritative relational
records (those live in Data Store) and NEVER the system of record for case data.

Narrow interface + in-memory fake (tests/local) + Catalyst-SDK impl (deployed).
Segment layout + TTLs live in `infra/catalyst/nosql/segments.json`.
"""
from __future__ import annotations

import os
import time
from abc import ABC, abstractmethod
from typing import Any, Optional

# Allowed segments (tables). Anything not here is rejected — NoSQL never becomes
# a shadow of the relational serving layer.
SEGMENT_BOARD_LAYOUT = "BoardLayout"        # reserved (Prompt 16), disabled scaffold
SEGMENT_UI_PREFERENCES = "UiPreferences"
SEGMENT_PRESENCE = "Presence"               # ephemeral, TTL-backed
SEGMENT_FEED_ENVELOPE = "FeedEnvelope"
_VALID_SEGMENTS = (SEGMENT_BOARD_LAYOUT, SEGMENT_UI_PREFERENCES,
                   SEGMENT_PRESENCE, SEGMENT_FEED_ENVELOPE)


class NoSQLClient(ABC):
    """Key/attribute document store with optional TTL for ephemeral items."""

    @abstractmethod
    def put(self, segment: str, key: str, item: dict[str, Any],
            *, ttl_s: Optional[int] = None) -> None: ...

    @abstractmethod
    def get(self, segment: str, key: str) -> Optional[dict[str, Any]]: ...

    @abstractmethod
    def delete(self, segment: str, key: str) -> None: ...


def _check_segment(segment: str) -> None:
    if segment not in _VALID_SEGMENTS:
        raise ValueError(f"unknown NoSQL segment {segment!r}; expected {_VALID_SEGMENTS}")


class InMemoryNoSQL(NoSQLClient):
    def __init__(self) -> None:
        self._t: dict[str, dict[str, tuple[dict, Optional[float]]]] = {}

    def put(self, segment, key, item, *, ttl_s=None):
        _check_segment(segment)
        exp = (time.time() + ttl_s) if ttl_s else None
        self._t.setdefault(segment, {})[key] = (dict(item), exp)

    def get(self, segment, key):
        _check_segment(segment)
        rec = self._t.get(segment, {}).get(key)
        if not rec:
            return None
        item, exp = rec
        if exp and exp < time.time():
            self._t[segment].pop(key, None)
            return None
        return dict(item)

    def delete(self, segment, key):
        _check_segment(segment)
        self._t.get(segment, {}).pop(key, None)


class CatalystNoSQL(NoSQLClient):
    """Deployed impl over the Catalyst SDK (NoSQL). SDK import deferred."""

    def __init__(self, app=None):
        import zcatalyst_sdk
        self._app = app or zcatalyst_sdk.initialize()
        self._nosql = self._app.nosql()

    def _table(self, segment: str):
        _check_segment(segment)
        return self._nosql.table(segment)

    def put(self, segment, key, item, *, ttl_s=None):
        payload = {"key": {"S": key}, **{k: {"S": str(v)} for k, v in item.items()}}
        if ttl_s:
            payload["ttl"] = {"N": str(int(time.time()) + ttl_s)}
        self._table(segment).insert_item(payload)

    def get(self, segment, key):
        res = self._table(segment).get_item({"key": {"S": key}})
        return res or None

    def delete(self, segment, key):
        self._table(segment).delete_item({"key": {"S": key}})


def get_nosql() -> NoSQLClient:
    if os.getenv("DRISHTI_USE_CATALYST_NOSQL", "").lower() == "true":
        return CatalystNoSQL()
    return InMemoryNoSQL()
