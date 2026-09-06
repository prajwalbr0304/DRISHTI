import {
  Activity,
  BarChart3,
  Cctv,
  FilePlus2,
  FolderKanban,
  Gauge,
  LayoutDashboard,
  LifeBuoy,
  ListChecks,
  Map,
  MessageSquareText,
  ScanFace,
  Share2,
  ShieldAlert,
  ShieldCheck,
  Truck,
  Users,
  Workflow,
  type LucideIcon,
} from "lucide-react";
import type { UserRole } from "@/config/roles";

/** The two top-level workspaces (context switcher). */
export type WorkspaceContext = "crime" | "emergency";

/* ============================================================================
   The sidebar destinations (doc 01 §3). Each maps to a Wave-B capability.

   ACCESS MODEL. Two filters, and they answer different questions.

   `roles` is a static allow-list and is still unused: every command role reaches
   every destination, and `adminOnly` passes for all roles because each RoleDef has
   `admin: true`. Re-add allow-lists here — with ids from config/roles.ts — when
   per-role narrowing returns.

   `requiresCaseLevel` is the filter that IS live, and it keys off the seat's SCOPE
   rather than its role, because a role cannot express it: an ADGP and a DIG share
   `senior_command`, and only the ADGP is aggregate-only. It mirrors the server's
   `require_case_level` guard, so the sidebar stops offering pages that would answer
   403.

   Neither is an authorization boundary. Both decide what is RENDERED; the server
   re-derives what may be read on every request.
   ========================================================================== */

export interface Destination {
  id: string;
  path: string;
  label: string;
  /** icon-rail label / short form */
  short: string;
  icon: LucideIcon;
  description: string;
  /** side-nav group heading (AWS console side navigation sections). Consecutive
   *  destinations sharing a section render under one heading, separated from the
   *  next group by a divider. */
  section: string;
  /** only super_admin sees this destination */
  adminOnly?: boolean;
  /** optional explicit role allow-list (future scoping) */
  roles?: UserRole[];
  /** Needs access to INDIVIDUAL records — a case file, a person, a face, a board.
   *
   *  Hidden from aggregate-only seats (state and wing scope), which the server
   *  refuses at `require_case_level`: a DGP is accountable for the whole force and
   *  has no case-level remit, so leaving these in the sidebar only offers a page
   *  that answers 403.
   *
   *  Deliberately NOT expressed through `roles`. A role cannot decide this: an
   *  ADGP and a DIG are both `senior_command`, and the ADGP is aggregate-only
   *  while the DIG commands real districts and reads cases. Scope decides. */
  requiresCaseLevel?: boolean;
  /** ⌘K keywords */
  keywords?: string[];
  /** which workspace this destination belongs to (default "crime") */
  context?: WorkspaceContext;
}

