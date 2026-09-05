"""Parse Catalyst Zia OCR text into a DraftPayload-shaped PROPOSAL.

This is stage two of the scanned-FIR lane. Stage one (``app/zia_ocr.py``) turns a
photographed/scanned page into plain text plus one document-level confidence
score. Zia returns no per-field values and no bounding boxes, so everything
field-level in DRISHTI is derived here — and is labelled as derived, never
presented as if the recogniser asserted it.

Approach: anchored template parsing, not free-text interpretation
----------------------------------------------------------------
DRISHTI publishes a fixed intake form (``FIR_TEMPLATE_V1``). ``template_spec()``
serves that same tuple to the SPA so the printable form and the parser can never
drift apart. Each line carries a bilingual label and one value, so parsing reduces
to: find the label, take the value after the separator, coerce it to the right
type. That is deterministic and auditable — a reviewer can see exactly which text
span produced which field.

Two properties make this survive real OCR output:
  * label matching is fuzzy, because OCR mangles labels ("Police Statlon");
  * a field is only pre-filled when its derived confidence clears
    ``scan_ocr_auto_fill_threshold``. Anything lower is returned as a suggestion
    the officer must accept, so the form is never quietly populated with a guess.

Deliberately NOT done here
--------------------------
No LLM is involved. A model could read messier pages, but it cannot show a
reviewer which characters produced a field, and a wrong police station or wrong
section on a registered FIR is a real-world harm. Deterministic parsing plus an
explicit "couldn't read this" is the safer trade for a police workflow. Free-text
narrative is the one place OCR error is cheap, because an officer reads it anyway.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Optional

from ..config import get_settings

TEMPLATE_CODE = "DRISHTI-FIR-V1"

# --- Kannada numerals -------------------------------------------------------
# A Kannada-language form is routinely filled with Kannada digits, which every
# downstream date/number parser would otherwise reject.
_KANNADA_DIGITS = str.maketrans("\u0ce6\u0ce7\u0ce8\u0ce9\u0cea\u0ceb\u0cec\u0ced\u0cee\u0cef",
                                "0123456789")

# OCR routinely confuses these inside an otherwise-numeric run.
_DIGIT_LOOKALIKES = {"O": "0", "o": "0", "l": "1", "I": "1", "|": "1",
                     "S": "5", "B": "8"}

# Label/value separators used on the printed form (ASCII + Devanagari danda +
# fullwidth colon, all of which show up in OCR output).
_SEPARATORS = (":", "\uff1a", "-", "\u2013", "\u2014", "=")

_LABEL_MATCH_MIN = 0.72        # fuzzy ratio floor for a Latin label
_LABEL_MATCH_MIN_KN = 0.80     # stricter for Kannada (fuzzy is less reliable)


# ---------------------------------------------------------------------------
# Field specification
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class FieldSpec:
    """One line on the printed form and where its value lands in DraftPayload."""
    path: str                                  # dotted DraftPayload path
    kind: str                                  # text|date|datetime|time|int|phone|sections|lookup_*
    labels_en: tuple[str, ...]
    labels_kn: tuple[str, ...] = field(default_factory=tuple)
    multiline: bool = False                    # value continues on following lines
    lookup: str = ""                           # reference table for lookup_* kinds
    party_role: str = ""                       # routes the value to a proposed party
    party_attr: str = ""                       # which party attribute this fills
    help_en: str = ""


# The printed DRISHTI intake form, in order. Keeping this as data (not code)
# means the print template, the parser and the API contract cannot drift.
FIR_TEMPLATE_V1: tuple[FieldSpec, ...] = (
    FieldSpec("registration.station_id", "lookup_unit",
              ("Police Station", "PS", "Station"),
              ("\u0caa\u0cca\u0cb2\u0cbf\u0cb8\u0ccd \u0ca0\u0cbe\u0ca3\u0cc6",),
              lookup="unit",
              help_en="Registering police station."),
    FieldSpec("registration.district_id", "lookup_district",
              ("District",),
              ("\u0c9c\u0cbf\u0cb2\u0ccd\u0cb2\u0cc6",),
              lookup="district",
              help_en="District; derived from the station when left blank."),
    FieldSpec("source.external_source_id", "text",
              ("FIR No", "FIR Number", "Crime No", "Reference No"),
              ("\u0c8e\u0cab\u0ccd\u200c\u0c90\u0c86\u0cb0\u0ccd \u0cb8\u0c82\u0c96\u0ccd\u0caf\u0cc6",),
              help_en="Source reference; a new number is issued on approval."),
    FieldSpec("registration.registration_date", "date",
              ("Date of Registration", "Registration Date", "Date"),
              ("\u0ca6\u0cbf\u0ca8\u0cbe\u0c82\u0c95",),
              help_en="Date the report was registered."),
    FieldSpec("registration.registration_time", "time",
              ("Time of Registration", "Registration Time", "Time"),
              ("\u0cb8\u0cae\u0caf",),
              help_en="Time the report was registered."),
    FieldSpec("__case_kind", "case_kind",
              ("Case Type", "Report Type", "Type of Case"),
              ("\u0caa\u0ccd\u0cb0\u0c95\u0cb0\u0ca3\u0ca6 \u0caa\u0ccd\u0cb0\u0c95\u0cbe\u0cb0",),
              help_en="Standard FIR / Zero FIR / NCR / UDR / PAR / Missing person."),
    FieldSpec("classification.acts_sections", "sections",
              ("Acts and Sections", "Acts & Sections", "Sections", "Under Section", "u/s"),
              ("\u0c95\u0cb2\u0c82",),
              help_en="e.g. IPC 379, 411 or BNS 303(2)."),
    FieldSpec("incident.incident_from", "datetime",
              ("Occurrence From", "Date of Occurrence From", "Occurrence Start"),
              ("\u0c98\u0c9f\u0ca8\u0cc6 \u0c86\u0cb0\u0c82\u0cad",),
              help_en="When the incident began."),
    FieldSpec("incident.incident_to", "datetime",
              ("Occurrence To", "Date of Occurrence To", "Occurrence End"),
              ("\u0c98\u0c9f\u0ca8\u0cc6 \u0c85\u0c82\u0ca4\u0ccd\u0caf",),
              help_en="When the incident ended."),
    FieldSpec("incident.info_received_at", "datetime",
              ("Information Received", "Info Received", "Received At"),
              ("\u0cae\u0cbe\u0cb9\u0cbf\u0ca4\u0cbf \u0cb8\u0ccd\u0cb5\u0cc0\u0c95\u0cc3\u0ca4",),
              help_en="When the information reached the police."),
    FieldSpec("incident.address", "text",
              ("Place of Occurrence", "Place", "Scene of Crime", "Address"),
              ("\u0cb8\u0ccd\u0ca5\u0cb3",),
              multiline=True,
              help_en="Where the incident happened."),
    FieldSpec("incident.landmark", "text",
              ("Landmark", "Nearest Landmark"),
              ("\u0c97\u0cc1\u0cb0\u0cc1\u0ca4\u0cc1",),
              help_en="Nearby reference point."),
    FieldSpec("incident.beat", "text",
              ("Beat", "Beat Area"),
              ("\u0cac\u0cc0\u0c9f\u0ccd",)),
    FieldSpec("__complainant_name", "text",
              ("Complainant Name", "Name of Complainant", "Complainant"),
              ("\u0ca6\u0cc2\u0cb0\u0cc1\u0ca6\u0cbe\u0cb0\u0cb0 \u0cb9\u0cc6\u0cb8\u0cb0\u0cc1",),
              party_role="complainant", party_attr="display_name",
              help_en="Who reported it."),
    FieldSpec("__complainant_age", "int",
              ("Complainant Age", "Age of Complainant", "Age"),
              ("\u0cb5\u0caf\u0cb8\u0ccd\u0cb8\u0cc1",),
              party_role="complainant", party_attr="age"),
    FieldSpec("__complainant_phone", "phone",
              ("Complainant Phone", "Phone", "Mobile", "Contact No"),
              ("\u0ca6\u0cc2\u0cb0\u0cb5\u0cbe\u0ca3\u0cbf",),
              party_role="complainant", party_attr="phone"),
    FieldSpec("__complainant_address", "text",
              ("Complainant Address", "Address of Complainant"),
              ("\u0ca6\u0cc2\u0cb0\u0cc1\u0ca6\u0cbe\u0cb0\u0cb0 \u0cb5\u0cbf\u0cb3\u0cbe\u0cb8",),
              multiline=True,
              party_role="complainant", party_attr="address"),
    FieldSpec("__victim_name", "text",
              ("Victim Name", "Name of Victim", "Victim"),
              ("\u0cb8\u0c82\u0ca4\u0ccd\u0cb0\u0cb8\u0ccd\u0ca4\u0cb0 \u0cb9\u0cc6\u0cb8\u0cb0\u0cc1",),
              party_role="victim", party_attr="display_name"),
    FieldSpec("__accused_name", "text",
              ("Accused Name", "Name of Accused", "Accused", "Suspect"),
              ("\u0c86\u0cb0\u0ccb\u0caa\u0cbf \u0cb9\u0cc6\u0cb8\u0cb0\u0cc1",),
              party_role="accused", party_attr="display_name"),
    FieldSpec("__witness_name", "text",
              ("Witness Name", "Witness"),
              ("\u0cb8\u0cbe\u0c95\u0ccd\u0cb7\u0cbf",),
              party_role="witness", party_attr="display_name"),
    FieldSpec("narrative.brief_facts", "text",
              ("Brief Facts", "Brief Facts of the Case", "Complaint", "Details",
               "Statement", "Facts"),
              ("\u0cb8\u0c82\u0c95\u0ccd\u0cb7\u0cbf\u0caa\u0ccd\u0ca4 \u0cb5\u0cbf\u0cb5\u0cb0",),
              multiline=True,
              help_en="What happened, in the complainant's words."),
    FieldSpec("registration.registering_officer_id", "lookup_officer",
              ("Registering Officer", "Officer", "SHO", "Recorded By"),
              ("\u0c85\u0ca7\u0cbf\u0c95\u0cbe\u0cb0\u0cbf",),
              lookup="officer"),
)

# Fields whose values feed a proposed party rather than DraftPayload directly.
_PARTY_SPECS = tuple(s for s in FIR_TEMPLATE_V1 if s.party_role)

# Case-kind vocabulary as it appears on a filled form, EN + KN.
_CASE_KIND_WORDS: dict[str, tuple[str, ...]] = {
    "fir_standard": ("standard fir", "fir", "cognizable", "regular fir"),
    "zero_fir": ("zero fir", "zero"),
    "ncr": ("ncr", "non cognizable", "non-cognizable", "noncognizable"),
    "udr": ("udr", "unnatural death", "unnatural death report"),
    "par": ("par", "preventive action", "preventive action report"),
    "missing_person": ("missing person", "missing", "man missing", "woman missing"),
}
_CASE_KIND_WORDS_KN: dict[str, tuple[str, ...]] = {
    "zero_fir": ("\u0cb6\u0cc2\u0ca8\u0ccd\u0caf",),
    "missing_person": ("\u0c95\u0cbe\u0ca3\u0cc6",),
    "udr": ("\u0c85\u0cb8\u0cb9\u0c9c \u0cae\u0cb0\u0ca3",),
}

# Known act tokens on a Karnataka FIR. Order matters: longest first so "BNSS"
# is not swallowed by "BNS".
_ACT_TOKENS: tuple[tuple[str, str], ...] = (
    ("BNSS", "BNSS"), ("BNS", "BNS"), ("CRPC", "CrPC"), ("CR.P.C", "CrPC"),
    ("IPC", "IPC"), ("I.P.C", "IPC"), ("POCSO", "POCSO"), ("NDPS", "NDPS"),
    ("ARMS ACT", "Arms Act"), ("ARMS", "Arms Act"),
    ("MV ACT", "MV Act"), ("M.V. ACT", "MV Act"), ("MOTOR VEHICLE", "MV Act"),
    ("IT ACT", "IT Act"), ("I.T. ACT", "IT Act"),
    ("KP ACT", "KP Act"), ("KARNATAKA POLICE", "KP Act"),
    ("SC/ST", "SC ST Act"), ("SCST", "SC ST Act"),
    ("DOWRY", "Dowry Act"), ("JJ ACT", "JJ Act"),
)


# ---------------------------------------------------------------------------
# Result objects
# ---------------------------------------------------------------------------
@dataclass
class ExtractedField:
    """One field the parser proposes, with everything a reviewer needs."""
    path: str
    value: Any = None
    raw_text: str = ""                  # the span OCR produced
    confidence: float = 0.0             # derived 0-1, never Zia's own number
    label_matched: str = ""
    requires_review: bool = False       # below auto-fill threshold
    auto_filled: bool = False           # actually written into the payload
    note: str = ""

    def as_dict(self) -> dict:
        return {
            "field": self.path, "value": self.value, "raw_text": self.raw_text,
            "confidence": round(self.confidence, 4),
            "label_matched": self.label_matched,
            "requires_review": self.requires_review,
            "auto_filled": self.auto_filled,
            "note": self.note or None,
        }


@dataclass
class UnresolvedLookup:
    """A reference value the parser read but refused to resolve on its own."""
    path: str
    raw_text: str
    lookup: str
    candidates: list[dict] = field(default_factory=list)
    reason: str = ""

    def as_dict(self) -> dict:
        return {"field": self.path, "raw_text": self.raw_text, "lookup": self.lookup,
                "candidates": self.candidates, "reason": self.reason}


@dataclass
class ExtractionResult:
    payload: dict = field(default_factory=dict)
    case_kind: Optional[str] = None
    fields: list[ExtractedField] = field(default_factory=list)
    parties: list[dict] = field(default_factory=list)
    unresolved: list[UnresolvedLookup] = field(default_factory=list)
    # Reference text read for lookup fields, keyed by payload path. Kept OUT of
    # ``payload`` so the payload always validates against DraftPayload; resolve.py
    # turns these into real ids (or leaves them unresolved for the officer).
    lookup_texts: dict[str, str] = field(default_factory=dict)
    template_code: str = TEMPLATE_CODE
    template_matched: bool = False
    matched_label_count: int = 0
    language: str = "en"
    notes: list[str] = field(default_factory=list)

    @property
    def field_confidence(self) -> dict[str, float]:
        return {f.path: round(f.confidence, 4) for f in self.fields}

    @property
    def fields_needing_review(self) -> int:
        return sum(1 for f in self.fields if f.requires_review)


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------
def normalize_digits(text: str) -> str:
    """Kannada numerals -> ASCII, so shared numeric parsers work on both forms."""
    return (text or "").translate(_KANNADA_DIGITS)


def _fix_digit_lookalikes(token: str) -> str:
    """Repair OCR letter/digit confusion inside an otherwise-numeric token."""
    if not token:
        return token
    digits = sum(1 for c in token if c.isdigit())
    # Only intervene when the token is clearly meant to be numeric.
    if digits and digits >= len(token) - 2:
        return "".join(_DIGIT_LOOKALIKES.get(c, c) for c in token)
    return token


def _norm_label(text: str) -> str:
    """Aggressive normalisation for label comparison only (never for values)."""
    t = (text or "").strip().lower()
    t = re.sub(r"^[\s\d]*[.)\]]\s*", "", t)     # strip "12." / "3)" numbering
    t = re.sub(r"[^\w\u0c80-\u0cff]+", " ", t)   # keep Latin/digits/Kannada
    return re.sub(r"\s+", " ", t).strip()


def _has_kannada(text: str) -> bool:
    return any("\u0c80" <= ch <= "\u0cff" for ch in text or "")


def _split_label_value(line: str) -> tuple[str, str, bool]:
    """Split ``label : value``. Returns (label, value, found_separator)."""
    best_idx, best_sep = -1, ""
    for sep in _SEPARATORS:
        idx = line.find(sep)
        # A separator only counts if a plausible label precedes it. Guards
        # against splitting on a hyphen inside a date or a name.
        if idx > 0 and (best_idx == -1 or idx < best_idx):
            if sep in "-\u2013\u2014" and idx < 3:
                continue
            best_idx, best_sep = idx, sep
    if best_idx == -1:
        return line.strip(), "", False
    return line[:best_idx].strip(), line[best_idx + len(best_sep):].strip(), True


def _label_score(candidate: str, spec: FieldSpec) -> tuple[float, str]:
    """Best (score, matched label) for a candidate label against one spec."""
    cand = _norm_label(candidate)
    if not cand:
        return 0.0, ""
    best, best_label = 0.0, ""

    for label in spec.labels_en:
        target = _norm_label(label)
        if not target:
            continue
        if cand == target:
            return 1.0, label
        # Containment scores high but not perfect: "date" inside "date of birth"
        # must not beat an exact "date" match elsewhere.
        if target in cand or cand in target:
            score = 0.93 if abs(len(cand) - len(target)) <= 4 else 0.85
        else:
            score = SequenceMatcher(None, cand, target).ratio()
        if score > best:
            best, best_label = score, label

    for label in spec.labels_kn:
        target = _norm_label(label)
        if not target:
            continue
        if cand == target:
            return 1.0, label
        if target in cand or cand in target:
            score = 0.92
        else:
            score = SequenceMatcher(None, cand, target).ratio()
            # Kannada fuzzy matching is noisier; require a higher bar.
            if score < _LABEL_MATCH_MIN_KN:
                score = 0.0
        if score > best:
            best, best_label = score, label

    return best, best_label


def _match_line(label_text: str) -> tuple[Optional[FieldSpec], float, str]:
    """Find the template field a line's label refers to."""
    best_spec, best_score, best_label = None, 0.0, ""
    for spec in FIR_TEMPLATE_V1:
        score, label = _label_score(label_text, spec)
        if score > best_score:
            best_spec, best_score, best_label = spec, score, label
    floor = _LABEL_MATCH_MIN_KN if _has_kannada(label_text) else _LABEL_MATCH_MIN
    if best_spec is None or best_score < floor:
        return None, 0.0, ""
    return best_spec, best_score, best_label


