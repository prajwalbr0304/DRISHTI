"""Catalyst Zia OCR adapter for the scanned-FIR intake lane.

Scope boundary (read this before extending the module)
------------------------------------------------------
This adapter exists for ONE purpose: reading a written/printed **FIR intake
form** so its fields can be proposed to an officer who must review them before
anything is submitted. That is intake-document prefill.

It is deliberately NOT evidence extraction. ``EVIDENCE_EXTRACTION_ENABLED``
stays false and continues to govern the ``/evidence`` custody path: files
uploaded as evidence are hashed and stored, never auto-parsed, never
transcribed, and never run through face/object recognition. The two paths are
separate flags for the same reason ``query_voice_enabled`` is separate from
``evidence_extraction_enabled`` — so enabling one can never silently enable the
other.

Why this is safe to enable
--------------------------
  * OCR output lands only in staging (``IntakeScan`` + ``IntakeDraft.Payload``).
  * A human must still approve the draft for a ``CaseMaster`` row to exist.
  * Every proposed field carries its own confidence and is recorded in
    ``IntakeScanField``, so machine-derived values stay distinguishable from
    typed ones for the life of the case.

Transport
---------
The documented Zia OCR endpoint is ``POST /baas/v1/project/{id}/ml/ocr``
(multipart, scope ``ZohoCatalyst.mlkit.READ``). We reach it through
``app.catalyst_rest`` rather than ``zcatalyst-sdk``: the SDK's base-URL
constants resolve to internal ``*.localzoho.com`` domains that do not exist in a
custom OCI AppSail, and its refresh-token path builds a double-slash URL that
404s (see the ``catalyst_rest`` module docstring for the full reasoning).

Honest limits of the upstream service
-------------------------------------
  * Zia returns plain text plus ONE document-level confidence score. It returns
    no per-field values and no bounding boxes, so any field-level confidence in
    DRISHTI is derived by ``app/intake/extract.py`` and is never presented as if
    it came from Zia.
  * Handwriting is supported by Zia only when the text is legible, clear and
    close to a standard character shape. Connected/cursive Kannada should be
    expected to degrade badly. The UI therefore always keeps the manual lane
    available and treats extraction as advisory.
  * Documented input limits: ``.webp/.jpeg/.png/.bmp/.tiff/.pdf``, 20 MB.

No credential is ever placed in the browser or written to a log.
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from .config import get_settings

# Verified capability evidence (official Catalyst docs, checked 2026-09-05).
_ZIA_OCR_EVIDENCE = (
    "Catalyst Zia OCR supports 9 international + 10 Indian languages including "
    "Kannada (code 'kan') and recognises handwritten content when the text is "
    "legible and close to a standard character shape: "
    "https://docs.catalyst.zoho.com/en/zia-services/help/optical-character-recognition/key-concepts/"
)

# Zia OCR language codes. DRISHTI speaks en/kn internally (see web/src/lib/lang.ts
# and nlsql.engine.detect_language); Zia wants ISO-639-2/B-style codes.
LANG_TO_ZIA: dict[str, str] = {"en": "eng", "kn": "kan"}
ZIA_TO_LANG: dict[str, str] = {"eng": "en", "kan": "kn"}

# Documented Zia OCR input contract (narrower than the evidence-upload allow-list
# on purpose — an OCR request must not be built for a file Zia cannot read).
ZIA_OCR_MAX_BYTES = 20 * 1024 * 1024          # 20 MB, per the API docs
ZIA_OCR_EXTENSIONS = ("webp", "jpeg", "jpg", "png", "bmp", "tiff", "tif", "pdf")
ZIA_OCR_MIME = (
    "image/webp", "image/jpeg", "image/png", "image/bmp",
    "image/tiff", "application/pdf",
)


class ZiaOcrError(RuntimeError):
    """Any OCR-layer failure. Never carries a credential or a raw response body."""


class ZiaOcrUnavailable(ZiaOcrError):
    """OCR is not configured/enabled — callers fall back to the manual lane."""


@dataclass(frozen=True)
class OcrResult:
    """One OCR run over one file.

    ``confidence`` is Zia's document-level score normalised to 0-1. It says how
    well the recogniser thinks it read the page — NOT how well the page mapped
    onto FIR fields. Field-level trust comes from the extractor.
    """
    text: str
    confidence: Optional[float] = None            # 0-1, document level
    detected_language: Optional[str] = None       # en|kn|mixed
    provider: str = ""
    requested_languages: tuple[str, ...] = field(default_factory=tuple)
    model_type: str = "OCR"

    @property
    def is_low_confidence(self) -> bool:
        threshold = get_settings().scan_ocr_low_confidence_threshold
        return self.confidence is not None and self.confidence < threshold


def detect_script(text: str) -> str:
    """Classify recognised text as ``en``, ``kn`` or ``mixed``.

    Mirrors ``web/src/lib/lang.ts`` and ``nlsql.engine.detect_language`` so the
    client, the query planner and the scan pipeline all agree on what script a
    piece of text is in.
    """
    if not text:
        return "en"
    has_kn = any("\u0c80" <= ch <= "\u0cff" for ch in text)
    has_latin = any(("a" <= ch <= "z") or ("A" <= ch <= "Z") for ch in text)
    if has_kn and has_latin:
        return "mixed"
    if has_kn:
        return "kn"
    return "en"


def validate_ocr_input(*, size_bytes: Optional[int], filename: str = "",
                       mime_type: str = "") -> None:
    """Reject a file Zia cannot process, before spending a network call on it.

    Raises ``ZiaOcrError`` with an operator-readable reason.
    """
    if size_bytes is not None and size_bytes > ZIA_OCR_MAX_BYTES:
        mb = ZIA_OCR_MAX_BYTES // (1024 * 1024)
        raise ZiaOcrError(
            f"Scan is larger than the {mb} MB Zia OCR limit. "
            "Re-scan at a lower resolution or split the pages.")
    if size_bytes is not None and size_bytes <= 0:
        raise ZiaOcrError("Scan is empty.")

    ext = (filename or "").rsplit(".", 1)[-1].strip().lower() if "." in (filename or "") else ""
    mime = (mime_type or "").split(";")[0].strip().lower()
    # Accept when EITHER signal is recognised: browsers occasionally send a blank
    # or generic MIME for a camera capture, and a correct extension is enough.
    if ext and ext in ZIA_OCR_EXTENSIONS:
        return
    if mime and mime in ZIA_OCR_MIME:
        return
    raise ZiaOcrError(
        "Unsupported scan format. Zia OCR reads "
        + ", ".join(sorted({"webp", "jpeg", "png", "bmp", "tiff", "pdf"}))
        + f" files (received '{ext or mime or 'unknown'}').")


class ZiaOcr(ABC):
    """Narrow server-side OCR boundary (deferred client construction)."""

    provider: str = ""
    available: bool = False

    @abstractmethod
    def recognize(self, content: bytes, *, filename: str = "",
                  content_type: str = "", languages: Optional[list[str]] = None,
                  model_type: str = "OCR") -> OcrResult: ...


class UnavailableZiaOcr(ZiaOcr):
    """Default adapter: OCR is off unless an operator explicitly enables it.

    Fail-closed and honest — it never fabricates text. The intake UI keeps the
    manual lane fully functional, so a disabled OCR path costs a convenience,
    not a capability.
    """

    provider = "unavailable"
    available = False

    def recognize(self, content: bytes, *, filename: str = "",
                  content_type: str = "", languages: Optional[list[str]] = None,
                  model_type: str = "OCR") -> OcrResult:
        raise ZiaOcrUnavailable(
            "Scanned-FIR OCR is not enabled on this server. Enter the FIR "
            "manually, or ask an operator to enable the Catalyst Zia OCR path.")


class CatalystZiaOcr(ZiaOcr):
    """Live adapter over the documented Catalyst Zia OCR REST endpoint."""

    provider = "catalyst-zia-ocr"
    available = True

    def __init__(self, client=None):
        # Deferred: importing this module must never require Catalyst config.
        from .catalyst_rest import get_rest_client
        self._client = client or get_rest_client()

    def recognize(self, content: bytes, *, filename: str = "",
                  content_type: str = "", languages: Optional[list[str]] = None,
                  model_type: str = "OCR") -> OcrResult:
        if not content:
            raise ZiaOcrError("Scan is empty.")
        validate_ocr_input(size_bytes=len(content), filename=filename,
                           mime_type=content_type)

        zia_langs = _zia_language_codes(languages)
        try:
            data = self._client.zia_ocr(
                content,
                filename=filename or "scan.jpg",
                content_type=(content_type or "application/octet-stream").split(";")[0],
                languages=zia_langs or None,
                model_type=model_type or "OCR")
        except Exception as exc:  # noqa: BLE001
            # Surface the failure type, never the response body (it can echo the
            # request and we do not want scan content in a log line).
            raise ZiaOcrError(f"Zia OCR call failed: {type(exc).__name__}") from exc

        text = str(data.get("text") or "")
        raw_conf = data.get("confidence")
        confidence: Optional[float] = None
        if raw_conf is not None:
            try:
                # Zia reports 0-100; normalise to 0-1 for the rest of the app.
                confidence = max(0.0, min(1.0, float(raw_conf) / 100.0))
            except (TypeError, ValueError):
                confidence = None

        return OcrResult(
            text=text,
            confidence=confidence,
            detected_language=detect_script(text),
            provider=self.provider,
            requested_languages=tuple(zia_langs),
            model_type=model_type or "OCR",
        )


def _zia_language_codes(languages: Optional[list[str]]) -> list[str]:
    """Map DRISHTI/ISO language hints onto Zia codes, de-duplicated + ordered.

    Unknown codes are dropped rather than forwarded: a bad ``language`` value
    makes Zia reject the whole request, and auto-detection is a better outcome
    than a hard failure.
    """
    out: list[str] = []
    for raw in languages or []:
        code = str(raw or "").strip().lower()
        if not code:
            continue
        zia = LANG_TO_ZIA.get(code, code if code in ZIA_TO_LANG else "")
        if zia and zia not in out:
            out.append(zia)
    return out


def scan_ocr_enabled() -> bool:
    """True only when BOTH the feature flag and the Catalyst adapter are on.

    Two gates on purpose: ``intake_scan_ocr_enabled`` is the product decision
    (does this deployment offer the scanned lane at all), and
    ``DRISHTI_USE_CATALYST_ZIA_OCR`` is the infrastructure decision (is a real
    Zia-enabled project wired up). Either one off means the manual lane only.
    """
    if not get_settings().intake_scan_ocr_enabled:
        return False
    return os.getenv("DRISHTI_USE_CATALYST_ZIA_OCR", "").strip().lower() == "true"


def get_zia_ocr() -> ZiaOcr:
    """Factory: the live Zia adapter only when explicitly enabled, else the
    honest unavailable adapter (the default)."""
    if scan_ocr_enabled():
        return CatalystZiaOcr()
    return UnavailableZiaOcr()


def default_languages() -> list[str]:
    """Language hints sent with every scan unless the caller overrides them.

    Karnataka FIRs are routinely bilingual — a Kannada narrative with English
    section numbers and dates — so both scripts are hinted by default.
    """
    raw = (get_settings().scan_ocr_languages or "").strip()
    codes = [c.strip().lower() for c in raw.split(",") if c.strip()] if raw else ["en", "kn"]
    return codes


def ocr_capability_status() -> dict:
    """The truthful scan capability the SPA reads, so the UI can label the
    feature accurately and never imply extraction it is not doing."""
    s = get_settings()
    enabled = scan_ocr_enabled()
    mb = ZIA_OCR_MAX_BYTES // (1024 * 1024)
    return {
        "scan_ocr_enabled": enabled,
        "feature_enabled": bool(s.intake_scan_ocr_enabled),
        "provider": "catalyst-zia-ocr" if enabled else "unavailable",
        "manual_entry_always_available": True,
        "languages": default_languages(),
        "supported_languages": sorted(LANG_TO_ZIA.keys()),
        "max_bytes": ZIA_OCR_MAX_BYTES,
        "max_mb": mb,
        "allowed_extensions": sorted(set(ZIA_OCR_EXTENSIONS)),
        "low_confidence_threshold": float(s.scan_ocr_low_confidence_threshold),
        "auto_fill_threshold": float(s.scan_ocr_auto_fill_threshold),
        # Human review is structural here, not a policy toggle: OCR only writes
        # staging, and CaseMaster is created solely by the approve transition.
        "requires_human_review": True,
        "creates_case_directly": False,
        # Strictly separate from intake prefill: evidence media stays unparsed.
        "evidence_extraction_enabled": bool(s.evidence_extraction_enabled),
        "handwriting_supported": True,
        "handwriting_caveat": (
            "Zia recognises handwriting only when the text is legible, clear and "
            "close to a standard character shape. Connected or cursive Kannada "
            "will often fail — review every field, and use manual entry when the "
            "page is untidy."),
        "evidence": _ZIA_OCR_EVIDENCE,
        "platform_limitation": None if enabled else (
            "Catalyst Zia OCR is not enabled on this server "
            "(INTAKE_SCAN_OCR_ENABLED + DRISHTI_USE_CATALYST_ZIA_OCR). "
            "FIRs are entered manually."),
    }
