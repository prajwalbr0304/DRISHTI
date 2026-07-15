import { CATEGORY_PALETTE, seriesColor } from "@/lib/palette";
import { hashString } from "@/lib/utils";

/* ============================================================================
   The graph encoding contract (doc 03 §4 / doc 04 §7), made concrete for
   WebGL rendering (sigma needs literal hex, not CSS variables):
     node size   = centrality
     node colour = entity type OR community (mode-dependent)
     halo        = high influence (top centrality)
     edge width  = relationship strength
     edge colour = relationship type
   A given entity type / community is ALWAYS the same colour (fixed palette).
   ========================================================================== */

export const ENTITY_COLORS: Record<string, string> = {
  person: "#6366f1", // indigo
  gang: "#f43f5e", // rose
  vehicle: "#f97316", // orange
  phone: "#06b6d4", // cyan
  location: "#0ea5e9", // sky
  bank_account: "#84cc16", // lime
  account: "#84cc16",
  organisation: "#a855f7", // purple
};
const DEFAULT_NODE = "#64748b"; // slate

export const ENTITY_LEGEND: { type: string; label: string; color: string }[] = [
  { type: "person", label: "Person", color: ENTITY_COLORS.person },
  { type: "gang", label: "Gang", color: ENTITY_COLORS.gang },
  { type: "vehicle", label: "Vehicle", color: ENTITY_COLORS.vehicle },
  { type: "phone", label: "Phone", color: ENTITY_COLORS.phone },
  { type: "location", label: "Location", color: ENTITY_COLORS.location },
  { type: "bank_account", label: "Account", color: ENTITY_COLORS.bank_account },
];

export function entityColor(entityType?: string | null): string {
  if (!entityType) return DEFAULT_NODE;
  return ENTITY_COLORS[entityType] ?? DEFAULT_NODE;
}

export function communityColor(community?: number | null): string {
  if (community == null) return DEFAULT_NODE;
  return CATEGORY_PALETTE[((community % 12) + 12) % 12];
}

const REL_COLORS: Record<string, string> = {
  co_accused: "#f59e0b",
  "co-accused": "#f59e0b",
  same_address: "#0ea5e9",
  "same-address": "#0ea5e9",
  same_phone: "#06b6d4",
  same_vehicle: "#f97316",
  financial: "#84cc16",
  transaction: "#84cc16",
  gang_member: "#f43f5e",
  called: "#a855f7",
};

export function relationshipColor(relType?: string | null): string {
  if (!relType) return "#334155";
  const key = relType.toLowerCase();
  if (REL_COLORS[key]) return REL_COLORS[key];
  return seriesColor(hashString(key));
}

/** Map a value within [min,max] to a node radius in [minR, maxR]. */
export function scaleSize(value: number, min: number, max: number, minR = 4, maxR = 18): number {
  if (!Number.isFinite(value)) return minR;
  if (max <= min) return (minR + maxR) / 2;
  const t = (value - min) / (max - min);
  return minR + Math.sqrt(Math.max(0, Math.min(1, t))) * (maxR - minR);
}

/** Edge width from a domain weight (0..1-ish or larger). */
export function scaleEdge(weight?: number | null): number {
  const w = weight ?? 0;
  return 0.6 + Math.min(1, Math.max(0, w)) * 3.4;
}
