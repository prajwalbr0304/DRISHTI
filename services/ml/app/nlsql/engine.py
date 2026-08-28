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

import hashlib
import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from psycopg2.extras import Json

from .. import db, models
from ..config import get_settings
from .briefing import build_briefing, is_briefing_request
from .executor import ExecutionError, execute_select
from .guard import GuardError
from .planner import Turn, fallback_planner, get_planner
from .schema import requires_aggregate
from .scope import ScopeError, is_aggregate, referenced_tables
from .viz import build_visualization

_NLSQL_MODEL = ("drishti-nlsql", "nlp", "1.0.0")
_ROWS_PREVIEW_CAP = 50      # rows sent to the browser for the answer table/chart
_DEFAULT_OWNER_SUBJECT = "local:engine"


class ChatSessionAccessError(RuntimeError):
    """An absent, foreign, or differently scoped conversation continuation."""


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
    # Prompt 19 §B.7: which planner actually produced the plan, the configured
    # primary for the live contract, and whether we fell back due to an outage.
    planner_source: str = "deterministic-fallback"
    planner_primary: str = "deterministic-fallback"
    planner_degraded: bool = False
    # Prompt 19 §F: server-validated typed visualization specification.
    visualization: Optional[dict] = None


def detect_language(text: str) -> str:
    return "kn" if _KANNADA.search(text or "") else "en"


# --------------------------------------------------------------------------- #
def ask(role: str, question: str, language: Optional[str] = None,
        session_id: Optional[int] = None, voice: Optional[dict] = None,
        owner_subject: str = _DEFAULT_OWNER_SUBJECT) -> AskOutcome:
    settings = get_settings()
    owner_subject = (owner_subject or "").strip()
    if not owner_subject:
        raise ChatSessionAccessError("chat owner is required")
    t0 = time.time()
    lang = language or detect_language(question)
    primary_name = settings.primary_planner_name()

    # --- briefing / overview: compose from several role-scoped aggregates ---
    # (a single SELECT can't answer "give me a briefing for my scope").
    if is_briefing_request(question):
        return _briefing(
            role, question, lang, session_id, voice, t0, primary_name, owner_subject)

    history = (_load_history(session_id, settings.nlsql_max_history_turns,
                             owner_subject, role) if session_id else [])

    # --- plan (semantic provider primary, deterministic LABELLED fallback) ---
    # Fail-closed: when the configured semantic provider is unreachable we drop to
    # the deterministic offline planner and MARK the answer as a degraded/fallback
    # plan — never a silent switch to a commercial API.
    planner = get_planner()
    planner_source = getattr(planner, "name", "deterministic-fallback")
    planner_degraded = False
    try:
        plan = planner.plan(question, role, lang, history)
    except Exception:
        plan = fallback_planner().plan(question, role, lang, history)
        planner_degraded = planner_source != "deterministic-fallback"
        planner_source = "deterministic-fallback"
    lang = plan.language or lang

    # --- Deterministic override for reference-entity counts ------------------
    # The LLM sometimes confuses "how many stations" with "how many FIRs".
    # The offline planner maps these DETERMINISTICALLY and CORRECTLY, so prefer
    # it whenever the question is clearly about stations/districts (not cases).
    fb_plan = fallback_planner().plan(question, role, lang, history)
    if fb_plan.intent in ("count_stations", "count_districts") and fb_plan.sql:
        plan = fb_plan
        planner_source = "deterministic-fallback"

    # Aggregate-only roles (schema.AGGREGATE_ONLY_ROLES) must receive an aggregate query.
    # The semantic planner is NOT trusted to honour that on its own: if it
    # returned a non-aggregate SELECT (which the scope guard would then block) or
    # asked to clarify a question the deterministic planner can still map, we
    # substitute the deterministic aggregate plan so the guarantee never depends
    # on model cooperation. The scope guard in the executor still enforces the
    # boundary independently (defence in depth) — this only avoids a needless
    # block/clarify when a safe aggregate answer is available.
    if requires_aggregate(role) and (not plan.sql or not is_aggregate(plan.sql)):
        fb = fallback_planner().plan(question, role, lang, history)
        if fb.sql and is_aggregate(fb.sql):
            plan = fb
            lang = plan.language or lang
            planner_source = "deterministic-fallback"    # scope-safe substitution

    # planner-label triple carried onto every outcome (transparency).
    plabels = dict(planner_source=planner_source, planner_primary=primary_name,
                   planner_degraded=planner_degraded)

    # --- clarify: ask, never guess ---
    if plan.needs_clarification or not plan.sql:
        reply = plan.clarifying_question or _clarify_text(lang)
        sid, mv = _persist(session_id, role, lang, question, reply, persisted_sql=None,
                           cites=[], confidence=plan.confidence, kind="clarify", voice=voice, owner_subject=owner_subject,
                           latency_ms=int((time.time() - t0) * 1000), planner_source=planner_source)
        return AskOutcome(session_id=sid, reply=reply, language=lang, sql=None,
                          confidence=round(plan.confidence, 4), needs_clarification=True,
                          model_version=mv, **plabels)

    # --- execute under the guarded, read-only, scoped path ---
    try:
        cleaned_sql, columns, rows = execute_select(plan.sql, role)
    except (ScopeError, GuardError) as exc:
        reply = _blocked_text(lang, str(exc))
        sid, mv = _persist(session_id, role, lang, question, reply, persisted_sql=plan.sql,
                           cites=[], confidence=0.0, kind="blocked", voice=voice, owner_subject=owner_subject,
                           latency_ms=int((time.time() - t0) * 1000), planner_source=planner_source)
        return AskOutcome(session_id=sid, reply=reply, language=lang, sql=None,
                          confidence=0.0, blocked=True, model_version=mv, **plabels)
    except ExecutionError as exc:
        reply = _error_text(lang, str(exc))
        sid, mv = _persist(session_id, role, lang, question, reply, persisted_sql=plan.sql,
                           cites=[], confidence=0.3, kind="error", voice=voice, owner_subject=owner_subject,
                           latency_ms=int((time.time() - t0) * 1000), planner_source=planner_source)
        return AskOutcome(session_id=sid, reply=reply, language=lang, sql=None,
                          confidence=0.3, model_version=mv, **plabels)

    # --- grounded reply + citations + honest confidence ---
    cites = _citations(columns, rows, cleaned_sql, settings.nlsql_max_citations)
    reply = _grounded_reply(columns, rows, lang, settings.nlsql_row_cap)
    confidence = _confidence(plan.confidence, rows)
    # Prompt 19 §F: deterministic, server-validated typed visualization spec
    # (never model-generated code) chosen from result shape + intent.
    viz = build_visualization(
        columns, rows, intent=plan.intent, language=lang, citations=cites,
        confidence=confidence, role=role, row_total=len(rows))
    sid, mv = _persist(session_id, role, lang, question, reply, persisted_sql=cleaned_sql,
                       cites=cites, confidence=confidence, kind="answer", voice=voice, owner_subject=owner_subject,
                       latency_ms=int((time.time() - t0) * 1000), row_count=len(rows),
                       planner_source=planner_source)

    return AskOutcome(
        session_id=sid, reply=reply, language=lang, sql=cleaned_sql, cited_record_ids=cites,
        confidence=confidence, model_version=mv, row_count=len(rows), columns=columns,
        rows_preview=rows[:_ROWS_PREVIEW_CAP], visualization=viz, **plabels,
    )