export const DESTINATIONS: Destination[] = [
  {
    id: "command",
    section: "Overview",
    path: "/command",
    label: "Command Center",
    short: "Home",
    icon: LayoutDashboard,
    description: "Live operational overview across the state.",
    keywords: ["home", "overview", "dashboard", "kpi"],
  },
  {
    id: "cases",
    section: "Case work",
    path: "/cases",
    label: "Cases",
    short: "Cases",
    icon: FolderKanban,
    description: "Case decision-support: summaries, similar cases, leads.",
    keywords: ["fir", "investigation", "summary", "leads", "similar"],
    // Individual case files. /cases enforces require_case_level server-side.
    requiresCaseLevel: true,
  },
  {
    id: "intake",
    section: "Case work",
    path: "/intake",
    label: "Intake",
    short: "Intake",
    icon: FilePlus2,
    description: "Register FIRs/cases: guided intake, bulk import and supervisory review.",
    keywords: ["fir", "intake", "new case", "register", "draft", "import", "review", "inbox"],
    // Registering an FIR is station work. A state or wing seat has no station.
    requiresCaseLevel: true,
  },
  {
    id: "people",
    section: "Case work",
    path: "/people",
    label: "People & Entities",
    short: "People",
    icon: Users,
    description: "Persons, gangs, vehicles, phones and accounts — with risk.",
    keywords: ["person", "entity", "offender", "gang", "vehicle", "phone", "risk"],
    // Names individuals and carries PII, which is the aggregate-only boundary.
    requiresCaseLevel: true,
  },
  {
    id: "face-search",
    section: "Case work",
    path: "/people/face",
    label: "Face Recognition",
    short: "Face",
    icon: ScanFace,
    description: "Photograph or upload a face and check it against person records.",
    keywords: ["face", "facial", "recognition", "photo", "identify", "biometric",
      "mugshot", "camera", "scan", "suspect", "match"],
    // Biometric identification of a named individual � the most case-level surface
    // in the product.
    requiresCaseLevel: true,
  },
  {
    id: "network",
    section: "Analysis",
    path: "/network",
    label: "Network Analysis",
    short: "Network",
    icon: Share2,
    description: "Link analysis: communities, hidden associations, money trail, paths.",
    keywords: ["graph", "network", "association", "community", "money", "path", "link"],
    // Link analysis resolves to named people; the aggregate boards deliberately
    // omit the equivalent KPI card for the same reason.
    requiresCaseLevel: true,
  },
  {
    id: "board",
    section: "Analysis",
    path: "/board",
    label: "Investigation Board",
    short: "Board",
    icon: Workflow,
    description: "Assemble live objects on a shared canvas; separate evidence from hypotheses.",
    keywords: ["board", "canvas", "link", "hypothesis", "evidence", "palantir", "corkboard", "investigation"],
    // A board is assembled from individual records.
    requiresCaseLevel: true,
  },
  {
    id: "map",
    section: "Analysis",
    path: "/map",
    label: "Map & Hotspots",
    short: "Map",
    icon: Map,
    description: "Geospatial hotspots, forecasts and red-zone alerts.",
    keywords: ["geo", "hotspot", "heatmap", "spatial", "forecast", "alert"],
  },
  {
    id: "watch",
    section: "Analysis",
    path: "/watch",
    label: "Live Watch Wall",
    short: "Watch",
    icon: Cctv,
    description:
      "CCTV video analytics: review proposed incident alerts and dispatch the nearest responder.",
    keywords: ["cctv", "camera", "video", "surveillance", "fight", "road rage",
               "traffic block", "crowd", "alert", "dispatch", "live", "feed", "wall"],
  },
  {
    id: "analytics",
    section: "Analysis",
    path: "/analytics",
    label: "Analytics & Forecasting",
    short: "Analytics",
    icon: BarChart3,
    description: "Trends, socio-economic correlations, forecasts and model explainability.",
    keywords: ["socioeconomic", "correlation", "explain", "trends", "forecast", "policy"],
  },
  {
    id: "ask",
    section: "Assistant",
    path: "/ask",
    label: "Ask DRISHTI",
    short: "Ask",
    icon: MessageSquareText,
    description: "Conversational, cited answers grounded in the data.",
    keywords: ["chat", "ask", "nl", "query", "voice", "question"],
  },
  {
    id: "support",
    section: "Administration",
    path: "/support",
    label: "Support",
    short: "Support",
    icon: LifeBuoy,
    description: "Raise and track cases for technical issues, data problems, access and feature requests.",
    keywords: ["support", "help", "ticket", "case", "issue", "bug", "problem", "contact", "feedback"],
  },
  {
    id: "admin",
    section: "Administration",
    path: "/admin",
    label: "Admin",
    short: "Admin",
    icon: ShieldCheck,
    description: "Model registry, contract audit and governance.",
    adminOnly: true,
    keywords: ["model", "registry", "governance", "audit", "contract"],
  },

  /* --- Emergency Response context (Prompt 17) --------------------------- */
  {
    id: "er-overview",
    section: "Situation",
    path: "/er",
    label: "Situation Overview",
    short: "Situation",
    icon: ShieldAlert,
    description: "Active hazards, alerts, readiness KPIs and data freshness.",
    context: "emergency",
    keywords: ["disaster", "hazard", "situation", "readiness", "emergency"],
  },
  {
    id: "er-live",
    section: "Situation",
    path: "/er/live",
    label: "Live Situation",
    short: "Live",
    icon: Activity,
    description: "Hazard extents, risk zones, sensors, resources and routes on the map.",
    context: "emergency",
    keywords: ["map", "hazard", "sensor", "resource", "shelter", "route"],
  },
  {
    id: "er-forecast",
    section: "Analysis",
    path: "/er/forecast",
    label: "Forecast & Risk",
    short: "Forecast",
    icon: Gauge,
    description: "Per-hazard risk surface, confidence, factors and model evidence.",
    context: "emergency",
    keywords: ["forecast", "risk", "confidence", "model", "flood", "landslide"],
  },
  {
    id: "er-resources",
    section: "Response",
    path: "/er/resources",
    label: "Resources",
    short: "Resources",
    icon: Truck,
    description: "Inventory, readiness, allocation planner and dispatch lifecycle.",
    context: "emergency",
    keywords: ["resource", "allocation", "dispatch", "shelter", "readiness"],
  },
  {
    id: "er-plans",
    section: "Response",
    path: "/er/plans",
    label: "Response Plans",
    short: "Plans",
    icon: ListChecks,
    description: "Per-hazard SOP checklists, task assignment and after-action.",
    context: "emergency",
    keywords: ["sop", "plan", "task", "checklist", "response"],
  },
];

