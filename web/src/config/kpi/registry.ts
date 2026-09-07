import type { ScopeType } from "@/config/roles";

/* ============================================================================
   The KPI card catalogue.

   One entry per metric, declaring which scope types it is MEANINGFUL at. Boards
   are then assembled by selecting from this catalogue (see roleBoards.ts), so
   "which role gets which card" is data you can test rather than five hand-written
   board components that drifted apart.

   THREE STATES, NOT TWO. A card can be:
     included   - listed for that seat
     excluded   - meaningful, but not this seat's job (`omit`)
     undefined  - NOT meaningful at that scope, and must be absent
   The third is the one that matters. Station load imbalance across a single
   station is not 1.0, it is undefined; anomaly detection on one station's monthly
   series is noise, not signal; there is no station-level forecast because the
   forecast grain is the district. Showing a zero would be a lie, so `scopes` lists
   only where the number means something.
   ========================================================================== */

export type KpiBand =
  | "volume"        // A - volume and pulse
  | "alerts"        // B - alerts and urgency
  | "outcomes"      // C - outcomes and accountability
  | "forecast"      // D - forecast and model trust
  | "integrity"     // E - data integrity
  | "patterns"      // F - patterns and networks
  | "financial"     // G - cyber and financial (wing-gated)
  | "traffic"       // H - traffic (wing-gated)
  | "casework"      // I - station and IO case work
  | "platform";     // J - admin

/** How far the active geography selection actually reaches a card's data.
 *  Mirrors `districtSupport` in stores/useScopeStore.ts. A card must never imply
 *  a filter that is not applied. */
export type ScopeReach = "server" | "client" | "focus" | "none";

export interface KpiSpec {
  id: string;
  label: string;
  band: KpiBand;
  /** Scope types where this metric is meaningful. Absent = do not render. */
  scopes: ScopeType[];
  /** Wing codes this card is restricted to, when wing-scoped. Absent = all wings. */
  wings?: string[];
  /** Endpoint that feeds it, for provenance and the "missing endpoint" audit. */
  source: string;
  /** How far the geography selector reaches. */
  reach: ScopeReach;
  unit?: "%" | "d" | "x";
  /** True when a smaller number is the better outcome. Defaults to true. */
  improveWhenDown?: boolean;
  /** Shown in the card's info affordance. States what the number is and is not. */
  hint: string;
  /** Set when no endpoint can serve this yet: renders an honest pending state
   *  instead of being quietly dropped. */
  pending?: boolean;
  pendingNote?: string;
}

const ALL_GEO: ScopeType[] = [
  "state", "wing", "range", "district", "commissionerate", "station",
];
const COMMAND: ScopeType[] = ["state", "wing", "range", "district", "commissionerate"];
const DISTRICT_UP: ScopeType[] = ["state", "wing", "range", "district", "commissionerate"];
const STATION_DOWN: ScopeType[] = ["station", "assigned_case"];

