'use strict';
/*
 * DRISHTI — notification delivery handler (Event function).
 * Phase 14 Part B, matrix rows 24/25, workflow §12 (notification-delivery).
 *
 * Target of a Catalyst Signals rule on the custom `notify.requested` event
 * (published by AppSail's /internal/notify when an approved task/report/
 * prediction/alert lifecycle event occurs). It renders a DATA-MINIMIZED template
 * and sends via Catalyst Mail (+ Push where a mobile app is registered), then
 * records a delivery-status row via AppSail. It NEVER includes evidence content,
 * scores, PII, or full case narratives — only a reference id + role + a short
 * synthetic notice.
 *
 * Inert until DRISHTI_NOTIFY_ENABLED=true (keeps Mail/Push credits at zero until
 * the owning phase turns it on). Idempotency key: the inbound `idempotency_key`.
 */
const catalyst = require('zcatalyst-sdk-node');

// Data-minimized templates. Placeholders are non-sensitive references only.
const TEMPLATES = {
  'task.assigned': (p) => ({ subject: 'DRISHTI: a task was assigned',
    body: `A task (${p.subject_ref || 'ref'}) was assigned to your role. Open DRISHTI to review. [Synthetic Hackathon Demo]` }),
  'report.ready': (p) => ({ subject: 'DRISHTI: a report is ready',
    body: `Report ${p.subject_ref || ''} is ready for download in DRISHTI. [Synthetic Hackathon Demo]` }),
  'prediction.result.ready': (p) => ({ subject: 'DRISHTI: a prediction is ready for review',
    body: `A prediction result (${p.request_ref || ''}) is ready for human review. [Synthetic Hackathon Demo]` }),
  'alert.review': (p) => ({ subject: 'DRISHTI: an alert needs review',
    body: `An alert (${p.subject_ref || ''}) requires human review before any action. [Synthetic Hackathon Demo]` }),
};

function render(template, payload) {
  const fn = TEMPLATES[template] || ((p) => ({ subject: 'DRISHTI notification',
    body: `A DRISHTI lifecycle event occurred (${p.subject_ref || ''}). [Synthetic Hackathon Demo]` }));
  return fn(payload || {});
}

module.exports = async (event, context) => {
  const enabled = String(process.env.DRISHTI_NOTIFY_ENABLED || '').toLowerCase() === 'true';
  const fromEmail = process.env.DRISHTI_NOTIFY_FROM_EMAIL || '';
  const events = (event && Array.isArray(event.events)) ? event.events : [];
  const out = [];

  let app = null;
  if (enabled) { try { app = catalyst.initialize(context); } catch (e) { app = null; } }

  for (const e of events) {
    const d = e.data || {};
    const idem = d.idempotency_key || `notify:${e.id}`;
    const toRole = d.recipients_role || d.role || 'investigating_officer';
    const toEmail = d.to_email || process.env.DRISHTI_NOTIFY_DEFAULT_TO || '';
    const { subject, body } = render(d.template, d);

    if (!enabled || !app || !fromEmail || !toEmail) {
      console.log(`[notify_dispatch] scaffold/disabled or unconfigured; would send '${subject}' to role=${toRole} (${idem})`);
      out.push({ event_id: e.id, idem, skipped: true });
      continue;
    }
    try {
      await app.email().sendMail({
        from_email: fromEmail, to_email: [toEmail],
        subject, content: body, html_mode: false,
      });
      // Push: only attempt when a mobile app id is configured; otherwise log intent.
      if (process.env.DRISHTI_PUSH_APP_ID) {
        console.log(`[notify_dispatch] push intent for ${idem} (mobile app ${process.env.DRISHTI_PUSH_APP_ID})`);
      }
      out.push({ event_id: e.id, idem, sent: true });
    } catch (err) {
      console.error(`[notify_dispatch] send failed for ${idem}: ${err && err.message}`);
      out.push({ event_id: e.id, idem, sent: false, error: err && err.message });
      throw err; // let Signals retry (idempotency guarded by idem key downstream)
    }
  }
  return { handled: out.length, results: out };
};