# ---------------------------------------------------------------------------
# Value parsers — each returns (value, value_confidence, note)
# ---------------------------------------------------------------------------
# Compared AFTER _norm_label, which strips punctuation — so "N/A" arrives as
# "n a" and "-" arrives as "". Both spellings are listed to keep that explicit.
_BLANK_MARKERS = {
    "", "-", "--", "---", "_", "__", "___",
    "n/a", "n a", "na", "nil", "none", "nill", "no", "not known", "unknown",
    "not applicable", "not available", "same as above", "do", "ditto", "x", "xx",
}


def _is_blank(raw: str) -> bool:
    """True for an unfilled line: empty, a dash/underscore rule, or a placeholder.

    Officers write "N/A", "-" or "Nil" on lines that do not apply, and treating
    those as real values would put literal "N/A" strings into case data.
    """
    return _norm_label(raw) in _BLANK_MARKERS or not (raw or "").strip(" _-.")


def _parse_text(raw: str) -> tuple[Optional[str], float, str]:
    v = re.sub(r"\s+", " ", (raw or "").strip()).strip(" _.-")
    if not v:
        return None, 0.0, ""
    # Very short free text is usually a mis-read fragment rather than a value.
    conf = 1.0 if len(v) >= 3 else 0.55
    return v, conf, "" if len(v) >= 3 else "Very short value — confirm."


