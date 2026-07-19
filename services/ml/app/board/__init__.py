"""Investigation Board (Prompt 16).

A shared, object-backed analytical canvas. Board/node/edge/annotation/activity
records live in Catalyst Data Store (Data Store-native; no PostgreSQL migration).
Canonical DRISHTI objects are REFERENCED (never copied) and hydrated read-only
from the operational store. Evidence edges are imported/read-only; hypothesis
edges are drawn by a demo investigator and require a rationale before promotion.
"""
