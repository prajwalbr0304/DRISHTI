"""Deterministic, source-qualified public-interest case records.

This module is intentionally separate from the synthetic scenario generator. It
adds a small number of manually researched public-source records *after* graph,
feature, label, and quality-scenario generation, so real named people never enter
synthetic analytics or consume the shared RNG.

The Renukaswamy record is not a finding of guilt. It remains pending trial. Every
assertion is either a procedural fact or explicitly framed as an allegation, and
all remote documents/media remain metadata-only external references.
"""
from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional

from . import reference as ref
from . import scenario_registry as SR
from . import v2common as C
from .db import Arr, Json

SOURCE_CUTOFF = "2026-08-27"
OFFICIAL_CRIME_REFERENCE = "Crime No.250/2024"
TRIAL_CASE_REFERENCE = "S.C.No.1319/2024"
COMMITTAL_CASE_REFERENCE = "C.C.No.28777/2024"
CASE_LOCATION_LAT = 12.9160908
CASE_LOCATION_LON = 77.5141119

_MANIFEST_PATH = (
    Path(__file__).resolve().parents[1]
    / "research"
    / "renukaswamy-case-evidence"
    / "evidence_manifest.csv"
)
_REQUIRED_MANIFEST_COLUMNS = {
    "id", "title", "category", "media_type", "format", "publisher", "date",
    "source_url", "asset_url", "http_status", "content_type", "size_bytes",
    "authenticity", "graphic", "presentation_use", "rights_and_handling",
    "notes", "last_checked",
}
_REQUIRED_SOURCE_IDS = {
    "DOC-001", "DOC-002", "DOC-003", "DOC-004", "DOC-005",
    "VID-001", "VID-002", "IMG-001", "SRC-003",
    "NPA-001", "NPA-002", "NPA-003", "NPA-004", "NPA-005", "NPA-006",
    "NPA-007", "SRC-004", "SRC-005", "GEO-001",
}
_CASE_SUMMARY_SOURCE_IDS = (
    "DOC-001", "DOC-002", "DOC-003", "DOC-004", "DOC-005",
    "SRC-004", "SRC-005", "GEO-001",
)
_MERGED_REFERENCE_IDS = {"VID-002", "IMG-001"}
_NEVER_EVIDENCE_IDS = {
    "SRC-003", "GEO-001", "NPA-001", "NPA-002", "NPA-003", "NPA-004",
    "NPA-005", "NPA-006", "NPA-007",
}


@dataclass(frozen=True)
class PersonSpec:
    key: str
    display_name: str
    gender_id: int
    aliases: tuple[str, ...] = ()
    sequence_no: Optional[int] = None


ACCUSED: tuple[PersonSpec, ...] = (
    PersonSpec("A01", "Pavitra Gowda", ref.GENDER_FEMALE, sequence_no=1),
    PersonSpec("A02", "Darshan S. Thoogudeepa", ref.GENDER_MALE,
               ("D. Boss", "Darshan Thoogudeepa"), 2),
    PersonSpec("A03", "Puttaswamy", ref.GENDER_MALE, ("Pavan K.",), 3),
    PersonSpec("A04", "Raghavendra N.", ref.GENDER_MALE, sequence_no=4),
    PersonSpec("A05", "Nandeesh", ref.GENDER_MALE, sequence_no=5),
    PersonSpec("A06", "Jagadeesh", ref.GENDER_MALE, ("Jagga",), 6),
    PersonSpec("A07", "Anu Kumar", ref.GENDER_MALE, ("Anu",), 7),
    PersonSpec("A08", "Ravi Shankar", ref.GENDER_MALE, ("Ravi",), 8),
    PersonSpec("A09", "Dhanraj", ref.GENDER_MALE, ("Raju", "Dhanaraju D."), 9),
    PersonSpec("A10", "V. Vinay", ref.GENDER_MALE, sequence_no=10),
    PersonSpec("A11", "Nagaraju R.", ref.GENDER_MALE, sequence_no=11),
    PersonSpec("A12", "Lakshman M.", ref.GENDER_MALE, sequence_no=12),
    PersonSpec("A13", "Deepak Kumar M.", ref.GENDER_MALE, ("Deepak",), 13),
    PersonSpec("A14", "Pradoosh S. Rao", ref.GENDER_MALE,
               ("Pradoosh", "Pradosh S. Rao", "Pradosh Rao"), 14),
    PersonSpec("A15", "Karthik", ref.GENDER_MALE, ("Kappe",), 15),
    PersonSpec("A16", "Keshavamurthy", ref.GENDER_MALE, sequence_no=16),
    PersonSpec("A17", "Nikhil Nayak", ref.GENDER_MALE, sequence_no=17),
)
VICTIM = PersonSpec("V01", "Renukaswamy", ref.GENDER_MALE)
COMPLAINANT = PersonSpec("C01", "Keval Ram Dorji", ref.GENDER_MALE)
WITNESS = PersonSpec("W01", "Rathnaprabha", ref.GENDER_FEMALE)

CHARGED_SECTIONS = (
    "120B", "364", "384", "355", "302", "201", "143", "147", "148",
    "149", "34",
)

