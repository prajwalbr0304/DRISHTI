# Test tiers and failure classes

## Test tiers

- `unit`: isolated functions/components;
- `contract`: repository, OpenAPI, Pydantic, TypeScript, role/visualization schemas;
- `integration`: disposable local services and deterministic fixtures;
- `live_catalyst`: authenticated real Catalyst resources;
- `live_aws`: authenticated real AWS resources/models;
- `e2e`: browser journey through the intended public boundary;
- `security`: authorization, injection, secrets, dependencies, container, IaC, DAST;
- `load`: bounded synthetic concurrency and latency;
- `recovery`: backup, restore, rollback, replay, cleanup.

## Failure classes

- `CODE`: deterministic implementation defect;
- `FIXTURE`: invalid or incomplete test setup;
- `DATA_STATE`: missing/stale derived data requiring deterministic refresh;
- `ENVIRONMENT`: unavailable local dependency or incompatible toolchain;
- `CLOUD`: authentication, capability, live resource, region, quota, or service failure;
- `TIMEOUT`: command exceeded its bound without a final verdict;
- `FLAKY`: repeated identical input produces inconsistent results; preserve evidence;
- `UNKNOWN`: not yet isolated and never acceptable for a strict release.
