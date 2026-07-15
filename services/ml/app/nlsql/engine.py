"""NL->SQL engine (doc 02 §6): the grounded, cited, read-only assistant.

Pipeline per question:
  1. load prior turns (multi-turn memory) from ChatSession/ChatMessage,
  2. plan  — LLM (if configured) or the deterministic fallback -> SQL | clarify,
  3. clarify path -> ask, don't guess,
  4. execute — guard + role scope + drishti_readonly + timeout + row cap,
  5. build a GROUNDED NL reply from the ACTUAL rows (no invention) + record-id
     citations + an honest confidence,
  6. persist the user + assistant turns to ChatMessage with the SQL, citations,
     confidence and a ModelVersion + ModelInference audit row.

Blocks and DB errors are recorded (audit) but never surface fabricated data.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from psycopg2.extras import Json

from .. import db, models
from ..config import get_settings
from .executor import ExecutionError, execute_select
from .guard import GuardError
from .planner import Turn, fallback_planner, get_planner
from .scope import ScopeError, referenced_tables

_NLSQL_MODEL = ("drishti-nlsql", "nlp", "1.0.0")

# result id-column -> source table, for record-id citations (the evidence trail).
_ID_COLS = {
    "CaseMasterID": "CaseMaster", "DistrictID": "District", "UnitID": "Unit",
    "AccusedMasterID": "Accused", "VictimMasterID": "Victim", "ComplainantID": "ComplainantDetails",
    "HotspotID": "CrimeHotspot", "PredictionID": "CrimePrediction", "PatternID": "CrimePattern",
    "RiskScoreID": "CrimeRiskScore", "AlertID": "AlertHistory", "EntityID": "EntityGraph",
    "SummaryID": "AISummary",
}
_KANNADA = re.compile(r"[\u0c80-\u0cff]")


@dataclass
class AskOutcome:
    session_id: int
    reply: str
    language: str
    sql: Optional[str]                 # the SQL that RAN (None if blocked/clarify/error)
    cited_record_ids: list[str] = field(default_factory=list)
    confidence: float = 0.0
    needs_clarification: bool = False
    blocked: bool = False
    model_version: Optional[str] = None
    row_count: int = 0
    columns: list[str] = field(default_factory=list)
    rows_preview: list[list[Any]] = field(default_factory=list)


def detect_language(text: str) -> str:
    return "kn" if _KANNADA.search(text or "") else "en"


# --------------------------------------------------------------------------- #
def ask(role: str, question: str, language: Optional[str] = None,
        session_id: Optional[int] = None, voice: Optional[dict] = None) -> AskOutcome:
    settings = get_settings()
    t0 = time.time()
    lang = language or detect_language(question)
    history = _load_history(session_id, settings.nlsql_max_history_turns) if session_id else []

    # --- plan (LLM primary, deterministic fallback on any LLM failure) ---
    planner = get_planner()
    try:
        plan = planner.plan(question, role, lang, history)
    except Exception:
        plan = fallback_planner().plan(question, role, lang, history)
    lang = plan.language or lang

    # --- clarify: ask, never guess ---
    if plan.needs_clarification or not plan.sql:
        reply = plan.clarifying_question or _clarify_text(lang)
        sid, mv = _persist(session_id, role, lang, question, reply, persisted_sql=None,
                           cites=[], confidence=plan.confidence, kind="clarify", voice=voice,
                           latency_ms=int((time.time() - t0) * 1000))
        return AskOutcome(session_id=sid, reply=reply, language=lang, sql=None,
                          confidence=round(plan.confidence, 4), needs_clarification=True,
                          model_version=mv)

    # --- execute under the guarded, read-only, scoped path ---
    try:
        cleaned_sql, columns, rows = execute_select(plan.sql, role)
    except (ScopeError, GuardError) as exc:
        reply = _blocked_text(lang, str(exc))
        sid, mv = _persist(session_id, role, lang, question, reply, persisted_sql=plan.sql,
                           cites=[], confidence=0.0, kind="blocked", voice=voice,
                           latency_ms=int((time.time() - t0) * 1000))
        return AskOutcome(session_id=sid, reply=reply, language=lang, sql=None,
                          confidence=0.0, blocked=True, model_version=mv)
    except ExecutionError as exc:
        reply = _error_text(lang, str(exc))
        sid, mv = _persist(session_id, role, lang, question, reply, persisted_sql=plan.sql,
                           cites=[], confidence=0.3, kind="error", voice=voice,
                           latency_ms=int((time.time() - t0) * 1000))
        return AskOutcome(session_id=sid, reply=reply, language=lang, sql=None,
                          confidence=0.3, model_version=mv)

    # --- grounded reply + citations + honest confidence ---
    cites = _citations(columns, rows, cleaned_sql, settings.nlsql_max_citations)
    reply = _grounded_reply(columns, rows, lang, settings.nlsql_row_cap)
    confidence = _confidence(plan.confidence, rows)
    sid, mv = _persist(session_id, role, lang, question, reply, persisted_sql=cleaned_sql,
                       cites=cites, confidence=confidence, kind="answer", voice=voice,
                       latency_ms=int((time.time() - t0) * 1000), row_count=len(rows))

    return AskOutcome(
        session_id=sid, reply=reply, language=lang, sql=cleaned_sql, cited_record_ids=cites,
        confidence=confidence, model_version=mv, row_count=len(rows), columns=columns,
        rows_preview=rows[:20],
    )


# --------------------------------------------------------------------------- #
def _load_history(session_id: int, limit: int) -> list[Turn]:
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT "Sender"::text, "ContentText" FROM "ChatMessage" '
                'WHERE "SessionID"=%s ORDER BY "MessageID" DESC LIMIT %s',
                (session_id, limit * 2))
            rows = cur.fetchall()
    return [Turn(sender=r[0], text=r[1] or "") for r in reversed(rows)]


def _citations(columns: list[str], rows: list[list], sql: str, cap: int) -> list[str]:
    id_cols = [(i, _ID_COLS[c]) for i, c in enumerate(columns) if c in _ID_COLS]
    cites: list[str] = []
    if id_cols:
        for row in rows:
            for i, table in id_cols:
                v = row[i]
                if v is None:
                    continue
                ref = f"{table}:{v}"
                if ref not in cites:
                    cites.append(ref)
                if len(cites) >= cap:
                    return cites
        return cites
    # aggregate: no individual records -> honest source-table provenance
    main = [t for t in ("CaseMaster", "CrimeHotspot", "CrimePrediction", "CrimePattern",
                        "AlertHistory", "CrimeRiskScore", "SocialIndicator", "EconomicIndicator")
            if t in referenced_tables(sql)]
    return [f"{t}(aggregated)" for t in main]


def _col(columns: list[str], name: str) -> int:
    try:
        return columns.index(name)
    except ValueError:
        return -1


def _grounded_reply(columns: list[str], rows: list[list], lang: str, cap: int) -> str:
    kn = lang == "kn"
    n = len(rows)
    if n == 0:
        return "ಈ ಪ್ರಶ್ನೆಗೆ ಹೊಂದುವ ದಾಖಲೆಗಳಿಲ್ಲ." if kn else "No matching records were found for that query."

    ci_count = _col(columns, "case_count")
    ci_dist = _col(columns, "DistrictName")
    ci_month = _col(columns, "month")
    ci_crime = _col(columns, "CrimeNo")

    # single aggregate number
    if n == 1 and ci_count != -1 and len(columns) == 1:
        val = rows[0][ci_count]
        return (f"{val} ಹೊಂದುವ ಎಫ್‌ಐಆರ್‌ಗಳು." if kn else f"{val} matching FIR(s).")
    # grouped counts (top / by-district)
    if ci_count != -1 and ci_dist != -1:
        top_name, top_val = rows[0][ci_dist], rows[0][ci_count]
        return (f"{top_name} ಮುಂಚೂಣಿಯಲ್ಲಿ ({top_val}); ಒಟ್ಟು {n} ಜಿಲ್ಲೆ(ಗಳು)."
                if kn else f"{top_name} leads with {top_val} FIR(s); {n} district(s) in total.")
    # monthly trend
    if ci_month != -1 and ci_count != -1:
        last = rows[-1]
        return (f"{n} ತಿಂಗಳ ಪ್ರವೃತ್ತಿ; ಇತ್ತೀಚಿನ {last[ci_month]}: {last[ci_count]}."
                if kn else f"Monthly counts over {n} month(s); latest {last[ci_month]}: {last[ci_count]}.")
    # case list
    if ci_crime != -1:
        first = rows[0]
        crime_no = first[ci_crime]
        cap_note = f" (showing up to {cap})" if n >= cap else ""
        return (f"{n} ಎಫ್‌ಐಆರ್{cap_note}. ಇತ್ತೀಚಿನದು: {crime_no}."
                if kn else f"{n} FIR(s){cap_note}. Most recent: {crime_no}.")
    return (f"{n} ಸಾಲು(ಗಳು) ದೊರಕಿದವು." if kn else f"{n} row(s) returned.")


def _confidence(base: float, rows: list[list]) -> float:
    c = base
    if not rows:
        c = min(c, 0.45)      # honest: matched an intent but found nothing
    return round(max(0.0, min(1.0, c)), 4)


def _clarify_text(lang: str) -> str:
    return ("Could you rephrase that a little more specifically?" if lang != "kn"
            else "ದಯವಿಟ್ಟು ಪ್ರಶ್ನೆಯನ್ನು ಸ್ವಲ್ಪ ನಿರ್ದಿಷ್ಟವಾಗಿ ಕೇಳಿ.")


def _blocked_text(lang: str, reason: str) -> str:
    return (f"I can't run that request: {reason}" if lang != "kn"
            else f"ಈ ವಿನಂತಿಯನ್ನು ನಡೆಸಲಾಗದು: {reason}")


def _error_text(lang: str, reason: str) -> str:
    return (f"That query couldn't be executed ({reason}). Try rephrasing." if lang != "kn"
            else f"ಈ ಪ್ರಶ್ನೆಯನ್ನು ನಡೆಸಲಾಗಲಿಲ್ಲ ({reason}). ಬೇರೆ ರೀತಿಯಲ್ಲಿ ಕೇಳಿ.")


_LOW_CONF_THRESHOLD = 0.6      # below this a voice transcript is flagged (doc 01 §4.7/§9)


def _persist(session_id: Optional[int], role: str, language: str, question: str,
             reply: str, *, persisted_sql: Optional[str], cites: list[str],
             confidence: float, kind: str, latency_ms: int,
             row_count: int = 0, voice: Optional[dict] = None) -> tuple[int, str]:
    """Write the user + assistant turns (+ audit + optional VoiceTranscript).
    Returns (session_id, model_label)."""
    name, mtype, ver = _NLSQL_MODEL
    conf = round(max(0.0, min(1.0, float(confidence))), 5)
    with db.rw_conn() as conn:
        mv_id = models.get_or_create_model_version(
            conn, name, mtype, ver, framework="nl2sql-guarded",
            hyperparameters={"read_only": True, "whitelist": "SELECT", "role_scoped": True})
        mv_label = models.model_version_label(conn, mv_id)
        with conn.cursor() as cur:
            if session_id is None:
                cur.execute(
                    'INSERT INTO "ChatSession" ("UserID","Role","Language","Title") '
                    'VALUES (NULL,%s,%s,%s) RETURNING "SessionID"',
                    (role, language, question[:120]))
                session_id = int(cur.fetchone()[0])
            cur.execute(
                'INSERT INTO "ChatMessage" ("SessionID","Sender","ContentText","Language") '
                "VALUES (%s,'user',%s,%s) RETURNING \"MessageID\"",
                (session_id, question, language))
            user_message_id = int(cur.fetchone()[0])
            # Phase 4: a dictated question persists its transcript + confidence,
            # flagging low-confidence recognitions for read-back confirmation.
            if voice is not None:
                vconf = voice.get("confidence")
                vconf = float(vconf) if vconf is not None else None
                low = voice.get("is_low_confidence")
                if low is None:
                    low = vconf is not None and vconf < _LOW_CONF_THRESHOLD
                cur.execute(
                    'INSERT INTO "VoiceTranscript" '
                    '("MessageID","RawAudioRef","TranscriptText","Language","Confidence","IsLowConfidence") '
                    "VALUES (%s,NULL,%s,%s,%s,%s)",
                    (user_message_id, voice.get("transcript") or question,
                     voice.get("language") or language,
                     round(vconf, 5) if vconf is not None else None, bool(low)))
            cur.execute(
                'INSERT INTO "ChatMessage" '
                '("SessionID","Sender","ContentText","Language","GeneratedSQL",'
                '"CitedRecordIds","Confidence","ModelVersionID") '
                "VALUES (%s,'assistant',%s,%s,%s,%s,%s,%s)",
                (session_id, reply, language, persisted_sql, Json(cites), conf, mv_id))
        models.log_inference(
            conn, mv_id,
            inputs={"question": question, "role": role, "kind": kind, "sql": persisted_sql},
            outputs={"rows": row_count, "citations": len(cites), "blocked": kind == "blocked"},
            confidence=conf, latency_ms=latency_ms)
    return session_id, mv_label
