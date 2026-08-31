import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api";
import { DISTRICT_NAMES } from "@/stores/useDisasterStore";
import { useScopeStore } from "@/stores/useScopeStore";

/* ============================================================================
   The district list behind the region selector.

   Source of truth is GET /cases/filters, which reads the District table, so it
   carries every district with its real name. That endpoint sits behind the
   case-read gate though, and the aggregate-only command seats are not guaranteed
   to hold it — so rather than render an empty selector we fall back to the
   known district map. `usingFallback` is exposed so the UI can say which it is
   instead of quietly showing a shorter list.
   ========================================================================== */

export interface DistrictOption {
  id: number;
  name: string;
}

const byName = (a: DistrictOption, b: DistrictOption) => a.name.localeCompare(b.name);

const FALLBACK: DistrictOption[] = Object.entries(DISTRICT_NAMES)
  .map(([id, name]) => ({ id: Number(id), name }))
  .sort(byName);

export function useDistricts() {
  // Same query key as useFilterOptions() so the two share one cache entry.
  const q = useQuery({
    queryKey: ["cases", "filters"],
    queryFn: ({ signal }) => api.cases.filters(signal),
    staleTime: Infinity,
    retry: false,
  });

  const fromApi = useMemo<DistrictOption[]>(
    () =>
      (q.data?.districts ?? [])
        .filter((d): d is { id: number; name?: string | null } => d.id != null)
        .map((d) => ({ id: d.id, name: d.name?.trim() || `District ${d.id}` }))
        .sort(byName),
    [q.data],
  );

  const resolved = fromApi.length > 0;

  return {
    districts: resolved ? fromApi : FALLBACK,
    loading: q.isLoading,
    /** true when the case-read list was unavailable and the static map is in use */
    usingFallback: !q.isLoading && !resolved,
  };
}

/** Resolve ANY district id to its name.
 *
 *  Several API responses carry `district_id` without a name (forecast MapCell,
 *  for one), so widgets used to print "District 12". This turns those ids into
 *  the real names, falling back to the id only when it is genuinely unknown. */
export function useDistrictNamer(): (id?: number | null) => string {
  const { districts } = useDistricts();
  return useMemo(() => {
    const byId = new Map(districts.map((d) => [d.id, d.name]));
    return (id?: number | null) =>
      id == null ? "Unknown district" : byId.get(id) ?? `District ${id}`;
  }, [districts]);
}

/** Display name for the active district ("All districts" when unscoped). */
export function useDistrictLabel(): string {
  const districtId = useScopeStore((s) => s.districtId);
  const name = useDistrictNamer();
  return districtId == null ? "All districts" : name(districtId);
}
