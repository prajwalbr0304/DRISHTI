-- DRISHTI seat provisioning. Idempotent and re-runnable.
--
-- Creates one login seat per command post, station and investigating officer,
-- deriving everything from the Employee establishment rather than from the
-- expected rank distribution — RANK_STAFFING is a weighted random draw, so the
-- actual per-rank counts differ every generator run.
--
-- SEAT INVENTORY
--   1      dgp_state_command     scope_type=state
--   6      senior_command        scope_type=wing    (one per ADGP wing)
--   7      senior_command        scope_type=range   (one per DIG range)
--   38     district_command      scope_type=district | commissionerate
--   1,000  sho                   scope_type=station
--   ~10,760 investigating_officer scope_type=assigned_case
--   1      system_admin          scope_type=platform
--
-- RANK IS NOT THE SEAT. Officer rank stays in Employee.RankID; the seat records
-- it in users.rank_label for display only. An SHO seat held by an ASI says
-- "Assistant Sub-Inspector", never "Police Inspector".
--
-- OFFICER SELECTION, AND WHY THE POOLS ARE WIDER THAN THE RANK NAME SUGGESTS
-- datagen assigns rank independently of post, so the establishment does not line
-- up with the org chart:
--   * 6 wings need an ADGP but only 4 exist -> pool widened to ADGP + IGP.
--   * 38 district commands need an SP but only 31 exist -> widened to SP + Addl.SP.
--   * 1,000 stations need a PI or PSI but only 728 stations have one -> the SHO is
--     the senior-most officer at that station AT OR BELOW PI rank, which yields a
--     realistic band (PI, PSI, ASI, and a small tail of HC/PC) instead of making a
--     DGP the chief of a rural station.
-- The rank distribution of the SHO seats is reported at the end so the shortfall
-- stays visible. The real fix is datagen/lookups.py::_load_employees (plan task 12).
--
-- LEAD INVESTIGATOR
-- is_lead_investigator = rank PI, PSI or ASI (Hierarchy <= 10). Head Constables
-- and Constables get seats to see the work assigned to them but cannot be the IO
-- of record. Designation is not used for this because the synthetic designations
-- are drawn at random relative to rank.

BEGIN;

-- ---------------------------------------------------------------------------
-- 0. Helper: officer establishment joined to rank hierarchy.
-- ---------------------------------------------------------------------------
CREATE TEMP TABLE _officer AS
SELECT e."EmployeeID", e."UnitID", e."DistrictID", e."FirstName",
       r."RankName", r."Hierarchy", dg."DesignationName"
  FROM "Employee" e
  JOIN "Rank" r ON r."RankID" = e."RankID"
  LEFT JOIN "Designation" dg ON dg."DesignationID" = e."DesignationID";

CREATE INDEX ON _officer ("UnitID", "Hierarchy");
CREATE INDEX ON _officer ("Hierarchy");

-- ---------------------------------------------------------------------------
-- 1. DGP — one state seat.
-- ---------------------------------------------------------------------------
INSERT INTO "users" (username, display_name, role_id, scope_type, employee_id,
                     rank_label, designation_label, posting_label,
                     is_active, must_reset_password, updated_by)
SELECT 'dgp.state', 'DGP ' || o."FirstName",
       (SELECT role_id FROM roles WHERE role_name = 'dgp_state_command'),
       'state', o."EmployeeID", o."RankName", 'Director General & IGP',
       'State Police Headquarters, Bengaluru', TRUE, TRUE, 'provision_seats'
  FROM _officer o WHERE o."Hierarchy" = 1
 ORDER BY o."EmployeeID" LIMIT 1
ON CONFLICT (username) DO UPDATE
  SET scope_type = 'state', employee_id = EXCLUDED.employee_id,
      rank_label = EXCLUDED.rank_label, posting_label = EXCLUDED.posting_label,
      updated_by = 'provision_seats';

-- ---------------------------------------------------------------------------
-- 2. ADGP wing seats — six, scope_type=wing.
-- ---------------------------------------------------------------------------
WITH pool AS (
    SELECT o.*, row_number() OVER (ORDER BY o."Hierarchy", o."EmployeeID") rn
      FROM _officer o WHERE o."Hierarchy" IN (2, 3)
),
slot AS (
    SELECT w."WingID", w."WingCode", w."WingName",
           row_number() OVER (ORDER BY w."WingID") rn
      FROM "Wing" w WHERE w."Active"
)
INSERT INTO "users" (username, display_name, role_id, scope_type, wing_id, employee_id,
                     rank_label, designation_label, posting_label,
                     is_active, must_reset_password, updated_by)
