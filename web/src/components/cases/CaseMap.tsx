import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ScatterplotLayer } from "@deck.gl/layers";
import type { Layer, PickingInfo } from "@deck.gl/core";
import { api } from "@/api";
import type { CaseListItem } from "@/api/types";
import { categoryColor } from "@/lib/palette";
import { MapCanvas, type MapViewState } from "@/components/map/MapCanvas";
import { hexToRgb, KARNATAKA_VIEW } from "@/components/map/mapConfig";
import { districtBoundaries, stateBoundary } from "@/components/map/layers";

/* ============================================================================
   Case Explorer spatial preview: the current page of results on the REAL
   Karnataka basemap (MapLibre + deck.gl), points coloured by crime type, with
   district/state outlines for context. The full toolset lives in Map & Hotspots.
   ========================================================================== */

const FALLBACK_UNCERTAINTY_RADIUS_M = 1000;

interface CasePoint {
  case_id: number;
  lon: number;
  lat: number;
  crime_group?: string | null;
  crime_no?: string | null;
  district?: string | null;
  status?: string | null;
  record_origin: string;
  is_synthetic: boolean;
  reference_mapping_kind?: string | null;
  location_label?: string | null;
  location_precision?: string | null;
  not_exact_incident_scene: boolean;
  location_uncertainty_radius_m?: number | null;
  location_attribution?: string | null;
}

function caseReferenceLabel(caseId: number, crimeNo?: string | null): string {
  const presentationNumber = crimeNo?.trim();
  return presentationNumber ? `Case ${presentationNumber}` : `Internal case ID #${caseId}`;
}

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[character] ?? character);
}

function formatRadius(radiusM: number): string {
  if (radiusM >= 1000) return `${Number((radiusM / 1000).toFixed(1))} km`;
  return `${Math.round(radiusM)} m`;
}

/** Frame the map to the points on screen (falls back to all-of-Karnataka). */
function fitView(pts: CasePoint[]): MapViewState {
  if (pts.length === 0) return { ...KARNATAKA_VIEW };
  const lons = pts.map((p) => p.lon);
  const lats = pts.map((p) => p.lat);
  const minLon = Math.min(...lons);
  const maxLon = Math.max(...lons);
  const minLat = Math.min(...lats);
  const maxLat = Math.max(...lats);
  const span = Math.max(maxLon - minLon, maxLat - minLat, 0.08);
  // world spans ~360° at zoom 0 and halves each level; pad a little.
  const zoom = Math.min(11, Math.max(5.2, Math.log2(360 / span) - 1.6));
  return {
    longitude: (minLon + maxLon) / 2,
    latitude: (minLat + maxLat) / 2,
    zoom,
    pitch: 0,
    bearing: 0,
  };
}

