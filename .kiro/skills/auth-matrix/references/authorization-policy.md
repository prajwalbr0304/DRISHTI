# Authorization Policy Checklist

The approved policy must define each decision using all four dimensions:

- **role**: the authenticated principal's assigned role;
- **scope**: ownership, station, district, state, tenant, or disaster assignment;
- **resource**: the protected entity or aggregate;
- **action**: read, list, create, update, delete, export, assign, or administer.

Minimum DRISHTI coverage should include investigator, analyst, supervisor, policymaker, disaster coordinator, and super-admin behavior where those roles exist in the product. Include:

- same-scope allowed decisions;
- adjacent-scope and unrelated-scope denied decisions;
- aggregate versus personally identifiable detail access;
- privileged mutations and exports;
- direct API attempts that bypass UI controls;
- unauthenticated and expired-session behavior.

The UI is not the policy source. Resolve contradictions against the approved requirements and server-side authorization contract before setting `expected` values.

