#!/bin/sh
# Apply migrations 026-035 up, then the matching down files in reverse order.
# Any error aborts and reports which file failed.
set -u
DB="psql -U postgres -d drishti -v ON_ERROR_STOP=1 -q"
Q="psql -U postgres -d drishti -At"

UP="026_org_wing_range 027_users_scope_profile 028_roles_six_app_roles \
029_role_ui_grants 030_role_settings 031_jurisdiction_range_level \
032_dashboard_rollup 033_org_roster_seed 034_district_commissionerates \
035_custom_roles"

DOWN="035_custom_roles 034_district_commissionerates 033_org_roster_seed \
032_dashboard_rollup 031_jurisdiction_range_level 030_role_settings \
029_role_ui_grants 028_roles_six_app_roles 027_users_scope_profile \
026_org_wing_range"

fail() { echo "FAIL: $1"; exit 1; }

# ---------------------------------------------------------------------------
# Baseline: the 32 districts, taluk boundaries and stations that migrations
# 033/034 operate on. Mirrors datagen output shape, at small scale.
# ---------------------------------------------------------------------------
echo "=========== BASELINE ==========="
$DB <<'SQL' 2>&1 | grep -i 'error' && fail "baseline"
INSERT INTO "State" ("StateID","StateName") VALUES (1,'Karnataka') ON CONFLICT DO NOTHING;

-- the five districts that get split, plus enough others to check range counts
INSERT INTO "District" ("DistrictID","DistrictName","StateID") VALUES
 (1,'Bengaluru City',1),(2,'Bengaluru Urban',1),(3,'Bengaluru Rural',1),
 (4,'Mysuru',1),(5,'Belagavi',1),(6,'Kalaburagi',1),(7,'Dakshina Kannada',1),
 (8,'Udupi',1),(9,'Uttara Kannada',1),(10,'Ballari',1),(11,'Vijayapura',1),
 (12,'Bidar',1),(13,'Raichur',1),(14,'Yadgir',1),(15,'Koppal',1),
 (16,'Davanagere',1),(17,'Dharwad',1),(18,'Gadag',1),(19,'Haveri',1),
 (20,'Shivamogga',1),(21,'Chitradurga',1),(22,'Tumakuru',1),(23,'Hassan',1),
 (24,'Mandya',1),(25,'Chikkamagaluru',1),(26,'Kodagu',1),(27,'Chamarajanagar',1),
 (28,'Kolar',1),(29,'Chikkaballapur',1),(30,'Ramanagara',1),(31,'Bagalkot',1),
 (32,'Vijayanagara',1) ON CONFLICT DO NOTHING;

INSERT INTO "UnitType" ("UnitTypeID","UnitTypeName") VALUES
 (1,'Police Station'),(4,'District HQ'),(5,'Commissionerate') ON CONFLICT DO NOTHING;

INSERT INTO "CrimeHead" ("CrimeHeadID","CrimeGroupName") VALUES
 (1,'Crimes Against Body'),(2,'Crimes Against Property'),(3,'Crimes Against Women'),
 (4,'Economic & Cyber Crime'),(5,'Drug Offences'),(6,'Public Order'),
 (7,'Traffic Offences'),(8,'Smuggling & Excise'),(9,'Miscellaneous')
 ON CONFLICT DO NOTHING;

INSERT INTO "Rank" ("RankID","RankName") VALUES
 (8,'Police Inspector'),(9,'Police Sub-Inspector'),(11,'Head Constable'),(12,'Police Constable')
 ON CONFLICT DO NOTHING;
INSERT INTO "Designation" ("DesignationID","DesignationName") VALUES
 (1,'Station House Officer'),(2,'Investigating Officer') ON CONFLICT DO NOTHING;

-- Commissionerate HQ unit for Bengaluru City (as datagen creates it)
INSERT INTO "Unit" ("UnitID","UnitName","TypeID","StateID","DistrictID") VALUES
 (1,'Bengaluru City Commissionerate',5,1,1),
 (4,'Mysuru District HQ',4,1,4),
 (5,'Belagavi District HQ',4,1,5),
 (6,'Kalaburagi District HQ',4,1,6),
 (7,'Dakshina Kannada District HQ',4,1,7),
 (17,'Dharwad District HQ',4,1,17) ON CONFLICT DO NOTHING;

