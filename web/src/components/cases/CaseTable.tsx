import { Gavel, UserCheck } from "lucide-react";
import type { CaseListItem } from "@/api/types";
import { cn, formatDate } from "@/lib/utils";
import { Badge, type BadgeProps } from "@/components/ui/badge";
import { SimpleTooltip } from "@/components/ui/tooltip";
import { Skeleton } from "@/components/ui/skeleton";

function gravityVariant(g?: string | null): BadgeProps["variant"] {
  const s = (g ?? "").toLowerCase();
  if (s.includes("heinous") && !s.includes("non")) return "critical";
  if (s.includes("serious")) return "high";
  if (s.includes("non")) return "low";
  return "medium";
}

const TH = "px-2.5 py-2 text-left text-12 font-semibold text-content-dim";
const TD = "px-2.5 py-2 align-middle";

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
    <>
      <div className="hidden overflow-hidden rounded-card border border-hairline lg:block">
        <table className="w-full table-fixed border-collapse text-13">
          <colgroup>
            <col className="w-[17%]" />
            <col className="w-[21%]" />
            <col className="w-[19%]" />
            <col className="w-[18%] xl:w-[16%]" />
            <col className="hidden w-[11%] xl:table-column" />
            <col className="hidden w-[11%] xl:table-column" />
            <col className="hidden w-[7%] 2xl:table-column" />
            <col className="hidden w-[7%] 2xl:table-column" />
          </colgroup>
          <thead className="sticky top-0 z-10 bg-surface-2">
            <tr className="border-b border-hairline">
              <th className={TH}>Crime No.</th>
              <th className={TH}>Crime</th>
              <th className={TH}>Location</th>
              <th className={TH}>Status</th>
              <th className={cn(TH, "hidden xl:table-cell")}>Gravity</th>
              <th className={cn(TH, "hidden text-right xl:table-cell")}>Registered</th>
              <th className={cn(TH, "hidden text-right 2xl:table-cell")}>V / A</th>
              <th className={cn(TH, "hidden text-center 2xl:table-cell")}>Progress</th>
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
                  <td className={cn(TD, "tnum break-all text-12 font-medium text-content")}>
                    {c.crime_no ?? c.case_id}
                  </td>
                  <td className={TD}>
                    <div className="break-words text-content">{c.crime_group ?? "—"}</div>
                    {c.crime_subhead && <div className="break-words text-12 text-content-dim">{c.crime_subhead}</div>}
                  </td>
                  <td className={TD}>
                    <div className="break-words text-content">{c.district ?? "—"}</div>
                    {c.station && <div className="break-words text-12 text-content-dim">{c.station}</div>}
                  </td>
                  <td className={TD}>
                    {c.status ? (
                      <Badge variant="neutral" className="max-w-full whitespace-normal text-left leading-tight">
                        {c.status}
                      </Badge>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className={cn(TD, "hidden xl:table-cell")}>
                    {c.gravity ? (
                      <Badge
                        variant={gravityVariant(c.gravity)}
                        className="max-w-full whitespace-normal capitalize leading-tight"
                      >
                        {c.gravity}
                      </Badge>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td
                    className={cn(
                      TD,
                      "tnum hidden whitespace-nowrap text-right text-12 text-content-dim xl:table-cell",
                    )}
                  >
                    {c.registered_date ? formatDate(c.registered_date) : "—"}
                  </td>
                  <td
                    className={cn(
                      TD,
                      "tnum hidden whitespace-nowrap text-right text-content-dim 2xl:table-cell",
                    )}
                  >
                    {c.victim_count} / {c.accused_count}
                  </td>
                  <td className={cn(TD, "hidden 2xl:table-cell")}>
                    <ProgressIcons item={c} />
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>

      <div className="space-y-2 lg:hidden" aria-label="Cases">
        {loading &&
          Array.from({ length: 6 }).map((_, i) => (
            <div key={`mobile-s${i}`} className="rounded-card border border-hairline bg-surface p-3">
              <Skeleton className="h-20 w-full" />
            </div>
          ))}
        {!loading &&
          items.map((c) => (
            <button
              key={c.case_id}
              type="button"
              onClick={() => onRowClick(c.case_id)}
              className="w-full min-w-0 rounded-card border border-hairline bg-surface p-3 text-left transition-colors hover:bg-surface-2"
            >
              <span className="flex min-w-0 items-start justify-between gap-3">
                <span className="min-w-0">
                  <span className="tnum block break-all text-12 font-semibold text-content">
                    {c.crime_no ?? c.case_id}
                  </span>
                  <span className="mt-1 block break-words text-13 text-content">{c.crime_group ?? "—"}</span>
                  {c.crime_subhead && (
                    <span className="block break-words text-12 text-content-dim">{c.crime_subhead}</span>
                  )}
                </span>
                {c.status && (
                  <Badge
                    variant="neutral"
                    className="max-w-[45%] shrink-0 whitespace-normal text-left leading-tight"
                  >
                    {c.status}
                  </Badge>
                )}
              </span>
              <span className="mt-3 grid grid-cols-2 gap-3 border-t border-hairline pt-2 text-12 text-content-dim">
                <span>
                  <span className="block font-medium text-content">Location</span>
                  {[c.district, c.station].filter(Boolean).join(" · ") || "—"}
                </span>
                <span>
                  <span className="block font-medium text-content">Registered</span>
                  {c.registered_date ? formatDate(c.registered_date) : "—"}
                </span>
                <span>
                  <span className="block font-medium text-content">Gravity</span>
                  {c.gravity ?? "—"}
                </span>
                <span>
                  <span className="block font-medium text-content">Victims / accused</span>
                  {c.victim_count} / {c.accused_count}
                </span>
              </span>
            </button>
          ))}
      </div>
    </>
  );
}

function ProgressIcons({ item }: { item: CaseListItem }) {
  return (
    <div className="flex items-center justify-center gap-2">
      {item.has_arrest && (
        <SimpleTooltip label="Arrest recorded">
          <UserCheck className="size-4 text-accent" />
        </SimpleTooltip>
      )}
      {item.has_chargesheet && (
        <SimpleTooltip label="Chargesheet filed">
          <Gavel className="size-4 text-primary" />
        </SimpleTooltip>
      )}
      {!item.has_arrest && !item.has_chargesheet && <span className="text-12 text-content-dim">—</span>}
    </div>
  );
}
