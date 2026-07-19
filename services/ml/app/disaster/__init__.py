"""DRISHTI Emergency Response (Prompt 17 — Disaster Response).

A separate operational context that converts synthetic or approved digital
hazard feeds into reproducible area-level forecasts, visible uncertainty,
human-approved resource plans and safe evacuation-route proposals.

Safety posture (enforced across this package):
  * synthetic hackathon decision-support demonstration — NOT an official warning,
    dispatch or evacuation system;
  * predictions operate at area/time-period level (never person-level);
  * no forecast auto-publishes an alert, auto-dispatches a resource or declares
    an area safe — stale/low-confidence inputs escalate visibly to a human;
  * Catalyst Data Store is the authoritative operational store (Data Store-native
    tables); the AWS PostGIS/pgRouting mirror is a reconstructable analytics copy.
"""
