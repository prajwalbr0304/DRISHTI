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

// --- Catalyst Event payload handling ---------------------------------------
// A Catalyst Event function receives a CatalystEvent OBJECT whose payload is
// exposed through GETTER METHODS (getData / getAction / getSource /
// getSourceEntityId / getTime ...), NOT plain properties — so JSON.stringify of
// the event is "{}". We must call event.getData() to read the inserted row.
// Falls back to plain shapes for local runtimes / unit tests.
function readEvent(event) {
  const meta = { action: null, source: null, entity: null };
  let data = null;
  try {
    if (event && typeof event.getData === 'function') {
      data = event.getData();
      if (typeof event.getAction === 'function') meta.action = event.getAction();
      if (typeof event.getSource === 'function') meta.source = event.getSource();
      if (typeof event.getSourceEntityId === 'function') meta.entity = event.getSourceEntityId();
    } else if (event && event.data !== undefined) {
      data = event.data;
    } else {
      data = event;
    }
  } catch (e) {
    console.log('[prediction_event] getData error:', e && e.message);
  }
  return { data, meta };
}
function toRecords(data) {
  const recs = [];
  const add = (d) => { if (d && typeof d === 'object' && !Array.isArray(d)) recs.push(d); };
  if (Array.isArray(data)) data.forEach(add);
  else if (data && Array.isArray(data.rows)) data.rows.forEach(add);
  else if (data && Array.isArray(data.events)) data.events.forEach((e) => add(e && e.data ? e.data : e));
  else add(data);
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

// Structured EXACTLY like the proven working cron_forecast: a single direct
// async export, a plain `return` (an event function completes when its promise
// resolves — no closeWithSuccess), and no extra export aliases. The earlier
// dual-export + closeWithSuccess wrapper suppressed all console output and the
// dispatch.
module.exports = async (event, context) => {
  const enabled = String(process.env.DRISHTI_PREDICTION_DISPATCH_ENABLED || '').toLowerCase() === 'true';
  const { data, meta } = readEvent(event);
  try {
    console.log('[prediction_event] action=' + meta.action + ' source=' + meta.source +
      ' entity=' + meta.entity + ' data=' + JSON.stringify(data).slice(0, 1500));
  } catch (_e) {
    console.log('[prediction_event] data keys=' +
      (data && typeof data === 'object' ? Object.keys(data).join(',') : typeof data));
  }

  const records = toRecords(data);
  const out = [];
  let idx = 0;
  for (const d of records) {
    idx += 1;
    const reqId = (pick(d, ['PredictionRequestID', 'prediction_request_id', 'request_id']) || '').toString();
    const eid = (pick(d, ['ROWID', 'id']) || `rec${idx}`).toString();
    const idem = (pick(d, ['idempotency_key']) || `pred:${reqId}`).toString();
    const isResult = !!pick(d, ['PredictionResultID']) ||
      (pick(d, ['record_type', 'table', 'api_name']) || '').toString().toLowerCase().includes('result');

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
    // PredictionRequest: dispatch approved requests. Safety net: if state is
    // unreadable (payload-shape surprise) but a PredictionRequestID IS present,
    // dispatch anyway — this table only holds requests and AppSail dispatch is
    // idempotent by key, so we never silently drop a real request.
    const state = String(pick(d, ['state', 'State', 'Status']) || '').toLowerCase();
    const dispatchable = ['approved', 'ready'].includes(state) || (!state && !!reqId);
    if (!dispatchable) {
      console.log(`[prediction_event] ignored not_approved state=${state} req=${reqId}`);
      out.push({ event_id: eid, ignored: 'not_approved', state });
      continue;
    }
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
    console.log(`[prediction_event] dispatch ${idem} (req=${reqId} state=${state}) -> ${JSON.stringify(r)}`);
    out.push({ event_id: eid, idem, reqId, ...r });
    // Do not throw: a persistent error would loop Signal retries. AppSail
    // dispatch is idempotent by key so cron_reconcile can re-drive a miss.
  }
  return { handled: out.length, results: out };
};
