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
};
