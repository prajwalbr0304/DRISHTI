# infra/catalyst/api-gateway — routing, auth, throttling (Phase 14 Part B, row 18)

Catalyst API Gateway is the routing/auth/throttling layer in front of the
Serverless Functions. `catalyst apig:enable` turns it on and **disables the
default Security Rules**, so functions become unreachable until routes are
declared — every public path must be listed.

> **Deploy status:** SCAFFOLDED. `routes.json` is the reviewed route design.
> `catalyst apig:enable` + Console route creation are held for go-ahead; then
> `catalyst pull` writes the canonical `catalyst-user-rules.json` here.

## Design

- `/api/*` → `gateway_api` (auth **required**, sliding-window throttle
  600 rpm general / 120 rpm per-IP). This is the single authenticated public
  entry; `gateway_api` derives identity from Catalyst Authentication, strips
  client identity headers, and invokes AppSail with a signed context.
- `/api/public/health` → `gateway_api` (auth optional, low throttle) for an
  unauthenticated liveness passthrough.

AppSail is **not** a documented native gateway target, so the gateway fronts the
`gateway_api` function facade, which securely invokes AppSail (report §8.1).

## CORS

The exact deployed frontend origin is whitelisted in **Console → Authentication →
Authorized Domains** (CORS toggle on). Function code never sets CORS headers for
production origins (Catalyst injects them; duplicate headers break browsers);
`gateway_api` sets CORS only for `localhost` during dev.

## Throttling → client behavior

Exceeding a limit returns `429`. The web client retries with exponential backoff
(1s/2s/4s). Throttle limits are tuned in the Console after observing real usage.
