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

// --- robust Signal payload handling ----------------------------------------
// Catalyst Signals may deliver the inserted row under different shapes
// (event.events[].data, event.data, or the record itself), and column names may
// be flat or one level nested. Extract records + fields defensively so a payload
// shape difference never silently drops the dispatch.
function extractRecords(event) {
  const recs = [];
  const add = (d) => { if (d && typeof d === 'object' && !Array.isArray(d)) recs.push(d); };
  if (event && Array.isArray(event.events)) {
    for (const e of event.events) add(e && e.data ? e.data : e);
  } else if (event && Array.isArray(event.data)) {
    for (const d of event.data) add(d);
  } else if (event && event.data) {
    add(event.data);
  } else {
    add(event);
  }
  return recs;
}
function pick(rec, keys) {
  for (const k of keys) {
    const v = rec[k];
    if (v !== undefined && v !== null && v !== '') return v;
  }
  for (const nk of Object.keys(rec)) {              // one level of nesting
    const nested = rec[nk];
    if (nested && typeof nested === 'object' && !Array.isArray(nested)) {
      for (const k of keys) {
        const v = nested[k];
        if (v !== undefined && v !== null && v !== '') return v;
      }
    }
  }
  return undefined;
}

module.exports = async (event, context) => {
  const enabled = String(process.env.DRISHTI_PREDICTION_DISPATCH_ENABLED || '').toLowerCase() === 'true';
  // Diagnostic (synthetic ids only): reveals the exact Signal payload shape.
  try { console.log('[prediction_event] raw event:', JSON.stringify(event).slice(0, 2000)); } catch (_e) { /* ignore */ }
  const records = extractRecords(event);
  const out = [];
  let idx = 0;
  for (const d of records) {
    idx += 1;
    const eid = (d.ROWID || d.id || `rec${idx}`).toString();
    const kind = (pick(d, ['record_type', 'table', 'api_name']) || '').toString().toLowerCase();
    const isResult = kind.includes('result');
    const reqId = (pick(d, ['PredictionRequestID', 'prediction_request_id', 'request_id']) || '').toString();
    const idem = (pick(d, ['idempotency_key']) || `pred:${reqId}`).toString();

    if (isResult) {
      // Route a data-minimized review notice (no scores/PII in the envelope).
      const r = await callAppSail('/internal/notify', {
        idempotency_key: `notify:${idem}`, template: 'prediction.result.ready',
        subject_ref: `PredictionResult:${pick(d, ['PredictionResultID', 'id']) || ''}`,
        request_ref: `PredictionRequest:${reqId}`, source: 'signals:prediction',
      }, 'prediction_event', eid);
      out.push({ event_id: eid, routed: 'notify', ...r });
      continue;
    }
    // PredictionRequest: only dispatch approved ones.
    const state = String(pick(d, ['state', 'State', 'Status']) || '').toLowerCase();
    if (!['approved', 'ready'].includes(state)) { out.push({ event_id: eid, ignored: 'not_approved', state }); continue; }
    if (!enabled) {
      console.log(`[prediction_event] scaffold disabled; would dispatch ${idem}`);
      out.push({ event_id: eid, skipped: true, idem });
      continue;
    }
    const r = await callAppSail('/internal/predictions/dispatch', {
      idempotency_key: idem, prediction_request_id: reqId,
      task: pick(d, ['task', 'Task']) || null,
      requested_backend: pick(d, ['requested_backend', 'RequestedBackend']) || null,
      source: 'signals:prediction', event_id: eid,
    }, 'prediction_event', eid);
    console.log(`[prediction_event] dispatch ${idem} (req=${reqId}) -> ${JSON.stringify(r)}`);
    out.push({ event_id: eid, idem, reqId, ...r });
    // NOTE: do not throw on failure — a persistent dispatch error would loop
    // Signal retries forever. The AppSail dispatch is idempotent by key, so
    // cron_reconcile can re-drive a transient miss; here we just record it.
  }
  return { handled: out.length, results: out };
};
