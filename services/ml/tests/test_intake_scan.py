"""Scanned-FIR intake lane (Catalyst Zia OCR) tests.

Unit (no DB):
  * template/parser contract — every printed line is one the parser can read back;
  * English + Kannada extraction, Kannada numerals, OCR digit/letter repair;
  * confidence gating — an ambiguous value is never silently pre-filled;
  * lookup resolution — unique match fills, ambiguity/contradiction/unknown do not;
  * the Zia adapter fails CLOSED by default and validates input before spending
    a network call;
  * the governance invariant: enabling the scan lane does not enable evidence
    extraction.

API (TestClient, no DB): capability + template contracts, and that the OCR
endpoint refuses cleanly (never 500s) while the feature is off.

Integration (@requires_db, inside the ROLLED-BACK ``rw_rollback`` transaction so
nothing is persisted): a fake OCR engine drives the real
scan -> propose -> officer-corrects -> draft path, asserting per-field provenance
and, above all, that NO CaseMaster is created without the human approve step.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import catalyst_rest, zia_ocr
from app.config import get_settings
from app.intake import extract, guards, resolve, scan_service
from app.intake.schemas import DraftPayload, ScanApplyRequest
from app.intake.service import IntakeConflict, IntakeValidationError
from app.main import app
from conftest import requires_db

# --- fixtures: filled forms as OCR would return them ------------------------

FORM_EN = """
DRISHTI FIR INTAKE FORM
1. Police Station : Udupi Town PS
2. District : Udupi
3. FIR No : CCTNS-SYN-000481
4. Date of Registration : 14/03/2026
5. Time of Registration : 21:45
6. Case Type : Standard FIR
7. Acts and Sections : IPC 379, 411
8. Occurrence From : 13/03/2026 22:30
9. Occurrence To : 14/03/2026 06:00
10. Place of Occurrence : Car Street, near the bus stand
11. Landmark : Opposite Sri Krishna Temple
12. Complainant Name : Ramesh Shetty
13. Complainant Age : 41
14. Complainant Phone : 9845012345
15. Brief Facts : The complainant parked his motorcycle outside the shop
at about 22:30 hours and found it missing the next morning.
16. Registering Officer : PSI Lakshmi Prasad
"""

# Kannada labels + Kannada numerals (a form filled in Kannada).
FORM_KN = (
    "\u0caa\u0cca\u0cb2\u0cbf\u0cb8\u0ccd \u0ca0\u0cbe\u0ca3\u0cc6 : Mangaluru North PS\n"
    "\u0c9c\u0cbf\u0cb2\u0ccd\u0cb2\u0cc6 : \u0ca6\u0c95\u0ccd\u0cb7\u0cbf\u0ca3 "
    "\u0c95\u0ca8\u0ccd\u0ca8\u0ca1\n"
    "\u0ca6\u0cbf\u0ca8\u0cbe\u0c82\u0c95 : \u0ce8\u0ce6/\u0ce6\u0ce9/\u0ce8\u0ce6\u0ce8\u0ce6\n"
    "\u0cb8\u0cae\u0caf : \u0ce7\u0ce6:\u0ce9\u0ce6\n"
    "\u0c95\u0cb2\u0c82 : BNS 303(2)\n"
    "\u0ca6\u0cc2\u0cb0\u0cc1\u0ca6\u0cbe\u0cb0\u0cb0 \u0cb9\u0cc6\u0cb8\u0cb0\u0cc1 : "
    "\u0cb8\u0cc1\u0cb0\u0cc7\u0cb6\u0ccd\n"
    "\u0ca6\u0cc2\u0cb0\u0cb5\u0cbe\u0ca3\u0cbf : 9845012345\n"
    "\u0cb8\u0c82\u0c95\u0ccd\u0cb7\u0cbf\u0caa\u0ccd\u0ca4 \u0cb5\u0cbf\u0cb5\u0cb0 : "
    "\u0c95\u0cb3\u0ccd\u0cb3\u0ca4\u0ca8 \u0cb5\u0cb0\u0ca6\u0cbf\n"
)

REFERENCE = {
    "units": [
        {"id": 101, "name": "Udupi Town Police Station", "parent_id": 27},
        {"id": 102, "name": "Udupi Rural Police Station", "parent_id": 27},
        {"id": 201, "name": "Mangaluru North Police Station", "parent_id": 24},
    ],
    "districts": [
        {"id": 27, "name": "Udupi"},
        {"id": 24, "name": "Dakshina Kannada"},
        {"id": 22, "name": "Mysuru"},
    ],
    "officers": [
        {"id": 5001, "name": "Lakshmi Prasad", "parent_id": 101},
        {"id": 5002, "name": "Ravi Kumar", "parent_id": 101},
    ],
    "acts": [{"act_code": "IPC"}, {"act_code": "BNS"}],
    "sections": [
        {"act_code": "IPC", "section_code": "379"},
        {"act_code": "IPC", "section_code": "411"},
        {"act_code": "IPC", "section_code": "302"},
        {"act_code": "BNS", "section_code": "303(2)"},
        {"act_code": "BNS", "section_code": "379"},
    ],
    "crime_heads": [], "crime_subheads": [], "gravities": [], "courts": [],
    "statuses": [], "categories": [], "party_roles": [],
}


def parse(text: str, *, confidence: float = 0.92, with_reference: bool = True):
    result = extract.extract_fir(text, ocr_confidence=confidence)
    if with_reference:
        result = resolve.resolve_extraction(result, reference=REFERENCE)
    return result


def field_by_path(result, path: str):
    return next((f for f in result.fields if f.path == path), None)


# ===========================================================================
# Template <-> parser contract
# ===========================================================================
def test_every_printed_line_is_readable_by_the_parser():
    """The print form is generated from the parser's own table, so a field can
    never be printed that the parser does not know how to read back."""
    spec = extract.template_spec()
    printed = {line["field"] for line in spec["lines"]}
    known = {s.path for s in extract.FIR_TEMPLATE_V1}
    assert printed == known
    assert spec["template_code"] == extract.TEMPLATE_CODE


def test_every_template_field_has_a_parser_and_a_bilingual_label():
    for s in extract.FIR_TEMPLATE_V1:
        assert s.labels_en, f"{s.path} has no English label"
        assert s.kind in extract._PARSERS or s.kind.startswith("lookup_"), (
            f"{s.path} has kind '{s.kind}' with no parser")


def test_numeric_fields_are_printed_as_character_cells():
    """Boxed cells are what make handwriting legible to OCR, so date/time/number
    fields must never be printed as a plain ruled line."""
    boxed = {l["field"]: l["boxed"] for l in extract.template_spec()["lines"]}
    assert boxed["registration.registration_date"] is True
    assert boxed["registration.registration_time"] is True
    assert boxed["__complainant_phone"] is True
    assert boxed["narrative.brief_facts"] is False


# ===========================================================================
# Extraction — English
# ===========================================================================
def test_english_form_extracts_core_fields():
    r = parse(FORM_EN)
    assert r.template_matched
    assert r.language == "en"
    assert r.case_kind == "fir_standard"
    assert r.payload["registration"]["registration_date"] == "2026-03-14"
    assert r.payload["registration"]["registration_time"] == "21:45"
    assert r.payload["incident"]["incident_from"] == "2026-03-13T22:30:00"
    assert r.payload["incident"]["landmark"] == "Opposite Sri Krishna Temple"
    assert r.payload["source"]["external_source_id"] == "CCTNS-SYN-000481"


def test_multiline_narrative_survives_line_wrapping():
    r = parse(FORM_EN)
    facts = r.payload["narrative"]["brief_facts"]
    assert "parked his motorcycle" in facts
    assert "missing the next morning" in facts
    # The following labelled line must NOT be swallowed into the narrative.
    assert "Registering Officer" not in facts


def test_sections_parse_with_act_attribution():
    r = parse(FORM_EN)
    assert r.payload["classification"]["acts_sections"] == [
        {"act_code": "IPC", "section_code": "379"},
        {"act_code": "IPC", "section_code": "411"},
    ]


def test_complainant_becomes_a_proposed_party_not_a_canonical_link():
    r = parse(FORM_EN)
    party = next(p for p in r.parties if p["role_type"] == "complainant")
    assert party["display_name"] == "Ramesh Shetty"
    assert party["attributes"]["age"] == 41
    assert party["attributes"]["phone"] == "9845012345"
    # A name is an attribute, never an identity key — canonicalisation happens
    # on approval, not on a machine read.
    assert "canonical_person_id" not in party


# ===========================================================================
# Extraction — Kannada
# ===========================================================================
def test_kannada_form_is_detected_and_parsed():
    r = parse(FORM_KN, confidence=0.85)
    assert r.language == "kn"
    assert r.payload["narrative"]["language"] == "kn"
    # Kannada numerals must reach the shared numeric parsers.
    assert r.payload["registration"]["registration_time"] == "10:30"
    assert r.payload["classification"]["acts_sections"] == [
        {"act_code": "BNS", "section_code": "303(2)"}]


def test_kannada_numerals_normalise_to_ascii():
    assert extract.normalize_digits("\u0ce7\u0ce6\u0ce9\u0ce6") == "1030"


def test_kannada_complainant_name_is_kept_in_its_own_script():
    r = parse(FORM_KN, confidence=0.85)
    party = next(p for p in r.parties if p["role_type"] == "complainant")
    assert party["display_name"] == "\u0cb8\u0cc1\u0cb0\u0cc7\u0cb6\u0ccd"


# ===========================================================================
# OCR noise handling + confidence gating
# ===========================================================================
# ===========================================================================
# Real recogniser layout (regression: Zia emits columns, not "label : value")
# ===========================================================================
# Verbatim shape of Catalyst Zia OCR output for the printed DRISHTI form. Zia
# reproduces the visual column gap and emits NO colon at all. An earlier parser
# required a separator and therefore silently dropped 17 of 22 fields on a page it
# had read at 99% confidence. Kept byte-faithful (leading spaces, the stray "."
# on the age line, the wrapped narrative) so the layout cannot regress.
ZIA_COLUMN_FORM = """                                DRISHTI FIR INTAKE FORM
                                  Synthetic end-to-end OCR test-DRISHTI-FIR-V1
  1. Police Station                      Udupi Town Police Station
  2. District                            Udupi
  3. FIR No                              OCR-E2E-20260905-001
  4. Date of Registration                25/09/2026
  5. Time of Registration                14:30
  6. Case Type                           Standard FIR
  7. Acts and Sections                   BNS 303(2)
  8. Occurrence From                    24/09/2026 20:15
  9. Occurrence To                       24/09/2026 20:30
  10. Information Received               25/09/2026 09:00
  11. Place of Occurrence                MG Road, Udupi, Karnataka
  12. Landmark                           Near City Bus Stand
  13. Beat                               Central Beat 1
  14. Complainant Name                   Arjun Rao
  15. Complainant Age                 .  34
  16. Complainant Phone                  9876543210
  17. Complainant Address                12 Market Road, Udupi, Karnataka
  18. Victim Name                        Arjun Rao
  19. Accused Name                       Unknown Person
  20. Witness Name                       Meera Nayak
  21. Brief Facts                        A blue motorcycle was reported missing from
                                         the parking area. This is synthetic test data
                                         and not a real complaint.
  22. Registering Officer                Lakshmi Prasad
  TEST FORM -DO NOT REGISTER AS A REAL FIR
