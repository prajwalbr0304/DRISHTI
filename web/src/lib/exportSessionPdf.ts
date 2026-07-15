import { api } from "@/api";
import type { AskMessage } from "@/stores/useAskStore";

/* ============================================================================
   Export an Ask DRISHTI session to a print-clean PDF (doc 01 §4.7, Phase 5).

   Builds a self-contained HTML document and prints it from a hidden iframe
   (no popup blocker, isolated from the app's styles). The header carries the
   session/case IDs, investigator + role, timestamp and language; each exchange
   shows the original + translated query, the grounded answer, its citations,
   the read-only SQL and confidence. Only data the user already sees is
   exported — aggregates were k-anonymity–suppressed server-side — and the
   footer states that explicitly.
   ========================================================================== */

export interface SessionPdfMeta {
  sessionId: number | null;
  roleLabel: string; // e.g. "Crime Analyst"
  role: string; // e.g. "analyst"
  scope: string; // e.g. "District · read-across"
  title?: string | null;
}

const FONTS =
  '<link rel="preconnect" href="https://fonts.googleapis.com">' +
  '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>' +
  '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Noto+Sans+Kannada:wght@400;500;600;700&display=swap" rel="stylesheet">';

const STYLE = `
@page { size: A4; margin: 16mm; }
* { box-sizing: border-box; }
body { font-family:'Inter','Noto Sans Kannada','Nirmala UI','Tunga',sans-serif; color:#12141c; font-size:12px; line-height:1.5; margin:0; }
:lang(kn){ font-family:'Noto Sans Kannada','Nirmala UI','Tunga','Inter',sans-serif; line-height:1.75; }
.brand { font-size:16px; font-weight:700; letter-spacing:.01em; }
.sub { font-size:10.5px; color:#5a6478; }
.doc-header { border-bottom:2px solid #12141c; padding-bottom:10px; margin-bottom:14px; }
.meta { width:100%; font-size:10.5px; color:#333; margin-top:8px; border-collapse:collapse; }
.meta td { padding:1px 10px 1px 0; vertical-align:top; }
.meta .k { color:#6b7280; white-space:nowrap; width:1%; }
.exchange { border:1px solid #dce1ec; border-radius:8px; padding:10px 12px; margin:0 0 10px; page-break-inside:avoid; }
.n { display:inline-block; min-width:18px; height:18px; line-height:18px; text-align:center; background:#12141c; color:#fff; border-radius:9px; font-size:10px; font-weight:600; margin-right:6px; }
.lbl { font-size:9.5px; text-transform:uppercase; letter-spacing:.05em; color:#6b7280; margin:8px 0 2px; }
.query { font-weight:600; }
.translated { color:#374151; font-style:italic; }
.answer { }
.blocked { color:#b42318; }
.chip { display:inline-block; border:1px solid #cbd5e1; border-radius:4px; padding:0 6px; font-size:10px; color:#374151; margin:2px 4px 0 0; }
.sql { background:#f5f6f9; border:1px solid #e3e6ee; border-radius:6px; padding:6px 8px; font-family:ui-monospace,'Consolas',monospace; font-size:10px; white-space:pre-wrap; word-break:break-word; margin-top:6px; }
.conf { font-size:10px; color:#374151; margin-top:4px; }
.doc-footer { margin-top:16px; border-top:1px solid #cbd5e1; padding-top:8px; font-size:9px; color:#6b7280; }
`;

