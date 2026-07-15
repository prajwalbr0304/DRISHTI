import { Gavel, UserCheck } from "lucide-react";
import type { CaseListItem } from "@/api/types";
import { cn, formatDate } from "@/lib/utils";
import { Badge, type BadgeProps } from "@/components/ui/badge";
import { SimpleTooltip } from "@/components/ui/tooltip";
import { Skeleton } from "@/components/ui/skeleton";

/* Dense, calm case table (doc 01 §4.2, 13px tabular numerals). */

function gravityVariant(g?: string | null): BadgeProps["variant"] {
  const s = (g ?? "").toLowerCase();
  if (s.includes("heinous") && !s.includes("non")) return "critical";
  if (s.includes("serious")) return "high";
  if (s.includes("non")) return "low";
  return "medium";
}

const TH = "px-3 py-2 text-left text-12 font-semibold text-content-dim whitespace-nowrap";
const TD = "px-3 py-2 align-middle";

export function CaseTable({
  items,
  loading,
  onRowClick,
}: {
  items: CaseListItem[];
  loading?: boolean;
  onRowClick: (id: number) => void;
}) {
  return (
    <div className="overflow-x-auto rounded-card border border-hairline">
      <table className="w-full border-collapse text-13">
        <thead className="sticky top-0 z-10 bg-surface-2">
          <tr className="border-b border-hairline">
            <th className={TH}>Crime No.</th>
            <th className={TH}>Crime</th>
            <th className={TH}>Location</th>
            <th className={TH}>Status</th>
            <th className={TH}>Gravity</th>
            <th className={cn(TH, "text-right")}>Registered</th>
            <th className={cn(TH, "text-right")}>V / A</th>
            <th className={cn(TH, "text-center")}>Progress</th>
          </tr>
        </thead>
        <tbody>
          {loading &&
            Array.from({ length: 10 }).map((_, i) => (
              <tr key={`s${i}`} className="border-b border-hairline">
                <td className={TD} colSpan={8}>
                  <Skeleton className="h-5 w-full" />
                </td>
              </tr>
            ))}

          {!loading &&
            items.map((c) => (
              <tr
                key={c.case_id}
                onClick={() => onRowClick(c.case_id)}
                className="cursor-pointer border-b border-hairline transition-colors hover:bg-surface-2"
              >
                <td className={cn(TD, "tnum font-medium text-content")}>{c.crime_no ?? c.case_id}</td>
                <td className={TD}>
                  <div className="max-w-[220px] truncate text-content">{c.crime_group ?? "—"}</div>
                  {c.crime_subhead && (
                    <div className="max-w-[220px] truncate text-12 text-content-dim">{c.crime_subhead}</div>
                  )}
                </td>
                <td className={TD}>
                  <div className="max-w-[180px] truncate text-content">{c.district ?? "—"}</div>
                  {c.station && (
                    <div className="max-w-[180px] truncate text-12 text-content-dim">{c.station}</div>
                  )}
                </td>
                <td className={TD}>
                  {c.status ? (
                    <Badge variant="neutral" className="whitespace-nowrap">
                      {c.status}
                    </Badge>
                  ) : (
                    "—"
                  )}
                </td>
                <td className={TD}>
                  {c.gravity ? (
                    <Badge variant={gravityVariant(c.gravity)} className="whitespace-nowrap capitalize">
                      {c.gravity}
                    </Badge>
                  ) : (
                    "—"
                  )}
                </td>
                <td className={cn(TD, "tnum whitespace-nowrap text-right text-content-dim")}>
                  {c.registered_date ? formatDate(c.registered_date) : "—"}
                </td>
                <td className={cn(TD, "tnum whitespace-nowrap text-right text-content-dim")}>
                  {c.victim_count} / {c.accused_count}
                </td>
                <td className={TD}>
                  <div className="flex items-center justify-center gap-2">
                    {c.has_arrest && (
                      <SimpleTooltip label="Arrest recorded">
                        <UserCheck className="size-4 text-accent" />
                      </SimpleTooltip>
                    )}
                    {c.has_chargesheet && (
                      <SimpleTooltip label="Chargesheet filed">
                        <Gavel className="size-4 text-primary" />
                      </SimpleTooltip>
                    )}
                    {!c.has_arrest && !c.has_chargesheet && (
                      <span className="text-12 text-content-dim">—</span>
                    )}
                  </div>
                </td>
              </tr>
            ))}
        </tbody>
      </table>
    </div>
  );
}
