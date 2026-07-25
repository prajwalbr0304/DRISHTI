# DRISHTI

Crime intelligence platform for the Karnataka Police Department. DRISHTI turns an
operational FIR (First Information Report) database into an analytics and
intelligence system: risk scoring, hotspot/geospatial analytics, entity & gang
network graphs, semantic similar-case search, forecasting, and a natural-language
"Ask DRISHTI" assistant.

> Built on a FastAPI ML/analytics service, a PostgreSQL + PostGIS + pgvector
> analytics database, and a Vite + React + TypeScript web front end. The
> submitted product is deployed on **Zoho Catalyst**; **AWS RDS PostgreSQL** is
> the retained historical/analytics corpus. See the architecture note below.

---

## Architecture

DRISHTI has two clearly separated planes (this is a **synthetic hackathon demo**,
not a production system):

- **Deployed serving plane — Zoho Catalyst.** The submitted frontend (Slate /
  Web Client Hosting), Authentication, API Gateway, the FastAPI backend (AppSail)
  and Functions, the operational relational store (**Catalyst Data Store**) and
  the application object store (**Catalyst Stratus**). The browser only ever talks
  to Catalyst — never to AWS or a database directly.
- **Retained analytics plane — AWS.** **AWS RDS PostgreSQL** (PostGIS / pgvector /
  pg_trgm) holds the full historical/analytics corpus and drives the justified
  custom ML/GPU/geospatial workloads. It is reached only server-to-server through a
  protected adapter — never from the browser and never as the submitted app's
  operational CRUD path.

For **local development** you run the FastAPI service and the React app directly
against a PostgreSQL analytics database (an AWS RDS instance, or any local
PostgreSQL 15+ with the required extensions). `DATABASE_URL` is that analytics
connection; it is server-side only and is never shipped to the browser.

> Row-Level Security (RLS/FORCE RLS) is **intentionally disabled** for this
> synthetic hackathon (see the security note below). Server-side Catalyst
> Authentication + API-Gateway checks + role/scope authorization remain the
> access boundary in every mode.

| Layer | Path | Stack |
| --- | --- | --- |
| Database schema & migrations | `services/ml/sql/` | PostgreSQL 15+ (AWS RDS), PostGIS, pgvector, pg_trgm |
| Synthetic data generator | `scripts/generate.py`, `datagen/` | Python, psycopg2 (COPY) |
| ML / analytics API | `services/ml/` | FastAPI, Uvicorn, scikit-learn, NetworkX, (optional) PyTorch / TabFM / TimesFM |
| Web front end | `web/` | Vite, React 18, TypeScript, Tailwind, deck.gl, MapLibre |
| Deployed serving | `infra/catalyst/` | Zoho Catalyst: Slate, Auth, API Gateway, AppSail, Data Store, Stratus |
| Retained analytics / model plane | `infra/aws/` | AWS RDS PostgreSQL (adapter-only), SageMaker/Batch (GPU) |

---

## Prerequisites

- **Python 3.12** (the service Docker image is `python:3.12-slim`)
- **Node.js 18+** and npm (for the `web/` front end)
- **PostgreSQL 15+** with the `postgis`, `vector` (pgvector) and `pg_trgm`
  extensions — an **AWS RDS PostgreSQL** instance (the retained analytics corpus)
  or any local PostgreSQL 15+ with these extensions. `pgrouting` is optional.
- Optional: **Docker** (to run the ML service in a container)

---

## Repository layout

```
DRISHTI/
├─ scripts/                       # operational + data-generation CLIs
│  ├─ generate.py                 # synthetic data generator (CLI entry point)
│  └─ generate_v2.py              # scenario-driven generator + safe loader
├─ datagen/                       # data-generation engine
├─ requirements.txt               # deps for the data generator
├─ services/ml/                   # FastAPI ML/analytics service
│  ├─ app/                        # application code (main.py -> app.main:app)
│  ├─ sql/                        # database schema + migrations (run in order)
│  │  ├─ police_fir_schema.sql        # 1) base operational FIR schema
│  │  ├─ police_fir_intelligence.sql  # 2) AI / analytics layer (pgvector, pg_trgm)
│  │  ├─ police_fir_extensions.sql    # 3) financial / chat / RBAC extensions
│  │  └─ 0NN_*.sql                     # 4) numbered service migrations (001-023)
│  ├─ requirements.txt            # backend deps (heavier: torch, foundation models)
│  ├─ Dockerfile / docker-compose.yml
│  └─ models/                     # ML model weights (NOT in git; see notes)
└─ web/                           # Vite + React + TypeScript SPA
   ├─ .env.example                # copy to .env and fill in
   └─ package.json
```

