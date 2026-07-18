# Phase 14 Part C — React deployment to Catalyst

Companion to `PHASE_14_REPORT.md` §5. Status date: 2026-07-18.
Catalyst project: **DHRISTI** (`48361000000030003`), India (IN) DC, Development env.

> **Status legend** (same as the main report):
> **DONE** — executed + verified here (evidence inline) · **IMPLEMENTED** — code/config
> written and locally verified (build/tests/scan) · **HELD** — real artifact ready, the
> single remaining step is credit-spending or a console action, deliberately not run
> without go-ahead.
>
> Nothing below claims a cloud deployment. The frontend is fully implemented and locally
> verified; the only remaining steps are the credit-spending Slate deploy and the
> one-time console actions named in §9.

---

## 0. Item-by-item status (spec Part C, 1–9)

| # | Requirement | State |
|---|---|---|
| 1 | Inspect current Vite/React build + API URL handling | **DONE** (§1) |
| 2 | Keep secrets / `DATABASE_URL` out of `VITE_*` + the bundle | **DONE** — centralised + build-time scan, verified (§2) |
| 3 | One public API base URL → API Gateway; facade → AppSail; no AWS URL to browser | **IMPLEMENTED** (§3) |
| 4 | Prefer Slate; else Web Client Hosting | **IMPLEMENTED** (Slate primary, fallback documented) (§4) |
| 5 | Run supported CLI init/link/deploy commands | **HELD** — safe reads run; mutating/credit steps documented, not run (§5) |
| 6 | SPA fallback, asset caching, env API URL, exact CORS origin, demo badge | **IMPLEMENTED** (§6) |
| 7 | Catalyst Authentication login/session + map user → synthetic role; never trust client role | **IMPLEMENTED** (§7) |
| 8 | Deploy to dev → smoke → promote to prod | **HELD** — local build-smoke DONE; cloud deploy/smoke held (§8) |
| 9 | If prod needs payment/console approval: keep dev, document the one exact action, don't move to AWS | **DONE** (documented; §9) |

---

## 1. Current build + API URL handling (DONE)

- App: React 18 + Vite 5 in `web/` (`vite build` → `web/dist/`, content-hashed assets,
  no `base`/`basePath` set — required for Slate root serving).
- API base was read directly from `import.meta.env.VITE_API_BASE_URL` in
  `web/src/api/client.ts`. There was **no real authentication** — only a display-only
  `X-Role` / `X-Demo-Actor` header (UX simulation). This was the biggest Part C gap and is
  now closed (§7).
- Deployed request path (unchanged, correct): browser → **API Gateway** `/api/*` →
  `gateway_api` Advanced I/O function (derives identity server-side, strips client identity
  headers, mints an HMAC-signed context) → **AppSail** FastAPI. The browser never calls
  AppSail or AWS directly.

## 2. No secrets in `VITE_*` or the bundle (DONE, verified)

- **Single source:** every `VITE_*` read now lives in `web/src/config/runtime.ts`
  (`apiBaseUrl`, `authMode`, `catalystSdkUrl`, `demoBadge`, `withCredentials`,
  `mapillaryToken`). `mapillary.ts` and `client.ts` consume it. Audit surface = one file.
- **Only public values** are exposed: the API base URL, auth mode, the CDN SDK URL, the
  badge label, and the public Mapillary read token. No `DATABASE_URL`, HMAC signing secret,
  AWS URL/keys, or credential is present.
- **Build-time enforcement:** `web/scripts/check-bundle-secrets.mjs` runs on every `npm run
  build` and fails on secret-shaped strings (`postgres://`, PEM keys, `AKIA…`, any
  `*.amazonaws.com`, `ZOHO_APPSAIL_SIGNING_SECRET`, server DB env keys). Verified on the real
  build: **no secrets / no AWS URL in `dist/`**; only the expected warning that
  `.env.production` still holds the unconfigured API-base placeholder.
- **Git hygiene:** `web/.gitignore` + root `.gitignore` commit the non-secret
  `.env.development` / `.env.production` while keeping `.env`, `.env.local`, `*.local`
  ignored. Verified with `git check-ignore` (dev/prod/example → tracked; `.env`/`.local` →
  ignored).

## 3. One public API base URL → API Gateway (IMPLEMENTED)

- `web/.env.development`: `VITE_API_BASE_URL=http://localhost:8000` (FastAPI direct),
  `VITE_AUTH_MODE=offline`.
