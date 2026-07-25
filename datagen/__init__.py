"""
DRISHTI — Synthetic Crime Data Generation Engine
================================================

A scalable, reproducible generator that populates the Karnataka Police FIR
PostgreSQL database (AWS RDS; base schema + Phase-3 intelligence layer) with
criminologically realistic, foreign-key-consistent synthetic data.

The engine does NOT emit random Faker-style rows. Every FIR is drawn from a
crime-type behavioural profile (time of day, weekday, season, urban/rural bias,
weapon, accused/victim cardinality, repeat-offender probability, clearance
probability) so the resulting dataset exhibits real-world statistical structure:
skewed (Zipf/power-law) crime-type frequencies, Poisson event counts, Gaussian
spatial clustering around police-station jurisdictions, gang co-offending
networks, serial offenders and geographic/temporal hotspots.

Run with:  python scripts/generate.py --help
"""

__version__ = "1.0.0"
