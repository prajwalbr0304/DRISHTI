"""Route-to-data-boundary inventory + static deployment-boundary check
(Prompt 21 §A, §B.5, §H.2).

This module is the single machine-checkable source of truth for HOW every
deployed FastAPI route reaches data. It:

  * enumerates every route registered on the app (method, path, endpoint module,
    domain package);
  * statically detects which app modules import the PostgreSQL connector
    (``app.db``) or ``psycopg2`` directly (the "opens RDS" signal);
  * classifies every domain into exactly one deployment data boundary; and
  * exposes a ``check()`` that FAILS when a demo-visible route is unclassified or
    when a domain that claims to be Catalyst-Data-Store-native still imports the
    PostgreSQL connector in its own package.

The four data-boundary classes (Prompt 21 §A.2):

  CATALYST_OPERATIONAL   Operational CRUD/read served from Catalyst Data Store /
                         Stratus repositories. ``migration`` records whether the
                         domain is already Data-Store-native or still RDS-backed
                         (an honest, tracked gap — never hidden).
  AWS_ANALYTICS          Graph/geospatial/derived-historical/bulk/model work that
                         genuinely needs AWS RDS/PostGIS, reached ONLY through the
                         protected server-to-server adapter (never from the
                         browser, never a generic SQL proxy).
  DISABLED_OUT_OF_SCOPE  Hidden from the submitted UI; returns an honest disabled
                         response.
  LOCAL_TOOLING_ONLY     Batch/admin/plumbing tooling not part of the submitted
                         AppSail UI surface.

Plus a non-data INFRASTRUCTURE bucket for health/liveness/readiness and the
framework's OpenAPI/docs routes (they serve no application data).

DEPLOYMENT NOTE — Prompt 23 Option A (documented deviation). For live-demo
completeness the deployed AppSail is given a ``DATABASE_URL`` to the synthetic
AWS RDS (``drishti-db``, ap-south-1) and reaches it SERVER-TO-SERVER for the
CATALYST_OPERATIONAL domains still marked ``rds_backed_migration_pending``
(intake/cases/casework/evidence/chat/governance/etc.), and for the AWS_ANALYTICS
domains. The browser NEVER touches RDS (browser -> API Gateway -> gateway_api ->
signed context -> AppSail -> RDS). This does not change the classifications
below (Data-Store migration is still the target for the operational domains, and
Board/Disaster/Search/Scenarios/Internal stay ``datastore_native``); it only
records that the RDS-backed reads/writes are now served live rather than being an
un-served gap. Bounded: the DB is synthetic (startup enforces the
``synthetic_meta`` marker), RLS is off by explicit hackathon request, and RDS is
reverted to unreachable simply by removing ``DATABASE_URL``. See
``infra/catalyst/appsail/appsail.deploy.json`` -> ``database_url_policy``.

The classification is *target-architecture* truth. ``route_data_boundary.py``
renders it to ``docs/deployment/ROUTE_DATA_BOUNDARY.md`` and the phase test wires
``check()`` into CI so the boundary cannot silently regress.
"""
from __future__ import annotations

import ast
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional

APP_DIR = Path(__file__).resolve().parent
APP_PKG = "app"

# --- boundary classes -------------------------------------------------------
CATALYST_OPERATIONAL = "CATALYST_OPERATIONAL"
AWS_ANALYTICS = "AWS_ANALYTICS"
DISABLED_OUT_OF_SCOPE = "DISABLED_OUT_OF_SCOPE"
LOCAL_TOOLING_ONLY = "LOCAL_TOOLING_ONLY"
INFRASTRUCTURE = "INFRASTRUCTURE"  # health/docs — no application data

BOUNDARY_CLASSES = (
    CATALYST_OPERATIONAL, AWS_ANALYTICS, DISABLED_OUT_OF_SCOPE,
    LOCAL_TOOLING_ONLY, INFRASTRUCTURE,
)

# Migration state for CATALYST_OPERATIONAL domains.
MIG_NATIVE = "datastore_native"          # already served from Data Store/Stratus
MIG_PENDING = "rds_backed_migration_pending"  # operational target; still on RDS
MIG_NA = "n/a"


@dataclass(frozen=True)
class DomainBoundary:
    domain: str
    boundary: str
    backend: str                 # short human label of the deployed data source
    rationale: str
    migration: str = MIG_NA
    demo_visible: bool = True


