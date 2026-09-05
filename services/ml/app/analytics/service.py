"""Socio-economic correlation service: AiResult envelope over the typed payload."""
from __future__ import annotations

import datetime as dt
from collections import Counter
from typing import Optional

from .. import db
from ..contracts import AiResult
from . import patterns as patterns_mod
from . import socioeconomic
from .schemas import (CorrelationCell, CrimePatternCard, CrimePatternsResponse,
                      DistrictPanelRow, NarrativeCard, ScatterPoint, ScatterSeries,
                      SocioEconomicResponse)

SOCIO_MODEL = "drishti-socioeconomic@1.0.0"
PATTERN_MODEL = "drishti-pattern-detection@1.0.0"


def socioeconomic_report(start: Optional[dt.date] = None, end: Optional[dt.date] = None,
                         k_threshold: int = 25,
                         focus_indicator: Optional[str] = None) -> SocioEconomicResponse:
    with db.ro_conn() as conn:
        data = socioeconomic.compute(conn, start, end, k_threshold, focus_indicator)

    matrix = [CorrelationCell(**c) for c in data["correlation_matrix"]]
    scatter = [ScatterSeries(crime_category=s["crime_category"], indicator=s["indicator"],
                             r=s["r"], fit_slope=s["fit_slope"], fit_intercept=s["fit_intercept"],
                             points=[ScatterPoint(**p) for p in s["points"]])
               for s in data["scatter"]]
    narrative = NarrativeCard(**data["narrative"])
    panel = [DistrictPanelRow(**d) for d in data["districts"]]

    result = AiResult(
        answer=narrative.headline,
        # confidence tracks the strength of the headline correlation (|r|), honest
        confidence=round(abs(narrative.r), 4) if narrative.r is not None else 0.0,
        source_record_ids=[f"{t}(district-aggregated)" for t in data["source_tables"]],
        reasoning_summary=(f"District-level per-capita crime rates correlated (Pearson) "
                           f"against {len(data['indicators'])} indicators over "
                           f"{data['period_start']}..{data['period_end']}; "
                           f"{data['districts_analysed']} districts, k-anon threshold "
                           f"{data['k_threshold']} ({data['suppressed_cells']} cells suppressed). "
                           f"Correlational, not causal."),
        model_version=SOCIO_MODEL,
    )
    return SocioEconomicResponse(
        result=result, period_start=data["period_start"], period_end=data["period_end"],
        indicators=data["indicators"], crime_categories=data["crime_categories"],
        districts_analysed=data["districts_analysed"], k_threshold=data["k_threshold"],
        suppressed_cells=data["suppressed_cells"], focus_indicator=data["focus_indicator"],
        correlation_matrix=matrix, scatter=scatter, narrative=narrative, districts=panel,
    )


def crime_patterns_report(pattern_type: Optional[str] = None,
                          crime_head_id: Optional[int] = None,
                          limit: int = 60) -> CrimePatternsResponse:
    """Detected crime patterns + their evidencing FIRs, wrapped in AiResult."""
    with db.ro_conn() as conn:
        data = patterns_mod.compute(conn, pattern_type, crime_head_id, limit)

    items = [CrimePatternCard(**c) for c in data["items"]]
    confs = [c.confidence for c in items if c.confidence is not None]
    mean_conf = round(sum(confs) / len(confs), 4) if confs else 0.0
    # Honest envelope model_version: the detector behind the most patterns here.
    model_counts = Counter(c.model_version for c in items if c.model_version)
    envelope_model = model_counts.most_common(1)[0][0] if model_counts else PATTERN_MODEL

    type_summary = ", ".join(f"{n} {t}" for t, n in data["by_type"].items()) or "none"
    result = AiResult(
        answer=(f"{data['total']} active crime pattern(s) surfaced ({type_summary})."
                if data["total"] else "No active crime patterns for this scope."),
        confidence=mean_conf,
        source_record_ids=[f"CrimePattern:{c.pattern_id}" for c in items],
        reasoning_summary=("Detected patterns (serial / spree / modus-operandi / temporal / "
                           "spatial / network / repeat-offender) read from CrimePattern with the "
                           "FIRs that evidence each one (CrimePatternCase). Decision support; "
                           "every pattern links back to its source cases."),
        model_version=envelope_model,
    )
    return CrimePatternsResponse(
        result=result, total=data["total"], pattern_types=data["pattern_types"],
        by_type=data["by_type"], items=items)
