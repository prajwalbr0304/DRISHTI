import {
  Activity,
  BarChart3,
  FilePlus2,
  FolderKanban,
  Gauge,
  LayoutDashboard,
  ListChecks,
  Map,
  MessageSquareText,
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
   The eight sidebar destinations (doc 01 §3). Super-admins see all eight;
   everyone else sees seven (Admin is hidden). Each maps to a Wave-B capability.
   ========================================================================== */

export interface Destination {
  id: string;
  path: string;
  label: string;
  /** icon-rail label / short form */
  short: string;
  icon: LucideIcon;
  description: string;
  /** only super_admin sees this destination */
  adminOnly?: boolean;
  /** optional explicit role allow-list (future scoping) */
  roles?: UserRole[];
  /** ⌘K keywords */
  keywords?: string[];
  /** which workspace this destination belongs to (default "crime") */
  context?: WorkspaceContext;
}

export const DESTINATIONS: Destination[] = [
  {
    id: "command",
    path: "/command",
    label: "Command Center",
    short: "Home",
    icon: LayoutDashboard,
    description: "Live operational overview across the state.",
    keywords: ["home", "overview", "dashboard", "kpi"],
  },
  {
    id: "cases",
    path: "/cases",
    label: "Cases",
    short: "Cases",
    icon: FolderKanban,
    description: "Case decision-support: summaries, similar cases, leads.",
    keywords: ["fir", "investigation", "summary", "leads", "similar"],
  },
  {
    id: "intake",
    path: "/intake",
    label: "Intake",
    short: "Intake",
    icon: FilePlus2,
    description: "Register FIRs/cases: guided intake, bulk import and supervisory review.",
    roles: ["investigator", "supervisor", "super_admin"],
    keywords: ["fir", "intake", "new case", "register", "draft", "import", "review", "inbox"],
  },
  {
    id: "people",
    path: "/people",
    label: "People & Entities",
    short: "People",
    icon: Users,
    description: "Persons, gangs, vehicles, phones and accounts — with risk.",
    keywords: ["person", "entity", "offender", "gang", "vehicle", "phone", "risk"],
  },
  {
    id: "network",
    path: "/network",
    label: "Network Analysis",
    short: "Network",
    icon: Share2,
    description: "Link analysis: communities, hidden associations, money trail, paths.",
    keywords: ["graph", "network", "association", "community", "money", "path", "link"],
  },
  {
    id: "board",
    path: "/board",
    label: "Investigation Board",
    short: "Board",
    icon: Workflow,
    description: "Assemble live objects on a shared canvas; separate evidence from hypotheses.",
    // Boards model sensitive investigative material — policymaker is excluded.
    roles: ["investigator", "analyst", "supervisor", "super_admin"],
    keywords: ["board", "canvas", "link", "hypothesis", "evidence", "palantir", "corkboard", "investigation"],
  },
  {
    id: "map",
    path: "/map",
    label: "Map & Hotspots",
    short: "Map",
    icon: Map,
    description: "Geospatial hotspots, forecasts and red-zone alerts.",
    keywords: ["geo", "hotspot", "heatmap", "spatial", "forecast", "alert"],
  },
  {
    id: "analytics",
    path: "/analytics",
    label: "Analytics & Forecasting",
    short: "Analytics",
    icon: BarChart3,
    description: "Trends, socio-economic correlations, forecasts and model explainability.",
    keywords: ["socioeconomic", "correlation", "explain", "trends", "forecast", "policy"],
  },
  {
    id: "ask",
    path: "/ask",
    label: "Ask DRISHTI",
    short: "Ask",
    icon: MessageSquareText,
    description: "Conversational, cited answers grounded in the data.",
    keywords: ["chat", "ask", "nl", "query", "voice", "question"],
  },
  {
    id: "admin",
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
    path: "/er/forecast",
    label: "Forecast & Risk",
    short: "Forecast",
    icon: Gauge,
    // Running/reviewing forecasts is a coordinator action (crime roles read-only).
    roles: ["disaster_coordinator", "super_admin"],
    description: "Per-hazard risk surface, confidence, factors and model evidence.",
    context: "emergency",
    keywords: ["forecast", "risk", "confidence", "model", "flood", "landslide"],
  },
  {
    id: "er-resources",
    path: "/er/resources",
    label: "Resources",
    short: "Resources",
    icon: Truck,
    roles: ["disaster_coordinator", "super_admin"],
    description: "Inventory, readiness, allocation planner and dispatch lifecycle.",
    context: "emergency",
    keywords: ["resource", "allocation", "dispatch", "shelter", "readiness"],
  },
  {
    id: "er-plans",
    path: "/er/plans",
    label: "Response Plans",
    short: "Plans",
    icon: ListChecks,
    roles: ["disaster_coordinator", "super_admin"],
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
): Destination[] {
  return DESTINATIONS.filter((d) => {
    if ((d.context ?? "crime") !== context) return false;
    if (d.adminOnly && !isAdmin) return false;
    if (d.roles && !d.roles.includes(role)) return false;
    return true;
  });
}

export function destinationByPath(path: string): Destination | undefined {
  // Prefer the longest matching path so "/er/live" wins over "/er".
  return [...DESTINATIONS]
    .sort((a, b) => b.path.length - a.path.length)
    .find((d) => path === d.path || path.startsWith(d.path + "/") || path.startsWith(d.path));
}
