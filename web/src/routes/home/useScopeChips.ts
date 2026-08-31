import { useDistrictLabel } from "@/hooks/useDistricts";
import { useScopeStore } from "@/stores/useScopeStore";

/* ============================================================================
   Context-chip text for dashboard widgets.

   Chips appear ONLY while a district is selected. With no selection every card
   would read "all districts", which is the default state and therefore says
   nothing — it just crowds the header and truncates the title.

   Once a district IS selected the chip starts earning its place, because that
   is the only moment the widgets disagree: most follow the selection, while the
   socio-economic correlation and graph centrality cannot (see districtSupport
   in useScopeStore). Those say "state-wide" so the selector never implies a
   filter that was not applied.
   ========================================================================== */

export function useScopeChips() {
  const districtId = useScopeStore((s) => s.districtId);
  const label = useDistrictLabel();
  const narrowed = districtId != null;

  return {
    /** true when a single district is selected */
    narrowed,
    /** widgets that follow the selector — names the district, else no chip */
    scoped: narrowed ? label : undefined,
    /** widgets that cannot follow it — flags itself only when that matters */
    stateWide: narrowed ? "state-wide" : undefined,
  };
}
