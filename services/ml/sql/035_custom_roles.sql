-- DRISHTI migration 035: admin-created roles with arbitrary permissions.
--
-- WHY
-- Roles were a fixed set defined in code and seeded in SQL. Admin needs to create
-- a role of any kind and compose any permission onto it — a Coastal Security cell,
-- a Dasara duty commander, a District Crime Records analyst — without a deploy.
--
-- WHY NOT role_permissions
-- role_permissions.action is permission_action_enum = ('read','write','none').
-- "Any kind of permission" needs verbs that enum cannot express (approve, export,
-- assign, dispatch, override). ALTER TYPE ... ADD VALUE would work but PostgreSQL
-- cannot REMOVE an enum value, so extending it would make this migration
-- irreversible. A catalogue table with a text action is fully reversible and
-- open-ended.
--
-- role_permissions is kept and maintained as a legacy PROJECTION, because the
-- whitelisted-SELECT executor and the Phase-14 RLS design both read it. Read/write
-- grants are mirrored into it; richer verbs live only in role_grant.
--
-- SEPARATION OF CONCERNS (§0 of the plan) is preserved:
--   permission  -> role_grant            (what actions)
--   UI surface  -> roles.base_surface + role_ui_grants  (what is rendered)
--   scope       -> users.scope_type      (how much data)
-- A custom role composes permissions and a UI surface. It never carries a scope:
-- scope belongs to the seat, so the same custom role can be issued at district
-- level to one officer and at state level to another.
--
-- NOT AN ENFORCEMENT BOUNDARY YET. Authentication and RLS are off in this phase,
-- so these grants describe intent and drive the UI. They become enforcing when the
-- capability matrix and RLS land.

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. Permission catalogue — the vocabulary admin composes from.
--    A catalogue rather than free text so the console offers real choices and a
--    typo cannot invent a permission nothing checks.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "permission_catalogue" (
    "permission_key" VARCHAR PRIMARY KEY,
    "resource"       VARCHAR NOT NULL,
    "action"         VARCHAR NOT NULL,
    "label"          VARCHAR NOT NULL,
    "description"    TEXT,
    "category"       VARCHAR NOT NULL,
    "is_sensitive"   BOOLEAN NOT NULL DEFAULT FALSE,
    "requires_scope" VARCHAR,
    "created_at"     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT "uq_permission_resource_action" UNIQUE ("resource", "action")
);

COMMENT ON TABLE "permission_catalogue" IS
    'Every permission that exists, as resource+action. Admin composes roles from these rows; the console reads it to build the grant picker.';
COMMENT ON COLUMN "permission_catalogue"."is_sensitive" IS
    'TRUE for permissions that expose PII or coercive capability. The console requires explicit confirmation and records a reason before granting one.';
COMMENT ON COLUMN "permission_catalogue"."requires_scope" IS
    'Narrowest scope_type at which this permission is meaningful, or NULL for any. Granting case_detail.read to a state seat is refused because that seat is aggregate-only.';

