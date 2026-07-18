'use strict';
/*
 * DRISHTI — shared helpers for event/cron functions (reference copy).
 *
 * NOTE ON DEPLOYMENT: Catalyst deploys each function folder independently and
 * does NOT bundle sibling folders, so this file is a REFERENCE implementation.
 * Each function inlines the tiny signing/dispatch helpers it needs (they are a
 * few lines). Keeping one annotated copy here prevents the inlined versions
 * from drifting and documents the internal AppSail trust contract in one place.
 *
 * Internal service context (event/cron/job -> AppSail):
 *   base64url(JSON {scope:'service', aud:'drishti-appsail', source, ts, exp,
 *                   nonce, request_id})
 *   + hex HMAC-SHA256(payload, ZOHO_APPSAIL_SIGNING_SECRET)
 * AppSail verifies signature + scope + expiry + nonce before trusting it. This
 * is the same secret used by the gateway facade, with scope='service' so the
 * FastAPI side can distinguish user-originated calls from internal ones.
 */
const crypto = require('crypto');

const SERVICE_CONTEXT_TTL_MS = 60 * 1000;

function b64url(buf) {
  return Buffer.from(buf).toString('base64')
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

/** Mint a signed service context for an internal AppSail call. */
function signServiceContext(source, secret, requestId) {
  const now = Date.now();
  const ctx = {
    scope: 'service',
    aud: 'drishti-appsail',
    source,
    ts: now,
    exp: now + SERVICE_CONTEXT_TTL_MS,
    nonce: crypto.randomBytes(12).toString('hex'),
    request_id: requestId || crypto.randomUUID(),
  };
  const payload = b64url(JSON.stringify(ctx));
  const signature = crypto.createHmac('sha256', secret).update(payload).digest('hex');
  return { payload, signature, ctx };
}

/** Normalise the Catalyst Signals envelope into a flat list of event data. */
function parseSignalEvents(event) {
  const events = (event && Array.isArray(event.events)) ? event.events : [];
  return events.map((e) => ({
    id: e.id,
    data: e.data || {},
    time_in_ms: e.time_in_ms,
    api_name: e.event_config && e.event_config.api_name,
    attempt: event.attempt || 1,
  }));
}

/**
 * POST a data-minimized payload to an AppSail internal endpoint with the signed
 * service context. Returns { ok, status }. Fails soft (never throws) so the
 * caller decides whether to trigger a Signals retry.
 */
async function callAppSail(endpointPath, payload, source, opts = {}) {
  const baseUrl = process.env.ZOHO_APPSAIL_BASE_URL;
  const secret = process.env.ZOHO_APPSAIL_SIGNING_SECRET;
  if (!baseUrl || !secret) return { ok: false, status: 0, reason: 'not_configured' };
  const requestId = opts.requestId || crypto.randomUUID();
  const { payload: sig, signature } = signServiceContext(source, secret, requestId);
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), opts.timeoutMs || 20000);
  try {
    const r = await fetch(baseUrl.replace(/\/+$/, '') + endpointPath, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-DRISHTI-Context': sig,
        'X-DRISHTI-Signature': signature,
        'X-Request-ID': requestId,
      },
      body: JSON.stringify(payload),
      signal: ac.signal,
    });
    return { ok: r.ok, status: r.status };
  } catch (e) {
    return { ok: false, status: 0, reason: e && e.name === 'AbortError' ? 'timeout' : 'error' };
  } finally {
    clearTimeout(timer);
  }
}

/** Feature-flag gate: an event function is inert until its owning phase enables it. */
function featureEnabled(flagName) {
  return String(process.env[flagName] || '').toLowerCase() === 'true';
}

module.exports = { signServiceContext, parseSignalEvents, callAppSail, featureEnabled, b64url };
