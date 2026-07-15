import { cn, formatNumber } from "@/lib/utils";

/* ============================================================================
   Status pipeline / stepper (doc 03 §2.13). Horizontal stages with the current
   stage lit; per-stage counts turn it into a caseload funnel for supervisors.
   When counts aren't available yet (no Cases API), stages render with an honest
   "—" rather than a fabricated number.
   ========================================================================== */

export interface PipelineStage {
  key: string;
  label: string;
  count?: number | null;
}

export function StatusPipeline({
  stages,
  currentKey,
  pending = false,
}: {
  stages: PipelineStage[];
  currentKey?: string;
  pending?: boolean;
}) {
  const currentIdx = stages.findIndex((s) => s.key === currentKey);
  return (
    <div className="flex items-stretch gap-1.5">
      {stages.map((s, i) => {
        const active = i === currentIdx;
        const done = currentIdx >= 0 && i < currentIdx;
        return (
          <div key={s.key} className="flex min-w-0 flex-1 flex-col">
            <div
              className={cn(
                "flex h-1.5 rounded-full",
                active ? "bg-primary" : done ? "bg-primary/50" : "bg-surface-2",
              )}
            />
            <div className="mt-2 min-w-0">
              <div
                className={cn(
                  "tnum text-20 font-semibold leading-none",
                  pending ? "text-content-dim" : "text-content",
                )}
              >
                {pending || s.count == null ? "—" : formatNumber(s.count)}
              </div>
              <div
                className={cn(
                  "mt-1 truncate text-12",
                  active ? "font-medium text-content" : "text-content-dim",
                )}
                title={s.label}
              >
                {s.label}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

/** Canonical FIR lifecycle stages (schema statuses). */
export const CASE_STAGES: PipelineStage[] = [
  { key: "registered", label: "Registered" },
  { key: "under_investigation", label: "Under investigation" },
  { key: "chargesheet", label: "Chargesheeted" },
  { key: "trial", label: "Trial" },
  { key: "disposed", label: "Disposed" },
];