INSERT INTO "permission_catalogue"
    ("permission_key","resource","action","label","category","is_sensitive","requires_scope","description") VALUES
  -- Case work
  ('cases.read',            'cases','read',        'View case list',            'Case work', FALSE, NULL,'Aggregate and list-level case access within scope.'),
  ('cases.detail_read',     'cases','detail_read', 'Open case file',            'Case work', TRUE,  'district','Full FIR detail including parties. PII-bearing.'),
  ('cases.write',           'cases','write',       'Edit case',                 'Case work', TRUE,  'station','Add evidence, statements and court updates.'),
  ('cases.assign_io',       'cases','assign_io',   'Assign investigating officer','Case work', TRUE,'station','Record who is the IO of a case.'),
  ('cases.reassign',        'cases','reassign',    'Transfer case',             'Case work', TRUE,  'station','Move a case between officers or stations.'),
  ('cases.close',           'cases','close',       'Close or dispose case',     'Case work', TRUE,  'station','Record a final disposition.'),
  -- Intake
  ('intake.create',         'intake','create',     'Register FIR',              'Intake',    TRUE,  'station','Create a new FIR or case record.'),
  ('intake.review',         'intake','review',     'Review intake queue',       'Intake',    FALSE, 'station','Approve, return or reject a submitted draft.'),
  ('intake.import',         'intake','import',     'Bulk import',               'Intake',    TRUE,  NULL,'Commit or roll back a structured import.'),
  ('intake.override_jurisdiction','intake','override_jurisdiction','Override jurisdiction','Intake',TRUE,'district','Audited district override at intake.'),
  -- People and entities
  ('entities.read',         'entities','read',     'View entities',             'People',    FALSE, NULL,'Person, vehicle, phone and account records.'),
  ('entities.pii_read',     'entities','pii_read', 'View personal details',     'People',    TRUE,  'district','Names, addresses and identifiers.'),
  ('entities.resolve',      'entities','resolve',  'Merge or split identities', 'People',    TRUE,  'district','Entity-resolution review decisions.'),
  -- Analysis
  ('network.read',          'network','read',      'Link analysis',             'Analysis',  FALSE, NULL,'Communities, associations and path finding.'),
  ('money.read',            'money','read',        'Money trail',               'Analysis',  TRUE,  NULL,'Accounts, transactions and flagged flows.'),
  ('board.use',             'board','use',         'Investigation board',       'Analysis',  FALSE, NULL,'Open and edit an investigation board.'),
  ('board.share',           'board','share',       'Share or lock board',       'Analysis',  FALSE, NULL,'Publish, lock or promote a board.'),
  ('analytics.read',        'analytics','read',    'Analytics and forecasting', 'Analysis',  FALSE, NULL,'Trends, correlations and model explainability.'),
  ('map.read',              'map','read',          'Map and hotspots',          'Analysis',  FALSE, NULL,'Geospatial hotspots and alerts.'),
  ('map.point_read',        'map','point_read',    'Individual incident points','Analysis',  TRUE,  'district','Point-level map data rather than aggregates.'),
  ('ask.use',               'ask','use',           'Ask DRISHTI',               'Analysis',  FALSE, NULL,'Natural-language querying within scope.'),
  -- Command
  ('dashboard.read',        'dashboard','read',    'Command dashboard',         'Command',   FALSE, NULL,'Aggregate KPI board for the seat scope.'),
  ('performance.read',      'performance','read',  'Station and officer performance','Command',FALSE,NULL,'Workload, throughput and load balance.'),
  ('export.aggregate',      'export','aggregate',  'Export aggregates',         'Command',   FALSE, NULL,'Download aggregate figures.'),
  ('export.case_data',      'export','case_data',  'Export case data',          'Command',   TRUE,  'district','Download case-level extracts. Audited.'),
  -- Emergency response
  ('disaster.read',         'disaster','read',     'Emergency situation view',  'Emergency', FALSE, NULL,'Hazards, resources and readiness.'),
  ('disaster.allocate',     'disaster','allocate', 'Allocate resources',        'Emergency', TRUE,  'district','Assign and dispatch response resources.'),
  ('disaster.approve',      'disaster','approve',  'Approve response plan',     'Emergency', TRUE,  'district','Approve warnings, evacuations and plans.'),
  -- Governance and platform
  ('governance.run',        'governance','run',    'Run governed pipeline',     'Governance',FALSE, NULL,'Trigger a governed model pipeline.'),
  ('governance.approve',    'governance','approve','Approve prediction',        'Governance',TRUE,  NULL,'Human review of a governed prediction.'),
  ('models.read',           'models','read',       'Model registry',            'Governance',FALSE, NULL,'Model versions, drift and calibration.'),
  ('models.write',          'models','write',      'Manage model registry',     'Governance',TRUE,  NULL,'Register, promote or retire a model.'),
  ('quality.review',        'quality','review',    'Data-quality queues',       'Governance',FALSE, NULL,'Quality, entity and jurisdiction review.'),
  ('audit.read',            'audit','read',        'Audit trail',               'Governance',TRUE,  NULL,'Read the append-only audit log.'),
  ('admin.seats',           'admin','seats',       'Manage seats',              'Platform',  TRUE,  NULL,'Create, edit and deactivate user seats.'),
  ('admin.roles',           'admin','roles',       'Manage roles',              'Platform',  TRUE,  NULL,'Create roles and compose permissions.'),
  ('admin.ui_visibility',   'admin','ui_visibility','Manage UI visibility',     'Platform',  FALSE, NULL,'Toggle destinations, boards, cards and widgets per role.'),
  ('admin.feature_flags',   'admin','feature_flags','Manage feature flags',     'Platform',  FALSE, NULL,'Enable or disable optional capabilities.')
ON CONFLICT ("permission_key") DO UPDATE
    SET "label" = EXCLUDED."label", "description" = EXCLUDED."description",
        "category" = EXCLUDED."category", "is_sensitive" = EXCLUDED."is_sensitive",
        "requires_scope" = EXCLUDED."requires_scope";

-- ---------------------------------------------------------------------------
-- 2. Role metadata for admin-created roles.
-- ---------------------------------------------------------------------------
ALTER TABLE "roles" ADD COLUMN IF NOT EXISTS "created_by"  VARCHAR;
ALTER TABLE "roles" ADD COLUMN IF NOT EXISTS "base_surface" VARCHAR;
ALTER TABLE "roles" ADD COLUMN IF NOT EXISTS "allowed_scope_types" VARCHAR[];

