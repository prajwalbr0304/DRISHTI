"""Supervisor station/officer performance metrics (Prompt 20 Part C).

Aggregate, explainable OPERATIONAL metrics computed from the committed case
record (CaseMaster / CaseStatusMaster / ChargesheetDetails / Unit / District) —
distinct from the ML workload-band PREDICTION in app/workload. Every metric
carries its denominator, time window, data-freshness (as-of) and a limitations
note; there is NO simplistic punitive per-officer ranking (officer load is
reported only as an aggregate distribution). Scope is derived server-side.
"""