"""


def test_column_aligned_recogniser_output_extracts_every_field():
    r = extract.extract_fir(ZIA_COLUMN_FORM, ocr_confidence=0.99)
    assert r.template_matched
    assert r.matched_label_count == len(extract.FIR_TEMPLATE_V1)
    found = {f.path for f in r.fields}
    missing = {s.path for s in extract.FIR_TEMPLATE_V1} - found
    assert not missing, f"column layout dropped: {sorted(missing)}"


def test_column_layout_values_are_the_full_cell_not_a_fragment():
    """The old separator split produced garbage like time '30' from '14:30' and a
    truncated reference from a hyphenated id."""
    r = extract.extract_fir(ZIA_COLUMN_FORM, ocr_confidence=0.99)
    payload = r.payload
    assert payload["registration"]["registration_time"] == "14:30"
    assert payload["source"]["external_source_id"] == "OCR-E2E-20260905-001"
    assert payload["incident"]["address"] == "MG Road, Udupi, Karnataka"
    assert payload["incident"]["beat"] == "Central Beat 1"
    assert payload["classification"]["acts_sections"] == [
        {"act_code": "BNS", "section_code": "303(2)"}]
    # A stray recogniser dot before a number must not defeat the int parser.
    party = next(p for p in r.parties if p["role_type"] == "complainant")
    assert party["attributes"]["age"] == 34
    assert party["attributes"]["phone"] == "9876543210"


def test_column_layout_narrative_stops_at_the_next_field():
    r = extract.extract_fir(ZIA_COLUMN_FORM, ocr_confidence=0.99)
    facts = r.payload["narrative"]["brief_facts"]
    assert "blue motorcycle" in facts
    assert "not a real complaint" in facts        # both wrapped lines absorbed
    assert "Registering Officer" not in facts     # next label ends the narrative
    assert "Lakshmi" not in facts


def test_all_four_party_roles_are_proposed_from_the_column_form():
    r = extract.extract_fir(ZIA_COLUMN_FORM, ocr_confidence=0.99)
    roles = {p["role_type"] for p in r.parties}
    assert {"complainant", "victim", "accused", "witness"} <= roles


def test_prose_mentioning_a_field_name_does_not_truncate_the_narrative():
    """A form line has a column gap or a separator; prose does not. Without that
    discriminator, 'Address of the shop...' inside a narrative would be read as an
    Address field and cut the statement short."""
    text = (
        "Brief Facts : The complainant returned at night.\n"
        "Address of the shop was visible from the road.\n"
        "District boundaries were not in question.\n"
    )
    r = extract.extract_fir(text, ocr_confidence=0.95)
    facts = r.payload["narrative"]["brief_facts"]
    assert "Address of the shop" in facts
    assert "District boundaries" in facts
    assert "address" not in r.payload["incident"]
    assert "district_id" not in r.payload["registration"]


def test_a_bare_label_with_no_value_is_not_a_field():
    """An unfilled line on the printed form must not produce an empty field."""
    r = extract.extract_fir("Landmark\nBeat   \n", ocr_confidence=0.95)
    assert r.matched_label_count == 0


def test_ambiguous_date_never_auto_fills_even_on_a_pristine_scan():
    """Confidence is scored so a perfect recogniser score cannot lift a DD/MM
    coin-flip into a pre-filled field."""
    r = extract.extract_fir("Date of Registration : 05/09/2026\n", ocr_confidence=1.0)
    f = next(f for f in r.fields if f.path == "registration.registration_date")
    assert f.auto_filled is False
    assert f.requires_review is True
    assert "registration_date" not in r.payload["registration"]


def test_boxed_character_cells_are_read_for_dates_times_and_stamps():
    """The printed form gives date/time fields character cells and tells the
    officer to write one digit per box, so a recogniser returns the digits with no
    separator. The parser must accept the layout its own form asks for."""
    r = extract.extract_fir(
        "Date of Registration        25092026\n"
        "Time of Registration        1430\n"
        "Occurrence From             24092026 2015\n",
        ocr_confidence=0.95)
    payload = r.payload
    assert payload["registration"]["registration_date"] == "2026-09-25"
    assert payload["registration"]["registration_time"] == "14:30"
    assert payload["incident"]["incident_from"] == "2026-09-24T20:15:00"


def test_boxed_cells_with_kannada_numerals_and_gaps():
    """Digits spaced one per box, in Kannada numerals."""
    kn = "\u0ce8\u0ce6 \u0ce6\u0ce9 \u0ce8\u0ce6\u0ce8\u0ce6"   # 20 03 2020
    r = extract.extract_fir(f"Date of Registration        {kn}\n", ocr_confidence=0.95)
    assert r.payload["registration"]["registration_date"] == "2020-03-20"


def test_boxed_cells_reject_an_impossible_value_instead_of_guessing():
    r = extract.extract_fir("Time of Registration        9999\n", ocr_confidence=0.95)
    f = next(f for f in r.fields if f.path == "registration.registration_time")
    assert f.value is None
    assert f.requires_review is True


def test_numbered_form_lines_are_matched_regardless_of_numbering_style():
    for prefix in ("1.", "12.", "3)", "7]", ""):
        r = extract.extract_fir(f"{prefix} District   Udupi\n", ocr_confidence=0.95)
        assert r.matched_label_count == 1, prefix


def test_specific_label_beats_a_shorter_alias():
    """'Date of Registration' and the bare alias 'Date' both match; the longer,
    more specific label must win so the value is not 'of Registration 25/09/2026'."""
    r = extract.extract_fir("Date of Registration        25/12/2026\n", ocr_confidence=0.95)
    f = next(f for f in r.fields if f.path == "registration.registration_date")
    assert f.raw_text == "25/12/2026"
    assert f.value == "2026-12-25"


def test_mangled_labels_still_match_fuzzily():
    r = parse("Pollce Statlon : Udupi Town PS\nDnte of Registration : 2026-01-09\n",
              confidence=0.9)
    assert field_by_path(r, "registration.station_id") is not None
    assert field_by_path(r, "registration.registration_date") is not None


def test_letter_digit_confusion_is_repaired_inside_section_numbers():
    """A mis-read "IPC 3O2" must become section 302, not sections "3O" and "2"."""
    r = extract.extract_fir("Acts and Sections : IPC 3O2\n", ocr_confidence=0.9)
    sections = field_by_path(r, "classification.acts_sections").value
    assert sections == [{"act_code": "IPC", "section_code": "302"}]


def test_ambiguous_date_is_flagged_and_not_auto_filled():
    """01/02/2026 could be 1 Feb or 2 Jan. The officer must settle it."""
    r = parse("Date of Registration : 01/02/2026\n", confidence=0.9)
    f = field_by_path(r, "registration.registration_date")
    assert f.requires_review is True
    assert f.auto_filled is False
    assert "ambiguous" in (f.note or "").lower()
    assert "registration_date" not in r.payload["registration"]


def test_unambiguous_date_is_auto_filled():
    r = parse("Date of Registration : 25/02/2026\n", confidence=0.9)
    f = field_by_path(r, "registration.registration_date")
    assert f.auto_filled is True
    assert r.payload["registration"]["registration_date"] == "2026-02-25"


def test_low_recogniser_confidence_drags_fields_below_the_fill_threshold():
    high = parse(FORM_EN, confidence=0.95)
    low = parse(FORM_EN, confidence=0.20)
    assert low.fields_needing_review > high.fields_needing_review
    assert any("confidence was low" in n for n in low.notes)


def test_non_form_text_is_reported_as_unrecognised():
    r = parse("just some prose with no labels at all whatsoever", confidence=0.95)
    assert r.template_matched is False
    assert r.matched_label_count == 0
    assert any("may not be a DRISHTI intake form" in n for n in r.notes)


def test_blank_and_placeholder_values_are_skipped():
    r = parse("Landmark : ---\nBeat : N/A\nDistrict : Udupi\n", confidence=0.9)
    assert "landmark" not in r.payload["incident"]
    assert "beat" not in r.payload["incident"]


def test_lookup_text_never_leaks_into_the_payload():
    """Reference values are resolved to ids or left blank. A raw string must never
    reach the payload, which has to stay valid against DraftPayload."""
    r = extract.extract_fir(FORM_EN, ocr_confidence=0.92)
    assert "registration.station_id" in r.lookup_texts
    assert "station_id" not in r.payload["registration"]
    # The payload must validate as a real draft payload at every stage.
    DraftPayload(**r.payload)


def test_resolved_payload_is_a_valid_draft_payload():
    DraftPayload(**parse(FORM_EN).payload)
    DraftPayload(**parse(FORM_KN, confidence=0.85).payload)


# ===========================================================================
# Lookup resolution
# ===========================================================================
def test_unique_station_match_resolves_and_derives_district():
    r = parse("Police Station : Mangaluru North PS\nTime of Registration : 09:15\n")
    assert r.payload["registration"]["station_id"] == 201
    assert r.payload["registration"]["district_id"] == 24
    assert any("derived from the police station" in n for n in r.notes)


def test_officer_rank_prefix_is_ignored_when_matching():
    r = parse(FORM_EN)
    assert r.payload["registration"]["registering_officer_id"] == 5001


def test_ambiguous_station_is_offered_as_candidates_not_guessed():
    r = parse("Police Station : Udupi PS\n")
    assert "station_id" not in r.payload["registration"]
    u = next(u for u in r.unresolved if u.path == "registration.station_id")
    names = {c["name"] for c in u.candidates}
    assert "Udupi Town Police Station" in names
    assert "Udupi Rural Police Station" in names
    assert "more than one" in u.reason


def test_unknown_station_is_left_blank_with_a_reason():
    r = parse("Police Station : Somewhere Nonexistent PS\n")
    assert "station_id" not in r.payload["registration"]
    u = next(u for u in r.unresolved if u.path == "registration.station_id")
    assert "No confident" in u.reason


def test_station_district_contradiction_clears_the_district():
    """The form names a district that is not the station's district. Trust neither."""
    r = parse("Police Station : Udupi Town PS\nDistrict : Mysuru\n")
    assert r.payload["registration"]["station_id"] == 101
    assert "district_id" not in r.payload["registration"]
    u = next(u for u in r.unresolved if u.path == "registration.district_id")
    assert "does not match" in u.reason