- `web/.env.production`: `VITE_API_BASE_URL=https://REPLACE-WITH-CATALYST-API-GATEWAY-ORIGIN/api`
  (intentionally invalid placeholder — the operator/CI sets the exact API Gateway origin from
  Console → API Gateway after `apig:enable`; the `/api` prefix is stripped by `gateway_api`
  via `DRISHTI_GATEWAY_PATH_PREFIX`), `VITE_AUTH_MODE=catalyst`, `VITE_API_WITH_CREDENTIALS=true`.
- **AppSail is not claimed as a native gateway/browser target.** The gateway fronts the
  `gateway_api` function, which securely invokes AppSail. **No AWS URL is ever exposed to the
  browser** (enforced by the bundle scan). The `gateway_api` facade + signed-context boundary
  are pre-existing (Part B) and interop-verified.
- **Cross-domain correctness:** Slate serves from `*.onslate.in`, functions from
  `*.catalystserverless.in`, so relative paths would break. The base URL is absolute; requests
  send `credentials:'include'`; authenticated calls attach a raw `Authorization` token from
  `catalyst.auth.generateAuthToken()` (no `Bearer` prefix — Catalyst convention).

## 4. Hosting choice (IMPLEMENTED)

- **Slate is primary** (`framework = "react-vite"`, build output `web/dist`). Web Client
  Hosting (legacy) remains the documented fallback via the `client` component in
  `catalyst.json`.
- Slate requires a **one-time console activation** (project → Slate → *Start Exploring*)
  before `slate:create`/`deploy` — recorded as a remaining action (§9), not a code gap.

## 5. CLI commands (HELD, with safe reads run)

- **Run here (safe, read-only):** `catalyst --version` (1.27.0), `whoami`
  (`prajwalbr0304@gmail.com`), `project:list` (DHRISTI active/base), `apig:status`
  (**API Gateway DISABLED**), and `--help` for `deploy` / `slate:link` / `slate:create`.
- **Held (mutating / interactive / credit-spending), documented not run:**
  `catalyst slate:create --name drishti-web --framework react-vite -ni` (scaffolds/links,
  writes the `slate` block), `catalyst slate:link` (interactive), `catalyst apig:enable`
  (disables default security rules — remote mutation), `catalyst deploy slate` ($). This
  matches the project-wide posture (Parts A/B hold all credit-spending cloud steps) and the
  safety rule that deployments need explicit go-ahead.

## 6. SPA fallback, caching, CORS, badge (IMPLEMENTED)

- **SPA deep links:** `web/public/_redirects` (`/* /index.html 200`, `/app/* /index.html
  200`) is copied into `dist/` by Vite; `web/scripts/postbuild-slate.mjs` regenerates
  `dist/.catalyst/slate-config.toml` (wiped by clean builds) with the same redirects. React
  Router additionally sends `/app` and `/app/*` → `/` for the embedded-auth SDK's legacy
  redirect. Verified present in `dist/` after build.
- **Asset caching:** Vite content-hashes `dist/assets/*` (immutable; hash busts on change);
  Slate's CDN serves them automatically, while `index.html`/`_redirects` are revalidated so
  new deploys are picked up. Slate exposes **no `_headers` mechanism**, so none is faked.
- **Environment-specific API URL:** committed `.env.development` / `.env.production` (§3).
- **Exact CORS origin:** the deployed Slate origin is whitelisted in **Console →
  Authentication → Authorized Domains** (CORS on); function code sets CORS only for
  `localhost` (production CORS is gateway-injected, never duplicated). No wildcard.
- **Badge:** `VITE_DEMO_BADGE` = "Synthetic Hackathon Demo" renders on the login gate
  (`LoginGate`) and in the shell (`SyntheticBadge`, which prefers the live server
  `environment_label` and falls back to this build-time label).

## 7. Catalyst Authentication (IMPLEMENTED)

New module `web/src/auth/`:

| File | Role |
|---|---|
| `catalystSdk.ts` | Loads `catalystWebSDK.js` (v4.6.1+) + `/__catalyst/sdk/init.js`; typed `signIn` / `isUserAuthenticated` / `generateAuthToken` / `signOut`. |
| `authClient.ts` | `AuthClient` interface with `CatalystAuthClient` (real) and `OfflineAuthClient` (dev fake) behind one contract; factory keys off `VITE_AUTH_MODE`. |
| `offline.ts` | Synthetic demo identities (localStorage-persisted) so `web` runs without a live project. |
| `types.ts` | `AuthUser` + defensive `normalizeCatalystUser` for the SDK's response shapes. |
| `roleMapping.ts` | `deriveDisplayRole` — **display-only**, mirrors the server's `resolveRole`. |
| `AuthProvider.tsx` | Session state + `useAuth` / `useAuthOptional` + `<RequireAuth>` route guard. |
| `LoginGate.tsx` | Embedded Catalyst login (catalyst mode) / synthetic role picker (offline). |

