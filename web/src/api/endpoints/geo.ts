import { apiClient } from "@/api/client";
import type { AlertResponse, HotspotResponse, TrendResponse } from "@/api/types";

export type HotspotParams = {
  /** "minLon,minLat,maxLon,maxLat" */
  bbox?: string;
  start?: string;
  end?: string;
  crime_head_id?: number;
  limit?: number;
};
export type TrendParams = {
  district_id?: number;
  crime_head_id?: number;
  sub_head_id?: number;
  start?: string;
  end?: string;
  window?: number;
  k?: number;
  decompose?: boolean;
};
export type AlertParams = {
  severity?: "info" | "low" | "medium" | "high" | "critical";
  alert_type?: string;
  bbox?: string;
  limit?: number;
};

/** Phase-7 geospatial analytics (services/ml/app/geo). */
export type PointsParams = {
  bbox?: string;
  start?: string;
  end?: string;
  crime_head_id?: number;
  limit?: number;
};

/** Administrative boundary overlay levels (real KGIS polygons, bundled). */
export type BoundaryLevel = "state" | "districts" | "taluks";
/** Persisted/versioned DB boundary levels (JurisdictionBoundary table). */
export type DbBoundaryLevel = "state" | "district" | "taluk" | "unit" | "sho";

export const geoApi = {
  hotspots: (params: HotspotParams = {}, signal?: AbortSignal) =>
    apiClient.get<HotspotResponse>("/geo/hotspots", params, signal),
  trends: (params: TrendParams = {}, signal?: AbortSignal) =>
    apiClient.get<TrendResponse>("/geo/trends", params, signal),
  alerts: (params: AlertParams = {}, signal?: AbortSignal) =>
    apiClient.get<AlertResponse>("/geo/alerts", params, signal),
  /** GET /geo/points — raw incident coordinates for the Live Map (blocked for policymaker). */
  points: (params: PointsParams = {}, signal?: AbortSignal) =>
    apiClient.get<import("@/api/types").PointsResponse>("/geo/points", params, signal),
  /** GET /geo/stations — police stations at their case-centroid (blocked for policymaker). */
  stations: (params: { bbox?: string; limit?: number } = {}, signal?: AbortSignal) =>
    apiClient.get<import("@/api/types").StationsResponse>("/geo/stations", params, signal),
  /** GET /geo/case-links — geo-located cases linked to a case by shared accused. */
  caseLinks: (caseId: number, limit = 60, signal?: AbortSignal) =>
    apiClient.get<import("@/api/types").CaseLinksResponse>("/geo/case-links", { case_id: caseId, limit }, signal),
  /** GET /geo/boundaries/{level} — admin boundary overlay (state | districts | taluks) as GeoJSON. */
  boundaries: (level: BoundaryLevel, signal?: AbortSignal) =>
    apiClient.get<GeoJSON.FeatureCollection>(`/geo/boundaries/${level}`, undefined, signal),
  /** GET /geo/sho-regions — police-station jurisdiction polygons (Voronoi ∩ district). */
  shoRegions: (limit = 1500, signal?: AbortSignal) =>
    apiClient.get<GeoJSON.FeatureCollection>("/geo/sho-regions", { limit }, signal),

  /* ---- Phase 9: persisted/versioned boundaries + containment workflow. The
     map and the database share ONE source of truth via these endpoints. ---- */
  /** GET /geo/db-boundaries/{level} — persisted, versioned boundary (the same
   *  geometry the DB enforces containment against) as GeoJSON. */
  dbBoundaries: (level: DbBoundaryLevel, signal?: AbortSignal) =>
    apiClient.get<GeoJSON.FeatureCollection>(`/geo/db-boundaries/${level}`, undefined, signal),
  /** GET /geo/jurisdiction/freshness — boundary versions/counts/as-of + last scan. */
  jurisdictionFreshness: (signal?: AbortSignal) =>
    apiClient.get<import("@/api/types").JurisdictionFreshness>("/geo/jurisdiction/freshness", undefined, signal),
  /** GET /geo/jurisdiction/issues — reviewed-reassignment queue (mismatch flags). */
  jurisdictionIssues: (
    params: { status?: "open" | "resolved" | "quarantined" | "accepted"; page?: number; page_size?: number } = {},
    signal?: AbortSignal,
  ) => apiClient.get<import("@/api/types").ContainmentIssuesResponse>("/geo/jurisdiction/issues", params, signal),
  /** POST /geo/jurisdiction/scan — stage containment failures as DataQualityIssues (no silent move). */
  jurisdictionScan: (scope: "caseversion" | "location_observation" | "all" = "all", signal?: AbortSignal) =>
    apiClient.post<import("@/api/types").ContainmentScanResult>("/geo/jurisdiction/scan", undefined, { scope }, signal),
  /** POST /geo/jurisdiction/reassign — reviewed reassignment/override/quarantine. */
  jurisdictionReassign: (body: import("@/api/types").JurisdictionReassignRequest, signal?: AbortSignal) =>
    apiClient.post<import("@/api/types").JurisdictionReassignResult>("/geo/jurisdiction/reassign", body, undefined, signal),
};
