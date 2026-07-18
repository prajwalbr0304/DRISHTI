import { ArcLayer, ScatterplotLayer, GeoJsonLayer } from "@deck.gl/layers";
import { HeatmapLayer, HexagonLayer } from "@deck.gl/aggregation-layers";
import type { Layer } from "@deck.gl/core";
import type {
  AlertFeature,
  CaseLinkNode,
  HotspotFeature,
  MapCell,
  PointFeature,
  StationFeature,
} from "@/api/types";
import { categoryColor, SEVERITY } from "@/lib/palette";
import { hexToRgb, rampRgb, type RGB } from "@/components/map/mapConfig";

/* ============================================================================
   deck.gl layer builders (doc 03 §3 / doc 05 §5). Encoding stays on-contract:
   12-hue category palette for crime type, sequential heat ramp for density /
   forecast, severity hues for alerts, confidence -> opacity (uncertainty shown).
   ========================================================================== */

const SEV_RGB: Record<string, RGB> = {
  critical: hexToRgb(SEVERITY.critical),
  high: hexToRgb(SEVERITY.high),
  medium: hexToRgb(SEVERITY.medium),
  low: hexToRgb(SEVERITY.low),
  info: [148, 163, 184],
};

/* --- Live Map: individual incident points, coloured by crime type --------- */
export function pointsScatter(points: PointFeature[], onClick?: (p: PointFeature) => void): Layer {
  return new ScatterplotLayer<PointFeature>({
    id: "incident-points",
    data: points,
    getPosition: (d) => [d.lon, d.lat],
    getFillColor: (d) => [...hexToRgb(categoryColor(d.crime_group ?? "other")), 200] as [number, number, number, number],
    getRadius: 40,
    radiusUnits: "meters",
    radiusMinPixels: 2.5,
    radiusMaxPixels: 7,
    stroked: false,
    pickable: true,
    onClick: onClick ? (info) => info.object && onClick(info.object as PointFeature) : undefined,
  });
}

/* --- Live Map: police stations (distinct white-with-ring markers) --------- */
export function stationMarkers(stations: StationFeature[], onClick?: (s: StationFeature) => void): Layer {
  return new ScatterplotLayer<StationFeature>({
    id: "police-stations",
    data: stations,
    getPosition: (d) => [d.lon, d.lat],
    getFillColor: [232, 236, 246, 235],
    getLineColor: [59, 130, 246, 255],
    stroked: true,
    filled: true,
    lineWidthUnits: "pixels",
    getLineWidth: 1.5,
    getRadius: 6,
    radiusUnits: "pixels",
    radiusMinPixels: 4,
    radiusMaxPixels: 8,
    pickable: true,
    onClick: onClick ? (info) => info.object && onClick(info.object as StationFeature) : undefined,
  });
}

/* --- Live Map (zoomed out): aggregated bins so it never becomes noise -----
   Same skew fix as hexBins3D: quantize over a clamped domain (pass hexColorDomain). */
export function pointsHex(points: PointFeature[], colorDomain?: [number, number]): Layer {
  return new HexagonLayer<PointFeature>({
    id: "incident-hex",
    data: points,
    getPosition: (d) => [d.lon, d.lat],
    radius: 1500,
    coverage: 0.9,
    elevationScale: 0,
    extruded: false,
    opacity: 0.6,
    colorRange: HEX_COLOR_RANGE,
    colorScaleType: "quantize",
    colorDomain,
    pickable: true,
  });
}

/* --- Hotspots: extruded 3D hex-bins (deck.gl HexagonLayer, screenshot 1) ---
   Bright low→high heat ramp. The raw per-bin count distribution is extremely
   skewed (Bengaluru dwarfs everywhere else), which collapses BOTH linear
   (everything → darkest) and quantile (count=1 ties → only 2 colours) scales.
   Fix: `quantize` scaling over a colour domain clamped to the ~88th percentile
   (see hexColorDomain) so the common density range spans the whole ramp and the
   metro simply saturates at red. deck.gl only supports linear elevation, so
   height still tracks raw count — the extreme spike is real. */