export const KPI_REGISTRY: KpiSpec[] = [
  /* ===== Band A - volume and pulse ====================================== */
  {
    id: "kpi-incidents", label: "Incidents (window)", band: "volume",
    scopes: ALL_GEO, source: "/geo/trends", reach: "server",
    hint: "Total recorded incidents for the selected window. The delta compares against the SAME PERIOD LAST YEAR, so seasonal swings do not read as trend.",
  },
  {
    id: "kpi-mom", label: "Month-on-month change", band: "volume",
    scopes: ALL_GEO, source: "/geo/trends", reach: "server", unit: "%",
    hint: "Change against the previous period in the series. Shown as a value rather than a delta because it IS a delta; the year-on-year comparison sits on the incidents card.",
  },
  {
    id: "kpi-anomalies", label: "Anomalous periods", band: "volume",
    // Not station-level: one station's monthly series is too sparse for a rolling
    // anomaly band to distinguish signal from noise.
    scopes: DISTRICT_UP, source: "/geo/trends", reach: "server",
    hint: "Periods whose count fell outside the rolling anomaly band - the months that broke trend. A count of periods, not of crimes.",
  },
  {
    id: "kpi-new-firs", label: "New FIRs (90d)", band: "volume",
    scopes: ALL_GEO, source: "/performance/overview", reach: "server",
    hint: "Cases registered in the last 90 days. The accountability window is fixed at 90 days so throughput, ageing and intake share one denominator.",
  },
  {
    id: "kpi-open-cases", label: "Open cases", band: "volume",
    scopes: ALL_GEO, source: "/cases/caseload", reach: "server",
    hint: "Cases not yet disposed or closed, across every stage of the FIR lifecycle. A present-state snapshot, so it ignores the time window.",
  },
  {
    id: "kpi-workload", label: "Active workload", band: "volume",
    scopes: ALL_GEO, source: "/performance/overview", reach: "server",
    hint: "Open cases carried as live investigative work - the subset that is somebody's active file.",
  },
  {
    id: "kpi-my-open", label: "My open cases", band: "volume",
    scopes: ["assigned_case"], source: "/cases/caseload", reach: "server",
    hint: "Cases assigned to you and not yet disposed.",
  },
  {
    id: "kpi-my-new", label: "New assignments", band: "volume",
    scopes: ["assigned_case"], source: "/cases/caseload", reach: "server",
    hint: "Cases assigned to you within the current window.",
  },

  /* ===== Band B - alerts and urgency ==================================== */
  {
    id: "kpi-critical-alerts", label: "Critical alerts", band: "alerts",
    scopes: ALL_GEO, source: "/geo/alerts", reach: "client",
    hint: "Live early-warning alerts at CRITICAL severity only - the escalate-now queue, not the whole alert list. A live queue, so it ignores the time window.",
  },
  {
    id: "kpi-open-alerts", label: "Open alerts", band: "alerts",
    // Now includes state. Total unresolved alert volume beside the critical count
    // is what tells a state seat whether the critical queue is the whole problem or
    // the tip of it, and it is a queue depth rather than a case-level disclosure.
    scopes: ["state", "wing", "range", "district", "commissionerate", "station"],
    source: "/geo/alerts", reach: "client",
    hint: "All unresolved alerts at every severity. Read beside the critical count: the gap between them is the queue that is waiting rather than escalating.",
  },
  {
    id: "kpi-my-alerts", label: "My alerts", band: "alerts",
    scopes: ["assigned_case"], source: "/geo/alerts", reach: "client",
    hint: "Alerts raised on cases or locations assigned to you.",
  },
  {
    id: "kpi-hotspots", label: "Hotspots", band: "alerts",
    scopes: [...ALL_GEO, "assigned_case"], source: "/geo/hotspots", reach: "client",
    hint: "Spatial clusters detected for the window. Area-level patterns only: a hotspot describes a place, never a person.",
  },

  /* ===== Band C - outcomes and accountability =========================== */
  {
    id: "kpi-chargesheet", label: "Chargesheet throughput", band: "outcomes",
    scopes: ALL_GEO, source: "/performance/overview", reach: "server",
    unit: "%", improveWhenDown: false,
    hint: "Chargesheets filed divided by new cases registered in the same window - a ratio between two different cohorts, so a throughput rate rather than a per-case conversion rate. Higher is better.",
  },
  {
    id: "kpi-days-to-chargesheet", label: "Median days to chargesheet", band: "outcomes",
    scopes: [...ALL_GEO, "assigned_case"], source: "/performance/overview",
    reach: "server", unit: "d",
    hint: "Median days from registration to chargesheet FILING, not to final court disposal.",
  },
  {
    id: "kpi-disposal", label: "Disposal rate", band: "outcomes",
    scopes: ALL_GEO, source: "/performance/overview", reach: "server",
    unit: "%", improveWhenDown: false,
    hint: "Cases disposed or closed as a share of every case on record. Cumulative rather than windowed, so it moves slowly.",
  },
  {
    id: "kpi-conviction", label: "Conviction rate", band: "outcomes",
    scopes: ALL_GEO, wings: ["CTS", "CID"], source: "/outcomes/overview",
    reach: "server", unit: "%", improveWhenDown: false,
    hint: "Convictions as a share of cases that reached a VERDICT. The denominator is convictions plus acquittals only — a B-report (undetected) or C-report (false complaint) is a decision not to prosecute, not a lost prosecution.",
  },
  {
    id: "kpi-prosecution-rate", label: "Prosecution rate", band: "outcomes",
    scopes: ALL_GEO, wings: ["CTS", "CID"], source: "/outcomes/overview",
    reach: "server", unit: "%", improveWhenDown: false,
    hint: "Cases reaching a verdict as a share of all finally-disposed cases. Only meaningful beside the conviction rate: a high rate on very few prosecutions is a different picture from the same rate on many.",
  },
  {
    id: "kpi-overdue", label: "Overdue reviews", band: "outcomes",
    scopes: [...ALL_GEO, "assigned_case"], source: "/performance/overview", reach: "server",
    hint: "Open cases past the review threshold. A backlog measure, so a rising number is the warning.",
  },
  {
    id: "kpi-ageing-180", label: "Open over 180 days", band: "outcomes",
    // Now includes state. The oldest ageing bucket is a backlog measure and it
    // sums cleanly across the force, so a state seat both can and should carry it;
    // its absence was an oversight rather than a statement about the metric.
    scopes: ["state", "wing", "range", "district", "commissionerate", "station",
             "assigned_case"],
    source: "/performance/overview", reach: "server",
    hint: "Open cases older than 180 days - the oldest ageing bucket.",
  },
  {
    id: "kpi-imbalance", label: "Station load imbalance", band: "outcomes",
    // Undefined at station scope: the busiest-over-median ratio across a single
    // station is not 1.0, it has no meaning.
    scopes: COMMAND, source: "/performance/overview", reach: "server", unit: "x",
    hint: "Busiest station's open caseload divided by the median station's. 1x would be perfectly even load; higher means pressure is concentrated. Comparative only - never a punitive ranking.",
  },
  {
    id: "kpi-stations", label: "Stations in scope", band: "outcomes",
    scopes: COMMAND, source: "/performance/overview", reach: "server",
    hint: "Police stations included in the accountability figures - the denominator behind the load and throughput cards.",
  },
  {
    id: "kpi-officers", label: "Officers in scope", band: "outcomes",
    scopes: ALL_GEO, source: "/performance/overview", reach: "server",
    hint: "Officers carrying cases within this seat's scope.",
  },
  {
    id: "kpi-officer-p90", label: "P90 open cases per officer", band: "outcomes",
    // Now includes state and wing. A percentile is a property of a DISTRIBUTION, so
    // it is better defined the more officers it is taken over, not worse — the
    // state-wide p90 is the most robust reading of it on any board. It is also an
    // aggregate over officers rather than a per-officer figure, so it carries no
    // case-level disclosure and is safe for the two aggregate-only seats.
    scopes: ["state", "wing", "range", "district", "commissionerate", "station"],
    source: "/performance/overview", reach: "server",
    hint: "The 90th-percentile officer's open caseload. An aggregate distribution, never an individual ranking.",
  },
  {
    id: "kpi-heavy-load", label: "Heavy-load officers", band: "outcomes",
    // Same reasoning as the p90: a COUNT of officers over a threshold names none
    // of them, so it is an aggregate the state and wing boards can carry.
    scopes: ["state", "wing", "range", "district", "commissionerate", "station"],
    source: "/performance/overview", reach: "server",
    hint: "Officers holding more open cases than the heavy-load threshold.",
  },

  /* ===== Band D - forecast and model trust ============================== */
  {
    id: "kpi-predicted", label: "Predicted next period", band: "forecast",
    // Forecast grain is the district, so there is no station-level prediction.
    scopes: COMMAND, source: "/forecast/map", reach: "client",
    hint: "Sum of the fused district forecasts for the next horizon. Read-only - opening a board never triggers a forecast run.",
  },
  {
    id: "kpi-wape", label: "Forecast error (WAPE)", band: "forecast",
    scopes: ["state", "wing"], wings: ["CTS"], source: "/forecast/backtest",
    reach: "none", unit: "%",
    hint: "Weighted absolute percentage error from the rolling-origin backtest, scored on held-out district-months. Lower is better. State-wide: model accuracy is a property of the model, not of a district.",
  },
  {
    id: "kpi-coverage", label: "80% interval coverage", band: "forecast",
    scopes: ["state", "wing"], wings: ["CTS"], source: "/forecast/backtest",
    reach: "none", unit: "%", improveWhenDown: false,
    hint: "Share of held-out actuals inside the forecast's 80% band. 80% is the target, not a maximum: well below means overconfident intervals, well above means they are too wide to act on.",
  },
  {
    id: "kpi-abstention", label: "Forecast abstention", band: "forecast",
    scopes: ["state", "wing"], wings: ["CTS"], source: "/forecast/backtest",
    reach: "none", unit: "%",
    hint: "Share of candidate cells the forecaster declined to score for want of signal. Abstention is deliberate: the model says \"I don't know\" instead of guessing.",
  },

  /* ===== Band E - data integrity ======================================== */
  {
    id: "kpi-data-age", label: "Case-data age", band: "integrity",
    scopes: [...ALL_GEO, "assigned_case", "platform"],
    source: "/performance/overview", reach: "server", unit: "d",
    hint: "Age of the most recent case data behind the accountability figures. Windows are relative to that as-of date, not to today.",
  },
  {
    id: "kpi-data-quality", label: "Data-quality issues", band: "integrity",
    scopes: ["state", "wing", "range", "district", "commissionerate", "station", "platform"],
    wings: ["CTS"], source: "/intake/quality/issues", reach: "none",
    hint: "Records the ingestion and containment checks flagged and STAGED for review - nothing is silently corrected. State-wide: staged records often have no district yet, which is frequently the defect being flagged.",
  },
  {
    id: "kpi-jurisdiction", label: "Jurisdiction issues", band: "integrity",
    scopes: ["state", "wing", "range", "district", "commissionerate", "station", "platform"],
    wings: ["CTS"], source: "/geo/jurisdiction/freshness", reach: "none",
    hint: "Open containment failures: cases whose incident point falls outside the district they are assigned to. Staged for reviewed, audited reassignment - never moved automatically.",
  },
  {
    id: "kpi-suppressed", label: "Cells suppressed", band: "integrity",
    // Wherever the socio-economic band renders, this card explains the gaps in it.
    // It was declared at state and wing only while the band itself was on the range,
    // district and commissionerate boards too, so those three carried the charts
    // without the one card that says why a district is missing from them.
    scopes: ["state", "wing", "range", "district", "commissionerate"],
    source: "/analytics/socioeconomic", reach: "none",
    hint: "Small-count cells hidden for k-anonymity - privacy by design, not missing data.",
  },
  {
    id: "kpi-districts", label: "Districts analysed", band: "integrity",
    // Meaningless below range: a single district cannot be a district count.
    scopes: ["state", "wing", "range"], source: "/analytics/socioeconomic", reach: "none",
    hint: "Districts with enough volume to support district-level correlation. Districts below the k-anonymity threshold are excluded rather than estimated.",
  },
  {
    id: "kpi-conformance", label: "Contract conformance", band: "integrity",
    scopes: ["state", "platform"], source: "/explain/contract", reach: "none",
    unit: "%", improveWhenDown: false,
    hint: "Share of API routes that declare and honour a typed response model. The board auditing whether its own numbers arrive under a checked contract.",
  },

  /* ===== Band F - patterns and networks ================================= */
  {
    id: "kpi-patterns", label: "Active patterns", band: "patterns",
    scopes: ALL_GEO, source: "/analytics/patterns", reach: "none",
    hint: "Active crime-pattern detections - serial, modus operandi, temporal, spatial, network and repeat-offender. The service returns only active patterns and caps the list, so this is a floor rather than an exhaustive count.",
  },
  {
    id: "kpi-groups", label: "Organised groups", band: "patterns",
    scopes: ["state", "wing", "range", "district", "commissionerate"],
    wings: ["INT", "ISC", "CID"], source: "/graph/communities/list", reach: "none",
    hint: "Detected network communities containing at least one known gang member. An aggregate count only - no names, no profiles.",
  },
  {
    id: "kpi-poi", label: "Persons of interest", band: "patterns",
    // Absent for state and wing: this is the one Band F card that names people,
    // so it stays off the aggregate-only boards.
    scopes: ["range", "district", "commissionerate", "station", "assigned_case"],
    wings: ["INT", "ISC", "CID"], source: "/graph/centrality", reach: "none",
    /* The hint states the cap because the number IS the cap. /graph/centrality
       answers with a `LIMIT top` ranked list and carries no population total, so
       this card reports the size of the shortlist it asked for and not how many
       persons of interest exist. Said out loud rather than left to look like a
       measurement that happens never to move. */
    hint: "Size of the ranked shortlist this board requests from graph centrality — a FIXED shortlist depth, not a count of how many persons of interest exist, because the service returns a top-N ranking with no population total. Decision support for prioritising enquiry, never an accusation.",
  },
  {
    id: "kpi-tasks", label: "Open tasks", band: "patterns",
    scopes: [...ALL_GEO, "assigned_case", "platform"],
    source: "/notifications/tasks", reach: "none",
    hint: "Work tasks still open. Scoped by status and actor rather than by geography.",
  },

  /* ===== Band G - cyber and financial (wing-gated) ====================== */
  {
    id: "kpi-flagged-txn", label: "Flagged transactions", band: "financial",
    scopes: ["wing"], wings: ["ISC", "CID"], source: "/money/flagged", reach: "none",
    hint: "Transactions flagged for structuring, mule behaviour or rapid fan-out, with the reason recorded.",
  },
  {
    id: "kpi-money-trails", label: "Circular flows", band: "financial",
    scopes: ["wing"], wings: ["ISC", "CID"], source: "/money/unified", reach: "none",
    hint: "Detected circular or high-risk money movements across linked accounts.",
  },
  {
    id: "kpi-linked-accounts", label: "Resolved account links", band: "financial",
    scopes: ["wing"], wings: ["ISC"], source: "/identity/stats", reach: "none",
    hint: "Account-to-entity links established by identity resolution.",
  },

  /* ===== Band H - traffic (wing-gated) ================================== */
  {
    id: "kpi-traffic-incidents", label: "Traffic incidents", band: "traffic",
    scopes: ["wing"], wings: ["TRF"], source: "/geo/trends", reach: "server",
    hint: "Incidents under the Traffic Offences head for the window.",
  },
  {
    id: "kpi-accident-hotspots", label: "Accident hotspots", band: "traffic",
    scopes: ["wing"], wings: ["TRF"], source: "/geo/hotspots", reach: "client",
    hint: "Spatial clusters of traffic incidents - corridor-level concentration.",
  },

  /* ===== Band I - case work ============================================= */
  {
    id: "kpi-review-queue", label: "Review queue depth", band: "casework",
    scopes: ["station"], source: "/intake", reach: "server",
    hint: "Submitted FIR drafts awaiting your approval, return or rejection.",
  },
  {
    id: "kpi-next-hearing", label: "Next court date", band: "casework",
    scopes: STATION_DOWN, source: "/casework/hearings/next", reach: "server", unit: "d",
    /* Was `pending` because no hearing in the corpus was scheduled-but-not-yet-heard:
       CourtEvent.ScheduledAt was NULL on all 64,391 rows and every event carried an
       OccurredAt. Migration 036 and datagen/court_outcomes.py now write the
       adjourned-to date for the 10,322 cases awaiting trial, so the card measures
       something real. */
    hint:
      "Days until the soonest scheduled hearing in your scope, counted from the record's as-of date rather than today — the corpus ends before the current date.",
  },
  {
    id: "kpi-evidence-pending", label: "Evidence pending", band: "casework",
    scopes: STATION_DOWN, source: "/casework", reach: "server",
    hint: "Evidence items awaiting collection, lab submission or result.",
    /* Explicitly pending. The casework service exposes seizures and lab results
       PER CASE (/casework/cases/{id}/seizures, /casework/cases/{id}/lab-results)
       and has no scope-wide aggregate, so counting this would mean fanning out one
       request per open case from the browser. Declared here so the card carries a
       reason a reader can act on, instead of falling through to the resolver's
       generic "no data binding" note, which is written for whoever maintains the
       registry rather than for the officer looking at the board. */
    pending: true,
    pendingNote:
      "Needs a scope-wide aggregate. The casework service reports seizures and lab results per case, with no station or caseload total, so this card is left explicitly pending rather than fanning out one request per open case.",
  },

  /* ===== Band J - platform ============================================== */
  {
    id: "kpi-active-seats", label: "Active seats", band: "platform",
    scopes: ["platform"], source: "/org/seats", reach: "none",
    improveWhenDown: false,
    hint: "Provisioned, active login seats across the force.",
  },
  {
    id: "kpi-imports", label: "Pending imports", band: "platform",
    scopes: ["platform"], source: "/admin/queues", reach: "none",
    hint: "Structured imports staged and awaiting commit or rollback.",
  },
  {
    id: "kpi-models", label: "Models in registry", band: "platform",
    scopes: ["platform"], source: "/admin", reach: "none", improveWhenDown: false,
    hint: "Registered model versions, including retired ones.",
  },
  {
    id: "kpi-ui-overrides", label: "UI overrides", band: "platform",
    scopes: ["platform"], source: "/admin/ui-visibility", reach: "none",
    hint: "Per-role UI visibility overrides currently diverging from the registry defaults. Zero means every role sees its default surface.",
  },
];

