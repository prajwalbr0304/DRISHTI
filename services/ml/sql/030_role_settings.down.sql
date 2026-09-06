-- Rollback for DRISHTI migration 030 (per-role presentation settings).
--
-- Drops every admin customisation of role labels, descriptions and landing
-- routes. The application falls back to the code defaults in
-- web/src/config/roles.ts and services/ml/app/roles.py. Export first if the
-- customisations matter:
--   \copy "role_settings" TO 'role_settings_backup.csv' CSV HEADER

BEGIN;

DROP TABLE IF EXISTS "role_settings";

COMMIT;