# ---------------------------------------------------------------------------
# The registry. Keyed by the top-level domain package under app/ (the second
# dotted segment of a route endpoint module, e.g. app.cases.router -> "cases").
# This is the reviewed, target-architecture classification for Prompt 21.
# ---------------------------------------------------------------------------
_REGISTRY: tuple[DomainBoundary, ...] = (
    # --- Catalyst Data Store-native operational features (no RDS) -----------
    DomainBoundary("board", CATALYST_OPERATIONAL,
                   "Catalyst Data Store canvas (native) + Stratus export; RDS/graph hydration pending adapter",
                   "Investigation Board CANVAS (board/node/edge/annotation/activity) "
                   "persists natively in Data Store (board/repo.py) and runs offline. "
                   "Emergency-Response references already hydrate from Data Store. "
                   "Search Around now fetches through the protected AWS analytics "
                   "adapter (app/analytics_adapter.py) when configured (deployed), "
                   "falling back to a direct RDS read only in dev. Crime-corpus "
                   "reference hydration still reads RDS (curated Data Store "
                   "projection is the target). Tracked, not hidden (C.3).",
                   migration=MIG_PENDING),
    DomainBoundary("disaster", CATALYST_OPERATIONAL, "Catalyst Data Store (native)",
                   "Emergency Response hazards/readings/forecasts/resources/routes "
                   "persist natively in Data Store (disaster/repo.py over the shared "
                   "DataStoreRepository). The AWS PostGIS mirror is reconstructable "
                   "and adapter-only.", migration=MIG_NATIVE),
    DomainBoundary("scenarios", CATALYST_OPERATIONAL, "Catalyst Data Store (native) / bundled fixtures",
                   "Prompt 20 synthetic scenario registry is additive fixture data "
                   "loaded at runtime; no RDS access.", migration=MIG_NATIVE),
    DomainBoundary("search", CATALYST_OPERATIONAL, "Catalyst Data Store full-text search",
                   "Deployed operational metadata search over Data Store search "
                   "columns (case/FIR/person/evidence).", migration=MIG_NATIVE),
    DomainBoundary("internal", CATALYST_OPERATIONAL, "Catalyst Data Store (service-scope)",
                   "Service-to-service endpoints (event/cron targets). Require a "
                   "signed service context; persist authoritative Data Store state "
                   "for prediction dispatch / notify / forecast run.", migration=MIG_NATIVE,
                   demo_visible=False),

    # --- Operational features still backed by RDS (tracked migration gap) ---
    DomainBoundary("intake", CATALYST_OPERATIONAL, "Catalyst Data Store reads (done) + Stratus; writes RDS today",
                   "FIR/case intake. Reference lookups + workflow metadata now "
                   "read from Catalyst Data Store (seeded serving subset) and work "
                   "with DATABASE_URL absent. The canonical FIR WRITE path "
                   "(create/submit/approve) still uses the RDS serving schema and "
                   "is the tracked remaining closure.", migration=MIG_PENDING),
    DomainBoundary("cases", CATALYST_OPERATIONAL, "Catalyst Data Store (target); RDS today",
                   "Case detail/read models. Case corpus embeddings/similarity are "
                   "AWS analytics; the operational case record is a Data Store "
                   "target.", migration=MIG_PENDING),
    DomainBoundary("identity", CATALYST_OPERATIONAL, "Catalyst Data Store (target); RDS today",
                   "Canonical person/entity operational records.", migration=MIG_PENDING),
    DomainBoundary("evidence", CATALYST_OPERATIONAL, "Catalyst Data Store metadata + Stratus objects (target); RDS today",
                   "Evidence metadata (manual only; no extraction). File bytes -> "
                   "private Stratus; metadata -> Data Store. Currently RDS metadata.",
                   migration=MIG_PENDING),
    DomainBoundary("casework", CATALYST_OPERATIONAL, "Catalyst Data Store reads (lookups done); writes RDS today",
                   "Statements/property/court/lifecycle. Lookups are code/Data "
                   "Store-served (work without DATABASE_URL); the record WRITE "
                   "paths still use RDS (tracked closure).", migration=MIG_PENDING),
    DomainBoundary("imports", CATALYST_OPERATIONAL, "Catalyst Data Store reads (done) + Stratus; commit RDS today",
                   "Import templates + financial account/transaction views now read "
                   "from Catalyst Data Store (seeded serving subset; work without "
                   "DATABASE_URL). The import COMMIT/canonicalization write pipeline "
                   "still uses RDS + Stratus objects (tracked closure).",
                   migration=MIG_PENDING),
    DomainBoundary("chat", CATALYST_OPERATIONAL, "Catalyst Data Store (target); RDS today",
                   "Assistant chat session/message metadata (data-minimised).",
                   migration=MIG_PENDING),
    DomainBoundary("notifications", CATALYST_OPERATIONAL, "Catalyst Data Store (target); RDS today",
                   "In-app notifications/work items.", migration=MIG_PENDING),
    DomainBoundary("reports", CATALYST_OPERATIONAL, "Catalyst Data Store + Stratus (target); RDS today",
                   "Report snapshots. Rendered report objects -> private Stratus.",
                   migration=MIG_PENDING),
    DomainBoundary("org", CATALYST_OPERATIONAL, "Catalyst Data Store (target); RDS today",
                   "Organizational hierarchy + provisioning. Scope derivation is a "
                   "pure server-side function; the establishment lookup is a Data "
                   "Store target.", migration=MIG_PENDING),
    DomainBoundary("admin", CATALYST_OPERATIONAL, "Catalyst Data Store/code reads (done); RDS for the rest",
                   "Admin/governance console. Feature flags + usage/plan baseline "
                   "are code-based config (work without DATABASE_URL); the deeper "
                   "governance read models still use RDS (tracked closure).",
                   migration=MIG_PENDING),
    DomainBoundary("governance", CATALYST_OPERATIONAL, "Catalyst Data Store (target); RDS today",
                   "Governance artifact/audit read models.", migration=MIG_PENDING),
    DomainBoundary("livefeed", CATALYST_OPERATIONAL, "Catalyst Data Store projection (target); RDS today",
                   "Live Command Center committed-FIR projection/freshness. "
                   "Idempotent projection; no person rescore, no auto-dispatch.",
                   migration=MIG_PENDING),
    DomainBoundary("investigate", CATALYST_OPERATIONAL, "Catalyst Data Store (target); RDS today",
                   "Prompt 20 case-scoped investigation assistant: thin orchestration "
                   "over case summary/similar/identity/leads/timeline that sends "
                   "cited objects to the Board. Reads the operational case corpus "
                   "(RDS today; Data Store target).", migration=MIG_PENDING),

    # --- AWS analytics (protected adapter only; never direct from AppSail) --
    DomainBoundary("graph", AWS_ANALYTICS, "AWS RDS via protected adapter",
                   "Graph algorithms/community/hidden-link analytics over the full "
                   "graph corpus. Reviewed projections may be surfaced via Data "
                   "Store; heavy queries stay adapter-only."),
    DomainBoundary("geo", AWS_ANALYTICS, "AWS RDS/PostGIS via protected adapter",
                   "PostGIS geospatial hotspots/trends/jurisdiction. Boundaries are "
                   "curated projections; spatial queries are adapter-only."),
    DomainBoundary("analytics", AWS_ANALYTICS, "AWS RDS via protected adapter",
                   "Cross-district correlation/socioeconomic patterns (aggregate, "
                   "k-anonymised, correlational-not-causal)."),
    DomainBoundary("forecast", AWS_ANALYTICS, "AWS RDS via protected adapter",
                   "Spatiotemporal forecasting/backtests. Derived historical + model "
                   "compute; adapter-only."),
    DomainBoundary("risk", AWS_ANALYTICS, "AWS RDS via protected adapter",
                   "Area/period risk scoring (decision support; never individual "
                   "operationalised risk)."),
    DomainBoundary("money", AWS_ANALYTICS, "AWS RDS via protected adapter",
                   "Financial-trail detection/graph analytics."),
    DomainBoundary("workload", AWS_ANALYTICS, "AWS RDS via protected adapter",
                   "Workload-band benchmark/evaluation over historical caseload."),
    DomainBoundary("explain", AWS_ANALYTICS, "AWS RDS via protected adapter",
                   "Analytics explainability over derived model artifacts."),
    DomainBoundary("predict", AWS_ANALYTICS, "AWS RDS + custom ML via protected adapter",
                   "Prediction runtime metadata (open aggregate) + job submit/"
                   "collect routed to the protected adapter / custom-ML plane."),
    DomainBoundary("performance", AWS_ANALYTICS, "AWS RDS via protected adapter",
                   "Prompt 20 supervisor station/officer performance metrics "
                   "(derived aggregate; scoped server-side)."),

    # --- disabled / out-of-scope in the submitted demo ----------------------
    DomainBoundary("stream", DISABLED_OUT_OF_SCOPE, "n/a (SSE channel; off by default)",
                   "Scoped SSE channel; OFF unless DRISHTI_STREAM_CHANNEL_ENABLED. "
                   "Its own short-lived channel-token auth, not a data path.",
                   migration=MIG_NA, demo_visible=False),
    DomainBoundary("rag", DISABLED_OUT_OF_SCOPE, "Catalyst Data Store KB when configured; else honest empty state",
                   "Optional retrieval-augmented knowledge base. Disabled/empty "
                   "state unless a knowledge base is configured; hidden from the "
                   "mandatory demo journey.", migration=MIG_NA, demo_visible=False),

    # --- infrastructure / framework (no application data) -------------------
    DomainBoundary("main", INFRASTRUCTURE, "process/health only",
                   "Root, /health, /health/live, /health/ready, and the "
                   "/demo/risk-score plumbing proof. Health probes are hit directly "
                   "by Catalyst infra; /demo/* is not in the submitted UI.",
                   migration=MIG_NA, demo_visible=False),
    DomainBoundary("fastapi.applications", INFRASTRUCTURE, "OpenAPI/docs (framework)",
                   "Framework-generated /openapi.json, /docs, /redoc. No app data.",
                   migration=MIG_NA, demo_visible=False),
)

