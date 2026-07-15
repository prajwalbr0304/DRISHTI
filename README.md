# DRISHTI

Crime intelligence platform for the Karnataka Police Department. DRISHTI turns an
operational FIR (First Information Report) database into an analytics and
intelligence system: risk scoring, hotspot/geospatial analytics, entity & gang
network graphs, semantic similar-case search, forecasting, and a natural-language
"Ask DRISHTI" assistant.

> Built on PostgreSQL (Supabase) + PostGIS + pgvector, a FastAPI ML/analytics
> service, and a Vite + React + TypeScript web front end.

---

## Architecture

| Layer | Path | Stack |
| --- | --- | --- |
| Database schema & migrations | `*.sql`, `services/ml/sql/` | PostgreSQL 15+, PostGIS, pgvector, pg_trgm |
| Synthetic data generator | `generate.py`, `datagen/` | Python, psycopg2 (COPY) |
| ML / analytics API | `services/ml/` | FastAPI, Uvicorn, scikit-learn, NetworkX, (optional) PyTorch / TabFM / TimesFM |
| Web front end | `web/` | Vite, React 18, TypeScript, Tailwind, deck.gl, MapLibre |

---

## Prerequisites

- **Python 3.12** (the service Docker image is `python:3.12-slim`)
- **Node.js 18+** and npm (for the `web/` front end)
- **PostgreSQL 15+** with the `postgis`, `vector` (pgvector) and `pg_trgm`
  extensions — a **Supabase** project provides all of these. `pgrouting` is
  optional.
- Optional: **Docker** (to run the ML service in a container)

---

## Repository layout

```
DRISHTI/
├─ police_fir_schema.sql          # 1) base operational FIR schema
├─ police_fir_intelligence.sql    # 2) AI / analytics layer (enables pgvector, pg_trgm)
├─ police_fir_extensions.sql      # 3) financial / chat / RBAC extensions
├─ generate.py                    # synthetic data generator (CLI entry point)
├─ datagen/                       # data-generation engine
├─ requirements.txt               # deps for the data generator
├─ services/ml/                   # FastAPI ML/analytics service
│  ├─ app/                        # application code (main.py -> app.main:app)
│  ├─ sql/                        # 4) service migrations (roles, matviews, graph)
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
# Full Postgres connection URI (Supabase: Project Settings -> Database ->
# Connection string -> URI). URL-encode special characters in the password
# (for example @ becomes %40).
DATABASE_URL=postgresql://postgres:<your-password>@db.<project-ref>.supabase.co:5432/postgres

# Restricted read-only role used by the NL->SQL executor (created by
# services/ml/sql/001_readonly_role.sql). Default shown.
READONLY_ROLE=drishti_readonly

# Optional Supabase API values (not required to run the DB/data generator).
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_PUBLISHABLE_KEY=<publishable-key>
SUPABASE_SECRET_KEY=<secret-key>

# Optional: enables the LLM-backed "Ask DRISHTI" assistant. Without a key the
# service uses a deterministic offline planner, so chat still works.
LLM_API_KEY=
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
```

> The API keys **cannot** open a direct Postgres/COPY connection — a real
> database password (`DATABASE_URL`) is required for data generation.

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
psql "$DATABASE_URL" -f police_fir_schema.sql
psql "$DATABASE_URL" -f police_fir_intelligence.sql
psql "$DATABASE_URL" -f police_fir_extensions.sql

# Service migrations (roles, graph objects, matviews, evidence)
psql "$DATABASE_URL" -f services/ml/sql/001_readonly_role.sql
psql "$DATABASE_URL" -f services/ml/sql/002_graph_objects.sql
psql "$DATABASE_URL" -f services/ml/sql/003_risk_matview.sql
psql "$DATABASE_URL" -f services/ml/sql/004_case_evidence.sql
```

On Windows PowerShell, reference the variable as `$env:DATABASE_URL`, or paste
the files into the **Supabase SQL Editor** and run them in the same order.

---

## 3. Generate synthetic data

From the repository root:

```bash
python -m venv .venv
# Windows:        .venv\Scripts\activate
# macOS / Linux:  source .venv/bin/activate

pip install -r requirements.txt

# Validate the generator with NO database writes:
python generate.py --dry-run 5000

# Load a reproducible sample (wipes target tables first):
python generate.py --firs 20000 --workers 4 --seed 7 --truncate

# Or a full state-wide load:
python generate.py --truncate
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
3. `pip install -r requirements.txt` then `python generate.py --firs 20000 --truncate` (step 3).
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
- **Row Level Security is disabled** on the database tables by design (see the
  security notices in the SQL files). Only deploy on a trusted/private network,
  or enable RLS + policies and revoke anon grants before exposing publicly.
- **Ports:** local `uvicorn` uses `8000` (matches the web default); Docker uses
  `8080`. Keep `VITE_API_BASE_URL` in sync with whichever you run.