-- stations: two per split district, one in the CITY taluk and one rural
INSERT INTO "Unit" ("UnitID","UnitName","TypeID","ParentUnit","StateID","DistrictID") VALUES
 (101,'Mysuru PS-1',1,4,1,4),      (102,'Nanjangud PS-1',1,4,1,4),
 (103,'Belagavi PS-1',1,5,1,5),    (104,'Bailhongal PS-1',1,5,1,5),
 (105,'Kalaburagi PS-1',1,6,1,6),  (106,'Afzalpur PS-1',1,6,1,6),
 (107,'Mangaluru PS-1',1,7,1,7),   (108,'Puttur PS-1',1,7,1,7),
 (109,'Hubballi PS-1',1,17,1,17),  (110,'Dharwad PS-1',1,17,1,17),
 (111,'Kalghatgi PS-1',1,17,1,17) ON CONFLICT DO NOTHING;

INSERT INTO "UnitLocation" ("UnitLocationID","UnitID",geom,"Taluk","IsCurrent") VALUES
 (101,101,ST_SetSRID(ST_MakePoint(76.65,12.30),4326),'Mysuru',TRUE),
 (102,102,ST_SetSRID(ST_MakePoint(76.68,12.11),4326),'Nanjangud',TRUE),
 (103,103,ST_SetSRID(ST_MakePoint(74.50,15.85),4326),'Belagavi',TRUE),
 (104,104,ST_SetSRID(ST_MakePoint(74.86,15.81),4326),'Bailhongal',TRUE),
 (105,105,ST_SetSRID(ST_MakePoint(76.83,17.33),4326),'Kalaburagi',TRUE),
 (106,106,ST_SetSRID(ST_MakePoint(76.36,17.20),4326),'Afzalpur',TRUE),
 (107,107,ST_SetSRID(ST_MakePoint(74.88,12.87),4326),'Mangaluru',TRUE),
 (108,108,ST_SetSRID(ST_MakePoint(75.20,12.76),4326),'Puttur',TRUE),
 (109,109,ST_SetSRID(ST_MakePoint(75.13,15.36),4326),'Hubballi',TRUE),
 (110,110,ST_SetSRID(ST_MakePoint(75.01,15.46),4326),'Dharwad',TRUE),
 (111,111,ST_SetSRID(ST_MakePoint(74.97,15.18),4326),'Kalghatgi',TRUE)
 ON CONFLICT DO NOTHING;

-- taluk polygons for the boundary dissolve, plus district polygons to subtract from
INSERT INTO "JurisdictionBoundary" ("Level","Name","StateID","DistrictID",geom,"IsCurrent","Version") VALUES
 ('taluk','Mysuru',    1,4, ST_GeomFromText('POLYGON((76.6 12.25,76.7 12.25,76.7 12.35,76.6 12.35,76.6 12.25))',4326),TRUE,1),
 ('taluk','Belagavi',  1,5, ST_GeomFromText('POLYGON((74.45 15.80,74.55 15.80,74.55 15.90,74.45 15.90,74.45 15.80))',4326),TRUE,1),
 ('taluk','Kalaburagi',1,6, ST_GeomFromText('POLYGON((76.78 17.28,76.88 17.28,76.88 17.38,76.78 17.38,76.78 17.28))',4326),TRUE,1),
 ('taluk','Mangaluru', 1,7, ST_GeomFromText('POLYGON((74.83 12.82,74.93 12.82,74.93 12.92,74.83 12.92,74.83 12.82))',4326),TRUE,1),
 ('taluk','Hubballi',  1,17,ST_GeomFromText('POLYGON((75.08 15.31,75.18 15.31,75.18 15.41,75.08 15.41,75.08 15.31))',4326),TRUE,1),
 ('taluk','Dharwad',   1,17,ST_GeomFromText('POLYGON((74.96 15.41,75.06 15.41,75.06 15.51,74.96 15.51,74.96 15.41))',4326),TRUE,1),
 ('district','Mysuru',          1,4, ST_GeomFromText('POLYGON((76.0 12.0,77.0 12.0,77.0 13.0,76.0 13.0,76.0 12.0))',4326),TRUE,1),
 ('district','Belagavi',        1,5, ST_GeomFromText('POLYGON((74.0 15.5,75.5 15.5,75.5 16.5,74.0 16.5,74.0 15.5))',4326),TRUE,1),
 ('district','Kalaburagi',      1,6, ST_GeomFromText('POLYGON((76.0 17.0,77.5 17.0,77.5 18.0,76.0 18.0,76.0 17.0))',4326),TRUE,1),
 ('district','Dakshina Kannada',1,7, ST_GeomFromText('POLYGON((74.5 12.5,75.5 12.5,75.5 13.2,74.5 13.2,74.5 12.5))',4326),TRUE,1),
 ('district','Dharwad',         1,17,ST_GeomFromText('POLYGON((74.8 15.0,75.5 15.0,75.5 15.7,74.8 15.7,74.8 15.0))',4326),TRUE,1)
 ON CONFLICT DO NOTHING;

