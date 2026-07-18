"""Catalyst QuickML contract — approved-text RAG + no-code baseline (rows 11/12).

QuickML is preferred for RAG in the India DC (workflow §10). The knowledge base
is built ONLY from approved SOP/policy text (curated source + version); uploaded
evidence bytes and unreviewed case narratives are excluded. Answers must carry
citations and refuse when unsupported. QuickML also hosts an eligible no-code
baseline experiment (row 12) as the tabular-training path where Zia AutoML is
unavailable in the IN DC.

This module is the deployed RAG boundary: an offline deterministic fake (fixed
citation/refusal behaviour, used by tests + when the assistant is disabled) and a
Catalyst-SDK-backed implementation. It is DISABLED until
`DRISHTI_QUICKML_RAG_ENABLED=true`. KB sources + the experiment live in
`infra/catalyst/quickml/`.
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True)
class RagAnswer:
    answer: str
    citations: list[str] = field(default_factory=list)  # approved-source refs only
    refused: bool = False
    knowledge_base_version: str = ""

    def as_dict(self) -> dict:
        return {"answer": self.answer, "citations": self.citations,
                "refused": self.refused, "knowledge_base_version": self.knowledge_base_version}


class QuickMLRag(ABC):
    @abstractmethod
    def query(self, question: str, *, top_k: int = 4) -> RagAnswer: ...

    @abstractmethod
    def knowledge_base_version(self) -> str: ...


class OfflineRag(QuickMLRag):
    """Deterministic fake. REFUSES unless the KB is explicitly loaded, so a
    disabled assistant can never fabricate an answer (fixed refusal contract)."""

    def __init__(self, kb: dict[str, str] | None = None, version: str = "offline-empty"):
        self._kb = kb or {}
        self._version = version

    def query(self, question, *, top_k=4):
        q = (question or "").lower().strip()
        hits = [src for key, src in self._kb.items() if key.lower() in q or q in key.lower()]
        if not hits:
            return RagAnswer(
                answer="I don't have an approved SOP/policy source that answers this. "
                       "(No fabricated guidance.)",
                citations=[], refused=True, knowledge_base_version=self._version)
        return RagAnswer(answer=f"Per approved SOP: {hits[0]}", citations=hits[:top_k],
                         refused=False, knowledge_base_version=self._version)

    def knowledge_base_version(self):
        return self._version


class CatalystQuickMLRag(QuickMLRag):
    """Deployed impl over the Catalyst SDK (QuickML endpoint). SDK import deferred."""

    def __init__(self, app=None):
        import zcatalyst_sdk
        self._app = app or zcatalyst_sdk.initialize()
        self._endpoint = os.getenv("DRISHTI_QUICKML_RAG_ENDPOINT", "")
        self._version = os.getenv("DRISHTI_QUICKML_KB_VERSION", "unset")

    def query(self, question, *, top_k=4):
        # The QuickML RAG endpoint returns {answer, citations, refused}.
        ml = self._app.quickml() if hasattr(self._app, "quickml") else None
        if ml is None or not self._endpoint:
            return RagAnswer(answer="RAG endpoint not configured.", refused=True,
                             knowledge_base_version=self._version)
        res = ml.rag_query(endpoint=self._endpoint, question=question, top_k=top_k)
        return RagAnswer(answer=res.get("answer", ""), citations=res.get("citations", []),
                         refused=bool(res.get("refused", False)),
                         knowledge_base_version=self._version)

    def knowledge_base_version(self):
        return self._version


def rag_enabled() -> bool:
    return os.getenv("DRISHTI_QUICKML_RAG_ENABLED", "").lower() == "true"


def get_rag() -> QuickMLRag:
    """Factory: Catalyst QuickML RAG when enabled+configured, else the offline
    (refusing) fake so the approved-text assistant is cost-free and safe by
    default."""
    if rag_enabled() and os.getenv("DRISHTI_USE_CATALYST_QUICKML", "").lower() == "true":
        return CatalystQuickMLRag()
    return OfflineRag()
