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
  /** Active station (Unit) id, or null. One level BELOW district: drilling into a
   *  station always implies its district, so the two are set together and clearing
   *  the district clears this too. Kept separate from `districtId` rather than
   *  overloading it, because "district 4, all stations" and "district 4, station
   *  112" are different views and a single field cannot hold both. */
  unitId: number | null;
  /** Display label for the drilled-into station, so the trail can name it without
   *  a second lookup. Presentation only. */
  unitLabel: string | null;
  /** true once the USER has picked a district. Guards the seat default below:
   *  an explicit choice must never be silently overwritten, including an explicit
   *  choice of "All districts" — which is indistinguishable from the initial
   *  state by `districtId` alone, hence this flag. */
  chosen: boolean;
  setDistrictId: (id: number | null) => void;
  /** Drill into a station. Sets the district too, so the trail is never a station
   *  with no district above it. */
  drillToUnit: (unitId: number, districtId: number, label?: string) => void;
  /** Step back up to district grain, keeping the district. */
  clearUnit: () => void;
  /** Adopt the seat's own district as the starting scope (see useSeatScopeAnchor).
   *  A no-op once the user has chosen, so it can be called freely on every
   *  render/route. Re-applies when the seat changes, so switching from an SHO view
   *  to a DGP view moves the scope back to state-wide on its own. */
  seedFromSeat: (id: number | null) => void;
}

export const useScopeStore = create<ScopeState>()(
  persist(
    (set) => ({
      districtId: null,
      unitId: null,
      unitLabel: null,
      chosen: false,
      // Changing district drops any station: station 112 is not in district 9, so
      // carrying it across would produce a filter that matches nothing.
      setDistrictId: (districtId) =>
        set({ districtId, unitId: null, unitLabel: null, chosen: true }),
      drillToUnit: (unitId, districtId, label) =>
        set({ unitId, districtId, unitLabel: label ?? null, chosen: true }),
      clearUnit: () => set({ unitId: null, unitLabel: null }),
      seedFromSeat: (districtId) =>
        set((s) => (s.chosen || s.districtId === districtId ? s : { districtId })),
    }),
    {
      name: "drishti.scope",
      version: 3,
      partialize: (s) => ({
        districtId: s.districtId, unitId: s.unitId, unitLabel: s.unitLabel,
        chosen: s.chosen,
      }),
      // v1 had no `chosen` flag. Anyone carrying a real district plainly picked
      // it, so treat that as chosen and leave it alone; anyone sitting on "All
      // districts" is indistinguishable from a fresh install and gets the seat
      // default instead.
      // v1 had no `chosen`; v2 had no station level. A persisted v2 state carries
      // no unitId, and `undefined` there would read as "not yet loaded" rather
      // than "no station", so it is normalised to null.
      migrate: (persisted) => {
        const p = (persisted ?? {}) as Partial<ScopeState>;
        return {
          ...p,
          chosen: p.chosen ?? p.districtId != null,
          unitId: p.unitId ?? null,
          unitLabel: p.unitLabel ?? null,
        } as ScopeState;
      },
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
     "focus"   — a district cannot be filtered to without destroying the measure,
                 so the widget keeps the full state-wide set and HIGHLIGHTS the
                 district instead. Different from "none": the selection is
                 honoured, just as emphasis rather than as a filter.
     "none"    — cannot be scoped; the widget stays state-wide and says so
   -------------------------------------------------------------------------- */
export type DistrictSupport = "server" | "client" | "focus" | "none";

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
  /** GET /performance/overview?district_id= — confined server-side to the
   *  caller's scope, so a state seat may request one district or all of them. */
  performance: "server",
  /** GET /analytics/socioeconomic — a correlation ACROSS districts. Narrowing to
   *  one district cannot produce a correlation (one point has none, and there is
   *  no socio-economic or population data below district grain to correlate
   *  within a district instead). The per-indicator boxes therefore follow the
   *  selector as EMPHASIS: they keep the whole district cloud and ring the
   *  selected district, reporting where it sits against the state median and the
   *  fit. The narrative and the ranked r values stay state-wide, because that is
   *  what they measure. */
  socio: "focus",
  /** GET /graph/centrality — no district in the params or the response. */
  centrality: "none",
  /** GET /forecast/backtest — model accuracy is reported per season and per head
   *  with a geographic holdout, not as a per-district filter. */
  backtest: "none",
  /** GET /explain/contract — an audit of API routes, not of crime data. */
  contract: "none",
  /** GET /intake/quality/issues — staged records, many of which have no district
   *  yet (that is often the defect being flagged). */
  dataQuality: "none",
  /** GET /geo/jurisdiction/freshness — boundary versions across the state. */
  jurisdictionFreshness: "none",
  /** GET /analytics/patterns — a pattern may span districts by construction. */
  patterns: "none",
  /** GET /graph/communities/list — no district in the params or the response. */
  communities: "none",
  /** GET /notifications, /notifications/tasks — queues are scoped by actor and
   *  status, never by geography. */
  notifications: "none",
} as const satisfies Record<string, DistrictSupport>;

/** Label for a widget whose data ignores the district selection. */
export const STATE_WIDE_NOTE =
  "State-wide: this measure is computed across all districts and does not follow the district selector.";
