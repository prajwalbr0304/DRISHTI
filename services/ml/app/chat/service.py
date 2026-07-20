"""Read-only Ask-DRISHTI chat history (doc 01 §4.7 — History sub-page).

Plain operational reads over ChatSession / ChatMessage / VoiceTranscript (the
Wave-A extension tables), joined to users (display name) and ModelVersion (the
model label on assistant turns). No writes, no NL->SQL — the conversational
query engine is Phase 2. Reads run under the restricted read-only role. All
identifiers/casing match police_fir_extensions.sql.
"""
from __future__ import annotations

from typing import Optional

from .. import db
from .schemas import (ChatMessageOut, ChatSessionDetail, ChatSessionSummary,
                      ChatSessionsResponse, VoiceInfo)


def list_sessions(limit: int = 50) -> ChatSessionsResponse:
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT s."SessionID", s."Title", s."Role", s."Language", s."CreatedAt"::text, '
                'u."display_name", '
                'COUNT(m."MessageID"), '
                'COUNT(*) FILTER (WHERE m."Sender" = \'user\'), '
                'COUNT(*) FILTER (WHERE m."Sender" = \'assistant\'), '
                'MAX(m."CreatedAt")::text, '
                '(SELECT m2."ContentText" FROM "ChatMessage" m2 '
                '   WHERE m2."SessionID" = s."SessionID" AND m2."Sender" = \'user\' '
                '   ORDER BY m2."MessageID" LIMIT 1), '
                'EXISTS(SELECT 1 FROM "VoiceTranscript" vt JOIN "ChatMessage" m3 '
                '   ON m3."MessageID" = vt."MessageID" WHERE m3."SessionID" = s."SessionID") '
                'FROM "ChatSession" s '
                'LEFT JOIN "users" u ON u."user_id" = s."UserID" '
                'LEFT JOIN "ChatMessage" m ON m."SessionID" = s."SessionID" '
                'GROUP BY s."SessionID", s."Title", s."Role", s."Language", s."CreatedAt", u."display_name" '
                'ORDER BY s."CreatedAt" DESC, s."SessionID" DESC LIMIT %s',
                (limit,))
            rows = cur.fetchall()
    sessions = [
        ChatSessionSummary(
            session_id=int(r[0]), title=r[1], role=r[2], language=r[3], created_at=r[4],
            user_display_name=r[5], message_count=int(r[6] or 0),
            user_message_count=int(r[7] or 0), assistant_message_count=int(r[8] or 0),
            last_activity=r[9], first_question=r[10], has_voice=bool(r[11]))
        for r in rows
    ]
    return ChatSessionsResponse(count=len(sessions), sessions=sessions)


def get_session(session_id: int) -> Optional[ChatSessionDetail]:
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT s."SessionID", s."Title", s."Role", s."Language", s."CreatedAt"::text, '
                'u."display_name" FROM "ChatSession" s '
                'LEFT JOIN "users" u ON u."user_id" = s."UserID" WHERE s."SessionID" = %s',
                (session_id,))
            head = cur.fetchone()
            if not head:
                return None
            cur.execute(
                'SELECT m."MessageID", m."Sender"::text, m."ContentText", m."Language", '
                'm."GeneratedSQL", m."CitedRecordIds", m."Confidence"::float, '
                'mv."ModelName", mv."Version", m."CreatedAt"::text, '
                'vt."TranscriptText", vt."Language", vt."Confidence"::float, '
                'vt."IsLowConfidence", vt."RawAudioRef" '
                'FROM "ChatMessage" m '
                'LEFT JOIN "ModelVersion" mv ON mv."ModelVersionID" = m."ModelVersionID" '
                'LEFT JOIN "VoiceTranscript" vt ON vt."MessageID" = m."MessageID" '
                'WHERE m."SessionID" = %s ORDER BY m."MessageID"',
                (session_id,))
            msg_rows = cur.fetchall()

    messages = [_message(r) for r in msg_rows]
    return ChatSessionDetail(
        session_id=int(head[0]), title=head[1], role=head[2], language=head[3],
        created_at=head[4], user_display_name=head[5], messages=messages)


def _message(r) -> ChatMessageOut:
    model_version = f"{r[7]}@{r[8]}" if r[7] and r[8] else None
    cited = r[5] if isinstance(r[5], list) else []
    voice = None
    if r[10] is not None or r[14] is not None:      # a VoiceTranscript row exists
        voice = VoiceInfo(
            transcript_text=r[10], language=r[11],
            confidence=float(r[12]) if r[12] is not None else None,
            is_low_confidence=bool(r[13]), raw_audio_ref=r[14])
    return ChatMessageOut(
        message_id=int(r[0]), sender=r[1], content=r[2], language=r[3],
        generated_sql=r[4], cited_record_ids=cited,
        confidence=float(r[6]) if r[6] is not None else None,
        model_version=model_version, created_at=r[9], voice=voice)


# --- Phase 2: NL->SQL conversational engine --------------------------------
from ..config import get_settings          # noqa: E402
from ..contracts import AiResult            # noqa: E402
from ..nlsql import engine as _engine       # noqa: E402
from ..nlsql.schema import ROLES            # noqa: E402
from .schemas import AskResponse, TranslateResponse  # noqa: E402


def _resolve_role(x_role: Optional[str]) -> str:
    """Trust the X-Role signal (pre-Phase-14, same as the rest of the app), but
    clamp anything unrecognised to the configured default so scope stays defined."""
    role = (x_role or get_settings().default_role or "investigator").strip()
    return role if role in ROLES else (get_settings().default_role or "investigator")


