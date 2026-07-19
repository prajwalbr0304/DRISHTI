"""Optional approved-text RAG assistant service (Phase 15).

Contract (prompt2.md Phase 15):
  * uses ONLY approved SOP/policy text (+ approved structured text); never uploaded
    file bytes (no OCR) and never raw case narratives;
  * enforces the same identity/demo-role and case/unit scope checks as ordinary
    APIs before retrieval;
  * cites source/version and REFUSES when no approved source supports the answer
    (never invents case facts);
  * retains only DATA-MINIMIZED prompt/response/audit metadata with an explicit
    synthetic retention window; never logs secrets or unrestricted evidence text;
  * is OPTIONAL — the demo works with it off (graceful disabled state), and it
    uses Catalyst QuickML when that capability is enabled (else a deterministic
    offline approved-text fake, never a third-party RAG service).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import os
import time
from typing import Optional

from psycopg2.extras import Json

from .. import audit, db
from ..cases.permissions import CASE_READ_DENY
from ..quickml import rag_enabled
from . import knowledge

_DEFAULT_RETENTION_DAYS = 30
_MAX_PREVIEW = 120


def _db_flag_enabled(key: str) -> bool:
    try:
        with db.ro_conn() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT "Enabled" FROM "FeatureFlag" WHERE "Key"=%s', (key,))
                r = cur.fetchone()
        return bool(r and r[0])
    except Exception:  # noqa: BLE001 — a missing flag/table must not crash the assistant
        return False


def assistant_available() -> bool:
    """RAG is available when its feature flag OR the QuickML env gate is on."""
    return rag_enabled() or _db_flag_enabled("rag_assistant")


def _provider() -> str:
    if rag_enabled() and os.getenv("DRISHTI_USE_CATALYST_QUICKML", "").lower() == "true":
        return "quickml"
    return "offline"


def status() -> dict:
    avail = assistant_available()
    reason = None
    if not avail:
        reason = ("RAG assistant is disabled. Enable the 'rag_assistant' feature flag "
                  "(admin) or set DRISHTI_QUICKML_RAG_ENABLED=true. QuickML is used "
                  "when DRISHTI_USE_CATALYST_QUICKML=true; otherwise an offline "
                  "approved-text fake serves the demo.")
    return {"enabled": avail, "provider": _provider() if avail else "disabled",
            "knowledge_base_version": knowledge.KNOWLEDGE_BASE_VERSION,
            "approved_sources": len(knowledge.APPROVED_SOURCES),
            "retention_days": _DEFAULT_RETENTION_DAYS, "reason": reason}


def _query_quickml(question: str) -> dict:
    from ..quickml import CatalystQuickMLRag
    ans = CatalystQuickMLRag().query(question)
    cits = [{"source": c, "version": None, "title": None} for c in ans.citations]
    return {"answer": ans.answer, "citations": cits, "refused": ans.refused,
            "knowledge_base_version": ans.knowledge_base_version or knowledge.KNOWLEDGE_BASE_VERSION}


def _log_interaction(actor: Optional[str], role: str, question: str, result: dict,
                     case_scope: Optional[str], unit_scope: Optional[str], latency_ms: int) -> None:
    """Persist ONLY data-minimized metadata (hash + short preview + citations +
    refusal + kb version + scope + latency). The answer text is never stored."""
    q = (question or "").replace("\r", " ").replace("\n", " ").strip()
    q_hash = hashlib.sha256(q.encode("utf-8")).hexdigest()
    preview = q[:_MAX_PREVIEW]
    citations = [{"source": c.get("source"), "version": c.get("version")}
                 for c in result.get("citations", [])]
    expires = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=_DEFAULT_RETENTION_DAYS)
    try:
        with db.rw_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    'INSERT INTO "RagInteraction" ("Actor","Role","QuestionHash","QuestionPreview",'
                    '"AnswerCitations","Refused","KnowledgeBaseVersion","CaseScopeRefID",'
                    '"UnitScopeRefID","LatencyMs","RetentionDays","ExpiresAt") '
                    'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING "RagInteractionID"',
                    (actor, role, q_hash, preview, Json(citations), bool(result.get("refused")),
                     result.get("knowledge_base_version"), case_scope, unit_scope, latency_ms,
                     _DEFAULT_RETENTION_DAYS, expires))
                rid = int(cur.fetchone()[0])
            audit.record(audit.Action.MODEL_RUN, "rag_interaction", rid, actor=actor, conn=conn,
                         detail={"refused": bool(result.get("refused")),
                                 "citations": len(citations), "case_scope": case_scope})
    except Exception:  # noqa: BLE001 — audit/log failure must not break the answer
        pass


def ask(role: str, question: str, *, case_scope_ref_id: Optional[str] = None,
        unit_scope_ref_id: Optional[str] = None, actor: Optional[str] = None) -> dict:
    kb_version = knowledge.KNOWLEDGE_BASE_VERSION
    # Graceful disabled state — the demo works without the assistant.
    if not assistant_available():
        return {"enabled": False, "provider": "disabled",
                "answer": ("The approved-text assistant is disabled for this demo. "
                           "Enable it in Admin to ask SOP/policy questions."),
                "citations": [], "refused": True, "knowledge_base_version": kb_version,
                "case_scope_ref_id": case_scope_ref_id, "unit_scope_ref_id": unit_scope_ref_id,
                "latency_ms": 0}

    # Same case/unit scope + demo-role access checks as ordinary APIs, BEFORE retrieval.
    if case_scope_ref_id and role in CASE_READ_DENY:
        return {"enabled": True, "provider": _provider(),
                "answer": (f"The '{role}' role has aggregate-only access and cannot use a "
                           "case-scoped assistant context."),
                "citations": [], "refused": True, "knowledge_base_version": kb_version,
                "case_scope_ref_id": case_scope_ref_id, "unit_scope_ref_id": unit_scope_ref_id,
                "latency_ms": 0}

    t0 = time.time()
    provider = _provider()
    try:
        result = _query_quickml(question) if provider == "quickml" else knowledge.retrieve(question)
    except Exception:  # noqa: BLE001 — a provider failure degrades to a safe refusal
        result = {"answer": "The assistant is temporarily unavailable.", "citations": [],
                  "refused": True, "knowledge_base_version": kb_version}
    latency_ms = int((time.time() - t0) * 1000)

    _log_interaction(actor, role, question, result, case_scope_ref_id, unit_scope_ref_id, latency_ms)

    return {"enabled": True, "provider": provider, "answer": result["answer"],
            "citations": result.get("citations", []), "refused": bool(result.get("refused")),
            "knowledge_base_version": result.get("knowledge_base_version", kb_version),
            "case_scope_ref_id": case_scope_ref_id, "unit_scope_ref_id": unit_scope_ref_id,
            "latency_ms": latency_ms}


def evaluate() -> dict:
    """Run the fixed synthetic question/citation set and score citation/refusal."""
    items = []
    passed = 0
    for case in knowledge.EVAL_SET:
        result = knowledge.retrieve(case["question"])
        refused = bool(result["refused"])
        sources = [c["source"] for c in result["citations"]]
        if case["expect_answer"]:
            ok = (not refused) and (case["expect_source"] in sources)
        else:
            ok = refused
        passed += 1 if ok else 0
        items.append({"question": case["question"], "expect_answer": case["expect_answer"],
                      "expect_source": case["expect_source"], "refused": refused,
                      "citations": sources, "passed": ok})
    total = len(items)
    return {"total": total, "passed": passed, "failed": total - passed,
            "accuracy": round(passed / total, 3) if total else 0.0,
            "knowledge_base_version": knowledge.KNOWLEDGE_BASE_VERSION, "items": items}