def test_kannada_district_resolves_through_the_alias_table():
    r = parse("\u0c9c\u0cbf\u0cb2\u0ccd\u0cb2\u0cc6 : \u0ca6\u0c95\u0ccd\u0cb7\u0cbf\u0ca3 "
              "\u0c95\u0ca8\u0ccd\u0ca8\u0ca1\n", confidence=0.9)
    assert r.payload["registration"]["district_id"] == 24


def test_unmatched_kannada_reference_is_not_transliterated_on_a_guess():
    r = parse("\u0c9c\u0cbf\u0cb2\u0ccd\u0cb2\u0cc6 : "
              "\u0c85\u0cb8\u0ccd\u0caa\u0cb7\u0ccd\u0c9f\u0cb5\u0cbe\u0ca6\n",
              confidence=0.9)
    assert "district_id" not in r.payload["registration"]
    u = next(u for u in r.unresolved if u.path == "registration.district_id")
    assert "Kannada script" in u.reason


def test_section_without_an_act_is_not_assigned_one_when_ambiguous():
    """379 exists under both IPC and BNS, so the Act must be chosen by a human."""
    r = extract.extract_fir("Acts and Sections : 379\n", ocr_confidence=0.95)
    f = field_by_path(r, "classification.acts_sections")
    assert f.requires_review is True
    assert f.value == [{"act_code": "", "section_code": "379"}]
    assert "No Act named" in (f.note or "")


