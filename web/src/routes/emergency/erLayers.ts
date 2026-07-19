import { GeoJsonLayer, ScatterplotLayer, PathLayer } from "@deck.gl/layers";
import type { Layer } from "@deck.gl/core";
import type {
  EvacRoute, HazardEvent, HazardRiskZone, HydroMetReading, Resource, Shelter,
} from "@/api/endpoints/disaster";

/* ============================================================================
   deck.gl layers for the Live Situation map (Prompt 17 §H). Disaster palette
   (amber/orange/red for hazards + risk, teal/green for readiness, blue for
   sensors/routes) — deliberately distinct from the criminal-person risk visuals.
   Observed / predicted / synthetic layers stay distinguishable via the legend.
   ========================================================================== */

type RGBA = [number, number, number, number];

const SEVERITY_FILL: Record<string, RGBA> = {
  minor: [250, 204, 21, 70], moderate: [249, 115, 22, 80],
  severe: [239, 68, 68, 95], extreme: [190, 18, 60, 110],
};
const SEVERITY_LINE: Record<string, RGBA> = {
  minor: [202, 138, 4, 220], moderate: [234, 88, 12, 235],
  severe: [220, 38, 38, 245], extreme: [190, 18, 60, 255],
};
const RISK_FILL: Record<string, RGBA> = {
  low: [16, 185, 129, 55], medium: [245, 158, 11, 70],
  high: [239, 68, 68, 90], critical: [190, 18, 60, 110],
};
const METRIC_COLOR: Record<string, RGBA> = {
  rainfall: [56, 189, 248, 220], river_level: [14, 165, 233, 230],
  reservoir_level: [2, 132, 199, 230], temperature: [239, 68, 68, 220],
  wind: [148, 163, 184, 220], humidity: [45, 212, 191, 220],
};

function fc(features: GeoJSON.Feature[]): GeoJSON.FeatureCollection {
  return { type: "FeatureCollection", features };
}

export function hazardExtentLayer(events: HazardEvent[]): Layer {
  const features = events
    .filter((e) => e.geojson && (e.geojson as { type?: string }).type)
    .map((e) => ({
      type: "Feature" as const,
      geometry: e.geojson as unknown as GeoJSON.Geometry,
      properties: { severity: e.severity, hazard: e.hazard_code, id: e.hazard_event_id,
                    status: e.status },
    }));
  return new GeoJsonLayer({
    id: "er-hazard-extent",
    data: fc(features),
    stroked: true, filled: true,
    getFillColor: (f) => SEVERITY_FILL[(f.properties as { severity: string }).severity] ?? SEVERITY_FILL.moderate,
    getLineColor: (f) => SEVERITY_LINE[(f.properties as { severity: string }).severity] ?? SEVERITY_LINE.moderate,
    lineWidthUnits: "pixels", getLineWidth: 2, lineWidthMinPixels: 1.5,
    pointRadiusMinPixels: 6, pickable: true,
  });
}

export function riskZoneLayer(zones: HazardRiskZone[]): Layer {
  const features = zones
    .filter((z) => z.geojson && (z.geojson as { type?: string }).type)
    .map((z) => ({
      type: "Feature" as const,
      geometry: z.geojson as unknown as GeoJSON.Geometry,
      properties: { risk: z.risk_level, kind: z.zone_kind, id: z.hazard_risk_zone_id,
                    hazard: z.hazard_code, score: z.score },
    }));
  return new GeoJsonLayer({
    id: "er-risk-zones",
    data: fc(features),
    stroked: true, filled: true,
    getFillColor: (f) => RISK_FILL[(f.properties as { risk: string }).risk] ?? RISK_FILL.medium,
    getLineColor: [148, 163, 184, 180],
    // dashed feel for static susceptibility vs solid dynamic (line width proxy)
    lineWidthUnits: "pixels",
    getLineWidth: (f) => ((f.properties as { kind: string }).kind === "static" ? 0.8 : 1.6),
    lineWidthMinPixels: 0.8, pickable: true,
  });
}

export function sensorLayer(readings: HydroMetReading[]): Layer {
  return new ScatterplotLayer<HydroMetReading>({
    id: "er-sensors",
    data: readings.filter((r) => r.lon != null && r.lat != null),
    getPosition: (d) => [d.lon as number, d.lat as number],
    getFillColor: (d) => {
      const c = METRIC_COLOR[d.metric_type] ?? [148, 163, 184, 220];
      // fade suspect/missing/superseded readings so quality reads at a glance
      return d.quality_flag === "valid" ? c : [c[0], c[1], c[2], 90] as RGBA;
    },
    getRadius: 4, radiusUnits: "pixels", radiusMinPixels: 3, radiusMaxPixels: 8,
    stroked: true, getLineColor: [255, 255, 255, 120], lineWidthMinPixels: 0.5,
    pickable: true,
  });
}

export function resourceLayer(resources: Resource[]): Layer {
  return new ScatterplotLayer<Resource>({
    id: "er-resources",
    data: resources.filter((r) => r.lon != null && r.lat != null),
    getPosition: (d) => [d.lon as number, d.lat as number],
    getFillColor: (d) =>
      d.status === "available" ? [13, 148, 136, 235]
      : d.status === "deployed" ? [79, 70, 229, 235]
      : [148, 163, 184, 200],
    getRadius: 6, radiusUnits: "pixels", radiusMinPixels: 5, radiusMaxPixels: 12,
    stroked: true, getLineColor: [255, 255, 255, 160], lineWidthMinPixels: 1,
    pickable: true,
  });
}

export function shelterLayer(shelters: Shelter[]): Layer {
  return new ScatterplotLayer<Shelter>({
    id: "er-shelters",
    data: shelters.filter((s) => s.lon != null && s.lat != null),
    getPosition: (d) => [d.lon as number, d.lat as number],
    getFillColor: (d) => (d.status === "full" ? [217, 119, 6, 235] : [22, 163, 74, 235]),
    getRadius: 7, radiusUnits: "pixels", radiusMinPixels: 6, radiusMaxPixels: 14,
    stroked: true, getLineColor: [255, 255, 255, 200], lineWidthMinPixels: 1.2,
    pickable: true,
  });
}

export function routeLayer(routes: EvacRoute[]): Layer {
  const paths = routes
    .filter((r) => r.geojson && (r.geojson as { type?: string }).type === "LineString")
    .map((r) => ({
      path: (r.geojson as unknown as { coordinates: [number, number][] }).coordinates,
      status: r.status,
    }));
  return new PathLayer<{ path: [number, number][]; status: string }>({
    id: "er-routes",
    data: paths,
    getPath: (d) => d.path,
    getColor: (d) => (d.status === "selected" ? [37, 99, 235, 255] : [2, 132, 199, 200]),
    getWidth: 3, widthUnits: "pixels", widthMinPixels: 2, capRounded: true, jointRounded: true,
    pickable: true,
  });
}

export const ER_LEGEND = [
  { label: "Hazard extent (observed/active)", color: "#ea580c" },
  { label: "Risk zone (predicted)", color: "#f59e0b" },
  { label: "Sensor reading (observed)", color: "#38bdf8" },
  { label: "Resource (available)", color: "#0d9488" },
  { label: "Shelter", color: "#16a34a" },
  { label: "Evacuation route", color: "#2563eb" },
];
