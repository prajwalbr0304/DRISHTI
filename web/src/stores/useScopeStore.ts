import { create } from "zustand";
import { persist } from "zustand/middleware";

/* ============================================================================
   Global geographic scope — the crime-side counterpart to the time window.

   One district id (or null = every district) narrows the dashboards, the way the
   AWS console region selector narrows every service page.

   IMPORTANT — this is a VIEW filter, not an authorisation boundary. The server
   re-derives and enforces what a role may read from the X-Role header; changing
   the selection here can never widen access. Emergency Response keeps its own
   two-axis store (useDisasterStore: assignedDistrict = write seat,
   activeDistrict = view filter) because a write seat is a different concept.

   Not every endpoint can honour it. See `districtSupport` below — the selector
   must never imply a filter that is not actually applied.
   ========================================================================== */

interface ScopeState {
  /** active district id, or null for "All districts" */
  districtId: number | null;
  setDistrictId: (id: number | null) => void;
}

export const useScopeStore = create<ScopeState>()(
  persist(
    (set) => ({
      districtId: null,
      setDistrictId: (districtId) => set({ districtId }),
    }),
    {
      name: "drishti.scope",
      version: 1,
      partialize: (s) => ({ districtId: s.districtId }),
    },
  ),
);

/** Convenience: the active district as a query param value (undefined = all). */
export function useDistrictParam(): number | undefined {
  return useScopeStore((s) => s.districtId) ?? undefined;
}

/* ----------------------------------------------------------------------------
   How far the district scope actually reaches.

   Recorded here rather than in prose so widgets can label themselves honestly.
     "server"  — the endpoint takes district_id and the API does the filtering
     "client"  — no district param, but rows carry district_id so we filter them
     "none"    — cannot be scoped; the widget stays state-wide and says so
   -------------------------------------------------------------------------- */
export type DistrictSupport = "server" | "client" | "none";

export const districtSupport = {
  /** GET /geo/trends?district_id= */
  trends: "server",
  /** GET /cases/caseload?district_id= */
  caseload: "server",
  /** GET /geo/hotspots — bbox only; HotspotFeature.district_id filtered here */
  hotspots: "client",
  /** GET /geo/alerts — bbox only; AlertFeature.district_id filtered here */
  alerts: "client",
  /** GET /forecast/map — no district param; MapCell.district_id filtered here */
  forecastMap: "client",
  /** GET /analytics/socioeconomic — a correlation ACROSS districts. Narrowing to
   *  one district cannot produce a correlation, so this stays state-wide. */
  socio: "none",
  /** GET /graph/centrality — no district in the params or the response. */
  centrality: "none",
} as const satisfies Record<string, DistrictSupport>;

/** Label for a widget whose data ignores the district selection. */
export const STATE_WIDE_NOTE =
  "State-wide: this measure is computed across all districts and does not follow the district selector.";