-- one officer per station, so the Employee.DistrictID follow-up is exercised
INSERT INTO "Employee" ("EmployeeID","DistrictID","UnitID","RankID","DesignationID","KGID","FirstName")
SELECT u."UnitID", u."DistrictID", u."UnitID",
       CASE WHEN u."UnitID" % 2 = 1 THEN 9 ELSE 11 END,
       CASE WHEN u."UnitID" % 2 = 1 THEN 2 ELSE 2 END,
       'KG' || lpad(u."UnitID"::text,7,'0'), 'Officer ' || u."UnitID"
  FROM "Unit" u WHERE u."TypeID" = 1
ON CONFLICT DO NOTHING;
SQL
echo "ok: baseline"

echo "=========== UP ==========="
for m in $UP; do
  if $DB -f "/sql/${m}.sql" 2>&1 | grep -i 'error'; then fail "up $m"; fi
  echo "ok(up):  $m"
done

echo "--- CHECK A: 38 district-level units, 6 Commissionerates ---"
D=$($Q -c "SELECT count(*) FROM \"District\";")
C=$($Q -c "SELECT count(*) FROM \"District\" WHERE \"IsCommissionerate\";")
echo "districts=$D commissionerates=$C  (expect 38 / 6)"
[ "$D" = "38" ] || fail "district count $D"
[ "$C" = "6" ]  || fail "commissionerate count $C"

echo "--- CHECK B: KGF exists in Central Range ---"
$Q -c "SELECT d.\"DistrictName\"||' -> '||r.\"RangeCode\" FROM \"District\" d JOIN \"Range\" r ON r.\"RangeID\"=d.\"RangeID\" WHERE d.\"DistrictName\" LIKE 'Kolar Gold%';"
[ "$($Q -c "SELECT count(*) FROM \"District\" d JOIN \"Range\" r ON r.\"RangeID\"=d.\"RangeID\" WHERE d.\"DistrictName\" LIKE 'Kolar Gold%' AND r.\"RangeCode\"='CR';")" = "1" ] || fail "KGF not in Central Range"

echo "--- CHECK C: Bengaluru Urban is NOT a Commissionerate ---"
BU=$($Q -c "SELECT \"IsCommissionerate\" FROM \"District\" WHERE \"DistrictName\"='Bengaluru Urban';")
echo "Bengaluru Urban IsCommissionerate=$BU (expect f)"
[ "$BU" = "f" ] || fail "Bengaluru Urban marked as Commissionerate"

echo "--- CHECK D: every non-Commissionerate district has a range ---"
ORPHAN=$($Q -c "SELECT count(*) FROM \"District\" WHERE \"RangeID\" IS NULL AND NOT \"IsCommissionerate\";")
echo "districts with no range=$ORPHAN (expect 0)"
[ "$ORPHAN" = "0" ] || { $Q -c "SELECT \"DistrictName\" FROM \"District\" WHERE \"RangeID\" IS NULL AND NOT \"IsCommissionerate\";"; fail "orphan districts"; }

echo "--- CHECK E: city stations moved to their Commissionerate ---"
$Q -c "SELECT d.\"DistrictName\"||': '||count(*) FROM \"Unit\" u JOIN \"District\" d ON d.\"DistrictID\"=u.\"DistrictID\" WHERE d.\"IsCommissionerate\" AND u.\"TypeID\"=1 GROUP BY d.\"DistrictName\" ORDER BY 1;"
MOVED=$($Q -c "SELECT count(*) FROM \"DistrictSplitAudit\";")
echo "stations moved=$MOVED (expect 6: Mysuru, Belagavi, Kalaburagi, Mangaluru, Hubballi, Dharwad)"
[ "$MOVED" = "6" ] || fail "moved $MOVED stations"