# ===========================================================================
# Zia OCR adapter — fail closed, validate early
# ===========================================================================
def test_adapter_is_unavailable_by_default():
    engine = zia_ocr.get_zia_ocr()
    assert engine.available is False
    assert engine.provider == "unavailable"
    with pytest.raises(zia_ocr.ZiaOcrUnavailable):
        engine.recognize(b"bytes", filename="scan.jpg", content_type="image/jpeg")


def test_scan_lane_needs_both_the_feature_flag_and_the_catalyst_flag(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "intake_scan_ocr_enabled", False, raising=False)
    monkeypatch.setenv("DRISHTI_USE_CATALYST_ZIA_OCR", "true")
    assert zia_ocr.scan_ocr_enabled() is False          # product flag off

    monkeypatch.setattr(settings, "intake_scan_ocr_enabled", True, raising=False)
    monkeypatch.delenv("DRISHTI_USE_CATALYST_ZIA_OCR", raising=False)
    assert zia_ocr.scan_ocr_enabled() is False          # infra flag off

    monkeypatch.setenv("DRISHTI_USE_CATALYST_ZIA_OCR", "true")
    assert zia_ocr.scan_ocr_enabled() is True


def test_input_validation_rejects_oversize_and_unsupported_files():
    with pytest.raises(zia_ocr.ZiaOcrError):
        zia_ocr.validate_ocr_input(size_bytes=zia_ocr.ZIA_OCR_MAX_BYTES + 1,
                                   filename="scan.jpg", mime_type="image/jpeg")
    with pytest.raises(zia_ocr.ZiaOcrError):
        zia_ocr.validate_ocr_input(size_bytes=10, filename="scan.exe",
                                   mime_type="application/octet-stream")
    with pytest.raises(zia_ocr.ZiaOcrError):
        zia_ocr.validate_ocr_input(size_bytes=0, filename="scan.jpg",
                                   mime_type="image/jpeg")
    # A correct extension is enough when a camera capture sends a blank MIME.
    zia_ocr.validate_ocr_input(size_bytes=1024, filename="page.pdf", mime_type="")


