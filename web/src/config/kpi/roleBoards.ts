import type { ScopeType, UserRole } from "@/config/roles";
import { KPI_BY_ID, KPI_REGISTRY, kpiApplies, type KpiSpec } from "@/config/kpi/registry";

/* ============================================================================
   Per-seat board composition.

   The registry says where a metric is MEANINGFUL. This file says which of those
   a given seat should actually be shown, and in what order — the difference
   between "the number exists" and "this is what you are accountable for".

   Boards are keyed by scope type rather than by role, because that is what the
   board is really a function of: a senior_command seat is an ADGP wing board when
   wing-scoped and a DIG range board when range-scoped, and those are different
   jobs sharing one UI surface.

   `omit` records cards that ARE meaningful at this scope but are deliberately not
   this seat's business, so the choice is reviewable instead of looking like an
   oversight. Anything meaningful and not omitted is included.
   ========================================================================== */

export interface WidgetSpec {
  id: string;
  label: string;
  /** Grid footprint on the 12-column board. */
  w: number;
  h: number;
}

export interface BoardSpec {
  scope: ScopeType;
  /** Heading shown above the board. */
  title: string;
  /** One line on what this seat is accountable for. */
  subtitle: string;
  /** Explicit card order. Cards not listed fall back to registry order. */
  order?: string[];
  /** Meaningful here, but deliberately not shown, with the reason. */
  omit?: Record<string, string>;
  widgets: WidgetSpec[];
}

const TREND: WidgetSpec = { id: "trend", label: "Crime trend", w: 8, h: 7 };
const FORECAST: WidgetSpec = { id: "forecast", label: "District forecast", w: 4, h: 7 };
const HOTSPOT_MAP: WidgetSpec = { id: "hotspot-map", label: "Hotspots", w: 6, h: 7 };
const STATUS_PIPELINE: WidgetSpec = { id: "pipeline", label: "Case pipeline", w: 6, h: 6 };
const ATTENTION: WidgetSpec = { id: "attention", label: "Attention queue", w: 6, h: 6 };

