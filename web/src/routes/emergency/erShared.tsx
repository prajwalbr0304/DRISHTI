import type { ReactNode } from "react";
import { AlertTriangle, CheckCircle2, CircleSlash, Clock, WifiOff } from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { NativeSelect } from "@/components/ui/native-select";
import { roleCan } from "@/config/roles";
import { useRole } from "@/providers/RoleProvider";
import { DISTRICT_NAMES, districtName, useDisasterStore } from "@/stores/useDisasterStore";
import type { FeedFreshness } from "@/api/endpoints/disaster";

/* ============================================================================
   Shared Emergency Response UI (Prompt 17 §H). A deliberately urgent-but-calm
   disaster palette (severity tokens), accessible status labels, and honesty
   affordances (confidence, freshness, synthetic label). NOT the criminal-person
   risk visuals.
   ========================================================================== */

export const SEVERITY_VARIANT: Record<string, "low" | "medium" | "high" | "critical"> = {
  minor: "low", moderate: "medium", severe: "high", extreme: "critical",
};

export function SeverityBadge({ severity }: { severity?: string | null }) {
  const s = (severity || "moderate").toLowerCase();
  return <Badge variant={SEVERITY_VARIANT[s] ?? "medium"}>{s}</Badge>;
}

export function StatusBadge({ status }: { status?: string | null }) {
  const s = (status || "").toLowerCase();
  const variant =
    s === "warning" || s === "active" ? "critical"
    : s === "watch" ? "high"
    : s === "recovery" ? "medium"
    : "neutral";
  return <Badge variant={variant}>{s || "—"}</Badge>;
}

export function QualityBadge({ quality }: { quality?: string | null }) {
  const q = (quality || "ok").toLowerCase();
  if (q === "ok") return <Badge variant="low"><CheckCircle2 className="size-3" /> validated</Badge>;
  if (q === "stale") return <Badge variant="high"><Clock className="size-3" /> stale</Badge>;
  if (q === "superseded") return <Badge variant="medium">superseded</Badge>;
  if (q === "rejected") return <Badge variant="critical">rejected</Badge>;
  return <Badge variant="high"><AlertTriangle className="size-3" /> low confidence</Badge>;
}

/** A confidence chip — colour by band, always with the numeric value (never
    colour alone). */
export function ConfidenceChip({ value }: { value?: number | null }) {
  if (value == null) return <Badge variant="neutral">confidence n/a</Badge>;
  const pct = Math.round(value * 100);
  const variant = value >= 0.7 ? "low" : value >= 0.4 ? "medium" : "critical";
  return <Badge variant={variant}>confidence {pct}%</Badge>;
}

export function SyntheticNote({ className }: { className?: string }) {
  return (
    <p className={cn("text-11 text-content-dim", className)}>
      Synthetic hackathon decision-support demonstration — not an official warning,
      dispatch or evacuation system. Predictions are area/period-level.
    </p>
  );
}

export function Panel({ title, actions, children, className }: {
  title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string;
}) {
  return (
    <section className={cn("rounded-control border border-hairline bg-surface", className)}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-2 border-b border-hairline px-3 py-2">
          {title && <h2 className="text-13 font-semibold text-content">{title}</h2>}
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className="p-3">{children}</div>
    </section>
  );
}

export function KpiTile({ label, value, tone = "neutral", hint }: {
  label: string; value: ReactNode; tone?: "neutral" | "warn" | "critical" | "good"; hint?: string;
}) {
  const toneCls = {
    neutral: "text-content", warn: "text-severity-high", critical: "text-severity-critical",
    good: "text-severity-low",
  }[tone];
  return (
    <div className="rounded-control border border-hairline bg-surface px-3 py-2.5">
      <div className="text-11 uppercase tracking-wide text-content-dim">{label}</div>
      <div className={cn("mt-0.5 text-20 font-semibold tabular-nums", toneCls)}>{value}</div>
      {hint && <div className="mt-0.5 text-11 text-content-dim">{hint}</div>}
    </div>
  );
}

const FRESH_ICON: Record<string, typeof CheckCircle2> = {
  fresh: CheckCircle2, stale: Clock, failed: WifiOff, never: CircleSlash,
};

export function FreshnessBanner({ feeds }: { feeds: FeedFreshness[] }) {
  const stale = feeds.filter((f) => f.status === "stale" || f.status === "failed");
  return (
    <div className={cn(
      "flex flex-wrap items-center gap-x-4 gap-y-1 rounded-control border px-3 py-2 text-12",
      stale.length
        ? "border-severity-high/40 bg-severity-high/10"
        : "border-hairline bg-surface-2/50",
    )}>
      <span className="font-medium text-content">Data freshness</span>
      {feeds.length === 0 && <span className="text-content-dim">No feeds registered.</span>}
      {feeds.map((f) => {
        const Icon = FRESH_ICON[f.status] ?? CircleSlash;
        const tone = f.status === "fresh" ? "text-severity-low"
          : f.status === "stale" ? "text-severity-high"
          : f.status === "failed" ? "text-severity-critical" : "text-content-dim";
        return (
          <span key={f.feed_code} className="inline-flex items-center gap-1" title={f.attribution || undefined}>
            <Icon className={cn("size-3.5", tone)} />
            <span className="text-content">{f.feed_code}</span>
            <span className={tone}>{f.status}</span>
            {f.age_minutes != null && <span className="text-content-dim">({Math.round(f.age_minutes)}m)</span>}
            {f.external_access_required && <Badge variant="outline" className="ml-1">External Access Required</Badge>}
          </span>
        );
      })}
    </div>
  );
}

/** District filter for reads (view scope). Never widens write scope. */
export function DistrictPicker() {
  const activeDistrict = useDisasterStore((s) => s.activeDistrict);
  const setActiveDistrict = useDisasterStore((s) => s.setActiveDistrict);
  const options = Object.entries(DISTRICT_NAMES)
    .map(([id, name]) => ({ value: id, label: name }))
    .sort((a, b) => a.label.localeCompare(b.label));
  return (
    <div className="flex items-center gap-2">
      <span className="text-12 text-content-dim">District</span>
      <NativeSelect
        aria-label="District"
        value={activeDistrict != null ? String(activeDistrict) : ""}
        onChange={(v) => setActiveDistrict(v ? Number(v) : null)}
        options={options}
        placeholder="All districts"
        className="w-52"
      />
    </div>
  );
}

/** Whether the current role may run mutating Emergency Response actions. */
export function useErCapabilities() {
  const { role } = useRole();
  const assignedDistrict = useDisasterStore((s) => s.assignedDistrict);
  const activeDistrict = useDisasterStore((s) => s.activeDistrict);
  const canWrite = roleCan(role, "disaster_write");
  return { role, canWrite, assignedDistrict, activeDistrict, districtName };
}