# --------------------------------------------------------------------------- #
def _briefing(role: str, question: str, lang: str, session_id: Optional[int],
              voice: Optional[dict], t0: float, primary_name: str,
              owner_subject: str) -> AskOutcome:
    """Compose + persist a grounded, cited multi-metric briefing."""
    result = build_briefing(role, lang)
    kind = "answer" if result.ran else "clarify"
    sid, mv = _persist(
        session_id, role, lang, question, result.reply,
        persisted_sql=result.sql_display, cites=result.citations,
        confidence=result.confidence, kind=kind, voice=voice, owner_subject=owner_subject,
        latency_ms=int((time.time() - t0) * 1000), row_count=result.ran,
        planner_source="deterministic-briefing")
    cols = ([] if not result.metrics
            else (["ಮಾಪನ", "ಮೌಲ್ಯ"] if lang == "kn" else ["Metric", "Value"]))
    viz = build_visualization(
        cols, result.metrics, intent="briefing", language=lang, citations=result.citations,
        confidence=result.confidence, role=role, row_total=len(result.metrics)) if result.metrics else None
    return AskOutcome(
        session_id=sid, reply=result.reply, language=lang, sql=result.sql_display,
        cited_record_ids=result.citations, confidence=result.confidence,
        needs_clarification=(result.ran == 0), model_version=mv,
        row_count=len(result.metrics), columns=cols, rows_preview=result.metrics,
        visualization=viz, planner_source="deterministic-briefing",
        planner_primary=primary_name, planner_degraded=False)


