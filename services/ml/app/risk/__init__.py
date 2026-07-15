"""Offender profiling + TabFM-family risk scoring (Phase 9 / doc 02 §2).

Offenders are the EntityGraph 'person' nodes (the modelled recurring offenders):
in this synthetic corpus the Accused table has no stable cross-case identity
(2,175 names across 304k rows), whereas each person entity carries individual
features (career offences, specialty, gang role, network centrality, financial
flags). Each entity is mapped to a UNIQUE AccusedMasterID (rank-match on name)
so results are written to CrimeRiskScore.AccusedMasterID per the schema.

Modules:
  features      — per-offender feature builder + noisy ordinal label (context)
  models_iface  — ModelInterface: foundation (Google TabFM primary, TabPFN v2
                  alt, in-context fallback) + XGBoost/GBM calibration baseline
  scoring       — batch + on-demand scoring, Factors, calibration
  service/router— /risk endpoints (score + factors + provenance)

The foundation backend is resolved at runtime (get_foundation_model): real
Google TabFM when importable and enough free RAM (it is a 6.3GB model), else
TabPFN v2, else an in-context stand-in. Force with DRISHTI_FOUNDATION_MODEL.
"""
