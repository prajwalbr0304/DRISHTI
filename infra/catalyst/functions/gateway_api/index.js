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
 *   - Authenticated: relies on API Gateway auth = required + a user-scope
 *     Catalyst identity. If no identity is resolvable, returns 401.
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

/* Map an authenticated Catalyst user to a synthetic demo role. Server-side only.
 * Real role mapping belongs in Data Store config; this default keeps the facade
 * fail-safe (least privilege) when no explicit mapping row exists. */
function resolveRole(user) {
  const roleField = (user && (user.role_details && user.role_details.role_name)) || '';
  if (/admin|super/i.test(roleField)) return 'admin';
  if (/supervisor|sho|inspector/i.test(roleField)) return 'supervisor';
  return 'investigator';
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

  // 1. Resolve identity from Catalyst Authentication (USER scope only).
  let user = null;
  try {
    const app = catalyst.initialize(req);
    user = await app.userManagement().getCurrentUser();
  } catch (e) {
    user = null;
  }
  if (!user || !user.user_id) {
    return sendJson(res, 401, { error: 'authentication_required', request_id: requestId });
  }

  // 2. Mint a short-lived signed internal context (identity is derived, not trusted).
  const now = Date.now();
  const ctx = {
    user_id: String(user.user_id),
    email: user.email_id || '',
    role: resolveRole(user),
    scope: 'gateway',
    aud: 'drishti-appsail',
    ts: now,
    exp: now + CONTEXT_TTL_MS,
    nonce: crypto.randomBytes(12).toString('hex'),
    request_id: requestId,
  };
  const { payload, signature } = signContext(ctx, secret);

  // 3. Build the upstream request: strip client identity headers, forward the rest.
  const prefix = process.env.DRISHTI_GATEWAY_PATH_PREFIX || '/api';
  const parsed = new URL(req.url, `https://${req.headers.host || 'localhost'}`);
  let upstreamPath = parsed.pathname;
  if (upstreamPath.startsWith(prefix)) upstreamPath = upstreamPath.slice(prefix.length) || '/';
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

  // 4. Proxy to AppSail with a bounded timeout (Advanced I/O caps at 30s).
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
