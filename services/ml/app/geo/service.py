"""High-level geospatial reads: typed payloads + the AiResult contract.

All reads run on the restricted read-only connection and aggregate server-side
(never ship raw incident rows). Hotspots/alerts are precomputed by batch jobs.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from .. import db
from ..cases import casedata
from ..contracts import AiResult
from . import trends
from .schemas import (AlertFeature, AlertResponse, HotspotFeature, HotspotResponse,
                      TrendDecomposition, TrendPoint, TrendResponse)

GEO_HOTSPOT_MODEL = "drishti-hotspot-kde@1.1.0"
GEO_TREND_MODEL = "drishti-trends@1.0.0"
GEO_ALERT_MODEL = "drishti-emerging-trend@1.0.0"


def hotspots(bbox: Optional[tuple] = None, start: Optional[dt.date] = None,
             end: Optional[dt.date] = None, crime_head_id: Optional[int] = None,
             limit: int = 500, district_ids: Optional[list] = None,
             crime_head_ids: Optional[list] = None) -> HotspotResponse:
    """Active hotspots, optionally confined to a seat's districts and crime heads.

    ``district_ids`` / ``crime_head_ids`` are the SEAT's confinement, applied
    server-side. The frontend used to fetch this unscoped and narrow the rows in a
    react-query `select`, which is fine for presentation but means the wire carried
    every district's hotspots regardless of who asked.

    An EMPTY list is meaningful and is not ignored: it denotes a seat entitled to
    nothing, so it must return nothing rather than everything.
    """
    from ..cases import analytics_policy

    limit = max(1, min(int(limit), 2000))
    where = ['h."IsActive"']
    params: list = []
    if bbox:
        where.append('ST_Intersects(h."geom", ST_MakeEnvelope(%s,%s,%s,%s,4326))')
        params.extend(bbox)
    if crime_head_id is not None:
        where.append('h."CrimeHeadID" = %s')
        params.append(crime_head_id)
    if district_ids is not None:
        if not district_ids:
            where.append("FALSE")
        else:
            where.append('h."DistrictID" = ANY(%s)')
            params.append([int(d) for d in district_ids])
    # A WING seat is state-wide geographically and narrowed by crime head instead.
    if crime_head_ids:
        where.append('h."CrimeHeadID" = ANY(%s)')
        params.append([int(h) for h in crime_head_ids])
    if start is not None:
        where.append('(h."PeriodEnd" IS NULL OR h."PeriodEnd" >= %s)')
        params.append(start)
    if end is not None:
        where.append('(h."PeriodStart" IS NULL OR h."PeriodStart" <= %s)')
        params.append(end)
    sql = (
        'SELECT h."HotspotID", h."Name", h."DistrictID", d."DistrictName", h."CrimeHeadID", '
        'ch."CrimeGroupName", h."Intensity"::float, h."CaseCount", '
        'ST_X(h."Centroid"), ST_Y(h."Centroid"), ST_AsGeoJSON(h."geom")::json, '
        'h."PeriodStart", h."PeriodEnd", h."ModelVersionID", mv."ModelName", '
        'mv."Version", mv."Hyperparameters" '
        'FROM "CrimeHotspot" h '
        'JOIN "ModelVersion" mv ON mv."ModelVersionID"=h."ModelVersionID" '
        'LEFT JOIN "District" d ON d."DistrictID" = h."DistrictID" '
        'LEFT JOIN "CrimeHead" ch ON ch."CrimeHeadID" = h."CrimeHeadID" '
        'WHERE ' + ' AND '.join(where) +
        ' ORDER BY h."Intensity" DESC NULLS LAST LIMIT %s'
    )
    params.append(limit)
    with db.ro_conn() as conn:
        current = analytics_policy.current_attestation(conn)
        # This run manifest is also the proof that a zero-row generation is a
        # genuine empty result rather than missing/legacy analytics.
        analytics_policy.latest_complete_generation(
            conn, model_names=["drishti-hotspot-kde"], ref_table="CrimeHotspot",
            artifact="hotspots", current=current)
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        for row in rows:
            analytics_policy.require_current(
                conn, row[16], f"CrimeHotspot {row[0]}", current=current)
    feats = [HotspotFeature(
        hotspot_id=int(r[0]), name=r[1], district_id=r[2], district_name=r[3],
        crime_head_id=r[4], crime_group=r[5], intensity=r[6], case_count=r[7],
        centroid_lon=r[8], centroid_lat=r[9], geometry=r[10],
        period_start=str(r[11]) if r[11] else None, period_end=str(r[12]) if r[12] else None)
        for r in rows]
    result = AiResult(
        answer=f"{len(feats)} active hotspots" + (f" for crime head {crime_head_id}" if crime_head_id else "") + ".",
        confidence=1.0,
        source_record_ids=[f"CrimeHotspot:{f.hotspot_id}" for f in feats[:50]],
        reasoning_summary="ST-DBSCAN clusters scored by Gaussian KDE, aggregated "
                          "server-side; filtered by bbox/time/crime head.",
        model_version=GEO_HOTSPOT_MODEL)
    return HotspotResponse(result=result, count=len(feats), hotspots=feats)


def trends_series(district_id=None, head_id=None, sub_head_id=None,
                  start=None, end=None, window: int = 6, k: float = 2.0,
                  decompose: bool = True, district_ids=None,
                  crime_head_ids=None) -> TrendResponse:
    """Monthly trend series, optionally confined to a seat's districts/heads.

    The returned ``scope`` echoes the confinement that was actually applied, so a
    caller can tell a range total from a single district's — otherwise a DIG's
    figure is indistinguishable from a state figure on the wire.
    """
    with db.ro_conn() as conn:
        periods, counts = trends.monthly_series(
            conn, district_id, head_id, sub_head_id, start, end,
            district_ids=district_ids, crime_head_ids=crime_head_ids)
    scope = {"district_id": district_id, "crime_head_id": head_id,
             "sub_head_id": sub_head_id,
             "district_ids": list(district_ids) if district_ids is not None else None,
             "crime_head_ids": list(crime_head_ids) if crime_head_ids else None}
    if not periods:
        result = AiResult(answer="No cases match this scope.", confidence=0.0,
                          source_record_ids=[], reasoning_summary="Empty series.",
                          model_version=GEO_TREND_MODEL)
        return TrendResponse(result=result, scope=scope, total=0, series=[])
    mean, upper, lower, anomaly = trends.rolling_band(counts, window=window, k=k)
    d = trends.deltas(periods, counts)
    series = [TrendPoint(period=periods[i], count=counts[i], rolling_mean=mean[i],
                         rolling_upper=upper[i], rolling_lower=lower[i], is_anomaly=anomaly[i])
              for i in range(len(periods))]
    decomp = None
    if decompose:
        tr, se, re = trends.decompose(periods, counts)
        decomp = TrendDecomposition(periods=periods, trend=tr, seasonal=se, residual=re)
    n_anom = sum(1 for a in anomaly if a)
    result = AiResult(
        answer=(f"{sum(counts)} cases over {len(periods)} months; latest {d.get('latest')} "
                f"(MoM {d.get('mom_pct')}%, YoY {d.get('yoy_pct')}%); {n_anom} anomalous month(s)."),
        confidence=1.0,
        source_record_ids=[f"CaseMaster(scope):{scope}"],
        reasoning_summary=f"Monthly volume; trailing {window}-mo rolling mean +/- {k}σ band; "
                          "additive trend/seasonal/residual decomposition.",
        model_version=GEO_TREND_MODEL)
    return TrendResponse(result=result, scope=scope, total=sum(counts),
                         latest_period=d.get("latest_period"), mom_delta=d.get("mom_delta"),
                         mom_pct=d.get("mom_pct"), yoy_delta=d.get("yoy_delta"),
                         yoy_pct=d.get("yoy_pct"), series=series, decomposition=decomp)


def active_alerts(bbox=None, severity: Optional[str] = None, alert_type: Optional[str] = None,
                  limit: int = 200) -> AlertResponse:
    from ..cases import analytics_policy

    limit = max(1, min(int(limit), 1000))
    where = ['a."Status" IN (\'open\',\'acknowledged\')']
    params: list = []
    if severity:
        where.append('a."Severity" = %s')
        params.append(severity)
    if alert_type:
        where.append('a."AlertType" = %s')
        params.append(alert_type)
    if bbox:
        where.append('a."geom" IS NOT NULL AND ST_Intersects(a."geom", ST_MakeEnvelope(%s,%s,%s,%s,4326))')
        params.extend(bbox)
    sql = (
        'SELECT a."AlertID", a."AlertType"::text, a."Severity"::text, a."Title", a."Message", '
        'a."DistrictID", d."DistrictName", (a."Payload"->>\'crime_head_id\')::int, '
        'ST_X(a."geom"), ST_Y(a."geom"), '
        'a."Status"::text, a."Payload", a."CreatedAt", a."ModelVersionID", '
        'mv."ModelName", mv."Hyperparameters", a."HazardEventID" '
        'FROM "AlertHistory" a LEFT JOIN "District" d ON d."DistrictID" = a."DistrictID" '
        'LEFT JOIN "ModelVersion" mv ON mv."ModelVersionID"=a."ModelVersionID" '
        'WHERE ' + ' AND '.join(where) +
        ' ORDER BY CASE a."Severity" WHEN \'critical\' THEN 4 WHEN \'high\' THEN 3 '
        "WHEN 'medium' THEN 2 WHEN 'low' THEN 1 ELSE 0 END DESC, a.\"CreatedAt\" DESC LIMIT %s"
    )
    params.append(limit)
    case_models = {"drishti-emerging-trend", "drishti-early-warning"}
    independent_models = {"drishti-money-aml"}
    with db.ro_conn() as conn:
        current = analytics_policy.current_attestation(conn)
        # The shared feed is complete only when each requested case-derived
        # domain has an attested run manifest. Independent domains remain live.
        if alert_type in (None, "anomaly"):
            analytics_policy.latest_complete_generation(
                conn, model_names=["drishti-emerging-trend"], ref_table="AlertHistory",
                artifact="case-derived anomaly alerts", current=current)
        prediction_scopes: set[Optional[int]] = set()
        if alert_type in (None, "prediction"):
            # Even a zero-row shared feed needs an authoritative all-head run.
            prediction_scopes.add(None)
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        for row in rows:
            payload = row[11] if isinstance(row[11], dict) else {}
            model_name = row[14]
            is_case_analytics = (
                model_name in case_models or payload.get("artifact_domain") == "case_analytics"
            )
            if is_case_analytics:
                if payload.get("artifact_domain") != "case_analytics":
                    raise analytics_policy.ArtifactPolicyMismatch(
                        f"AlertHistory {row[0]} is a legacy case-derived alert without a trusted "
                        "artifact-domain marker.")
                analytics_policy.require_current(
                    conn, payload, f"AlertHistory {row[0]}", current=current)
                analytics_policy.require_current(
                    conn, row[15], f"AlertHistory {row[0]} model", current=current)
                if row[1] == "prediction":
                    scope_head = payload.get("crime_head_id")
                    if (scope_head is not None
                            and (not isinstance(scope_head, int) or isinstance(scope_head, bool))):
                        raise analytics_policy.ArtifactPolicyMismatch(
                            f"AlertHistory {row[0]} has an invalid prediction-alert head scope.")
                    prediction_scopes.add(scope_head)
            elif row[16] is not None or model_name in independent_models:
                continue
            elif row[13] is None and payload.get("kind") == "board_hypothesis_promotion":
                continue
            else:
                raise analytics_policy.DerivedArtifactUnavailable(
                    f"AlertHistory {row[0]} has no trusted independent domain or current "
                    "case-analytics attestation; classify or regenerate it before serving.")
        for scope_head in sorted(
                prediction_scopes, key=lambda value: (-1 if value is None else value)):
            analytics_policy.latest_complete_generation(
                conn, model_names=["drishti-early-warning"], ref_table="AlertHistory",
                artifact="case-derived prediction alerts", scope={"head_id": scope_head},
                current=current)
    feats = [AlertFeature(
        alert_id=int(r[0]), alert_type=r[1], severity=r[2], title=r[3], message=r[4],
        district_id=r[5], district_name=r[6], crime_head_id=r[7], lon=r[8], lat=r[9],
        status=r[10], payload=r[11], created_at=str(r[12]) if r[12] else None)
        for r in rows]
    result = AiResult(
        answer=f"{len(feats)} active alert(s)" + (f" at severity {severity}" if severity else "") + ".",
        confidence=1.0,
        source_record_ids=[f"AlertHistory:{f.alert_id}" for f in feats[:50]],
        reasoning_summary="Open/acknowledged AlertHistory rows, severity-ranked; "
                          "emerging-trend alerts fire when a cell exceeds its rolling baseline.",
        model_version=GEO_ALERT_MODEL)
    return AlertResponse(result=result, count=len(feats), alerts=feats)


def points(bbox: Optional[tuple] = None, start: Optional[dt.date] = None,
           end: Optional[dt.date] = None, crime_head_id: Optional[int] = None,
           limit: int = 5000, district_ids: Optional[list] = None,
           unit_id: Optional[int] = None):
    """Raw incident coordinates for the Live Map.

    Point-level and therefore the most sensitive read here: each row is one
    reported crime at one place on one date. The router refuses aggregate-only and
    unposted seats; ``district_ids`` / ``unit_id`` confine what is left to the
    seat's jurisdiction, so a bbox cannot be used to pan across the state.
    """
    from .schemas import PointFeature, PointsResponse
    limit = max(1, min(int(limit), 20000))
    where = ['cm."geom" IS NOT NULL']
    params: list = []
    join_unit = district_ids is not None or unit_id is not None
    if bbox:
        where.append('ST_Intersects(cm."geom", ST_MakeEnvelope(%s,%s,%s,%s,4326))')
        params.extend(bbox)
    if unit_id is not None:
        where.append('cm."PoliceStationID" = %s')
        params.append(int(unit_id))
    if district_ids is not None:
        if not district_ids:
            where.append("FALSE")
        else:
            where.append('pu."DistrictID" = ANY(%s)')
            params.append([int(d) for d in district_ids])
    if crime_head_id is not None:
        where.append('cm."CrimeMajorHeadID" = %s')
        params.append(crime_head_id)
    if start is not None:
        where.append('cm."CrimeRegisteredDate" >= %s')
        params.append(start)
    if end is not None:
        where.append('cm."CrimeRegisteredDate" <= %s')
        params.append(end)
    sql = (
        'SELECT cm."CaseMasterID", ST_X(cm."geom"), ST_Y(cm."geom"), '
        'cm."CrimeMajorHeadID", ch."CrimeGroupName", cm."CrimeRegisteredDate", '
        'EXTRACT(HOUR FROM cm."IncidentFromDate")::int, '
        'COALESCE(NULLIF(cv.attrs #>> \'{official_references,police_crime_no}\', \'\'), '
        'cm."CrimeNo"), cv.attrs #>> \'{location,label}\', '
        'cv.attrs #>> \'{location,precision}\', '
        'COALESCE((cv.attrs #>> \'{location,not_exact_incident_scene}\')::boolean,FALSE), '
        'NULLIF(cv.attrs #>> \'{location,uncertainty_radius_m}\', \'\')::int, '
        'cv.attrs #>> \'{location,attribution}\', '
        'COALESCE((cv.attrs->>\'excluded_from_derived_analytics\')::boolean,FALSE) '
        'FROM "CaseMaster" cm '
        'LEFT JOIN "CrimeHead" ch ON ch."CrimeHeadID" = cm."CrimeMajorHeadID" '
        + ('JOIN "Unit" pu ON pu."UnitID" = cm."PoliceStationID" ' if join_unit else '') +
        'LEFT JOIN LATERAL (SELECT cv0."SnapshotAttributes" AS attrs '
        '  FROM "CaseVersion" cv0 WHERE cv0."CaseMasterID"=cm."CaseMasterID" '
        '  AND cv0."IsCurrent"=TRUE ORDER BY cv0."VersionNo" DESC LIMIT 1) cv ON TRUE '
        'WHERE ' + ' AND '.join(where) +
        ' ORDER BY cm."CrimeRegisteredDate" DESC NULLS LAST LIMIT %s'
    )
    params.append(limit + 1)  # fetch one extra to detect capping
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
    capped = len(rows) > limit
    rows = rows[:limit]
    feats = [PointFeature(
        case_id=int(r[0]), lon=float(r[1]), lat=float(r[2]),
        crime_head_id=r[3], crime_group=r[4],
        date=str(r[5]) if r[5] else None,
        hour=r[6] if r[6] is not None else None,
        crime_no=r[7], location_label=r[8], location_precision=r[9],
        not_exact_incident_scene=bool(r[10]),
        uncertainty_radius_m=r[11], location_attribution=r[12],
        excluded_from_derived_analytics=bool(r[13])) for r in rows]
    return PointsResponse(count=len(feats), capped=capped, points=feats)


def stations(bbox: Optional[tuple] = None, limit: int = 1500):
    """Police stations plotted at the centroid of the incidents they handle
    (Unit has no geometry of its own). Point-level -> router applies the cap."""
    from .schemas import StationFeature, StationsResponse
    limit = max(1, min(int(limit), 2000))
    where = [
        'cm."geom" IS NOT NULL',
        'cm."PoliceStationID" IS NOT NULL',
        casedata.analytics_eligible_sql("cm"),
    ]
    params: list = []
    if bbox:
        where.append('ST_Intersects(cm."geom", ST_MakeEnvelope(%s,%s,%s,%s,4326))')
        params.extend(bbox)
    sql = (
        'SELECT cm."PoliceStationID", u."UnitName", d."DistrictName", '
        'AVG(ST_X(cm."geom"))::float, AVG(ST_Y(cm."geom"))::float, COUNT(*)::int, '
        'MODE() WITHIN GROUP (ORDER BY ch."CrimeGroupName") '
        'FROM "CaseMaster" cm '
        'JOIN "Unit" u ON u."UnitID" = cm."PoliceStationID" '
        'LEFT JOIN "District" d ON d."DistrictID" = u."DistrictID" '
        'LEFT JOIN "CrimeHead" ch ON ch."CrimeHeadID" = cm."CrimeMajorHeadID" '
        'WHERE ' + ' AND '.join(where) +
        ' GROUP BY cm."PoliceStationID", u."UnitName", d."DistrictName" '
        'ORDER BY COUNT(*) DESC LIMIT %s'
    )
    params.append(limit)
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
    feats = [StationFeature(
        station_id=int(r[0]), name=r[1], district=r[2],
        lon=float(r[3]), lat=float(r[4]), case_count=int(r[5]), top_crime=r[6])
        for r in rows]
    return StationsResponse(count=len(feats), stations=feats)


def case_links(case_id: int, limit: int = 60):
    """Geo-located cases linked to a source case by a shared CANONICAL accused
    person (co-offending footprint, Phase 4 — never a name match). Powers the Live
    Map arc view. Point-level -> router applies the point-level cap."""
    from .schemas import CaseLinkNode, CaseLinksResponse
    limit = max(1, min(int(limit), 200))
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT ST_X(cm."geom"), ST_Y(cm."geom"), '
                'COALESCE(NULLIF(cv.attrs #>> \'{official_references,police_crime_no}\', \'\'), '
                'cm."CrimeNo"), '
                'COALESCE(NULLIF(cv.attrs->>\'record_origin\', \'\'), \'synthetic_fixture\'), '
                'COALESCE((cv.attrs->>\'is_synthetic\')::boolean, TRUE), '
                'cv.attrs #>> \'{reference_mapping,kind}\', '
                'cv.attrs #>> \'{location,label}\', cv.attrs #>> \'{location,precision}\', '
                'COALESCE((cv.attrs #>> \'{location,not_exact_incident_scene}\')::boolean, FALSE), '
                'NULLIF(cv.attrs #>> \'{location,uncertainty_radius_m}\', \'\')::int, '
                'cv.attrs #>> \'{location,attribution}\' '
                'FROM "CaseMaster" cm '
                'LEFT JOIN LATERAL (SELECT cv0."SnapshotAttributes" AS attrs '
                'FROM "CaseVersion" cv0 '
                'WHERE cv0."CaseMasterID"=cm."CaseMasterID" AND cv0."IsCurrent"=TRUE '
                'ORDER BY cv0."VersionNo" DESC LIMIT 1) cv ON TRUE '
                'WHERE cm."CaseMasterID" = %s', (case_id,))
            src = cur.fetchone()
            if src is None:
                return None
            cur.execute(
                'SELECT DISTINCT r2."CaseMasterID", ST_X(cm2."geom"), ST_Y(cm2."geom"), '
                'COALESCE(NULLIF(cv2.attrs #>> \'{official_references,police_crime_no}\', \'\'), '
                'cm2."CrimeNo"), ch."CrimeGroupName", '
                'COALESCE(p."DisplayLabel", p."PublicRef"), '
                'COALESCE(NULLIF(cv2.attrs->>\'record_origin\', \'\'), \'synthetic_fixture\'), '
                'COALESCE((cv2.attrs->>\'is_synthetic\')::boolean, TRUE), '
                'cv2.attrs #>> \'{reference_mapping,kind}\', '
                'cv2.attrs #>> \'{location,label}\', cv2.attrs #>> \'{location,precision}\', '
                'COALESCE((cv2.attrs #>> \'{location,not_exact_incident_scene}\')::boolean, FALSE), '
                'NULLIF(cv2.attrs #>> \'{location,uncertainty_radius_m}\', \'\')::int, '
                'cv2.attrs #>> \'{location,attribution}\' '
                'FROM "CasePartyRole" r1 '
                'JOIN "CasePartyRole" r2 ON r2."CanonicalPersonID" = r1."CanonicalPersonID" '
                '                        AND r2."CaseMasterID" <> r1."CaseMasterID" '
                '                        AND r2."RoleType" = \'accused\' '
                'JOIN "CanonicalPerson" p ON p."CanonicalPersonID" = r1."CanonicalPersonID" '
                'JOIN "CaseMaster" cm2 ON cm2."CaseMasterID" = r2."CaseMasterID" '
                'LEFT JOIN "CrimeHead" ch ON ch."CrimeHeadID" = cm2."CrimeMajorHeadID" '
                'LEFT JOIN LATERAL (SELECT cv0."SnapshotAttributes" AS attrs '
                'FROM "CaseVersion" cv0 '
                'WHERE cv0."CaseMasterID"=cm2."CaseMasterID" AND cv0."IsCurrent"=TRUE '
                'ORDER BY cv0."VersionNo" DESC LIMIT 1) cv2 ON TRUE '
                'WHERE r1."CaseMasterID" = %s AND r1."RoleType"=\'accused\' '
                '  AND r1."CanonicalPersonID" IS NOT NULL AND p."IsUnknown"=FALSE '
                '  AND cm2."geom" IS NOT NULL '
                'ORDER BY r2."CaseMasterID" LIMIT %s', (case_id, limit))
            links = [CaseLinkNode(
                case_id=int(r[0]), lon=float(r[1]), lat=float(r[2]),
                crime_no=r[3], crime_group=r[4], via=r[5],
                record_origin=r[6], is_synthetic=bool(r[7]),
                reference_mapping_kind=r[8], location_label=r[9],
                location_precision=r[10], not_exact_incident_scene=bool(r[11]),
                uncertainty_radius_m=r[12], location_attribution=r[13])
                for r in cur.fetchall()]
    return CaseLinksResponse(
        source_case_id=case_id,
        source_lon=float(src[0]) if src[0] is not None else None,
        source_lat=float(src[1]) if src[1] is not None else None,
        source_crime_no=src[2], source_record_origin=src[3],
        source_is_synthetic=bool(src[4]), source_reference_mapping_kind=src[5],
        source_location_label=src[6], source_location_precision=src[7],
        source_not_exact_incident_scene=bool(src[8]),
        source_uncertainty_radius_m=src[9], source_location_attribution=src[10],
        count=len(links), links=links)
