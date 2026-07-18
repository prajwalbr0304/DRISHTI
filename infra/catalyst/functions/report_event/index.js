'use strict';
/*
 * DRISHTI — report lifecycle event handler (Event function).
 * Phase 14 Part B, matrix rows 16/21, workflow §11
 * (report-generation-and-delivery).
 *
 * Target of a Catalyst Signals rule on the custom `report.ready` event (emitted
 * by the report job after SmartBrowz renders a PDF/image and the object lands in
 * a private Stratus bucket). It routes a data-minimized delivery notice and
 * records delivery status; it never embeds report bytes or full narratives.
 *
 * Inert until DRISHTI_REPORT_DELIVERY_ENABLED=true.
 * Idempotency key: report:<report_id>:<version>.
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
  const enabled = String(process.env.DRISHTI_REPORT_DELIVERY_ENABLED || '').toLowerCase() === 'true';
  const events = (event && Array.isArray(event.events)) ? event.events : [];
  const out = [];
  for (const e of events) {
    const d = e.data || {};
    const reportId = d.report_id || d.ReportID || d.id || '';
    const version = d.version || d.Version || 'v1';
    const idem = `report:${reportId}:${version}`;
    if (!enabled) {
      console.log(`[report_event] scaffold disabled; skipping ${idem}`);
      out.push({ event_id: e.id, skipped: true, idem });
      continue;
    }
    const r = await callAppSail('/internal/notify', {
      idempotency_key: `notify:${idem}`, template: 'report.ready',
      subject_ref: `Report:${reportId}`, object_ref: d.object_key || null,
      recipients_role: d.recipients_role || null, source: 'signals:report', event_id: e.id,
    }, 'report_event', e.id || idem);
    console.log(`[report_event] ${idem} -> ${JSON.stringify(r)}`);
    out.push({ event_id: e.id, idem, ...r });
    if (r.ok === false && r.status >= 500) throw new Error(`report notify failed for ${idem}`);
  }
  return { handled: out.length, results: out };
};