---

## 1. Configure environment variables

### Root `.env` (used by the data generator and the ML service)

Create a file named `.env` in the repository root:

```dotenv
# Full Postgres connection URI for the analytics database (AWS RDS PostgreSQL,
# or a local PostgreSQL 15+ with PostGIS/pgvector/pg_trgm). Server-side ONLY —
# never shipped to the browser. URL-encode special characters in the password
# (for example @ becomes %40). AWS RDS strongly prefers TLS (sslmode=require).
DATABASE_URL=postgresql://<user>:<password>@<db-host>.<region>.rds.amazonaws.com:5432/drishti

# Restricted read-only role used by the NL->SQL executor (created by
# services/ml/sql/001_readonly_role.sql). Default shown.
READONLY_ROLE=drishti_readonly

# Optional: enables the LLM-backed "Ask DRISHTI" assistant (provider-neutral,
# OpenAI-compatible chat API). Without a key the service uses a deterministic
# offline planner, so chat still works. The deployed submission's primary
# semantic path is finalised in a later phase (Catalyst QuickML).
LLM_API_KEY=
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=

# CORS is an exact allow-list (localhost + this origin). Do NOT use a wildcard
# for a deployed build. A purely-local throwaway demo may set
# DRISHTI_CORS_ALLOW_ALL=true, but the deployed AppSail never does.
DEMO_FRONTEND_ORIGIN=
```

> `DATABASE_URL` points at the **retained analytics** database and is required
> for local data generation and the analytics API. The **deployed** operational
> serving path (Catalyst AppSail) uses Catalyst Data Store / Stratus and runs
> **without** `DATABASE_URL`.

### Web `web/.env`

```bash
cp web/.env.example web/.env
```

Then edit `web/.env`:

```dotenv
# Base URL of the ML/analytics API (see step 4). Match the port you run the
# backend on: 8000 for local `uvicorn` below, or 8080 if you use Docker.
VITE_API_BASE_URL=http://localhost:8000

# Optional Mapillary token for street-level imagery (map degrades gracefully
# without it): https://www.mapillary.com/dashboard/developers
VITE_MAPILLARY_TOKEN=
```

---

## 2. Set up the database

Run the SQL files **in this exact order** against your database. With `psql`:

```bash
psql "$DATABASE_URL" -f services/ml/sql/police_fir_schema.sql
psql "$DATABASE_URL" -f services/ml/sql/police_fir_intelligence.sql
psql "$DATABASE_URL" -f services/ml/sql/police_fir_extensions.sql

# Service migrations (roles, graph objects, matviews, evidence)
psql "$DATABASE_URL" -f services/ml/sql/001_readonly_role.sql
psql "$DATABASE_URL" -f services/ml/sql/002_graph_objects.sql
psql "$DATABASE_URL" -f services/ml/sql/003_risk_matview.sql
psql "$DATABASE_URL" -f services/ml/sql/004_case_evidence.sql
```

On Windows PowerShell, reference the variable as `$env:DATABASE_URL`, or run the
files in the same order through any PostgreSQL client (psql, `pgAdmin`, or your
RDS query editor).

---

## 3. Generate synthetic data

From the repository root:

```bash
python -m venv .venv
# Windows:        .venv\Scripts\activate
# macOS / Linux:  source .venv/bin/activate

pip install -r requirements.txt

# Validate the generator with NO database writes:
python scripts/generate.py --dry-run 5000

# Load a reproducible sample (wipes target tables first):
python scripts/generate.py --firs 20000 --workers 4 --seed 7 --truncate

# Or a full state-wide load:
python scripts/generate.py --truncate
```

