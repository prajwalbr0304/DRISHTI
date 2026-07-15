#!/usr/bin/env python
"""Phase 1 load verification: row counts vs targets, FK orphan checks,
CrimeNo integrity, matview refresh + sanity, and spot-check queries."""
import os, psycopg2

conn = psycopg2.connect(
    host=os.environ["PGHOST"], port=os.getenv("PGPORT", "5432"),
    dbname=os.getenv("PGDATABASE", "postgres"), user=os.getenv("PGUSER", "postgres"),
    password=os.environ["PGPASSWORD"], sslmode="require", connect_timeout=30,
)
conn.autocommit = True
cur = conn.cursor()


def scalar(sql):
    cur.execute(sql)
    return cur.fetchone()[0]


# ---- 1. Row counts vs targets ---------------------------------------------
TARGETS = {
    "CaseMaster": 100_000, "Accused": 300_000, "Victim": 250_000,
    "ComplainantDetails": 120_000, "ArrestSurrender": 100_000,
    "ChargesheetDetails": 40_000,
}
GROUPS = {
    "Operational core": [
        "CaseMaster", "ComplainantDetails", "Victim", "Accused",
        "ArrestSurrender", "ChargesheetDetails", "ActSectionAssociation",
        "Inv_OccuranceTime", "inv_arrestsurrenderaccused",
    ],
    "Reference / org": [
        "State", "District", "UnitType", "Unit", "Rank", "Designation",
        "Employee", "Court", "CaseCategory", "GravityOffence", "CrimeHead",
        "CrimeSubHead", "CaseStatusMaster", "CasteMaster", "ReligionMaster",
        "OccupationMaster", "Act", "Section", "CrimeHeadActSection",
    ],
    "Intelligence": [
        "ModelVersion", "ModelInference", "EntityGraph", "NetworkEdge",
        "GangMembership", "CrimeRiskScore", "CrimePrediction", "CrimeHotspot",
        "CrimePattern", "CrimePatternCase", "CrimeEmbedding", "AISummary",
        "AlertHistory", "OfficerRecommendation", "SocialIndicator",
        "WeatherIndicator", "EconomicIndicator",
    ],
}
print("=" * 78)
print("ROW COUNTS")
print("=" * 78)
grand = 0
for group, tables in GROUPS.items():
    print(f"\n-- {group} --")
    for t in tables:
        n = scalar(f'SELECT COUNT(*) FROM "{t}"')
        grand += n
        tgt = TARGETS.get(t)
        if tgt:
            pct = (n - tgt) / tgt * 100
            flag = "OK" if abs(pct) <= 10 else "OUT-OF-BAND"
            print(f"  {t:<26} {n:>10,}   target {tgt:>9,}  ({pct:+5.1f}%) {flag}")
        else:
            print(f"  {t:<26} {n:>10,}")
print(f"\nTOTAL project rows: {grand:,}")

# ---- 2. CrimeNo integrity --------------------------------------------------
print("\n" + "=" * 78)
print("CrimeNo INTEGRITY")
print("=" * 78)
total = scalar('SELECT COUNT(*) FROM "CaseMaster"')
distinct = scalar('SELECT COUNT(DISTINCT "CrimeNo") FROM "CaseMaster"')
bad_len = scalar(r"""SELECT COUNT(*) FROM "CaseMaster" WHERE "CrimeNo" !~ '^[0-9]{18}$'""")
null_caseno = scalar('SELECT COUNT(*) FROM "CaseMaster" WHERE "CaseNo" IS NULL')
print(f"  rows                    : {total:,}")
print(f"  distinct CrimeNo        : {distinct:,}  (unique={distinct == total})")
print(f"  non 18-digit CrimeNo    : {bad_len}")
print(f"  NULL CaseNo (trigger)   : {null_caseno}")

