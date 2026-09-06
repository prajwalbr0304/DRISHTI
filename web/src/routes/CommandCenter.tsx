import { useRole } from "@/providers/RoleProvider";
import { useLanguage } from "@/providers/LanguageProvider";
import { PRESETS, useTimeStore } from "@/stores/useTimeStore";
import { PageHeader } from "@/components/common/PageHeader";
import { TimeScrubber } from "@/components/shell/TimeScrubber";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api";
import { RoleBoard } from "@/routes/home/RoleBoard";
import { useMyScope } from "@/hooks/useMyScope";
import { useUiVisibility } from "@/hooks/useUiVisibility";
import { ScopeTrail } from "@/routes/home/ScopeTrail";
import { boardFor } from "@/config/kpi/roleBoards";

/* ============================================================================
   Command Center — role-adaptive home (doc 01 §4.1 / §7). It is a genuinely
   DIFFERENT screen per role: the widget set is swapped, not relabelled. All
   data is live from the Wave-B services and scoped server-side by role.
   ========================================================================== */

function greeting() {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 17) return "Good afternoon";
  return "Good evening";
}

export function CommandCenter() {
  const { role, def } = useRole();
  const { t } = useLanguage();
  const { preset } = useTimeStore();
  const rangeLabel = preset === "custom" ? t("Custom range") : t(PRESETS.find((p) => p.id === preset)?.label ?? "");

  /* No header actions: the seat, its scope and the active time range are all
     already shown in the top bar, so repeating them here was duplication. The
     PageHeader's own bottom margin is the only gap before the board. */
  return (
    <div>
      <PageHeader
        title={`${t(greeting())}, ${t(def.label)}`}
        description={def.blurb}
        info={
          <p>
            Widgets are assembled for the {t(def.label)} seat and scoped server-side to{" "}
            {t(def.scope)} over the last {rangeLabel}. Drag a widget by the grip in its header to
            rearrange the board, or resize it from its bottom-right corner.
          </p>
        }
        actions={<TimeScrubber />}
      />

      {/* Where you have drilled to, and the way back. Renders nothing until you
          have actually narrowed below your seat's own grain. */}
      <ScopeTrail />

      <RoleHome role={role} />
    </div>
  );
}

/* Board selection is a function of the seat's SCOPE TYPE, not its role.
 *
 * A senior_command seat is an ADGP wing board when wing-scoped and a DIG range
 * board when range-scoped; district_command is an SP district board or a CP city
 * board. Switching on role alone would give each of those pairs the same board,
 * which is the conflation the six-role model exists to remove.
 *
 * One component now serves all of them: RoleBoard composes its card set from the
 * KPI registry (config/kpi/registry.ts + roleBoards.ts). The five hand-written
 * boards it replaces had drifted apart — the same metric carried different labels
 * and hints depending on which of the five files you were reading, and adding a
 * card meant editing whichever subset you remembered.
 *
 * An unposted seat renders the board's own notice rather than falling back to a
 * state-wide view: the server will refuse every scoped query it makes, so showing
 * it the whole force would be a lie the data cannot back. */
function RoleHome({ role }: { role: ReturnType<typeof useRole>["role"] }) {
  const seat = useMyScope();
  const wingCode = useWingCode(seat.wingId);
  const ui = useUiVisibility();

  // The seat's scope has not resolved yet; a skeleton is honest, a state-wide
  // board would not be.
  if (seat.loading) return <BoardSkeleton />;

  /* An administrator can switch off a whole board for a role, and this is the
     only place that can honour it. Saying so beats rendering an empty grid: the
     seat is not broken and has no missing data, someone turned the board off.
     The reason is shown when one was recorded, because "ask an administrator" is
     a much worse answer than the note they already wrote. */
  if (!ui.isVisible("board", seat.scopeType)) {
    const reason = ui.reasonFor("board", seat.scopeType);
    return (
      <div className="rounded-card border border-hairline bg-surface p-6">
        <h2 className="text-16 font-semibold text-content">
          {boardFor(seat.scopeType).title} is turned off
        </h2>
        <p className="mt-2 max-w-[70ch] text-13 leading-relaxed text-content-dim">
          An administrator has disabled this board for your role
          {reason ? `: ${reason}` : "."} Other sections of DRISHTI are unaffected.
        </p>
      </div>
    );
  }

  return <RoleBoard scope={seat.scopeType} wingCode={wingCode} />;
}

/** The wing CODE for a wing-scoped seat, which the registry needs to decide
 *  wing-restricted cards. /org/my-scope returns wing_id; the code lives on
 *  /org/wings, so this resolves one to the other. Null for every other seat. */
function useWingCode(wingId: number | null): string | null {
  const wings = useQuery({
    queryKey: ["org", "wings"],
    queryFn: ({ signal }) => api.org.wings(signal),
    staleTime: 30 * 60_000,
    enabled: wingId != null,
  });
  if (wingId == null) return null;
  return wings.data?.items.find((w) => w.wing_id === wingId)?.wing_code ?? null;
}

function BoardSkeleton() {
  return (
    <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
      {Array.from({ length: 8 }).map((_, i) => (
        <div
          key={i}
          className="h-[104px] animate-pulse rounded-card border border-hairline bg-surface-2/40"
        />
      ))}
    </div>
  );
}
