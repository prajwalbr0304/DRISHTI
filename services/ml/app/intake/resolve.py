"""Resolve OCR-extracted reference TEXT onto real reference-data ids.

``extract.py`` reads "Udupi Town PS" off a scanned form. The draft needs
``station_id: int``. This module bridges that gap against live reference data
from ``lookups.reference_lookups()`` (RDS when configured, else Catalyst Data
Store — the same source the wizard's dropdowns render).

The governing rule: **auto-fill only on a confident, unambiguous, unique match.**

Everything else becomes an ``UnresolvedLookup`` carrying ranked candidates for
the officer to pick from. Silently selecting the wrong police station, the wrong
district or the wrong section on a report that becomes a registered FIR is a
real-world harm, and a blank field an officer must fill is strictly better than a
plausible-looking wrong one. So there is no "best guess" fallback here by design.

Script handling
---------------
Reference tables are stored in English. A Kannada-language form names its station
and district in Kannada script, and fuzzy string matching across scripts is
meaningless (a Latin and a Kannada string share no characters). Two mitigations:

  * ``KANNADA_DISTRICT_ALIASES`` maps Karnataka's district names in Kannada to
    their English forms. It is a bounded, finite, verifiable set, unlike general
    transliteration.
  * Anything else in Kannada that finds no alias is reported unresolved with an
    explicit reason. It is not transliterated on a guess.

No new dependency: matching uses ``difflib`` from the standard library. Postgres
``pg_trgm`` is available and would be faster at scale, but reference data here is
small (a few thousand units) and keeping this pure makes it unit-testable without
a database.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Optional

from ..config import get_settings
from .extract import ExtractedField, ExtractionResult, UnresolvedLookup

# A match must clear this to be considered at all.
_MATCH_FLOOR = 0.62
# A unique auto-fill also needs this much daylight over the runner-up, otherwise
# the two names are too close to choose between mechanically.
_AMBIGUITY_MARGIN = 0.08
# How many ranked alternatives to hand back for a manual choice.
_MAX_CANDIDATES = 5

# Noise words to drop before comparing station names. "Udupi Town PS",
# "Udupi Town Police Station" and "UDUPI TOWN P.S." must all compare equal.
_STATION_NOISE = (
    "police station", "police stn", "police", "p s", "ps", "pstn", "stn",
    "station", "thana", "thane", "circle", "sub division", "subdivision",
)

# Kannada district names -> the English spelling used in the District table.
# Bounded and checkable, which is why this exists instead of transliteration.
KANNADA_DISTRICT_ALIASES: dict[str, str] = {
    "\u0cac\u0cbe\u0c97\u0cb2\u0c95\u0ccb\u0c9f\u0cc6": "Bagalkot",
    "\u0cac\u0cb3\u0ccd\u0cb3\u0cbe\u0cb0\u0cbf": "Ballari",
    "\u0cac\u0cc6\u0cb3\u0c97\u0cbe\u0cb5\u0cbf": "Belagavi",
    "\u0cac\u0cc6\u0c82\u0c97\u0cb3\u0cc2\u0cb0\u0cc1": "Bengaluru",
    "\u0cac\u0cc0\u0ca6\u0cb0\u0ccd": "Bidar",
    "\u0c9a\u0cbe\u0cae\u0cb0\u0cbe\u0c9c\u0ca8\u0c97\u0cb0": "Chamarajanagar",
    "\u0c9a\u0cbf\u0c95\u0ccd\u0c95\u0cac\u0cb3\u0ccd\u0cb3\u0cbe\u0caa\u0cc1\u0cb0": "Chikkaballapur",
    "\u0c9a\u0cbf\u0c95\u0ccd\u0c95\u0cae\u0c97\u0cb3\u0cc2\u0cb0\u0cc1": "Chikkamagaluru",
    "\u0c9a\u0cbf\u0ca4\u0ccd\u0cb0\u0ca6\u0cc1\u0cb0\u0ccd\u0c97": "Chitradurga",
    "\u0ca6\u0c95\u0ccd\u0cb7\u0cbf\u0ca3 \u0c95\u0ca8\u0ccd\u0ca8\u0ca1": "Dakshina Kannada",
    "\u0ca6\u0cbe\u0cb5\u0ca3\u0c97\u0cc6\u0cb0\u0cc6": "Davanagere",
    "\u0ca7\u0cbe\u0cb0\u0cb5\u0cbe\u0ca1": "Dharwad",
    "\u0c97\u0ca6\u0c97": "Gadag",
    "\u0cb9\u0cbe\u0cb8\u0ca8": "Hassan",
    "\u0cb9\u0cbe\u0cb5\u0cc7\u0cb0\u0cbf": "Haveri",
    "\u0c95\u0cb2\u0cac\u0cc1\u0cb0\u0c97\u0cbf": "Kalaburagi",
    "\u0c95\u0ccb\u0ca1\u0c97\u0cc1": "Kodagu",
    "\u0c95\u0ccb\u0cb2\u0cbe\u0cb0": "Kolar",
    "\u0c95\u0cca\u0caa\u0ccd\u0caa\u0cb3": "Koppal",
    "\u0cae\u0c82\u0ca1\u0ccd\u0caf": "Mandya",
    "\u0cae\u0cc8\u0cb8\u0cc2\u0cb0\u0cc1": "Mysuru",
    "\u0cb0\u0cbe\u0caf\u0c9a\u0cc2\u0cb0\u0cc1": "Raichur",
    "\u0cb0\u0cbe\u0cae\u0ca8\u0c97\u0cb0": "Ramanagara",
    "\u0cb6\u0cbf\u0cb5\u0cae\u0cca\u0c97\u0ccd\u0c97": "Shivamogga",
    "\u0ca4\u0cc1\u0cae\u0c95\u0cc2\u0cb0\u0cc1": "Tumakuru",
    "\u0c89\u0ca1\u0cc1\u0caa\u0cbf": "Udupi",
    "\u0c89\u0ca4\u0ccd\u0ca4\u0cb0 \u0c95\u0ca8\u0ccd\u0ca8\u0ca1": "Uttara Kannada",
    "\u0cb5\u0cbf\u0c9c\u0caf\u0caa\u0cc1\u0cb0": "Vijayapura",
    "\u0cb5\u0cbf\u0c9c\u0caf\u0ca8\u0c97\u0cb0": "Vijayanagara",
    "\u0caf\u0cbe\u0ca6\u0c97\u0cbf\u0cb0\u0cbf": "Yadgir",
}

# Which reference collection backs each lookup kind, and its human label.
_LOOKUP_SOURCE: dict[str, tuple[str, str]] = {
    "unit": ("units", "police station"),
    "district": ("districts", "district"),
    "officer": ("officers", "officer"),
    "crime_head": ("crime_heads", "crime head"),
    "gravity": ("gravities", "gravity"),
    "court": ("courts", "court"),
}


@dataclass
class ResolvedLookup:
    path: str
    value: Optional[int] = None
    matched_name: str = ""
    score: float = 0.0
    unique: bool = False


def _has_kannada(text: str) -> bool:
    return any("\u0c80" <= ch <= "\u0cff" for ch in text or "")


def _norm(text: str) -> str:
    t = (text or "").strip().lower()
    t = re.sub(r"[^\w\u0c80-\u0cff\s]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _norm_station(text: str) -> str:
    """Normalise a station name by removing rank/type noise words."""
    t = _norm(text)
    for noise in _STATION_NOISE:
        t = re.sub(rf"\b{re.escape(noise)}\b", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _norm_officer(text: str) -> str:
    """Drop a rank prefix so "PSI Lakshmi Prasad" compares against "Lakshmi"."""
    t = _norm(text)
    ranks = ("psi", "asi", "si", "hc", "pc", "dysp", "sp", "addl sp", "acp",
             "dcp", "ci", "pi", "inspector", "sub inspector", "constable",
             "head constable", "sho", "smt", "sri", "shri", "mr", "mrs", "ms")
    for rank in sorted(ranks, key=len, reverse=True):
        t = re.sub(rf"^{re.escape(rank)}\b", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _translate_kannada(text: str, kind: str) -> tuple[str, bool]:
    """Map a Kannada reference name to English via the bounded alias table.

    Returns (text_to_match, was_translated). For a station, the district alias is
    still useful because station names usually embed a place name.
    """
    if not _has_kannada(text):
        return text, False
    stripped = _norm(text)
    for kn, en in KANNADA_DISTRICT_ALIASES.items():
        if _norm(kn) and _norm(kn) in stripped:
            # Keep any Latin remainder ("ಉಡುಪಿ Town PS" -> "Udupi Town PS").
            remainder = re.sub(re.escape(_norm(kn)), " ", stripped).strip()
            remainder = "".join(ch for ch in remainder if not _has_kannada(ch)).strip()
            return (f"{en} {remainder}".strip() if remainder else en), True
    return text, False


def _score(candidate: str, target: str) -> float:
    """Similarity of two already-normalised names."""
    if not candidate or not target:
        return 0.0
    if candidate == target:
        return 1.0
    if candidate in target or target in candidate:
        # Containment is strong evidence but shorter overlaps mean less.
        shorter, longer = sorted((len(candidate), len(target)))
        return 0.88 + 0.1 * (shorter / longer)
    ratio = SequenceMatcher(None, candidate, target).ratio()
    # Token overlap rescues reordered names ("Town Udupi PS").
    ct, tt = set(candidate.split()), set(target.split())
    if ct and tt:
        overlap = len(ct & tt) / len(ct | tt)
        ratio = max(ratio, overlap * 0.95)
    return ratio


def _rank(text: str, items: list[dict], normaliser) -> list[tuple[float, dict]]:
    target = normaliser(text)
    scored = [(_score(normaliser(str(it.get("name") or "")), target), it)
              for it in items if it.get("name")]
    scored.sort(key=lambda p: (-p[0], str(p[1].get("name") or "")))
    return scored


def _resolve_one(text: str, items: list[dict], kind: str,
                 threshold: float) -> tuple[ResolvedLookup, list[dict], str]:
    """Best-effort resolution of one reference name.

    Returns (resolution, candidate list, reason-when-unresolved).
    """
    normaliser = {"unit": _norm_station, "officer": _norm_officer}.get(kind, _norm)
    match_text, translated = _translate_kannada(text, kind)
    ranked = _rank(match_text, items, normaliser)
    if not ranked:
        return ResolvedLookup(path=""), [], f"No {kind} reference data available."

    top_score, top = ranked[0]
    runner_up = ranked[1][0] if len(ranked) > 1 else 0.0
    candidates = [
        {"id": it.get("id"), "name": it.get("name"),
         "parent_id": it.get("parent_id"), "score": round(sc, 4)}
        for sc, it in ranked[:_MAX_CANDIDATES] if sc >= _MATCH_FLOOR * 0.8
    ]

    if _has_kannada(text) and not translated:
        return (ResolvedLookup(path=""), candidates,
                f"'{text}' is in Kannada script and no English equivalent is on "
                f"record for this {kind}. Select it from the list.")
    if top_score < max(_MATCH_FLOOR, threshold):
        return (ResolvedLookup(path=""), candidates,
                f"No confident {kind} match for '{text}'.")
    if top_score - runner_up < _AMBIGUITY_MARGIN:
        return (ResolvedLookup(path=""), candidates,
                f"'{text}' matches more than one {kind} about equally well "
                f"({top.get('name')} vs {ranked[1][1].get('name')}). Choose one.")

    return (ResolvedLookup(path="", value=top.get("id"),
                           matched_name=str(top.get("name") or ""),
                           score=top_score, unique=True),
            candidates, "")


# ---------------------------------------------------------------------------
# Section / act validation
# ---------------------------------------------------------------------------
def _resolve_sections(pairs: list[dict], acts: list[dict],
                      sections: list[dict]) -> tuple[list[dict], list[str]]:
    """Keep only act/section pairs that exist in reference data.

    A pair the parser read with no Act named is matched against the Section table;
    if exactly one Act carries that section number it is filled in, otherwise the
    pair is kept with a blank act so the officer chooses. Nothing is invented.
    """
    if not pairs:
        return [], []
    valid_acts = {str(a.get("act_code") or "").upper() for a in acts if a.get("act_code")}
    by_section: dict[str, list[str]] = {}
    known: set[tuple[str, str]] = set()
    for s in sections:
        act = str(s.get("act_code") or "").upper()
        sec = str(s.get("section_code") or "").strip()
        if act and sec:
            known.add((act, sec))
            by_section.setdefault(sec, []).append(act)

    out: list[dict] = []
    notes: list[str] = []
    for pair in pairs:
        act = str(pair.get("act_code") or "").upper().strip()
        sec = str(pair.get("section_code") or "").strip()
        if not sec:
            continue
        if act and (act, sec) in known:
            out.append({"act_code": act, "section_code": sec})
            continue
        if act and act in valid_acts:
            out.append({"act_code": act, "section_code": sec})
            notes.append(
                f"Section {sec} is not on record under {act} — verify it before submitting.")
            continue
        if not act:
            owners = by_section.get(sec, [])
            if len(owners) == 1:
                out.append({"act_code": owners[0], "section_code": sec})
                notes.append(f"Section {sec} was matched to {owners[0]} (no Act on the form).")
            else:
                out.append({"act_code": "", "section_code": sec})
                notes.append(
                    f"Section {sec} exists under several Acts — choose the Act."
                    if owners else
                    f"Section {sec} is not in the Act/Section reference — verify it.")
            continue
        # An act token we do not recognise at all: keep the section, drop the act.
        out.append({"act_code": "", "section_code": sec})
        notes.append(f"Act '{act}' is not in the reference list — select the Act for section {sec}.")
    return out, notes


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def resolve_extraction(result: ExtractionResult, *, reference: Optional[dict] = None,
                       unit_id: Optional[int] = None) -> ExtractionResult:
    """Fill reference ids into ``result.payload``, in place, and return it.

    ``reference`` is a ``lookups.reference_lookups()`` payload. It is injectable so
    this is testable without a database; when omitted it is fetched.

    Unresolvable values are appended to ``result.unresolved`` with ranked
    candidates and never written to the payload.
    """
    if reference is None:
        from . import lookups
        try:
            reference = lookups.reference_lookups(unit_id=unit_id)
        except Exception as exc:  # noqa: BLE001 — reference data is best-effort
            result.notes.append(
                "Reference data was unavailable, so station/district/officer could "
                f"not be matched automatically ({type(exc).__name__}). Select them manually.")
            return result

    threshold = get_settings().scan_ocr_auto_fill_threshold
    by_path = {f.path: f for f in result.fields}

    for path, text in list(result.lookup_texts.items()):
        kind = _kind_for_path(path)
        collection, label = _LOOKUP_SOURCE.get(kind, ("", kind))
        items = list(reference.get(collection) or []) if collection else []

        resolution, candidates, reason = _resolve_one(text, items, kind, threshold)
        ef = by_path.get(path)

        if resolution.unique and resolution.value is not None:
            section, _, key = path.partition(".")
            result.payload.setdefault(section, {})[key] = resolution.value
            if ef is not None:
                ef.value = resolution.value
                ef.auto_filled = True
                ef.requires_review = False
                # The resolution step can only lower trust, never raise it.
                ef.confidence = min(ef.confidence, resolution.score)
                ef.note = (f"Matched '{text}' to {label} '{resolution.matched_name}'."
                           if _norm(resolution.matched_name) != _norm(text) else ef.note)
            continue

        result.unresolved.append(UnresolvedLookup(
            path=path, raw_text=text, lookup=kind,
            candidates=candidates, reason=reason))
        if ef is not None:
            ef.value = None
            ef.auto_filled = False
            ef.requires_review = True
            ef.note = reason

    # District can be derived from a resolved station, which is how the manual
    # wizard behaves too (Registration.district_id is "derived; overridable").
    reg = result.payload.setdefault("registration", {})
    station_district = None
    for unit in reference.get("units") or []:
        if unit.get("id") == reg.get("station_id"):
            station_district = unit.get("parent_id")
            break

    if reg.get("station_id") and not reg.get("district_id") and station_district:
        reg["district_id"] = station_district
        result.notes.append("District was derived from the police station.")
    elif (reg.get("station_id") and reg.get("district_id") and station_district
            and reg["district_id"] != station_district):
        # Both fields were read and they contradict each other. Trust neither:
        # clear the district and make the officer settle it, because guessing
        # here silently mis-files the case's jurisdiction.
        names = {d.get("id"): d.get("name") for d in reference.get("districts") or []}
        read_name = names.get(reg["district_id"], reg["district_id"])
        derived_name = names.get(station_district, station_district)
        result.unresolved.append(UnresolvedLookup(
            path="registration.district_id",
            raw_text=str(result.lookup_texts.get("registration.district_id", "")),
            lookup="district",
            candidates=[
                {"id": station_district, "name": derived_name, "parent_id": None, "score": 1.0},
                {"id": reg["district_id"], "name": read_name, "parent_id": None, "score": 1.0},
            ],
            reason=(f"The form's district ('{read_name}') does not match the district "
                    f"of the station it names ('{derived_name}'). Confirm which is right.")))
        reg.pop("district_id", None)
        district_field = by_path.get("registration.district_id")
        if district_field is not None:
            district_field.value = None
            district_field.auto_filled = False
            district_field.requires_review = True
            district_field.note = "Contradicts the station's district — confirm."

    # Validate act/section pairs against reference data.
    cls = result.payload.setdefault("classification", {})
    pairs = cls.get("acts_sections") or []
    if pairs:
        cleaned, section_notes = _resolve_sections(
            pairs, list(reference.get("acts") or []), list(reference.get("sections") or []))
        cls["acts_sections"] = cleaned
        result.notes.extend(section_notes)
        sec_field = by_path.get("classification.acts_sections")
        if sec_field is not None and section_notes:
            sec_field.requires_review = True
            sec_field.value = cleaned
            sec_field.note = " ".join(section_notes)

    return result


def _kind_for_path(path: str) -> str:
    """Map a payload path back to its reference kind."""
    if path.endswith("station_id") or path.endswith("unit_id"):
        return "unit"
    if path.endswith("district_id"):
        return "district"
    if path.endswith("officer_id") or path.endswith("io_id"):
        return "officer"
    if path.endswith("major_head_id") or path.endswith("minor_head_id"):
        return "crime_head"
    if path.endswith("gravity_id"):
        return "gravity"
    if path.endswith("court_id"):
        return "court"
    return "unit"
