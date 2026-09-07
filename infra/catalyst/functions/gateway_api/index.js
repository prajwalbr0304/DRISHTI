'use strict';
/*
 * DRISHTI — API Gateway facade (Advanced I/O function).  Phase 14 Part B, matrix
 * rows 1/17/18, workflow inventory §8.1–8.2.
 *
 * This is the PUBLIC HTTP boundary of the deployed app. The browser (Slate) and
 * API Gateway route here. It NEVER trusts client-supplied identity: it derives
 * the user from Catalyst Authentication (user scope), strips any inbound
 * identity headers, then mints a short-lived HMAC-signed internal context and
 * forwards the request to the AppSail FastAPI service server-side. The browser
 * never talks to AppSail or AWS directly.
 *
 * Security posture:
 *   - Authenticated: relies on API Gateway auth + a user-scope Catalyst identity.
 *     If no identity is resolvable, returns 401 — UNLESS the synthetic-demo mode
 *     (DRISHTI_DEMO_AUTH=true) is on, in which case a full-access system_admin
 *     context is minted so the offline role-card demo shows live synthetic data.
 *   - Role is resolved SERVER-SIDE (never read from the request).
 *   - Signed context = base64url(JSON {user_id,email,role,scope,aud,ts,nonce,
 *     request_id}) + hex HMAC-SHA256 over the canonical string, keyed by
 *     ZOHO_APPSAIL_SIGNING_SECRET (configured as an env var, never committed).
 *     aud ('drishti-appsail') binds the context to the AppSail audience.
 *   - CORS for production origins is handled by Catalyst Authorized Domains, so
 *     this code sets CORS headers ONLY for localhost dev.
 *
 * Env vars (configured in the Catalyst console / AppSail env, never committed):
 *   ZOHO_APPSAIL_BASE_URL        - https base URL of the AppSail FastAPI service
 *   ZOHO_APPSAIL_SIGNING_SECRET  - shared HMAC secret for the internal context
 *   DRISHTI_GATEWAY_TIMEOUT_MS   - upstream timeout (default 25000; aio cap 30s)
 *   DRISHTI_GATEWAY_PATH_PREFIX  - public path prefix to strip (default /api)
 *   DRISHTI_DEMO_AUTH            - "true" enables synthetic-demo auth: no Catalyst
 *                                  session required; a full-access system_admin
 *                                  context is minted for the offline role-card
 *                                  demo. Synthetic hackathon demo ONLY.
 */
const crypto = require('crypto');
const https = require('https');
const catalyst = require('zcatalyst-sdk-node');

const CONTEXT_TTL_MS = 60 * 1000; // signed context is valid for 60s
// Identity headers a client might try to spoof — always stripped before proxying.
const STRIPPED_INBOUND_HEADERS = [
  'x-role', 'x-demo-actor', 'x-drishti-context', 'x-drishti-signature',
  'x-user-id', 'x-user-email', 'x-forwarded-user', 'authorization', 'cookie',
];

/* A seat USERNAME the demo client asks to operate as.
 *
 * DEMO MODE ONLY, and it names a seat rather than describing one. Demo auth mints
 * one full-access system_admin context for every caller, so the whole ~11,800-seat
 * establishment collapsed to a single platform-scoped identity: the seat picked in
 * the UI never reached AppSail, and an SP of Bagalkot saw all 38 districts.
 *
 * Carrying the name inside the SIGNED context fixes that without weakening the
 * boundary, for three reasons:
 *   - the browser supplies a name, never a role, district or unit;
 *   - AppSail resolves that name against its own `users` table, so the scope is
 *     still derived server-side from trusted data;
 *   - in demo mode the baseline is full platform access, so resolving a named seat
 *     can only ever NARROW what is served.
 * In the AUTHENTICATED path this is ignored entirely — the Catalyst identity is
 * authoritative there and a client-named seat must not override it.
 *
 * Conservative charset: a username, an email local part, or a demo actor like
 * `demo.sho`. Anything else is dropped rather than sanitised into something else. */