# (person key, date, type id, source-qualified display label)
# Type 1=arrest and 2=surrender in the legacy fixture. A6/A7 are left NULL
# because public records use conflicting descriptions.
ARRESTS = (
    ("A04", "2024-06-10", 2, "A4 surrender reported"),
    ("A15", "2024-06-10", 2, "A15 surrender reported"),
    ("A16", "2024-06-10", 2, "A16 surrender reported"),
    ("A17", "2024-06-10", 2, "A17 surrender reported"),
    ("A01", "2024-06-11", 1, "A1 arrest reported"),
    ("A02", "2024-06-11", 1, "A2 arrest reported"),
    ("A03", "2024-06-11", 1, "A3 arrest reported"),
    ("A05", "2024-06-11", 1, "A5 arrest reported"),
    ("A10", "2024-06-11", 1, "A10 arrest reported"),
    ("A11", "2024-06-11", 1, "A11 arrest reported"),
    ("A12", "2024-06-11", 1, "A12 arrest reported"),
    ("A13", "2024-06-11", 1, "A13 arrest reported"),
    ("A14", "2024-06-11", 1, "A14 arrest reported"),
    ("A08", "2024-06-13", 2, "A8 surrender reported"),
    ("A06", "2024-06-14", None, "A6 custody reported; sources differ on arrest/surrender"),
    ("A07", "2024-06-14", None, "A7 custody reported; sources differ on arrest/surrender"),
    ("A09", "2024-06-15", 1, "A9 arrest reported"),
)

# External-reference items may point at a person only when that relationship is
# apparent from the publisher/court description. The link means "mentions", not
# that the item proves any allegation.
_EVIDENCE_ENTITY_KEYS: dict[str, tuple[str, ...]] = {
    "DOC-005": tuple(p.key for p in ACCUSED) + (WITNESS.key,),
    "IMG-002": ("A02",),
    "IMG-003": ("A02",),
    "IMG-004": ("A02",),
    "IMG-006": ("A01",),
    "IMG-007": ("A02",),
    "IMG-008": ("A02",),
    "IMG-009": ("A02",),
    "IMG-010": ("W01",),
    "IMG-011": ("A02", "V01"),
    "SRC-004": ("A02", "A14"),
    "SRC-005": ("A02", "A14"),
}


def _manifest_rows() -> tuple[dict[str, str], ...]:
    """Read and strictly validate the checked-in public-source inventory."""
    if not _MANIFEST_PATH.is_file():
        raise RuntimeError(f"Curated source manifest is missing: {_MANIFEST_PATH}")
    with _MANIFEST_PATH.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        fields = set(reader.fieldnames or ())
        if fields != _REQUIRED_MANIFEST_COLUMNS:
            missing = sorted(_REQUIRED_MANIFEST_COLUMNS - fields)
            extra = sorted(fields - _REQUIRED_MANIFEST_COLUMNS)
            raise RuntimeError(
                f"Curated source manifest columns changed (missing={missing}, extra={extra})"
            )
        rows = tuple({k: (v or "").strip() for k, v in row.items()} for row in reader)

    by_id = {row["id"]: row for row in rows}
    if len(by_id) != len(rows):
        raise RuntimeError("Curated source manifest contains duplicate ids")
    missing_ids = sorted(_REQUIRED_SOURCE_IDS - set(by_id))
    if missing_ids:
        raise RuntimeError(f"Curated source manifest is missing required records: {missing_ids}")
    for row in rows:
        if not row["id"] or not row["title"] or not row["category"]:
            raise RuntimeError(f"Curated source manifest has an incomplete row: {row!r}")
        if row["last_checked"] != "27-08-2026":
            raise RuntimeError(
                f"Curated source {row['id']} is outside the fixed {SOURCE_CUTOFF} check"
            )
        if row["graphic"].lower() not in {"no", "yes", "unknown", "private", "likely graphic/private", "may contain private data", "may contain graphic/private data"}:
            raise RuntimeError(f"Curated source {row['id']} has an unreviewed graphic flag")
    return rows


def _source_system_code(row: dict[str, str]) -> str:
    category = row["category"]
    if category.startswith("A-"):
        return "PUBLIC_JUDICIAL_RECORD"
    if category.startswith("F-"):
        return "PUBLIC_GEODATA_REFERENCE"
    if category.startswith(("D-", "E-")):
        return "PUBLIC_AVAILABILITY_CATALOG"
    return "PUBLIC_PUBLISHER_REFERENCE"


def _record_kind(row: dict[str, str]) -> str:
    category = row["category"]
    if category.startswith("A-"):
        return "judicial_record"
    if category.startswith("F-"):
        return "geodata_reference"
    if category.startswith("D-"):
        return "nonpublic_availability"
    if category.startswith("E-"):
        return "excluded_reference"
    return "publisher_reference"


def _source_payload(row: dict[str, str]) -> dict:
    payload = {k: (v if v != "" else None) for k, v in row.items()}
    payload.update({
        "record_origin": "public_source_curated",
        "is_synthetic": False,
        "source_cutoff": SOURCE_CUTOFF,
        "official_crime_reference": OFFICIAL_CRIME_REFERENCE,
        "availability_only": row["id"].startswith("NPA-"),
        "excluded_from_evidence": row["id"] in _NEVER_EVIDENCE_IDS,
    })
    return payload


def _hash_payload(payload: dict) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _emit_sources(world: C.World) -> tuple[dict[str, int], dict[str, dict[str, str]]]:
    source_systems = (
        ("PUBLIC_JUDICIAL_RECORD", "Public judicial record references",
         "Court texts linked for attribution; mirrors are not certified copies."),
        ("PUBLIC_PUBLISHER_REFERENCE", "Public publisher references",
         "Copyrighted publisher pages/assets referenced by URL only."),
        ("PUBLIC_GEODATA_REFERENCE", "Public geodata references",
         "Open geodata used only for approximate locality display."),
        ("PUBLIC_AVAILABILITY_CATALOG", "Nonpublic/excluded material inventory",
         "Availability and exclusion metadata; no native evidence is represented."),
    )
    for code, name, description in source_systems:
        if code in world.source_system:
            raise RuntimeError(f"Curated source system already exists: {code}")
        source_system_id = world.next_id("SourceSystem")
        world.add("SourceSystem", (
            source_system_id, code, name, "external_reference", description, False,
        ))
        world.source_system[code] = source_system_id

    rows = _manifest_rows()
    source_record_ids: dict[str, int] = {}
    manifest_by_id: dict[str, dict[str, str]] = {}
    for row in rows:
        manifest_id = row["id"]
        payload = _source_payload(row)
        source_record_id = world.next_id("SourceRecord")
        world.add("SourceRecord", (
            source_record_id,
            world.source_system[_source_system_code(row)],
            f"PUBSRC-RSW-{manifest_id}",
            _record_kind(row),
            Json(payload),
            _hash_payload(payload),
            1,
            None,
            "committed",
            False,
        ))
        source_record_ids[manifest_id] = source_record_id
        manifest_by_id[manifest_id] = row
    return source_record_ids, manifest_by_id


