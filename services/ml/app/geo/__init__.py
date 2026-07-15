"""Geospatial & crime-pattern analytics (Phase 7 / doc 05 Layer 0).

Modules:
  hotspots    — KDE + ST-DBSCAN hotspot job -> CrimeHotspot
  trends      — volume series with MoM/YoY deltas, rolling band, decomposition
  alerts      — emerging-trend threshold-breach detection -> AlertHistory
  validation  — PAI / hit-rate on held-out incidents + known-pattern checks
  service     — AiResult envelopes over the typed geospatial payloads
  router      — GET endpoints the map UI consumes (server-side aggregation)
"""