export const BOARDS: Record<ScopeType, BoardSpec> = {
  /* --- DGP: the whole force, aggregate only ----------------------------- */
  state: {
    scope: "state",
    title: "State Command",
    subtitle: "State-wide priorities, outcomes and readiness. Aggregate only.",
    order: [
      "kpi-incidents", "kpi-mom", "kpi-critical-alerts", "kpi-anomalies",
      "kpi-hotspots", "kpi-open-cases", "kpi-workload", "kpi-new-firs",
      "kpi-chargesheet", "kpi-days-to-chargesheet", "kpi-disposal",
      "kpi-conviction", "kpi-prosecution-rate",
      "kpi-overdue", "kpi-imbalance", "kpi-stations", "kpi-officers",
      "kpi-predicted", "kpi-wape", "kpi-coverage", "kpi-abstention",
      "kpi-data-age", "kpi-data-quality", "kpi-jurisdiction", "kpi-suppressed",
      "kpi-districts", "kpi-conformance",
      "kpi-patterns", "kpi-groups", "kpi-tasks",
    ],
    omit: {
      "kpi-open-alerts":
        "The state board carries the critical queue only. Total alert volume is a range and district supervision measure.",
      "kpi-poi":
        "Names people. A state seat is aggregate-only, so persons of interest belong to the seats that can act on them.",
    },
    widgets: [
      TREND, FORECAST,
      { id: "range-league", label: "Range comparison", w: 6, h: 7 },
      { id: "socio", label: "Socio-economic correlations", w: 6, h: 7 },
    ],
  },

  /* --- ADGP: state-wide, own crime heads -------------------------------- */
  wing: {
    scope: "wing",
    title: "Wing Command",
    subtitle: "State-wide accountability for this wing's crime heads.",
    order: [
      "kpi-incidents", "kpi-mom", "kpi-critical-alerts", "kpi-open-alerts",
      "kpi-anomalies", "kpi-hotspots", "kpi-open-cases", "kpi-workload",
      "kpi-new-firs", "kpi-chargesheet", "kpi-days-to-chargesheet", "kpi-disposal",
      "kpi-conviction", "kpi-overdue", "kpi-ageing-180", "kpi-imbalance",
      "kpi-stations", "kpi-officers", "kpi-predicted",
      "kpi-wape", "kpi-coverage", "kpi-abstention",
      "kpi-data-age", "kpi-data-quality", "kpi-jurisdiction",
      "kpi-suppressed", "kpi-districts",
      "kpi-patterns", "kpi-groups", "kpi-tasks",
      "kpi-flagged-txn", "kpi-money-trails", "kpi-linked-accounts",
      "kpi-traffic-incidents", "kpi-accident-hotspots",
    ],
    omit: {
      "kpi-poi":
        "Names people, and a wing seat is aggregate-only. Wing analysis hands off to a district or station seat to act.",
    },
    widgets: [
      TREND,
      { id: "head-breakdown", label: "By crime head", w: 4, h: 7 },
      { id: "district-league", label: "District comparison", w: 6, h: 7 },
      HOTSPOT_MAP,
    ],
  },

  /* --- DIG: compare the districts in the range -------------------------- */
  range: {
    scope: "range",
    title: "Range Command",
    subtitle: "Cross-district comparison and supervision within the range.",
    order: [
      "kpi-incidents", "kpi-mom", "kpi-critical-alerts", "kpi-open-alerts",
      "kpi-anomalies", "kpi-hotspots", "kpi-open-cases", "kpi-workload",
      "kpi-new-firs", "kpi-chargesheet", "kpi-days-to-chargesheet", "kpi-disposal",
      "kpi-conviction", "kpi-overdue", "kpi-ageing-180", "kpi-imbalance",
      "kpi-stations", "kpi-officers", "kpi-officer-p90", "kpi-heavy-load",
      "kpi-predicted", "kpi-data-age", "kpi-data-quality", "kpi-jurisdiction",
      "kpi-districts", "kpi-patterns", "kpi-groups", "kpi-poi", "kpi-tasks",
    ],
    widgets: [
      { id: "district-league", label: "District comparison", w: 8, h: 7 },
      FORECAST, TREND, HOTSPOT_MAP,
    ],
  },

  /* --- SP: one district, all its stations ------------------------------- */
  district: {
    scope: "district",
    title: "District Command",
    subtitle: "District workload, station performance and approvals.",
    order: [
      "kpi-incidents", "kpi-mom", "kpi-new-firs", "kpi-open-cases",
      "kpi-workload", "kpi-critical-alerts", "kpi-open-alerts", "kpi-hotspots",
      "kpi-chargesheet", "kpi-days-to-chargesheet", "kpi-disposal", "kpi-conviction",
      "kpi-overdue", "kpi-ageing-180", "kpi-imbalance", "kpi-stations",
      "kpi-officers", "kpi-officer-p90", "kpi-heavy-load", "kpi-predicted",
      "kpi-data-age", "kpi-data-quality", "kpi-jurisdiction",
      "kpi-patterns", "kpi-groups", "kpi-poi", "kpi-tasks",
    ],
    omit: {
      "kpi-anomalies":
        "Kept for range and above, where the series has the volume to make a rolling band informative.",
    },
    widgets: [
      { id: "station-league", label: "Station performance", w: 8, h: 7 },
      FORECAST, TREND, HOTSPOT_MAP, ATTENTION,
    ],
  },

  /* --- CP: same job, city command -------------------------------------- */
  commissionerate: {
    scope: "commissionerate",
    title: "City Commissionerate",
    subtitle: "City workload, station performance and approvals.",
    order: [
      "kpi-incidents", "kpi-mom", "kpi-new-firs", "kpi-open-cases",
      "kpi-workload", "kpi-critical-alerts", "kpi-open-alerts", "kpi-hotspots",
      "kpi-chargesheet", "kpi-days-to-chargesheet", "kpi-disposal", "kpi-conviction",
      "kpi-overdue", "kpi-ageing-180", "kpi-imbalance", "kpi-stations",
      "kpi-officers", "kpi-officer-p90", "kpi-heavy-load", "kpi-predicted",
      "kpi-data-age", "kpi-data-quality", "kpi-jurisdiction",
      "kpi-patterns", "kpi-groups", "kpi-poi", "kpi-tasks",
    ],
    omit: {
      "kpi-anomalies":
        "Kept for range and above, where the series has the volume to make a rolling band informative.",
    },
    widgets: [
      { id: "station-league", label: "Station performance", w: 8, h: 7 },
      FORECAST, TREND, HOTSPOT_MAP, ATTENTION,
    ],
  },

  /* --- SHO: one station ------------------------------------------------ */
  station: {
    scope: "station",
    title: "Station Command",
    subtitle: "Registration, assignment and the station review queue.",
    order: [
      "kpi-incidents", "kpi-mom", "kpi-new-firs", "kpi-open-cases", "kpi-workload",
      "kpi-critical-alerts", "kpi-open-alerts", "kpi-hotspots",
      "kpi-review-queue", "kpi-chargesheet", "kpi-days-to-chargesheet",
      "kpi-disposal", "kpi-overdue", "kpi-ageing-180",
      "kpi-officers", "kpi-officer-p90", "kpi-heavy-load",
      "kpi-next-hearing", "kpi-evidence-pending",
      "kpi-data-age", "kpi-data-quality", "kpi-jurisdiction",
      "kpi-patterns", "kpi-poi", "kpi-tasks",
    ],
    omit: {
      "kpi-conviction":
        "Court outcomes at a single station are too few per window to read as a rate; the district board carries it.",
    },
    widgets: [
      STATUS_PIPELINE,
      { id: "officer-load", label: "Officer load", w: 6, h: 6 },
      { id: "station-jurisdiction", label: "Station jurisdiction", w: 6, h: 7 },
      ATTENTION,
    ],
  },

  /* --- IO: my cases ---------------------------------------------------- */
  assigned_case: {
    scope: "assigned_case",
    title: "My Case Work",
    subtitle: "Your assigned cases, evidence and leads.",
    order: [
      "kpi-my-open", "kpi-my-new", "kpi-my-alerts", "kpi-overdue",
      "kpi-days-to-chargesheet", "kpi-ageing-180",
      "kpi-next-hearing", "kpi-evidence-pending", "kpi-hotspots",
      "kpi-poi", "kpi-tasks",
    ],
    widgets: [
      { id: "my-caseload", label: "My caseload", w: 6, h: 6 },
      ATTENTION,
      { id: "case-timeline", label: "Recent activity", w: 6, h: 6 },
      { id: "my-jurisdiction", label: "My jurisdiction", w: 6, h: 7 },
    ],
  },

  /* --- Admin ----------------------------------------------------------- */
  platform: {
    scope: "platform",
    title: "Platform Administration",
    subtitle: "Seats, roles, UI visibility, models and data integrity.",
    order: [
      "kpi-active-seats", "kpi-imports", "kpi-models", "kpi-ui-overrides",
      "kpi-conformance", "kpi-data-age", "kpi-data-quality", "kpi-jurisdiction",
      "kpi-tasks",
    ],
    widgets: [
      { id: "seat-directory", label: "Seat directory", w: 8, h: 7 },
      { id: "role-matrix", label: "Role and UI visibility", w: 4, h: 7 },
    ],
  },

  /* --- Unposted seat: says so, shows nothing --------------------------- */
  unresolved: {
    scope: "unresolved",
    title: "No posting on record",
    subtitle:
      "This seat has no district, station or wing assigned, so no data is in scope. An administrator must post it before any figures appear.",
    order: [],
    widgets: [],
  },
};