def _proxy_references(ctx) -> dict:
    district_index = next(
        (i for i, d in enumerate(ctx.districts) if d["name"] == "Bengaluru City"),
        None,
    )
    if district_index is None:
        raise RuntimeError("Bengaluru City reference district is unavailable")
    district = ctx.districts[district_index]
    station_indexes = ctx.stations_by_district.get(district_index) or []
    if not station_indexes:
        raise RuntimeError("No deterministic proxy station exists in Bengaluru City")
    station_index = min(station_indexes, key=lambda i: int(ctx.stations[i]["id"]))
    station = ctx.stations[station_index]
    unit_id = int(station["id"])
    officers = ctx.officers_by_station.get(unit_id) or []
    courts = ctx.courts_by_district.get(district_index) or []
    if not officers or not courts:
        raise RuntimeError("No deterministic proxy officer/court exists in Bengaluru City")
    murder_profile = next((p for p in ctx.crime_profiles if p["sub"] == "Murder"), None)
    if murder_profile is None:
        raise RuntimeError("Murder taxonomy profile is unavailable")
    return {
        "district_index": district_index,
        "district_id": int(district["id"]),
        "unit_id": unit_id,
        "officer_id": int(min(officers)),
        "court_id": int(min(courts)),
        "murder_profile": murder_profile,
    }


def _public_person_ref(key: str) -> str:
    return f"PUBSRC-RSW-P-{key}"


def _public_entity_ref(key: str) -> str:
    return f"PUBSRC-RSW-ENT-{key}"


def _mint_person(world: C.World, spec: PersonSpec, source_record_id: int) -> tuple[int, int]:
    attributes = {
        "record_origin": "public_source_curated",
        "is_synthetic": False,
        "public_case_reference": OFFICIAL_CRIME_REFERENCE,
        "stable_case_key": spec.key,
        "aliases": list(spec.aliases),
        "source_record_id": source_record_id,
        "privacy": "public_name_only_no_address_contact_or_identifier",
    }
    canonical_person_id = world.next_id("CanonicalPerson")
    world.add("CanonicalPerson", (
        canonical_person_id,
        _public_person_ref(spec.key),
        spec.display_name,
        False,
        spec.gender_id,
        None,
        False,
        "canonical",
        None,
        Json(attributes),
        False,
    ))
    canonical_entity_id = world.next_id("CanonicalEntity")
    world.add("CanonicalEntity", (
        canonical_entity_id,
        "person",
        canonical_person_id,
        None,
        _public_entity_ref(spec.key),
        spec.display_name,
        Json({
            "record_origin": "public_source_curated",
            "is_synthetic": False,
            "excluded_from_derived_analytics": True,
        }),
        False,
    ))
    world.person_entity[canonical_person_id] = canonical_entity_id
    world.person_gender[canonical_person_id] = spec.gender_id
    world.person_label[canonical_person_id] = spec.display_name
    for alias in spec.aliases:
        world.add("PersonAlias", (
            canonical_person_id, alias, "aka", source_record_id, False,
        ))
    return canonical_person_id, canonical_entity_id


def _event(
    world: C.World,
    *,
    case_id: int,
    sequence_no: int,
    event_type: str,
    event_category: str,
    occurred_at: Optional[str],
    from_status: Optional[str],
    to_status: Optional[str],
    display_label: str,
    source_ids: Iterable[str],
    source_record_ids: dict[str, int],
    payload: Optional[dict] = None,
) -> None:
    ids = tuple(source_ids)
    details = dict(payload or {})
    details.update({
        "display_label": display_label,
        "source_ids": list(ids),
        "allegation_not_finding": bool(details.get("alleged")),
        "record_origin": "public_source_curated",
        "is_synthetic": False,
    })
    provenance = {
        "source_record_ids": [source_record_ids[x] for x in ids],
        "source_ids": list(ids),
        "source_cutoff": SOURCE_CUTOFF,
        "public_source_reference": True,
    }
    world.add("CaseEvent", (
        case_id, event_type, event_category, sequence_no, occurred_at,
        from_status, to_status, Json(details), "public_source_curator", Json(provenance),
    ))


def _court_event(
    world: C.World,
    *,
    case_id: int,
    court_id: int,
    event_type: str,
    occurred_at: Optional[str],
    outcome: str,
    source_ids: Iterable[str],
    source_record_ids: dict[str, int],
    detail: Optional[dict] = None,
) -> int:
    ids = tuple(source_ids)
    court_event_id = world.next_id("CourtEvent")
    body = dict(detail or {})
    body.update({
        "source_ids": list(ids),
        "source_record_ids": [source_record_ids[x] for x in ids],
        "source_cutoff": SOURCE_CUTOFF,
        "record_origin": "public_source_curated",
        "is_synthetic": False,
        "reference_mapping": "proxy",
        "public_trial_court_label": "City Civil and Sessions Court, Bengaluru",
    })
    world.add("CourtEvent", (
        court_event_id, case_id, court_id, event_type, None, occurred_at,
        outcome, Json(body),
    ))
    return court_event_id


