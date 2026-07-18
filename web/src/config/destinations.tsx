import {
  BarChart3,
  FilePlus2,
  FolderKanban,
  LayoutDashboard,
  Map,
  MessageSquareText,
  Share2,
  ShieldCheck,
  Users,
  type LucideIcon,
} from "lucide-react";
import type { UserRole } from "@/config/roles";

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
];

/** Destinations visible to a role (8 for super_admin, 7 otherwise). */
export function visibleDestinations(role: UserRole, isAdmin: boolean): Destination[] {
  return DESTINATIONS.filter((d) => {
    if (d.adminOnly && !isAdmin) return false;
    if (d.roles && !d.roles.includes(role)) return false;
    return true;
  });
}

export function destinationByPath(path: string): Destination | undefined {
  return DESTINATIONS.find((d) => path.startsWith(d.path));
}