SELECT 'adgp.' || lower(s."WingCode"), 'ADGP ' || p."FirstName",
       (SELECT role_id FROM roles WHERE role_name = 'senior_command'),
       'wing', s."WingID", p."EmployeeID", p."RankName",
       'ADGP ' || s."WingName", s."WingName" || ', State Headquarters',
       TRUE, TRUE, 'provision_seats'
  FROM slot s JOIN pool p ON p.rn = s.rn
ON CONFLICT (username) DO UPDATE
  SET scope_type = 'wing', wing_id = EXCLUDED.wing_id,
      employee_id = EXCLUDED.employee_id, rank_label = EXCLUDED.rank_label,
      designation_label = EXCLUDED.designation_label,
      posting_label = EXCLUDED.posting_label, updated_by = 'provision_seats';

-- ---------------------------------------------------------------------------
-- 3. DIG range seats — seven, scope_type=range.
-- ---------------------------------------------------------------------------
WITH pool AS (
    SELECT o.*, row_number() OVER (ORDER BY o."EmployeeID") rn
      FROM _officer o WHERE o."Hierarchy" = 4
),
slot AS (
    SELECT r."RangeID", r."RangeCode", r."RangeName",
           row_number() OVER (ORDER BY r."RangeID") rn
      FROM "Range" r WHERE r."Active"
)
INSERT INTO "users" (username, display_name, role_id, scope_type, range_id, employee_id,
                     rank_label, designation_label, posting_label,
                     is_active, must_reset_password, updated_by)
SELECT 'dig.' || lower(s."RangeCode"), 'DIG ' || p."FirstName",
       (SELECT role_id FROM roles WHERE role_name = 'senior_command'),
       'range', s."RangeID", p."EmployeeID", p."RankName",
       'IGP/DIG ' || s."RangeName", s."RangeName",
       TRUE, TRUE, 'provision_seats'
  FROM slot s JOIN pool p ON p.rn = s.rn
ON CONFLICT (username) DO UPDATE
  SET scope_type = 'range', range_id = EXCLUDED.range_id,
      employee_id = EXCLUDED.employee_id, rank_label = EXCLUDED.rank_label,
      designation_label = EXCLUDED.designation_label,
      posting_label = EXCLUDED.posting_label, updated_by = 'provision_seats';

-- ---------------------------------------------------------------------------
-- 4. District command — 38 seats. SP for a district, CP for a Commissionerate.
-- ---------------------------------------------------------------------------
WITH pool AS (
    SELECT o.*, row_number() OVER (ORDER BY o."Hierarchy", o."EmployeeID") rn
      FROM _officer o WHERE o."Hierarchy" IN (5, 6)
),
slot AS (
    SELECT d."DistrictID", d."DistrictName", d."IsCommissionerate", d."CommandRank",
           row_number() OVER (ORDER BY d."IsCommissionerate" DESC, d."DistrictID") rn
      FROM "District" d WHERE d."Active"
)
INSERT INTO "users" (username, display_name, role_id, scope_type, district_id, employee_id,
                     rank_label, designation_label, posting_label,
                     is_active, must_reset_password, updated_by)
SELECT CASE WHEN s."IsCommissionerate" THEN 'cp.' ELSE 'sp.' END
         || regexp_replace(lower(s."DistrictName"), '[^a-z0-9]+', '', 'g'),
       CASE WHEN s."IsCommissionerate" THEN 'CP ' ELSE 'SP ' END || p."FirstName",
       (SELECT role_id FROM roles WHERE role_name = 'district_command'),
       CASE WHEN s."IsCommissionerate" THEN 'commissionerate' ELSE 'district' END,
       s."DistrictID", p."EmployeeID", p."RankName",
       CASE WHEN s."IsCommissionerate" THEN 'Commissioner of Police'
            ELSE 'Superintendent of Police' END,
       s."DistrictName" || CASE WHEN s."IsCommissionerate"
                                THEN ' Commissionerate' ELSE ' District' END,
       TRUE, TRUE, 'provision_seats'
  FROM slot s JOIN pool p ON p.rn = s.rn
ON CONFLICT (username) DO UPDATE
  SET scope_type = EXCLUDED.scope_type, district_id = EXCLUDED.district_id,
      employee_id = EXCLUDED.employee_id, rank_label = EXCLUDED.rank_label,
      designation_label = EXCLUDED.designation_label,
      posting_label = EXCLUDED.posting_label, updated_by = 'provision_seats';

-- ---------------------------------------------------------------------------
-- 5. SHO — one per police station. Senior-most officer AT OR BELOW PI rank.
-- ---------------------------------------------------------------------------
CREATE TEMP TABLE _sho AS
SELECT DISTINCT ON (o."UnitID")
       o."UnitID", o."EmployeeID", o."FirstName", o."RankName", o."Hierarchy"
  FROM _officer o
  JOIN "Unit" u ON u."UnitID" = o."UnitID"
 WHERE u."TypeID" = 1 AND o."Hierarchy" >= 8
 ORDER BY o."UnitID", o."Hierarchy", o."EmployeeID";

