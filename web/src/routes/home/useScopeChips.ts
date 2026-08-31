import { useDistrictLabel } from "@/hooks/useDistricts";
import { useScopeStore } from "@/stores/useScopeStore";

/* ============================================================================
   Context-chip text for dashboard widgets, so each card states the scope it is
   ACTUALLY showing rather than the scope the top-bar selector implies.

   `scoped`     — follows the district selector (server- or client-side)
   `stateWide`  — cannot be narrowed; always the whole state
   ========================================================================== */

export function useScopeChips() {
  const districtId = useScopeStore((s) => s.districtId);
  const label = useDistrictLabel();
  const scoped = districtId == null ? "all districts" : label;
  return {
    /** widgets whose data follows the selector */
    scoped,
    /** widgets that can never follow it */
    stateWide: "state-wide",
    /** true when a single district is selected */
    narrowed: districtId != null,
    /** aliases kept explicit so a widget cannot mislabel itself by accident */
    trends: scoped,
    forecast: scoped,
    hotspots: scoped,
    alerts: scoped,
    caseload: scoped,
    socio: "state-wide",
    centrality: "state-wide",
  };
}
