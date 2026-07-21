import type { Page, Route, Request } from "@playwright/test";
import * as fx from "../fixtures";

/* ============================================================================
   LOCAL-target network stubbing.

   In the "local" E2E target we never touch a backend: every DRISHTI API call
   (the app talks to VITE_API_BASE_URL, default http://localhost:8000) is
   intercepted with Playwright route interception and fulfilled with the
   deterministic fixtures. The app bundle is served by `vite preview`, so the
   API origin is cross-origin to the app origin (localhost:4173) — that means we
   must answer the CORS preflight and echo CORS headers on every fulfilment.

   In the "live" target (Prompt 23) this module is NOT installed: the identical
   journey specs run against the real Catalyst gateway at E2E_BASE_URL.
   ========================================================================== */

/** API origin the app calls (must match the build's VITE_API_BASE_URL). */
export const API_ORIGIN = process.env.E2E_API_ORIGIN ?? "http://localhost:8000";

/** Request headers the typed client sends (client.ts) — allowed in preflight. */
const ALLOW_HEADERS = [
  "Content-Type",
  "Accept",
  "Authorization",
  "X-Role",
  "X-Demo-Actor",
  "X-Request-ID",
  "X-Disaster-District",
  "X-Idempotency-Key",
  "If-Match",
].join(", ");

function corsHeaders(request: Request): Record<string, string> {
  const origin = request.headers()["origin"];
  if (origin) {
    return {
      "access-control-allow-origin": origin,
      "access-control-allow-credentials": "true",
      vary: "Origin",
    };
  }
  return { "access-control-allow-origin": "*" };
}

function preflightHeaders(request: Request): Record<string, string> {
  return {
    ...corsHeaders(request),
    "access-control-allow-methods": "GET,POST,PUT,PATCH,DELETE,OPTIONS",
    "access-control-allow-headers": ALLOW_HEADERS,
    "access-control-max-age": "600",
  };
}

async function fulfillJson(route: Route, request: Request, body: unknown, status = 200): Promise<void> {
  await route.fulfill({
    status,
    headers: { "content-type": "application/json", ...corsHeaders(request) },
    body: JSON.stringify(body),
  });
}

/* --------------------------------------------------------------------------
   Route table — matched by METHOD + PATHNAME against the server contract.
   Ordered specific-first; the first match wins, else the kitchen-sink default.
   ------------------------------------------------------------------------ */
interface RouteRule {
  method: string;
  test: RegExp;
  body: unknown;
  status?: number;
}

const RULES: RouteRule[] = [
  // global shell
  { method: "GET", test: /^\/health\/?$/, body: fx.health },
  { method: "GET", test: /^\/intake\/status\/?$/, body: fx.intakeStatus },
  { method: "GET", test: /^\/geo\/alerts\/?$/, body: fx.geoAlerts },

  // intake
  { method: "GET", test: /^\/intake\/drafts\/?$/, body: fx.intakeDrafts },
  { method: "POST", test: /^\/intake\/drafts\/?$/, body: fx.intakeDraft },
  { method: "GET", test: /^\/intake\/lookups\/?$/, body: fx.intakeLookups },
  { method: "GET", test: /^\/intake\/workflow\/?$/, body: fx.intakeWorkflow },
  { method: "GET", test: /^\/intake\/drafts\/[^/]+\/activity\/?$/, body: [] },
  { method: "GET", test: /^\/intake\/drafts\/[^/]+\/?$/, body: fx.intakeDraft },

  // cases
  { method: "GET", test: /^\/cases\/filters\/?$/, body: fx.caseFilters },
  { method: "GET", test: /^\/cases\/caseload\/?$/, body: fx.kitchenSink },
  { method: "GET", test: /^\/cases\/[0-9]+\/detail\/?$/, body: fx.caseDetail },
  { method: "GET", test: /^\/cases\/[0-9]+\/evidence\/?$/, body: { available: true, items: [] } },
  { method: "GET", test: /^\/cases\/?$/, body: fx.caseList },

  // evidence
  { method: "GET", test: /^\/evidence\/status\/?$/, body: fx.evidenceStatus },
  { method: "GET", test: /^\/evidence\/lookups\/?$/, body: fx.evidenceLookups },
  { method: "GET", test: /^\/evidence\/items\/?$/, body: fx.evidenceList },

  // ask
  { method: "POST", test: /^\/chat\/ask\/?$/, body: fx.askGrounded },
  { method: "GET", test: /^\/chat\/sessions\/?$/, body: fx.chatSessionsEmpty },
  { method: "GET", test: /^\/chat\/capabilities\/?$/, body: fx.chatCapabilities },

  // board
  { method: "GET", test: /^\/boards\/meta\/object-kinds\/?$/, body: fx.boardObjectKinds },
  { method: "GET", test: /^\/boards\/?$/, body: fx.boardList },
  { method: "GET", test: /^\/boards\/[0-9]+\/activity\/?$/, body: fx.boardActivity },
  { method: "GET", test: /^\/boards\/[0-9]+\/diffs\/?$/, body: [] },
  { method: "GET", test: /^\/boards\/[0-9]+\/presence\/?$/, body: fx.boardPresence },
  { method: "POST", test: /^\/boards\/[0-9]+\/presence\/?$/, body: fx.boardPresence },
  { method: "GET", test: /^\/boards\/[0-9]+\/?$/, body: fx.boardDetail },
  { method: "POST", test: /^\/boards\/?$/, body: fx.boardDetail },

  // emergency response
  { method: "GET", test: /^\/disaster\/overview\/?$/, body: fx.disasterOverview },
  { method: "GET", test: /^\/disaster\/alerts\/?$/, body: fx.disasterAlerts },
  { method: "GET", test: /^\/disaster\/hazard-types\/?$/, body: fx.disasterHazardTypes },
];

