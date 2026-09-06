"""Admin console: UI visibility, admin-created roles, role settings.

Backs the three things an administrator was promised but had no code for, even
though migrations 029/030/035 shipped the tables:

  * per-role UI visibility switches  (role_ui_grants)
  * roles created with any permission (permission_catalogue + role_grant)
  * per-role presentation settings    (role_settings)

Kept out of app/admin/ because that module is the platform-operations surface
(retention, legal holds, model review, reconciliation) and is already large. This
one is organisation administration, which is a different job.
"""
