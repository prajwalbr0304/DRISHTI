import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ScatterplotLayer } from "@deck.gl/layers";
import type { Layer, PickingInfo } from "@deck.gl/core";
import { api } from "@/api";
import type { HotspotFeature } from "@/api/types";
import { formatNumber } from "@/lib/utils";
import { MapCanvas, type MapViewState } from "@/components/map/MapCanvas";
import { KARNATAKA_VIEW } from "@/components/map/mapConfig";
import { districtBoundaries, stateBoundary } from "@/components/map/layers";

/* ============================================================================
   Command Center "My jurisdiction" map: REAL hotspot centroids on the Karnataka
   basemap (MapLibre + deck.gl), with district/state outlines for context. Dot
   radius + opacity encode intensity — the same encoding as the old mini scatter,
   now anchored to real geography. The full toolset lives in Map & Hotspots.
   ========================================================================== */

interface HotPoint {
  id: number;
  lon: number;
  lat: number;
  intensity: number; // 0..1
  case_count: number;
  name?: string | null;
  district?: string | null;
}

/** Frame the map to the hotspots (falls back to all-of-Karnataka). */
function fitView(pts: HotPoint[]): MapViewState {
  if (pts.length === 0) return { ...KARNATAKA_VIEW };
  const lons = pts.map((p) => p.lon);
  const lats = pts.map((p) => p.lat);
  const minLon = Math.min(...lons);
  const maxLon = Math.max(...lons);
  const minLat = Math.min(...lats);
  const maxLat = Math.max(...lats);
  const span = Math.max(maxLon - minLon, maxLat - minLat, 0.08);
  const zoom = Math.min(11, Math.max(5.2, Math.log2(360 / span) - 1.6));
  return {
    longitude: (minLon + maxLon) / 2,
    latitude: (minLat + maxLat) / 2,
    zoom,
    pitch: 0,
    bearing: 0,
  };
}

const BLUE: [number, number, number] = [59, 130, 246];

export function JurisdictionMap({ hotspots }: { hotspots: HotspotFeature[] }) {
  const points = useMemo<HotPoint[]>(
    () =>
      hotspots
        .filter((h) => h.centroid_lon != null && h.centroid_lat != null)
        .map((h) => ({
          id: h.hotspot_id,
          lon: h.centroid_lon as number,
          lat: h.centroid_lat as number,
          intensity: Math.max(0, Math.min(1, h.intensity ?? 0.5)),
          case_count: h.case_count ?? 0,
          name: h.name,
          district: h.district_name,
        })),
    [hotspots],
  );

  // Re-frame whenever the hotspot set changes (window / scope change).
  const sig = useMemo(() => points.map((p) => `${p.id}:${p.lon},${p.lat}`).join("|"), [points]);
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
      new ScatterplotLayer<HotPoint>({
        id: "jurisdiction-hotspots",
        data: points,
        getPosition: (d) => [d.lon, d.lat],
        // radius + opacity encode intensity (same read as the old mini scatter).
        getRadius: (d) => 5 + d.intensity * 13,
        radiusUnits: "pixels",
        radiusMinPixels: 5,
        radiusMaxPixels: 22,
        getFillColor: (d) =>
          [BLUE[0], BLUE[1], BLUE[2], Math.round(90 + d.intensity * 150)] as [number, number, number, number],
        getLineColor: [255, 255, 255, 210],
        stroked: true,
        filled: true,
        lineWidthUnits: "pixels",
        getLineWidth: 1,
        pickable: true,
      }),
    );
    return L;
  }, [points, distBndQ.data, stateBndQ.data]);

  const getTooltip = (info: PickingInfo): { html: string; style: Record<string, string> } | null => {
    const o = info.object as HotPoint | undefined;
    if (!o) return null;
    const html = [
      o.name || o.district || "Hotspot",
      o.district && o.name ? o.district : null,
      `${formatNumber(o.case_count)} cases`,
      `intensity ${(o.intensity * 100).toFixed(0)}%`,
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

  return (
    <div className="relative h-full min-h-[280px] w-full">
      <MapCanvas viewState={viewState} onViewStateChange={setViewState} layers={layers} getTooltip={getTooltip} />
      <div className="pointer-events-none absolute bottom-2 left-2 z-10 rounded-control border border-hairline bg-surface/90 px-2 py-1 text-11 text-content-dim backdrop-blur">
        {points.length} hotspots · dot size &amp; opacity = intensity
      </div>
    </div>
  );
}