const HEX_COLOR_RANGE: [number, number, number][] = [
  [12, 74, 110], // deep blue (low, still visible on dark/satellite)
  [14, 116, 144],
  [20, 184, 166], // teal
  [132, 204, 22], // lime
  [245, 158, 11], // amber
  [220, 38, 38], // red (high)
];

/**
 * A stable colour domain for hex bins. Grid-bins the points at roughly hex
 * scale and clamps the domain to the ~88th percentile of bin counts, so one
 * extreme metro can't collapse the ramp to a couple of colours.
 */
export function hexColorDomain(points: { lon: number; lat: number }[]): [number, number] {
  if (points.length < 2) return [1, 6];
  const grid = new Map<string, number>();
  for (const p of points) {
    const k = Math.round(p.lon / 0.012) + ":" + Math.round(p.lat / 0.012);
    grid.set(k, (grid.get(k) ?? 0) + 1);
  }
  const counts = [...grid.values()].sort((a, b) => a - b);
  const p88 = counts[Math.floor(counts.length * 0.88)] ?? counts[counts.length - 1] ?? 6;
  return [1, Math.min(60, Math.max(6, p88))];
}

export function hexBins3D(
  points: PointFeature[],
  extruded = true,
  colorDomain?: [number, number],
): Layer {
  return new HexagonLayer<PointFeature>({
    id: "hotspot-hex-3d",
    data: points,
    getPosition: (d) => [d.lon, d.lat],
    radius: 1100,
    coverage: 0.9,
    extruded,
    elevationScale: extruded ? 12 : 0,
    elevationRange: [0, 2600],
    colorRange: HEX_COLOR_RANGE,
    colorScaleType: "quantize", // linear buckets over a CLAMPED domain → full ramp is used
    colorDomain,
    opacity: 0.85,
    material: true,
    pickable: true,
  });
}

/* --- Live Map: 3D arcs from a case to its shared-accused links (screenshot 2) */
export function caseArcs(source: { lon: number; lat: number }, links: CaseLinkNode[]): Layer {
  return new ArcLayer<CaseLinkNode>({
    id: "case-arcs",
    data: links,
    getSourcePosition: () => [source.lon, source.lat],
    getTargetPosition: (d) => [d.lon, d.lat],
    getSourceColor: [59, 130, 246, 210],
    getTargetColor: [236, 72, 153, 220],
    getWidth: 1.8,
    getHeight: 0.5,
    greatCircle: false,
    pickable: true,
  });
}

export function linkTargets(links: CaseLinkNode[], onClick?: (l: CaseLinkNode) => void): Layer {
  return new ScatterplotLayer<CaseLinkNode>({
    id: "link-targets",
    data: links,
    getPosition: (d) => [d.lon, d.lat],
    getFillColor: [236, 72, 153, 235],
    getLineColor: [255, 255, 255, 220],
    stroked: true,
    lineWidthUnits: "pixels",
    getLineWidth: 1,
    getRadius: 6,
    radiusUnits: "pixels",
    radiusMinPixels: 4,
    radiusMaxPixels: 8,
    pickable: true,
    onClick: onClick ? (info) => info.object && onClick(info.object as CaseLinkNode) : undefined,
  });
}

export function linkSource(source: { lon: number; lat: number }): Layer {
  return new ScatterplotLayer({
    id: "link-source",
    data: [source],
    getPosition: (d: { lon: number; lat: number }) => [d.lon, d.lat],
    getFillColor: [59, 130, 246, 255],
    getLineColor: [255, 255, 255, 255],
    stroked: true,
    lineWidthUnits: "pixels",
    getLineWidth: 2,
    getRadius: 10,
    radiusUnits: "pixels",
    pickable: false,
  });
}

/* --- Hotspots: KDE-style density from incident points --------------------- */
export function densityHeatmap(points: PointFeature[]): Layer {
  return new HeatmapLayer<PointFeature>({
    id: "density-heatmap",
    data: points,
    getPosition: (d) => [d.lon, d.lat],
    getWeight: 1,
    radiusPixels: 42,
    intensity: 1,
    threshold: 0.04,
    colorRange: HEX_COLOR_RANGE,
  });
}

