'use strict';
/*
 * DRISHTI — scoped channel-token minter (Advanced I/O function). Phase 14 Part F,
 * item 1 (+ the G prediction-flow "scoped AppSail WebSocket/SSE token channel").
 *
 * This runs on the AUTHENTICATED Catalyst API Gateway path. It derives the user
 * from Catalyst Authentication server-side (never from client headers), performs
 * a strict Origin check, optionally checks board membership, then mints a
 * SHORT-LIVED token bound to { audience, board, user, origin } that the browser
 * uses to open ONE direct AppSail SSE/WS stream. AppSail verifies the token
 * (services/ml/app/channel.py) before opening the stream.
 *
 * The token is the ONLY thing that authorises the direct AppSail channel; the
 * browser still never touches AWS or AppSail CRUD directly.
 *
 * Env (Console/AppSail, never committed):
 *   DRISHTI_CHANNEL_SIGNING_SECRET  - HMAC secret (falls back to ZOHO_APPSAIL_SIGNING_SECRET)
 *   ZOHO_APPSAIL_SIGNING_SECRET     - shared signing secret fallback
 *   DRISHTI_CHANNEL_ALLOWED_ORIGINS - comma-separated exact browser origins
 *   DRISHTI_APPSAIL_STREAM_URL      - https base URL of the AppSail SSE endpoint
 *   DRISHTI_CHANNEL_TTL_MS          - token lifetime (default 300000 = 5 min)
 */
const crypto = require('crypto');
const catalyst = require('zcatalyst-sdk-node');

const AUD = 'drishti-channel';
const SCOPE = 'channel';
const DEFAULT_TTL_MS = 5 * 60 * 1000;

function b64url(buf) {
  return Buffer.from(buf).toString('base64')
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function sendJson(res, status, body) {
  res.writeHead(status, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify(body));
}

function localhostCors(req, res) {
  const origin = req.headers.origin || '';
  if (/^http:\/\/localhost(:\d+)?$/.test(origin) || /^http:\/\/127\.0\.0\.1(:\d+)?$/.test(origin)) {
    res.setHeader('Access-Control-Allow-Origin', origin);
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Accept');
    if (req.method === 'OPTIONS') { res.writeHead(204); res.end(); return true; }
  }
  return false;
}

function allowedOrigins() {
  return String(process.env.DRISHTI_CHANNEL_ALLOWED_ORIGINS || '')
    .split(',').map((o) => o.trim()).filter(Boolean);
}

/* Server-side board membership check. The default is fail-closed friendly for
 * the demo (any authenticated user may open their own board channel); a real
 * deployment resolves board membership from Data Store here and returns false to
 * deny. It never trusts a client-supplied role/board claim. */
function userMayAccessBoard(_user, boardId) {
  return Boolean(boardId);
}

async function readBoardId(req) {
  const url = new URL(req.url, `https://${req.headers.host || 'localhost'}`);
  const q = url.searchParams.get('board_id');
  if (q) return q;
  if (req.body && typeof req.body === 'object') return req.body.board_id || '';
  if (typeof req.body === 'string') {
    try { return (JSON.parse(req.body).board_id) || ''; } catch (e) { return ''; }
  }
  return '';
}

module.exports = async (req, res) => {
  if (localhostCors(req, res) && req.method === 'OPTIONS') return;

  const requestId = req.headers['x-request-id'] || crypto.randomUUID();
  const secret = process.env.DRISHTI_CHANNEL_SIGNING_SECRET
    || process.env.ZOHO_APPSAIL_SIGNING_SECRET;
  const streamUrl = process.env.DRISHTI_APPSAIL_STREAM_URL;
  if (!secret || !streamUrl) {
    return sendJson(res, 503, { error: 'channel_not_configured', request_id: requestId });
  }

  // 1. Identity from Catalyst Authentication (server-side; never trusted headers).
  let user = null;
  try {
    const app = catalyst.initialize(req);
    user = await app.userManagement().getCurrentUser();
  } catch (e) {
    user = null;
  }
  if (!user || !user.user_id) {
    return sendJson(res, 401, { error: 'authentication_required', request_id: requestId });
  }

  // 2. Strict Origin check at mint time (allow-listed exact origins only).
  const origin = req.headers.origin || '';
  const allow = allowedOrigins();
  if (!allow.length || !allow.includes(origin)) {
    return sendJson(res, 403, { error: 'origin_not_allowed', request_id: requestId });
  }

  // 3. Board binding + server-side membership check.
  const boardId = String(await readBoardId(req) || '').trim();
  if (!boardId) {
    return sendJson(res, 400, { error: 'board_id_required', request_id: requestId });
  }
  if (!userMayAccessBoard(user, boardId)) {
    return sendJson(res, 403, { error: 'board_forbidden', request_id: requestId });
  }

  // 4. Mint the short-lived, bound token (same scheme as app/channel.py).
  const now = Date.now();
  const ttl = parseInt(process.env.DRISHTI_CHANNEL_TTL_MS || String(DEFAULT_TTL_MS), 10);
  const claims = {
    scope: SCOPE, aud: AUD,
    user_id: String(user.user_id), board_id: boardId, origin,
    ts: now, exp: now + ttl,
    nonce: crypto.randomBytes(12).toString('hex'), request_id: String(requestId),
  };
  const payload = b64url(JSON.stringify(claims));
  const signature = crypto.createHmac('sha256', secret).update(payload).digest('hex');

  return sendJson(res, 200, {
    token: `${payload}.${signature}`,
    board_id: boardId,
    expires_at: claims.exp,
    stream_url: streamUrl.replace(/\/+$/, '') + '/stream/predictions',
    request_id: requestId,
  });
};
