import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { apiClient } from "@/api/client";
import {
  DEFAULT_ROLE,
  ROLES,
  demoActorFor,
  isUserRole,
  type RoleDef,
  type UserRole,
} from "@/config/roles";
import { useAuthOptional } from "@/auth";
import { deriveDisplayRole } from "@/auth/roleMapping";
import { useDisasterStore } from "@/stores/useDisasterStore";
import { selectedActor } from "@/stores/useSeatStore";

/* ============================================================================
   Role context. The shell reads the active role to adapt the sidebar and data
   scope, and every request carries it as X-Role.

   The role is DERIVED from the authenticated Catalyst identity
   (deriveDisplayRole); logging in as a different user resets the view to that
   user's role. A persisted/demo override (localStorage) lets the ProfileMenu
   switch the view during a session.

   X-Role is a DISPLAY/AUDIT hint only — the API Gateway strips it and
   re-derives the authoritative role server-side. Never a security boundary.

   Auth is read OPTIONALLY (useAuthOptional) so this provider also works in
   isolated component tests that mount it without <AuthProvider>.
   ========================================================================== */

interface RoleContextValue {
  role: UserRole;
  def: RoleDef;
  setRole: (r: UserRole) => void;
  isAdmin: boolean;
}

const RoleContext = createContext<RoleContextValue | null>(null);
const STORAGE_KEY = "drishti.role";

function loadStoredRole(): UserRole | null {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (isUserRole(v)) return v;
  } catch {
    /* ignore */
  }
  return null;
}

function persistRole(r: UserRole) {
  try {
    localStorage.setItem(STORAGE_KEY, r);
  } catch {
    /* ignore */
  }
}

export function RoleProvider({ children }: { children: React.ReactNode }) {
  const authCtx = useAuthOptional();
  const user = authCtx?.user ?? null;

  const [role, setRoleState] = useState<UserRole>(
    () => loadStoredRole() ?? deriveDisplayRole(user) ?? DEFAULT_ROLE,
  );

  // When the authenticated identity changes (login / switch), reset the view to
  // that user's derived role. No-op when there is no auth context (tests) so a
  // pre-set localStorage role is honored.
  const lastUserId = useRef<string | null>(user?.userId ?? null);
  useEffect(() => {
    if (!authCtx) return;
    const id = user?.userId ?? null;
    if (id !== lastUserId.current) {
      lastUserId.current = id;
      const derived = deriveDisplayRole(user);
      // INTERIM (all roles hold every capability): a full-access identity may
      // explore any seat's workspace as a demo view, so an explicitly chosen
      // role wins when one is stored. The server re-derives + enforces the real
      // role regardless of this presentation choice.
      const stored = loadStoredRole();
      const next = ROLES[derived].admin && stored ? stored : derived;
      setRoleState(next);
      persistRole(next);
    }
  }, [authCtx, user]);

  // Live refs so the API client always reads the current role/actor.
  const roleRef = useRef(role);
  const userRef = useRef(user);
  useEffect(() => {
    roleRef.current = role;
  }, [role]);
  useEffect(() => {
    userRef.current = user;
  }, [user]);
  useEffect(() => {
    apiClient.setRoleGetter(() => roleRef.current);
    // Actor precedence, most to least specific:
    //   1. the SEAT chosen in the picker — one of ~11,825 provisioned seats, and
    //      the only thing that identifies WHICH SP or WHICH station;
    //   2. the authenticated email, for the audit trail;
    //   3. the role's seeded demo seat, so the app still works before a pick.
    // The seat comes first because a role no longer identifies a jurisdiction: an
    // SP of Mysuru and an SP of Belagavi share a role and see different districts,
    // and only the seat distinguishes them.
    //
    // Display/audit only. The server resolves that seat's scope from its own
    // record, so naming a seat cannot grant its jurisdiction.
    apiClient.setActorGetter(() =>
      selectedActor() || userRef.current?.email || demoActorFor(roleRef.current));
    // Emergency Response: send the seat's assigned district so the server scopes
    // disaster writes. A state-level/admin seat covers all districts server-side.
    apiClient.setDistrictGetter(() => useDisasterStore.getState().assignedDistrict);
  }, []);

  const setRole = useCallback((r: UserRole) => {
    setRoleState(r);
    persistRole(r);
  }, []);

  const value = useMemo<RoleContextValue>(
    () => ({ role, def: ROLES[role], setRole, isAdmin: ROLES[role].admin }),
    [role, setRole],
  );

  return <RoleContext.Provider value={value}>{children}</RoleContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useRole(): RoleContextValue {
  const ctx = useContext(RoleContext);
  if (!ctx) throw new Error("useRole must be used within <RoleProvider>");
  return ctx;
}

/** The role context if there is one, else null.
 *
 *  For LEAF utilities that only want the role as an input to something else — a
 *  cache key, a default — rather than because they are role-aware UI. `useRole`
 *  throwing is right for a screen that cannot render without knowing the seat, and
 *  wrong for a shared data hook: it turns a missing provider anywhere in the tree
 *  into a crash in every consumer of that hook. See useSeatKey. */
// eslint-disable-next-line react-refresh/only-export-components
export function useRoleOptional(): RoleContextValue | null {
  return useContext(RoleContext) ?? null;
}