/* --- Hotspots: DBSCAN cluster outlines (real precomputed polygons) -------- */
export function hotspotOutlines(hotspots: HotspotFeature[]): Layer {
  const features = hotspots
    .filter((h) => h.geometry)
    .map((h) => ({ type: "Feature" as const, geometry: h.geometry as unknown as GeoJSON.Geometry, properties: { id: h.hotspot_id, intensity: h.intensity ?? 0 } }));
  return new GeoJsonLayer({
    id: "hotspot-outlines",
    data: { type: "FeatureCollection", features } as GeoJSON.FeatureCollection,
    stroked: true,
    filled: false,
    getLineColor: [245, 158, 11, 200],
    lineWidthUnits: "pixels",
    getLineWidth: 1.5,
    pickable: false,
  });
}

/* --- Optional admin boundary overlays (state / district / taluk / SHO) -----
   Reference geography, not data encoding: distinct hue + line weight per level
   (and a labelled toggle) so each reads clearly on dark, light and satellite
   basemaps. Drawn beneath the incident/forecast layers. ``data`` may be a
   GeoJSON FeatureCollection or a URL. */
type BoundaryData = GeoJSON.FeatureCollection | string;

export function stateBoundary(data: BoundaryData): Layer {
  return new GeoJsonLayer({
    id: "bnd-state",
    data,
    stroked: true,
    filled: false,
    getLineColor: [245, 158, 11, 235], // amber — high contrast on any basemap
    lineWidthUnits: "pixels",
    getLineWidth: 2.6,
    lineWidthMinPixels: 2,
    lineJointRounded: true,
    pickable: false,
  });
}

export function districtBoundaries(data: BoundaryData): Layer {
  return new GeoJsonLayer({
    id: "bnd-districts",
    data,
    stroked: true,
    filled: false,
    getLineColor: [56, 189, 248, 225], // sky
    lineWidthUnits: "pixels",
    getLineWidth: 1.5,
    lineWidthMinPixels: 1.2,
    lineJointRounded: true,
    pickable: true,
  });
}

export function talukBoundaries(data: BoundaryData): Layer {
  return new GeoJsonLayer({
    id: "bnd-taluks",
    data,
    stroked: true,
    filled: false,
    getLineColor: [148, 163, 184, 175], // slate, thin
    lineWidthUnits: "pixels",
    getLineWidth: 0.7,
    lineWidthMinPixels: 0.6,
    lineJointRounded: true,
    pickable: true,
  });
}

export function shoRegionsLayer(data: BoundaryData): Layer {
  return new GeoJsonLayer({
    id: "bnd-sho",
    data,
    stroked: true,
    filled: true,
    getFillColor: [59, 130, 246, 26], // faint jurisdiction wash
    getLineColor: [96, 165, 250, 155],
    lineWidthUnits: "pixels",
    getLineWidth: 0.6,
    lineWidthMinPixels: 0.5,
    lineJointRounded: true,
    pickable: true,
  });
}

/* --- Forecast: fine cell surface; radius by count, opacity by confidence -- */
export function forecastCells(cells: MapCell[], horizonScale = 1): Layer {
  const maxPred = Math.max(1, ...cells.map((c) => (c.predicted_count ?? 0) * horizonScale));
  return new ScatterplotLayer<MapCell>({
    id: "forecast-cells",
    data: cells.filter((c) => c.lat != null && c.lon != null),
    getPosition: (d) => [d.lon as number, d.lat as number],
    getFillColor: (d) => {
      const v = (d.predicted_count ?? 0) * horizonScale;
      const conf = d.confidence ?? 0.5;
      const [r, g, b] = rampRgb(
        ["#0b1a3a", "#5b1667", "#a32167", "#dd513a", "#f4941e", "#f6d746"],
        v / maxPred,
      );
      // confidence -> alpha (low confidence = faded => "uncertainty shown")
      return [r, g, b, Math.round(70 + conf * 165)] as [number, number, number, number];
    },
    getRadius: (d) => 300 + ((d.predicted_count ?? 0) * horizonScale) / maxPred * 900,
    radiusUnits: "meters",
    radiusMinPixels: 4,
    radiusMaxPixels: 26,
    stroked: false,
    pickable: true,
  });
}

