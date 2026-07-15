# 04 — Network / Graph Analysis
### The "Neo4j-style" link-analysis engine on top of the Supabase schema

> The client asked specifically *how we can include a Neo4j-type implementation for network mapping.* This document answers it end-to-end: the data model already in place, the three deployment options (with an honest benchmark-backed recommendation), the algorithms, the query patterns, and the two headline capabilities — **community detection** and the **hidden-association detector** (the "impossible-to-spot-in-Excel" feature). This is the engine behind the [Network Analysis destination](01_UX_UI_ARCHITECTURE.md#44--network-analysis--link-analysis--phases-6--11).

---

## 1. What you already have (and it's good)

The schema was designed graph-first, so the hard part is done. The Phase-6 review even noted the actual tables are *better* than the generic `entity_relationships` placeholder they replaced.

| Table | Graph role | Notable columns |
|---|---|---|
| `EntityGraph` | **nodes** — people, gangs, locations, vehicles, phones, accounts | `EntityID` (BIGINT), `EntityType`, `AccusedMasterID` link, `Embedding vector(768)`, `geom`, `Properties` JSONB |
| `NetworkEdge` | **edges** — typed, weighted, directed | `source`, `target`, `cost`, `reverse_cost` (**pgRouting-shaped**), `RelationshipType`, `Weight`, `EvidenceCaseID` |
| `GangMembership` | **known groups** — ground truth for validating detected communities | role enum, join/left dates, confidence, source |
| `FinancialAccount` / `FinancialTransaction` / `TransactionLink` | **the money sub-graph** — accounts as nodes, transactions as directed weighted edges | `Amount`, `IsFlagged`, `FlagReason`, optional `EntityID` link into `EntityGraph` |

Two design decisions already made that pay off here:
- **`NetworkEdge` carries `cost`/`reverse_cost`**, so pgRouting shortest-path works with zero remodelling.
- **`FinancialAccount.EntityID`** optionally links a bank account into `EntityGraph`, so the people-graph and the money-graph can be shown as **one unified network** without merging their underlying tables.

The entire "Neo4j-type implementation" question is therefore not *"how do we build a graph?"* — you have one — but *"which engine executes the graph algorithms, and where?"*

---

## 2. The core question: where does graph compute run?

Postgres can do a lot of graph work, but it is not a native graph engine. The published benchmarks are clear about the trade-off, and they point to a *tiered* answer rather than a single winner:

- Postgres **recursive CTEs** are actually **faster than Neo4j on shallow neighbourhood/reachability** queries (roughly a few× on 1–2-hop expansions).
- Neo4j is **dramatically faster on deep point-to-point traversal** — reports of ~85–135× on shortest-path, and the gap *widens with path length* — because of **index-free adjacency** (relationships are stored as direct pointers, so a hop is a pointer-follow, not a join).

(Trade-off summarized from [Neo4j vs Postgres traversal benchmarks](https://www.pedroalonso.net/blog/graphrag-vs-vector-postgres/) and [markaicode — Neo4j vs Postgres](https://markaicode.com/vs/neo4j-vs-postgres/); figures are indicative and workload-dependent — rephrased for compliance.)

So the right architecture depends on **traversal depth**, and DRISHTI has both shallow and deep needs.

---

## 3. Three deployment options (and the recommendation)

### Option A — Postgres-native (recursive CTEs + pgRouting)  ·  *ship first*
Use what's already in the box. `WITH RECURSIVE` for N-hop neighbourhoods and the hidden-association joins; **pgRouting** (`pgr_dijkstra` over `NetworkEdge`) for shortest paths; the existing `fn_entity_shortest_path()` helper.

- ✅ Zero new infrastructure, single source of truth, transactional, already coded.
- ✅ Excellent for the common case: 1–3 hop expansions, per-entity subgraphs, money-trail CTEs.
- ⚠️ Community detection (Louvain) and deep all-pairs work are awkward/slow in pure SQL.
- **Verdict:** the baseline. Covers most of the Network destination on day one.

### Option B — Apache AGE (openCypher *inside* Postgres)  ·  *the sweet spot*
**Apache AGE** is a Postgres extension that adds property-graph storage and the **openCypher** query language to the same database. You write Cypher (`MATCH (a)-[:CO_ACCUSED*1..3]-(b) …`) against graph data living beside your relational tables. (Sources: [gdotv — Apache AGE explained](https://gdotv.com/blog/apache-age-explained/); [PuppyGraph — Apache AGE vs Neo4j](https://www.puppygraph.com/learn/apache-age-vs-neo4j).)

- ✅ **One database.** No sync, no second system to secure — critical for a law-enforcement data-residency posture.
- ✅ Cypher is far more ergonomic than recursive CTEs for multi-hop pattern matching.
- ✅ Runs on the same Supabase-compatible Postgres.
- ⚠️ Less mature than Neo4j; not as fast as a native engine on the very deepest traversals; check Supabase extension availability (may require a self-managed Postgres).
- **Verdict:** the preferred upgrade when CTEs get unwieldy — keeps the single-DB simplicity while gaining Cypher.

### Option C — Neo4j / Memgraph analytics mirror  ·  *when depth demands it*
Stand up a **native graph database** as a **read-only analytics mirror**, synced from Postgres (CDC or scheduled ETL). Postgres stays the source of truth; the mirror exists purely to run heavy graph algorithms fast.

- ✅ **index-free adjacency** → deep traversals and all-pairs analytics that are painful elsewhere.
- ✅ **Graph Data Science (GDS) library**: Louvain/Leiden community detection, PageRank, betweenness/closeness centrality, node similarity, weakly/strongly connected components — production-grade, one call each.
- ✅ Memgraph is an open-source, Cypher-compatible alternative if licensing/cost matters.
- ⚠️ A second system to deploy, sync, secure, and keep consistent. Only worth it at scale.
- **Verdict:** add in Wave C/D **if** graph depth or community-detection volume outgrows AGE. Not needed to launch.

### The recommendation, in one line
> **Start with A (you already have it) → adopt B (Apache AGE) for ergonomic multi-hop Cypher in the same DB → add C (Neo4j/Memgraph mirror) only if deep-traversal or GDS performance demands it.** Everything the Network destination promises is achievable at stage A/B; C is a performance upgrade, not a prerequisite.

| | A · Postgres CTE + pgRouting | B · Apache AGE | C · Neo4j/Memgraph mirror |
|---|---|---|---|
| New infra | none | extension only | full second DB + sync |
| Query language | SQL / recursive CTE | **openCypher** | Cypher |
| Shallow (1–3 hop) | ✅ fast | ✅ fast | ✅ fast |
| Deep traversal | ⚠️ degrades | ⚪ ok | ✅ **excellent** |
| Community detection | ⚠️ hard | ⚪ possible | ✅ **GDS built-in** |
| Data residency | ✅ single DB | ✅ single DB | ⚠️ two systems |
| When | now | when CTEs hurt | at scale |

---

## 4. The algorithms and what they mean to an officer

Each algorithm maps to a concrete investigative question and a UI surface.

| Algorithm | Officer's question | Output & where it shows |
|---|---|---|
| **N-hop subgraph (BFS)** | "Who is *this* person connected to, and how closely?" | Entity → Network; Explore mode. Expand hop-by-hop. |
| **Shortest / all paths** (Dijkstra / pgRouting / GDS) | "How is A connected to B?" | Network → Path Finder; animated path(s). |
| **Louvain / Leiden community detection** | "Which clusters look like organized groups?" | Network → Communities; coloured clusters, cross-checked vs. `GangMembership`. |
| **PageRank / eigenvector centrality** | "Who is the most *influential* node in this network?" | node size + halo; ranked "persons of interest". |
| **Betweenness centrality** | "Who is the *broker/bridge* between groups?" (arrest them and the network fractures) | node size in bridge-analysis view. |
| **Connected components** | "How many separate networks exist in this data?" | cluster count; scoping. |
| **Node similarity / co-occurrence** | "Who behaves like a known offender?" | the hidden-association engine (§6) & MO cross-links. |

> **Validation loop:** detected communities are scored against `GangMembership` ground truth (precision/recall on known gangs). This is both a quality gate and a great demo slide — "our unsupervised detector rediscovered N of M known gangs *and* surfaced K new candidate groups."

---

## 5. Query patterns (concrete)

**A · N-hop neighbourhood — Postgres recursive CTE (Option A):**
```sql
WITH RECURSIVE neighbourhood AS (
  SELECT source, target, 1 AS hop
  FROM "NetworkEdge" WHERE source = :entity_id
  UNION ALL
  SELECT e.source, e.target, n.hop + 1
  FROM "NetworkEdge" e
  JOIN neighbourhood n ON e.source = n.target
  WHERE n.hop < :max_hops
)
SELECT DISTINCT target, MIN(hop) AS distance
FROM neighbourhood GROUP BY target ORDER BY distance;
```

**B · same, in Cypher (Option B, Apache AGE):**
```cypher
MATCH (p:Entity {entity_id: $id})-[r:RELATED*1..3]-(n:Entity)
RETURN n, min(length(r)) AS distance ORDER BY distance;
```

**C · shortest path between two entities (pgRouting, already scaffolded):**
```sql
SELECT * FROM fn_entity_shortest_path(:source_id, :target_id);
-- wraps pgr_dijkstra over NetworkEdge(id, source, target, cost, reverse_cost)
```

**D · money-trail multi-hop trace (Phase 11, recursive CTE over transactions):**
```sql
WITH RECURSIVE trail AS (
  SELECT "SourceAccountID", "DestinationAccountID", "Amount", 1 AS hop,
         ARRAY["SourceAccountID"] AS path
  FROM "FinancialTransaction" WHERE "SourceAccountID" = :start
  UNION ALL
  SELECT t."SourceAccountID", t."DestinationAccountID", t."Amount", tr.hop + 1,
         tr.path || t."SourceAccountID"
  FROM "FinancialTransaction" t
  JOIN trail tr ON t."SourceAccountID" = tr."DestinationAccountID"
  WHERE tr.hop < :max_hops
    AND NOT t."SourceAccountID" = ANY(tr.path)   -- cycle guard
)
SELECT * FROM trail;
```

Community detection and PageRank are **not** written in SQL by hand — they run in the graph engine (AGE procedures or Neo4j GDS) or in a Python job (**graphology**/`networkx`/`igraph`) that reads `EntityGraph`+`NetworkEdge` and **writes results back** into `Properties`/`CrimePattern`, keeping Postgres the source of truth.

---

## 6. The hidden-association detector (the headline feature)

This is the "impossible-to-spot-in-Excel" capability the problem statement calls out, and it must be a **clearly demoable output, not a log line**.

**Definition.** Surface pairs of entities that **never appear together in a single FIR** yet share **two or more independent indirect links** — e.g., the *same address* **and** the *same financial account*, or a *shared phone* **and** a *shared vehicle*. Co-appearing in a case is obvious; *this* is the non-obvious connection an analyst would never find by eye.

**How it computes** (Option A form, generalizes to Cypher):
```sql
-- entities linked through >= 2 DISTINCT shared intermediaries,
-- excluding pairs that already co-appear in any case
SELECT a.entity_a, a.entity_b,
       COUNT(DISTINCT a.shared_type) AS independent_links,
       array_agg(DISTINCT a.shared_type) AS link_kinds
FROM shared_intermediaries a           -- (address, account, phone, vehicle, …)
WHERE NOT EXISTS (                      -- never in the same FIR
        SELECT 1 FROM co_case_pairs c
        WHERE c.entity_a = a.entity_a AND c.entity_b = a.entity_b)
GROUP BY a.entity_a, a.entity_b
HAVING COUNT(DISTINCT a.shared_type) >= 2
ORDER BY independent_links DESC;
```

**How it's presented.** Network → *Hidden Associations* shows a ranked feed of **association cards**: "*Person X ↔ Person Y — 0 shared cases, but shared: home address (3 records) + bank account (2 transfers)*". Clicking a card **draws the proof-path on the canvas** and exposes the Evidence Trail (record IDs, link types). The analyst can then **promote it to an alert** or **attach it to a case**.

**Why it lands in a demo:** it produces a finding that is (a) genuinely non-trivial, (b) instantly explainable via the proof path, and (c) actionable in one click. That is the difference between "a graph" and "intelligence."

---

## 7. Rendering it (ties to Docs 01 & 03)

- **Frontend:** sigma.js (WebGL) for the big canvas; React Flow for the embedded case-graph and the Investigation Board; Cytoscape.js where in-browser layout/metrics help.
- **Encoding contract** (identical everywhere a graph appears — from [03 §4](03_DATA_VISUALIZATION.md)): node size = centrality, node colour = entity type *or* community, halo = high influence, edge width = strength, edge style = relationship type, animation = flow/time.
- **Anti-hairball rule:** never render the whole graph. Start from an object or a query and **expand on demand**. Communities and filters (min edge weight, edge types, time window via the global scrubber) keep the canvas legible.
- **Unified people+money view:** when a `FinancialAccount` has an `EntityID`, its account node joins the same canvas as its owner — the two graphs merge visually without merging tables.

---

## 8. Performance & scale notes

- **Index the edges both ways** (`source`, `target`) — already indexed in the intelligence schema.
- **Precompute expensive metrics** (PageRank, community labels) in scheduled jobs; store on the node (`Properties`) so the UI reads, never recomputes.
- **Cap traversal depth and fan-out** in the API (e.g., max 3 hops, top-N neighbours by weight) — both for performance and legibility.
- **Materialize the hidden-association candidates** nightly into a table the UI can page through instantly, refreshing the ranked feed.
- **If/when Option C is added:** sync is one-directional (Postgres → mirror), the mirror is read-only, and it is secured on the same private network — it never becomes a second source of truth.

---

*Previous: [← 03 Data Visualization](03_DATA_VISUALIZATION.md)  ·  Next: [05 Geospatial & Crime-Pattern Analytics →](05_GEOSPATIAL_CRIME_ANALYTICS.md)*
