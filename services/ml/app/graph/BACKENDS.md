# Graph engine — backend strategy (doc 04 §2–3)

The graph endpoints are deliberately written against a **thin data-access seam**
(`app/graph/queries.py` for traversal, `app/graph/algorithms.py` for analytics,
`app/graph/hidden.py::detect_hidden_pairs` for the backend-agnostic detector
rule). The FastAPI router and `service.py` never embed engine-specific query
text, so the execution engine can be swapped without touching the API contract.

Current: **Option A — Postgres-native** (shipped)
- N-hop neighbourhood: `WITH RECURSIVE` over `NetworkEdge`, fan-out capped by weight.
- Shortest path: `fn_entity_shortest_path()` (pgRouting `pgr_dijkstra`), with a
  recursive-CTE fallback if pgRouting is absent.
- Communities / centrality: Python (`networkx`) batch jobs that read
  `EntityGraph`+`NetworkEdge` and write results back into `EntityGraph.Attributes`.
- Hidden associations: SQL self-join on shared intermediaries, materialized into
  `drishti_hidden_associations`.

## Swapping to Option B — Apache AGE (openCypher in the same Postgres)

AGE stores a property graph beside the relational tables and speaks openCypher.
The migration path keeps **one database** and the **same HTTP API**:

1. **Install** the extension on a self-managed/compatible Postgres:
   `CREATE EXTENSION age; LOAD 'age'; SET search_path = ag_catalog, "$user", public;`
   and create a graph: `SELECT create_graph('drishti');`
2. **Project** the existing tables into AGE (one-time + incremental sync):
   - `EntityGraph` rows → vertices `(:Entity {entity_id, type, label})`
   - `NetworkEdge` rows → edges `(:Entity)-[:RELATED {type, weight}]->(:Entity)`
   A trigger or nightly job mirrors inserts/updates; Postgres stays source of truth.
3. **Replace only the query bodies** behind the existing functions:
   - `queries.neighbourhood()` → 
     `MATCH (a:Entity {entity_id:$id})-[r:RELATED*1..$hops]-(b) RETURN b, min(length(r))`
   - `queries.shortest_path()` → `MATCH p = shortestPath((a)-[*..$max]-(b)) RETURN p`
   - `algorithms.detect_communities()` / `compute_centrality()` → AGE/GDS-style
     procedures where available, otherwise keep the `networkx` batch (it already
     only reads rows and writes `Attributes`, so it is engine-independent).
   - `hidden.detect_hidden_pairs()` is already backend-agnostic — feed it rows
     from a Cypher `MATCH (p)-[]->(i) ...` instead of the SQL CTE; the rule is
     identical.
   The router, `service.py`, `schemas.py` and the `AiResult` contract are unchanged.

## Option C — Neo4j / Memgraph analytics mirror (at scale)

Add only if deep-traversal / GDS performance outgrows A/B. One-directional sync
(Postgres → read-only mirror). The same seam applies: swap the traversal/analytics
implementations, keep the API. The mirror never becomes a second source of truth.