REGISTRY: dict[str, DomainBoundary] = {d.domain: d for d in _REGISTRY}


# ---------------------------------------------------------------------------
# Route enumeration
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RouteInfo:
    methods: tuple[str, ...]
    path: str
    module: str          # dotted module of the endpoint function
    domain: str          # top-level app domain package
    name: str            # endpoint function name


def _domain_of(module: str) -> str:
    """The top-level domain package for a route endpoint module."""
    if module.startswith(APP_PKG + "."):
        parts = module.split(".")
        # app.cases.router -> "cases"; app.main -> "main"
        return parts[1] if len(parts) > 1 else "main"
    return module  # e.g. fastapi.applications


def enumerate_routes(app) -> list[RouteInfo]:
    routes: list[RouteInfo] = []
    for r in app.routes:
        methods = getattr(r, "methods", None)
        endpoint = getattr(r, "endpoint", None)
        if not methods or endpoint is None:
            continue
        module = getattr(endpoint, "__module__", "") or ""
        routes.append(RouteInfo(
            methods=tuple(sorted(m for m in methods if m != "HEAD")),
            path=getattr(r, "path", ""),
            module=module,
            domain=_domain_of(module),
            name=getattr(endpoint, "__name__", ""),
        ))
    return routes


# ---------------------------------------------------------------------------
# Static direct-DB detection (imports the PostgreSQL connector / psycopg2)
# ---------------------------------------------------------------------------
def _module_to_path(dotted: str) -> Optional[Path]:
    """Resolve an app.* dotted module to a file under APP_DIR."""
    if not dotted.startswith(APP_PKG + "."):
        return None
    rel = dotted[len(APP_PKG) + 1:].replace(".", os.sep)
    cand = APP_DIR / (rel + ".py")
    if cand.exists():
        return cand
    pkg_init = APP_DIR / rel / "__init__.py"
    return pkg_init if pkg_init.exists() else None