echo "--- CHECK F: Employee.DistrictID followed its station ---"
DRIFT=$($Q -c "SELECT count(*) FROM \"Employee\" e JOIN \"Unit\" u ON u.\"UnitID\"=e.\"UnitID\" WHERE e.\"DistrictID\" <> u.\"DistrictID\";")
echo "officer/station district drift=$DRIFT (expect 0)"
[ "$DRIFT" = "0" ] || fail "officer drift $DRIFT"

echo "--- CHECK G: Commissionerate + rural remainder polygons are disjoint ---"
$Q -c "SELECT d.\"DistrictName\"||' area='||round(ST_Area(jb.geom)::numeric,5) FROM \"JurisdictionBoundary\" jb JOIN \"District\" d ON d.\"DistrictID\"=jb.\"DistrictID\" WHERE jb.\"Level\"='district' AND jb.\"IsCurrent\" AND d.\"DistrictName\" IN ('Mysuru','Mysuru City') ORDER BY 1;"
OVL=$($Q -c "SELECT count(*) FROM \"JurisdictionBoundary\" a JOIN \"JurisdictionBoundary\" b ON a.\"JurisdictionBoundaryID\"<>b.\"JurisdictionBoundaryID\" JOIN \"District\" da ON da.\"DistrictID\"=a.\"DistrictID\" JOIN \"District\" db ON db.\"DistrictID\"=b.\"DistrictID\" WHERE a.\"Level\"='district' AND b.\"Level\"='district' AND a.\"IsCurrent\" AND b.\"IsCurrent\" AND da.\"DistrictName\"='Mysuru' AND db.\"DistrictName\"='Mysuru City' AND ST_Overlaps(a.geom,b.geom);")
echo "Mysuru / Mysuru City polygon overlap=$OVL (expect 0)"
[ "$OVL" = "0" ] || fail "carved polygons overlap"

echo "--- CHECK H: range polygons built ---"
# Expect 4, not 7: the fixture seeds district geometry for only five districts
# (Mysuru, Belagavi, Kalaburagi, Dakshina Kannada, Dharwad), which fall in four
# ranges. A range with no district polygon correctly produces no range polygon.
$Q -c "SELECT count(*)||' range polygons (expect 4 with this fixture)' FROM \"JurisdictionBoundary\" WHERE \"Level\"='range' AND \"IsCurrent\";"
[ "$($Q -c "SELECT count(*) FROM \"JurisdictionBoundary\" WHERE \"Level\"='range' AND \"IsCurrent\";")" = "4" ] || fail "range polygon count"

echo "--- CHECK I: permission catalogue + built-in grants ---"
$Q -c "SELECT count(*)||' permissions in catalogue' FROM \"permission_catalogue\";"
$Q -c "SELECT count(*)||' sensitive' FROM \"permission_catalogue\" WHERE \"is_sensitive\";"
$Q -c "SELECT count(*)||' grants for built-in roles' FROM \"role_grant\";"

echo "--- CHECK J: admin can create a custom role with an arbitrary permission set ---"
$DB <<'SQL' 2>&1 | grep -i 'error' && fail "custom role creation"
INSERT INTO "roles" ("role_name","description","is_system","created_by","base_surface","allowed_scope_types")
VALUES ('coastal_security_cell','Coastal Security Police cell.',FALSE,'admin.nikhil','district_command',
        ARRAY['district','commissionerate','station']);
INSERT INTO "role_grant" ("role_name","permission_key","granted","granted_by","reason")
VALUES ('coastal_security_cell','dashboard.read',TRUE,'admin.nikhil',NULL),
       ('coastal_security_cell','map.read',TRUE,'admin.nikhil',NULL),
       ('coastal_security_cell','cases.read',TRUE,'admin.nikhil',NULL),
       ('coastal_security_cell','disaster.allocate',TRUE,'admin.nikhil','Coastal response duty.');
INSERT INTO "role_settings" ("role_name","display_label","default_route","sort_order")
VALUES ('coastal_security_cell','Coastal Security Cell','/map',70);
INSERT INTO "role_ui_grants" ("role_name","element_kind","element_id","enabled","updated_by")
VALUES ('coastal_security_cell','kpi','kpi-imbalance',FALSE,'admin.nikhil');
SQL
$Q -c "SELECT r.\"role_name\"||' surface='||r.\"base_surface\"||' grants='||count(g.*) FROM \"roles\" r LEFT JOIN \"role_grant\" g ON g.\"role_name\"=r.\"role_name\" WHERE r.\"is_system\"=FALSE GROUP BY r.\"role_name\", r.\"base_surface\";"
echo "ok: custom role created with settings and UI override"