CREATE UNIQUE INDEX ON _sho ("EmployeeID");

INSERT INTO "users" (username, display_name, role_id, scope_type, unit_id, employee_id,
                     rank_label, designation_label, posting_label,
                     is_lead_investigator, is_active, must_reset_password, updated_by)
SELECT 'sho.' || s."UnitID", s."RankName" || ' ' || s."FirstName",
       (SELECT role_id FROM roles WHERE role_name = 'sho'),
       'station', s."UnitID", s."EmployeeID", s."RankName",
       'Station House Officer',
       u."UnitName" || ', ' || d."DistrictName",
       TRUE, TRUE, TRUE, 'provision_seats'
  FROM _sho s
  JOIN "Unit" u ON u."UnitID" = s."UnitID"
  JOIN "District" d ON d."DistrictID" = u."DistrictID"
ON CONFLICT (username) DO UPDATE
  SET scope_type = 'station', unit_id = EXCLUDED.unit_id,
      employee_id = EXCLUDED.employee_id, rank_label = EXCLUDED.rank_label,
      designation_label = EXCLUDED.designation_label,
      posting_label = EXCLUDED.posting_label,
      is_lead_investigator = TRUE, updated_by = 'provision_seats';

-- ---------------------------------------------------------------------------
-- 6. Investigating officers — every officer PI or below not holding an SHO seat.
--    is_lead_investigator only for PI / PSI / ASI.
-- ---------------------------------------------------------------------------
INSERT INTO "users" (username, display_name, role_id, scope_type, unit_id, employee_id,
                     rank_label, designation_label, posting_label,
                     is_lead_investigator, is_active, must_reset_password, updated_by)
SELECT 'io.' || o."EmployeeID", o."RankName" || ' ' || o."FirstName",
       (SELECT role_id FROM roles WHERE role_name = 'investigating_officer'),
       'assigned_case', o."UnitID", o."EmployeeID", o."RankName",
       CASE WHEN o."Hierarchy" <= 10 THEN 'Investigating Officer'
            ELSE 'Case Assistant' END,
       u."UnitName" || ', ' || d."DistrictName",
       (o."Hierarchy" <= 10), TRUE, TRUE, 'provision_seats'
  FROM _officer o
  JOIN "Unit" u ON u."UnitID" = o."UnitID" AND u."TypeID" = 1
  JOIN "District" d ON d."DistrictID" = u."DistrictID"
 WHERE o."Hierarchy" >= 8
   AND NOT EXISTS (SELECT 1 FROM _sho s WHERE s."EmployeeID" = o."EmployeeID")
ON CONFLICT (username) DO UPDATE
  SET scope_type = 'assigned_case', unit_id = EXCLUDED.unit_id,
      employee_id = EXCLUDED.employee_id, rank_label = EXCLUDED.rank_label,
      designation_label = EXCLUDED.designation_label,
      posting_label = EXCLUDED.posting_label,
      is_lead_investigator = EXCLUDED.is_lead_investigator,
      updated_by = 'provision_seats';

-- ---------------------------------------------------------------------------
-- 7. Platform admin.
-- ---------------------------------------------------------------------------
INSERT INTO "users" (username, display_name, role_id, scope_type,
                     designation_label, posting_label,
                     is_active, must_reset_password, updated_by)
VALUES ('sysadmin', 'Platform Administrator',
        (SELECT role_id FROM roles WHERE role_name = 'system_admin'),
        'platform', 'System Administrator', 'State Police Headquarters',
        TRUE, TRUE, 'provision_seats')
ON CONFLICT (username) DO UPDATE
  SET scope_type = 'platform', updated_by = 'provision_seats';

-- ---------------------------------------------------------------------------
-- 8. Give the pre-existing demo logins a real posting, so the seeded usernames
--    referenced by web/src/config/roles.ts and app/roles.py DEMO_USERS keep
--    working instead of resolving to 'unresolved' and seeing nothing.
-- ---------------------------------------------------------------------------
UPDATE "users" u SET scope_type = 'state', updated_by = 'provision_seats'
 WHERE u.username = 'dgp.vikram';

UPDATE "users" u SET scope_type = 'range', range_id = r."RangeID",
                     posting_label = r."RangeName", updated_by = 'provision_seats'
  FROM "Range" r WHERE r."RangeCode" = 'CR' AND u.username = 'igp.meenakshi';

UPDATE "users" u SET scope_type = 'wing', wing_id = w."WingID",
                     posting_label = w."WingName", updated_by = 'provision_seats'
  FROM "Wing" w
 WHERE (u.username, w."WingCode") IN
       (('analyst.divya','CTS'), ('analyst.kavya','CTS'),
        ('cyber.arjun','ISC'), ('traffic.latha','TRF'));

