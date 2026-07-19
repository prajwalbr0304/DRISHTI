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

interface CasePoint {
  case_id: number;
  lon: number;
  lat: number;
  crime_group?: string | null;
  crime_no?: string | null;
  district?: string | null;
  status?: string | null;
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
        })),
    [items],
  );

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
    const L: Layer[] = [];
    if (distBndQ.data) L.push(districtBoundaries(distBndQ.data));
    if (stateBndQ.data) L.push(stateBoundary(stateBndQ.data));
    L.push(
      new ScatterplotLayer<CasePoint>({
        id: "case-points",
        data: points,
        getPosition: (d) => [d.lon, d.lat],
        getFillColor: (d) =>
          [...hexToRgb(categoryColor(d.crime_group ?? "other")), 235] as [number, number, number, number],
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
        onClick: onSelect ? (info) => info.object && onSelect((info.object as CasePoint).case_id) : undefined,
      }),
    );
    return L;
  }, [points, distBndQ.data, stateBndQ.data, onSelect]);

  const getTooltip = (info: PickingInfo): { html: string; style: Record<string, string> } | null => {
    const o = info.object as CasePoint | undefined;
    if (!o) return null;
    const html = [
      o.crime_no ? `Case ${o.crime_no}` : `Case ${o.case_id}`,
      o.crime_group,
      o.district,
      o.status,
    ]
      .filter(Boolean)
      .join(" · ");
    return {
      html,
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
        No mapped incidents on this page. Cases without coordinates can't be plotted — adjust filters
        or open the full map in Map &amp; Hotspots.
      </div>
    );
  }

  return (
    <div className="relative h-[440px] overflow-hidden rounded-control border border-hairline">
      <MapCanvas viewState={viewState} onViewStateChange={setViewState} layers={layers} getTooltip={getTooltip} />
      <div className="pointer-events-none absolute bottom-2 left-2 z-10 rounded-control border border-hairline bg-surface/90 px-2 py-1 text-11 text-content-dim backdrop-blur">
        {points.length} of this page&apos;s cases mapped · click a point to open
      </div>
    </div>
  );
}