# --------------------------------------------------------------------------- #
def _load_history(session_id: int, limit: int, owner_subject: str,
                  role: str) -> list[Turn]:
    """Load memory only after owner and role-snapshot authorization."""
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT "Role" FROM "ChatSession" '
                'WHERE "SessionID"=%s AND "OwnerSubject"=%s',
                (session_id, owner_subject))
            session = cur.fetchone()
            if not session or session[0] != role:
                raise ChatSessionAccessError("chat session not found")
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


_COUNT_WORDS = ("count", "cnt", "total", "number", "num", "qty", "quantity", "tally")


def _humanize_label(col: str) -> str:
    """Turn a column alias into a readable noun: split camelCase + underscores,
    drop the aggregate word. e.g. 'PoliceStationCount' -> 'police station',
    'station_count' -> 'station', 'DistrictName' -> 'district name'."""
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", col)     # split camel/Pascal case
    s = s.replace("_", " ").strip().lower()
    words = [w for w in s.split() if w and w not in _COUNT_WORDS]
    return " ".join(words)


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _first_col_where(columns: list[str], rows: list[list], want_numeric: bool,
                     exclude: int = -1) -> int:
    """Index of the first column whose first non-null value matches the wanted
    kind (numeric vs. text). Returns -1 if none."""
    for i in range(len(columns)):
        if i == exclude:
            continue
        for r in rows:
            v = r[i]
            if v is None:
                continue
            num = _is_num(v)
            if want_numeric and num:
                return i
            if not want_numeric and isinstance(v, str):
                return i
            break      # first non-null decided this column's kind
    return -1


def _scalar_reply(col: str, val: Any, kn: bool) -> str:
    """Report a single aggregate value (COUNT/SUM/AVG/…), whatever it measures."""
    if val is None:
        return ("ಈ ಪ್ರಶ್ನೆಗೆ ಮೌಲ್ಯ ಲೆಕ್ಕ ಹಾಕಲಾಗಲಿಲ್ಲ." if kn
                else "No value could be computed for that query.")
    if col == "case_count":     # emitted by the offline planner for FIR counts
        return (f"{val} ಹೊಂದುವ ಎಫ್‌ಐಆರ್‌ಗಳು." if kn else f"{val} matching FIR(s).")
    is_count = any(w in col.lower() for w in _COUNT_WORDS)
    if kn:
        return (f"ಒಟ್ಟು {val}." if is_count else f"ಫಲಿತಾಂಶ: {val}.")
    label = _humanize_label(col)
    if is_count and label:
        if not label.endswith("s"):
            label += "s"
        return f"There are {val} {label}."
    if is_count:
        return f"Total: {val}."
    return f"The result is {val}."


def _grounded_reply(columns: list[str], rows: list[list], lang: str, cap: int) -> str:
    """Build an NL reply grounded in the ACTUAL rows. Column names are matched
    by SHAPE (a scalar / a label+measure / a trend / a case list), not by fixed
    aliases, so it works whether the SQL came from the LLM or the offline planner."""
    kn = lang == "kn"
    n = len(rows)
    if n == 0:
        return "ಈ ಪ್ರಶ್ನೆಗೆ ಹೊಂದುವ ದಾಖಲೆಗಳಿಲ್ಲ." if kn else "No matching records were found for that query."

    # 1) single scalar aggregate (COUNT/SUM/AVG/…): report the value itself
    if n == 1 and len(columns) == 1:
        return _scalar_reply(columns[0], rows[0][0], kn)

    ci_month = _col(columns, "month")
    ci_crime = _col(columns, "CrimeNo")

    # 2) case list (has a CrimeNo column) — individual records
    if ci_crime != -1:
        crime_no = rows[0][ci_crime]
        cap_note = f" (showing up to {cap})" if n >= cap else ""
        return (f"{n} ಎಫ್‌ಐಆರ್{cap_note}. ಇತ್ತೀಚಿನದು: {crime_no}."
                if kn else f"{n} FIR(s){cap_note}. Most recent: {crime_no}.")

    num_idx = _first_col_where(columns, rows, want_numeric=True)

    # 3) monthly trend (a 'month' column + a numeric measure)
    if ci_month != -1 and num_idx != -1:
        last = rows[-1]
        return (f"{n} ತಿಂಗಳ ಪ್ರವೃತ್ತಿ; ಇತ್ತೀಚಿನ {last[ci_month]}: {last[num_idx]}."
                if kn else f"Monthly counts over {n} month(s); latest {last[ci_month]}: {last[num_idx]}.")

    # 4) grouped / ranked (a label column + a numeric measure)
    if num_idx != -1:
        txt_idx = _first_col_where(columns, rows, want_numeric=False, exclude=num_idx)
        if txt_idx != -1:
            # Never assume row 0 is the largest: a planner-produced SELECT may omit
            # ORDER BY, and claiming the first row "leads" would be a FALSE
            # statement. Pick the true maximum from the returned rows.
            best = rows[0]
            for r in rows:
                try:
                    if r[num_idx] is not None and (best[num_idx] is None
                                                   or float(r[num_idx]) > float(best[num_idx])):
                        best = r
                except (TypeError, ValueError):
                    continue
            top_name, top_val = best[txt_idx], best[num_idx]
            if n == 1:
                return f"{top_name}: {top_val}."
            return (f"{top_name} ಅತಿ ಹೆಚ್ಚು ({top_val}); ಒಟ್ಟು {n} ಗುಂಪುಗಳು."
                    if kn else f"{top_name} is highest with {top_val}; {n} group(s) in total.")

    # 5) fallback: honest row count
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