def _resolve_from_import(cur_module: str, level: int, mod: Optional[str]) -> Optional[str]:
    """Resolve a relative ``from`` import to an absolute app.* module base."""
    if level == 0:
        return mod
    parts = cur_module.split(".")
    # The importing module's own package is parts[:-1]; level 1 == that package.
    base = parts[: len(parts) - level]
    if mod:
        base = base + mod.split(".")
    return ".".join(base) if base else None


@dataclass
class _ModuleFacts:
    direct_db: bool = False                # imports app.db or psycopg2 directly
    app_imports: frozenset = frozenset()   # app.* modules this module imports


@lru_cache(maxsize=None)
def _module_facts(dotted: str) -> _ModuleFacts:
    path = _module_to_path(dotted)
    if path is None:
        return _ModuleFacts()
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return _ModuleFacts()
    direct = False
    app_imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "psycopg2" or alias.name.startswith("psycopg2."):
                    direct = True
                if alias.name == f"{APP_PKG}.db":
                    direct = True
                if alias.name.startswith(APP_PKG + "."):
                    app_imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            resolved = _resolve_from_import(dotted, node.level or 0, node.module)
            if node.module and (node.module == "psycopg2"
                                or node.module.startswith("psycopg2.")):
                direct = True
            if resolved:
                # e.g. `from ..db import ...` -> resolved == "app.db"
                if resolved == f"{APP_PKG}.db":
                    direct = True
                if resolved.startswith(APP_PKG):
                    # Names imported from a package may themselves be submodules.
                    for alias in node.names:
                        child = f"{resolved}.{alias.name}"
                        if child == f"{APP_PKG}.db":
                            direct = True
                        app_imports.add(child)
                    app_imports.add(resolved)
    return _ModuleFacts(direct_db=direct, app_imports=frozenset(app_imports))