def _outcome_to_response(o: "_engine.AskOutcome") -> AskResponse:
    if o.blocked:
        reasoning = ("Refused server-side by the read-only + role-scope guard; "
                     "no rows were returned.")
    elif o.needs_clarification:
        reasoning = "Ambiguous request — asked a clarifying question rather than guessing."
    else:
        reasoning = (f"Translated to a read-only SELECT, executed under the drishti_readonly "
                     f"role and scoped to the caller's role; reply grounded in {o.row_count} "
                     f"returned row(s).")
    result = AiResult(
        answer=o.reply,
        confidence=o.confidence,
        source_record_ids=[str(c) for c in o.cited_record_ids],
        reasoning_summary=reasoning,
        model_version=o.model_version or "drishti-nlsql@1.0.0",
    )
    return AskResponse(
        result=result, session_id=o.session_id, reply=o.reply, language=o.language, sql=o.sql,
        cited_record_ids=o.cited_record_ids, confidence=o.confidence,
        needs_clarification=o.needs_clarification, blocked=o.blocked,
        model_version=o.model_version, row_count=o.row_count, columns=o.columns,
        rows_preview=o.rows_preview, planner_source=o.planner_source,
        planner_primary=o.planner_primary, planner_degraded=o.planner_degraded,
        visualization=o.visualization)


def ask(x_role: Optional[str], question: str, language: Optional[str] = None,
        session_id: Optional[int] = None, voice: Optional[dict] = None) -> AskResponse:
    role = _resolve_role(x_role)
    outcome = _engine.ask(role, question, language=language, session_id=session_id, voice=voice)
    return _outcome_to_response(outcome)


def explain(x_role: Optional[str], context: str, language: Optional[str] = None,
            session_id: Optional[int] = None) -> AskResponse:
    """Route a chart/alert context through the same grounded, cited engine."""
    role = _resolve_role(x_role)
    outcome = _engine.ask(role, context, language=language, session_id=session_id)
    return _outcome_to_response(outcome)


def _provider_chat(messages: list[dict]) -> Optional[str]:
    """Provider-neutral chat completion for translate / auxiliary text (Prompt 19
    §B/§E). Routes to Catalyst QuickML LLM Serving when configured, else a
    self-hosted OpenAI-compatible runtime, else returns None. Fail-closed: there is
    NO commercial default, so an unconfigured provider yields no fabricated text."""
    s = get_settings()
    provider = s.primary_planner_name()
    try:
        import httpx

        if provider == "catalyst-quickml-llm":
            endpoint = s.quickml_llm_endpoint.rstrip("/")
            url = endpoint if endpoint.endswith("/chat/completions") else f"{endpoint}/chat/completions"
            headers = {"Content-Type": "application/json"}
            if s.quickml_llm_api_key.strip():
                headers["Authorization"] = f"Bearer {s.quickml_llm_api_key.strip()}"
            model, timeout = s.quickml_llm_model, s.quickml_llm_timeout_s
        elif provider == "openai-compatible":
            url = f"{s.llm_base_url.rstrip('/')}/chat/completions"
            headers = {"Authorization": f"Bearer {s.llm_api_key}", "Content-Type": "application/json"}
            model, timeout = s.llm_model, s.llm_timeout_s
        else:
            return None      # no semantic provider configured -> no fabrication
        resp = httpx.post(url, headers=headers,
                          json={"model": model, "temperature": 0, "messages": messages},
                          timeout=timeout)
        resp.raise_for_status()
        return (resp.json()["choices"][0]["message"]["content"] or "").strip() or None
    except Exception:
        return None


def translate(text: str, target: str) -> TranslateResponse:
    """Best-effort EN<->KN translation for the bilingual PDF export (Phase 5).

    Provider-neutral: routes through the configured semantic provider (Catalyst
    QuickML LLM Serving preferred). When none is configured it returns no
    translation (available=False) rather than fabricating — the PDF then shows the
    original with an honest 'translation unavailable' note. (Catalyst Zia does not
    expose a translation service in the IN DC; see app/zia_voice.py.)
    """
    tgt = "kn" if target == "kn" else "en"
    text = (text or "").strip()
    if not text:
        return TranslateResponse(text=text, translated=None, target=tgt, available=False)
    target_name = "Kannada" if tgt == "kn" else "English"
    messages = [
        {"role": "system", "content":
            f"Translate the user's text to {target_name}. Keep police/legal terms and "
            "identifiers (FIR, IPC/section numbers, district and station names) intact. "
            "Reply with ONLY the translation — no quotes, no notes."},
        {"role": "user", "content": text},
    ]
    out = _provider_chat(messages)
    return TranslateResponse(text=text, translated=out or None, target=tgt, available=bool(out))


def capabilities() -> "CapabilitiesResponse":
    """Truthful Ask-DRISHTI capabilities the SPA reads to label itself honestly:
    the semantic planner primary + fallback, the voice provider (browser vs Zia),
    supported languages, allowed visualization kinds and the scope flags."""
    from ..nlsql.viz import ALLOWED_KINDS
    from .. import zia_voice
    from .schemas import CapabilitiesResponse, SemanticPlannerInfo, ScopeFlags

    s = get_settings()
    return CapabilitiesResponse(
        semantic_planner=SemanticPlannerInfo(
            primary=s.primary_planner_name(),
            provider=s.semantic_provider(),
            quickml_llm_configured=s.quickml_llm_configured(),
            fallback="deterministic-fallback"),
        voice=zia_voice.voice_capability_status(),
        languages=["en", "kn"],
        visualization_kinds=sorted(ALLOWED_KINDS),
        scope=ScopeFlags(
            query_voice_enabled=bool(s.query_voice_enabled),
            evidence_extraction_enabled=bool(s.evidence_extraction_enabled)),
    )
