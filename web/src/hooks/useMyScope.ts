import { useQuery } from "@tanstack/react-query";
import { api } from "@/api";
import type { MyScopeResponse } from "@/api/endpoints/org";
import { useSeatKey } from "@/hooks/useSeatKey";
import { useRole } from "@/providers/RoleProvider";
import type { ScopeType, UserRole } from "@/config/roles";

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
  /** The seat's scope type — what actually determines which board renders and
   *  how much data is in scope. Authoritative from the server. */
  scopeType: ScopeType;
  /** Districts a range seat covers. null when not range-scoped. */
  districtIds: number[] | null;
  /** Units (police stations) the seat is confined to. null above station grain.
   *
   *  Carried because the district alone cannot name a STATION seat's posting, and a
   *  station or IO board has to be able to say which station its figures are for —
   *  that is the difference between "your caseload" and "some caseload". */
  unitIds: number[] | null;
  /** Rank on the trusted seat record, e.g. "Police Sub-Inspector". Display only. */
  rank: string | null;
  /** Username of the resolved seat. Display/audit only, never authentication. */
  username: string | null;
  /** Wing / range the seat is anchored to, when applicable. */
  wingId: number | null;
  rangeId: number | null;
  /** Crime heads a wing seat is limited to. null = every head. */
  crimeHeadIds: number[] | null;
  /** True when the seat must never read individual case rows (state / wing). */
  aggregateOnly: boolean;
  /** True when this seat may be recorded as the IO of a case. */
  isLeadInvestigator: boolean;
}

/** Scope levels that command more than one district — no single-district default. */
const BROAD_LEVELS = new Set(["state", "range"]);

/** Scope types that are not pinned to one district. `wing` belongs here because a
 *  wing is state-wide geographically and narrowed by crime head instead. */
const BROAD_SCOPE_TYPES = new Set<ScopeType>(["state", "wing", "platform"]);

/** Fallback breadth by role, for when /org/my-scope is unreachable. Only the two
 *  roles that are inherently unpinned; every other role must resolve a posting
 *  before it sees anything, so guessing breadth for them would be wrong. */
const BROAD_ROLES = new Set<UserRole>([
  "dgp_state_command",
  "system_admin",
]);

export function useMyScope(): SeatRegion {
  const { role } = useRole();
  const seatKey = useSeatKey();

  const q = useQuery({
    /* Keyed by SEAT, not by role. The request carries the seat's actor header and
       the server resolves the posting from that record, so two seats sharing a role
       get different answers — an SP of Bagalkot and an SP of Mysuru are both
       `district_command` and are entitled to different districts.

       Keyed by role alone this cache replayed the first seat's scope to the second:
       opening SP Ganesh Gowda after SP Anand reported Anand's district here, and
       because this hook is what anchors the region selector and what every board
       reads, the whole workspace then claimed to be somewhere it was not. */
    queryKey: ["org", "my-scope", seatKey],
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
  const pinned = scope?.district_ids ?? null;

  const seat = {
    scopeType: (scope?.scope_type as ScopeType | undefined) ?? "unresolved",
    districtIds: pinned,
    unitIds: scope?.unit_ids ?? null,
    rank: scope?.rank ?? null,
    username: scope?.username ?? null,
    wingId: scope?.wing_id ?? null,
    rangeId: scope?.range_id ?? null,
    crimeHeadIds: scope?.crime_head_ids ?? null,
    aggregateOnly: scope?.aggregate_only ?? false,
    isLeadInvestigator: scope?.is_lead_investigator ?? false,
    loading,
  };

  // A trusted assignment wins whenever the server pinned exactly one district.
  // More than one (a range) is not a single default, so it falls through rather
  // than arbitrarily picking the first of five.
  if (pinned?.length === 1) {
    return {
      ...seat,
      districtId: pinned[0],
      scopeLevel: level || "district",
      source: "trusted-assignment",
    };
  }

  // Not district-pinned by remit: unpinned is the correct answer here, not a
  // missing one. `wing` counts because a wing is state-wide geographically.
  if (scope?.scope_type
      ? BROAD_SCOPE_TYPES.has(scope.scope_type as ScopeType)
      : (level ? BROAD_LEVELS.has(level) : BROAD_ROLES.has(role))) {
    return {
      ...seat,
      districtId: null,
      scopeLevel: level || "state",
      source: "role-default",
    };
  }

  // A range seat with several districts is genuinely resolved; it just has no
  // single default district for the top-bar selector.
  if (pinned && pinned.length > 1) {
    return {
      ...seat,
      districtId: null,
      scopeLevel: level || "range",
      source: "trusted-assignment",
    };
  }

  // Posted seat with nothing on record. Deliberately resolves to null rather than
  // inventing a district: inventing one would put a jurisdiction in the selector
  // the officer was never posted to, and every widget would silently report on
  // somewhere else.
  return {
    ...seat,
    districtId: null,
    scopeLevel: level || "district",
    source: "unresolved",
  };
}

/** The seat's scope type on its own — what board selection keys off. */
export function useSeatScopeType(): ScopeType {
  return useMyScope().scopeType;
}