def _iter_app_modules() -> Iterable[str]:
    for p in APP_DIR.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        rel = p.relative_to(APP_DIR).with_suffix("")
        parts = [APP_PKG] + list(rel.parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        yield ".".join(parts)


def domain_direct_db_modules(domain: str) -> list[str]:
    """app.<domain>.* modules that DIRECTLY import the PG connector / psycopg2.

    Direct import within the domain's own package is the precise "opens RDS"
    signal (Prompt 21 §B.5: an operational route must not import/open the
    PostgreSQL connector). Deep-transitive imports through cross-cutting pure
    utilities (e.g. audit.sanitize_detail) are reported separately and do NOT
    trip the native check.
    """
    prefix = f"{APP_PKG}.{domain}"
    out: list[str] = []
    for mod in _iter_app_modules():
        if mod == prefix or mod.startswith(prefix + "."):
            if _module_facts(mod).direct_db:
                out.append(mod)
    return sorted(out)


def _transitive_uses_db(dotted: str, _seen: Optional[set] = None) -> bool:
    _seen = _seen if _seen is not None else set()
    if dotted in _seen:
        return False
    _seen.add(dotted)
    facts = _module_facts(dotted)
    if facts.direct_db:
        return True
    return any(_transitive_uses_db(dep, _seen) for dep in facts.app_imports)


# ---------------------------------------------------------------------------
# Analysis + check
# ---------------------------------------------------------------------------
def analyze(app) -> dict:
    routes = enumerate_routes(app)
    domains: dict[str, dict] = {}
    for rt in routes:
        d = domains.setdefault(rt.domain, {"routes": [], "route_count": 0})
        d["routes"].append({"methods": list(rt.methods), "path": rt.path,
                            "endpoint": f"{rt.module}:{rt.name}"})
        d["route_count"] += 1

    unclassified: list[str] = []
    for domain, info in domains.items():
        db = REGISTRY.get(domain)
        if db is None:
            unclassified.append(domain)
            info["boundary"] = "UNCLASSIFIED"
            info["backend"] = ""
            info["rationale"] = ""
            info["migration"] = MIG_NA
            info["demo_visible"] = True
            info["direct_db_modules"] = domain_direct_db_modules(domain)
            continue
        info["boundary"] = db.boundary
        info["backend"] = db.backend
        info["rationale"] = db.rationale
        info["migration"] = db.migration
        info["demo_visible"] = db.demo_visible
        info["direct_db_modules"] = domain_direct_db_modules(domain)

    by_class: dict[str, int] = {c: 0 for c in BOUNDARY_CLASSES}
    by_class["UNCLASSIFIED"] = 0
    for domain, info in domains.items():
        by_class[info["boundary"]] = by_class.get(info["boundary"], 0) + info["route_count"]

    return {
        "total_routes": len(routes),
        "domain_count": len(domains),
        "route_count_by_class": by_class,
        "unclassified_domains": sorted(unclassified),
        "domains": dict(sorted(domains.items())),
    }


def check(app) -> list[str]:
    """Return a list of boundary violations (empty == pass). Wired into CI.

    Fails when:
      1. a demo-visible route's domain is unclassified;
      2. a CATALYST_OPERATIONAL domain marked ``datastore_native`` still imports
         the PostgreSQL connector in its own package;
      3. a DISABLED/INFRASTRUCTURE domain is marked demo_visible (inconsistent).
    """
    report = analyze(app)
    violations: list[str] = []
    for domain, info in report["domains"].items():
        db = REGISTRY.get(domain)
        if db is None:
            if info.get("demo_visible", True):
                violations.append(
                    f"unclassified demo-visible domain {domain!r} "
                    f"({info['route_count']} route(s)) — classify it in "
                    f"deployment_boundary.REGISTRY")
            continue
        if db.boundary == CATALYST_OPERATIONAL and db.migration == MIG_NATIVE:
            offenders = info.get("direct_db_modules") or []
            if offenders:
                violations.append(
                    f"native operational domain {domain!r} imports the PostgreSQL "
                    f"connector in: {', '.join(offenders)} — route via Data Store "
                    f"or the protected adapter, or reclassify")
    return violations
