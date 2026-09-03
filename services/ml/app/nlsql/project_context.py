"""Small, auditable knowledge layer for questions about DRISHTI itself."""
from __future__ import annotations

import re

_PROJECT = re.compile(
    r"\b(drishti|dashboard|this project|this system|architecture|tech stack|"
    r"data source|real.?time data|synthetic data|privacy|security|language support|"
    r"voice mode|model|llm|what can (?:you|it) do|capabilit(?:y|ies))\b",
    re.IGNORECASE,
)
_DATABASE_TASK = re.compile(
    r"\b(how many|count|list|show|top|trend|forecast|case|fir|crime|district|station|"
    r"accused|victim|arrest|chargesheet|hotspot|pattern)\b",
    re.IGNORECASE,
)
_EXPLICIT_CONTEXT = re.compile(
    r"\b(architecture|tech stack|data source|"
    r"real.?time data|synthetic data|privacy|security|language support|voice mode|"
    r"what can (?:you|it) do|capabilit(?:y|ies))\b",
    re.IGNORECASE,
)


def is_project_context_request(question: str) -> bool:
    text = (question or "").strip()
    if not _PROJECT.search(text):
        return False
    # Explicit questions about the system remain contextual even when they say
    # "crime data". Dashboard questions that request an actual count/list still
    # go through the database path.
    return bool(_EXPLICIT_CONTEXT.search(text)) or not bool(_DATABASE_TASK.search(text))


def answer(question: str) -> str:
    q = (question or "").lower()
    parts: list[str] = []
    if re.search(r"real.?time|data source|synthetic", q):
        parts.append(
            "DRISHTI queries its connected PostgreSQL database at request time, but this "
            "deployment is populated with synthetic demonstration data. It is not a live "
            "Karnataka Police operational feed. Results are current for the connected demo "
            "database only; production freshness would depend on authenticated source-system "
            "integrations, ingestion monitoring, and data-quality controls."
        )
    if re.search(r"privacy|security|role|permission|audit", q):
        parts.append(
            "DRISHTI binds conversations to the authenticated owner and role, permits only "
            "guarded read-only SELECT queries, applies server-side scope checks and row caps, "
            "and records model/query provenance. Voice audio is streamed to Amazon Bedrock "
            "with explicit consent and is not stored by DRISHTI; transcripts and grounded "
            "answers are retained in chat history. Demo access and synthetic data are not a "
            "substitute for production identity, retention, and police-data governance."
        )
    if re.search(r"architecture|tech stack|model|llm", q):
        parts.append(
            "DRISHTI uses a React/Vite dashboard, a FastAPI service, and PostgreSQL. Ask "
            "DRISHTI uses an AWS Bedrock GLM semantic planner to propose SQL, followed by "
            "server-enforced schema, read-only, scope, timeout, and result-size guards. Amazon "
            "Nova 2 Sonic provides optional English speech through an AgentCore relay; Kannada "
            "uses browser speech. Deterministic analytics services handle governed workloads "
            "such as briefings and socio-economic correlations."
        )
    if re.search(r"voice|language|kannada|english", q):
        parts.append(
            "The interface and text assistant support English and Kannada. English continuous "
            "speech can use Amazon Nova 2 Sonic with six selectable voices; browser speech is "
            "the fallback and handles Kannada. Grounded answer cards remain separate from the "
            "spoken summary, and raw microphone audio is not stored by DRISHTI."
        )
    if parts:
        return "\n\n".join(parts)
    return (
        "DRISHTI is a decision-intelligence dashboard for synthetic public-safety workflows. "
        "It covers cases and intake, people/entities, networks, investigation boards, maps and "
        "hotspots, analytics/forecasting, emergency response, administration, and a cited "
        "conversational assistant. Database answers are generated through guarded read-only "
        "queries; specialized analytics use governed server-side services. It supports decision "
        "support, not autonomous policing, and this deployment is not a live police data feed."
    )
