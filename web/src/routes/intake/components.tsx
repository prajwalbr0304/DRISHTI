import type { ReactNode } from "react";
import { AlertTriangle, CheckCircle2, Info, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import type { IntakeValidationIssue } from "@/api/types";

/* Shared building blocks for the intake wizard — Calm Authority tokens. */

export function Field({
  label, required, error, hint, htmlFor, children,
}: {
  label: string; required?: boolean; error?: string; hint?: string;
  htmlFor?: string; children: ReactNode;
}) {
  return (
    <label htmlFor={htmlFor} className="block space-y-1">
      <span className="flex items-center gap-1 text-12 font-medium text-content-dim">
        {label}
        {required && <span className="text-severity-high">*</span>}
      </span>
      {children}
      {error ? (
        <span className="flex items-center gap-1 text-12 text-severity-high">
          <AlertTriangle className="size-3" /> {error}
        </span>
      ) : hint ? (
        <span className="text-12 text-content-dim">{hint}</span>
      ) : null}
    </label>
  );
}

export function SectionCard({ title, description, children }: {
  title: string; description?: string; children: ReactNode;
}) {
  return (
    <section className="rounded-card border border-hairline bg-surface p-4">
      <div className="mb-3">
        <h3 className="text-14 font-semibold text-content">{title}</h3>
        {description && <p className="mt-0.5 text-12 text-content-dim">{description}</p>}
      </div>
      {children}
    </section>
  );
}

/** A grouped list of validation issues (errors are blocking, warnings advisory). */
export function IssueList({ issues, kind }: { issues: IntakeValidationIssue[]; kind: "error" | "warning" }) {
  if (!issues.length) return null;
  const blocking = kind === "error";
  return (
    <div
      className={cn(
        "rounded-card border p-3 text-13",
        blocking ? "border-severity-high/40 bg-severity-high/5" : "border-severity-medium/40 bg-severity-medium/5",
      )}
    >
      <div className="mb-1.5 flex items-center gap-1.5 font-medium">
        {blocking ? (
          <AlertTriangle className="size-4 text-severity-high" />
        ) : (
          <Info className="size-4 text-severity-medium" />
        )}
        <span className={blocking ? "text-severity-high" : "text-severity-medium"}>
          {blocking ? `${issues.length} blocking error${issues.length > 1 ? "s" : ""}` : `${issues.length} review warning${issues.length > 1 ? "s" : ""}`}
        </span>
      </div>
      <ul className="space-y-1">
        {issues.map((i, idx) => (
          <li key={`${i.field}-${i.code}-${idx}`} className="flex gap-2 text-content-dim">
            <span className="tnum shrink-0 text-content/50">{i.field}</span>
            <span className="text-content">{i.message}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export type SaveState = "idle" | "dirty" | "saving" | "saved" | "error";

/** Visible autosave indicator (DoD §E: autosave with visible state). */
export function SaveBadge({ state }: { state: SaveState }) {
  const map: Record<SaveState, { label: string; cls: string; icon?: ReactNode }> = {
    idle: { label: "No changes", cls: "text-content-dim" },
    dirty: { label: "Unsaved changes", cls: "text-severity-medium" },
    saving: { label: "Saving…", cls: "text-content-dim", icon: <Loader2 className="size-3 animate-spin" /> },
    saved: { label: "Draft saved", cls: "text-severity-low", icon: <CheckCircle2 className="size-3" /> },
    error: { label: "Save failed", cls: "text-severity-high", icon: <AlertTriangle className="size-3" /> },
  };
  const s = map[state];
  return (
    <span className={cn("inline-flex items-center gap-1 text-12", s.cls)}>
      {s.icon}
      {s.label}
    </span>
  );
}

const STATUS_VARIANT: Record<string, "neutral" | "primary" | "low" | "medium" | "high"> = {
  draft: "neutral", submitted: "primary", under_review: "primary",
  approved: "low", rejected: "high", returned_for_correction: "medium",
};

export function StatusPill({ status }: { status: string }) {
  return (
    <Badge variant={STATUS_VARIANT[status] ?? "neutral"} className="capitalize">
      {status.replace(/_/g, " ")}
    </Badge>
  );
}
