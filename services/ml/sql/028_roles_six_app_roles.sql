-- DRISHTI migration 028: collapse ten presentation seats into six application roles.
--
-- WHY
-- The ten seeded roles conflated two different things: the UI surface a seat
-- needs, and the data breadth it carries. `adgp_igp_range` was the clearest
-- symptom — one role covering ADGP (functional, state-wide) and IGP/DIG
-- (geographic, multi-district), which have the same UI surface but completely
-- different scope. Three more (crime_analyst, cyber_cell, traffic_command) were
-- really ADGP wings wearing role names.
--
-- The application role now answers only "which UI surface", and scope_type
-- (migration 027) answers "how much data":
--
--   dgp_state_command     scope_type=state
--   senior_command        scope_type=wing   (ADGP)  | range (DIG/IGP)
--   district_command      scope_type=district (SP)  | commissionerate (CP)
--   sho                   scope_type=station
--   investigating_officer scope_type=assigned_case
--   system_admin          scope_type=platform
--
-- REMAPPING
--   dgp_state_command     -> dgp_state_command      (unchanged)
--   adgp_igp_range        -> senior_command
--   crime_analyst         -> senior_command   (wing: Crime & Technical Services)
--   cyber_cell            -> senior_command   (wing: Internal Security & Cyber)
--   traffic_command       -> senior_command   (wing: Traffic & Road Safety)
--   sp_district_command   -> district_command
--   dysp_acp              -> district_command  (sub-division tier deferred:
--                                               no Circle/Sub-Division Unit rows
--                                               exist to anchor it)
--   sho                   -> sho                    (unchanged)
--   investigating_officer -> investigating_officer   (unchanged)
--   system_admin          -> system_admin            (unchanged)
--
-- The live database also still carries the PRE-ten-role vocabulary (verified on
-- RDS: 15 roles, not 10). Those are remapped too, or they would survive this
-- migration and leave eleven roles instead of six:
--   investigator          -> investigating_officer
--   supervisor            -> sho
--   analyst               -> senior_command      (was the crime-analyst seat)
--   policymaker           -> senior_command      (served the IGP/SP board)
--   super_admin           -> system_admin
--
-- REVERSIBILITY
-- users.legacy_role_name preserves the pre-migration role name, so the rollback
-- restores each seat to the exact role it held. Without it the remap would be
-- lossy: three former roles all collapse onto senior_command and could not be
-- told apart afterwards.

BEGIN;

-- ---------------------------------------------------------------------------
-- 0. Preserve the pre-migration role name so the rollback is faithful.
-- ---------------------------------------------------------------------------
ALTER TABLE "users" ADD COLUMN IF NOT EXISTS "legacy_role_name" VARCHAR;

UPDATE "users" u
   SET "legacy_role_name" = r."role_name"
  FROM "roles" r
 WHERE r."role_id" = u."role_id"
   AND u."legacy_role_name" IS NULL;

COMMENT ON COLUMN "users"."legacy_role_name" IS
    'Role held before migration 028 collapsed ten seats into six. Retained solely so the rollback can restore the original assignment; not read by the application.';

-- ---------------------------------------------------------------------------
-- 1. The six application roles.
-- ---------------------------------------------------------------------------
INSERT INTO "roles" ("role_name", "description", "is_system") VALUES
    ('dgp_state_command',
     'State command: state-wide priorities, escalations and outcomes. Aggregate-only.', TRUE),
    ('senior_command',
     'Senior command. scope_type=wing for an ADGP functional wing (state-wide, crime-head narrowed); scope_type=range for an IGP/DIG range (multi-district).', TRUE),
    ('district_command',
     'District command. scope_type=district for an SP; scope_type=commissionerate for a CP.', TRUE),
    ('sho',
     'Station chief: registration, assignment and the station review queue.', TRUE),
    ('investigating_officer',
     'Field IO: assigned cases, evidence, statements and leads.', TRUE),
    ('system_admin',
     'Platform administration: seats, roles, UI visibility, model registry and governance.', TRUE)
ON CONFLICT ("role_name") DO UPDATE
    SET "description" = EXCLUDED."description",
        "is_system"   = EXCLUDED."is_system";

-- ---------------------------------------------------------------------------
-- 2. Remap every user onto its new role.
-- ---------------------------------------------------------------------------
UPDATE "users" u
   SET "role_id" = tgt."role_id"
  FROM "roles" old
  JOIN (VALUES
        ('adgp_igp_range',      'senior_command'),
        ('crime_analyst',       'senior_command'),
        ('cyber_cell',          'senior_command'),
        ('traffic_command',     'senior_command'),
        ('sp_district_command', 'district_command'),
        ('dysp_acp',            'district_command'),
        -- pre-ten-role vocabulary still present on RDS
        ('investigator',        'investigating_officer'),
        ('supervisor',          'sho'),
        ('analyst',             'senior_command'),
        ('policymaker',         'senior_command'),
        ('super_admin',         'system_admin')
       ) AS m(from_role, to_role) ON m.from_role = old."role_name"
  JOIN "roles" tgt ON tgt."role_name" = m.to_role
 WHERE old."role_id" = u."role_id";

-- ---------------------------------------------------------------------------
-- 3. Rebuild the permission matrix for the six roles.
--    INTERIM, unchanged in substance from the previous seed: every role is
--    granted write on every resource. Authentication and RLS are off in this
--    phase, so this table is not yet an enforcement boundary. Narrowing it is
--    tracked as a pre-real-data task, not done here.
-- ---------------------------------------------------------------------------
DELETE FROM "role_permissions"
 WHERE "role_id" IN (SELECT "role_id" FROM "roles" WHERE "role_name" IN (
        'adgp_igp_range', 'crime_analyst', 'cyber_cell', 'traffic_command',
        'sp_district_command', 'dysp_acp',
        'investigator', 'supervisor', 'analyst', 'policymaker', 'super_admin'));

INSERT INTO "role_permissions" ("role_id", "resource", "action")
SELECT r."role_id", v.resource, 'write'::permission_action_enum
  FROM "roles" r
 CROSS JOIN (VALUES
        ('command_center'), ('cases'), ('people_entities'), ('network_analysis'),
        ('money_trail'), ('map'), ('analytics'), ('ask_drishti'),
        ('admin_governance'), ('pii')
       ) AS v(resource)
 WHERE r."role_name" IN ('dgp_state_command', 'senior_command', 'district_command',
                         'sho', 'investigating_officer', 'system_admin')
ON CONFLICT ("role_id", "resource", "action") DO NOTHING;

-- ---------------------------------------------------------------------------
-- 4. Retire the four superseded roles, now that nothing references them.
-- ---------------------------------------------------------------------------
DELETE FROM "roles"
 WHERE "role_name" IN ('adgp_igp_range', 'crime_analyst', 'cyber_cell',
                       'traffic_command', 'sp_district_command', 'dysp_acp',
                       'investigator', 'supervisor', 'analyst', 'policymaker',
                       'super_admin')
   AND NOT EXISTS (SELECT 1 FROM "users" u WHERE u."role_id" = "roles"."role_id");

COMMIT;
