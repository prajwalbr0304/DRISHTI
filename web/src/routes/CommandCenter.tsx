import { Sparkles } from "lucide-react";
import { useRole } from "@/providers/RoleProvider";
import { useUIStore } from "@/stores/useUIStore";
import { PRESETS, useTimeStore } from "@/stores/useTimeStore";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/common/PageHeader";
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
  const askAbout = useUIStore((s) => s.askAbout);
  const { preset } = useTimeStore();
  const rangeLabel = preset === "custom" ? "Custom range" : (PRESETS.find((p) => p.id === preset)?.label ?? "");

  return (
    <div className="space-y-4">
      <PageHeader
        title={`${greeting()}, ${def.label}`}
        description={def.blurb}
        actions={
          <>
            <Badge variant="neutral">{def.scope}</Badge>
            <Badge variant="neutral">{rangeLabel}</Badge>
            <Button
              variant="outline"
              size="sm"
              onClick={() => askAbout(`Give me a ${def.label.toLowerCase()} briefing for my scope`)}
            >
              <Sparkles />
              Ask about this view
            </Button>
          </>
        }
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