echo "--- CHECK K: a seat can hold the custom role ---"
$DB <<'SQL' 2>&1 | grep -i 'error' && fail "custom role seat"
INSERT INTO "users" ("username","display_name","role_id","scope_type","district_id","rank_label","designation_label")
VALUES ('csc.dk','PI Coastal DK',(SELECT role_id FROM roles WHERE role_name='coastal_security_cell'),
        'district',7,'Police Inspector','Coastal Security Officer');
SQL
echo "ok: seat holds custom role"

echo "--- CHECK L: IO seats carry TRUE rank, not a blanket PSI label ---"
$DB <<'SQL' 2>&1 | grep -i 'error' && fail "io seats"
INSERT INTO "users" ("username","display_name","role_id","scope_type","unit_id","rank_label","designation_label","is_lead_investigator")
VALUES ('io.101','PSI Ramesh',   (SELECT role_id FROM roles WHERE role_name='investigating_officer'),'assigned_case',101,'Police Sub-Inspector','Investigating Officer',TRUE),
       ('io.102','HC Lakshmi',   (SELECT role_id FROM roles WHERE role_name='investigating_officer'),'assigned_case',102,'Head Constable','Case Assistant',FALSE),
       ('io.103','PC Manjunath', (SELECT role_id FROM roles WHERE role_name='investigating_officer'),'assigned_case',103,'Police Constable','Case Assistant',FALSE);
SQL
$Q -c "SELECT \"rank_label\"||' | lead='||\"is_lead_investigator\" FROM \"users\" WHERE \"username\" LIKE 'io.%' ORDER BY 1;"
LEADS=$($Q -c "SELECT count(*) FROM \"users\" WHERE \"scope_type\"='assigned_case' AND \"is_lead_investigator\";")
TOTAL=$($Q -c "SELECT count(*) FROM \"users\" WHERE \"scope_type\"='assigned_case';")
echo "assigned_case seats=$TOTAL of which lead-investigator=$LEADS (expect 3 / 1)"
[ "$TOTAL" = "3" ] && [ "$LEADS" = "1" ] || fail "lead-investigator split wrong ($LEADS/$TOTAL)"
DISTINCT=$($Q -c "SELECT count(DISTINCT \"rank_label\") FROM \"users\" WHERE \"scope_type\"='assigned_case';")
echo "distinct ranks among IO seats=$DISTINCT (expect 3 — NOT all labelled PSI)"
[ "$DISTINCT" = "3" ] || fail "IO seats collapsed to one rank label"

echo ""
echo "=========== DOWN (reverse order) ==========="
# the custom-role seat must be reassigned first, exactly as the down file documents
$DB -c "DELETE FROM \"users\" WHERE username='csc.dk';" >/dev/null 2>&1
for m in $DOWN; do
  if $DB -f "/sql/${m}.down.sql" 2>&1 | grep -i 'error'; then fail "down $m"; fi
  echo "ok(down): $m"
done

echo "--- CHECK M: back to 32 districts, 10 roles, no residue ---"
$Q -c "SELECT count(*)||' districts (expect 32)' FROM \"District\";"
$Q -c "SELECT count(*)||' roles (expect 10)' FROM \"roles\";"
$Q -c "SELECT count(*)||' leftover tables (expect 0)' FROM information_schema.tables WHERE table_name IN ('Range','Wing','WingCrimeHead','role_ui_grants','role_settings','mv_refresh_state','permission_catalogue','role_grant','DistrictSplitAudit');"
$Q -c "SELECT count(*)||' leftover users columns (expect 0)' FROM information_schema.columns WHERE table_name='users' AND column_name IN ('scope_type','wing_id','range_id','district_id','employee_id','legacy_role_name','is_lead_investigator');"
$Q -c "SELECT count(*)||' leftover roles columns (expect 0)' FROM information_schema.columns WHERE table_name='roles' AND column_name IN ('created_by','base_surface','allowed_scope_types');"

echo ""
echo "=========== ALL CHECKS COMPLETE ==========="
