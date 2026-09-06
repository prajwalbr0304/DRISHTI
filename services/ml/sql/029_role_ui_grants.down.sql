-- Rollback for DRISHTI migration 029 (per-role UI visibility overrides).
--
-- Drops every admin override. The application falls back to the code registry
-- defaults, so the UI stays coherent — it simply stops honouring console
-- customisation. Export the table first if the overrides are worth keeping:
--   \copy "role_ui_grants" TO 'role_ui_grants_backup.csv' CSV HEADER

BEGIN;

DROP INDEX IF EXISTS "idx_role_ui_grants_lookup";
DROP INDEX IF EXISTS "uq_role_ui_grants";
DROP TABLE IF EXISTS "role_ui_grants";

COMMIT;
