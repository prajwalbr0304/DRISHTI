'use strict';
/*
 * DRISHTI — digital-evidence ingestion event handler (Event function).
 * Phase 14 Part B, matrix rows 8/21, workflow §4 (digital-evidence-ingestion).
 *
 * Target of Catalyst Signals rules on:
 *   - Stratus: stratus_object_uploaded (evidence bucket prefix)
 *   - Data Store: row_inserted on EvidenceObject
 *
 * It orchestrates the SECURITY path only: keep the object quarantined and ask
 * AppSail to run MIME/size/hash validation + an isolated malware scan, then flip
 * available/rejected. It performs NO OCR, transcription, semantic media analysis
 * or canonical-field extraction (Prompt 14 capability-not-used rule).
 *
 * Cost posture: inert until DRISHTI_EVIDENCE_SCAN_ENABLED=true (the isolated
 * scanner job is scaffolded/disabled in Part B). When disabled it logs and
 * ack's the event so no retry storm and no charge accrue.
 *
 * Idempotency key: evidence:<object_key>:<version_id>.
 */
const crypto = require('crypto');

function b64url(buf) {
  return Buffer.from(buf).toString('base64')
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
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
  const enabled = String(process.env.DRISHTI_EVIDENCE_SCAN_ENABLED || '').toLowerCase() === 'true';
  const events = (event && Array.isArray(event.events)) ? event.events : [];
  const results = [];
  for (const e of events) {
    const data = e.data || {};
    const objectKey = data.key || data.object_key || data.EvidenceObjectKey || '';
    const versionId = data.version_id || data.VersionID || 'v1';
    const idem = `evidence:${objectKey}:${versionId}`;
    if (!enabled) {
      console.log(`[evidence_event] scaffold disabled; skipping ${idem} (attempt ${event.attempt || 1})`);
      results.push({ idem, skipped: true });
      continue;
    }
    // Data-minimized: only object identity + integrity metadata cross the wire.
    const payload = {
      idempotency_key: idem, object_key: objectKey, version_id: versionId,
      size: data.size || null, content_type: data.content_type || null,
      sha256: data.sha256 || null, bucket: data.bucket || null,
      event_id: e.id, source: 'signals:evidence',
    };
    const r = await callAppSail('/internal/evidence/validate', payload, 'evidence_event', e.id || idem);
    console.log(`[evidence_event] ${idem} -> ${JSON.stringify(r)}`);
    results.push({ idem, ...r });
    // Hard failure (endpoint reachable but errored) -> throw so Signals retries.
    if (r.ok === false && r.status >= 500) throw new Error(`evidence validate failed for ${idem}`);
  }
  return { handled: results.length, results };
};
