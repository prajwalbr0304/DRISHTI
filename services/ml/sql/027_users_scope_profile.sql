-- DRISHTI migration 027: seat scope anchors + admin-editable profile on users.
--
-- WHY (scope)
-- `users` carried exactly one scope column, `unit_id`. That cannot express a
-- wing, a range or a district, so nine of the ten seats had nowhere to record
-- their posting and all ten seeded demo users were left with unit_id NULL.
-- The consequence, documented in app/org/scope.py derive_scope, is that an SHO
-- and a DGP resolved to identical unbounded scope.
--
-- One anchor per scope_type, enforced by a CHECK so a half-provisioned seat
-- fails loudly at insert instead of silently widening to state-wide:
--   state | platform    -> no anchor
--   wing                -> wing_id
--   range               -> range_id
--   district | commissionerate -> district_id
--   station             -> unit_id
--   assigned_case       -> unit_id (home station; case set resolved per request)
--
-- WHY (profile)
-- Admin needs to edit a seat's display name and profile. `display_name` already
-- existed; the rest of the editable surface did not.
--
-- SEPARATION OF CONCERNS
-- employee_id links a login seat to its establishment row WITHOUT copying rank
-- or designation onto users. Rank stays in Employee.RankID, assignment in
-- Employee.DesignationID, scope here, permissions in role_permissions. Nothing
-- in this migration grants anything.

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. Scope anchors
-- ---------------------------------------------------------------------------
ALTER TABLE "users" ADD COLUMN IF NOT EXISTS "scope_type"  VARCHAR;
ALTER TABLE "users" ADD COLUMN IF NOT EXISTS "wing_id"     INTEGER REFERENCES "Wing" ("WingID");
ALTER TABLE "users" ADD COLUMN IF NOT EXISTS "range_id"    INTEGER REFERENCES "Range" ("RangeID");
ALTER TABLE "users" ADD COLUMN IF NOT EXISTS "district_id" INTEGER REFERENCES "District" ("DistrictID");
ALTER TABLE "users" ADD COLUMN IF NOT EXISTS "employee_id" INTEGER REFERENCES "Employee" ("EmployeeID");

-- Existing rows predate scope typing. 'unresolved' is deliberate: the scope
-- resolver must treat it as "no posting on record", never as state-wide.
UPDATE "users" SET "scope_type" = 'unresolved' WHERE "scope_type" IS NULL;

ALTER TABLE "users" ALTER COLUMN "scope_type" SET NOT NULL;
ALTER TABLE "users" ALTER COLUMN "scope_type" SET DEFAULT 'unresolved';

ALTER TABLE "users" DROP CONSTRAINT IF EXISTS "chk_users_scope_type";
ALTER TABLE "users" ADD CONSTRAINT "chk_users_scope_type" CHECK ("scope_type" IN (
    'state', 'wing', 'range', 'district', 'commissionerate',
    'station', 'assigned_case', 'platform', 'unresolved'));

-- Exactly one anchor for the scope_type, and no stray anchors from other tiers.
ALTER TABLE "users" DROP CONSTRAINT IF EXISTS "chk_users_scope_anchor";
ALTER TABLE "users" ADD CONSTRAINT "chk_users_scope_anchor" CHECK (
    CASE "scope_type"
        WHEN 'state'           THEN "wing_id" IS NULL AND "range_id" IS NULL AND "district_id" IS NULL AND "unit_id" IS NULL
        WHEN 'platform'        THEN "wing_id" IS NULL AND "range_id" IS NULL AND "district_id" IS NULL AND "unit_id" IS NULL
        WHEN 'wing'            THEN "wing_id" IS NOT NULL AND "range_id" IS NULL AND "district_id" IS NULL AND "unit_id" IS NULL
        WHEN 'range'           THEN "range_id" IS NOT NULL AND "wing_id" IS NULL AND "district_id" IS NULL AND "unit_id" IS NULL
        WHEN 'district'        THEN "district_id" IS NOT NULL AND "wing_id" IS NULL AND "range_id" IS NULL
        WHEN 'commissionerate' THEN "district_id" IS NOT NULL AND "wing_id" IS NULL AND "range_id" IS NULL
        WHEN 'station'         THEN "unit_id" IS NOT NULL AND "wing_id" IS NULL AND "range_id" IS NULL
        WHEN 'assigned_case'   THEN "unit_id" IS NOT NULL AND "wing_id" IS NULL AND "range_id" IS NULL
        WHEN 'unresolved'      THEN TRUE
        ELSE FALSE
    END);

