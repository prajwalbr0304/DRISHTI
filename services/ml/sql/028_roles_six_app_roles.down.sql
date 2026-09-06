-- Rollback for DRISHTI migration 028 (six application roles).
--
-- Restores the ten original roles and puts every seat back on the role recorded
-- in users.legacy_role_name, so the three wings that collapsed onto
-- senior_command (crime_analyst, cyber_cell, traffic_command) are separated
-- again correctly rather than guessed at.
--
-- Seats created AFTER migration 028 have no legacy_role_name — every one of the
-- 1,046 provisioned seats falls in that class. They are mapped back by
-- scope_type in step 2b, because without it they would be stranded on
-- senior_command / district_command, step 4 would rightly refuse to delete a
-- role still in use, and the rollback would leave twelve roles instead of ten.
--
-- This down migration MUST run before 027's, which drops users.scope_type that
-- step 2b depends on. The documented reverse order (032 -> 026) satisfies that.

BEGIN;

-- 1. Recreate the ten command roles plus the five pre-ten-role legacy names that
--    were present on RDS, so a rollback restores the database as it actually was
--    rather than as the ten-role design assumed it to be.
INSERT INTO "roles" ("role_name", "description", "is_system") VALUES
    ('investigator', 'Legacy pre-command-role seat: field investigator.',        TRUE),
    ('supervisor',   'Legacy pre-command-role seat: station supervisor.',        TRUE),
    ('analyst',      'Legacy pre-command-role seat: crime analyst.',             TRUE),
    ('policymaker',  'Legacy pre-command-role seat: district/range policymaker.',TRUE),
    ('super_admin',  'Legacy pre-command-role seat: platform super admin.',      TRUE)
ON CONFLICT ("role_name") DO NOTHING;

INSERT INTO "roles" ("role_name", "description", "is_system") VALUES
    ('dgp_state_command',     'State command: state-wide priorities, escalations and outcomes.',      TRUE),
    ('adgp_igp_range',        'Range command: oversight and comparison across the range''s districts.', TRUE),
    ('sp_district_command',   'District command: workload, approvals and station performance.',        TRUE),
    ('dysp_acp',              'Sub-divisional oversight: case review, quality and escalation.',        TRUE),
    ('sho',                   'Station chief: registration, assignment and the station review queue.', TRUE),
    ('investigating_officer', 'Field IO: assigned cases, evidence, statements and leads.',             TRUE),
    ('crime_analyst',         'Crime analysis: patterns, networks, hotspots and forecasting.',         TRUE),
    ('cyber_cell',            'Cyber / financial crime: money trail, devices and accounts.',           TRUE),
    ('traffic_command',       'Traffic command: road-safety hotspots and enforcement load.',           TRUE),
    ('system_admin',          'Platform administration: credentials, model registry and governance.',  TRUE)
ON CONFLICT ("role_name") DO NOTHING;

-- 2a. Restore each pre-028 seat to the exact role it held.
UPDATE "users" u
   SET "role_id" = r."role_id"
  FROM "roles" r
 WHERE r."role_name" = u."legacy_role_name"
   AND u."legacy_role_name" IS NOT NULL;

-- 2b. Map post-028 seats back by scope_type. senior_command splits by scope
--     into the single role that previously covered both ADGP and DIG, and
--     district_command collapses onto the SP role for either scope.
-- Every correlation sits in WHERE, not in a JOIN ... ON. PostgreSQL forbids
-- referencing the UPDATE target alias from a join condition inside the FROM
-- list, so the scope_type match must be a WHERE predicate.
UPDATE "users" u
   SET "role_id" = tgt."role_id"
  FROM "roles" cur,
       "roles" tgt,
       (VALUES
        ('senior_command',   'wing',            'adgp_igp_range'),
        ('senior_command',   'range',           'adgp_igp_range'),
        ('senior_command',   'unresolved',      'adgp_igp_range'),
        ('district_command', 'district',        'sp_district_command'),
        ('district_command', 'commissionerate', 'sp_district_command'),
        ('district_command', 'unresolved',      'sp_district_command')
       ) AS m(from_role, scope_type, to_role)
 WHERE cur."role_id"   = u."role_id"
   AND m.from_role     = cur."role_name"
   AND m.scope_type    = u."scope_type"
   AND tgt."role_name" = m.to_role
   AND u."legacy_role_name" IS NULL;

-- 3. Restore the interim all-roles-all-resources grant for the ten roles.
INSERT INTO "role_permissions" ("role_id", "resource", "action")
SELECT r."role_id", v.resource, 'write'::permission_action_enum
  FROM "roles" r
 CROSS JOIN (VALUES
        ('command_center'), ('cases'), ('people_entities'), ('network_analysis'),
        ('money_trail'), ('map'), ('analytics'), ('ask_drishti'),
        ('admin_governance'), ('pii')
       ) AS v(resource)
 WHERE r."role_name" IN (
        'dgp_state_command', 'adgp_igp_range', 'sp_district_command', 'dysp_acp',
        'sho', 'investigating_officer', 'crime_analyst', 'cyber_cell',
        'traffic_command', 'system_admin',
        'investigator', 'supervisor', 'analyst', 'policymaker', 'super_admin')
ON CONFLICT ("role_id", "resource", "action") DO NOTHING;

-- 4. Remove the two roles that only exist post-028, once unreferenced.
DELETE FROM "role_permissions"
 WHERE "role_id" IN (SELECT "role_id" FROM "roles"
                      WHERE "role_name" IN ('senior_command', 'district_command'));

DELETE FROM "roles"
 WHERE "role_name" IN ('senior_command', 'district_command')
   AND NOT EXISTS (SELECT 1 FROM "users" u WHERE u."role_id" = "roles"."role_id");

ALTER TABLE "users" DROP COLUMN IF EXISTS "legacy_role_name";

COMMIT;

-- Verification: any seat still on a post-028 role needs manual assignment.
-- SELECT u."user_id", u."username", r."role_name"
--   FROM "users" u JOIN "roles" r ON r."role_id" = u."role_id"
--  WHERE r."role_name" IN ('senior_command', 'district_command');