def test_language_codes_map_to_zia_and_unknown_codes_are_dropped():
    assert zia_ocr._zia_language_codes(["en", "kn"]) == ["eng", "kan"]
    # Unknown codes are dropped rather than forwarded, so Zia auto-detects
    # instead of rejecting the whole request.
    assert zia_ocr._zia_language_codes(["en", "klingon"]) == ["eng"]
    assert zia_ocr._zia_language_codes([]) == []


def test_script_detection_matches_the_client_helper():
    assert zia_ocr.detect_script("plain english") == "en"
    assert zia_ocr.detect_script("\u0c95\u0ca8\u0ccd\u0ca8\u0ca1") == "kn"
    assert zia_ocr.detect_script("FIR \u0cb8\u0c82\u0c96\u0ccd\u0caf\u0cc6 12") == "mixed"


def test_zia_document_confidence_is_normalised_to_zero_one():
    class _FakeClient:
        def zia_ocr(self, content, **kwargs):
            return {"confidence": 79.7, "text": "District : Udupi"}

    engine = zia_ocr.CatalystZiaOcr(client=_FakeClient())
    result = engine.recognize(b"x" * 64, filename="scan.jpg", content_type="image/jpeg")
    assert 0.79 < (result.confidence or 0) < 0.80
    assert result.detected_language == "en"
    assert result.provider == "catalyst-zia-ocr"


