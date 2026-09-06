"""Typed responses for aggregate court outcomes."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class DispositionCount(BaseModel):
    disposition_type: str
    label: str
    count: int
    share_of_disposed: Optional[float] = None


class OutcomesOverview(BaseModel):
    scope: dict = Field(default_factory=dict)

    # --- the headline ------------------------------------------------------
    # Convictions as a share of cases that actually reached a verdict. The
    # denominator is convictions + acquittals ONLY: a B-report (undetected) or a
    # C-report (false complaint) is a decision not to prosecute, so counting it as
    # a failed conviction would understate court performance and conflate two
    # different things.
    conviction_rate: Optional[float] = None
    conviction_rate_denominator: str = (
        "convictions / (convictions + acquittals) — cases that reached a verdict")

    convicted: int = 0
    acquitted: int = 0
    verdicts: int = 0

    # --- the wider disposal mix -------------------------------------------
    # Reported alongside, because a high conviction rate on a small number of
    # prosecutions is a different picture from the same rate on many.
    prosecution_rate: Optional[float] = None
    prosecution_rate_denominator: str = (
        "cases reaching a verdict / all finally-disposed cases")
    total_disposed: int = 0
    breakdown: list[DispositionCount] = Field(default_factory=list)

    # --- provenance --------------------------------------------------------
    as_of: Optional[str] = None
    data_age_days: Optional[int] = None
    stale: bool = False
    empty: bool = False
    window_days: Optional[int] = None
    limitations: list[str] = Field(default_factory=list)
    dataset: str = "synthetic"
