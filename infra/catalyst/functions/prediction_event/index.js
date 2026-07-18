'use strict';
/*
 * DRISHTI — prediction dispatch/result event handler (Event function).
 * Phase 14 Part B, matrix rows 21/22, workflow §7
 * (custom-prediction-dispatch-and-result).
 *
 * Target of Catalyst Signals rules on Data Store row_inserted for
 * PredictionRequest (state=approved) and PredictionResult.
 *
 *   - PredictionRequest(approved) -> ask AppSail to build the minimum-required
 *     snapshot and dispatch to the protected AWS adapter (SQS/Batch/SageMaker).
 *   - PredictionResult -> emit a data-minimized notify.requested event for UI
 *     review (handled by notify_dispatch).
 *
 * Duplicate-result protection + idempotency are enforced by AppSail keyed on the
 * request idempotency key; this handler only routes and never mutates source
 * input. Inert until DRISHTI_PREDICTION_DISPATCH_ENABLED=true.
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
  const timer = setTimeout(() => ac.abort(), 20000);
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

module.exports = async (event, context) => {
  const enabled = String(process.env.DRISHTI_PREDICTION_DISPATCH_ENABLED || '').toLowerCase() === 'true';
  const events = (event && Array.isArray(event.events)) ? event.events : [];
  const out = [];
  for (const e of events) {
    const d = e.data || {};
    const kind = (d.record_type || d.table || d.api_name || '').toString().toLowerCase();
    const isResult = kind.includes('result');
    const reqId = d.prediction_request_id || d.PredictionRequestID || d.request_id || '';
    const idem = d.idempotency_key || `pred:${reqId}`;

    if (isResult) {
      // Route a data-minimized review notice (no scores/PII in the envelope).
      const r = await callAppSail('/internal/notify', {
        idempotency_key: `notify:${idem}`, template: 'prediction.result.ready',
        subject_ref: `PredictionResult:${d.PredictionResultID || d.id || ''}`,
        request_ref: `PredictionRequest:${reqId}`, source: 'signals:prediction',
      }, 'prediction_event', e.id || idem);
      out.push({ event_id: e.id, routed: 'notify', ...r });
      continue;
    }
    // PredictionRequest: only dispatch approved ones.
    const state = String(d.state || d.Status || '').toLowerCase();
    if (!['approved', 'ready'].includes(state)) { out.push({ event_id: e.id, ignored: 'not_approved', state }); continue; }
    if (!enabled) {
      console.log(`[prediction_event] scaffold disabled; would dispatch ${idem}`);
      out.push({ event_id: e.id, skipped: true, idem });
      continue;
    }
    const r = await callAppSail('/internal/predictions/dispatch', {
      idempotency_key: idem, prediction_request_id: String(reqId),
      task: d.task || null, requested_backend: d.requested_backend || null,
      source: 'signals:prediction', event_id: e.id,
    }, 'prediction_event', e.id || idem);
    console.log(`[prediction_event] dispatch ${idem} -> ${JSON.stringify(r)}`);
    out.push({ event_id: e.id, idem, ...r });
    if (r.ok === false && r.status >= 500) throw new Error(`dispatch failed for ${idem}`);
  }
  return { handled: out.length, results: out };
};