export function CaseMap({
  items,
  onSelect,
}: {
  items: CaseListItem[];
  onSelect?: (caseId: number) => void;
}) {
  const points = useMemo<CasePoint[]>(
    () =>
      items
        .filter((c) => c.latitude != null && c.longitude != null)
        .map((c) => ({
          case_id: c.case_id,
          lon: c.longitude as number,
          lat: c.latitude as number,
          crime_group: c.crime_group,
          crime_no: c.crime_no,
          district: c.district,
          status: c.status,
          record_origin: c.record_origin,
          is_synthetic: c.is_synthetic,
          reference_mapping_kind: c.reference_mapping_kind,
          location_label: c.location_label,
          location_precision: c.location_precision,
          not_exact_incident_scene:
            c.not_exact_incident_scene || c.location_precision === "approximate_locality_reference",
          location_uncertainty_radius_m: c.location_uncertainty_radius_m,
          location_attribution: c.location_attribution,
        })),
    [items],
  );
  const exactPoints = useMemo(() => points.filter((point) => !point.not_exact_incident_scene), [points]);
  const approximatePoints = useMemo(() => points.filter((point) => point.not_exact_incident_scene), [points]);

  // Re-frame the map whenever the result set (this page) changes.
  const sig = useMemo(() => points.map((p) => `${p.case_id}:${p.lon},${p.lat}`).join("|"), [points]);
  const [viewState, setViewState] = useState<MapViewState>(() => fitView(points));
  useEffect(() => {
    setViewState(fitView(points));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sig]);

  // Reference geography for context (fetched once, cached forever).
  const stateBndQ = useQuery({
    queryKey: ["geo", "boundary", "state"],
    queryFn: ({ signal }) => api.geo.boundaries("state", signal),
    staleTime: Infinity,
    retry: false,
  });
  const distBndQ = useQuery({
    queryKey: ["geo", "boundary", "districts"],
    queryFn: ({ signal }) => api.geo.boundaries("districts", signal),
    staleTime: Infinity,
    retry: false,
  });

  const layers = useMemo<Layer[]>(() => {
    const mapLayers: Layer[] = [];
    if (distBndQ.data) mapLayers.push(districtBoundaries(distBndQ.data));
    if (stateBndQ.data) mapLayers.push(stateBoundary(stateBndQ.data));

    if (approximatePoints.length > 0) {
      mapLayers.push(
        new ScatterplotLayer<CasePoint>({
          id: "case-approximate-rings",
          data: approximatePoints,
          getPosition: (point) => [point.lon, point.lat],
          getFillColor: (point) =>
            [...hexToRgb(categoryColor(point.crime_group ?? "other")), 45] as [number, number, number, number],
          getLineColor: (point) =>
            [...hexToRgb(categoryColor(point.crime_group ?? "other")), 225] as [number, number, number, number],
          getRadius: (point) => point.location_uncertainty_radius_m ?? FALLBACK_UNCERTAINTY_RADIUS_M,
          radiusUnits: "meters",
          radiusMinPixels: 6,
          radiusMaxPixels: 36,
          stroked: true,
          filled: true,
          lineWidthUnits: "pixels",
          getLineWidth: 1.5,
          autoHighlight: true,
          highlightColor: [255, 255, 255, 90],
          pickable: true,
          onClick: onSelect
            ? (info) => info.object && onSelect((info.object as CasePoint).case_id)
            : undefined,
        }),
      );
    }

    if (exactPoints.length > 0) {
      mapLayers.push(
        new ScatterplotLayer<CasePoint>({
          id: "case-exact-points",
          data: exactPoints,
          getPosition: (point) => [point.lon, point.lat],
          getFillColor: (point) =>
            [...hexToRgb(categoryColor(point.crime_group ?? "other")), 235] as [number, number, number, number],
          getLineColor: [255, 255, 255, 230],
          stroked: true,
          filled: true,
          lineWidthUnits: "pixels",
          getLineWidth: 1.2,
          getRadius: 7,
          radiusUnits: "pixels",
          radiusMinPixels: 5,
          radiusMaxPixels: 10,
          pickable: true,
          onClick: onSelect
            ? (info) => info.object && onSelect((info.object as CasePoint).case_id)
            : undefined,
        }),
      );
    }
    return mapLayers;
  }, [approximatePoints, exactPoints, distBndQ.data, stateBndQ.data, onSelect]);

  const getTooltip = (info: PickingInfo): { html: string; style: Record<string, string> } | null => {
    if (info.layer?.id !== "case-exact-points" && info.layer?.id !== "case-approximate-rings") return null;
    const point = info.object as CasePoint | undefined;
    if (!point) return null;

    const radiusM = point.location_uncertainty_radius_m ?? FALLBACK_UNCERTAINTY_RADIUS_M;
    const details: Array<string | null | undefined> = [
      caseReferenceLabel(point.case_id, point.crime_no),
      point.crime_group,
      point.district,
      point.status,
      point.not_exact_incident_scene ? "Approximate locality reference — not an exact incident scene" : null,
      point.location_label ? `Locality: ${point.location_label}` : null,
      point.location_precision ? `Precision: ${point.location_precision}` : null,
      point.not_exact_incident_scene
        ? `Uncertainty radius: ${formatRadius(radiusM)}${point.location_uncertainty_radius_m == null ? " fallback" : ""}`
        : null,
      point.location_attribution ? `Location source: ${point.location_attribution}` : null,
    ];
    return {
      html: escapeHtml(details.filter((detail): detail is string => Boolean(detail)).join(" · ")),
      style: {
        background: "#1d2740",
        color: "#e8ecf6",
        fontSize: "12px",
        padding: "4px 8px",
        borderRadius: "8px",
        border: "1px solid #28324d",
      },
    };
  };

  if (points.length === 0) {
    return (
      <div className="flex h-[440px] items-center justify-center rounded-control border border-hairline bg-surface-2/40 px-4 text-center text-13 text-content-dim">
        No mapped incidents on this page. Cases without coordinates can&apos;t be plotted — adjust filters
        or open the full map in Map &amp; Hotspots.
      </div>
    );
  }

  return (
    <div className="relative h-[440px] overflow-hidden rounded-control border border-hairline">
      <MapCanvas viewState={viewState} onViewStateChange={setViewState} layers={layers} getTooltip={getTooltip} />
      {approximatePoints.length > 0 && (
        <div className="pointer-events-none absolute right-2 top-2 z-10 flex max-w-80 items-start gap-2 rounded-control border border-hairline bg-surface/95 px-2.5 py-2 text-11 leading-relaxed text-content-dim shadow-sm backdrop-blur">
          <span className="mt-0.5 size-3 shrink-0 rounded-full border-2 border-primary bg-primary/10" />
          <span>
            Outlined locality rings are approximate references, not exact incident scenes. Ring size shows uncertainty; 1 km is used only when no radius is supplied.
          </span>
        </div>
      )}
      <div className="pointer-events-none absolute bottom-2 left-2 z-10 rounded-control border border-hairline bg-surface/90 px-2 py-1 text-11 text-content-dim backdrop-blur">
        {points.length} of this page&apos;s cases mapped · click a marker or ring to open
      </div>
    </div>
  );
}