# ---- 3. FK orphan checks ---------------------------------------------------
print("\n" + "=" * 78)
print("FK ORPHAN CHECKS (expect 0 everywhere)")
print("=" * 78)
ORPHAN_CHECKS = [
    ("Accused->CaseMaster", 'SELECT COUNT(*) FROM "Accused" a LEFT JOIN "CaseMaster" c ON c."CaseMasterID"=a."CaseMasterID" WHERE c."CaseMasterID" IS NULL'),
    ("Victim->CaseMaster", 'SELECT COUNT(*) FROM "Victim" v LEFT JOIN "CaseMaster" c ON c."CaseMasterID"=v."CaseMasterID" WHERE c."CaseMasterID" IS NULL'),
    ("ComplainantDetails->CaseMaster", 'SELECT COUNT(*) FROM "ComplainantDetails" x LEFT JOIN "CaseMaster" c ON c."CaseMasterID"=x."CaseMasterID" WHERE c."CaseMasterID" IS NULL'),
    ("ArrestSurrender->CaseMaster", 'SELECT COUNT(*) FROM "ArrestSurrender" x LEFT JOIN "CaseMaster" c ON c."CaseMasterID"=x."CaseMasterID" WHERE c."CaseMasterID" IS NULL'),
    ("ArrestSurrender->Accused", 'SELECT COUNT(*) FROM "ArrestSurrender" x WHERE x."AccusedMasterID" IS NOT NULL AND NOT EXISTS (SELECT 1 FROM "Accused" a WHERE a."AccusedMasterID"=x."AccusedMasterID")'),
    ("ChargesheetDetails->CaseMaster", 'SELECT COUNT(*) FROM "ChargesheetDetails" x LEFT JOIN "CaseMaster" c ON c."CaseMasterID"=x."CaseMasterID" WHERE c."CaseMasterID" IS NULL'),
    ("ActSectionAssociation->CaseMaster", 'SELECT COUNT(*) FROM "ActSectionAssociation" x LEFT JOIN "CaseMaster" c ON c."CaseMasterID"=x."CaseMasterID" WHERE c."CaseMasterID" IS NULL'),
    ("ActSectionAssociation->Act", 'SELECT COUNT(*) FROM "ActSectionAssociation" x WHERE NOT EXISTS (SELECT 1 FROM "Act" a WHERE a."ActCode"=x."ActID")'),
    ("ActSectionAssociation->Section", 'SELECT COUNT(*) FROM "ActSectionAssociation" x WHERE NOT EXISTS (SELECT 1 FROM "Section" s WHERE s."SectionCode"=x."SectionID")'),
    ("CaseMaster->Employee", 'SELECT COUNT(*) FROM "CaseMaster" c WHERE NOT EXISTS (SELECT 1 FROM "Employee" e WHERE e."EmployeeID"=c."PolicePersonID")'),
    ("CaseMaster->Unit", 'SELECT COUNT(*) FROM "CaseMaster" c WHERE NOT EXISTS (SELECT 1 FROM "Unit" u WHERE u."UnitID"=c."PoliceStationID")'),
    ("inv_asa->ArrestSurrender", 'SELECT COUNT(*) FROM "inv_arrestsurrenderaccused" x WHERE NOT EXISTS (SELECT 1 FROM "ArrestSurrender" a WHERE a."ArrestSurrenderID"=x."ArrestSurrenderID")'),
    ("inv_asa->Accused", 'SELECT COUNT(*) FROM "inv_arrestsurrenderaccused" x WHERE NOT EXISTS (SELECT 1 FROM "Accused" a WHERE a."AccusedMasterID"=x."AccusedMasterID")'),
    ("NetworkEdge->EntityGraph(src)", 'SELECT COUNT(*) FROM "NetworkEdge" n WHERE NOT EXISTS (SELECT 1 FROM "EntityGraph" e WHERE e."EntityID"=n."Source")'),
    ("NetworkEdge->EntityGraph(tgt)", 'SELECT COUNT(*) FROM "NetworkEdge" n WHERE NOT EXISTS (SELECT 1 FROM "EntityGraph" e WHERE e."EntityID"=n."Target")'),
    ("CrimeRiskScore->ModelVersion", 'SELECT COUNT(*) FROM "CrimeRiskScore" r WHERE r."ModelVersionID" IS NOT NULL AND NOT EXISTS (SELECT 1 FROM "ModelVersion" m WHERE m."ModelVersionID"=r."ModelVersionID")'),
    ("CrimeEmbedding->CaseMaster", 'SELECT COUNT(*) FROM "CrimeEmbedding" x WHERE x."CaseMasterID" IS NOT NULL AND NOT EXISTS (SELECT 1 FROM "CaseMaster" c WHERE c."CaseMasterID"=x."CaseMasterID")'),
    ("AlertHistory->CaseMaster", 'SELECT COUNT(*) FROM "AlertHistory" x WHERE x."CaseMasterID" IS NOT NULL AND NOT EXISTS (SELECT 1 FROM "CaseMaster" c WHERE c."CaseMasterID"=x."CaseMasterID")'),
    ("OfficerRecommendation->Employee", 'SELECT COUNT(*) FROM "OfficerRecommendation" x WHERE NOT EXISTS (SELECT 1 FROM "Employee" e WHERE e."EmployeeID"=x."EmployeeID")'),
    ("CrimePatternCase->CrimePattern", 'SELECT COUNT(*) FROM "CrimePatternCase" x WHERE NOT EXISTS (SELECT 1 FROM "CrimePattern" p WHERE p."PatternID"=x."PatternID")'),
]
orphans_total = 0
for label, sql in ORPHAN_CHECKS:
    n = scalar(sql)
    orphans_total += n
    print(f"  {label:<34} {n}")
