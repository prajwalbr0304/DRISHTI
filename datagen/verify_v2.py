"""Read-only final verification of the loaded Datagen v2 dataset.

Reports DB size, per-domain counts, and the DoD-relevant integrity proofs
(stable canonical identity vs the old 26-PersonID defect, repeat offenders,
graph canonical linkage + edge provenance, lifecycle consistency, spatial
containment, RLS-disabled) without printing secrets or row contents.
"""
from __future__ import annotations

import psycopg2

from .preflight import _with_sslmode, resolve_dsn


def main() -> int:
    conn = psycopg2.connect(_with_sslmode(resolve_dsn()), connect_timeout=45)
    conn.set_session(readonly=True, autocommit=True)
    cur = conn.cursor()

    def scalar(sql):
        cur.execute(sql)
        return cur.fetchone()[0]

    print("=" * 74)
    print("DRISHTI Datagen v2 — final verification (read-only)")
    print("=" * 74)
    print(f"database size: {scalar('SELECT pg_size_pretty(pg_database_size(current_database()))')}")

    print("\n-- row counts by domain --")
    groups = {
        "operational": ["CaseMaster", "Accused", "Victim", "ComplainantDetails",
                        "ArrestSurrender", "ChargesheetDetails", "ActSectionAssociation"],
        "canonical identity": ["CanonicalPerson", "CanonicalOrganisation", "CanonicalEntity",
                              "CasePartyRole", "PersonAlias", "EntityResolutionCandidate",
                              "EntityMergeHistory"],
        "case workflow": ["CaseSource", "CaseVersion", "CaseEvent", "CaseCategoryWorkflow"],
        "evidence": ["EvidenceItem", "EvidenceObject", "EvidenceVersion",
                    "EvidenceCaseLink", "EvidenceActivityEvent", "EvidenceEntityLink"],
        "domains": ["Statement", "StatementVersion", "Seizure", "PropertyItem",
                   "Device", "CommunicationEvent", "LocationObservation",
                   "FinancialAccount", "FinancialTransaction", "TransactionLink",
                   "CourtEvent", "BailEvent", "CaseDisposition", "OutcomeObservation"],
        "jurisdiction/context": ["JurisdictionBoundary", "UnitLocation",
                                "ExternalSourceVersion", "HolidayCalendar",
                                "PublicEvent", "AreaContextObservation"],
        "features/prediction": ["FeatureDefinition", "FeatureSchemaVersion",
                              "FeatureSnapshot", "TrainingDatasetSnapshot",
                              "OutcomeLabel", "PredictionRequest", "PredictionResult",
                              "PredictionReview"],
        "graph": ["EntityGraph", "NetworkEdge", "GangMembership"],
        "staging/quality/audit": ["SourceSystem", "SourceRecord", "IngestionJob",
                                "IngestionRecord", "DataQualityIssue", "audit_logs"],
    }
    for grp, tables in groups.items():
        print(f"  [{grp}]")
        for t in tables:
            try:
                print(f"    {t:<28} {scalar(f'SELECT count(*) FROM \"{t}\"'):>10,}")
            except Exception:
                pass

    print("\n-- IDENTITY (fixes the 26-distinct-PersonID / name-join defect) --")
    print(f"  distinct CanonicalPersonID linked from Accused : "
          f"{scalar('SELECT count(DISTINCT \"CanonicalPersonID\") FROM \"Accused\" WHERE \"CanonicalPersonID\" IS NOT NULL'):,}")
    print(f"  Accused with a canonical person                : "
          f"{scalar('SELECT count(*) FROM \"Accused\" WHERE \"CanonicalPersonID\" IS NOT NULL'):,}")
    print(f"  Accused unknown/unidentified (no canonical)    : "
          f"{scalar('SELECT count(*) FROM \"Accused\" WHERE \"CanonicalPersonID\" IS NULL'):,}")
    print(f"  canonical persons appearing in >1 case         : "
          f"{scalar('SELECT count(*) FROM (SELECT \"CanonicalPersonID\" FROM \"CasePartyRole\" WHERE \"CanonicalPersonID\" IS NOT NULL GROUP BY \"CanonicalPersonID\" HAVING count(DISTINCT \"CaseMasterID\")>1) s'):,}")
    print(f"  same-name pairs kept separate (resolution cand.): "
          f"{scalar('SELECT count(*) FROM \"EntityResolutionCandidate\" WHERE \"Status\"=\'rejected\''):,}")

    print("\n-- GRAPH (canonical linkage + edge provenance) --")
    print(f"  person nodes                                   : "
          f"{scalar('SELECT count(*) FROM \"EntityGraph\" WHERE \"EntityType\"=\'person\''):,}")
    print(f"  person nodes WITHOUT CanonicalEntityID (want 0): "
          f"{scalar('SELECT count(*) FROM \"EntityGraph\" WHERE \"EntityType\"=\'person\' AND \"CanonicalEntityID\" IS NULL'):,}")
    print(f"  edges verified                                 : "
          f"{scalar('SELECT count(*) FROM \"NetworkEdge\" WHERE \"ProvenanceStatus\"=\'verified\''):,}")
    print(f"  edges synthetic-unverified                     : "
          f"{scalar('SELECT count(*) FROM \"NetworkEdge\" WHERE \"ProvenanceStatus\"=\'synthetic_unverified\''):,}")
    print(f"  edges WITHOUT provenance (want 0)              : "
          f"{scalar('SELECT count(*) FROM \"NetworkEdge\" WHERE \"ProvenanceStatus\" IS NULL'):,}")

    print("\n-- LIFECYCLE consistency --")
    print(f"  Charge Sheeted cases missing a chargesheet(0)  : "
          f"{scalar('SELECT count(*) FROM \"CaseVersion\" v WHERE v.\"StatusCode\"=\'chargesheeted\' AND NOT EXISTS (SELECT 1 FROM \"ChargesheetDetails\" cs WHERE cs.\"CaseMasterID\"=v.\"CaseMasterID\")'):,}")
    print(f"  Missing-person cases with a chargesheet (0)    : "
          f"{scalar('SELECT count(*) FROM \"CaseVersion\" v JOIN \"ChargesheetDetails\" cs ON cs.\"CaseMasterID\"=v.\"CaseMasterID\" WHERE v.\"CaseCategoryCode\"=\'FIR\' AND v.\"StatusCode\" LIKE \'missing%\''):,}")
    print(f"  cases with NO court assigned (pre-court exists) : "
          f"{scalar('SELECT count(*) FROM \"CaseMaster\" WHERE \"CourtID\" IS NULL'):,}")

    print("\n-- SPATIAL containment (canonical CaseVersion coords, FULL scan) --")
    print(f"  current CaseVersions out of STATE (want 0)     : "
          f"{scalar('SELECT count(*) FROM \"vw_caseversion_containment\" WHERE \"InState\"=FALSE'):,}")
    print(f"  current CaseVersions out of DISTRICT (want 0)  : "
          f"{scalar('SELECT count(*) FROM \"vw_caseversion_containment\" WHERE \"InAssignedDistrict\"=FALSE'):,}")

    print("\n-- HACKATHON security posture --")
    print(f"  app tables with RLS/FORCE enabled (want 0)     : "
          f"{scalar('SELECT count(*) FROM fn_drishti_app_tables() WHERE rls_enabled OR rls_forced'):,}")
    print(f"  synthetic marker                               : "
          f"{scalar('SELECT \"Value\" FROM \"synthetic_meta\" WHERE \"Key\"=\'app_environment\'')}")
    cur.execute('SELECT "Mode","Status","TargetFirs" FROM "SyntheticDataRun" '
                'WHERE "IsBackupMarker"=FALSE ORDER BY "SyntheticDataRunID" DESC LIMIT 3')
    print("  recent runs (mode/status/firs):", [tuple(r) for r in cur.fetchall()])
    print("=" * 74)
    conn.close()
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