/** Cards to render for a seat, in board order.
 *
 *  Composed by intersecting three things: what the metric is defined at, what the
 *  board asks for, and what the board explicitly omits. A card listed in `order`
 *  but not meaningful at this scope is dropped rather than rendered empty. */
export function boardKpis(scope: ScopeType, wingCode?: string | null): KpiSpec[] {
  const board = BOARDS[scope];
  if (!board) return [];
  const omitted = new Set(Object.keys(board.omit ?? {}));

  const eligible = KPI_REGISTRY.filter(
    (k) => kpiApplies(k, scope, wingCode) && !omitted.has(k.id),
  );

  if (!board.order?.length) return board.order ? [] : eligible;

  const eligibleIds = new Set(eligible.map((k) => k.id));
  const ordered = board.order
    .filter((id) => eligibleIds.has(id))
    .map((id) => KPI_BY_ID[id]);

  // Anything eligible the board forgot to order still renders, after the
  // explicit list — a new registry card appears rather than vanishing silently.
  const orderedIds = new Set(ordered.map((k) => k.id));
  return [...ordered, ...eligible.filter((k) => !orderedIds.has(k.id))];
}

export function boardFor(scope: ScopeType): BoardSpec {
  return BOARDS[scope] ?? BOARDS.unresolved;
}

/** Why a meaningful card is not on this board. Empty when it is shown or N/A. */
export function omissionReason(scope: ScopeType, kpiId: string): string | undefined {
  return BOARDS[scope]?.omit?.[kpiId];
}

/** Role -> the scope types whose boards it can render. Used by the admin console
 *  to show which boards a role reaches. */
export function boardsForRole(role: UserRole, scopeTypes: ScopeType[]): BoardSpec[] {
  return scopeTypes.map((s) => BOARDS[s]).filter(Boolean);
}