def test_zia_rest_uses_one_language_hint_or_auto_detects_bilingual_pages():
    assert catalyst_rest._ocr_form_data("OCR", ["eng"]) == {
        "model_type": "OCR", "language": "eng"}
    assert catalyst_rest._ocr_form_data("OCR", ["eng", "kan"]) == {
        "model_type": "OCR"}


def test_adapter_surfaces_failures_without_leaking_the_response_body():
    class _BoomClient:
        def zia_ocr(self, content, **kwargs):
            raise RuntimeError("secret-token-abc123 leaked in body")

    engine = zia_ocr.CatalystZiaOcr(client=_BoomClient())
    with pytest.raises(zia_ocr.ZiaOcrError) as exc:
        engine.recognize(b"x" * 64, filename="scan.jpg", content_type="image/jpeg")
    assert "secret-token-abc123" not in str(exc.value)
    assert "RuntimeError" in str(exc.value)


# ===========================================================================
# Governance invariants
# ===========================================================================
def test_capability_status_is_honest_about_review_and_evidence_scope():
    status = zia_ocr.ocr_capability_status()
    # Human review is structural, not a toggle.
    assert status["requires_human_review"] is True
    assert status["creates_case_directly"] is False
    assert status["manual_entry_always_available"] is True
    # The whole point: intake prefill must not imply evidence extraction.
    assert status["evidence_extraction_enabled"] is False
    assert "kn" in status["supported_languages"]
    assert status["handwriting_caveat"]


def test_enabling_the_scan_lane_does_not_enable_evidence_extraction(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "intake_scan_ocr_enabled", True, raising=False)
    monkeypatch.setenv("DRISHTI_USE_CATALYST_ZIA_OCR", "true")
    assert zia_ocr.scan_ocr_enabled() is True
    # The separate flag is untouched — that separation is the safety argument.
    assert get_settings().evidence_extraction_enabled is False
    assert zia_ocr.ocr_capability_status()["evidence_extraction_enabled"] is False


def test_evidence_extraction_stays_disabled_by_default():
    assert get_settings().evidence_extraction_enabled is False


# ===========================================================================
# API contract (no DB)
# ===========================================================================
@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_capability_endpoint_reports_the_truth(client):
    r = client.get("/intake/scan/capability")
    assert r.status_code == 200
    body = r.json()
    assert body["requires_human_review"] is True
    assert body["creates_case_directly"] is False
    assert body["evidence_extraction_enabled"] is False
    assert body["max_bytes"] == zia_ocr.ZIA_OCR_MAX_BYTES
    if not body["scan_ocr_enabled"]:
        assert body["platform_limitation"]


def test_template_endpoint_serves_the_printable_form(client):
    r = client.get("/intake/scan/template")
    assert r.status_code == 200
    body = r.json()
    assert body["template_code"] == extract.TEMPLATE_CODE
    assert len(body["lines"]) == len(extract.FIR_TEMPLATE_V1)
    assert body["guidance_en"] and body["guidance_kn"]
    assert "reviewed by the registering officer" in body["notice_en"]
    station = next(l for l in body["lines"] if l["field"] == "registration.station_id")
    assert station["label_kn"]           # bilingual labels are printed


def test_disabled_lane_refuses_with_an_actionable_message():
    """A disabled feature must be an actionable refusal, never a crash.

    Asserted at the service layer: the engine check happens before any database
    or environment gate, so this is deterministic and tests the refusal itself
    rather than whichever ambient gate happens to trip first over HTTP.
    """
    if zia_ocr.scan_ocr_enabled():
        pytest.skip("OCR lane is enabled in this environment")

    with pytest.raises(IntakeConflict) as exc:
        # conn is never touched: the availability check precedes all DB work.
        scan_service._run_scan_ocr(None, b"x" * 128, filename="scan.jpg",
                                   content_type="image/jpeg")
    message = str(exc.value).lower()
    assert "not enabled" in message
    # The refusal has to tell the officer what to do instead.
    assert "manually" in message


def test_ocr_endpoint_never_succeeds_while_the_feature_is_off(client):
    """Over HTTP the request must be refused, never accepted.

    The exact status depends on which gate the environment trips first (feature
    off, write guard, or app readiness), so this asserts the invariant that
    matters: no success, and no unhandled server error.
    """
    if zia_ocr.scan_ocr_enabled():
        pytest.skip("OCR lane is enabled in this environment")
    r = client.post("/intake/scan/ocr",
                    files={"file": ("scan.jpg", b"x" * 128, "image/jpeg")})
    assert r.status_code >= 400
    assert r.status_code != 500
    assert r.status_code in (409, 403, 503)


def test_scan_endpoints_keep_the_shared_intake_write_guard():
    """Guard against the previous test accidentally documenting away a control:
    the scan write routes must still declare the localhost + synthetic-DB guard."""
    import inspect

    from app.intake import router as intake_router

    for fn in (intake_router.scan_ocr, intake_router.apply_scan,
               intake_router.discard_scan):
        declared = set()
        for param in inspect.signature(fn).parameters.values():
            dependency = getattr(param.default, "dependency", None)
            if dependency is not None:
                declared.add(dependency)
        assert guards.require_write_allowed in declared, fn.__name__
        assert guards.require_intake_write in declared, fn.__name__


