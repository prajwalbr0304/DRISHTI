"""Pluggable digital hazard-feed ingestion (Prompt 17 §D).

A connector emits normalized ``ReadingCandidate`` objects plus source/version/
licence metadata. Ingestion is idempotent, deduplicating, unit-converting,
geometry-validating and quality-tracked, with observed-at vs received-at,
late/correction handling, conflict detection and a DLQ for rejects. Every run
records a heartbeat (FeedIngestionRun) so the UI can surface stale/failed status.
An unvalidated reading never directly produces a forecast/alert (the model only
consumes the effective, valid readings — see ``resolve_effective``).

HydroMetReading is APPEND-ONLY: a correction is a NEW row (never a rewrite), and
supersession is DERIVED (latest ReceivedAt wins for a given observed instant).

Connectors:
  * ``SyntheticReplayConnector`` — the required deterministic replay from
    JSON/CSV (the reliable demo path);
  * ``RecordedSampleConnector`` — the live-connector CONTRACT (IMD/KSNDMC
    rainfall) exercised against an approved, versioned RECORDED SAMPLE. Marked
    ``external_access_required`` because a documented live endpoint/licence/
    credential was not available at implementation time (see the phase report).

We never scrape a portal or bypass registration/terms. Raw approved payloads go
to private Stratus (pointer only); normalized rows go to Data Store. Full
payloads/credentials are never logged.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from ..datastore import disaster_schema as ds
from .repo import DisasterRepo, disaster_repo

_VALID_METRICS = set(ds.HYDROMET_METRICS)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _parse_ts(v: Any) -> Optional[datetime]:
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if not v:
        return None
    try:
        dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# canonical units + conversion
# ---------------------------------------------------------------------------
_CANONICAL_UNIT = {
    "rainfall": "mm", "river_level": "m", "reservoir_level": "m",
    "temperature": "C", "wind": "kmph", "humidity": "%",
}


def normalize_unit(metric: str, value: Optional[float], unit: Optional[str]
                   ) -> tuple[Optional[float], str, bool]:
    """Convert (value, unit) to the canonical unit for a metric.

    Returns (canonical_value, canonical_unit, converted?). Unknown units pass
    through unchanged (converted=False)."""
    canonical = _CANONICAL_UNIT.get(metric, unit or "")
    if value is None:
        return None, canonical, False
    u = (unit or "").strip().lower()
    v = float(value)
    conv = False
    if metric == "rainfall":
        if u in ("cm", "centimetre", "centimeter"):
            v, conv = v * 10.0, True
        elif u in ("m", "metre", "meter"):
            v, conv = v * 1000.0, True
        elif u in ("in", "inch", "inches"):
            v, conv = v * 25.4, True
    elif metric in ("river_level", "reservoir_level"):
        if u in ("ft", "feet", "foot"):
            v, conv = v * 0.3048, True
        elif u in ("cm",):
            v, conv = v / 100.0, True
    elif metric == "temperature":
        if u in ("f", "fahrenheit"):
            v, conv = (v - 32.0) * 5.0 / 9.0, True
        elif u in ("k", "kelvin"):
            v, conv = v - 273.15, True
    elif metric == "wind":
        if u in ("mps", "m/s", "ms"):
            v, conv = v * 3.6, True
        elif u in ("knots", "kt", "kn"):
            v, conv = v * 1.852, True
    return round(v, 4), canonical, conv


# ---------------------------------------------------------------------------
# reading candidate + connector interface
# ---------------------------------------------------------------------------
@dataclass
class ReadingCandidate:
    station_code: str
    metric_type: str
    value: Optional[float]
    unit: Optional[str]
    observed_at: Optional[str]
    lon: Optional[float] = None
    lat: Optional[float] = None
    district_id: Optional[int] = None
    source_agency: Optional[str] = None


@dataclass
class ConnectorMeta:
    code: str
    name: str
    provider: str
    connector_kind: str            # synthetic_replay | recorded_sample | live
    licence: str = ""
    attribution: str = ""
    freshness_sla_minutes: int = 180
    external_access_required: bool = False


class Connector:
    """Base connector contract. Subclasses emit normalized reading candidates."""

    meta: ConnectorMeta

    def emit(self, *, now: Optional[datetime] = None) -> list[ReadingCandidate]:
        raise NotImplementedError


class SyntheticReplayConnector(Connector):
    """Required hackathon connector: deterministic replay from JSON/CSV (or a
    bundled deterministic sample). The reliable demo path."""

    meta = ConnectorMeta(
        code="synthetic_replay", name="Synthetic deterministic replay",
        provider="DRISHTI datagen", connector_kind="synthetic_replay",
        licence="synthetic", attribution="Synthetic hackathon data",
        freshness_sla_minutes=180, external_access_required=False)

    def __init__(self, rows: Optional[list[dict]] = None,
                 csv_text: Optional[str] = None):
        self._rows = rows
        self._csv_text = csv_text

    def emit(self, *, now: Optional[datetime] = None) -> list[ReadingCandidate]:
        now = now or _now()
        if self._csv_text is not None:
            return self._from_csv(self._csv_text)
        if self._rows is not None:
            return [self._to_candidate(r) for r in self._rows]
        return self._bundled_sample(now)

    @staticmethod
    def _to_candidate(r: dict) -> ReadingCandidate:
        return ReadingCandidate(
            station_code=str(r.get("station_code") or r.get("StationCode") or ""),
            metric_type=str(r.get("metric_type") or r.get("MetricType") or ""),
            value=(None if r.get("value") in (None, "") else float(r.get("value"))),
            unit=r.get("unit"), observed_at=r.get("observed_at"),
            lon=(float(r["lon"]) if r.get("lon") not in (None, "") else None),
            lat=(float(r["lat"]) if r.get("lat") not in (None, "") else None),
            district_id=(int(r["district_id"]) if r.get("district_id") not in (None, "") else None),
            source_agency=r.get("source_agency"))

    def _from_csv(self, text: str) -> list[ReadingCandidate]:
        reader = csv.DictReader(io.StringIO(text))
        return [self._to_candidate(row) for row in reader]

    @staticmethod
    def _bundled_sample(now: datetime) -> list[ReadingCandidate]:
        """A small deterministic rainfall/river batch anchored to ``now`` — a
        rising monsoon rainfall sequence at a coastal station plus a river level
        in feet (to exercise unit conversion)."""
        out: list[ReadingCandidate] = []
        base = now - timedelta(hours=6)
        for i, mm in enumerate((18.0, 34.0, 61.0, 88.0, 120.0, 96.0)):
            out.append(ReadingCandidate(
                station_code="KSNDMC-DK-001", metric_type="rainfall", value=mm,
                unit="mm", observed_at=_iso(base + timedelta(hours=i)),
                lon=74.856, lat=12.914, source_agency="KSNDMC(synthetic)"))
        out.append(ReadingCandidate(
            station_code="CWC-NETRAVATI-01", metric_type="river_level", value=28.5,
            unit="ft", observed_at=_iso(now), lon=74.87, lat=12.87,
            source_agency="CWC(synthetic)"))
        return out


class RecordedSampleConnector(Connector):
    """Live-connector CONTRACT exercised against an approved recorded sample.

    Prefer official rainfall (IMD/KSNDMC/CWC). A documented live endpoint,
    licence and credential were NOT available at implementation time, so this
    runs the same connector contract against a versioned recorded sample and is
    marked ``external_access_required`` — the deterministic replay stays the
    reliable demo path. We never scrape a portal or bypass registration/terms."""

    meta = ConnectorMeta(
        code="imd_rainfall_recorded", name="IMD/KSNDMC rainfall (recorded sample)",
        provider="IMD / KSNDMC", connector_kind="recorded_sample",
        licence="Recorded sample — official terms apply; live access pending",
        attribution="India Meteorological Department / KSNDMC (recorded sample)",
        freshness_sla_minutes=180, external_access_required=True)

    SAMPLE_VERSION = "recorded-2024-07-15"
    _SAMPLE = [
        {"station_code": "IMD-MNG-AWS", "metric_type": "rainfall", "value": 72.0,
         "unit": "mm", "lon": 74.842, "lat": 12.914, "source_agency": "IMD"},
        {"station_code": "IMD-MNG-AWS", "metric_type": "temperature", "value": 27.4,
         "unit": "C", "lon": 74.842, "lat": 12.914, "source_agency": "IMD"},
    ]

    def emit(self, *, now: Optional[datetime] = None) -> list[ReadingCandidate]:
        now = now or _now()
        return [ReadingCandidate(
            station_code=r["station_code"], metric_type=r["metric_type"],
            value=r["value"], unit=r["unit"],
            observed_at=_iso(now - timedelta(minutes=30)),
            lon=r["lon"], lat=r["lat"], source_agency=r["source_agency"])
            for r in self._SAMPLE]


class LiveOpenMeteoConnector(Connector):
    """Read-only LIVE weather connector (Prompt 17 §D.3).

    Open-Meteo (https://open-meteo.com) is a documented, free, **no-API-key**
    weather API (CC BY 4.0, free for non-commercial use) covering Karnataka. It
    supplies live precipitation (rainfall), temperature, wind and humidity for
    each configured station — the read-only live rainfall/weather path.

    We attribute the source ("Weather data by Open-Meteo.com, CC BY 4.0"), store
    no credential, and never scrape a portal. Official gauge networks (IMD/
    KSNDMC/CWC) remain registration-gated (see RecordedSampleConnector). If the
    network is unavailable the run fails-closed (DLQ) and the deterministic
    synthetic replay remains the reliable demo path.
    """

    meta = ConnectorMeta(
        code="open_meteo_live", name="Open-Meteo live weather (rainfall/temp/wind/humidity)",
        provider="Open-Meteo", connector_kind="live",
        licence="CC BY 4.0 (open-meteo.com) — free for non-commercial use",
        attribution="Weather data by Open-Meteo.com (CC BY 4.0)",
        freshness_sla_minutes=180, external_access_required=False)

    # Live stations across the demo districts (district ids match DISTRICT_NAMES).
    DEFAULT_STATIONS = [
        {"station_code": "OM-DK-MANGALURU", "district_id": 24, "lat": 12.914, "lon": 74.856},
        {"station_code": "OM-BLR-URBAN", "district_id": 5, "lat": 12.9716, "lon": 77.5946},
        {"station_code": "OM-KODAGU-MADIKERI", "district_id": 18, "lat": 12.4218, "lon": 75.7382},
        {"station_code": "OM-KALABURAGI", "district_id": 16, "lat": 17.3297, "lon": 76.8343},
    ]
    # Open-Meteo `current` field -> (canonical metric, unit).
    _METRICS = [("precipitation", "rainfall", "mm"),
                ("temperature_2m", "temperature", "C"),
                ("relative_humidity_2m", "humidity", "%"),
                ("wind_speed_10m", "wind", "kmph")]

    def __init__(self, stations: Optional[list[dict]] = None,
                 base_url: Optional[str] = None, timeout_s: Optional[float] = None):
        from ..config import get_settings
        s = get_settings()
        self.stations = stations or self.DEFAULT_STATIONS
        self.base_url = (base_url or s.openmeteo_url).rstrip("/")
        self.timeout_s = timeout_s if timeout_s is not None else s.live_feed_timeout_s

    @classmethod
    def _map_response(cls, data: dict, station: dict,
                      now: Optional[datetime] = None) -> list[ReadingCandidate]:
        """Map one Open-Meteo `current` response into reading candidates. Pure
        (no network) so it is unit-testable against a canned payload."""
        cur = (data or {}).get("current") or {}
        obs = _parse_ts(cur.get("time"))
        obs_iso = (obs or now or _now()).isoformat()
        out: list[ReadingCandidate] = []
        for api_key, metric, unit in cls._METRICS:
            val = cur.get(api_key)
            if val is None:
                continue
            out.append(ReadingCandidate(
                station_code=station["station_code"], metric_type=metric,
                value=float(val), unit=unit, observed_at=obs_iso,
                lon=station["lon"], lat=station["lat"],
                district_id=station.get("district_id"), source_agency="Open-Meteo"))
        return out

    def emit(self, *, now: Optional[datetime] = None) -> list[ReadingCandidate]:
        import httpx  # local import: keep the module importable without httpx
        now = now or _now()
        current_vars = ",".join(k for k, _, _ in self._METRICS)
        out: list[ReadingCandidate] = []
        with httpx.Client(timeout=self.timeout_s) as client:
            for st in self.stations:
                resp = client.get(self.base_url, params={
                    "latitude": st["lat"], "longitude": st["lon"],
                    "current": current_vars, "timezone": "UTC"})
                resp.raise_for_status()
                out.extend(self._map_response(resp.json(), st, now))
        if not out:
            raise RuntimeError("live feed returned no readings")
        return out


CONNECTORS: dict[str, type[Connector]] = {
    SyntheticReplayConnector.meta.code: SyntheticReplayConnector,
    RecordedSampleConnector.meta.code: RecordedSampleConnector,
    LiveOpenMeteoConnector.meta.code: LiveOpenMeteoConnector,
}

# Connectors that make outbound network calls (gated by config.live_feed_enabled).
LIVE_FEED_CODES = {LiveOpenMeteoConnector.meta.code}


def connector_for(feed_code: str) -> Connector:
    return CONNECTORS.get(feed_code, SyntheticReplayConnector)()


# ---------------------------------------------------------------------------
# ingestion
# ---------------------------------------------------------------------------
def ensure_feed_source(repo: DisasterRepo, meta: ConnectorMeta) -> dict:
    existing = repo.find_one("FeedSource", {"Code": meta.code})
    if existing:
        return existing
    return repo.create("FeedSource", {
        "Code": meta.code, "Name": meta.name, "Provider": meta.provider,
        "ConnectorKind": meta.connector_kind, "Licence": meta.licence,
        "Attribution": meta.attribution, "FreshnessSlaMinutes": meta.freshness_sla_minutes,
        "ExternalAccessRequired": bool(meta.external_access_required)})


def _validate(cand: ReadingCandidate) -> Optional[str]:
    if not cand.station_code:
        return "missing station_code"
    if cand.metric_type not in _VALID_METRICS:
        return f"unknown metric {cand.metric_type!r}"
    if not cand.observed_at or _parse_ts(cand.observed_at) is None:
        return "missing/invalid observed_at"
    if cand.lon is not None and not (-180 <= cand.lon <= 180):
        return "lon out of range"
    if cand.lat is not None and not (-90 <= cand.lat <= 90):
        return "lat out of range"
    return None


def _source_key(feed_code: str, station: str, metric: str, observed_at: Optional[str],
                value: Optional[float]) -> str:
    """Idempotent key includes the value, so an exact re-send dedups but a
    CORRECTED value is a new (append-only) row for the same observed instant."""
    return f"{feed_code}:{station}:{metric}:{observed_at}:{'NA' if value is None else value}"


def ingest(feed_code: str, *, connector: Optional[Connector] = None,
           candidates: Optional[list[ReadingCandidate]] = None,
           actor: str = "system", now: Optional[datetime] = None,
           repo: Optional[DisasterRepo] = None) -> dict:
    """Run one ingestion for ``feed_code``. Idempotent + dedup + unit-convert +
    quality + late/correction + conflict + DLQ. Records a FeedIngestionRun and
    returns the run row."""
    repo = repo or disaster_repo()
    now = now or _now()
    conn = connector or connector_for(feed_code)
    meta = conn.meta
    ensure_feed_source(repo, meta)

    started = now
    accepted = duplicate = rejected = 0
    dlq: list[dict] = []
    last_observed: Optional[datetime] = None
    run_status = "ok"

    if candidates is None:
        cands: list[ReadingCandidate] = []
        last_exc: Optional[Exception] = None
        for _ in range(2):                       # retry once, then DLQ the run
            try:
                cands = conn.emit(now=now)
                last_exc = None
                break
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
        if last_exc is not None:
            return repo.create("FeedIngestionRun", {
                "FeedCode": feed_code, "StartedAt": _iso(started),
                "FinishedAt": _iso(_now()), "Status": "failed",
                "AcceptedCount": 0, "DuplicateCount": 0, "RejectedCount": 0,
                "Detail": {"error": type(last_exc).__name__, "dlq": True}})
    else:
        cands = candidates

    seen_keys: set[str] = set()
    seen_instant: dict[tuple, float] = {}
    for cand in cands:
        err = _validate(cand)
        if err:
            rejected += 1
            dlq.append({"station": cand.station_code, "reason": err})
            continue
        value, unit, _conv = normalize_unit(cand.metric_type, cand.value, cand.unit)
        quality = "valid" if value is not None else "missing"
        obs = _parse_ts(cand.observed_at)
        instant = (cand.station_code, cand.metric_type, cand.observed_at)
        key = _source_key(feed_code, cand.station_code, cand.metric_type,
                          cand.observed_at, value)

        # exact idempotent replay within this batch
        if key in seen_keys:
            duplicate += 1
            continue
        seen_keys.add(key)

        # in-batch conflict: same observed instant, different value -> flag suspect
        if instant in seen_instant and value is not None and seen_instant[instant] != value:
            quality = "suspect"
        seen_instant.setdefault(instant, value if value is not None else -1e18)

        # cross-run exact idempotency
        if repo.find_one("HydroMetReading", {"SourceRecordID": key}) is not None:
            duplicate += 1
            continue

        # correction of a prior value for the same observed instant -> 'late'
        prior_same_instant = [
            r for r in repo.list("HydroMetReading",
                                 where={"StationCode": cand.station_code,
                                        "MetricType": cand.metric_type})
            if r.get("ObservedAt") == cand.observed_at]
        if prior_same_instant and quality == "valid":
            quality = "late"
        else:
            latest = _latest_observed(repo, cand.station_code, cand.metric_type)
            if obs and latest and obs < latest and quality == "valid":
                quality = "late"

        repo.create("HydroMetReading", {
            "StationCode": cand.station_code, "SourceAgency": cand.source_agency,
            "MetricType": cand.metric_type, "Value": value, "Unit": unit,
            "Lon": cand.lon, "Lat": cand.lat, "DistrictID": cand.district_id,
            "ObservedAt": cand.observed_at, "ReceivedAt": _iso(now),
            "QualityFlag": quality, "SourceRecordID": key, "FeedCode": feed_code})
        accepted += 1
        last_observed = _max_dt(last_observed, obs)

    if last_observed is not None:
        age_min = (now - last_observed).total_seconds() / 60.0
        if age_min > meta.freshness_sla_minutes:
            run_status = "stale"
    if rejected and accepted and run_status == "ok":
        run_status = "partial"
    if rejected and not accepted:
        run_status = "failed"

    run = repo.create("FeedIngestionRun", {
        "FeedCode": feed_code, "StartedAt": _iso(started), "FinishedAt": _iso(_now()),
        "Status": run_status, "AcceptedCount": accepted, "DuplicateCount": duplicate,
        "RejectedCount": rejected, "LastObservedAt": _iso(last_observed),
        "Detail": {"dlq": dlq[:20], "connector": meta.connector_kind,
                   "external_access_required": meta.external_access_required}})
    repo.append_activity("feed", feed_code, actor=actor, action="feed.ingest",
                         diff={"accepted": accepted, "duplicate": duplicate,
                               "rejected": rejected, "status": run_status})
    return run


def _latest_observed(repo: DisasterRepo, station: str, metric: str) -> Optional[datetime]:
    best: Optional[datetime] = None
    for r in repo.list("HydroMetReading",
                       where={"StationCode": station, "MetricType": metric}):
        best = _max_dt(best, _parse_ts(r.get("ObservedAt")))
    return best


def _max_dt(a: Optional[datetime], b: Optional[datetime]) -> Optional[datetime]:
    if a is None:
        return b
    if b is None:
        return a
    return max(a, b)


# ---------------------------------------------------------------------------
# effective readings (derived supersession — latest ReceivedAt wins per instant)
# ---------------------------------------------------------------------------
def resolve_effective(readings: list[dict]) -> list[dict]:
    """Collapse readings to the effective set: for a given (station, metric,
    observed instant) keep the LATEST received row (a correction supersedes the
    original by derivation — append-only, history preserved)."""
    best: dict[tuple, dict] = {}
    for r in readings:
        instant = (r.get("StationCode"), r.get("MetricType"), r.get("ObservedAt"))
        cur = best.get(instant)
        if cur is None or _parse_ts(r.get("ReceivedAt")) is None:
            best[instant] = r if cur is None else cur
        rr = _parse_ts(r.get("ReceivedAt"))
        cc = _parse_ts(cur.get("ReceivedAt")) if cur else None
        if cur is None or (rr and (cc is None or rr >= cc)):
            best[instant] = r
    return list(best.values())


def valid_readings(readings: list[dict]) -> list[dict]:
    """Effective readings that are usable by a model: valid or a valid late
    correction; missing/suspect/superseded are excluded (never feed a forecast)."""
    eff = resolve_effective(readings)
    return [r for r in eff if r.get("QualityFlag") in ("valid", "late")
            and r.get("Value") is not None]


# ---------------------------------------------------------------------------
# freshness / heartbeat
# ---------------------------------------------------------------------------
def freshness(repo: Optional[DisasterRepo] = None, *,
              now: Optional[datetime] = None) -> list[dict]:
    """Per-source freshness/heartbeat for the UI banner. status in
    fresh|stale|failed|never."""
    repo = repo or disaster_repo()
    now = now or _now()
    sources = repo.list("FeedSource")
    runs_all = repo.list("FeedIngestionRun")
    codes = {s.get("Code") for s in sources} | {r.get("FeedCode") for r in runs_all}
    by_code = {s.get("Code"): s for s in sources}

    out: list[dict] = []
    for code in sorted(c for c in codes if c):
        src = by_code.get(code, {})
        runs = sorted((r for r in runs_all if r.get("FeedCode") == code),
                      key=lambda r: int(r.get("FeedIngestionRunID") or 0))
        last_run = runs[-1] if runs else None
        last_obs = None
        for r in runs:
            last_obs = _max_dt(last_obs, _parse_ts(r.get("LastObservedAt")))
        sla = int(src.get("FreshnessSlaMinutes") or 180)
        age = None
        status = "never"
        if last_obs is not None:
            age = round((now - last_obs).total_seconds() / 60.0, 1)
            status = "stale" if age > sla else "fresh"
        if last_run and last_run.get("Status") == "failed":
            status = "failed"
        out.append({
            "feed_code": code, "provider": src.get("Provider"),
            "connector_kind": src.get("ConnectorKind") or "synthetic_replay",
            "external_access_required": bool(src.get("ExternalAccessRequired")),
            "freshness_sla_minutes": sla, "last_observed_at": _iso(last_obs),
            "last_run_at": (last_run.get("FinishedAt") if last_run else None),
            "age_minutes": age, "status": status,
            "licence": src.get("Licence"), "attribution": src.get("Attribution")})
    return out
