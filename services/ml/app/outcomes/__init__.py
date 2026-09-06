"""Aggregate court-outcome reporting (conviction rate and disposal mix).

Exists because a conviction rate is the metric a state or range command seat is
actually judged on, and computing it previously required reading case rows — which
is exactly what an aggregate-only seat must not do. This module answers it as
counts, so the seats that need the number can have it without case-level access.
"""