function match(method: string, pathname: string): RouteRule | undefined {
  return RULES.find((r) => r.method === method && r.test.test(pathname));
}

/**
 * Install the deterministic local backend. Every request to the API origin is
 * fulfilled from the fixtures (with CORS); preflights are answered. Unknown
 * endpoints get the permissive kitchen-sink default so incidental calls render
 * honest empty states instead of throwing.
 */
export async function installLocalStubs(page: Page): Promise<void> {
  await page.route(
    (url) => url.origin === API_ORIGIN,
    async (route) => {
      const request = route.request();
      const method = request.method();
      if (method === "OPTIONS") {
        await route.fulfill({ status: 204, headers: preflightHeaders(request) });
        return;
      }
      const pathname = new URL(request.url()).pathname;
      const rule = match(method, pathname);
      await fulfillJson(route, request, rule ? rule.body : fx.kitchenSink, rule?.status ?? 200);
    },
  );
}

/* --------------------------------------------------------------------------
   Per-spec overrides. Registered AFTER installLocalStubs so they win (later
   Playwright handlers take precedence). Use them to force loading / empty /
   error / stale states for a single endpoint while everything else stays
   deterministic. Each helper still speaks CORS.
   ------------------------------------------------------------------------ */

type UrlMatcher = string | RegExp | ((url: URL) => boolean);

/** Fulfil a matching endpoint with a fixed JSON body (default 200). */
export async function overrideJson(
  page: Page,
  matcher: UrlMatcher,
  body: unknown,
  status = 200,
): Promise<void> {
  await page.route(matcher, async (route) => {
    const request = route.request();
    if (request.method() === "OPTIONS") {
      await route.fulfill({ status: 204, headers: preflightHeaders(request) });
      return;
    }
    await fulfillJson(route, request, body, status);
  });
}

/** Fulfil a matching endpoint with an error status (default 500). */
export async function overrideError(
  page: Page,
  matcher: UrlMatcher,
  status = 500,
  detail = "Synthetic E2E failure",
): Promise<void> {
  await overrideJson(page, matcher, { detail }, status);
}

/** Fulfil a matching endpoint after a delay (to exercise the loading state). */
export async function overrideDelayedJson(
  page: Page,
  matcher: UrlMatcher,
  body: unknown,
  delayMs: number,
): Promise<void> {
  await page.route(matcher, async (route) => {
    const request = route.request();
    if (request.method() === "OPTIONS") {
      await route.fulfill({ status: 204, headers: preflightHeaders(request) });
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, delayMs));
    await fulfillJson(route, request, body, 200);
  });
}

/** Path predicate helper: exact pathname match on the API origin. */
export function pathIs(pathname: string): (url: URL) => boolean {
  return (url) => url.origin === API_ORIGIN && url.pathname === pathname;
}
