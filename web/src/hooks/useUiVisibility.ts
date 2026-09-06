import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api";
import type { ElementKind, UiGrant } from "@/api/endpoints/adminConsole";
import { useRole } from "@/providers/RoleProvider";
import { useMyScope } from "@/hooks/useMyScope";
import type { ScopeType } from "@/config/roles";

/* ============================================================================
   Admin UI-visibility overrides, applied on top of the registry defaults.

   DEFAULTS IN CODE, OVERRIDES IN THE DATABASE. An absent row means "use the
   registry default"; a present row overrides it. The alternative — a row per
   element per role — was rejected because a newly shipped KPI card would then be
   invisible to everyone until an admin remembered to enable it six times, and the
   database would hold a stale copy of a registry that ships with the frontend.

   PRECEDENCE. A scope-specific override beats a role-wide one, so an admin can
   hide a card from wing seats while range seats keep it. Both rows are allowed to
   exist; the narrower one wins.

   THIS IS NOT ACCESS CONTROL. While authentication and RLS are off, hiding an
   element stops it being rendered and nothing more: the route still resolves if
   typed and the endpoint still answers. The admin console states this using the
   server's own wording.
   ========================================================================== */

export interface UiVisibility {
  /** False only when an override says so. Unknown elements are visible, which is
   *  what keeps the registry the source of truth for defaults. */
  isVisible: (kind: ElementKind, elementId: string) => boolean;
  /** The admin's note for why something is hidden, when one was recorded. */
  reasonFor: (kind: ElementKind, elementId: string) => string | undefined;
  /** Ids hidden for this seat, by kind — handy for filtering a list in one pass. */
  hidden: Record<ElementKind, Set<string>>;
  loading: boolean;
}

const EMPTY: Record<ElementKind, Set<string>> = {
  destination: new Set(), board: new Set(), kpi: new Set(), widget: new Set(),
};

function key(kind: ElementKind, id: string) {
  return `${kind}:${id}`;
}

/** Overrides that apply to a seat, narrower rows last so they overwrite. */
function applicable(grants: UiGrant[], role: string, scopeType: ScopeType) {
  const forRole = grants.filter((g) => g.role_name === role);
  return [
    ...forRole.filter((g) => g.scope_type == null),
    ...forRole.filter((g) => g.scope_type === scopeType),
  ];
}

export function useUiVisibility(): UiVisibility {
  const { role } = useRole();
  const { scopeType } = useMyScope();

  const q = useQuery({
    // Keyed by role only: the response is every override for the role, and the
    // scope filter is applied client-side so switching seats does not refetch.
    queryKey: ["admin", "ui-visibility", role],
    queryFn: ({ signal }) => api.adminConsole.uiVisibility({ role_name: role }, signal),
    staleTime: 5 * 60_000,
    // A visibility service that is down must not blank the workspace. Falling
    // back to the registry defaults shows too much rather than nothing, which is
    // the right failure for a presentation-only control.
    retry: false,
  });

  return useMemo(() => {
    const rows = applicable(q.data?.items ?? [], role, scopeType);

    const state = new Map<string, { enabled: boolean; reason: string | null }>();
    for (const g of rows) {
      state.set(key(g.element_kind, g.element_id),
                { enabled: g.enabled, reason: g.reason });
    }

    const hidden: Record<ElementKind, Set<string>> = {
      destination: new Set(), board: new Set(), kpi: new Set(), widget: new Set(),
    };
    for (const g of rows) {
      if (!g.enabled) hidden[g.element_kind].add(g.element_id);
      else hidden[g.element_kind].delete(g.element_id);
    }

    return {
      isVisible: (kind, id) => state.get(key(kind, id))?.enabled ?? true,
      reasonFor: (kind, id) => state.get(key(kind, id))?.reason ?? undefined,
      hidden,
      loading: q.isLoading,
    };
  }, [q.data, q.isLoading, role, scopeType]);
}

/** For contexts with no provider (tests, storybook): everything visible. */
export const ALL_VISIBLE: UiVisibility = {
  isVisible: () => true,
  reasonFor: () => undefined,
  hidden: EMPTY,
  loading: false,
};