def _parse_int(raw: str) -> tuple[Optional[int], float, str]:
    digits = re.findall(r"\d+", normalize_digits(_fix_digit_lookalikes(raw or "")))
    if not digits:
        return None, 0.0, ""
    return int(digits[0]), 1.0, ""


def _parse_phone(raw: str) -> tuple[Optional[str], float, str]:
    digits = re.sub(r"\D", "", normalize_digits(_fix_digit_lookalikes(raw or "")))
    if len(digits) >= 12 and digits.startswith("91"):
        digits = digits[-10:]
    if len(digits) == 10:
        return digits, 1.0, ""
    if 7 <= len(digits) <= 15:
        return digits, 0.5, f"Expected 10 digits, read {len(digits)} — confirm."
    return None, 0.0, ""


_DATE_PATTERNS = (
    (re.compile(r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b"), "ymd"),
    (re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})\b"), "dmy"),
    (re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{2})\b"), "dmy2"),
)
_TIME_PATTERN = re.compile(r"\b(\d{1,2})[:.\u0ca6](\d{2})\s*(am|pm|AM|PM)?\b")


def _parse_date_parts(raw: str) -> tuple[Optional[str], float, str]:
    """Return an ISO date (YYYY-MM-DD) with a confidence + caveat."""
    text = normalize_digits(raw or "")
    for pattern, order in _DATE_PATTERNS:
        m = pattern.search(text)
        if not m:
            continue
        try:
            if order == "ymd":
                y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            else:
                d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if order == "dmy2":
                    y += 2000 if y < 70 else 1900
        except (TypeError, ValueError):
            continue
        note, conf = "", 1.0
        # An unambiguous day (>12) proves the order; otherwise DD/MM vs MM/DD is
        # genuinely ambiguous and the officer has to confirm.
        if order.startswith("dmy") and d <= 12 and mo <= 12 and d != mo:
            conf = 0.72
            note = "Day/month order is ambiguous — confirm."
        if not (1 <= mo <= 12 and 1 <= d <= 31):
            return None, 0.0, "Unreadable date."
        return f"{y:04d}-{mo:02d}-{d:02d}", conf, note
    return None, 0.0, ""


def _parse_time_parts(raw: str) -> tuple[Optional[str], float, str]:
    m = _TIME_PATTERN.search(normalize_digits(raw or ""))
    if not m:
        return None, 0.0, ""
    try:
        hh, mm = int(m.group(1)), int(m.group(2))
    except (TypeError, ValueError):
        return None, 0.0, ""
    suffix = (m.group(3) or "").lower()
    if suffix == "pm" and hh < 12:
        hh += 12
    if suffix == "am" and hh == 12:
        hh = 0
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        return None, 0.0, "Unreadable time."
    return f"{hh:02d}:{mm:02d}", 1.0, ""


def _parse_date(raw: str) -> tuple[Optional[str], float, str]:
    return _parse_date_parts(raw)


def _parse_time(raw: str) -> tuple[Optional[str], float, str]:
    return _parse_time_parts(raw)


def _parse_datetime(raw: str) -> tuple[Optional[str], float, str]:
    """Combine a date and an optional time into an ISO-8601 local timestamp."""
    date_v, date_conf, date_note = _parse_date_parts(raw)
    if not date_v:
        return None, 0.0, date_note
    time_v, _time_conf, time_note = _parse_time_parts(raw)
    if time_v:
        return f"{date_v}T{time_v}:00", date_conf, (date_note or time_note)
    # Date with no time is legitimate; midnight is an assumption, so flag it.
    return f"{date_v}T00:00:00", min(date_conf, 0.85), (
        date_note or "No time on the form — assumed 00:00.")


def _parse_case_kind(raw: str) -> tuple[Optional[str], float, str]:
    norm = _norm_label(raw)
    if not norm:
        return None, 0.0, ""
    for kind, words in _CASE_KIND_WORDS.items():
        for w in words:
            if w in norm:
                # "fir" also appears inside "zero fir": prefer the longer word,
                # handled by checking specific kinds before the generic one.
                if kind == "fir_standard" and "zero" in norm:
                    continue
                return kind, 0.95 if len(w) > 3 else 0.8, ""
    for kind, words in _CASE_KIND_WORDS_KN.items():
        for w in words:
            if w in raw:
                return kind, 0.85, ""
    return None, 0.0, "Unrecognised case type — defaulted to Standard FIR."


def _parse_sections(raw: str) -> tuple[list[dict], float, str]:
    """Parse ``IPC 379, 411 / BNS 303(2)`` into ActSection pairs.

    Section numbers are attached to the most recent act token, which is how the
    text actually reads on a form.
    """
    text = normalize_digits(raw or "")
    if not text.strip():
        return [], 0.0, ""
    upper = text.upper()

    # Locate every act token with its position.
    hits: list[tuple[int, str, int]] = []   # (position, act_code, token_length)
    for token, act in _ACT_TOKENS:
        start = 0
        while True:
            idx = upper.find(token, start)
            if idx == -1:
                break
            # Skip a token already covered by a longer match at the same spot.
            if not any(h[0] <= idx < h[0] + h[2] for h in hits):
                hits.append((idx, act, len(token)))
            start = idx + len(token)
    hits.sort()

    out: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def _sections_in(span: str) -> list[str]:
        # Matches 302, 304A, 303(2), 66-C. The lookalike repair runs per token so
        # a mis-read "3O2" becomes "302" instead of section "3O" plus section "2".
        return [_fix_digit_lookalikes(m.group(0).replace(" ", ""))
                for m in re.finditer(r"\d{0,4}[O0-9]{1,4}\s*(?:\([0-9a-zA-Z]+\)|[-\s]?[A-Za-z]{1,2})?", span)]

    if hits:
        for i, (pos, act, tok_len) in enumerate(hits):
            end = hits[i + 1][0] if i + 1 < len(hits) else len(text)
            for sec in _sections_in(text[pos + tok_len:end]):
                key = (act, sec)
                if sec and key not in seen:
                    seen.add(key)
                    out.append({"act_code": act, "section_code": sec})
        if out:
            return out, 0.9, ""
        return [], 0.3, "Act recognised but no section number read — confirm."

    # No act token: collect bare section numbers and say so rather than guessing
    # an act, because the wrong act on a registered FIR is a real harm.
    bare = _sections_in(text)
    if bare:
        return ([{"act_code": "", "section_code": s} for s in bare], 0.45,
                "No Act named on the form — select the Act before submitting.")
    return [], 0.0, ""


_PARSERS = {
    "text": _parse_text,
    "int": _parse_int,
    "phone": _parse_phone,
    "date": _parse_date,
    "time": _parse_time,
    "datetime": _parse_datetime,
    "case_kind": _parse_case_kind,
    "sections": _parse_sections,
}


# ---------------------------------------------------------------------------
# Payload assembly
# ---------------------------------------------------------------------------
def _empty_payload() -> dict:
    """DraftPayload shape with every section present (mirrors schemas.DraftPayload)."""
    return {
        "source": {}, "registration": {}, "incident": {},
        "classification": {"acts_sections": [], "category_specific": {}},
        "narrative": {"restricted": False, "language": "en"},
    }


def _set_path(payload: dict, path: str, value: Any) -> None:
    section, _, key = path.partition(".")
    if not key:
        return
    payload.setdefault(section, {})[key] = value


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def extract_fir(text: str, *, ocr_confidence: Optional[float] = None,
                language: Optional[str] = None,
                auto_fill_threshold: Optional[float] = None) -> ExtractionResult:
    """Parse OCR text into a DraftPayload proposal.

    ``ocr_confidence`` is Zia's document-level score (0-1). It dampens every
    derived field confidence but never dominates it: a cleanly parsed date on a
    mediocre scan is still more trustworthy than an unparseable one on a good
    scan.

    Lookup fields (station/district/officer) are parsed to TEXT here and left for
    ``resolve.py`` to turn into ids against live reference data, so this function
    stays pure and unit-testable with no database.
    """
    settings = get_settings()
    threshold = (auto_fill_threshold if auto_fill_threshold is not None
                 else settings.scan_ocr_auto_fill_threshold)
    max_chars = settings.scan_ocr_max_text_chars
    raw_text = (text or "")[:max_chars]

    result = ExtractionResult(payload=_empty_payload())
    result.language = language or ("kn" if _has_kannada(raw_text) else "en")
    result.payload["narrative"]["language"] = "kn" if result.language in ("kn", "mixed") else "en"

    doc_factor = 0.5 + 0.5 * (ocr_confidence if ocr_confidence is not None else 0.8)

    # --- pass 1: split lines into (spec, raw value) pairs, honouring multiline
    lines = [ln.rstrip() for ln in raw_text.splitlines()]
    collected: list[tuple[FieldSpec, float, str, str]] = []   # spec, label_score, label, value
    idx = 0
    while idx < len(lines):
        line = lines[idx]
        if not line.strip():
            idx += 1
            continue
        label_text, value_text, had_sep = _split_label_value(line)
        if not had_sep:
            idx += 1
            continue
        spec, label_score, matched_label = _match_line(label_text)
        if spec is None:
            idx += 1
            continue

        if spec.multiline:
            # Absorb following lines until the next recognised label, so a
            # narrative or address survives line wrapping.
            parts = [value_text] if value_text else []
            look = idx + 1
            while look < len(lines):
                nxt = lines[look]
                if not nxt.strip():
                    look += 1
                    continue
                nxt_label, _nxt_value, nxt_sep = _split_label_value(nxt)
                if nxt_sep and _match_line(nxt_label)[0] is not None:
                    break
                parts.append(nxt.strip())
                look += 1
            value_text = " ".join(p for p in parts if p).strip()
            idx = look
        else:
            idx += 1

        collected.append((spec, label_score, matched_label, value_text))

    result.matched_label_count = len(collected)
    # A real intake form carries ~19 labelled lines. Requiring a solid majority
    # of a handful keeps a stray letter or an unrelated document from being
    # presented to the officer as a recognised FIR.
    result.template_matched = len(collected) >= 6

    # --- pass 2: parse values, score confidence, assemble payload + parties
    party_values: dict[str, dict[str, Any]] = {}
    party_conf: dict[str, float] = {}

    for spec, label_score, matched_label, value_text in collected:
        if _is_blank(value_text):
            continue
        parser = _PARSERS.get(spec.kind, _parse_text)
        # Lookup fields resolve later; capture their text now.
        if spec.kind.startswith("lookup_"):
            value, value_conf, note = _parse_text(value_text)
        else:
            value, value_conf, note = parser(value_text)

        if value is None or (isinstance(value, list) and not value):
            # Parsed nothing usable: surface it so the officer sees the form had
            # content the parser could not read, rather than silent omission.
            result.fields.append(ExtractedField(
                path=spec.path, value=None, raw_text=value_text, confidence=0.0,
                label_matched=matched_label, requires_review=True, auto_filled=False,
                note=note or "Could not read this value."))
            continue

        confidence = max(0.0, min(1.0, label_score * value_conf * doc_factor))
        auto = confidence >= threshold

        ef = ExtractedField(
            path=spec.path, value=value, raw_text=value_text, confidence=confidence,
            label_matched=matched_label, requires_review=not auto, auto_filled=False,
            note=note)

        if spec.party_role:
            # Party attributes are grouped into one proposed party per role.
            if auto:
                party_values.setdefault(spec.party_role, {})[spec.party_attr] = value
                party_conf[spec.party_role] = min(
                    party_conf.get(spec.party_role, 1.0), confidence)
                ef.auto_filled = True
            result.fields.append(ef)
            continue

        if spec.path == "__case_kind":
            if auto:
                result.case_kind = value
                ef.auto_filled = True
            result.fields.append(ef)
            continue

        if spec.kind.startswith("lookup_"):
            # Reference text only. resolve.py decides whether it maps to exactly
            # one id; until then nothing is written to the payload, because a
            # silently wrong police station or officer is worse than a blank one.
            if auto:
                result.lookup_texts[spec.path] = value
                ef.auto_filled = True
            result.fields.append(ef)
            continue

        if auto:
            _set_path(result.payload, spec.path, value)
            ef.auto_filled = True
        result.fields.append(ef)

    # --- proposed parties (never auto-linked to a canonical person)
    for role, attrs in party_values.items():
        name = attrs.pop("display_name", None)
        party: dict[str, Any] = {
            "role_type": role,
            "party_nature": "person",
            "is_unknown": not bool(name),
            "display_name": name,
            "attributes": {k: v for k, v in attrs.items() if v is not None},
            "confidence": round(party_conf.get(role, 0.0), 4),
        }
        result.parties.append(party)

    if not result.case_kind:
        result.case_kind = "fir_standard"
        result.notes.append(
            "Case type was not read from the form; defaulted to Standard FIR. "
            "Change it on step 1 if that is wrong.")

    if not result.template_matched:
        result.notes.append(
            f"Only {result.matched_label_count} form label(s) were recognised, so "
            "this may not be a DRISHTI intake form or the scan may be too unclear. "
            "Check every field, or enter the FIR manually.")

    if ocr_confidence is not None and ocr_confidence < settings.scan_ocr_low_confidence_threshold:
        result.notes.append(
            f"Recogniser confidence was low ({ocr_confidence:.0%}). Expect errors "
            "and read the original page alongside the form.")

    return result


# ---------------------------------------------------------------------------
# Printable-template contract
# ---------------------------------------------------------------------------
# Field kinds the officer should be given character cells for rather than a plain
# ruled line. Discrete boxes are what makes handwriting legible to OCR: Zia only
# recognises handwriting close to a standard character shape, and one character
# per cell gets much closer to that than joined writing does.
_BOXED_KINDS = frozenset({"date", "time", "datetime", "int", "phone"})

_KIND_HINTS = {
    "date": "DD / MM / YYYY",
    "time": "HH : MM (24 hour)",
    "datetime": "DD / MM / YYYY   HH : MM",
    "phone": "10 digits",
    "int": "digits",
    "sections": "Act then section numbers, e.g. IPC 379, 411",
}


def template_spec() -> dict:
    """The printable intake-form contract, generated from ``FIR_TEMPLATE_V1``.

    The SPA renders this into the blank form officers write on. Generating it from
    the same tuple the parser uses means a field can never appear on the printed
    page without the parser knowing how to read it back.
    """
    settings = get_settings()
    lines = []
    for i, spec in enumerate(FIR_TEMPLATE_V1, start=1):
        lines.append({
            "index": i,
            "field": spec.path,
            "kind": spec.kind,
            "label_en": spec.labels_en[0] if spec.labels_en else spec.path,
            "label_kn": spec.labels_kn[0] if spec.labels_kn else "",
            "aliases_en": list(spec.labels_en),
            "multiline": spec.multiline,
            "boxed": spec.kind in _BOXED_KINDS,
            "format_hint": _KIND_HINTS.get(spec.kind, ""),
            "help_en": spec.help_en,
            "party_role": spec.party_role or None,
        })
    return {
        "template_code": TEMPLATE_CODE,
        "separator": ":",
        "languages": ["en", "kn"],
        "lines": lines,
        "auto_fill_threshold": float(settings.scan_ocr_auto_fill_threshold),
        "guidance_en": [
            "Write one value per line, after the colon.",
            "Use CAPITAL letters and leave a clear gap between words.",
            "Write dates as DD/MM/YYYY and times on the 24-hour clock.",
            "Write one character per box where boxes are printed.",
            "Kannada or English are both fine, and the two may be mixed.",
            "Keep the page flat and well lit when photographing it.",
        ],
        "guidance_kn": [
            "\u0caa\u0ccd\u0cb0\u0ca4\u0cbf \u0cb8\u0cbe\u0cb2\u0cbf\u0c97\u0cc6 \u0c92\u0c82\u0ca6\u0cc1 "
            "\u0cae\u0cbe\u0cb9\u0cbf\u0ca4\u0cbf\u0caf\u0ca8\u0ccd\u0ca8\u0cc1 \u0cac\u0cb0\u0cc6\u0caf\u0cbf\u0cb0\u0cbf.",
            "\u0ca6\u0cbf\u0ca8\u0cbe\u0c82\u0c95\u0cb5\u0ca8\u0ccd\u0ca8\u0cc1 DD/MM/YYYY "
            "\u0cb0\u0cc2\u0caa\u0ca6\u0cb2\u0ccd\u0cb2\u0cbf \u0cac\u0cb0\u0cc6\u0caf\u0cbf\u0cb0\u0cbf.",
            "\u0c85\u0c95\u0ccd\u0cb7\u0cb0\u0c97\u0cb3\u0ca8\u0ccd\u0ca8\u0cc1 "
            "\u0cb8\u0ccd\u0caa\u0cb7\u0ccd\u0c9f\u0cb5\u0cbe\u0c97\u0cbf \u0cac\u0cb0\u0cc6\u0caf\u0cbf\u0cb0\u0cbf.",
        ],
        # Stated on the form itself so nobody mistakes this for an automated
        # registration path.
        "notice_en": (
            "Reading this form is an aid to typing, not a decision. Every field is "
            "reviewed by the registering officer, and the case is created only when "
            "a supervisor approves the draft."),
    }