COMMENT ON COLUMN "users"."scope_type" IS
    'Data breadth this seat carries. Kept separate from rank (Employee.RankID), assignment (Employee.DesignationID) and permission (role_permissions). ''unresolved'' means no posting on record and MUST resolve to no data, never to state-wide.';
COMMENT ON COLUMN "users"."employee_id" IS
    'Establishment row backing this login seat. Links a credential to an officer without copying rank or designation onto users.';

CREATE INDEX IF NOT EXISTS "idx_users_scope_type" ON "users" ("scope_type");
CREATE INDEX IF NOT EXISTS "idx_users_district"   ON "users" ("district_id");
CREATE INDEX IF NOT EXISTS "idx_users_range"      ON "users" ("range_id");
CREATE INDEX IF NOT EXISTS "idx_users_wing"       ON "users" ("wing_id");
CREATE INDEX IF NOT EXISTS "idx_users_employee"   ON "users" ("employee_id");

-- ---------------------------------------------------------------------------
-- 2. Admin-editable profile
-- ---------------------------------------------------------------------------
ALTER TABLE "users" ADD COLUMN IF NOT EXISTS "email"              VARCHAR;
ALTER TABLE "users" ADD COLUMN IF NOT EXISTS "phone"              VARCHAR;
ALTER TABLE "users" ADD COLUMN IF NOT EXISTS "rank_label"         VARCHAR;
ALTER TABLE "users" ADD COLUMN IF NOT EXISTS "designation_label"  VARCHAR;
ALTER TABLE "users" ADD COLUMN IF NOT EXISTS "posting_label"      VARCHAR;
ALTER TABLE "users" ADD COLUMN IF NOT EXISTS "preferred_language" VARCHAR NOT NULL DEFAULT 'en';
ALTER TABLE "users" ADD COLUMN IF NOT EXISTS "avatar_url"         VARCHAR;
ALTER TABLE "users" ADD COLUMN IF NOT EXISTS "notes"              TEXT;
ALTER TABLE "users" ADD COLUMN IF NOT EXISTS "updated_by"         VARCHAR;

-- ---------------------------------------------------------------------------
-- 3. Lead-investigator eligibility — an ASSIGNMENT property, not a rank and not
--    a scope.
--
-- ~10,744 seats carry scope_type='assigned_case', spanning PSI, ASI, Head
-- Constable and Police Constable. They are NOT all Investigating Officers: a
-- constable sees the work assigned to them but is not the IO of record. Labelling
-- every one of those seats "PSI / Investigating Officer" would be false on both
-- counts and would collapse rank and assignment into the seat.
--
-- So: scope_type says how much data the seat sees (identical for all of them),
-- rank_label says what the officer actually is (varies), and this flag says
-- whether they can be the IO of record (varies independently of both). Seeded
-- from Employee.DesignationID at provisioning; admin-overridable, because a
-- posting can change without an establishment change.
-- ---------------------------------------------------------------------------
ALTER TABLE "users" ADD COLUMN IF NOT EXISTS "is_lead_investigator" BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN "users"."is_lead_investigator" IS
    'TRUE when this seat may be recorded as the Investigating Officer of a case. Independent of rank and of scope_type: an assisting Head Constable and a lead PSI both hold scope_type=assigned_case, and only the PSI is a lead. Derived from Employee.DesignationID at provisioning, then admin-editable.';

CREATE INDEX IF NOT EXISTS "idx_users_lead_investigator"
    ON "users" ("is_lead_investigator") WHERE "is_lead_investigator" = TRUE;

ALTER TABLE "users" DROP CONSTRAINT IF EXISTS "chk_users_language";
ALTER TABLE "users" ADD CONSTRAINT "chk_users_language"
    CHECK ("preferred_language" IN ('en', 'kn'));

COMMENT ON COLUMN "users"."rank_label" IS
    'DISPLAY label for the seat holder''s rank. Denormalised for presentation only; Employee.RankID remains the establishment source of truth.';
COMMENT ON COLUMN "users"."designation_label" IS
    'DISPLAY label for the post held (e.g. Station House Officer). Employee.DesignationID remains the source of truth.';
COMMENT ON COLUMN "users"."posting_label" IS
    'Human-readable posting, e.g. "Jayanagar PS, Bengaluru City". Derived from the scope anchor for display.';
COMMENT ON COLUMN "users"."preferred_language" IS
    'UI language. Kannada support is planned; ''kn'' is accepted so seats can be provisioned ahead of the translations.';

COMMIT;