def _evidence_category(row: dict[str, str]) -> str:
    manifest_id = row["id"]
    category = row["category"]
    if category.startswith("A-"):
        return "public_judicial_reference"
    if category.startswith("C-"):
        return "media_published_extract"
    if manifest_id in {"SRC-004", "SRC-005"}:
        return "procedural_reporting_not_case_evidence"
    if manifest_id.startswith("SRC-"):
        return "source_only_context_not_case_evidence"
    return "presentation_context_not_case_evidence"


def _evidence_rows(
    world: C.World,
    *,
    case_id: int,
    source_record_ids: dict[str, int],
    manifest_by_id: dict[str, dict[str, str]],
    entity_ids_by_key: dict[str, int],
) -> None:
    alternate_video = manifest_by_id["VID-002"]
    poster = manifest_by_id["IMG-001"]

    for manifest_id, row in manifest_by_id.items():
        if manifest_id in _MERGED_REFERENCE_IDS or manifest_id in _NEVER_EVIDENCE_IDS:
            continue
        if not row["source_url"]:
            continue
        if row["graphic"].lower() != "no":
            raise RuntimeError(f"Refusing to emit graphic/unreviewed reference {manifest_id}")
        if not row["category"].startswith(("A-", "B-", "C-")):
            continue

        category = _evidence_category(row)
        not_case_evidence = "not_case_evidence" in category
        tags = [
            "public_source", "non_synthetic", "external_reference",
            "pending_trial", "allegation_not_finding",
        ]
        tags.append("not_case_evidence" if not_case_evidence else "source_qualified_reference")
        if row["category"].startswith("A-"):
            tags.append("judicial_record")
        elif row["category"].startswith("C-"):
            tags.append("media_published_extract_not_original")
        else:
            tags.append("publisher_context")

        metadata = {
            "manual": True,
            "metadata_only": True,
            "file_backed": False,
            "record_origin": "public_source_curated",
            "is_synthetic": False,
            "public_source_id": manifest_id,
            "source_cutoff": SOURCE_CUTOFF,
            "external_reference_url": row["source_url"],
            "remote_asset_url": row["asset_url"] or None,
            "publisher": row["publisher"],
            "publication_date": row["date"] or None,
            "media_type": row["media_type"],
            "format": row["format"],
            "http_status_at_check": row["http_status"] or None,
            "content_type_at_check": row["content_type"] or None,
            "size_bytes_at_check": row["size_bytes"] or None,
            "authenticity": row["authenticity"],
            "rights_and_handling": row["rights_and_handling"],
            "presentation_use": row["presentation_use"],
            "notes": row["notes"],
            "graphic": False,
            "not_case_evidence": not_case_evidence,
            "presumption_of_innocence": True,
        }
        if manifest_id == "VID-001":
            metadata["alternate_stream"] = {
                "public_source_id": "VID-002",
                "url": alternate_video["asset_url"],
                "format": alternate_video["format"],
                "note": "Alternate stream for VID-001; not separate evidence.",
            }
            metadata["poster_reference"] = {
                "public_source_id": "IMG-001",
                "url": poster["asset_url"],
                "note": "Publisher thumbnail; not a forensic still.",
            }

        description_prefix = (
            "Presentation/source context only; not case evidence. "
            if not_case_evidence
            else "Source-qualified external reference; no native file is stored. "
        )
        evidence_item_id = world.next_id("EvidenceItem")
        world.add("EvidenceItem", (
            evidence_item_id,
            case_id,
            world.source_system[_source_system_code(row)],
            source_record_ids[manifest_id],
            "external_reference",
            category,
            row["title"],
            description_prefix + row["notes"],
            f"PUBSRC-RSW-E-{manifest_id}",
            "en",
            Arr(tags),
            "public_source_curator",
            "demo_normal",
            "available",
            Json(metadata),
            None,
            None,
            None,
            False,
        ))
        world.add("EvidenceActivityEvent", (
            evidence_item_id,
            "created",
            "public_source_curator",
            Json({
                "metadata_only": True,
                "public_source_id": manifest_id,
                "is_synthetic": False,
                "no_native_file": True,
            }),
        ))
        world.add("EvidenceCaseLink", (
            evidence_item_id, case_id, "external_reference", "public_source_curator",
        ))
        for person_key in _EVIDENCE_ENTITY_KEYS.get(manifest_id, ()):
            world.add("EvidenceEntityLink", (
                evidence_item_id,
                entity_ids_by_key[person_key],
                "mentions",
                1.0,
                "reviewed",
                source_record_ids[manifest_id],
            ))


