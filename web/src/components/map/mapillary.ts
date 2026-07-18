/* ============================================================================
   Mapillary integration (street-level imagery). Uses a public client read
   token (VITE_MAPILLARY_TOKEN, via src/config/runtime) — safe to run
   client-side. Provides the vector coverage tiles and a nearest-image lookup
   for the street-view viewer.
   ========================================================================== */

import { runtime } from "@/config/runtime";

export const MAPILLARY_TOKEN = runtime.mapillaryToken;

export function hasMapillary(): boolean {
  return MAPILLARY_TOKEN.length > 0;
}

/** Vector coverage tiles (sequence/image layers). Empty when no token. */
export const MAPILLARY_TILES = MAPILLARY_TOKEN
  ? `https://tiles.mapillary.com/maps/vtp/mly1_public/2/{z}/{x}/{y}?access_token=${MAPILLARY_TOKEN}`
  : "";

export interface MlyImage {
  id: string;
  lon: number;
  lat: number;
}

/**
 * Find the Mapillary image closest to a coordinate (Graph API bbox search).
 * Widens the search radius a couple of times before giving up.
 */
export async function findNearestMapillaryImage(
  lon: number,
  lat: number,
  signal?: AbortSignal,
): Promise<MlyImage | null> {
  if (!hasMapillary()) return null;
  for (const radius of [0.006, 0.015, 0.04]) {
    const bbox = [lon - radius, lat - radius, lon + radius, lat + radius]
      .map((n) => n.toFixed(6))
      .join(",");
    // NB: request only `geometry` — `computed_geometry` in a bbox search 500s.
    const url =
      `https://graph.mapillary.com/images?access_token=${encodeURIComponent(MAPILLARY_TOKEN)}` +
      `&fields=id,geometry&bbox=${bbox}&limit=50`;
    const res = await fetch(url, { signal });
    if (!res.ok) throw new Error(`Mapillary API ${res.status}`);
    const json = (await res.json()) as {
      data?: { id: string; geometry?: GeoPoint }[];
    };
    const data = json.data ?? [];
    let best: MlyImage | null = null;
    let bestDist = Infinity;
    for (const img of data) {
      const coords = img.geometry?.coordinates;
      if (!coords) continue;
      const d = (coords[0] - lon) ** 2 + (coords[1] - lat) ** 2;
      if (d < bestDist) {
        bestDist = d;
        best = { id: img.id, lon: coords[0], lat: coords[1] };
      }
    }
    if (best) return best;
  }
  return null;
}

interface GeoPoint {
  type: string;
  coordinates: [number, number];
}
