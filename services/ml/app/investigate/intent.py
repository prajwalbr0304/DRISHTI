"""Deterministic, bilingual (EN / Kannada / transliterated) case-scoped intent
classifier for the investigation assistant (Prompt 20 Part D).

This maps a natural-language case question to ONE of a small fixed set of
governed actions over the existing case APIs — it never generates free SQL and
is not a second chatbot. Free-form data questions are deferred to Prompt 19's
/chat engine (see service).
"""
from __future__ import annotations

# Intents -> which existing case capability the orchestrator composes.
SIMILAR = "similar_cases"        # "have similar cases happened before?" / MO
SUMMARY = "summary"              # cited case brief
LEADS = "leads"                  # ranked investigative suggestions
IDENTITY = "identity_links"      # reviewed canonical + candidate identity links
NETWORK = "network"             # case-centric relationship graph
TIMELINE = "timeline"            # lifecycle timeline
OVERVIEW = "overview"            # default: brief + top similar

INTENTS = (SIMILAR, SUMMARY, LEADS, IDENTITY, NETWORK, TIMELINE, OVERVIEW)

# (intent, [keywords]) — EN + transliterated-Kannada + Kannada-script cues.
_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    (SIMILAR, ("similar", "before", "prior", "happened before", "same pattern",
               "modus", "mo", "method", "serial", "repeat",
               "hinde", "hindina", "ide riti", "ಹಿಂದೆ", "ಇದೇ", "ಸದೃಶ", "ಕಾರ್ಯವಿಧಾನ", "ಮಾದರಿ")),
    (SUMMARY, ("summary", "summarise", "summarize", "brief", "overview of facts",
               "what happened", "saramsha", "ಸಾರಾಂಶ", "ಸಂಕ್ಷಿಪ್ತ")),
    (LEADS, ("lead", "leads", "next step", "what next", "do next", "suggest", "recommend",
             "munde", "mundina", "sulivu", "ಮುಂದಿನ", "ಸುಳಿವು", "ಶಿಫಾರಸು")),
    (IDENTITY, ("identity", "same person", "who is", "linked person", "aliases",
                "obbare", "vyakti", "ಒಬ್ಬರೇ", "ವ್ಯಕ್ತಿ", "ಗುರುತು")),
    (NETWORK, ("network", "connection", "connected", "related cases", "linked cases",
               "graph", "gang", "sampark", "jaala", "ಸಂಪರ್ಕ", "ಜಾಲ", "ಸಂಬಂಧ")),
    (TIMELINE, ("timeline", "sequence", "chronology", "when did", "order of events",
                "kaalanukrama", "samaya", "ಕಾಲಾನುಕ್ರಮ", "ಸಮಯ", "ಘಟನಾವಳಿ")),
]


def detect_language(text: str) -> str:
    """'kn' if any Kannada-script character is present, else 'en' (transliterated
    Kannada is treated as en-script but its keywords are recognised above)."""
    for ch in text or "":
        if "\u0c80" <= ch <= "\u0cff":
            return "kn"
    return "en"


def classify(question: str) -> str:
    """Return the best-matching case intent (OVERVIEW when nothing matches)."""
    q = (question or "").strip().lower()
    if not q:
        return OVERVIEW
    for intent, kws in _KEYWORDS:
        if any(kw in q for kw in kws):
            return intent
    return OVERVIEW
