'use strict';
/*
 * DRISHTI — reconciliation / backup / cleanup cron (Cron function).
 * Phase 14 Part B, matrix row 20, workflow §17
 * (reconciliation-backup-recovery-and-cleanup).
 *
 * DISABLED SCAFFOLD: this function is deployed but NO Catalyst cron schedule is
 * registered for it, so it never fires and incurs no charge until its owning
 * phase enables the schedule (see infra/catalyst/jobs/cron-schedules.json).
 *
 * When enabled it asks AppSail to run: Data Store/Stratus count-hash-version
 * reconciliation, backup/export, a restore drill, failed-job replay, stale
 * temp-object cleanup, temporary AWS GPU/Batch shutdown checks, and to emit
 * budget/health evidence. It performs no destructive action itself; AppSail owns
 * the guarded operations and every step is audited.
 *
 * Cron functions have a 15-minute execution ceiling; long work is chunked and
 * resumed idempotently by AppSail (keyed on the run date).
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
  const enabled = String(process.env.DRISHTI_RECONCILE_ENABLED || '').toLowerCase() === 'true';
  const runDate = new Date().toISOString().slice(0, 10);
  if (!enabled) {
    console.log(`[cron_reconcile] disabled scaffold; no-op for ${runDate}`);
    return { skipped: true, run_date: runDate };
  }
  const r = await callAppSail('/internal/ops/reconcile', {
    idempotency_key: `reconcile:${runDate}`, run_date: runDate, source: 'cron:reconcile',
  }, 'cron_reconcile', `reconcile:${runDate}`);
  console.log(`[cron_reconcile] ${runDate} -> ${JSON.stringify(r)}`);
  return { run_date: runDate, ...r };
};
