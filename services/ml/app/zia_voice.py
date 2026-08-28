"""Catalyst Zia voice/translation adapter + honest capability status (Prompt 19 §E).

Voice DICTATION of a question and spoken read-back are in hackathon scope. The
organizer preference is to use Catalyst **Zia** speech/translation services when
they are available for the India-DC project. They are NOT: the documented Catalyst
Zia service catalogue exposes OCR, Face Analytics, Identity Scanner, Image
Moderation, Object Recognition, Barcode Scanner, AutoML and Text Analytics — there
is no speech-to-text, text-to-speech or translation Zia service in the IN DC
(capability evidence recorded below and in the Phase 19 report). Most of that
catalogue (OCR/face/object) is also explicitly OUT of DRISHTI scope.

So per §E.5 the submitted voice capability is the browser Web Speech API, clearly
LABELLED as browser-based (never as Zia), feature-detected, with fully working
bilingual English/Kannada TEXT retained when it is absent. This module is the
server-side boundary that:
  * reports the truthful capability (`voice_capability_status`) the SPA reads so
    it labels the mic honestly and never claims Zia;
  * carries a ready, env-gated Catalyst Zia adapter contract (`CatalystZiaVoice`)
    so that IF Zia speech/translation is later exposed in the IN DC, it drops in
    behind the SAME interface without touching the browser or leaking a credential.

No service credential is ever placed in React or logged. This module performs NO
OCR, document parsing, evidence-media transcription or field extraction.
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from .config import get_settings

# Verified capability evidence (official Catalyst docs, checked 2026-07-21).
# The Zia services list contains no speech/translation component.
_ZIA_CATALOG_EVIDENCE = (
    "Catalyst Zia Services catalogue (OCR, Face Analytics, Identity Scanner, Image "
    "Moderation, Object Recognition, Barcode Scanner, AutoML, Text Analytics) lists "
    "no speech-to-text/text-to-speech/translation component: "
    "https://docs.catalyst.zoho.com/en/zia-services/getting-started/components-of-zia-services/"
)


@dataclass(frozen=True)
class VoiceResult:
    transcript: str
    language: str
    confidence: Optional[float] = None
    provider: str = ""
    is_low_confidence: bool = False


class ZiaVoice(ABC):
    """Narrow server-side speech/translation boundary (deferred SDK import)."""

    provider: str = ""
    available: bool = False

    @abstractmethod
    def transcribe(self, audio_ref: str, *, language: str) -> VoiceResult: ...

    @abstractmethod
    def synthesize(self, text: str, *, language: str) -> bytes: ...

    @abstractmethod
    def translate(self, text: str, *, target: str) -> Optional[str]: ...


class UnavailableZiaVoice(ZiaVoice):
    """Default adapter: Catalyst Zia speech/translation is not offered in the IN
    DC, so every server-side voice op is unavailable (never faked). The SPA uses
    the labelled browser Web Speech fallback; bilingual text always works."""

    provider = "unavailable"
    available = False

    def transcribe(self, audio_ref: str, *, language: str) -> VoiceResult:
        raise RuntimeError("Catalyst Zia speech-to-text is not available in the IN DC.")

    def synthesize(self, text: str, *, language: str) -> bytes:
        raise RuntimeError("Catalyst Zia text-to-speech is not available in the IN DC.")

    def translate(self, text: str, *, target: str) -> Optional[str]:
        return None      # no fabricated translation


class CatalystZiaVoice(ZiaVoice):
    """Deployed adapter over the Catalyst Zia SDK — used ONLY if Zia speech/
    translation is actually exposed for the project (env-gated). SDK import is
    deferred so importing this module never requires the SDK. The concrete method
    mapping is verified live in Prompt 23 before this path is enabled."""

    provider = "catalyst-zia"
    available = True

    def __init__(self, app=None):
        import zcatalyst_sdk  # only present in the AppSail image
        self._app = app or zcatalyst_sdk.initialize()
        self._zia = self._app.zia()

    def transcribe(self, audio_ref: str, *, language: str) -> VoiceResult:
        raise NotImplementedError("Enable + verify against the live Zia deployment in Prompt 23.")

    def synthesize(self, text: str, *, language: str) -> bytes:
        raise NotImplementedError("Enable + verify against the live Zia deployment in Prompt 23.")

    def translate(self, text: str, *, target: str) -> Optional[str]:
        raise NotImplementedError("Enable + verify against the live Zia deployment in Prompt 23.")


def zia_voice_enabled() -> bool:
    """Operators only set this after verifying Zia speech is exposed for the project."""
    return os.getenv("DRISHTI_USE_CATALYST_ZIA_VOICE", "").lower() == "true"


def get_zia_voice() -> ZiaVoice:
    """Factory: the Catalyst Zia adapter only when explicitly enabled + verified,
    else the honest unavailable adapter (the default for this submission)."""
    if zia_voice_enabled():
        return CatalystZiaVoice()
    return UnavailableZiaVoice()


def voice_capability_status() -> dict:
    """The truthful voice capability the SPA reads to label the mic honestly.

    `provider` is the browser Web Speech API in this submission — never Zia. When
    Zia speech is unavailable (the case here) the SPA keeps full bilingual text and
    a labelled, feature-detected browser-voice fallback."""
    s = get_settings()
    zia_on = zia_voice_enabled()
    return {
        "voice_query_enabled": bool(s.query_voice_enabled),
        # The submitted STT/TTS provider. Browser recognition is NEVER called Zia.
        "provider": "catalyst-zia" if zia_on else "browser-web-speech",
        # The shipped continuous Voice Mode loops browser STT -> guarded Ask ->
        # browser TTS over ordinary HTTPS. It is not a server audio stream.
        "mode": "server-streaming" if zia_on else "browser-continuous-turns",
        "continuous_mode_available": bool(s.query_voice_enabled),
        "server_audio_streaming": bool(zia_on),
        "zia_voice_available": zia_on,
        "zia_translation_available": zia_on,
        "browser_fallback": True,
        "bilingual_text": True,          # EN/KN text always works, voice or not
        "low_confidence_threshold": float(s.voice_low_confidence_threshold),
        # Strictly separate from voice: evidence extraction stays OFF (Prompt 19 §A).
        "evidence_extraction_enabled": bool(s.evidence_extraction_enabled),
        "platform_limitation": None if zia_on else (
            "Catalyst Zia does not expose speech-to-text/text-to-speech/translation "
            "in the India DC; voice uses the browser Web Speech API (labelled), and "
            "bilingual English/Kannada text is fully supported."),
        "evidence": None if zia_on else _ZIA_CATALOG_EVIDENCE,
    }
