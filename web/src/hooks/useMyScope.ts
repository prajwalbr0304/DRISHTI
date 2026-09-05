import { useQuery } from "@tanstack/react-query";
import { api } from "@/api";
import type { MyScopeResponse } from "@/api/endpoints/org";
import { useRole } from "@/providers/RoleProvider";
import type { UserRole } from "@/config/roles";

/* ============================================================================
   The seat's own region — the district the workspace should open on before the
   user touches the top-bar selector.

   A DGP commands the state, so their default is the whole state. An SP or SHO
   works one district, so theirs is that district. Rather than hard-code that from
   the presentation role, this asks the SERVER: GET /org/my-scope re-derives the
   caller's scope from the trusted user record (role + unit assignment) and returns
   the district ids it is pinned to, or null for a state/range seat.

   NOT an authorisation boundary. It only chooses a DEFAULT for a view filter.
   Every endpoint re-derives and enforces what the caller may read on its own, so
   a wrong guess here can change what is displayed but never what may be read.

   Three ways the answer is reached, and the caller is told which:
     trusted-assignment  the server read a real district assignment.
     role-default        a state/range seat — genuinely not district-pinned, so
                         state-wide IS its scope.
     unresolved          a district/station seat with no posting on record (the
                         documented demo fallback in org/scope.py derive_scope), or
                         /org/my-scope unreachable. Deliberately resolves to null
                         rather than guessing a district: inventing one would put a
                         district in the top-bar selector that the user was never
                         posted to, and every widget would then silently report on
                         somewhere else. "All districts" is the honest fallback.
   ========================================================================== */

export type SeatRegionSource = "trusted-assignment" | "role-default" | "unresolved";

export interface SeatRegion {
  /** District the seat opens on. null = state-wide (not district-pinned). */
  districtId: number | null;
  /** Server-reported scope level: state / range / district / station / assigned_case. */
  scopeLevel: string;
  /** How `districtId` was arrived at. */
  source: SeatRegionSource;
  loading: boolean;
}

/** Scope levels that command more than one district — no single-district default. */
const BROAD_LEVELS = new Set(["state", "range"]);

/** Fallback breadth by presentation role, for when /org/my-scope is unreachable.
 *  Mirrors the seats whose `scope` in config/roles.ts spans the state. */
const BROAD_ROLES = new Set<UserRole>([
  "dgp_state_command",
  "adgp_igp_range",
  "crime_analyst",
  "cyber_cell",
  "system_admin",
]);

export function useMyScope(): SeatRegion {
  const { role } = useRole();

  const q = useQuery({
    // Keyed by role so switching seats re-resolves; the request carries the
    // seat's actor header, which is what the server resolves the posting from.
    queryKey: ["org", "my-scope", role],
    queryFn: ({ signal }) => api.org.myScope(signal),
    staleTime: 5 * 60_000,
    retry: false,
  });

  return resolveSeatRegion(q.data, { role, loading: q.isLoading });
}

/** Pure resolution, split out so the precedence is readable and testable. */
export function resolveSeatRegion(
  scope: MyScopeResponse | undefined,
  { role, loading }: { role: UserRole; loading: boolean },
): SeatRegion {
  const level = scope?.scope_level ?? "";

  // A trusted assignment wins whenever the server pinned exactly one district.
  // More than one (a range with explicit districts) is not a single default, so
  // it falls through rather than arbitrarily picking the first.
  const pinned = scope?.district_ids ?? null;
  if (pinned?.length === 1) {
    return {
      districtId: pinned[0],
      scopeLevel: level || "district",
      source: "trusted-assignment",
      loading,
    };
  }

  // State/range seat: unpinned is the correct answer, not a missing one.
  if (level ? BROAD_LEVELS.has(level) : BROAD_ROLES.has(role)) {
    return { districtId: null, scopeLevel: level || "state", source: "role-default", loading };
  }

  // District/station seat with nothing on record — state-wide, and say so.
  return { districtId: null, scopeLevel: level || "district", source: "unresolved", loading };
}