/** Fast lookup by id. */
export const KPI_BY_ID: Record<string, KpiSpec> = Object.fromEntries(
  KPI_REGISTRY.map((k) => [k.id, k]),
);

/* --------------------------------------------------------------------------
   The platform seat.

   A platform administrator reaches every card, and that is a property of the
   seat rather than a convenience: `derive_scope` in services/ml/app/org/scope.py
   gives a platform seat NO geographic narrowing (identically to state), and
   `isAggregateOnly` covers state and wing only — so a platform seat is the one
   seat for which every measure here is both defined and readable.

   Expressed as a rule instead of by adding "platform" to all ~50 entries, which
   would say the same thing fifty times and drift the moment someone adds the
   fifty-first. Without it the admin board carried four platform counters and
   nothing else: an administrator could configure every board in the console and
   never see what any of them actually rendered.

   SEAT-RELATIVE CARDS ARE THE EXCEPTION. "My open cases", "My new assignments",
   "My alerts" and the station review queue are defined relative to a personal
   caseload or an approval inbox that a platform seat does not have. For those the
   honest answer is absence, not a structural zero — an admin board reporting "0
   open cases assigned to you" is reporting on nothing.
   -------------------------------------------------------------------------- */
const SEAT_RELATIVE = new Set<string>([
  "kpi-my-open", "kpi-my-new", "kpi-my-alerts", "kpi-review-queue",
]);

/** True when a card is meaningful for this seat.
 *
 *  Three independent gates: the scope type must be one the metric is defined at
 *  (or the seat must be the platform seat, which reaches all of them), and — for a
 *  wing seat — the card must not be restricted to other wings. */
export function kpiApplies(
  spec: KpiSpec,
  scope: ScopeType,
  wingCode?: string | null,
): boolean {
  if (scope === "platform") {
    return spec.scopes.includes("platform") || !SEAT_RELATIVE.has(spec.id);
  }
  if (!spec.scopes.includes(scope)) return false;
  if (spec.wings && spec.wings.length > 0) {
    // A wing restriction only bites on a wing seat. A DGP still sees the
    // conviction-rate card; it is only the ADGP wings other than CTS/CID that do not.
    if (scope === "wing") return !!wingCode && spec.wings.includes(wingCode);
  }
  return true;
}

/** Every card meaningful for a seat, in registry (band) order. */
export function kpisForScope(scope: ScopeType, wingCode?: string | null): KpiSpec[] {
  return KPI_REGISTRY.filter((k) => kpiApplies(k, scope, wingCode));
}