/** The two top-level workspaces surfaced by the context switcher. */
export const WORKSPACES: { id: WorkspaceContext; label: string; home: string; blurb: string }[] = [
  { id: "crime", label: "Crime Intelligence", home: "/command",
    blurb: "FIRs, people, networks, hotspots and forecasting." },
  { id: "emergency", label: "Emergency Response", home: "/er",
    blurb: "Multi-hazard forecasting, readiness and evacuation." },
];

/** Derive the active workspace from the current path (context lives in the URL). */
export function contextForPath(path: string): WorkspaceContext {
  return path === "/er" || path.startsWith("/er/") ? "emergency" : "crime";
}

/** Destinations visible to a role within the active workspace context. */
export function visibleDestinations(
  role: UserRole,
  isAdmin: boolean,
  context: WorkspaceContext = "crime",
  /** Seat-derived facts. Optional so existing callers keep working; omitting
   *  `aggregateOnly` shows everything, which is the pre-existing behaviour. */
  seat: { aggregateOnly?: boolean } = {},
): Destination[] {
  return DESTINATIONS.filter((d) => {
    if ((d.context ?? "crime") !== context) return false;
    if (d.adminOnly && !isAdmin) return false;
    if (d.roles && !d.roles.includes(role)) return false;
    // Mirrors the server's require_case_level guard. Without this a DGP's sidebar
    // offers Cases, Intake, People and Face Recognition, all of which answer 403 —
    // which reads as a broken product rather than as a scope boundary.
    if (d.requiresCaseLevel && seat.aggregateOnly) return false;
    return true;
  });
}

/** Group destinations into consecutive side-nav sections, preserving order.
 *  Mirrors the AWS console side navigation: a bold section heading per group,
 *  with a divider between groups. */
export function groupDestinations(
  destinations: Destination[],
): { section: string; items: Destination[] }[] {
  const groups: { section: string; items: Destination[] }[] = [];
  for (const d of destinations) {
    const last = groups[groups.length - 1];
    if (last && last.section === d.section) last.items.push(d);
    else groups.push({ section: d.section, items: [d] });
  }
  return groups;
}

export function destinationByPath(path: string): Destination | undefined {
  // Prefer the longest matching path so "/er/live" wins over "/er".
  return [...DESTINATIONS]
    .sort((a, b) => b.path.length - a.path.length)
    .find((d) => path === d.path || path.startsWith(`${d.path}/`));
}
