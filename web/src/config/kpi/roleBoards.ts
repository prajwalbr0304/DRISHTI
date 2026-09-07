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

/* The socio-economic band. COMPOSITE: RoleBoard expands this one entry into a
   full-width read-out (narrative + the ranked-r bar chart + the shared crime-type
   selector) plus one scatter tile per indicator, via `socioTiles`.

   The footprint declared here is the READ-OUT's; the indicator tiles size
   themselves in socioTiles.tsx, since how many there are is only known once the
   service answers. It carries `socio-band` rather than a component id so the whole
   band is one admin switch and one dismissal instead of eleven.

   ON EVERY BOARD EXCEPT THE IO'S. Socio-economic and population data exist only at
   DISTRICT grain, so this is always a district-level correlation no matter which
   seat is reading it — which is why it can sit on a station board (a station's
   figures against its district's economic context) as readily as a state one. The
   assigned-case board is the single exclusion, and the reason is recorded there. */
const SOCIO_BAND: WidgetSpec = {
  id: "socio-band",
  label: "Socio-economic correlations",
  w: 12,
  h: 8,
};

/* An SP of a district and a CP of a Commissionerate do the same job over a
   different kind of jurisdiction, so their boards are the same board. Shared
   rather than duplicated because the two copies had to be edited in lockstep and
   silently diverging was the only possible outcome of forgetting one.

   `kpi-anomalies` is no longer omitted here. It was held back on the grounds that
   the rolling band needs volume, but a district's monthly series carries thousands
   of cases — the registry already withholds the card at STATION grain, which is
   where the sparseness argument actually bites. */
const DISTRICT_ORDER: string[] = [
  "kpi-incidents", "kpi-mom", "kpi-anomalies", "kpi-new-firs", "kpi-open-cases",
  "kpi-workload",
  "kpi-critical-alerts", "kpi-open-alerts", "kpi-hotspots",
  "kpi-chargesheet", "kpi-days-to-chargesheet", "kpi-disposal",
  "kpi-conviction", "kpi-prosecution-rate",
  "kpi-overdue", "kpi-ageing-180", "kpi-imbalance",
  "kpi-stations", "kpi-officers", "kpi-officer-p90", "kpi-heavy-load",
  "kpi-predicted",
  "kpi-data-age", "kpi-data-quality", "kpi-jurisdiction", "kpi-suppressed",
  "kpi-patterns", "kpi-groups", "kpi-poi", "kpi-tasks",
];

const DISTRICT_WIDGETS: WidgetSpec[] = [
  { id: "station-league", label: "Station performance", w: 8, h: 7 },
  FORECAST, TREND, HOTSPOT_MAP, STATUS_PIPELINE, ATTENTION,
  SOCIO_BAND,
];