def test_ocr_endpoint_rejects_an_oversize_upload(client):
    r = client.post(
        "/intake/scan/ocr",
        files={"file": ("scan.jpg", b"x" * (zia_ocr.ZIA_OCR_MAX_BYTES + 10), "image/jpeg")})
    assert r.status_code == 413
    assert "MB" in str(r.json().get("detail", ""))


def test_scan_upload_is_exempt_from_the_small_json_body_cap():
    """A photographed page is far larger than the global JSON cap, so the scan
    endpoint carries its own bounded limit. Without this the feature could never
    receive a real photo."""
    from app.hardening import BodySizeLimitMiddleware

    mw = BodySizeLimitMiddleware(app)
    scan_limit = mw._limit_for("/intake/scan/ocr")
    other_limit = mw._limit_for("/intake/drafts")

    assert scan_limit == zia_ocr.ZIA_OCR_MAX_BYTES
    assert other_limit == get_settings().max_request_bytes
    # The exemption must be a real increase, and still bounded.
    assert scan_limit > other_limit
    assert scan_limit == 20 * 1024 * 1024


def test_body_cap_exemption_does_not_leak_to_neighbouring_paths():
    """Exact-path matching, so a future /intake/scan/* route cannot silently
    inherit a 20 MB body allowance."""
    from app.hardening import BodySizeLimitMiddleware

    mw = BodySizeLimitMiddleware(app)
    small = get_settings().max_request_bytes
    for path in ("/intake/scan", "/intake/scan/ocr/extra", "/intake/scan/queue",
                 "/intake/scan/SC-123/apply"):
        assert mw._limit_for(path) == small, path


def test_placeholder_markers_are_treated_as_unfilled_lines():
    """Officers write N/A, Nil or a dash on lines that do not apply; those must
    never become literal values in case data."""
    for marker in ("N/A", "-", "---", "Nil", "not known", "___"):
        r = extract.extract_fir(f"Landmark : {marker}\n", ocr_confidence=0.95)
        assert "landmark" not in r.payload["incident"], marker


def test_scan_routes_are_registered_in_a_matchable_order():
    """Literal paths must be declared before /scan/{scan_key} or they would be
    swallowed by the parameterised route."""
    paths = [getattr(r, "path", "") for r in app.routes]
    for literal in ("/intake/scan/capability", "/intake/scan/template", "/intake/scan/queue"):
        assert literal in paths
        assert paths.index(literal) < paths.index("/intake/scan/{scan_key}")


# ===========================================================================
# Integration — scan -> propose -> correct -> draft (rolled back)
# ===========================================================================
class FakeOcrEngine:
    """Stands in for Catalyst Zia OCR so the pipeline is testable offline."""

    provider = "fake-zia-ocr"
    available = True

    def __init__(self, text: str, confidence: float = 0.9):
        self._text = text
        self._confidence = confidence

    def recognize(self, content, *, filename="", content_type="", languages=None,
                  model_type="OCR"):
        return zia_ocr.OcrResult(
            text=self._text, confidence=self._confidence,
            detected_language=zia_ocr.detect_script(self._text),
            provider=self.provider, requested_languages=tuple(languages or ()),
            model_type=model_type)


@pytest.fixture
def fake_ocr(monkeypatch):
    """Install a fake engine + skip byte retention (no object store in tests)."""
    def _install(text: str, confidence: float = 0.9):
        monkeypatch.setattr(scan_service.ocr_mod, "get_zia_ocr",
                            lambda: FakeOcrEngine(text, confidence))
        monkeypatch.setattr(scan_service, "_store_scan_bytes",
                            lambda *a, **k: (None, None))
    return _install


@requires_db
def test_scan_creates_a_reviewable_proposal_and_no_case(rw_rollback, fake_ocr):
    fake_ocr(FORM_EN)
    scan = scan_service._run_scan_ocr(
        rw_rollback, b"fake-jpeg-bytes", filename="fir.jpg",
        content_type="image/jpeg", actor="tester", reference=REFERENCE)

    assert scan.scan_key.startswith("SC-")
    assert scan.status == "extracted"
    assert scan.review_state == "pending_review"
    # Nothing has been applied anywhere yet.
    assert scan.draft_key is None
    assert scan.sha256 and len(scan.sha256) == 64
    assert scan.fields, "the proposal should carry fields"
    assert scan.template_matched


@requires_db
def test_applying_a_scan_creates_a_draft_that_still_needs_approval(rw_rollback, fake_ocr):
    fake_ocr(FORM_EN)
    scan = scan_service._run_scan_ocr(
        rw_rollback, b"fake-jpeg-bytes", filename="fir.jpg",
        content_type="image/jpeg", actor="tester", reference=REFERENCE)

    result = scan_service._apply_scan_to_draft(
        rw_rollback, scan.scan_key, ScanApplyRequest(actor="tester"))

    draft = result.draft
    assert draft.draft_key.startswith("DR-")
    # THE core invariant: reading a form never registers a case.
    assert draft.case_master_id is None
    assert draft.crime_no is None
    assert draft.status == "draft"
    # Provenance is recorded truthfully as a scanned form, not a typed one.
    assert draft.payload.source.source_system_code == "FIR_SCAN_OCR"
    assert result.fields_from_scan > 0