- **Gating:** `<RequireAuth>` guards every app route; the public landing page (`/`) stays
  open. Unauthenticated → login gate; error (SDK can't load off-domain) → clear error state.
- **Server owns the role.** The authenticated identity drives the *display* role only; the
  API Gateway re-derives the authoritative role server-side and strips the client `X-Role`.
  The demo-view switcher is presentation-only and never a security boundary. Disabling
  PostgreSQL RLS does not remove this app-auth requirement.
- **Resilience:** `RoleProvider` reads auth via `useAuthOptional`, so isolated component
  tests (which mount it without `AuthProvider`) still pass; a pre-set `localStorage` role is
  honored there.

## 8. Deploy → smoke → promote (local DONE; cloud HELD)

- **Local build-smoke (DONE):** `npm run build` = `tsc --noEmit` + `vite build` +
  `postbuild-slate` + `check-bundle-secrets`, all green (3600 modules; SPA config + secret
  scan pass). `npm run test` = **41/41** unit tests pass. `get_diagnostics` clean on all new
  files.
- **Cloud (HELD):** dev deploy (`catalyst deploy slate`), the post-deploy smoke
  (`infra/catalyst/pipelines/smoke_test.py` against the deployed base URL), and production
  promotion of the same immutable artifact are held for go-ahead. The CI/CD pipeline
  (`catalyst-pipelines.yaml`) already encodes dev→smoke→approve→promote.

## 9. Remaining platform actions (exact, ordered)

These are the only steps left; each is a console/credit action, not a code gap. Hosting
stays on Catalyst (never AWS).

1. **Console (one-time):** project → Slate → *Start Exploring* (activates Slate). And
   Console → Authentication → set up Native Auth + add sign-in provider(s).
2. `catalyst apig:enable` (API Gateway is currently DISABLED) + create the `/api/*` →
   `gateway_api` route; `catalyst pull` to write `catalyst-user-rules.json`.
3. Set `VITE_API_BASE_URL` to the exact API Gateway origin (`https://<project-domain>/api`)
   and rebuild (`npm --prefix web run build`).
4. Console → Authentication → Authorized Domains: add the exact Slate origin (CORS on).
5. `catalyst slate:create --name drishti-web --framework react-vite -ni` then
   `catalyst deploy slate -m "drishti web (dev)"`  **(credit-spending)**.
6. Run `python infra/catalyst/pipelines/smoke_test.py --base-url <deployed>`; on green,
   promote to production (`--production`). **If production promotion requires a
   payment/console approval, keep the working Development deployment and stop here** — that
   is the single documented remaining platform action; do not move hosting to AWS.

## 10. Files (Part C)

**New:** `web/src/config/runtime.ts`, `web/src/auth/{types,catalystSdk,offline,authClient,roleMapping,AuthProvider,LoginGate,index}.{ts,tsx}`, `web/.env.development`, `web/.env.production`, `web/public/client-package.json`, `web/scripts/{postbuild-slate,check-bundle-secrets}.mjs`, this report.

**Changed:** `web/src/api/client.ts`, `web/src/providers/RoleProvider.tsx`, `web/src/App.tsx`, `web/src/main.tsx`, `web/src/components/shell/{ProfileMenu,SyntheticBadge}.tsx`, `web/src/components/map/mapillary.ts`, `web/src/vite-env.d.ts`, `web/.env.example`, `web/.gitignore`, `.gitignore`, `web/package.json`, `infra/catalyst/client/README.md`, `infra/catalyst/README.md`, `docs/phase-reports/PHASE_14_REPORT.md`.

## 11. Honest limits

- Nothing is cloud-deployed. Matrix row 4 carries local build/test/scan evidence + artifact
  paths, not a live Slate URL or deployed component IDs.
- The production `VITE_API_BASE_URL` is a placeholder until the API Gateway origin exists
  (post `apig:enable`); the bundle scan warns until it is set.
- `generateAuthToken`/embedded-auth and Slate's cross-domain cookie/token behavior are coded
  to the current documented SDK (v4.6.1+) but can only be confirmed end-to-end once deployed
  on the Catalyst domain with Authentication set up.
- `eslint` is not installed in `web/` (pre-existing; the `lint` script cannot run here).
  TypeScript type-checking (`tsc --noEmit`) and IDE diagnostics were used instead — both clean.
