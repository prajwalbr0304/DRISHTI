import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api";
import { useMyScope } from "@/hooks/useMyScope";
import { useSeatKey } from "@/hooks/useSeatKey";
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

   THE RESPONSE IS PER-SEAT. /cases/filters is confined server-side to the caller's
   jurisdiction, so it returns 38 districts to a DGP and exactly one to an SP. That
   makes the SEAT part of the cache identity: keyed by role alone, opening SP Ganesh
   Gowda straight after SP Anand replayed Anand's district list, because both seats
   are `district_command`. See useSeatKey.
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
  const seatKey = useSeatKey();
  // Same query key as useFilterOptions() and the Case Explorer rail, so all three
  // share one cache entry per seat rather than issuing the same request three times.
  const q = useQuery({
    queryKey: ["cases", "filters", seatKey],
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

/* ----------------------------------------------------------------------------
   The districts a seat may actually choose between.

   `useDistricts` answers "what districts exist". This answers "what districts is
   THIS SEAT allowed to look at", and they are not the same question. /cases/filters
   is now confined server-side, so for a live seat the two mostly agree — but this
   hook is still the authority, for two reasons:

     the static FALLBACK list has no idea who is asking, so when the endpoint is
     unavailable an SP would be offered all 30 known districts again;

     and "All districts" is a choice the endpoint's row list cannot express either
     way. Offering it to a seat pinned to one district is the specific lie being
     fixed: the trigger would read "All districts" while every endpoint confined the
     answer to one district, so the number on screen and the label above it
     described different places.
   -------------------------------------------------------------------------- */
export interface ScopedDistricts {
  /** Selectable districts, already bounded by the seat's entitlement. */
  districts: DistrictOption[];
  /** Whether an unpinned "all districts in my remit" choice is honest for this
   *  seat. False for a seat posted to exactly one district. */
  allowAll: boolean;
  /** The single district a pinned seat is confined to, else null. */
  pinnedTo: number | null;
  /** True when the seat has no posting, so there is nothing to choose. */
  unposted: boolean;
  loading: boolean;
  /** The static list is in use because the lookup was unavailable. */
  usingFallback: boolean;
  /** One line explaining the bound, for the selector footnote. */
  note: string;
  /** Label for the "no extra narrowing" option in any district picker.
   *
   *  "All districts" only where that is true. For a seat posted to one district the
   *  unfiltered request still comes back confined to that district server-side, so
   *  a picker labelling the same option "All districts" describes somewhere other
   *  than the data it returns — it names the district instead. */
  allLabel: string;
}

export function useScopedDistricts(): ScopedDistricts {
  const { districts, loading, usingFallback } = useDistricts();
  const seat = useMyScope();
  const entitled = seat.districtIds;

  return useMemo(() => {
    const base = {
      loading: loading || seat.loading,
      usingFallback,
    };

    // Not district-pinned by remit: state, wing and platform seats. The whole list
    // is correct here, and so is "All districts".
    if (entitled == null) {
      return {
        ...base,
        districts,
        allowAll: true,
        pinnedTo: null,
        unposted: false,
        allLabel: "All districts",
        note: "Your seat covers every district. Narrowing here is a view filter only — it cannot widen what you may read.",
      };
    }

    // Unposted seat. Empty on purpose: the server confines it to nothing, so
    // offering districts would offer 38 ways to get an empty page.
    if (entitled.length === 0) {
      return {
        ...base,
        districts: [],
        allowAll: false,
        pinnedTo: null,
        unposted: true,
        allLabel: "No district in scope",
        note: "This seat has no posting on record, so no district is in scope. An administrator must post it.",
      };
    }

    const allowed = new Set(entitled);
    const scoped = districts.filter((d) => allowed.has(d.id));

    /* The fallback list can be missing a district the seat is entitled to (it is a
       static map, and a real posting is authoritative). Naming it "District 12" is
       worse than the alternative only in appearance — dropping it would hide the
       officer's own jurisdiction from their own selector. */
    for (const id of entitled) {
      if (!scoped.some((d) => d.id === id)) scoped.push({ id, name: `District ${id}` });
    }
    scoped.sort(byName);

    if (entitled.length === 1) {
      return {
        ...base,
        districts: scoped,
        allowAll: false,
        pinnedTo: entitled[0],
        unposted: false,
        allLabel: scoped[0]?.name ?? `District ${entitled[0]}`,
        note: "Your seat is posted to this district, so it is the only scope available. Every figure in the workspace is confined to it server-side.",
      };
    }

    return {
      ...base,
      districts: scoped,
      allowAll: true,
      pinnedTo: null,
      unposted: false,
      allLabel: `All ${entitled.length} districts in your range`,
      note: `Your seat covers ${entitled.length} districts. "All districts" means all ${entitled.length} — the workspace never reaches outside your command.`,
    };
  }, [districts, entitled, loading, seat.loading, usingFallback]);
}
