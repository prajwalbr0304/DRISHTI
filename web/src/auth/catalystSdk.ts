/* ============================================================================
   Catalyst Web SDK (v4) loader + typings for embedded authentication.

   The deployed build loads two scripts:
     1. the versioned CDN SDK  (VITE_CATALYST_SDK_URL)
     2. /__catalyst/sdk/init.js — served ONLY by Catalyst hosting on the project
        domain; it initialises `window.catalyst` with the project config.

   Because init.js exists only on the deployed Catalyst origin, this loader is
   invoked exclusively in `catalyst` auth mode. Off-domain (local preview of a
   production build) init.js 404s and the loader rejects — the AuthProvider then
   surfaces a clear error instead of a broken login.
   ========================================================================== */

/** Token returned by generateAuthToken() (v4.6.1+). Token is `access_token`. */
export interface CatalystAuthToken {
  access_token?: string;
  content?: { token?: string };
}

/** Minimal surface of the Catalyst Web SDK auth namespace that we use. */
export interface CatalystAuthNamespace {
  /** Render the embedded login iframe into the element with this id. */
  signIn(elementId: string, config?: Record<string, unknown>): void;
  /** Resolves with the current user details if signed in; rejects otherwise. */
  isUserAuthenticated(): Promise<unknown>;
  /** Mint a short-lived token for cross-domain calls (Slate → Functions). */
  generateAuthToken(): Promise<CatalystAuthToken>;
  /** Sign out and redirect the browser to `redirectURL`. */
  signOut(redirectURL: string): void | Promise<void>;
}

export interface CatalystGlobal {
  auth: CatalystAuthNamespace;
}

declare global {
  interface Window {
    catalyst?: CatalystGlobal;
  }
}

const INIT_SCRIPT = "/__catalyst/sdk/init.js";

function injectScript(src: string): Promise<void> {
  return new Promise((resolve, reject) => {
    // Reuse an existing tag if the same src is already present.
    const existing = document.querySelector<HTMLScriptElement>(`script[src="${src}"]`);
    if (existing) {
      if (existing.dataset.loaded === "true") return resolve();
      existing.addEventListener("load", () => resolve(), { once: true });
      existing.addEventListener("error", () => reject(new Error(`Failed to load ${src}`)), {
        once: true,
      });
      return;
    }
    const el = document.createElement("script");
    el.src = src;
    el.async = false; // preserve order: CDN SDK must run before init.js
    el.addEventListener(
      "load",
      () => {
        el.dataset.loaded = "true";
        resolve();
      },
      { once: true },
    );
    el.addEventListener("error", () => reject(new Error(`Failed to load ${src}`)), { once: true });
    document.head.appendChild(el);
  });
}

let loadPromise: Promise<CatalystGlobal> | null = null;

/** Load the Catalyst Web SDK once and resolve with `window.catalyst`. */
export function loadCatalystSdk(sdkUrl: string): Promise<CatalystGlobal> {
  if (typeof window === "undefined" || typeof document === "undefined") {
    return Promise.reject(new Error("Catalyst SDK requires a browser environment"));
  }
  if (window.catalyst?.auth) return Promise.resolve(window.catalyst);
  if (loadPromise) return loadPromise;

  loadPromise = injectScript(sdkUrl)
    .then(() => injectScript(INIT_SCRIPT))
    .then(() => {
      if (!window.catalyst?.auth) {
        throw new Error("Catalyst SDK loaded but window.catalyst.auth is unavailable");
      }
      return window.catalyst;
    })
    .catch((err) => {
      loadPromise = null; // allow a retry on transient failure
      throw err;
    });

  return loadPromise;
}
