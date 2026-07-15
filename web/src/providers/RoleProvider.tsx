import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { apiClient } from "@/api/client";
import { DEFAULT_ROLE, ROLES, type RoleDef, type UserRole } from "@/config/roles";

/* ============================================================================
   Role context. The whole shell reads the active role to adapt the sidebar and
   data scope, and every API request carries it as X-Role (money-trail + scope).
   ========================================================================== */

interface RoleContextValue {
  role: UserRole;
  def: RoleDef;
  setRole: (r: UserRole) => void;
  isAdmin: boolean;
}

const RoleContext = createContext<RoleContextValue | null>(null);
const STORAGE_KEY = "drishti.role";

function loadRole(): UserRole {
  try {
    const v = localStorage.getItem(STORAGE_KEY) as UserRole | null;
    if (v && v in ROLES) return v;
  } catch {
    /* ignore */
  }
  return DEFAULT_ROLE;
}

export function RoleProvider({ children }: { children: React.ReactNode }) {
  const [role, setRoleState] = useState<UserRole>(loadRole);

  // Keep a live ref so the API client always reads the current role.
  const roleRef = useRef(role);
  useEffect(() => {
    roleRef.current = role;
  }, [role]);
  useEffect(() => {
    apiClient.setRoleGetter(() => roleRef.current);
  }, []);

  const setRole = useCallback((r: UserRole) => {
    setRoleState(r);
    try {
      localStorage.setItem(STORAGE_KEY, r);
    } catch {
      /* ignore */
    }
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