export const BOARDS: Record<ScopeType, BoardSpec> = {
  /* --- DGP: the whole force, aggregate only -----------------------------
     Carries every card and chart that is DEFINED state-wide. The two former
     omissions are gone: total open-alert volume is a queue depth a state seat
     should see beside the critical count, and the persons-of-interest card is now
     excluded by the registry itself (it is the one Band F card that names people,
     and this seat is aggregate-only) rather than by a board rule restating it. */
  state: {
    scope: "state",
    title: "State Command",
    subtitle: "State-wide priorities, outcomes and readiness. Aggregate only.",
    order: [
      "kpi-incidents", "kpi-mom", "kpi-anomalies", "kpi-new-firs",
      "kpi-open-cases", "kpi-workload",
      "kpi-critical-alerts", "kpi-open-alerts", "kpi-hotspots",
      "kpi-chargesheet", "kpi-days-to-chargesheet", "kpi-disposal",
      "kpi-conviction", "kpi-prosecution-rate",
      "kpi-overdue", "kpi-ageing-180", "kpi-imbalance",
      "kpi-stations", "kpi-officers", "kpi-officer-p90", "kpi-heavy-load",
      "kpi-predicted", "kpi-wape", "kpi-coverage", "kpi-abstention",
      "kpi-data-age", "kpi-data-quality", "kpi-jurisdiction", "kpi-suppressed",
      "kpi-districts", "kpi-conformance",
      "kpi-patterns", "kpi-groups", "kpi-tasks",
    ],
    widgets: [
      TREND, FORECAST,
      { id: "range-league", label: "Range comparison", w: 6, h: 7 },
      { id: "district-league", label: "District comparison", w: 6, h: 7 },
      HOTSPOT_MAP, STATUS_PIPELINE, ATTENTION,
      SOCIO_BAND,
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
      "kpi-conviction", "kpi-prosecution-rate",
      "kpi-overdue", "kpi-ageing-180", "kpi-imbalance",
      "kpi-stations", "kpi-officers", "kpi-officer-p90", "kpi-heavy-load",
      "kpi-predicted", "kpi-wape", "kpi-coverage", "kpi-abstention",
      "kpi-data-age", "kpi-data-quality", "kpi-jurisdiction",
      "kpi-suppressed", "kpi-districts",
      "kpi-patterns", "kpi-groups", "kpi-tasks",
      "kpi-flagged-txn", "kpi-money-trails", "kpi-linked-accounts",
      "kpi-traffic-incidents", "kpi-accident-hotspots",
    ],
    /* kpi-poi needs no omission here: the registry excludes it from every
       aggregate-only scope, so stating it again on this board would be the same
       rule written twice, drifting the moment one of the two changed. */
    widgets: [
      TREND,
      { id: "head-breakdown", label: "By crime head", w: 4, h: 7 },
      { id: "district-league", label: "District comparison", w: 6, h: 7 },
      HOTSPOT_MAP, FORECAST, STATUS_PIPELINE, ATTENTION,
      SOCIO_BAND,
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
      "kpi-prosecution-rate",
      "kpi-predicted", "kpi-data-age", "kpi-data-quality", "kpi-jurisdiction",
      "kpi-suppressed", "kpi-districts",
      "kpi-patterns", "kpi-groups", "kpi-poi", "kpi-tasks",
    ],
    widgets: [
      { id: "district-league", label: "District comparison", w: 8, h: 7 },
      FORECAST, TREND, HOTSPOT_MAP, STATUS_PIPELINE, ATTENTION,
      SOCIO_BAND,
    ],
  },

  /* --- SP: one district, all its stations ------------------------------- */
  district: {
    scope: "district",
    title: "District Command",
    subtitle: "District workload, station performance and approvals.",
    order: DISTRICT_ORDER,
    widgets: DISTRICT_WIDGETS,
  },

  /* --- CP: same job, city command -------------------------------------- */
  commissionerate: {
    scope: "commissionerate",
    title: "City Commissionerate",
    subtitle: "City workload, station performance and approvals.",
    order: DISTRICT_ORDER,
    widgets: DISTRICT_WIDGETS,
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
      "kpi-prosecution-rate":
        "Same small-denominator problem as the conviction rate, and only meaningful beside it. Both live on the district board.",
    },
    /* The trend chart is new here, and it is new because it can now be TRUE here:
       /geo/trends took only a district, so a station board would have plotted its
       whole district's series beside station-confined KPI cards — one board
       reporting two jurisdictions. The endpoint now accepts the seat's unit, so the
       series is the station's own.

       The socio-economic band is included with its grain stated rather than left
       off. There is no socio-economic or population data below district grain, so
       these are the DISTRICT's correlations; an SHO reading their station's numbers
       against the district's economic context is the point, and the band's own
       read-out says which geography it is computed over. */
    widgets: [
      STATUS_PIPELINE, TREND,
      { id: "officer-load", label: "Officer load", w: 6, h: 6 },
      { id: "station-jurisdiction", label: "Station jurisdiction", w: 6, h: 7 },
      ATTENTION,
      SOCIO_BAND,
    ],
  },

  /* --- IO: my cases ----------------------------------------------------
     An IO's board is the one board that is scoped to a PERSON rather than to a
     geography, which is exactly why it has to name the geography it sits inside.
     `my-posting` leads the board for that reason: the seat's district and station,
     stated, so the officer can see which jurisdiction every other figure on the
     board is confined to instead of inferring it from a map.

     The socio-economic band is deliberately absent, and this is the one board it is
     absent from. It expands to eleven tiles of district-grain correlation across
     the state — context for whoever sets district priorities, and eleven tiles of
     noise above an officer's own caseload. The station board above carries it. */
  assigned_case: {
    scope: "assigned_case",
    title: "My Case Work",
    subtitle: "Your assigned cases, evidence and leads — within your posted station.",
    order: [
      "kpi-my-open", "kpi-my-new", "kpi-my-alerts", "kpi-overdue",
      "kpi-days-to-chargesheet", "kpi-ageing-180",
      "kpi-next-hearing", "kpi-evidence-pending", "kpi-hotspots",
      "kpi-poi", "kpi-tasks", "kpi-data-age",
    ],
    widgets: [
      { id: "my-posting", label: "My posting", w: 4, h: 6 },
      { id: "my-caseload", label: "My caseload", w: 4, h: 6 },
      ATTENTION,
      TREND,
      { id: "case-timeline", label: "Recent activity", w: 6, h: 6 },
      { id: "my-jurisdiction", label: "My jurisdiction", w: 6, h: 7 },
    ],
  },

  /* --- Admin -----------------------------------------------------------
     EVERY board's cards and every panel, because a platform seat is the one seat
     for which all of them are both defined and readable: `derive_scope` gives it no
     geographic narrowing (like state) and it is not aggregate-only (unlike state
     and wing). See the platform rule in registry.ts `kpiApplies`.

     Previously four platform counters and two admin panels. That left an
     administrator able to configure the visibility of every card in the console
     while never being able to see what any of them rendered — which is also the
     only way to notice that one of them is broken.

     The platform tier leads, then the operational bands, so the board opens on what
     is uniquely this seat's job before it becomes a state-wide read-out. */
  platform: {
    scope: "platform",
    title: "Platform Administration",
    subtitle:
      "Seats, roles, UI visibility, models and data integrity — over the whole force, with every board's own figures.",
    order: [
      "kpi-active-seats", "kpi-imports", "kpi-models", "kpi-ui-overrides",
      "kpi-conformance", "kpi-data-age", "kpi-data-quality", "kpi-jurisdiction",
      "kpi-incidents", "kpi-mom", "kpi-anomalies", "kpi-new-firs",
      "kpi-open-cases", "kpi-workload",
      "kpi-critical-alerts", "kpi-open-alerts", "kpi-hotspots",
      "kpi-chargesheet", "kpi-days-to-chargesheet", "kpi-disposal",
      "kpi-conviction", "kpi-prosecution-rate",
      "kpi-overdue", "kpi-ageing-180", "kpi-imbalance",
      "kpi-stations", "kpi-officers", "kpi-officer-p90", "kpi-heavy-load",
      "kpi-predicted", "kpi-wape", "kpi-coverage", "kpi-abstention",
      "kpi-suppressed", "kpi-districts",
      "kpi-patterns", "kpi-groups", "kpi-poi", "kpi-tasks",
      "kpi-flagged-txn", "kpi-money-trails", "kpi-linked-accounts",
      "kpi-traffic-incidents", "kpi-accident-hotspots",
      // Last on purpose. Both are STATION_DOWN cards that a platform seat reads
      // force-wide, and `kpi-evidence-pending` is declared pending in the registry —
      // an admin board is the right place for an unserved card to be visible rather
      // than quietly dropped, but not the top of it.
      "kpi-next-hearing", "kpi-evidence-pending",
    ],
    widgets: [
      { id: "seat-directory", label: "Seat directory", w: 8, h: 7 },
      { id: "role-matrix", label: "Role and UI visibility", w: 4, h: 7 },
      TREND, FORECAST,
      { id: "range-league", label: "Range comparison", w: 6, h: 7 },
      { id: "district-league", label: "District comparison", w: 6, h: 7 },
      HOTSPOT_MAP, STATUS_PIPELINE, ATTENTION,
      SOCIO_BAND,
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
