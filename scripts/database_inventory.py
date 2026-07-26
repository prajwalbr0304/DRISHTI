"""Read-only PostgreSQL inventory for the DRISHTI synthetic database.

The script reads ``DATABASE_URL`` from the process environment, queries only
catalogue metadata and ``COUNT(*)``, and never prints the connection string.
It does not run ANALYZE or make any database change.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from typing import Any

import psycopg2
from psycopg2 import sql


DOMAINS: dict[str, set[str]] = {
    "Core cases and FIR taxonomy": set(
        "CaseEvent CaseMaster CaseVersion CaseSource SourceRecord SourceSystem "
        "Inv_OccuranceTime CrimeHead CrimeSubHead CaseStatusMaster GravityOffence "
        "CrimeHeadActSection CaseCategory CaseCategoryWorkflow".split()
    ),
    "People, parties and organisations": set(
        "CasePartyRole Accused Victim ComplainantDetails CanonicalEntity "
        "CanonicalPerson CanonicalOrganisation PersonAlias PersonAddress "
        "PersonContact PersonIdentifier Employee OccupationMaster Rank "
        "Designation ReligionMaster CasteMaster".split()
    ),
    "Legal, court and lifecycle": set(
        "ActSectionAssociation Act Section ArrestSurrender "
        "inv_arrestsurrenderaccused Court CourtEvent ChargesheetDetails "
        "CaseDisposition OutcomeObservation BailEvent Statement "
        "StatementVersion OutcomeLabel".split()
    ),
    "Evidence, property, digital and financial": set(
        "EvidenceActivityEvent EvidenceObject EvidenceItem EvidenceCaseLink "
        "EvidenceVersion EvidenceEntityLink CaseEvidence PropertyItem Seizure "
        "FinancialTransaction FinancialAccount TransactionLink Device "
        "DeviceArtifact CommunicationEvent DigitalImportBatch LabResult "
        "LegalHold MoneyAlert MoneyAlertReview".split()
    ),
    "Networks and intelligence": set(
        "EntityGraph NetworkEdge drishti_hidden_associations CrimePattern "
        "CrimePatternCase GangMembership LocationObservation".split()
    ),
    "Geospatial and contextual": set(
        "JurisdictionBoundary Unit UnitLocation UnitType District State "
        "CrimeHotspot AreaContextObservation EconomicIndicator SocialIndicator "
        "WeatherIndicator HolidayCalendar PublicEvent spatial_ref_sys".split()
    ),
    "ML, forecasts and model governance": set(
        "CrimePrediction FeatureSnapshot PredictionRequest PredictionResult "
        "ModelInference ModelVersion ModelBenchmark ModelReview PredictionReview "
        "ForecastBacktest FeatureDefinition FeatureSchemaVersion "
        "TrainingDatasetSnapshot CrimeEmbedding CrimeRiskScore AISummary "
        "OfficerRecommendation".split()
    ),
    "Intake, import and data quality": set(
        "IntakeDraft IntakeDraftActivity IntakeDraftParty IngestionRecord "
        "IngestionJob ImportBatch ImportStagingRow ImportTemplate "
        "ImportTemplateVersion DataQualityIssue EntityResolutionCandidate "
        "EntityMergeHistory JurisdictionReassignment SpatialRepairRun "
        "ExternalSourceVersion SyntheticDataRun".split()
    ),
    "Identity, audit, collaboration and reporting": set(
        "AlertHistory users roles role_permissions audit_logs DemoActor "
        "FeatureFlag synthetic_meta RetentionPolicy ChatMessage ChatSession "
        "VoiceTranscript RagInteraction NotificationPreference "
        "NotificationDelivery NotificationMessage ReportTemplate "
        "ReportSnapshot SavedFilter SavedQuery WorkTask".split()
    ),
}


def _human_bytes(value: int) -> str:
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    size = float(value)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.2f} {unit}"
        size /= 1024
    raise AssertionError("unreachable")


def collect(*, exact: bool) -> dict[str, Any]:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is required in the process environment")

    started = time.perf_counter()
    conn = psycopg2.connect(database_url, connect_timeout=15)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout='120s'")
            cur.execute(
                """
                SELECT current_database(), pg_database_size(current_database()),
                       current_setting('server_version')
                """
            )
            database, database_bytes, server_version = cur.fetchone()

            cur.execute(
                """
                SELECT n.nspname, c.relname, COALESCE(s.n_live_tup, 0)::bigint,
                       pg_total_relation_size(c.oid)::bigint,
                       pg_relation_size(c.oid)::bigint,
                       pg_indexes_size(c.oid)::bigint
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                LEFT JOIN pg_stat_user_tables s
                  ON s.schemaname = n.nspname AND s.relname = c.relname
                WHERE c.relkind = 'r'
                  AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
                ORDER BY n.nspname, c.relname
                """
            )
            relations = cur.fetchall()

            tables: list[dict[str, Any]] = []
            for schema, table, estimate, total_bytes, data_bytes, index_bytes in relations:
                if exact:
                    cur.execute(
                        sql.SQL("SELECT count(*) FROM {}.{}").format(
                            sql.Identifier(schema), sql.Identifier(table)
                        )
                    )
                    rows = int(cur.fetchone()[0])
                else:
                    rows = int(estimate)
                tables.append(
                    {
                        "schema": schema,
                        "table": table,
                        "rows": rows,
                        "total_bytes": int(total_bytes),
                        "data_bytes": int(data_bytes),
                        "index_bytes": int(index_bytes),
                    }
                )

            cur.execute(
                """
                SELECT count(*) FROM information_schema.columns
                WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
                """
            )
            columns = int(cur.fetchone()[0])
            cur.execute(
                """
                SELECT count(*) FROM pg_indexes
                WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
                """
            )
            indexes = int(cur.fetchone()[0])
            cur.execute(
                """
                SELECT count(*)
                FROM pg_constraint con
                JOIN pg_namespace n ON n.oid = con.connamespace
                WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
                """
            )
            constraints = int(cur.fetchone()[0])
            cur.execute(
                """
                SELECT count(*) FROM information_schema.views
                WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
                """
            )
            views = int(cur.fetchone()[0])
            cur.execute("SELECT count(*) FROM pg_matviews")
            materialized_views = int(cur.fetchone()[0])
    finally:
        conn.close()

    domain_rows: dict[str, int] = defaultdict(int)
    domain_tables: dict[str, int] = defaultdict(int)
    known = set().union(*DOMAINS.values())
    for table in tables:
        name = table["table"]
        domain = next((key for key, names in DOMAINS.items() if name in names), "Unclassified")
        domain_rows[domain] += table["rows"]
        domain_tables[domain] += 1

    return {
        "mode": "exact" if exact else "planner_estimate",
        "database": database,
        "server_version": server_version,
        "database_bytes": int(database_bytes),
        "database_size": _human_bytes(int(database_bytes)),
        "table_count": len(tables),
        "nonempty_tables": sum(1 for item in tables if item["rows"] > 0),
        "empty_tables": sum(1 for item in tables if item["rows"] == 0),
        "rows_total": sum(item["rows"] for item in tables),
        "columns": columns,
        "indexes": indexes,
        "constraints": constraints,
        "views": views,
        "materialized_views": materialized_views,
        "domain_summary": [
            {
                "domain": domain,
                "tables": domain_tables[domain],
                "rows": domain_rows[domain],
            }
            for domain in DOMAINS
        ],
        "unclassified_tables": sorted(
            item["table"] for item in tables if item["table"] not in known
        ),
        "tables": sorted(tables, key=lambda item: (-item["rows"], item["table"])),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "| Measure | Value |",
        "|---|---:|",
        f"| Database | `{report['database']}` |",
        f"| PostgreSQL | {report['server_version']} |",
        f"| Database size | {report['database_size']} |",
        f"| Ordinary tables | {report['table_count']:,} |",
        f"| Exact/estimated rows | {report['rows_total']:,} |",
        f"| Non-empty tables | {report['nonempty_tables']:,} |",
        f"| Empty tables | {report['empty_tables']:,} |",
        f"| Views | {report['views']:,} |",
        f"| Materialized views | {report['materialized_views']:,} |",
        f"| Columns | {report['columns']:,} |",
        f"| Indexes | {report['indexes']:,} |",
        f"| Constraints | {report['constraints']:,} |",
        "",
        "| Domain | Tables | Rows |",
        "|---|---:|---:|",
    ]
    lines.extend(
        f"| {item['domain']} | {item['tables']:,} | {item['rows']:,} |"
        for item in report["domain_summary"]
    )
    lines.extend(
        [
            "",
            "| Table | Rows | Total storage |",
            "|---|---:|---:|",
        ]
    )
    lines.extend(
        f"| `{item['schema']}.{item['table']}` | {item['rows']:,} | "
        f"{_human_bytes(item['total_bytes'])} |"
        for item in report["tables"]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--exact",
        action="store_true",
        help="Run COUNT(*) on every table; otherwise use planner estimates.",
    )
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="json",
        help="Output format.",
    )
    args = parser.parse_args()
    try:
        report = collect(exact=args.exact)
    except Exception as exc:  # noqa: BLE001
        print(f"database inventory failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    if args.format == "markdown":
        print(render_markdown(report))
    else:
        print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