-- dcp.anand held the legacy `policymaker` role, which migration 028 folds into
-- senior_command. A DCP commands a city district, not a wing or a range, so the
-- seat is moved to district_command as well — otherwise it would carry
-- scope_type='district' under a role whose allowed_scope_types are wing|range,
-- which the seat-consistency check below rejects.
UPDATE "users"
   SET role_id = (SELECT role_id FROM roles WHERE role_name = 'district_command'),
       updated_by = 'provision_seats'
 WHERE username = 'dcp.anand';

UPDATE "users" u SET scope_type = 'district', district_id = d."DistrictID",
                     posting_label = d."DistrictName" || ' District',
                     updated_by = 'provision_seats'
  FROM "District" d
 WHERE (u.username, d."DistrictName") IN
       (('sp.anand','Mysuru'), ('dysp.kavya','Mandya'), ('dcp.anand','Belagavi'));

UPDATE "users" u SET scope_type = 'station', unit_id = s."UnitID",
                     posting_label = (SELECT "UnitName" FROM "Unit" WHERE "UnitID" = s."UnitID"),
                     is_lead_investigator = TRUE, updated_by = 'provision_seats'
  FROM (SELECT min("UnitID") AS "UnitID" FROM "Unit" WHERE "TypeID" = 1) s
 WHERE u.username = 'sho.suresh';

UPDATE "users" u SET scope_type = 'assigned_case', unit_id = s."UnitID",
                     posting_label = (SELECT "UnitName" FROM "Unit" WHERE "UnitID" = s."UnitID"),
                     rank_label = 'Police Sub-Inspector',
                     is_lead_investigator = TRUE, updated_by = 'provision_seats'
  FROM (SELECT min("UnitID") AS "UnitID" FROM "Unit" WHERE "TypeID" = 1) s
 WHERE u.username = 'io.ramesh';

UPDATE "users" SET scope_type = 'platform', updated_by = 'provision_seats'
 WHERE username = 'admin';

COMMIT;

-- ---------------------------------------------------------------------------
-- REPORT
-- ---------------------------------------------------------------------------
SELECT '--- seats by role and scope ---' AS report;
SELECT rpad(r.role_name, 24) || rpad(u.scope_type, 18) || count(*) AS report
  FROM users u JOIN roles r ON r.role_id = u.role_id
 GROUP BY r.role_name, u.scope_type ORDER BY 1;

SELECT '--- total seats ---' AS report;
SELECT count(*)::text AS report FROM users;

SELECT '--- SHO seats by ACTUAL officer rank (the generator shortfall) ---' AS report;
SELECT rpad(rank_label, 30) || count(*) AS report
  FROM users WHERE scope_type = 'station'
 GROUP BY rank_label ORDER BY count(*) DESC;

SELECT '--- IO seats: lead investigator vs assisting ---' AS report;
SELECT rpad(rank_label, 30) || rpad(is_lead_investigator::text, 8) || count(*) AS report
  FROM users WHERE scope_type = 'assigned_case'
 GROUP BY rank_label, is_lead_investigator ORDER BY count(*) DESC;

SELECT '--- unresolved seats (must be zero) ---' AS report;
SELECT count(*)::text AS report FROM users WHERE scope_type = 'unresolved';

-- Rule 4 from migration 035: a seat's scope_type must appear in its role's
-- allowed_scope_types. Enforced in the API, checked here because provisioning
-- writes seats directly and a mismatch is otherwise invisible until a dashboard
-- renders the wrong board.
SELECT '--- seats whose scope_type is not allowed by their role (must be zero) ---' AS report;
SELECT count(*)::text AS report
  FROM users u JOIN roles r ON r.role_id = u.role_id
 WHERE r.allowed_scope_types IS NOT NULL
   AND NOT (u.scope_type = ANY (r.allowed_scope_types));

SELECT '--- offending seats, if any ---' AS report;
SELECT rpad(u.username, 20) || rpad(r.role_name, 24) || rpad(u.scope_type, 18)
       || 'allowed=' || array_to_string(r.allowed_scope_types, '|') AS report
  FROM users u JOIN roles r ON r.role_id = u.role_id
 WHERE r.allowed_scope_types IS NOT NULL
   AND NOT (u.scope_type = ANY (r.allowed_scope_types));

-- Each seat must carry exactly the anchor its scope_type requires. The CHECK
-- constraint guarantees this per row; this confirms it across the whole set.
SELECT '--- seats missing their scope anchor (must be zero) ---' AS report;
SELECT count(*)::text AS report FROM users
 WHERE (scope_type = 'wing'            AND wing_id     IS NULL)
    OR (scope_type = 'range'           AND range_id    IS NULL)
    OR (scope_type IN ('district','commissionerate') AND district_id IS NULL)
    OR (scope_type IN ('station','assigned_case')    AND unit_id     IS NULL);
