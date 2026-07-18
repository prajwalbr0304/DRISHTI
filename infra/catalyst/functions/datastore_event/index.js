'use strict';
/*
 * DRISHTI — Data Store source-change event handler (Event function).
 * Phase 14 Part B, matrix rows 6/10/21/22, workflows §3 (intake) and §6
 * (feature-snapshot-and-staleness).
 *
 * Target of Catalyst Signals rules on Data Store row_inserted / row_updated for
 * CaseVersion / CaseEvent (approved canonical rows only). It enforces the
 * input-to-model routing contract (report §8.5):
 *   - Only APPROVED canonical versions are eligible.
 *   - It NEVER scores a person / complainant / accused / victim / FIR.
 *   - It marks only affected AGGREGATE snapshots stale and coalesces an
 *     idempotent prediction request for eligible area/workload subjects.
 *
 * Draft / submitted / rejected / quarantined rows are ineligible and ignored.
 *
 * Cost posture: inert until DRISHTI_FEATURE_SNAPSHOT_ENABLED=true.
 * Idempotency key: snap:<subject_kind>:<subject_id>:<cutoff>:<feature_schema_version>:<source_version_hash>.
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

// Person-like subjects are never model subjects (fairness/safety gate).
const INELIGIBLE_SUBJECTS = new Set(['person', 'complainant', 'accused', 'victim', 'fir', 'case']);
const ELIGIBLE_STATES = new Set(['approved', 'canonical', 'committed']);

module.exports = async (event, context) => {
  const enabled = String(process.env.DRISHTI_FEATURE_SNAPSHOT_ENABLED || '').toLowerCase() === 'true';
  const events = (event && Array.isArray(event.events)) ? event.events : [];
  const out = [];
  for (const e of events) {
    const d = e.data || {};
    const state = String(d.state || d.Status || d.lifecycle_state || '').toLowerCase();
    if (!ELIGIBLE_STATES.has(state)) {
      out.push({ event_id: e.id, ignored: 'not_canonical', state });
      continue;
    }
    // Determine affected AGGREGATE subjects only (unit workload / area forecast).
    const cutoff = d.observation_cutoff || d.approved_at || d.ModifiedTime || '';
    const schemaVer = d.feature_schema_version || process.env.DRISHTI_FEATURE_SCHEMA_VERSION || 'unset';
    const srcHash = d.source_version_hash || d.CaseVersionID || d.ROWID || '';
    const subjects = [];
    if (d.unit_id || d.UnitID) subjects.push({ kind: 'station', id: String(d.unit_id || d.UnitID) });
    if (d.district_id || d.DistrictID) subjects.push({ kind: 'area', id: String(d.district_id || d.DistrictID) });
    const safeSubjects = subjects.filter((s) => !INELIGIBLE_SUBJECTS.has(s.kind));
    if (!safeSubjects.length) { out.push({ event_id: e.id, ignored: 'no_aggregate_subject' }); continue; }

    if (!enabled) {
      console.log(`[datastore_event] scaffold disabled; would snapshot ${safeSubjects.map((s) => s.kind + ':' + s.id).join(',')}`);
      out.push({ event_id: e.id, skipped: true, subjects: safeSubjects });
      continue;
    }
    for (const s of safeSubjects) {
      const idem = `snap:${s.kind}:${s.id}:${cutoff}:${schemaVer}:${srcHash}`;
      const r = await callAppSail('/internal/features/snapshot', {
        idempotency_key: idem, subject_kind: s.kind, subject_id: s.id,
        observation_cutoff: cutoff, feature_schema_version: schemaVer,
        source_version_hash: srcHash, source: 'signals:datastore', event_id: e.id,
      }, 'datastore_event', e.id || idem);
      console.log(`[datastore_event] ${idem} -> ${JSON.stringify(r)}`);
      out.push({ event_id: e.id, idem, ...r });
      if (r.ok === false && r.status >= 500) throw new Error(`snapshot failed for ${idem}`);
    }
  }
  return { handled: out.length, results: out };
};