print(f"\n  TOTAL ORPHANS: {orphans_total}")

# ---- 4. Matviews -----------------------------------------------------------
print("\n" + "=" * 78)
print("MATERIALIZED VIEWS (refresh + count)")
print("=" * 78)
for mv in ("mv_crime_stats", "mv_district_risk_profile", "mv_active_hotspots"):
    cur.execute(f'REFRESH MATERIALIZED VIEW "{mv}"')
    n = scalar(f'SELECT COUNT(*) FROM "{mv}"')
    print(f"  {mv:<28} rows={n:,}")

# ---- 5. Spot checks --------------------------------------------------------
print("\n" + "=" * 78)
print("SPOT CHECKS")
print("=" * 78)
print("\nTop 5 districts by cyber/economic-crime FIRs (expect Bengaluru on top):")
cur.execute("""
    SELECT d."DistrictName", COUNT(*) AS n
    FROM "CaseMaster" cm
    JOIN "Unit" u ON u."UnitID"=cm."PoliceStationID"
    JOIN "District" d ON d."DistrictID"=u."DistrictID"
    JOIN "CrimeHead" ch ON ch."CrimeHeadID"=cm."CrimeMajorHeadID"
    WHERE ch."CrimeGroupName" ILIKE '%cyber%' OR ch."CrimeGroupName" ILIKE '%economic%'
    GROUP BY d."DistrictName" ORDER BY n DESC LIMIT 5
""")
for name, n in cur.fetchall():
    print(f"    {name:<20} {n:,}")

print("\nTop 6 crime sub-heads overall (Zipf shape):")
cur.execute("""
    SELECT csh."CrimeHeadName", COUNT(*) n
    FROM "CaseMaster" cm JOIN "CrimeSubHead" csh ON csh."CrimeSubHeadID"=cm."CrimeMinorHeadID"
    GROUP BY csh."CrimeHeadName" ORDER BY n DESC LIMIT 6
""")
for name, n in cur.fetchall():
    print(f"    {name:<22} {n:,}")

print("\nCaseMaster.geom populated (should equal rows with lat/long):")
geom_n = scalar('SELECT COUNT(*) FROM "CaseMaster" WHERE "geom" IS NOT NULL')
ll_n = scalar('SELECT COUNT(*) FROM "CaseMaster" WHERE "latitude" IS NOT NULL AND "longitude" IS NOT NULL')
print(f"    geom NOT NULL={geom_n:,}   lat&long NOT NULL={ll_n:,}   match={geom_n == ll_n}")

print("\nBriefFactsFTS full-text sample ('robbery'):")
fts = scalar("""SELECT COUNT(*) FROM "CaseMaster" WHERE "BriefFactsFTS" @@ websearch_to_tsquery('english','robbery')""")
print(f"    FIRs matching FTS 'robbery' = {fts:,}")

print("\nSemantic-embedding cluster sanity (avg cosine sim within vs across heads):")
cur.execute("""
    WITH s AS (
      SELECT ROW_NUMBER() OVER () AS rn, e."Embedding" AS emb, cm."CrimeMajorHeadID" AS head
      FROM "CrimeEmbedding" e JOIN "CaseMaster" cm ON cm."CaseMasterID"=e."CaseMasterID"
      LIMIT 2000)
    SELECT
      AVG(CASE WHEN a.head=b.head THEN 1-(a.emb<=>b.emb) END) AS within,
      AVG(CASE WHEN a.head<>b.head THEN 1-(a.emb<=>b.emb) END) AS across
    FROM s a JOIN s b ON a.rn < b.rn
""")
within, across = cur.fetchone()
print(f"    within-head sim={within:.3f}  across-head sim={across:.3f}  (within>across => clusters OK)")

conn.close()
print("\nDONE.")
