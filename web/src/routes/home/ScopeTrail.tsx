import { ChevronRight, Lock } from "lucide-react";
import { useScopeStore } from "@/stores/useScopeStore";
import { useMyScope } from "@/hooks/useMyScope";
import { useDistrictNamer } from "@/hooks/useDistricts";
import { SCOPE_TYPE_LABELS, type ScopeType } from "@/config/roles";
import { SimpleTooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

/* ============================================================================
   Drill-down trail: where you are inside your own jurisdiction, and the way back.

   THE SEAT IS THE CEILING. The first crumb is the seat's own scope and is NOT
   clickable, because there is nowhere above it to go: a DIG cannot step up to the
   state, and the server would refuse the query if the UI offered it. Rendering it
   as a disabled crumb rather than omitting it is deliberate — it tells an SP that
   "Mysuru District" is the top of their world, instead of leaving them wondering
   which districts the numbers cover.

   Everything after the ceiling is a narrowing the user chose, and each is a link
   back to that level. Clicking the district crumb drops the station; clicking the
   ceiling clears both.

   Hidden entirely when there is nothing to go back to, so a seat that cannot drill
   (a station chief, an IO) never sees a one-crumb bar that does nothing.
   ========================================================================== */

export function ScopeTrail() {
  const seat = useMyScope();
  const districtId = useScopeStore((s) => s.districtId);
  const unitId = useScopeStore((s) => s.unitId);
  const unitLabel = useScopeStore((s) => s.unitLabel);
  const setDistrictId = useScopeStore((s) => s.setDistrictId);
  const clearUnit = useScopeStore((s) => s.clearUnit);
  const nameOf = useDistrictNamer();

  /* A seat already pinned to one district has not "drilled" by having that
     district selected — that IS its ceiling. Only a narrowing BELOW the seat's own
     grain counts as something to step back from. */
  const seatPinnedDistrict = seat.districtId;
  const drilledDistrict =
    districtId != null && districtId !== seatPinnedDistrict ? districtId : null;
  const drilledUnit = unitId != null ? unitId : null;

  if (drilledDistrict == null && drilledUnit == null) return null;

  const ceilingLabel = ceilingFor(seat.scopeType, seatPinnedDistrict, nameOf);

  return (
    <nav
      aria-label="Scope trail"
      className="mb-3 flex flex-wrap items-center gap-1.5 text-12"
    >
      {/* The ceiling. Clickable only if we are currently below it. */}
      <SimpleTooltip label={`Your seat commands ${ceilingLabel}. You cannot look above it.`}>
        <button
          type="button"
          disabled={drilledDistrict == null && drilledUnit == null}
          onClick={() => setDistrictId(seatPinnedDistrict ?? null)}
          className={cn(
            "inline-flex items-center gap-1 rounded-control px-1.5 py-0.5 transition-colors",
            "text-content-dim hover:bg-surface-2 hover:text-content",
            "disabled:pointer-events-none disabled:opacity-70",
          )}
        >
          <Lock className="size-3" aria-hidden />
          {ceilingLabel}
        </button>
      </SimpleTooltip>

      {drilledDistrict != null && (
        <>
          <ChevronRight className="size-3.5 text-content-dim/60" aria-hidden />
          <button
            type="button"
            onClick={clearUnit}
            disabled={drilledUnit == null}
            className={cn(
              "rounded-control px-1.5 py-0.5 font-medium transition-colors",
              drilledUnit != null
                ? "text-content-dim hover:bg-surface-2 hover:text-content"
                : "text-content disabled:pointer-events-none",
            )}
          >
            {nameOf(drilledDistrict)}
          </button>
        </>
      )}

      {drilledUnit != null && (
        <>
          <ChevronRight className="size-3.5 text-content-dim/60" aria-hidden />
          <span className="px-1.5 py-0.5 font-medium text-content">
            {unitLabel ?? `Station ${drilledUnit}`}
          </span>
        </>
      )}
    </nav>
  );
}

/** What the seat's own scope is called, for the non-clickable root crumb. */
function ceilingFor(
  scopeType: ScopeType,
  pinnedDistrict: number | null,
  nameOf: (id?: number | null) => string,
): string {
  // A district-pinned seat names its district; that is more useful than
  // "SP / District Command", which does not say WHICH district.
  if (pinnedDistrict != null) return nameOf(pinnedDistrict);
  if (scopeType === "state") return "Karnataka";
  return SCOPE_TYPE_LABELS[scopeType] ?? "My jurisdiction";
}