@requires_db
def test_officer_corrections_are_recorded_as_edited_provenance(rw_rollback, fake_ocr):
    fake_ocr(FORM_EN)
    scan = scan_service._run_scan_ocr(
        rw_rollback, b"fake-jpeg-bytes", filename="fir.jpg",
        content_type="image/jpeg", actor="tester", reference=REFERENCE)

    # The officer corrects the landmark the recogniser read.
    corrected = scan.payload.model_copy(deep=True)
    corrected.incident.landmark = "Corrected by the officer"

    result = scan_service._apply_scan_to_draft(
        rw_rollback, scan.scan_key,
        ScanApplyRequest(payload=corrected, actor="tester",
                         edited_fields=["incident.landmark"]))

    assert result.fields_edited >= 1
    assert result.draft.payload.incident.landmark == "Corrected by the officer"

    rows = _provenance_rows(rw_rollback, scan.scan_key)
    landmark = rows["incident.landmark"]
    assert landmark["was_edited"] is True
    assert landmark["origin"] == "ocr_edited"
    # What the machine proposed is retained alongside what was accepted.
    assert landmark["proposed"] == "Opposite Sri Krishna Temple"
    assert landmark["accepted"] == "Corrected by the officer"


def _provenance_rows(conn, scan_key: str) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            'SELECT f."FieldPath", f."ProposedValue", f."AcceptedValue", f."Origin",'
            ' f."WasEdited", f."RequiresReview" '
            'FROM "IntakeScanField" f JOIN "IntakeScan" s '
            '  ON s."IntakeScanID" = f."IntakeScanID" '
            'WHERE s."ScanKey" = %s', (scan_key,))
        return {
            r[0]: {"proposed": r[1], "accepted": r[2], "origin": r[3],
                   "was_edited": bool(r[4]), "requires_review": bool(r[5])}
            for r in cur.fetchall()
        }


@requires_db
def test_a_scan_cannot_be_applied_twice(rw_rollback, fake_ocr):
    fake_ocr(FORM_EN)
    scan = scan_service._run_scan_ocr(
        rw_rollback, b"fake-jpeg-bytes", filename="fir.jpg",
        content_type="image/jpeg", actor="tester", reference=REFERENCE)
    scan_service._apply_scan_to_draft(
        rw_rollback, scan.scan_key, ScanApplyRequest(actor="tester"))

    with pytest.raises(IntakeConflict, match="already applied"):
        scan_service._apply_scan_to_draft(
            rw_rollback, scan.scan_key, ScanApplyRequest(actor="tester"))


@requires_db
def test_a_discarded_scan_cannot_become_a_draft(rw_rollback, fake_ocr):
    fake_ocr(FORM_EN)
    scan = scan_service._run_scan_ocr(
        rw_rollback, b"fake-jpeg-bytes", filename="fir.jpg",
        content_type="image/jpeg", actor="tester", reference=REFERENCE)

    discarded = scan_service._discard_scan(rw_rollback, scan.scan_key, "tester")
    assert discarded.status == "discarded"

    with pytest.raises(IntakeConflict, match="discarded"):
        scan_service._apply_scan_to_draft(
            rw_rollback, scan.scan_key, ScanApplyRequest(actor="tester"))


@requires_db
def test_proposed_party_is_dropped_when_the_case_kind_forbids_the_role(rw_rollback, fake_ocr):
    """A Missing Person case must not silently acquire an accused just because the
    scanned page had an "Accused" line on it."""
    fake_ocr(FORM_EN + "\nAccused Name : Someone Named\n")
    scan = scan_service._run_scan_ocr(
        rw_rollback, b"fake-jpeg-bytes", filename="fir.jpg",
        content_type="image/jpeg", actor="tester", reference=REFERENCE)
    assert any(p.role_type == "accused" for p in scan.parties)

    result = scan_service._apply_scan_to_draft(
        rw_rollback, scan.scan_key,
        ScanApplyRequest(case_kind="missing_person", actor="tester"))

    roles = {p.role_type for p in result.draft.parties}
    assert "accused" not in roles


@requires_db
def test_empty_recognised_text_is_refused_before_anything_is_stored(rw_rollback, fake_ocr):
    fake_ocr("   \n  \n")
    with pytest.raises(IntakeValidationError, match="No text was recognised"):
        scan_service._run_scan_ocr(
            rw_rollback, b"fake-jpeg-bytes", filename="fir.jpg",
            content_type="image/jpeg", actor="tester", reference=REFERENCE)


@requires_db
def test_the_scan_records_its_source_page_hash_for_traceability(rw_rollback, fake_ocr):
    import hashlib

    content = b"a-specific-page-of-bytes"
    fake_ocr(FORM_EN)
    scan = scan_service._run_scan_ocr(
        rw_rollback, content, filename="fir.jpg", content_type="image/jpeg",
        actor="tester", reference=REFERENCE)
    # An approved FIR must always be traceable to the exact page it was read from.
    assert scan.sha256 == hashlib.sha256(content).hexdigest()


@requires_db
def test_idempotent_rerun_returns_the_same_scan(rw_rollback, fake_ocr):
    fake_ocr(FORM_EN)
    first = scan_service._run_scan_ocr(
        rw_rollback, b"fake-jpeg-bytes", filename="fir.jpg",
        content_type="image/jpeg", actor="tester", reference=REFERENCE,
        idempotency_key="scan-key-1")
    second = scan_service._run_scan_ocr(
        rw_rollback, b"fake-jpeg-bytes", filename="fir.jpg",
        content_type="image/jpeg", actor="tester", reference=REFERENCE,
        idempotency_key="scan-key-1")
    assert first.scan_key == second.scan_key
