import type { StyleSpecification } from "maplibre-gl";
import { SEQUENTIAL_BLUE, SEQUENTIAL_HEAT } from "@/lib/palette";

/* ============================================================================
   Map configuration: free basemaps (no API key), the Karnataka default view,
   and colour helpers for deck.gl (which needs [r,g,b] tuples).
   ========================================================================== */

export const MAP_STYLES = {
  ops: "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
  desk: "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
} as const;

/* --- Selectable basemap modes (satellite / streets / dark / light) -------- */
export type BasemapId = "auto" | "dark" | "light" | "streets" | "satellite";

export const BASEMAP_OPTIONS: { id: BasemapId; label: string }[] = [
  { id: "auto", label: "Match theme" },
  { id: "dark", label: "Dark" },
  { id: "light", label: "Light" },
  { id: "streets", label: "Streets" },
  { id: "satellite", label: "Satellite" },
];

const STREETS_STYLE = "https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json";

// Esri World Imagery + place/boundary labels — free, no key required.
const SATELLITE_STYLE: StyleSpecification = {
  version: 8,
  sources: {
    "esri-imagery": {
      type: "raster",
      tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"],
      tileSize: 256,
      attribution: "Imagery © Esri, Maxar, Earthstar Geographics",
    },
    "esri-labels": {
      type: "raster",
      tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}"],
      tileSize: 256,
    },
  },
  layers: [
    { id: "esri-imagery", type: "raster", source: "esri-imagery" },
    { id: "esri-labels", type: "raster", source: "esri-labels" },
  ],
};

/** Resolve a basemap selection to a MapLibre style (URL or spec). */
export function basemapStyle(id: BasemapId, theme: "ops" | "desk"): string | StyleSpecification {
  switch (id) {
    case "dark":
      return MAP_STYLES.ops;
    case "light":
      return MAP_STYLES.desk;
    case "streets":
      return STREETS_STYLE;
    case "satellite":
      return SATELLITE_STYLE;
    default:
      return theme === "ops" ? MAP_STYLES.ops : MAP_STYLES.desk;
  }
}

/** Karnataka, roughly centred. */
export const KARNATAKA_VIEW = {
  longitude: 76.2,
  latitude: 14.8,
  zoom: 5.7,
  pitch: 0,
  bearing: 0,
};

export type RGB = [number, number, number];
export type RGBA = [number, number, number, number];

export function hexToRgb(hex: string): RGB {
  const h = hex.replace("#", "");
  const n = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
  return [
    parseInt(n.slice(0, 2), 16),
    parseInt(n.slice(2, 4), 16),
    parseInt(n.slice(4, 6), 16),
  ];
}

/** Sample a hex ramp at t in [0,1] -> rgb. */
export function rampRgb(ramp: readonly string[], t: number): RGB {
  const clamped = Math.min(1, Math.max(0, t));
  return hexToRgb(ramp[Math.round(clamped * (ramp.length - 1))]);
}

export const HEAT_RAMP_RGB: RGB[] = SEQUENTIAL_HEAT.map(hexToRgb);
export const BLUE_RAMP_RGB: RGB[] = SEQUENTIAL_BLUE.map(hexToRgb);

/** deck.gl HeatmapLayer colorRange (6 stops, flattened as RGB). */
export const HEATMAP_RANGE: RGB[] = [...HEAT_RAMP_RGB];
