import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { apiClient } from "@/api/client";
import { DEFAULT_ROLE, ROLES, type RoleDef, type UserRole } from "@/config/roles";
import { useAuthOptional } from "@/auth";
import { deriveDisplayRole } from "@/auth/roleMapping";
import { useDisasterStore } from "@/stores/useDisasterStore";

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
    const v = localStorage.getItem(STORAGE_KEY) as UserRole | null;
    if (v && v in ROLES) return v;
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
      setRoleState(derived);
      persistRole(derived);
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
    // Actor = authenticated email for the audit trail when available; otherwise
    // the demo actor. Display/audit only — never authentication.
    apiClient.setActorGetter(() => userRef.current?.email || `demo.${roleRef.current}`);
    // Emergency Response: send the coordinator's assigned district seat so the
    // server scopes disaster writes. super_admin covers all districts server-side.
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
