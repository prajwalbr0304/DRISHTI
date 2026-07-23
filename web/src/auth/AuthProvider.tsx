import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { apiClient } from "@/api/client";
import type { UserRole } from "@/config/roles";
import { createAuthClient } from "@/auth/authClient";
import { saveOfflineUser } from "@/auth/offline";
import type { AuthMode, AuthStatus, AuthUser } from "@/auth/types";

/* ============================================================================
   AuthProvider — Catalyst Authentication login/session (Phase 14 Part C, item 7).

   Mounted high so the whole app shares one auth check; it does NOT gate by
   itself. Gating is done by <RequireAuth> around the app routes, so the public
   landing page ("/") stays reachable while every app route requires a session.

   The authenticated identity is exposed for PRESENTATION; the API Gateway
   re-derives the role server-side from the Catalyst session and strips any
   client role header. Never trust a client-supplied role.
   ========================================================================== */

interface AuthContextValue {
  status: AuthStatus;
  user: AuthUser | null;
  mode: AuthMode;
  error?: string;
  signOut: () => void;
  /** Offline mode only: pick a synthetic demo identity. */
  signInOffline: (role: UserRole) => void;
  /** Catalyst mode only: render the embedded login into `elementId`. */
  renderSignIn: (elementId: string) => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const client = useMemo(() => createAuthClient(), []);
  const [status, setStatus] = useState<AuthStatus>("initializing");
  const [user, setUser] = useState<AuthUser | null>(null);
  const [error, setError] = useState<string | undefined>();

  useEffect(() => {
    let cancelled = false;
    let settled = false;
    // The optional bearer token (undefined for cookie-based Catalyst sessions).
    apiClient.setTokenGetter(() => client.getToken());
    // Bound the session check. After a sign-out / SSO hand-off the Catalyst SDK
    // can leave `init()`/`isUserAuthenticated()` pending, which would strand the
    // app on "Checking your session…" forever. On timeout we fall back to
    // unauthenticated so the sign-in screen renders (the user can sign in again).
    const guard = window.setTimeout(() => {
      if (cancelled || settled) return;
      settled = true;
      setStatus("unauthenticated");
    }, 9000);
    (async () => {
      try {
        await client.init();
        const u = await client.getUser();
        if (cancelled || settled) return;
        settled = true;
        window.clearTimeout(guard);
        setUser(u);
        setStatus(u ? "authenticated" : "unauthenticated");
      } catch (e) {
        if (cancelled || settled) return;
        settled = true;
        window.clearTimeout(guard);
        setError(e instanceof Error ? e.message : String(e));
        setStatus("error");
      }
    })();
    return () => {
      cancelled = true;
      window.clearTimeout(guard);
    };
  }, [client]);

  const signOut = useCallback(() => {
    // Return to the sign-in screen after sign-out (offline: hard redirect;
    // catalyst: Zoho logout then back to /login).
    const redirect = `${window.location.origin}/login`;
    setUser(null);
    setStatus("unauthenticated");
    void client.signOut(redirect);
  }, [client]);

  const signInOffline = useCallback(
    (role: UserRole) => {
      if (client.mode !== "offline") return;
      const u = saveOfflineUser(role);
      setUser(u);
      setStatus("authenticated");
    },
    [client],
  );

  const renderSignIn = useCallback(
    (elementId: string) => {
      client.renderSignIn(elementId);
    },
    [client],
  );

  const value = useMemo<AuthContextValue>(
    () => ({ status, user, mode: client.mode, error, signOut, signInOffline, renderSignIn }),
    [status, user, client.mode, error, signOut, signInOffline, renderSignIn],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within <AuthProvider>");
  return ctx;
}

/** Like useAuth but returns null instead of throwing when there is no provider
 *  (e.g. isolated component tests that mount RoleProvider without AuthProvider). */
// eslint-disable-next-line react-refresh/only-export-components
export function useAuthOptional(): AuthContextValue | null {
  return useContext(AuthContext);
}

/** Minimal loading state while the session check runs. */
function AuthSplash() {
  return (
    <div className="flex h-screen w-full items-center justify-center bg-bg text-content-dim">
      <div className="flex items-center gap-2 text-13">
        <span className="size-2 animate-pulse rounded-full bg-primary" />
        Checking your session…
      </div>
    </div>
  );
}

/**
 * Route guard used as a layout element around the app routes. Renders the app
 * (via <Outlet/>) only when authenticated; otherwise redirects to /login,
 * preserving the intended destination so sign-in returns the user there.
 */
export function RequireAuth() {
  const { status } = useAuth();
  const location = useLocation();
  if (status === "initializing") return <AuthSplash />;
  if (status === "authenticated") return <Outlet />;
  return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
}
