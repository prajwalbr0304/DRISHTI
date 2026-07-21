"""Load the deterministic synthetic disaster fixture into Catalyst Data Store.

The fixture (datagen/disaster.py -> fixtures/golden-001/disaster_response.json)
holds Data Store rows keyed by table name (PascalCase columns matching
disaster_schema). This module upserts them into the disaster repo (idempotent by
ExternalID/pk). It is used by ``POST /disaster/demo/seed`` and by the backend
tests (mirrors how the board tests load datagen/investigation_board.py).

Reading timestamps are OPTIONALLY rebased so the freshest reading aligns to
``now`` — the live demo then shows fresh forecasts while the deliberately-stale
scenario stays stale. Tests pass a fixed ``now`` for determinism.
"""
from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from ..datapaths import repo_data_path
from ..datastore import disaster_schema as ds
from .repo import DisasterRepo, disaster_repo

# The datagen fixture/module exist in the repo checkout under datagen/; they are
# ABSENT in the minimal AppSail image (only app/ + sql/ are copied), where
# repo_data_path returns None. Resolving these at import must therefore never
# raise — load_fixture() is called on-demand (POST /disaster/demo/seed), and in
# the deployed image disaster rows come from Catalyst Data Store (provisioned via
# infra/catalyst/ds-schema), not this local fixture.
_FIXTURE = repo_data_path("datagen", "fixtures", "golden-001", "disaster_response.json")
_DATAGEN = repo_data_path("datagen", "disaster.py")


def load_fixture() -> dict:
    """Load the committed fixture JSON; if absent, build it from datagen by path.
    Raises a clear error only when neither is available (e.g. the minimal image),
    where the disaster demo is seeded via the Catalyst ds-schema provisioner."""
    if _FIXTURE and _FIXTURE.exists():
        return json.loads(_FIXTURE.read_text(encoding="utf-8"))
    if not _DATAGEN or not _DATAGEN.exists():
        raise RuntimeError(
            "Disaster fixture unavailable: the datagen tree is not present in this "
            "image. Seed disaster Data Store rows via infra/catalyst/ds-schema, or "
            "run from the repo checkout for the local fixture.")
    spec = importlib.util.spec_from_file_location("drishti_disaster_fixture", _DATAGEN)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod.build_disaster_fixture()


def _parse(v) -> Optional[datetime]:
    if not v:
        return None
    try:
        dtv = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return dtv if dtv.tzinfo else dtv.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _rebase(fixture: dict, now: datetime) -> dict:
    """Shift reading + event timestamps so the freshest reading aligns to ``now``
    (preserves relative spacing so the stale scenario stays stale)."""
    readings = fixture["tables"].get("HydroMetReading", [])
    observed = [_parse(r.get("ObservedAt")) for r in readings if r.get("ObservedAt")]
    observed = [o for o in observed if o]
    if not observed:
        return fixture
    shift = now - max(observed)

    def _shift(v):
        p = _parse(v)
        return (p + shift).isoformat() if p else v

    for r in readings:
        r["ObservedAt"] = _shift(r.get("ObservedAt"))
        r["ReceivedAt"] = _shift(r.get("ReceivedAt"))
        # keep the idempotent source key consistent with the shifted observed_at
        if r.get("SourceRecordID") and ":" in str(r["SourceRecordID"]):
            parts = str(r["SourceRecordID"]).split(":")
            # feed:station:metric:observed:value  -> rebuild observed segment
            if len(parts) >= 5:
                parts_obs = ":".join(parts[3:-1])
                new_obs = _shift(parts_obs)
                r["SourceRecordID"] = ":".join(parts[:3] + [new_obs, parts[-1]])
    for e in fixture["tables"].get("HazardEvent", []):
        for k in ("OnsetAt", "PredictedPeakAt"):
            if e.get(k):
                e[k] = _shift(e[k])
    for a in fixture["tables"].get("AlertHistory", []):
        if a.get("CreatedAt"):
            a["CreatedAt"] = _shift(a["CreatedAt"])
    for run in fixture["tables"].get("FeedIngestionRun", []):
        for k in ("StartedAt", "FinishedAt", "LastObservedAt", "CreatedAt"):
            if run.get(k):
                run[k] = _shift(run[k])
    fixture["_rebased_to"] = now.isoformat()
    return fixture


def seed_from_fixture(fixture: Optional[dict] = None, *, repo: Optional[DisasterRepo] = None,
                      now: Optional[datetime] = None, rebase: bool = True) -> dict:
    """Upsert the fixture rows into the disaster repo. Idempotent by pk/ExternalID.
    Returns per-table row counts."""
    repo = repo or disaster_repo()
    fixture = fixture if fixture is not None else load_fixture()
    if rebase:
        fixture = _rebase(json.loads(json.dumps(fixture)),  # copy (don't mutate caller)
                          now or datetime.now(timezone.utc))

    counts: dict[str, int] = {}
    ds_tables = set(ds.table_names())
    for table, rows in fixture.get("tables", {}).items():
        n = 0
        for row in rows:
            if table == "AlertHistory":
                aid = int(row["AlertID"])
                repo.store.upsert("AlertHistory", f"alert:{aid}", dict(row))
                n += 1
                continue
            if table not in ds_tables:
                continue
            pk = ds.table(table).pk
            repo.create(table, dict(row), pk_value=int(row[pk]))
            n += 1
        counts[table] = n
    repo.reseed_counters()
    counts["_rebased"] = bool(rebase)
    counts["scenario_coverage"] = len(fixture.get("scenario_coverage", {}))
    return counts