function esc(s: unknown): string {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function langLabel(l?: string): string {
  return l === "kn" ? "ಕನ್ನಡ (Kannada)" : "English";
}

/** distinct "Case N" references across all citations, for the header. */
function caseRefs(messages: AskMessage[]): string[] {
  const ids = new Set<string>();
  for (const m of messages) {
    for (const c of m.citedRecordIds ?? []) {
      const mm = String(c).match(/^CaseMaster:(\d+)$/);
      if (mm) ids.add(mm[1]);
    }
  }
  return [...ids];
}

async function translateUserTurns(messages: AskMessage[]): Promise<Map<string, string>> {
  const out = new Map<string, string>();
  const users = messages.filter((m) => m.sender === "user" && m.text.trim()).slice(0, 25);
  await Promise.allSettled(
    users.map(async (m) => {
      const target: "en" | "kn" = m.language === "kn" ? "en" : "kn";
      try {
        const r = await api.chat.translate(m.text, target);
        if (r.available && r.translated) out.set(m.id, r.translated);
      } catch {
        /* translation unavailable — the PDF notes it */
      }
    }),
  );
  return out;
}

function citationChips(m: AskMessage): string {
  const cites = m.citedRecordIds ?? [];
  if (!cites.length) return "";
  const chips = cites
    .map((c) => {
      const raw = String(c);
      const agg = raw.match(/^(.+?)\(aggregated\)$/);
      const label = agg ? `${agg[1]} (aggregated)` : raw.replace(/^CaseMaster:/, "Case ");
      return `<span class="chip">${esc(label)}</span>`;
    })
    .join("");
  return `<div class="lbl">Citations</div>${chips}`;
}

function exchangeHtml(user: AskMessage, answer: AskMessage | null, n: number, translated?: string): string {
  const tLang = user.language === "kn" ? "en" : "kn";
  const translationBlock = translated
    ? `<div class="lbl">Query (${esc(langLabel(tLang))})</div><div class="translated" lang="${esc(tLang)}">${esc(translated)}</div>`
    : `<div class="lbl">Query (translation)</div><div class="translated">Translation unavailable offline (requires the language model).</div>`;

  let ans = "";
  if (answer) {
    const blockedCls = answer.blocked ? " blocked" : "";
    ans += `<div class="lbl">Answer</div><div class="answer${blockedCls}" lang="${esc(answer.language ?? "en")}">${esc(answer.text)}</div>`;
    if (answer.confidence != null && !answer.blocked && !answer.needsClarification) {
      ans += `<div class="conf">Confidence: ${Math.round((answer.confidence ?? 0) * 100)}%${
        answer.modelVersion ? ` · ${esc(answer.modelVersion)}` : ""
      }</div>`;
    }
    ans += citationChips(answer);
    if (answer.generatedSql) {
      ans += `<div class="lbl">Read-only SQL executed</div><div class="sql">${esc(answer.generatedSql)}</div>`;
    }
  }

  return (
    `<div class="exchange">` +
    `<div class="lbl"><span class="n">${n}</span>Query (${esc(langLabel(user.language))})${user.spoken ? " · voice" : ""}</div>` +
    `<div class="query" lang="${esc(user.language ?? "en")}">${esc(user.text)}</div>` +
    translationBlock +
    ans +
    `</div>`
  );
}

function printViaIframe(html: string): void {
  const iframe = document.createElement("iframe");
  Object.assign(iframe.style, {
    position: "fixed",
    right: "0",
    bottom: "0",
    width: "0",
    height: "0",
    border: "0",
  });
  document.body.appendChild(iframe);
  const win = iframe.contentWindow;
  if (!win) {
    iframe.remove();
    return;
  }
  win.document.open();
  win.document.write(html);
  win.document.close();

  let cleaned = false;
  const cleanup = () => {
    if (cleaned) return;
    cleaned = true;
    setTimeout(() => iframe.remove(), 300);
  };
  win.onafterprint = cleanup;
  // Give the webfonts + layout a moment before printing.
  setTimeout(() => {
    try {
      win.focus();
      win.print();
    } finally {
      setTimeout(cleanup, 60_000); // safety net if onafterprint never fires
    }
  }, 500);
}

export async function exportSessionPdf(messages: AskMessage[], meta: SessionPdfMeta): Promise<void> {
  const translations = await translateUserTurns(messages);

  // Build exchanges by pairing each user turn with the following assistant turn.
  const exchanges: string[] = [];
  let n = 0;
  for (let i = 0; i < messages.length; i++) {
    const m = messages[i];
    if (m.sender !== "user") continue;
    const answer =
      i + 1 < messages.length && messages[i + 1].sender === "assistant" ? messages[i + 1] : null;
    n += 1;
    exchanges.push(exchangeHtml(m, answer, n, translations.get(m.id)));
  }

  const cases = caseRefs(messages);
  const generated = new Date().toLocaleString();
  const sessionLang = messages.find((m) => m.language)?.language;

  const html =
    `<!doctype html><html lang="en"><head><meta charset="utf-8">` +
    `<title>DRISHTI — Ask session ${meta.sessionId ?? ""}</title>${FONTS}<style>${STYLE}</style></head><body>` +
    `<header class="doc-header">` +
    `<div class="brand">DRISHTI · Ask session export</div>` +
    `<div class="sub">Karnataka State Police — crime intelligence · CONFIDENTIAL</div>` +
    `<table class="meta"><tbody>` +
    `<tr><td class="k">Session ID</td><td>${esc(meta.sessionId ?? "— (unsaved)")}</td>` +
    `<td class="k">Investigator</td><td>${esc(meta.roleLabel)} (${esc(meta.role)})</td></tr>` +
    `<tr><td class="k">Case references</td><td>${cases.length ? cases.map((c) => "Case " + esc(c)).join(", ") : "—"}</td>` +
    `<td class="k">Scope</td><td>${esc(meta.scope)}</td></tr>` +
    `<tr><td class="k">Generated</td><td>${esc(generated)}</td>` +
    `<td class="k">Language</td><td>${esc(langLabel(sessionLang))}</td></tr>` +
    (meta.title ? `<tr><td class="k">Title</td><td colspan="3">${esc(meta.title)}</td></tr>` : "") +
    `</tbody></table></header>` +
    `<main>${exchanges.join("") || "<p>No exchanges in this session.</p>"}</main>` +
    `<footer class="doc-footer">Role-scoped export reflecting only what this role may view. ` +
    `Aggregate figures are k-anonymity–suppressed at source; individual records shown are within the ` +
    `investigator's access. Generated ${esc(generated)}. Not for public release.</footer>` +
    `</body></html>`;

  printViaIframe(html);
}