const SEAT_ACTOR_MAX_LEN = 120;
const SEAT_ACTOR_PATTERN = /^[A-Za-z0-9._@+-]+$/;

function requestedSeatActor(req) {
  const raw = req.headers['x-demo-actor'];
  const value = (Array.isArray(raw) ? raw[0] : raw || '').trim();
  if (!value || value.length > SEAT_ACTOR_MAX_LEN) return null;
  return SEAT_ACTOR_PATTERN.test(value) ? value : null;
}

function localhostCors(req, res) {
  const origin = req.headers.origin || '';
  if (/^http:\/\/localhost(:\d+)?$/.test(origin) || /^http:\/\/127\.0\.0\.1(:\d+)?$/.test(origin)) {
    res.setHeader('Access-Control-Allow-Origin', origin);
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Accept');
    if (req.method === 'OPTIONS') { res.writeHead(204); res.end(); return true; }
  }
  return false;
}

function sendJson(res, status, body) {
  res.writeHead(status, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify(body));
}

function b64url(buf) {
  return Buffer.from(buf).toString('base64')
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

/* Canonical functional roles (the ten command seats) — MUST mirror
 * services/ml/app/roles.py FUNCTIONAL_ROLES (re-exported by org/hierarchy.py).
 * AppSail re-validates the role against the same set (defence in depth), so the
 * two cannot drift silently. */
const FUNCTIONAL_ROLES = new Set([
  'dgp_state_command', 'senior_command', 'district_command',
  'sho', 'investigating_officer', 'system_admin',
]);

/* Superseded role names -> current role. A directory attribute or Catalyst role
 * may still carry an old value; translating it is safer than rejecting the seat
 * or silently defaulting it. Mirrors LEGACY_ROLE_ALIASES in app/roles.py. */
const LEGACY_ROLE_ALIASES = {
  adgp_igp_range: 'senior_command',
  sp_district_command: 'district_command',
  dysp_acp: 'district_command',
  crime_analyst: 'senior_command',
  cyber_cell: 'senior_command',
  traffic_command: 'senior_command',
  investigator: 'investigating_officer',
  supervisor: 'sho',
  analyst: 'senior_command',
  policymaker: 'senior_command',
  super_admin: 'system_admin',
};

/* Least-privilege default seat when no DRISHTI role is asserted. */
const DEFAULT_ROLE = 'investigating_officer';

/* Rank / assignment label -> [functional_role, scope_level]. Mirrors the
 * synthetic establishment catalogue in org/hierarchy.py (_CATALOG). Keys are
 * normalized (lowercase, single-spaced). */
/* Rank/assignment label -> [functional_role, scope_type].
 *
 * The second element is now a SCOPE TYPE, not a geographic level: an ADGP heads a
 * functional wing (state-wide, crime-head narrowed) while an IGP/DIG commands a
 * range of districts. Both are `senior_command`; only the scope differs, which is
 * the distinction the previous single 'adgp_igp_range' role could not express. */
const RANK_MAP = {
  'dgp': ['dgp_state_command', 'state'],
  'director general of police': ['dgp_state_command', 'state'],
  'dg igp': ['dgp_state_command', 'state'],
  // ADGP -> functional wing. IGP/DIG -> geographic range.
  'adgp': ['senior_command', 'wing'],
  'additional director general': ['senior_command', 'wing'],
  'igp': ['senior_command', 'range'],
  'inspector general': ['senior_command', 'range'],
  'dig': ['senior_command', 'range'],
  'deputy inspector general': ['senior_command', 'range'],
  // Staff cells are wings under an ADGP, not roles of their own.
  'crime analyst': ['senior_command', 'wing'], 'analyst': ['senior_command', 'wing'],
  'scrb': ['senior_command', 'wing'], 'policy': ['senior_command', 'wing'],
  'cyber cell': ['senior_command', 'wing'], 'cen': ['senior_command', 'wing'],
  'cyber crime': ['senior_command', 'wing'],
  'traffic': ['senior_command', 'wing'], 'traffic police': ['senior_command', 'wing'],
  'intelligence': ['senior_command', 'wing'], 'cid': ['senior_command', 'wing'],
  // District level: SP for a district, CP for a city Commissionerate.
  'sp': ['district_command', 'district'],
  'superintendent of police': ['district_command', 'district'],
  'addl sp': ['district_command', 'district'],
  'additional superintendent of police': ['district_command', 'district'],
  'cp': ['district_command', 'commissionerate'],
  'commissioner of police': ['district_command', 'commissionerate'],
  'dcp': ['district_command', 'district'],
  'deputy commissioner of police': ['district_command', 'district'],
  // Sub-division has no data model yet, so these resolve to district command.
  'dy sp': ['district_command', 'district'], 'asp': ['district_command', 'district'],
  'acp': ['district_command', 'district'], 'ci': ['district_command', 'district'],
  'circle inspector': ['district_command', 'district'],
  // Station.
  'sho': ['sho', 'station'], 'station house officer': ['sho', 'station'],
  'station chief': ['sho', 'station'], 'pi': ['sho', 'station'],
  'police inspector': ['sho', 'station'], 'inspector': ['sho', 'station'],
  // Field officers.
  'io': ['investigating_officer', 'assigned_case'],
  'investigating officer': ['investigating_officer', 'assigned_case'],
  'psi': ['investigating_officer', 'assigned_case'],
  'police sub inspector': ['investigating_officer', 'assigned_case'],
  'asi': ['investigating_officer', 'assigned_case'],
  'assistant sub inspector': ['investigating_officer', 'assigned_case'],
  'head constable': ['investigating_officer', 'assigned_case'],
  'police constable': ['investigating_officer', 'assigned_case'],
  'system administrator': ['system_admin', 'platform'],
  'admin': ['system_admin', 'platform'],
};

/* Default scope_type when a rank gives no refinement.
 *
 * Only the two inherently unpinned seats get a real default. Every other role
 * resolves to 'unresolved', which the server treats as "no posting on record" and
 * therefore NO data — never state-wide. Defaulting a station seat to anything
 * wider would hand it the whole force. */
const ROLE_DEFAULT_SCOPE = {
  dgp_state_command: 'state',
  system_admin: 'platform',
  senior_command: 'unresolved',
  district_command: 'unresolved',
  sho: 'unresolved',
  investigating_officer: 'unresolved',
};

function normLabel(s) {
  return String(s == null ? '' : s).toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
}

/* Parse a trusted numeric scope attribute. Returns:
 *   {value:int}     a valid positive id;
 *   {value:null}    the attribute is absent (no restriction at that level);
 *   {invalid:true}  the attribute is PRESENT but not a valid id (ambiguous). */
function scopeInt(raw) {
  if (raw === undefined || raw === null || raw === '') return { value: null };
  const n = parseInt(raw, 10);
  if (!Number.isFinite(n) || n <= 0 || String(n) !== String(raw).trim()) return { invalid: true };
  return { value: n };
}

/* Resolve an authenticated Catalyst user to a functional role + organizational
 * scope, SERVER-SIDE ONLY (never from a request header). Priority:
 *   1. explicit DRISHTI role assignment (custom attribute `drishti_role`) — an
 *      unrecognized value here is REJECTED (unknown/ambiguous role);
 *   2. the Catalyst role_name mapped through RANK_MAP;
 *   3. least-privilege default (investigating_officer / assigned_case) when no
 *      DRISHTI role is asserted — a documented safe default, not an ambiguous
 *      coercion.
 * district_id / unit_id come only from trusted custom attributes; a present-but-
 * malformed scope value is REJECTED. Returns {role,scope_level,district_id,
 * unit_id} or {rejected:<reason>}. */
function resolveIdentity(user) {
  const attrs = (user && (user.custom_fields || {})) || {};
  const roleDetails = (user && user.role_details) || {};
  let role = null, scopeLevel = null;

  const explicit = normLabel(user && (user.drishti_role || attrs.drishti_role));
  if (explicit) {
    const compact = explicit.replace(/ /g, '_');
    if (FUNCTIONAL_ROLES.has(compact)) role = compact;
    else if (LEGACY_ROLE_ALIASES[compact]) role = LEGACY_ROLE_ALIASES[compact];
    else if (RANK_MAP[explicit]) [role, scopeLevel] = RANK_MAP[explicit];
    else return { rejected: 'unknown_or_ambiguous_role' };  // asserted but invalid
  }
  if (!role) {
    const rn = normLabel(roleDetails.role_name);
    const rnCompact = rn.replace(/ /g, '_');
    if (rn && FUNCTIONAL_ROLES.has(rnCompact)) role = rnCompact;
    else if (rn && LEGACY_ROLE_ALIASES[rnCompact]) role = LEGACY_ROLE_ALIASES[rnCompact];
    else if (rn && RANK_MAP[rn]) [role, scopeLevel] = RANK_MAP[rn];
    // an unrecognized built-in role_name is NOT a DRISHTI assertion -> default below
  }
  if (!role) { role = DEFAULT_ROLE; scopeLevel = ROLE_DEFAULT_SCOPE[DEFAULT_ROLE]; }
  if (!scopeLevel) scopeLevel = ROLE_DEFAULT_SCOPE[role] || 'assigned_case';

  const district = scopeInt(user && (user.district_id !== undefined ? user.district_id : attrs.district_id));
  const unit = scopeInt(user && (user.unit_id !== undefined ? user.unit_id : attrs.unit_id));
  if (district.invalid || unit.invalid) return { rejected: 'ambiguous_scope' };

  return { role, scope_level: scopeLevel, district_id: district.value, unit_id: unit.value };
}

function signContext(ctx, secret) {
  const payload = b64url(JSON.stringify(ctx));
  const mac = crypto.createHmac('sha256', secret).update(payload).digest('hex');
  return { payload, signature: mac };
}

function readRawBody(req) {
  // Some runtimes pre-parse the body onto req.body; normalize it once.
  const b = req.body;
  if (b !== undefined && b !== null) {
    if (Buffer.isBuffer(b)) return Promise.resolve(b);
    if (typeof b === 'string') return Promise.resolve(Buffer.from(b));
    if (typeof b === 'object') return Promise.resolve(Buffer.from(JSON.stringify(b)));
    return Promise.resolve(Buffer.from(String(b)));
  }
  // Catalyst Advanced I/O does NOT set req.body — it hands us the raw stream.
  // Drain it FULLY into a Buffer. This MUST run before any await that lets the
  // Catalyst SDK consume the stream, or only a fragment survives.
  return new Promise((resolve) => {
    const chunks = [];
    req.on('data', (c) => chunks.push(Buffer.isBuffer(c) ? c : Buffer.from(c)));
    req.on('end', () => resolve(Buffer.concat(chunks)));
    req.on('error', () => resolve(Buffer.concat(chunks)));
  });
}

module.exports = async (req, res) => {
  if (localhostCors(req, res) && req.method === 'OPTIONS') return;

  const requestId = (req.headers['x-request-id'] || crypto.randomUUID());
  const baseUrl = process.env.ZOHO_APPSAIL_BASE_URL;
  const secret = process.env.ZOHO_APPSAIL_SIGNING_SECRET;
  if (!baseUrl || !secret) {
    return sendJson(res, 503, { error: 'gateway_not_configured', request_id: requestId });
  }

  // Resolve the upstream path once (strip the public prefix).
  const prefix = process.env.DRISHTI_GATEWAY_PATH_PREFIX || '/api';
  const parsed = new URL(req.url, `https://${req.headers.host || 'localhost'}`);
  let upstreamPath = parsed.pathname;
  if (upstreamPath.startsWith(prefix)) upstreamPath = upstreamPath.slice(prefix.length) || '/';

  // 0. Health passthrough: liveness/readiness MUST be reachable without a
  //    Catalyst session (the API Gateway 'drishti-health' route is No-Auth and
  //    AppSail exempts /health/* from the signed-context requirement). Proxy the
  //    GET directly — no identity, no signed context, non-sensitive.
  if (upstreamPath === '/health' || upstreamPath.startsWith('/health/')) {
    const healthUrl = baseUrl.replace(/\/+$/, '') + upstreamPath + (parsed.search || '');
    const hac = new AbortController();
    const htimer = setTimeout(() => hac.abort(), 10000);
    try {
      const up = await fetch(healthUrl, { method: 'GET', signal: hac.signal });
      const txt = await up.text();
      res.writeHead(up.status, {
        'Content-Type': up.headers.get('content-type') || 'application/json',
        'X-Request-ID': requestId,
      });
      res.end(txt);
    } catch (e) {
      sendJson(res, 502, { error: 'upstream_unavailable', request_id: requestId });
    } finally {
      clearTimeout(htimer);
    }
    return;
  }

  // 0b. Read the request body NOW — BEFORE catalyst.initialize()/getCurrentUser()
  //     touch the request. The Catalyst SDK drains the raw request stream, so
  //     reading the body later returned only a 2-byte fragment and every
  //     POST/PUT forwarded a truncated body (AppSail rejected it with 422).
  //     Advanced I/O does not pre-parse req.body, so we drain the stream here.
  const method = req.method || 'GET';
  const hasBody = !['GET', 'HEAD', 'OPTIONS'].includes(method);
  const bodyBuf = hasBody ? await readRawBody(req) : undefined;

  // 1. Resolve identity from Catalyst Authentication (USER scope only).
  let user = null;
  try {
    const app = catalyst.initialize(req);
    user = await app.userManagement().getCurrentUser();
  } catch (e) {
    user = null;
  }

  // 2. Resolve the server-trusted functional role + organizational scope. An
  //    asserted-but-unknown role or a malformed scope is REJECTED (403) rather
  //    than silently coerced (Prompt 21 §E.2).
  let identity;
  if (user && user.user_id) {
    identity = resolveIdentity(user);
    if (identity.rejected) {
      return sendJson(res, 403, { error: 'role_scope_unresolved',
        reason: identity.rejected, request_id: requestId });
    }
  } else if (String(process.env.DRISHTI_DEMO_AUTH || '').toLowerCase() === 'true') {
    // DEMO AUTH (synthetic hackathon only, DRISHTI_DEMO_AUTH=true). The offline
    // role-card login replaces the embedded Catalyst IAM widget, so requests
    // carry NO Catalyst session. Mint a full-access synthetic super_admin context
    // so the role-card demo shows live data. The HMAC signed-context contract to
    // AppSail is UNCHANGED — only the identity SOURCE differs (the gateway, which
    // alone holds the signing secret, is still the sole minter). Data is
    // synthetic and every write stays behind the AppSail synthetic-DB guard. The
    // role card selects the presentation workspace CLIENT-SIDE; the server serves
    // the full demo dataset. Never enable outside the synthetic demo.
    //
    // The seat the client asks to operate as rides along so AppSail can resolve
    // its REAL scope from the users table (see requestedSeatActor). Without it
    // every seat resolved to this platform-wide identity and the district
    // selector offered all 38 districts to an SP posted to one.
    identity = { role: 'system_admin', scope_level: 'state', district_id: null, unit_id: null,
                 actor: requestedSeatActor(req) };
    user = { user_id: 'demo-system-admin', email_id: 'demo.system_admin@drishti.local' };
  } else {
    return sendJson(res, 401, { error: 'authentication_required', request_id: requestId });
  }

  // 3. Mint a short-lived signed internal context. Role + scope are DERIVED
  //    server-side here and signed; AppSail re-validates the role and trusts the
  //    signed scope, never a browser-supplied role/district/unit header.
  const now = Date.now();
  const ctx = {
    user_id: String(user.user_id),
    email: user.email_id || '',
    role: identity.role,
    scope_level: identity.scope_level,
    district_id: identity.district_id,
    unit_id: identity.unit_id,
    // Demo-mode seat request only; absent (null) on the authenticated path, where
    // resolveIdentity() has already produced the trusted role + scope.
    actor: identity.actor || null,
    scope: 'gateway',
    aud: 'drishti-appsail',
    ts: now,
    exp: now + CONTEXT_TTL_MS,
    nonce: crypto.randomBytes(12).toString('hex'),
    request_id: requestId,
  };
  const { payload, signature } = signContext(ctx, secret);

  // 4. Build the upstream request: strip client identity headers, forward the rest.
  //    (upstreamPath was resolved above.)
  const upstreamUrl = baseUrl.replace(/\/+$/, '') + upstreamPath + (parsed.search || '');

  const fwdHeaders = { 'Content-Type': req.headers['content-type'] || 'application/json' };
  for (const [k, v] of Object.entries(req.headers)) {
    const lk = k.toLowerCase();
    if (STRIPPED_INBOUND_HEADERS.includes(lk)) continue;      // never forward spoofable identity
    if (lk.startsWith('x-drishti-')) continue;                 // reserved internal namespace
    // Hop-by-hop / body-framing headers must NOT be forwarded: undici sets its
    // own Content-Length from the buffered body, so a stale inbound
    // Content-Length or a Transfer-Encoding here produces invalid request
    // framing and the upstream resets the connection — which is why every
    // request WITH A BODY (POST/PUT/PATCH) failed with 502 while GET worked.
    // Also strip accept-encoding: we forward the upstream response body as raw
    // bytes (no decompression), so the upstream must not gzip it or the browser
    // would receive compressed bytes without a Content-Encoding header.
    if (['host', 'content-length', 'connection', 'transfer-encoding',
         'keep-alive', 'expect', 'upgrade', 'te', 'accept-encoding'].includes(lk)) continue;
    fwdHeaders[k] = v;
  }
  fwdHeaders['X-DRISHTI-Context'] = payload;
  fwdHeaders['X-DRISHTI-Signature'] = signature;
  fwdHeaders['X-Request-ID'] = requestId;

  // (method / hasBody / bodyBuf were captured at the top, before the stream was drained.)

  // 5. Proxy to AppSail via Node's core https module (NOT global fetch): the
  //    runtime's fetch JSON-re-encoded a string body (double-encoding the JSON
  //    so AppSail rejected it 422). https.request writes the raw body bytes
  //    verbatim with an exact Content-Length.
  const timeoutMs = parseInt(process.env.DRISHTI_GATEWAY_TIMEOUT_MS || '25000', 10);
  if (bodyBuf !== undefined) fwdHeaders['Content-Length'] = String(bodyBuf.length);
  try {
    const u = new URL(upstreamUrl);
    const upstream = await new Promise((resolve, reject) => {
      const r = https.request(
        { method, hostname: u.hostname, port: u.port || 443,
          path: u.pathname + u.search, headers: fwdHeaders, timeout: timeoutMs },
        (resp) => {
          const chunks = [];
          resp.on('data', (c) => chunks.push(c));
          resp.on('end', () => resolve({
            status: resp.statusCode || 502,
            contentType: resp.headers['content-type'] || 'application/json',
            body: Buffer.concat(chunks),
          }));
        });
      r.on('error', reject);
      r.on('timeout', () => r.destroy(Object.assign(new Error('timeout'), { _timedOut: true })));
      if (bodyBuf !== undefined) r.write(bodyBuf);   // raw bytes, verbatim
      r.end();
    });
    res.writeHead(upstream.status, { 'Content-Type': upstream.contentType, 'X-Request-ID': requestId });
    res.end(upstream.body);
  } catch (err) {
    const timedOut = !!(err && err._timedOut);
    try {
      console.error('[gateway] upstream request failed', method, upstreamPath,
        'code=' + (err && err.code), 'msg=' + (err && err.message));
    } catch (_e) { /* never let logging mask the response */ }
    sendJson(res, timedOut ? 504 : 502, {
      error: timedOut ? 'upstream_timeout' : 'upstream_unavailable',
      request_id: requestId,
    });
  }
};
