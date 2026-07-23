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
 *     (DRISHTI_DEMO_AUTH=true) is on, in which case a full-access super_admin
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
 *                                  session required; a full-access super_admin
 *                                  context is minted for the offline role-card
 *                                  demo. Synthetic hackathon demo ONLY.
 */
const crypto = require('crypto');
const catalyst = require('zcatalyst-sdk-node');

const CONTEXT_TTL_MS = 60 * 1000; // signed context is valid for 60s
// Identity headers a client might try to spoof — always stripped before proxying.
const STRIPPED_INBOUND_HEADERS = [
  'x-role', 'x-demo-actor', 'x-drishti-context', 'x-drishti-signature',
  'x-user-id', 'x-user-email', 'x-forwarded-user', 'authorization', 'cookie',
];

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

/* Canonical six functional roles — MUST mirror
 * services/ml/app/org/hierarchy.py FUNCTIONAL_ROLES. AppSail re-validates the
 * role against the same set (defence in depth), so the two cannot drift silently. */
const FUNCTIONAL_ROLES = new Set([
  'investigator', 'analyst', 'supervisor', 'policymaker',
  'disaster_coordinator', 'super_admin',
]);

/* Rank / assignment label -> [functional_role, scope_level]. Mirrors the
 * synthetic establishment catalogue in org/hierarchy.py (_CATALOG). Keys are
 * normalized (lowercase, single-spaced). */
const RANK_MAP = {
  'dgp': ['supervisor', 'state'], 'director general of police': ['supervisor', 'state'],
  'adgp': ['supervisor', 'state'], 'igp': ['supervisor', 'range'],
  'dig': ['supervisor', 'range'], 'sp': ['supervisor', 'district'],
  'superintendent of police': ['supervisor', 'district'], 'dcp': ['supervisor', 'district'],
  'addl sp': ['supervisor', 'district'], 'dy sp': ['supervisor', 'subdivision'],
  'asp': ['supervisor', 'subdivision'], 'acp': ['supervisor', 'subdivision'],
  'ci': ['supervisor', 'subdivision'], 'circle inspector': ['supervisor', 'subdivision'],
  'sho': ['supervisor', 'station'], 'station house officer': ['supervisor', 'station'],
  'station chief': ['supervisor', 'station'], 'pi': ['supervisor', 'station'],
  'police inspector': ['supervisor', 'station'], 'inspector': ['supervisor', 'station'],
  'io': ['investigator', 'assigned_case'], 'investigating officer': ['investigator', 'assigned_case'],
  'psi': ['investigator', 'assigned_case'], 'asi': ['investigator', 'assigned_case'],
  'head constable': ['investigator', 'assigned_case'], 'police constable': ['investigator', 'assigned_case'],
  'crime analyst': ['analyst', 'district'], 'analyst': ['analyst', 'district'],
  'scrb': ['policymaker', 'state'], 'policy': ['policymaker', 'state'],
  'ddma': ['disaster_coordinator', 'district'], 'disaster coordinator': ['disaster_coordinator', 'district'],
  'system administrator': ['super_admin', 'state'], 'admin': ['super_admin', 'state'],
};

const ROLE_DEFAULT_SCOPE = {
  super_admin: 'state', policymaker: 'state', supervisor: 'district',
  analyst: 'district', disaster_coordinator: 'district', investigator: 'assigned_case',
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
 *   3. least-privilege default (investigator / assigned_case) when no DRISHTI
 *      role is asserted — a documented safe default, not an ambiguous coercion.
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
    else if (RANK_MAP[explicit]) [role, scopeLevel] = RANK_MAP[explicit];
    else return { rejected: 'unknown_or_ambiguous_role' };  // asserted but invalid
  }
  if (!role) {
    const rn = normLabel(roleDetails.role_name);
    const rnCompact = rn.replace(/ /g, '_');
    if (rn && FUNCTIONAL_ROLES.has(rnCompact)) role = rnCompact;
    else if (rn && RANK_MAP[rn]) [role, scopeLevel] = RANK_MAP[rn];
    // an unrecognized built-in role_name is NOT a DRISHTI assertion -> default below
  }
  if (!role) { role = 'investigator'; scopeLevel = 'assigned_case'; }
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

async function readBody(req) {
  if (req.body && typeof req.body === 'object') return JSON.stringify(req.body);
  if (typeof req.body === 'string') return req.body;
  return await new Promise((resolve) => {
    let data = '';
    req.on('data', (c) => { data += c; });
    req.on('end', () => resolve(data));
    req.on('error', () => resolve(''));
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
    identity = { role: 'super_admin', scope_level: 'state', district_id: null, unit_id: null };
    user = { user_id: 'demo-super-admin', email_id: 'demo.super_admin@drishti.local' };
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
    if (['host', 'content-length', 'connection'].includes(lk)) continue;
    fwdHeaders[k] = v;
  }
  fwdHeaders['X-DRISHTI-Context'] = payload;
  fwdHeaders['X-DRISHTI-Signature'] = signature;
  fwdHeaders['X-Request-ID'] = requestId;

  const method = req.method || 'GET';
  const hasBody = !['GET', 'HEAD', 'OPTIONS'].includes(method);
  const body = hasBody ? await readBody(req) : undefined;

  // 5. Proxy to AppSail with a bounded timeout (Advanced I/O caps at 30s).
  const timeoutMs = parseInt(process.env.DRISHTI_GATEWAY_TIMEOUT_MS || '25000', 10);
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), timeoutMs);
  try {
    const upstream = await fetch(upstreamUrl, { method, headers: fwdHeaders, body, signal: ac.signal });
    const text = await upstream.text();
    res.writeHead(upstream.status, {
      'Content-Type': upstream.headers.get('content-type') || 'application/json',
      'X-Request-ID': requestId,
    });
    res.end(text);
  } catch (err) {
    const timedOut = err && err.name === 'AbortError';
    sendJson(res, timedOut ? 504 : 502, {
      error: timedOut ? 'upstream_timeout' : 'upstream_unavailable',
      request_id: requestId,
    });
  } finally {
    clearTimeout(timer);
  }
};