-- A custom role must render SOMETHING. base_surface names which of the six
-- built-in UI surfaces it starts from; role_ui_grants then trims or extends it.
-- This is why a new role needs no new rendering code.
ALTER TABLE "roles" DROP CONSTRAINT IF EXISTS "chk_roles_base_surface";
ALTER TABLE "roles" ADD CONSTRAINT "chk_roles_base_surface" CHECK (
    "base_surface" IS NULL OR "base_surface" IN (
        'state_command', 'senior_command', 'district_command',
        'station', 'case_work', 'platform'));

COMMENT ON COLUMN "roles"."base_surface" IS
    'Which built-in UI surface a role renders. role_ui_grants then trims or extends it, so an admin-created role needs no new frontend code.';
COMMENT ON COLUMN "roles"."allowed_scope_types" IS
    'scope_types a seat holding this role may be assigned. NULL means any. Prevents e.g. a station-only role being issued as a state seat.';

UPDATE "roles" SET "base_surface" = v.surface,
                   "allowed_scope_types" = v.scopes
  FROM (VALUES
        ('dgp_state_command',     'state_command',    ARRAY['state']),
        ('senior_command',        'senior_command',   ARRAY['wing','range']),
        ('district_command',      'district_command', ARRAY['district','commissionerate']),
        ('sho',                   'station',          ARRAY['station']),
        ('investigating_officer', 'case_work',        ARRAY['assigned_case']),
        ('system_admin',          'platform',         ARRAY['platform'])
       ) AS v(role_name, surface, scopes)
 WHERE "roles"."role_name" = v.role_name;

-- ---------------------------------------------------------------------------
-- 3. role_grant — the composable permission set.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "role_grant" (
    "id"             INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    "role_name"      VARCHAR NOT NULL REFERENCES "roles" ("role_name") ON DELETE CASCADE,
    "permission_key" VARCHAR NOT NULL REFERENCES "permission_catalogue" ("permission_key"),
    "granted"        BOOLEAN NOT NULL DEFAULT TRUE,
    "reason"         TEXT,
    "granted_by"     VARCHAR,
    "granted_at"     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT "uq_role_grant" UNIQUE ("role_name", "permission_key")
);

CREATE INDEX IF NOT EXISTS "idx_role_grant_role" ON "role_grant" ("role_name")
    WHERE "granted" = TRUE;

COMMENT ON TABLE "role_grant" IS
    'Composable permission grants per role, including admin-created roles. Supersedes role_permissions for anything beyond read/write; role_permissions is maintained as a legacy projection for the whitelisted-SELECT executor.';
COMMENT ON COLUMN "role_grant"."reason" IS
    'Required by the console when granting a permission flagged is_sensitive. Recorded in the audit trail.';

-- INTERIM, matching the policy already in force elsewhere: the six built-in roles
-- receive every catalogued permission. Narrowing this is the capability-matrix
-- task, tracked in the plan's pre-real-data section, and is deliberately NOT done
-- here so this migration changes no effective access.
INSERT INTO "role_grant" ("role_name", "permission_key", "granted", "granted_by", "reason")
SELECT r."role_name", pc."permission_key", TRUE, 'migration:035',
       'Interim: built-in roles hold every permission pending the capability matrix.'
  FROM "roles" r
 CROSS JOIN "permission_catalogue" pc
 WHERE r."is_system" = TRUE
ON CONFLICT ("role_name", "permission_key") DO NOTHING;

ALTER TABLE "permission_catalogue" DISABLE ROW LEVEL SECURITY;
ALTER TABLE "role_grant"           DISABLE ROW LEVEL SECURITY;

COMMIT;

-- ---------------------------------------------------------------------------
-- Admin API this backs
--   GET    /admin/permissions                  catalogue, grouped by category
--   GET    /admin/roles                        roles + grant counts + surface
--   POST   /admin/roles                        create: name, label, base_surface,
--                                              allowed_scope_types, permission set
--   PUT    /admin/roles/{role}/grants          replace the grant set
--   PATCH  /admin/roles/{role}/grants/{key}    toggle one grant
--   DELETE /admin/roles/{role}                 delete a custom role (is_system=FALSE
--                                              only, and only with zero seats)
--
-- Server-side rules the API must enforce, none of which SQL can express alone:
--   1. is_system roles cannot be renamed or deleted.
--   2. A grant whose requires_scope is narrower than a seat's scope_type is
--      refused, so an aggregate-only state seat cannot receive cases.detail_read.
--   3. Granting is_sensitive requires a reason, written to audit_logs.
--   4. A seat's scope_type must appear in its role's allowed_scope_types.
--   5. role_permissions is re-projected from role_grant on every change, so the
--      legacy executor stays consistent.
-- ---------------------------------------------------------------------------
