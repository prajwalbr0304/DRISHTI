import {
  Banknote,
  Car,
  ClipboardCheck,
  FileText,
  Gauge,
  Home,
  Image as ImageIcon,
  Landmark,
  MapPin,
  MessageSquareQuote,
  Navigation,
  Network,
  Newspaper,
  Phone,
  ScrollText,
  Shield,
  Siren,
  Sparkles,
  StickyNote,
  Truck,
  User,
  Users,
  Waves,
  type LucideIcon,
} from "lucide-react";
import { ENTITY_COLORS } from "@/components/network/graphEncoding";

/* ============================================================================
   Board visual contract (doc 06 §5). Node colour encodes the object kind,
   consistent with the graph module. Evidence edges are solid; hypothesis edges
   are dashed. Confidence is shown as text/tooltip, never colour alone.
   ========================================================================== */

export interface KindStyle {
  label: string;
  color: string;
  icon: LucideIcon;
}

const SLATE = "#64748b";

export const NODE_KIND_STYLE: Record<string, KindStyle> = {
  entity: { label: "Entity", color: ENTITY_COLORS.person, icon: User },
  case: { label: "Case / FIR", color: "#0284c7", icon: ScrollText },
  accused: { label: "Accused", color: "#e11d48", icon: User },
  victim: { label: "Victim", color: "#0d9488", icon: User },
  complainant: { label: "Complainant", color: "#7c3aed", icon: User },
  vehicle: { label: "Vehicle", color: ENTITY_COLORS.vehicle, icon: Car },
  phone: { label: "Phone / Device", color: ENTITY_COLORS.phone, icon: Phone },
  account: { label: "Account", color: ENTITY_COLORS.account, icon: Banknote },
  location: { label: "Location", color: ENTITY_COLORS.location, icon: MapPin },
  hotspot: { label: "Hotspot", color: "#f59e0b", icon: MapPin },
  news_event: { label: "News (unverified)", color: "#a16207", icon: Newspaper },
  chat_answer: { label: "Cited answer", color: "#0891b2", icon: MessageSquareQuote },
  note: { label: "Note", color: SLATE, icon: StickyNote },
  image: { label: "Image", color: "#8b5cf6", icon: ImageIcon },
  document: { label: "Document", color: "#6366f1", icon: FileText },
  map_extract: { label: "Map extract", color: ENTITY_COLORS.location, icon: MapPin },
  prediction: { label: "Prediction", color: "#db2777", icon: Sparkles },
  organisation: { label: "Organisation", color: ENTITY_COLORS.organisation, icon: Users },
  gang: { label: "Gang", color: ENTITY_COLORS.gang, icon: Shield },
  // Emergency Response (Prompt 17) — a distinct disaster palette (ambers/teals),
  // deliberately NOT the criminal-person risk visuals.
  hazard_event: { label: "Hazard event", color: "#ea580c", icon: Siren },
  hazard_prediction: { label: "Hazard forecast", color: "#d97706", icon: Gauge },
  hazard_risk_zone: { label: "Risk zone", color: "#0891b2", icon: Waves },
  resource: { label: "Resource", color: "#0d9488", icon: Truck },
  shelter: { label: "Relief shelter", color: "#16a34a", icon: Home },
  allocation: { label: "Allocation", color: "#4f46e5", icon: ClipboardCheck },
  evacuation_route: { label: "Evacuation route", color: "#0284c7", icon: Navigation },
};

export function kindStyle(kind?: string | null): KindStyle {
  if (!kind) return { label: "Object", color: SLATE, icon: Network };
  return NODE_KIND_STYLE[kind] ?? { label: kind, color: SLATE, icon: Network };
}

export const NODE_KIND_LEGEND = [
  "case", "entity", "accused", "vehicle", "phone", "account", "location",
  "document", "note",
].map((k) => ({ kind: k, ...kindStyle(k) }));

/** A subtle tinted background for a node card from its kind colour. */
export function tint(color: string, alpha = 0.12): string {
  const c = color.replace("#", "");
  const r = parseInt(c.slice(0, 2), 16);
  const g = parseInt(c.slice(2, 4), 16);
  const b = parseInt(c.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}
