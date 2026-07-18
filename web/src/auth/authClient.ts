import { runtime } from "@/config/runtime";
import { loadCatalystSdk, type CatalystGlobal } from "@/auth/catalystSdk";
import { clearOfflineUser, loadOfflineUser } from "@/auth/offline";
import { normalizeCatalystUser, type AuthMode, type AuthUser } from "@/auth/types";

/* ============================================================================
   AuthClient — one narrow interface, two implementations:
     - CatalystAuthClient : real embedded Catalyst Authentication (deployed).
     - OfflineAuthClient  : synthetic demo identity (local dev).
   The AuthProvider talks only to this interface; the factory picks the impl
   from VITE_AUTH_MODE. This mirrors the Part B component pattern (fake ⇄ real
   behind one contract).
   ========================================================================== */

export interface AuthClient {
  readonly mode: AuthMode;
  /** Prepare the client (load SDK in catalyst mode; no-op offline). */
  init(): Promise<void>;
  /** Current authenticated identity, or null if not signed in. */
  getUser(): Promise<AuthUser | null>;
  /** Render the embedded sign-in UI into `elementId` (catalyst mode). */
  renderSignIn(elementId: string): void;
  /** Sign out and redirect the browser to `redirectUrl`. */
  signOut(redirectUrl: string): Promise<void>;
  /** Cross-domain auth token for the API client (undefined when unavailable). */
  getToken(): Promise<string | undefined>;
}

class CatalystAuthClient implements AuthClient {
  readonly mode = "catalyst" as const;
  private sdk: CatalystGlobal | null = null;

  async init(): Promise<void> {
    this.sdk = await loadCatalystSdk(runtime.catalystSdkUrl);
  }

  async getUser(): Promise<AuthUser | null> {
    const sdk = this.sdk;
    if (!sdk) return null;
    try {
      const raw = await sdk.auth.isUserAuthenticated();
      return normalizeCatalystUser(raw);
    } catch {
      // Rejection = not signed in (expected pre-login).
      return null;
    }
  }

  renderSignIn(elementId: string): void {
    // The SDK renders the branded embedded login iframe (Zoho/Google/etc.
    // providers are configured in the Console). On success it redirects to the
    // configured login_redirect ("/"), reloading the app.
    this.sdk?.auth.signIn(elementId, {});
  }

  async signOut(redirectUrl: string): Promise<void> {
    await Promise.resolve(this.sdk?.auth.signOut(redirectUrl));
  }

  async getToken(): Promise<string | undefined> {
    // Cross-domain (Slate → API Gateway) auth: mint a short-lived token. The
    // SDK manages the token lifecycle, so calling per request is cheap. Sent as
    // a RAW Authorization header (no "Bearer " prefix) — the Catalyst convention.
    const sdk = this.sdk;
    if (!sdk) return undefined;
    try {
      const res = await sdk.auth.generateAuthToken();
      return res?.access_token ?? res?.content?.token ?? undefined;
    } catch {
      return undefined; // fall back to cookie-based session
    }
  }
}

class OfflineAuthClient implements AuthClient {
  readonly mode = "offline" as const;

  async init(): Promise<void> {
    /* nothing to load */
  }

  async getUser(): Promise<AuthUser | null> {
    return loadOfflineUser();
  }

  renderSignIn(): void {
    /* offline sign-in is a role picker rendered by <LoginGate> directly */
  }

  async signOut(redirectUrl: string): Promise<void> {
    clearOfflineUser();
    if (typeof window !== "undefined") window.location.assign(redirectUrl);
  }

  async getToken(): Promise<string | undefined> {
    return undefined;
  }
}

export function createAuthClient(mode: AuthMode = runtime.authMode): AuthClient {
  return mode === "catalyst" ? new CatalystAuthClient() : new OfflineAuthClient();
}