def _sql_hash(sql: Optional[str]) -> Optional[str]:
    """SHA-256 of the executed plan/SQL (C6) — a stable, non-sensitive fingerprint
    for the audit trail (the full SQL is already stored on the assistant turn)."""
    if not sql:
        return None
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


def _persist(session_id: Optional[int], role: str, language: str, question: str,
             reply: str, *, persisted_sql: Optional[str], cites: list[str],
             confidence: float, kind: str, latency_ms: int, owner_subject: str,
             row_count: int = 0, voice: Optional[dict] = None,
             planner_source: str = "deterministic-fallback") -> tuple[int, str]:
    """Atomically authorize the thread and persist both finalized turns."""
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
                    'INSERT INTO "ChatSession" '
                    '("UserID","OwnerSubject","Role","Language","Title") '
                    'VALUES (NULL,%s,%s,%s,%s) RETURNING "SessionID"',
                    (owner_subject, role, language, question[:120]))
                session_id = int(cur.fetchone()[0])
            else:
                # Recheck inside the write transaction to prevent a foreign or
                # differently scoped thread from being appended after planning.
                cur.execute(
                    'SELECT "Role" FROM "ChatSession" '
                    'WHERE "SessionID"=%s AND "OwnerSubject"=%s FOR UPDATE',
                    (session_id, owner_subject))
                session = cur.fetchone()
                if not session or session[0] != role:
                    raise ChatSessionAccessError("chat session not found")

            cur.execute(
                'INSERT INTO "ChatMessage" ("SessionID","Sender","ContentText","Language") '
                "VALUES (%s,'user',%s,%s) RETURNING \"MessageID\"",
                (session_id, question, language))
            user_message_id = int(cur.fetchone()[0])
            if voice is not None:
                vconf = voice.get("confidence")
                vconf = float(vconf) if vconf is not None else None
                threshold = float(get_settings().voice_low_confidence_threshold)
                low = vconf is None or vconf < threshold
                cur.execute(
                    'INSERT INTO "VoiceTranscript" '
                    '("MessageID","RawAudioRef","TranscriptText","Language","Confidence","IsLowConfidence") '
                    "VALUES (%s,NULL,%s,%s,%s,%s)",
                    (user_message_id, voice.get("transcript") or question,
                     voice.get("language") or language,
                     round(vconf, 5) if vconf is not None else None, low))
            cur.execute(
                'INSERT INTO "ChatMessage" '
                '("SessionID","Sender","ContentText","Language","GeneratedSQL",'
                '"CitedRecordIds","Confidence","ModelVersionID") '
                "VALUES (%s,'assistant',%s,%s,%s,%s,%s,%s)",
                (session_id, reply, language, persisted_sql, Json(cites), conf, mv_id))
        models.log_inference(
            conn, mv_id,
            inputs={"question": question, "role": role, "kind": kind,
                    "planner_source": planner_source, "sql_sha256": _sql_hash(persisted_sql)},
            outputs={"rows": row_count, "citations": len(cites), "blocked": kind == "blocked",
                     "refusal": kind == "blocked", "sql_sha256": _sql_hash(persisted_sql)},
            confidence=conf, latency_ms=latency_ms)
    return session_id, mv_label
