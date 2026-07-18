"""Typed statements + append-only statement versions (manual entry only)."""
from __future__ import annotations

import datetime as dt
from typing import List, Optional

from .db import Json
from . import v2common as C

C.register("Statement", [
    "StatementID", "CaseMasterID", "CanonicalPersonID", "CasePartyRoleID",
    "StatementType", "RecordedByActor", "RecordedAt", "Place", "Language",
    "AccessClassification", "State", "EvidenceItemID",
])
C.register("StatementVersion", [
    "StatementID", "VersionNo", "StatementText", "CorrectionReason",
    "Translation", "Redacted", "CreatedByActor",
])


def build_case_statements(world: C.World, *, case_id: int, speaker_cpids: List[int],
                          reg_date: dt.date, count: int, restricted: bool,
                          recorded_by: str = "io_demo") -> None:
    w = world
    rng = w.rng
    if not speaker_cpids or count <= 0:
        return
    recorded = dt.datetime(reg_date.year, reg_date.month, reg_date.day, 14, 0)
    # Rotate across all statement types, seeded by case so single-statement cases
    # are not all 'witness' (golden coverage: witness/complainant/accused/expert).
    stypes = ["witness", "complainant", "accused", "expert"]
    for i in range(count):
        cpid = int(rng.choice(speaker_cpids))
        stype = stypes[(case_id + i) % len(stypes)]
        access = "restricted" if restricted else "demo_normal"
        st_id = w.next_id("Statement")
        w.add("Statement", (
            st_id, case_id, cpid, None, stype, recorded_by,
            recorded.strftime("%Y-%m-%d %H:%M:%S+00"), "Police Station", "en",
            access, "recorded", None,
        ))
        w.add("StatementVersion", (
            st_id, 1, f"Synthetic {stype} statement recorded for demo case {case_id}.",
            None, None, restricted, recorded_by,
        ))
        # occasional correction (v2)
        if rng.bernoulli(0.12):
            w.add("StatementVersion", (
                st_id, 2, f"Corrected synthetic {stype} statement (typo fixed).",
                "correction: clarified timeline", None, restricted, recorded_by,
            ))
        w.cover("statement_recorded")
