# Migration validation harness

Validates migrations `026`–`035` (role-scoped command views) against a throwaway
PostGIS container before anything runs on RDS. Both directions are exercised:
every `up` file, then every `down` file in reverse order, with assertions in
between.

## Why a fixture instead of the full dump

`_migration/drishti_schema.sql` requires `pgrouting` and `vector`, which the
standard `postgis/postgis` image does not ship. Rather than build a custom image,
`extract_fixture.py` pulls just the 19 tables, one enum and their identity and
PK/UNIQUE constraints that these migrations actually touch, straight out of the
real dump so the definitions stay faithful.

Foreign keys to omitted tables are deliberately skipped. The FKs the migrations
themselves add are exercised.

## Run

```powershell
python scripts/migrations/extract_fixture.py

docker run -d --name drishti-migtest `
  -e POSTGRES_PASSWORD=test -e POSTGRES_DB=drishti `
  postgis/postgis:17-3.5-alpine

docker cp scripts/migrations/fixture.generated.sql drishti-migtest:/tmp/fixture.sql
docker cp services/ml/sql drishti-migtest:/sql
docker cp scripts/migrations/validate_026_035.sh drishti-migtest:/tmp/v.sh

docker exec drishti-migtest sh -c `
  "sed -i 's/\r$//' /tmp/v.sh; psql -U postgres -d drishti -q -f /tmp/fixture.sql >/dev/null 2>&1; sh /tmp/v.sh"

docker rm -f drishti-migtest
```

Two gotchas when iterating:

- `docker cp` of a directory onto an existing path **nests** it (`/sql/sql`), so
  `docker exec drishti-migtest rm -rf /sql` before re-copying.
- `DROP DATABASE` fails while a session is attached. Use
  `DROP DATABASE IF EXISTS drishti WITH (FORCE);`.

## What it asserts

| # | Assertion |
|---|---|
| 1 | A `wing` seat with no `wing_id` is rejected |
| 2 | A `station` seat carrying a stray `wing_id` is rejected |
| 3 | All seven valid `scope_type` / anchor combinations are accepted |
| 4 | Six application roles exist; the six superseded roles are gone |
| 5 | A duplicate role-wide `role_ui_grants` override is rejected |
| 6 | A `Level='range'` jurisdiction boundary is accepted |
| 7 | `mv_case_daily` refreshes, honours the analytics-eligibility policy, and supports `REFRESH ... CONCURRENTLY` |
| A | 38 district-level units, 6 Commissionerates |
| B | KGF exists in Central Range |
| C | Bengaluru Urban is **not** a Commissionerate |
| D | Every non-Commissionerate district has a range |
| E | City stations moved to their Commissionerate, count recorded in `DistrictSplitAudit` |
| F | `Employee.DistrictID` followed its station — zero drift |
| G | Commissionerate and rural-remainder polygons do not overlap |
| H | Range polygons dissolved from the final district set |
| I | Permission catalogue populated; built-in grants issued |
| J | Admin can create a custom role with an arbitrary permission set |
| K | A seat can hold a custom role |
| L | IO seats carry their **true** rank; exactly one lead investigator among three |
| M | Rollback restores 32 districts, 10 roles, no residue |

Three of these exist because they would otherwise fail silently:

- **Check 7** seeds three cases, one flagged `excluded_from_derived_analytics`,
  and requires `open=1, closed=1` — not `2/1`. That proves the fail-closed
  predicate copied from `app/cases/analytics_policy.py` is in effect, which is
  why the rollup reconciles with `/performance/overview` rather than over-counting.
- **Check G** runs `ST_Overlaps` between Mysuru and Mysuru City. If the carve
  left them overlapping, every hotspot in the city would be counted twice.
- **Check L** asserts three distinct `rank_label` values across the
  `assigned_case` seats. A regression that labelled all ~10,744 IO seats
  uniformly would still pass every other check.

## Ordering constraints found while validating

- `027.down` before `026.down`: the `wing_id` / `range_id` FKs reference tables
  `026` drops.
- `028.down` before `027.down`: it maps post-`028` seats back by `scope_type`,
  which `027` drops.
- `034.down` before `033.down`: `034` creates District rows referencing `033`'s
  Range rows.
- `031.down` deletes `range` / `subdivision` boundary rows before narrowing the
  CHECK, which would otherwise reject the `ALTER`.

## Fixture limits worth knowing

The fixture is small, so two counts are intentionally lower than production:

- **Check H expects 4 range polygons, not 7.** Only five districts get seeded
  geometry, and those fall in four ranges. A range with no district polygon
  correctly yields no range polygon.
- **Check E moves 6 stations.** Production moves whatever the real taluk
  distribution yields (~34 across the five Commissionerates).

## Known-good result

Last run: all ten migrations up, thirteen checks pass with zero errors, all ten
down, 32 districts and 10 roles restored, zero leftover tables or columns.
