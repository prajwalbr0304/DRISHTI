/* ============================================================================
   Small formatting helpers shared by the CCTV wall.

   NOTE ON TIMESTAMPS — this is deliberate, not an oversight. Catalyst Data Store
   returns datetimes as naive `'YYYY-MM-DD HH:mm:ss'` strings with no timezone
   marker, and `new Date("2026-09-06 10:00:00")` is interpreted as LOCAL time by
   browsers. Feeding those strings to the shared `timeAgo()` helper would silently
   skew every age on this page by the viewer's UTC offset — which on a live
   incident wall is the difference between "1 minute ago" and "6 hours ago".
   So the server computes `age_seconds` at read time and the UI formats that
   instead. Use `formatAge(alert.age_seconds)`, never `timeAgo(alert.created_at)`.
   ========================================================================== */

/** "just now" / "3m ago" / "2h 15m ago", from a server-computed age in seconds. */
export function formatAge(seconds?: number | null): string {
  if (seconds == null || Number.isNaN(seconds)) return "time unknown";
  const s = Math.max(0, Math.round(seconds));
  if (s < 10) return "just now";
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  const rem = m % 60;
  if (h < 24) return rem ? `${h}h ${rem}m ago` : `${h}h ago`;
  const d = Math.floor(h / 24);
  return d === 1 ? "1 day ago" : `${d} days ago`;
}

/** Compact "in ~4 min" for a dispatch ETA. */
export function formatEta(minutes?: number | null): string {
  if (minutes == null) return "ETA unavailable";
  if (minutes < 1) return "under a minute";
  return `~${Math.round(minutes)} min`;
}

export function formatKm(km?: number | null): string {
  if (km == null) return "—";
  if (km < 1) return `${Math.round(km * 1000)} m`;
  return `${km.toFixed(km < 10 ? 2 : 1)} km`;
}

/** Turn a snake_case enum into a readable label. */
export function humanise(value?: string | null): string {
  if (!value) return "—";
  return value.replace(/_/g, " ");
}

/** Where a dispatch ranking came from, in words an operator can act on. */
export function geometrySourceLabel(source?: string | null): string {
  if (source === "postgis_knn") return "canonical station geometry (PostGIS nearest-neighbour)";
  if (source === "datastore_haversine") return "responder registry (great-circle distance)";
  if (source === "unavailable") return "unavailable";
  return source || "unknown";
}

/** Dismissal reasons, labelled for the dropdown. Mirrors guards.DISMISS_REASONS. */
export const DISMISS_REASON_OPTIONS: { value: string; label: string }[] = [
  { value: "false_positive", label: "False positive — nothing of the sort in frame" },
  { value: "duplicate", label: "Duplicate — already raised by another camera" },
  { value: "already_handled", label: "Already handled — unit aware / on scene" },
  { value: "not_actionable", label: "Real but not actionable" },
  { value: "poor_visibility", label: "Cannot judge — poor visibility" },
  { value: "other", label: "Other" },
];

/** The onward status an analyst can move a dispatch to, given where it is. */
export const NEXT_DISPATCH_STATUS: Record<string, string | undefined> = {
  proposed: "dispatched",
  dispatched: "acknowledged",
  acknowledged: "enroute",
  enroute: "onsite",
  onsite: "closed",
};
