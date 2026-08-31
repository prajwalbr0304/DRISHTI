import { useRole } from "@/providers/RoleProvider";
import { useLanguage } from "@/providers/LanguageProvider";
import { PRESETS, useTimeStore } from "@/stores/useTimeStore";
import { PageHeader } from "@/components/common/PageHeader";
import { TimeScrubber } from "@/components/shell/TimeScrubber";
import { InvestigatorHome } from "@/routes/home/InvestigatorHome";
import { AnalystHome } from "@/routes/home/AnalystHome";
import { SupervisorHome } from "@/routes/home/SupervisorHome";
import { PolicymakerHome } from "@/routes/home/PolicymakerHome";

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

      <RoleHome role={role} />
    </div>
  );
}

function RoleHome({ role }: { role: ReturnType<typeof useRole>["role"] }) {
  switch (role) {
    // Field + station seats open on the case-work dashboard.
    case "investigating_officer":
    case "cyber_cell":
      return <InvestigatorHome />;
    // Station / sub-division oversight: review queue + workload.
    case "sho":
    case "dysp_acp":
      return <SupervisorHome />;
    // Command chain: strategic aggregate briefing.
    case "dgp_state_command":
    case "adgp_igp_range":
    case "sp_district_command":
      return <PolicymakerHome />;
    // Analytical overview (crime analyst, traffic command, platform admin).
    case "crime_analyst":
    case "traffic_command":
    case "system_admin":
    default:
      return <AnalystHome />;
  }
}