Useful flags: `--firs N`, `--workers N`, `--seed N`, `--start/--end YYYY-MM-DD`,
`--dsn <url>` (override `DATABASE_URL`), `--no-intelligence`, `--dry-run N`.

---

## 4. Run the ML / analytics API (`services/ml`)

```bash
cd services/ml
pip install -r requirements.txt      # heavy: pulls torch and optional foundation models
uvicorn app.main:app --reload --port 8000
```

- Reads `DATABASE_URL` from the repo-root `.env`.
- Health check: open http://localhost:8000/health — it reports DB connectivity
  and which extensions are installed.
- Interactive API docs: http://localhost:8000/docs

### Alternative: Docker

```bash
cd services/ml
DATABASE_URL="postgresql://..." docker compose up --build
```

The container listens on **port 8080**. If you use Docker, set
`VITE_API_BASE_URL=http://localhost:8080` in `web/.env`.

---

## 5. Run the web front end (`web`)

```bash
cd web
npm install
npm run dev
```

The app runs at http://localhost:5173 and talks to the API at
`VITE_API_BASE_URL`. Start the ML service (step 4) first so the UI has live data.

Production build / preview:

```bash
npm run build      # type-check + bundle
npm run preview    # serve the build at http://localhost:4173
```

---

## Quick start (summary)

1. Create root `.env` with `DATABASE_URL` (step 1).
2. Run the SQL files in order (step 2).
3. `pip install -r requirements.txt` then `python scripts/generate.py --firs 20000 --truncate` (step 3).
4. `cd services/ml && pip install -r requirements.txt && uvicorn app.main:app --reload --port 8000` (step 4).
5. `cp web/.env.example web/.env`, then `cd web && npm install && npm run dev` (step 5).
6. Open http://localhost:5173.

---

## Notes

- **Model weights are not in the repo.** Large ML weights (for example
  `services/ml/models/*.safetensors`) are excluded via `.gitignore`. The service
  auto-detects available models and **falls back gracefully** (TabFM → TabPFN →
  in-context; sentence-transformers → hashing encoder; TimesFM/ST-GNN →
  statistical baselines), so everything runs without them.
- **Secrets stay local.** `.env`, `web/.env` and `web/.env.local` are
  git-ignored. Never commit real keys or database passwords. Rotate any secret
  that has been shared.
- **Row Level Security is disabled** on the database tables by design for this
  synthetic hackathon (see the security notices in the SQL files). This does NOT
  disable the real access boundary: Catalyst Authentication, API-Gateway checks
  and server-side role/scope authorization still gate every request. The browser
  has no direct database or AWS access. Production RLS/privacy hardening is
  tracked as post-hackathon work.
- **Ports:** local `uvicorn` uses `8000` (matches the web default); Docker uses
  `8080`. Keep `VITE_API_BASE_URL` in sync with whichever you run.

---

## Legacy / historical note (Supabase migration)

Earlier iterations of DRISHTI were bootstrapped on a **Supabase**-hosted
PostgreSQL instance, and older revisions of this README and `services/ml/app/db.py`
described a Supabase-first setup (`SUPABASE_URL` / `SUPABASE_PUBLISHABLE_KEY` /
`SUPABASE_SECRET_KEY`, the Supabase connection-string UI and SQL editor). The
project has since moved to the architecture described above:

- the retained analytics/historical database is **AWS RDS PostgreSQL** (reached
  server-to-server through a protected adapter, never from the browser);
- the deployed operational serving layer is **Zoho Catalyst** (Data Store +
  Stratus + Auth + API Gateway + AppSail + Slate).

The Supabase-era `SUPABASE_*` environment keys are no longer used by the running
code. `DATABASE_URL` now points at the AWS RDS (or a local PostgreSQL) analytics
instance. This note is retained so the migration history is explicit and the old
references are not mistaken for the current setup. Schema files and migrations are
unchanged and remain portable across any conforming PostgreSQL 15+ instance.