def build_renukaswamy_case(
    world: C.World,
    *,
    case_id: int,
    status_id_by_name: dict[str, int],
) -> int:
    """Append the curated case without reading or advancing ``world.rng``."""
    if case_id <= 0:
        raise RuntimeError("Curated case requires a reserved positive CaseMasterID")
    existing_case_ids = {
        row[C.TABLES["CaseMaster"].index("CaseMasterID")]
        for row in world.rows.get("CaseMaster", ())
    }
    if case_id in existing_case_ids:
        raise RuntimeError(f"Reserved curated CaseMasterID {case_id} is already occupied")

    source_record_ids, manifest_by_id = _emit_sources(world)
    proxy = _proxy_references(world.ctx)
    district_id = proxy["district_id"]
    unit_id = proxy["unit_id"]
    officer_id = proxy["officer_id"]
    court_id = proxy["court_id"]
    profile = proxy["murder_profile"]

    crime_no = f"1{district_id:04d}{unit_id:04d}2024{99999:05d}"
    if len(crime_no) != 18 or not crime_no.isdigit():
        raise RuntimeError(f"Curated surrogate CrimeNo is not 18 digits: {crime_no}")
    existing_crime_nos = {
        row[C.TABLES["CaseMaster"].index("CrimeNo")]
        for row in world.rows.get("CaseMaster", ())
    }
    if crime_no in existing_crime_nos:
        raise RuntimeError(f"Curated surrogate CrimeNo collides with generated data: {crime_no}")

    brief_facts = (
        "Public-source curated record concerning the alleged abduction and killing "
        "of Renukaswamy in Bengaluru on 8 June 2024. Pavitra Gowda, Darshan S. "
        "Thoogudeepa and 15 others were charged. The allegations remain to be tested "
        "at trial; no finding of guilt or final disposition is represented. Public "
        "documents and publisher media are external references, not forensic originals."
    )
    world.add("CaseMaster", (
        case_id,
        crime_no,
        "2024-06-09",
        officer_id,
        unit_id,
        world.ctx.category_id["FIR"],
        profile["gravity_id"],
        profile["crime_head_id"],
        profile["crime_sub_id"],
        status_id_by_name["Pending Trial"],
        court_id,
        "2024-06-08 00:00:00+00",
        "2024-06-08 23:59:59+00",
        "2024-06-09 00:00:00+00",
        round(CASE_LOCATION_LAT, 6),
        round(CASE_LOCATION_LON, 6),
        brief_facts,
    ))
    world.case_meta[case_id] = {
        "kind": "fir_standard",
        "category": "FIR",
        "status": SR.S_PENDING_TRIAL,
        "converted": False,
        "has_cs": True,
        "record_origin": "public_source_curated",
        "is_synthetic": False,
        "excluded_from_derived_analytics": True,
    }

    for source_id in _CASE_SUMMARY_SOURCE_IDS:
        world.add("CaseSource", (
            case_id,
            world.source_system[_source_system_code(manifest_by_id[source_id])],
            source_record_ids[source_id],
            f"{OFFICIAL_CRIME_REFERENCE} / PUBSRC-RSW-{source_id}",
            "external_reference",
        ))

    snapshot = {
        "kind": "fir_standard",
        "record_origin": "public_source_curated",
        "is_synthetic": False,
        "excluded_from_derived_analytics": True,
        "source_cutoff": SOURCE_CUTOFF,
        "official_references": {
            "police_crime_no": OFFICIAL_CRIME_REFERENCE,
            "committal_case_no": COMMITTAL_CASE_REFERENCE,
            "sessions_case_no": TRIAL_CASE_REFERENCE,
            "surrogate_crime_no": crime_no,
        },
        "status": {
            "code": SR.S_PENDING_TRIAL,
            "label": "Pending Trial",
            "as_of": SOURCE_CUTOFF,
            "no_final_disposition": True,
        },
        "notices": [
            "PENDING_TRIAL", "ALLEGATION_NOT_FINDING", "PUBLIC_SOURCE_REFERENCE",
        ],
        "location": {
            "label": "Pattanagere locality, Bengaluru",
            "precision": "approximate_locality_reference",
            "not_exact_incident_scene": True,
            "source_id": "GEO-001",
            "attribution": "OpenStreetMap contributors, ODbL 1.0",
        },
        "reference_mapping": {
            "kind": "proxy",
            "reason": "Fixture reference tables do not contain the real station, officer, or trial court.",
            "public_station_label": "Kamakshipalya Police Station",
            "public_trial_court_label": "City Civil and Sessions Court, Bengaluru",
            "reported_approver_court_label": "59th City Civil and Sessions Court, Bengaluru",
            "proxy_district_id": district_id,
            "proxy_unit_id": unit_id,
            "proxy_officer_id": officer_id,
            "proxy_court_id": court_id,
            "do_not_present_proxy_as_real_authority": True,
        },
        "privacy": {
            "excluded": [
                "street_addresses", "phone_numbers", "private_chats",
                "account_identifiers", "graphic_assault_or_autopsy_images",
                "minors_images", "unverified_reposts",
            ],
        },
    }
    case_version_id = world.next_id("CaseVersion")
    world.add("CaseVersion", (
        case_version_id, case_id, 1, "FIR", SR.S_PENDING_TRIAL, True,
        round(CASE_LOCATION_LAT, 6), round(CASE_LOCATION_LON, 6),
        district_id, unit_id, Json(snapshot),
        "Initial public-source curated snapshot", "public_source_curator",
    ))

    # Canonical people and legacy compatibility rows.
    all_people = ACCUSED + (VICTIM, COMPLAINANT, WITNESS)
    person_ids: Dict[str, int] = {}
    entity_ids: Dict[str, int] = {}
    for person in all_people:
        canonical_person_id, canonical_entity_id = _mint_person(
            world, person, source_record_ids["DOC-005"]
        )
        person_ids[person.key] = canonical_person_id
        entity_ids[person.key] = canonical_entity_id
        world.person_case_count[canonical_person_id] = 1

    accused_master_ids: Dict[str, int] = {}
    for person in ACCUSED:
        accused_master_id = world.next_id("Accused")
        role_id = world.next_id("CasePartyRole")
        provenance = {
            "record_origin": "public_source_curated",
            "is_synthetic": False,
            "source_ids": ["DOC-001", "DOC-005"],
            "source_record_ids": [source_record_ids["DOC-001"], source_record_ids["DOC-005"]],
            "allegation_not_finding": True,
            "presumption_of_innocence": True,
            "charged_accused_sequence": person.sequence_no,
        }
        if person.key == "A14":
            provenance["current_procedural_update"] = {
                "as_of": "2026-08-25",
                "reported_role": "approver / prosecution witness",
                "source_ids": ["SRC-004", "SRC-005"],
                "underlying_order_obtained": False,
            }
        world.add("CasePartyRole", (
            role_id, case_id, person_ids[person.key], None, "accused", False,
            "Accused", accused_master_id, person.display_name, person.sequence_no,
            Json(provenance),
        ))
        world.add("Accused", (
            accused_master_id, case_id, person.display_name, None, person.gender_id,
            f"A{person.sequence_no}", person_ids[person.key], role_id,
        ))
        accused_master_ids[person.key] = accused_master_id

    victim_master_id = world.next_id("Victim")
    victim_role_id = world.next_id("CasePartyRole")
    world.add("CasePartyRole", (
        victim_role_id, case_id, person_ids[VICTIM.key], None, "victim", False,
        "Victim", victim_master_id, VICTIM.display_name, 1,
        Json({
            "record_origin": "public_source_curated", "is_synthetic": False,
            "source_ids": ["DOC-001", "DOC-005"],
            "age_omitted_due_to_source_conflict": True,
        }),
    ))
    world.add("Victim", (
        victim_master_id, case_id, VICTIM.display_name, None, VICTIM.gender_id,
        "0", person_ids[VICTIM.key],
    ))

    complainant_id = world.next_id("ComplainantDetails")
    complainant_role_id = world.next_id("CasePartyRole")
    world.add("CasePartyRole", (
        complainant_role_id, case_id, person_ids[COMPLAINANT.key], None,
        "complainant", False, "ComplainantDetails", complainant_id,
        COMPLAINANT.display_name, 1,
        Json({
            "record_origin": "public_source_curated", "is_synthetic": False,
            "source_ids": ["DOC-001"], "public_role": "apartment security officer",
        }),
    ))
    world.add("ComplainantDetails", (
        complainant_id, case_id, COMPLAINANT.display_name, None,
        ref.OCCUPATIONS.index("Private Employee") + 1,
        None, None, COMPLAINANT.gender_id, person_ids[COMPLAINANT.key],
    ))
    informant_role_id = world.next_id("CasePartyRole")
    world.add("CasePartyRole", (
        informant_role_id, case_id, person_ids[COMPLAINANT.key], None,
        "informant", False, None, None, COMPLAINANT.display_name, 1,
        Json({
            "record_origin": "public_source_curated", "is_synthetic": False,
            "source_ids": ["DOC-001"],
        }),
    ))

    witness_role_id = world.next_id("CasePartyRole")
    world.add("CasePartyRole", (
        witness_role_id, case_id, person_ids[WITNESS.key], None,
        "witness", False, None, None, WITNESS.display_name, 1,
        Json({
            "record_origin": "public_source_curated", "is_synthetic": False,
            "source_ids": ["DOC-005"], "public_role": "victim's mother / PW-1",
            "statement_text_not_available": True,
        }),
    ))
    approver_role_id = world.next_id("CasePartyRole")
    world.add("CasePartyRole", (
        approver_role_id, case_id, person_ids["A14"], None,
        "witness", False, None, None, "Pradoosh S. Rao (reported approver)", 2,
        Json({
            "record_origin": "public_source_curated", "is_synthetic": False,
            "procedural_role": "approver / prosecution witness",
            "effective_reported_date": "2026-08-25",
            "source_ids": ["SRC-004", "SRC-005"],
            "source_record_ids": [source_record_ids["SRC-004"], source_record_ids["SRC-005"]],
            "underlying_order_obtained": False,
            "not_a_guilt_finding": True,
        }),
    ))

    # Charged provisions. Section IDs are namespaced exactly like reference.py.
    for order, section in enumerate(CHARGED_SECTIONS, start=1):
        world.add("ActSectionAssociation", (
            case_id, "IPC", ref.section_code("IPC", section), 1, order,
        ))

    # Source-qualified lifecycle and allegation chronology.
    sequence_no = 0

    def add_event(**kwargs):
        nonlocal sequence_no
        sequence_no += 1
        _event(
            world,
            case_id=case_id,
            sequence_no=sequence_no,
            source_record_ids=source_record_ids,
            **kwargs,
        )

    add_event(
        event_type="alleged_messages_started", event_category="allegation",
        occurred_at="2024-02-01 00:00:00+00", from_status=None, to_status=None,
        display_label="February 2024 (month precision): alleged messages reportedly began",
        source_ids=("DOC-001",), payload={"alleged": True, "date_precision": "month"},
    )
    add_event(
        event_type="alleged_instagram_contact", event_category="allegation",
        occurred_at="2024-06-03 00:00:00+00", from_status=None, to_status=None,
        display_label="Alleged Instagram contact", source_ids=("DOC-001",),
        payload={"alleged": True, "date_precision": "day", "no_private_content_stored": True},
    )
    add_event(
        event_type="alleged_phone_whatsapp_contact", event_category="allegation",
        occurred_at="2024-06-05 00:00:00+00", from_status=None, to_status=None,
        display_label="Alleged phone/WhatsApp contact", source_ids=("DOC-001",),
        payload={"alleged": True, "date_precision": "day", "no_private_content_stored": True},
    )
    add_event(
        event_type="alleged_search_attempt", event_category="allegation",
        occurred_at="2024-06-07 00:00:00+00", from_status=None, to_status=None,
        display_label="Alleged unsuccessful search for Renukaswamy",
        source_ids=("DOC-001",), payload={"alleged": True, "date_precision": "day"},
    )
    add_event(
        event_type="alleged_abduction_assault_death", event_category="allegation",
        occurred_at="2024-06-08 00:00:00+00", from_status=None, to_status=None,
        display_label="Alleged transport to Pattanagere, assault and death",
        source_ids=("DOC-001", "DOC-002"),
        payload={
            "alleged": True, "date_precision": "day",
            "location_precision": "public_locality_only", "graphic_detail_excluded": True,
        },
    )
    add_event(
        event_type="body_found", event_category="investigation",
        occurred_at="2024-06-09 00:00:00+00", from_status=None, to_status=None,
        display_label="Body found near Sumanahalli drain",
        source_ids=("DOC-001",), payload={"date_precision": "day", "graphic_detail_excluded": True},
    )
    add_event(
        event_type=SR.E_REGISTERED, event_category="lifecycle",
        occurred_at="2024-06-09 00:00:00+00", from_status=None,
        to_status=SR.S_UNDER_INVESTIGATION,
        display_label=f"FIR registered against unknown persons ({OFFICIAL_CRIME_REFERENCE})",
        source_ids=("DOC-001", "DOC-005"), payload={"date_precision": "day"},
    )
    add_event(
        event_type=SR.E_INVESTIGATION, event_category="lifecycle",
        occurred_at="2024-06-09 00:00:00+00",
        from_status=SR.S_UNDER_INVESTIGATION, to_status=SR.S_UNDER_INVESTIGATION,
        display_label="Investigation commenced", source_ids=("DOC-001",),
        payload={"date_precision": "day"},
    )

    for person_key, arrest_date, arrest_type, label in ARRESTS:
        arrest_surrender_id = world.next_id("ArrestSurrender")
        world.add("ArrestSurrender", (
            arrest_surrender_id, case_id, arrest_type, arrest_date,
            world.ctx.state_id, district_id, unit_id, officer_id, court_id,
            accused_master_ids[person_key], True, False,
        ))
        world.add("inv_arrestsurrenderaccused", (
            arrest_surrender_id, accused_master_ids[person_key],
        ))
        event_type = "surrender" if arrest_type == 2 else SR.E_ARREST
        add_event(
            event_type=event_type, event_category="investigation",
            occurred_at=f"{arrest_date} 00:00:00+00",
            from_status=SR.S_UNDER_INVESTIGATION,
            to_status=SR.S_UNDER_INVESTIGATION,
            display_label=label,
            source_ids=("DOC-001", "DOC-002"),
            payload={
                "date_precision": "day", "person_key": person_key,
                "legacy_arrest_surrender_type": arrest_type,
                "source_description_conflict": arrest_type is None,
            },
        )

    chargesheet_id = world.next_id("ChargesheetDetails")
    world.add("ChargesheetDetails", (
        chargesheet_id, case_id, "2024-09-04 00:00:00+00", "A", officer_id,
    ))
    add_event(
        event_type=SR.E_CHARGESHEET_FILED, event_category="court",
        occurred_at="2024-09-04 00:00:00+00",
        from_status=SR.S_UNDER_INVESTIGATION, to_status=SR.S_CHARGESHEETED,
        display_label="Primary charge sheet reportedly filed (3,991 pages)",
        source_ids=("DOC-001", "DOC-002"),
        payload={
            "date_precision": "day", "reported_page_count": 3991,
            "native_document_available": False,
            "supplementary_charge_sheets_reported": 2,
            "supplementary_dates_verified": False,
        },
    )
    add_event(
        event_type=SR.E_COURT_ASSIGNED, event_category="court",
        occurred_at=None, from_status=SR.S_CHARGESHEETED, to_status=SR.S_PENDING_TRIAL,
        display_label="Case committed/assigned for trial (exact assignment date unavailable)",
        source_ids=("DOC-001", "DOC-005"),
        payload={
            "date_precision": "unavailable", "sessions_case_no": TRIAL_CASE_REFERENCE,
            "committal_case_no": COMMITTAL_CASE_REFERENCE,
            "reference_mapping": "proxy",
        },
    )
    add_event(
        event_type="charges_framed_reported", event_category="court",
        occurred_at="2025-11-03 00:00:00+00",
        from_status=SR.S_PENDING_TRIAL, to_status=SR.S_PENDING_TRIAL,
        display_label="By 3 November 2025 reporting, charges had been framed",
        source_ids=("DOC-005",),
        payload={
            "date_is_publication_anchor": True,
            "exact_charge_framing_date_not_verified": True,
        },
    )
    add_event(
        event_type="state_bail_cancellation_petitions_rejected", event_category="court",
        occurred_at="2026-06-10 00:00:00+00",
        from_status=SR.S_PENDING_TRIAL, to_status=SR.S_PENDING_TRIAL,
        display_label="High Court rejected State bail-cancellation petitions concerning A3/A4 and A5",
        source_ids=("DOC-003", "DOC-004"), payload={"date_precision": "day"},
    )
    add_event(
        event_type="approver_objection_challenge_dismissed", event_category="court",
        occurred_at="2026-08-13 00:00:00+00",
        from_status=SR.S_PENDING_TRIAL, to_status=SR.S_PENDING_TRIAL,
        display_label="High Court reportedly dismissed A2's procedural challenge concerning A14's approver request",
        source_ids=("SRC-004",),
        payload={"secondary_source_only": True, "underlying_order_obtained": False},
    )
    add_event(
        event_type=SR.E_HEARING, event_category="court",
        occurred_at="2026-08-18 00:00:00+00",
        from_status=SR.S_PENDING_TRIAL, to_status=SR.S_PENDING_TRIAL,
        display_label="Trial pending; High Court decided PW-1 procedural issue",
        source_ids=("DOC-005",),
        payload={"date_precision": "day", "no_witness_statement_text_stored": True},
    )
    add_event(
        event_type="approver_allowed", event_category="court",
        occurred_at="2026-08-25 00:00:00+00",
        from_status=SR.S_PENDING_TRIAL, to_status=SR.S_PENDING_TRIAL,
        display_label="A14 reportedly allowed to turn approver/prosecution witness",
        source_ids=("SRC-004", "SRC-005"),
        payload={
            "secondary_sources_only": True, "underlying_order_obtained": False,
            "not_a_guilt_finding": True, "trial_remains_pending": True,
        },
    )

    # Court and bail records are procedural summaries only. The fixture CourtID
    # is a disclosed proxy; the public court labels live in Detail/SnapshotAttributes.
    _court_event(
        world, case_id=case_id, court_id=court_id, event_type="chargesheet_filed",
        occurred_at="2024-09-04 00:00:00+00", outcome="filed",
        source_ids=("DOC-001", "DOC-002"), source_record_ids=source_record_ids,
        detail={
            "reported_page_count": 3991, "native_document_available": False,
            "supplementary_charge_sheets_reported": 2,
            "supplementary_dates_verified": False,
        },
    )
    _court_event(
        world, case_id=case_id, court_id=court_id, event_type="interim_medical_bail",
        occurred_at="2024-10-15 00:00:00+00", outcome="six weeks granted to A2",
        source_ids=("DOC-001", "DOC-002"), source_record_ids=source_record_ids,
        detail={"person_key": "A02", "bail_type": "medical_interim"},
    )
    world.add("BailEvent", (
        case_id, person_ids["A02"], "medical_interim_six_weeks", "granted",
        "2024-10-15 00:00:00+00", court_id,
        Json({
            "source_ids": ["DOC-001", "DOC-002"],
            "is_synthetic": False, "reference_mapping": "proxy",
        }),
    ))

    high_court_bail_keys = ("A01", "A02", "A06", "A07", "A11", "A12", "A14")
    _court_event(
        world, case_id=case_id, court_id=court_id, event_type="regular_bail",
        occurred_at="2024-12-13 00:00:00+00", outcome="granted to A1, A2, A6, A7, A11, A12 and A14",
        source_ids=("DOC-002",), source_record_ids=source_record_ids,
        detail={"person_keys": list(high_court_bail_keys), "later_set_aside": True},
    )
    for key in high_court_bail_keys:
        world.add("BailEvent", (
            case_id, person_ids[key], "regular_high_court", "granted",
            "2024-12-13 00:00:00+00", court_id,
            Json({
                "source_ids": ["DOC-002"], "is_synthetic": False,
                "later_set_aside_on": "2025-08-14", "reference_mapping": "proxy",
            }),
        ))

    trial_court_bail_keys = ("A03", "A04", "A05")
    _court_event(
        world, case_id=case_id, court_id=court_id, event_type="regular_bail",
        occurred_at="2024-12-23 00:00:00+00", outcome="granted to A3, A4 and A5",
        source_ids=("DOC-001", "DOC-003", "DOC-004"),
        source_record_ids=source_record_ids,
        detail={"person_keys": list(trial_court_bail_keys)},
    )
    for key in trial_court_bail_keys:
        world.add("BailEvent", (
            case_id, person_ids[key], "regular_trial_court", "granted",
            "2024-12-23 00:00:00+00", court_id,
            Json({
                "source_ids": ["DOC-001", "DOC-003", "DOC-004"],
                "is_synthetic": False, "reference_mapping": "proxy",
            }),
        ))

    _court_event(
        world, case_id=case_id, court_id=court_id, event_type="bail_cancellation",
        occurred_at="2025-08-14 00:00:00+00", outcome="seven High Court bail grants set aside",
        source_ids=("DOC-001",), source_record_ids=source_record_ids,
        detail={
            "person_keys": list(high_court_bail_keys),
            "decision_scope": "bail only", "not_a_trial_finding": True,
        },
    )
    _court_event(
        world, case_id=case_id, court_id=court_id, event_type="framing_of_charges",
        occurred_at="2025-11-03 00:00:00+00", outcome="reported as framed",
        source_ids=("DOC-005",), source_record_ids=source_record_ids,
        detail={
            "date_is_publication_anchor": True,
            "exact_charge_framing_date_not_verified": True,
        },
    )
    _court_event(
        world, case_id=case_id, court_id=court_id,
        event_type="bail_cancellation_petition",
        occurred_at="2026-06-10 00:00:00+00",
        outcome="State petitions rejected for A3/A4 and A5",
        source_ids=("DOC-003", "DOC-004"), source_record_ids=source_record_ids,
    )
    _court_event(
        world, case_id=case_id, court_id=court_id, event_type="hearing",
        occurred_at="2026-08-18 00:00:00+00", outcome="PW-1 procedure decided; trial pending",
        source_ids=("DOC-005",), source_record_ids=source_record_ids,
        detail={"no_witness_statement_text_stored": True},
    )
    _court_event(
        world, case_id=case_id, court_id=court_id, event_type="approver_allowed",
        occurred_at="2026-08-25 00:00:00+00",
        outcome="A14 reportedly permitted to become approver/prosecution witness",
        source_ids=("SRC-004", "SRC-005"), source_record_ids=source_record_ids,
        detail={
            "reported_court_label": "59th City Civil and Sessions Court, Bengaluru",
            "secondary_sources_only": True, "underlying_order_obtained": False,
            "trial_remains_pending": True,
        },
    )

    world.add("Inv_OccuranceTime", (case_id,))
    _evidence_rows(
        world,
        case_id=case_id,
        source_record_ids=source_record_ids,
        manifest_by_id=manifest_by_id,
        entity_ids_by_key=entity_ids,
    )

    world.cover("curated_public_source_case")
    world.cover("curated_pending_trial_safeguard")
    world.cover("curated_non_synthetic_people", len(all_people))
    world.cover("curated_external_references")
    return case_id