/* --- Forecast (district aggregate): proportional symbols, policymaker-safe - */
export interface DistrictAgg {
  district_id: number;
  lon: number;
  lat: number;
  predicted: number;
  confidence: number;
}
export function districtSymbols(aggs: DistrictAgg[], horizonScale = 1): Layer {
  const maxPred = Math.max(1, ...aggs.map((a) => a.predicted * horizonScale));
  return new ScatterplotLayer<DistrictAgg>({
    id: "district-symbols",
    data: aggs,
    getPosition: (d) => [d.lon, d.lat],
    getFillColor: (d) => {
      const [r, g, b] = rampRgb(["#12376b", "#1d5aa6", "#2f7fd1", "#5aa2e8", "#9cc7f5"], (d.predicted * horizonScale) / maxPred);
      return [r, g, b, Math.round(90 + d.confidence * 150)] as [number, number, number, number];
    },
    getRadius: (d) => 2500 + Math.sqrt((d.predicted * horizonScale) / maxPred) * 22000,
    radiusUnits: "meters",
    radiusMinPixels: 8,
    radiusMaxPixels: 60,
    stroked: true,
    getLineColor: [255, 255, 255, 120],
    lineWidthUnits: "pixels",
    getLineWidth: 1,
    pickable: true,
  });
}

/* --- Patrol Planning: coverage-gap markers (high forecast, no hotspot near) */
export function coverageGaps(gaps: { lon: number; lat: number; predicted: number }[]): Layer {
  return new ScatterplotLayer({
    id: "coverage-gaps",
    data: gaps,
    getPosition: (d: { lon: number; lat: number }) => [d.lon, d.lat],
    getFillColor: [239, 68, 68, 40],
    getLineColor: [239, 68, 68, 230],
    stroked: true,
    filled: true,
    lineWidthUnits: "pixels",
    getLineWidth: 2,
    getRadius: 900,
    radiusUnits: "meters",
    radiusMinPixels: 8,
    radiusMaxPixels: 28,
    pickable: true,
  });
}

/* --- Red-Zone Alerts: pulsing rings (the only looping animation) + core --- */
export function alertPulse(alerts: AlertFeature[], pulse: number): Layer {
  return new ScatterplotLayer<AlertFeature>({
    id: "alert-pulse",
    data: alerts.filter((a) => a.lat != null && a.lon != null),
    getPosition: (d) => [d.lon as number, d.lat as number],
    getFillColor: (d) => {
      const c = SEV_RGB[d.severity] ?? SEV_RGB.info;
      return [c[0], c[1], c[2], Math.round((1 - pulse) * 120)] as [number, number, number, number];
    },
    getRadius: 400 + pulse * 2600,
    radiusUnits: "meters",
    radiusMinPixels: 6 + pulse * 26,
    stroked: false,
    updateTriggers: { getRadius: pulse, getFillColor: pulse, radiusMinPixels: pulse },
    pickable: false,
  });
}
export function alertCore(alerts: AlertFeature[], onClick?: (a: AlertFeature) => void): Layer {
  return new ScatterplotLayer<AlertFeature>({
    id: "alert-core",
    data: alerts.filter((a) => a.lat != null && a.lon != null),
    getPosition: (d) => [d.lon as number, d.lat as number],
    getFillColor: (d) => [...(SEV_RGB[d.severity] ?? SEV_RGB.info), 255] as [number, number, number, number],
    getRadius: 7,
    radiusUnits: "pixels",
    stroked: true,
    getLineColor: [255, 255, 255, 220],
    getLineWidth: 1.5,
    lineWidthUnits: "pixels",
    pickable: true,
    onClick: onClick ? (info) => info.object && onClick(info.object as AlertFeature) : undefined,
  });
}
