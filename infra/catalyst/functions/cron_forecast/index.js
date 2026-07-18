'use strict';
/*
 * DRISHTI — scheduled forecast/backfill dispatch cron (Cron function).
 * Phase 14 Part B, matrix row 20, workflow §9
 * (aggregate-and-spatiotemporal-forecast).
 *
 * DISABLED SCAFFOLD: deployed but NO cron schedule is registered, so it never
 * fires and incurs no charge until the owning phase enables it (see
 * infra/catalyst/jobs/cron-schedules.json). The hazard-response forecast path
 * (workflows §14-§16) is owned by Prompt 17 and stays disabled here per the
 * phase-order rule.
 *
 * When enabled it asks AppSail to snapshot a time/area window and dispatch
 * separately typed baseline / TimesFM / ST-GNN / hotspot / near-repeat jobs to
 * the protected AWS adapter, then stop temporary compute. It never fuses
 * incompatible layers and never auto-publishes an operational result.
 */
const crypto = require('crypto');

function b64url(b) {
  return Buffer.from(b).toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}
function signServiceContext(source, secret, requestId) {
  const now = Date.now();
  const ctx = { scope: 'service', aud: 'drishti-appsail', source, ts: now, exp: now + 60000,
    nonce: crypto.randomBytes(12).toString('hex'), request_id: requestId };
  const payload = b64url(JSON.stringify(ctx));
  return { payload, signature: crypto.createHmac('sha256', secret).update(payload).digest('hex') };
}
async function callAppSail(path, payload, source, requestId) {
  const baseUrl = process.env.ZOHO_APPSAIL_BASE_URL;
  const secret = process.env.ZOHO_APPSAIL_SIGNING_SECRET;
  if (!baseUrl || !secret) return { ok: false, reason: 'not_configured' };
  const { payload: sig, signature } = signServiceContext(source, secret, requestId);
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), 60000);
  try {
    const r = await fetch(baseUrl.replace(/\/+$/, '') + path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-DRISHTI-Context': sig,
        'X-DRISHTI-Signature': signature, 'X-Request-ID': requestId },
      body: JSON.stringify(payload), signal: ac.signal });
    return { ok: r.ok, status: r.status };
  } catch (e) { return { ok: false, reason: e && e.name === 'AbortError' ? 'timeout' : 'error' }; }
  finally { clearTimeout(timer); }
}

module.exports = async (cronDetails, context) => {
  const enabled = String(process.env.DRISHTI_FORECAST_CRON_ENABLED || '').toLowerCase() === 'true';
  const window = new Date().toISOString().slice(0, 10);
  if (!enabled) {
    console.log(`[cron_forecast] disabled scaffold; no-op for ${window}`);
    return { skipped: true, window };
  }
  const r = await callAppSail('/internal/forecast/run', {
    idempotency_key: `forecast:${window}`, window, source: 'cron:forecast',
  }, 'cron_forecast', `forecast:${window}`);
  console.log(`[cron_forecast] ${window} -> ${JSON.stringify(r)}`);
  return { window, ...r };
};
