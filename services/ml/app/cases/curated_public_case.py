"""Loader for a CURATED PUBLIC-SOURCE case record.

Most of DRISHTI's corpus is synthetic. This module handles the other kind: a real
case reconstructed from published court records, loaded so the case surfaces can be
demonstrated on material a Karnataka officer would recognise.

The distinction is not cosmetic, and the plumbing for it already existed before this
loader did — ``record_origin='public_source_curated'`` is read by nine modules:

  * ``cases/casedata.py``     -> ``read_only=True``, ``is_synthetic=False``, and the
                                notice banners (PENDING_TRIAL / ALLEGATION_NOT_FINDING
                                / PUBLIC_SOURCE_REFERENCE) rendered on the case file;
  * ``intake/service.py``     -> refuses operational lifecycle events on the case, so
                                nobody can "progress" a real matter from a demo seat;
  * ``casework/service.py``   -> same read-only guard on casework actions;
  * ``evidence/service.py``   -> keeps curated source material out of the evidence
                                upload/extraction path;
  * ``geo/jurisdiction.py``   -> excludes it from containment reassignment;
  * ``identity/service.py``   -> keeps curated persons out of automatic entity merges;
  * ``cases/analytics_policy.py`` -> EXCLUDES it from every derived analytics artifact.

That last one matters operationally: loading this case moves the analytics-policy
digest, which invalidates the persisted hotspot/alert/workload artifacts. Re-run
``hotspots``, ``emerging-alerts`` and ``workload-run`` afterwards or those endpoints
correctly fail closed with a policy mismatch.

WHAT THIS LOADER WILL NOT DO. It records no biometric material for any real person.
The parties carry no face descriptor and no ``face_enrol_on_approval`` flag, so the
intake approval path cannot enrol one. Face recognition is demonstrated separately
against synthetic identities. A living accused who has not been convicted does not
belong in a face-identification gallery, and putting one there would contradict the
presumption of innocence this record is explicitly built to preserve.

Everything the narrative asserts is the PROSECUTION'S CASE or a published report,
never an established fact. The trial is pending; there is no verdict.
"""
from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from psycopg2.extras import Json

from ..intake import service as intake
from ..intake.schemas import (Classification, CreateDraftRequest, DraftPayload,
                              IncidentInfo, Narrative, PartyInput, Registration,
                              SourceInfo)

# Marks every row this loader writes, so a reload updates in place.
CURATED_ORIGIN = "public_source_curated"

# CaseStatusMaster: 7 = "Pending Trial". The status has to match reality — charges
# are framed and the trial has begun, so "Under Investigation" would be wrong.
STATUS_PENDING_TRIAL_ID = 7
STATUS_PENDING_TRIAL_CODE = "pending_trial"

# SourceRecord.RecordKind values that casedata.fetch_case_provenance refuses to
# surface on the case file. Used to keep nonpublic and graphic material listed in
# the manifest but never rendered.
KIND_PRESENTABLE = "public_source_reference"
KIND_EXCLUDED = "excluded_reference"
KIND_NONPUBLIC = "nonpublic_availability"

# chk_sourcerecord_status allows received|staged|committed|rejected|retracted|
# duplicate|stale. A curated record is settled reference material, not something
# still moving through an ingestion pipeline.
RECORD_STATUS = "committed"


@dataclass
class CuratedParty:
    role_type: str                      # victim | accused | complainant | witness
    display_name: str
    accused_number: Optional[str] = None
    notes: Optional[str] = None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class CuratedCase:
    """A real case reconstructed from published records."""

    external_source_id: str
    title: str
    registration_date: str
    incident_from: str
    incident_to: str
    info_received_at: str
    station_id: int
    district_id: int
    registering_officer_id: int
    assigned_io_id: Optional[int]
    major_head_id: int
    acts_sections: list[tuple[str, str]]
    latitude: float
    longitude: float
    address: str
    landmark: str
    brief_facts: str
    source_notes: str
    parties: list[CuratedParty]
    official_references: dict[str, Any]
    source_cutoff: str
    notices: list[str]
    location_note: str


# ---------------------------------------------------------------------------
# The case
# ---------------------------------------------------------------------------
# Accused numbering follows the 3,991-page charge sheet as reported: Pavithra Gowda
# is A1 and Darshan Thoogudeepa is A2. Only the accused whose numbering is
# corroborated by a cited record are named here. The remainder are carried as
# numbered placeholders rather than invented, because a demo that fabricates the
# name of a real person on trial is worse than one that admits the gap.
_NAMED_ACCUSED: list[tuple[str, str, str]] = [
    ("A1", "Pavithra Gowda",
     "Named Accused No. 1 in the charge sheet as reported."),
    ("A2", "Darshan Thoogudeepa",
     "Named Accused No. 2 in the charge sheet as reported. Kannada film actor. "
     "Bail granted by the High Court on 13 Dec 2024 was cancelled by the Supreme "
     "Court on 14 Aug 2025 (2025 INSC 979)."),
    ("A3", "Puttaswamy alias Pavan K.",
     "Subject of Karnataka High Court bail proceedings dated 10 Jun 2026 "
     "(NC:2026:KHC:30009); the State's cancellation petition was rejected."),
    ("A4", "Raghavendra N.",
     "Subject of the same 10 Jun 2026 bail proceeding as A3."),
    ("A5", "Nandeesh",
     "Subject of Karnataka High Court bail proceedings dated 10 Jun 2026 "
     "(NC:2026:KHC:30010); the State's cancellation petition was rejected."),
    ("A14", "Pradosh S. Rao",
     "Permitted by the 59th City Civil and Sessions Court to turn approver, on "
     "conditions, as reported in Aug 2026. Darshan's challenge to that order was "
     "dismissed by the High Court. An approver's account is untested evidence."),
]

_BRIEF_FACTS = (
    "CURATED PUBLIC-SOURCE RECORD — NOT AN OPERATIONAL CASE FILE. Reconstructed "
    "from published court records and reporting; every assertion below is the "
    "prosecution's case or a published report, not an established fact. The trial "
    "is pending and no finding of guilt has been recorded against any accused.\n\n"
    "As alleged by the prosecution: Renukaswamy, aged 33, a pharmacy employee and "
    "resident of Chitradurga, was abducted from Chitradurga on 7 June 2024, taken "
    "to Bengaluru and assaulted in a shed in the Pattanagere area of "
    "Rajarajeshwari Nagar, dying of his injuries on 8 June 2024. His body was "
    "recovered from a stormwater drain at Kamakshipalya, Bengaluru, on 9 June "
    "2024. The prosecution alleges the motive was retaliation for obscene "
    "messages sent to Accused No. 1 over Instagram.\n\n"
    "Bengaluru City Police filed a 3,991-page charge sheet on 4 September 2024 in "
    "seven volumes and ten files before the 24th Additional Chief Metropolitan "
    "Magistrate, citing 231 witnesses, of whom 97 were independent and 27 recorded "
    "statements before a magistrate under Section 164 CrPC. A supplementary charge "
    "sheet of over 1,300 pages followed in November 2024.\n\n"
    "A Sessions Court framed charges against all 17 accused on 3 November 2025 "
    "under provisions including IPC 302 (murder), kidnapping/abduction, 120B "
    "(criminal conspiracy), unlawful assembly and destruction of evidence. Every "
    "accused pleaded NOT GUILTY. The Supreme Court has directed the trial court to "
    "expedite the trial."
)

_SOURCE_NOTES = (
    "Sources are catalogued in research/renukaswamy-case-evidence/evidence_manifest.csv "
    "and classified A-F by evidentiary weight. Class A are primary judicial texts via "
    "an Indian Kanoon mirror, which is NOT a certified court copy. Class B are "
    "copyrighted publisher photographs held for attribution only. Class C is a "
    "media-published CCTV extract, not an original police export, and carries no "
    "native timestamps, acquisition metadata, hash or chain of custody. Class D "
    "material (CCTV masters, forensic phone images, FSL reports, post-mortem, CDRs, "
    "witness depositions, the authenticated charge sheets, exhibits P1-P13, material "
    "objects MO1-MO8, defence markings D1-D22) remains in police or court custody and "
    "is recorded here as unavailable, not reconstructed. Class E graphic leaked "
    "material is excluded from display entirely."
)

RENUKASWAMY_CASE = CuratedCase(
    external_source_id="PUBLIC-CURATED-RENUKASWAMY-2024",
    title="Renukaswamy homicide — curated public-source record",
    # The FIR follows the recovery of the body and the complaint that preceded it.
    registration_date="2024-06-09",
    incident_from="2024-06-07T00:00:00",
    incident_to="2024-06-08T23:59:00",
    info_received_at="2024-06-09T00:00:00",
    # The synthetic Unit table has no real Karnataka station names, so the record
    # sits on a Bengaluru City station and the ACTUAL investigating jurisdiction is
    # recorded in official_references instead of being faked into the unit table.
    station_id=33,
    district_id=1,
    registering_officer_id=1,
    assigned_io_id=1001,
    major_head_id=1,               # Crimes Against Body
    # Only sections present in the reference table are applied. The full charged
    # set, including IPC 120B and the evidence-destruction provisions that this
    # deployment's Section lookup does not carry, is recorded in
    # official_references["charges_framed"] so nothing is silently dropped.
    acts_sections=[("IPC", "IPC-302"), ("IPC", "IPC-364"),
                   ("IPC", "IPC-143"), ("IPC", "IPC-506")],
    # Locality-level reference only (OpenStreetMap/Nominatim). Deliberately NOT a
    # verified shed or exact scene coordinate.
    latitude=12.9160908,
    longitude=77.5141119,
    address="Pattanagere, Rajarajeshwari Nagar, Bengaluru, Karnataka",
    landmark="Locality-level reference only — not the verified scene",
    brief_facts=_BRIEF_FACTS,
    source_notes=_SOURCE_NOTES,
    parties=[
        CuratedParty(
            role_type="complainant",
            display_name="Kashinatha Shivanagowdara (father of the deceased)",
            notes="Complainant / next of kin. No contact or address details are "
                  "recorded in this curated pack.",
            attributes={"relationship_to_victim": "father"},
        ),
        CuratedParty(
            role_type="victim",
            display_name="Renukaswamy",
            notes="Deceased. Aged 33, pharmacy employee, resident of Chitradurga.",
            attributes={"age": 33, "deceased": True,
                        "occupation": "pharmacy employee",
                        "home_district": "Chitradurga"},
        ),
        *[
            CuratedParty(role_type="accused", display_name=name,
                         accused_number=num, notes=note)
            for num, name, note in _NAMED_ACCUSED
        ],
        # 17 accused were charged. The 11 not named above are carried as numbered
        # placeholders so the count is right without inventing identities.
        *[
            CuratedParty(
                role_type="accused",
                display_name=f"Accused No. {n} (name not recorded in this pack)",
                accused_number=f"A{n}",
                notes="Charged with the other accused on 3 Nov 2025. This pack does "
                      "not carry a corroborated name for this accused number.",
                attributes={"name_withheld_in_pack": True},
            )
            for n in (6, 7, 8, 9, 10, 11, 12, 13, 15, 16, 17)
        ],
    ],
    official_references={
        "investigating_agency": "Bengaluru City Police",
        "actual_jurisdiction_reported": "Kamakshipalya Police Station, Bengaluru City",
        "jurisdiction_note": (
            "This deployment's Unit table holds synthetic station names only, so the "
            "record is attached to a Bengaluru City station. The real reported "
            "jurisdiction is stated here rather than fabricated into the unit table."
        ),
        "charge_sheet": {
            "filed_on": "2024-09-04",
            "pages": 3991,
            "volumes": 7,
            "files": 10,
            "before": "24th Additional Chief Metropolitan Magistrate, Bengaluru",
            "witnesses": 231,
            "independent_witnesses": 97,
            "statements_under_164_crpc": 27,
        },
        "supplementary_charge_sheet": {
            "filed_on": "2024-11-24", "pages_approx": 1300,
            "note": "Reported to include photographs and call detail records.",
        },
        "charges_framed": {
            "on": "2025-11-03",
            "court": "Sessions Court, Bengaluru",
            "accused_count": 17,
            "plea": "not guilty (all accused)",
            "sections_reported": [
                "IPC 302 - murder",
                "IPC 364 / 359 - kidnapping / abduction",
                "IPC 120B - criminal conspiracy",
                "IPC 204 - destruction of evidence",
                "unlawful assembly",
            ],
            "note": "IPC 120B and 204 are not present in this deployment's Section "
                    "lookup, so they are recorded here rather than as applied "
                    "sections on the case.",
        },
        "appellate_history": [
            {"date": "2024-12-13", "court": "Karnataka High Court",
             "citation": "NC:2024:KHC:51482",
             "outcome": "Bail granted; later set aside for seven accused."},
            {"date": "2025-08-14", "court": "Supreme Court of India",
             "citation": "2025 INSC 979",
             "matter": "Criminal Appeal Nos. 3528-3534/2025",
             "outcome": "Bail cancelled for seven accused."},
            {"date": "2026-06-10", "court": "Karnataka High Court",
             "citation": "NC:2026:KHC:30009 / NC:2026:KHC:30010",
             "outcome": "State bail-cancellation petitions against A3, A4 and A5 rejected."},
            {"date": "2026-08-18", "court": "Karnataka High Court",
             "matter": "Criminal Petition No. 6820/2026",
             "outcome": "Trial-procedure order; trial remained pending."},
        ],
        "trial_status": {
            "as_of": "2026-09-07",
            "state": "pending",
            "verdict": None,
            "note": "Charges framed and trial under way. No conviction or acquittal "
                    "has been recorded against any accused.",
        },
        "approver": {
            "accused_number": "A14",
            "reported_on": "2026-08-25",
            "court": "59th City Civil and Sessions Court, Bengaluru",
            "note": "Permitted to turn approver on conditions, per corroborated "
                    "publisher reports; the underlying order was not obtained.",
        },
    },
    source_cutoff="2026-09-07",
    notices=["PENDING_TRIAL", "ALLEGATION_NOT_FINDING", "PUBLIC_SOURCE_REFERENCE"],
    location_note=(
        "Locality-level OpenStreetMap/Nominatim reference for Pattanagere, "
        "Rajarajeshwari Nagar. Not the verified shed or exact alleged scene."
    ),
)


# ---------------------------------------------------------------------------
# loader
# ---------------------------------------------------------------------------
def _party_inputs(case: CuratedCase) -> list[PartyInput]:
    """Draft parties. Deliberately carries NO face material.

    ``intake.service._enrol_party_face`` enrols a descriptor onto the identity it
    creates when a party sets ``face_enrol_on_approval`` and ``face_probe_ref``.
    Neither is ever set here, so approving this case cannot put a real accused into
    the face gallery.
    """
    out: list[PartyInput] = []
    for i, p in enumerate(case.parties, start=1):
        attrs: dict[str, Any] = dict(p.attributes)
        attrs["record_origin"] = CURATED_ORIGIN
        attrs["presumption_of_innocence"] = True
        if p.notes:
            attrs["curated_note"] = p.notes
        if p.accused_number:
            attrs["accused_number"] = p.accused_number
            # Stated on every accused party so no surface can imply a conviction.
            attrs["legal_status"] = "accused — undertrial, charges framed 2025-11-03"
            attrs["plea"] = "not guilty"
            attrs["convicted"] = False
        out.append(PartyInput(
            role_type=p.role_type,
            party_nature="person",
            display_name=p.display_name,
            attributes=attrs,
            sequence_no=i,
        ))
    return out


def _draft_payload(case: CuratedCase) -> DraftPayload:
    return DraftPayload(
        source=SourceInfo(
            source_system_code="COURT_DOC",
            source_method="public_source_curation",
            external_source_id=case.external_source_id,
        ),
        registration=Registration(
            registration_date=case.registration_date,
            registering_officer_id=case.registering_officer_id,
            station_id=case.station_id,
            district_id=case.district_id,
            assigned_io_id=case.assigned_io_id,
            sensitivity="restricted",
            classification="curated public-source record",
        ),
        incident=IncidentInfo(
            incident_from=case.incident_from,
            incident_to=case.incident_to,
            info_received_at=case.info_received_at,
            latitude=case.latitude,
            longitude=case.longitude,
            address=case.address,
            landmark=case.landmark,
            occurrence_description=case.location_note,
        ),
        classification=Classification(
            major_head_id=case.major_head_id,
            acts_sections=[{"act_code": a, "section_code": s}
                           for a, s in case.acts_sections],
            category_specific={"curated_public_source": True},
        ),
        narrative=Narrative(
            brief_facts=case.brief_facts,
            language="en",
            source_notes=case.source_notes,
            restricted=True,
        ),
    )


def _existing_case_id(conn, external_source_id: str) -> Optional[int]:
    """The case this loader previously created, if any (idempotent reload).

    The APPROVED DRAFT is the authoritative marker, not the source links: the FIR is
    registered before the manifest is loaded, so a run that failed partway through
    leaves a real case with no CaseSource rows. Keying only on CaseSource would then
    register a duplicate FIR for the same matter on the next attempt.
    """
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "CaseMasterID" FROM "IntakeDraft" '
            'WHERE "IdempotencyKey"=%s AND "CaseMasterID" IS NOT NULL '
            'ORDER BY "IntakeDraftID" DESC LIMIT 1',
            (external_source_id,),
        )
        row = cur.fetchone()
        if row:
            return int(row[0])
        cur.execute(
            'SELECT cs."CaseMasterID" FROM "CaseSource" cs '
            'WHERE cs."ExternalRef"=%s ORDER BY cs."CaseMasterID" LIMIT 1',
            (external_source_id,),
        )
        row = cur.fetchone()
    return int(row[0]) if row else None


def _stamp_curated_version(conn, case_id: int, case: CuratedCase) -> None:
    """Add the curated-origin attributes to the current CaseVersion snapshot.

    Applied AFTER approval, not before: the same marker makes the case read-only to
    the intake and casework lifecycle paths, so stamping it first would block the
    approval that creates the record.
    """
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "CaseVersionID","SnapshotAttributes" FROM "CaseVersion" '
            'WHERE "CaseMasterID"=%s AND "IsCurrent"=TRUE LIMIT 1', (case_id,))
        row = cur.fetchone()
        if row is None:
            raise RuntimeError(f"case {case_id} has no current CaseVersion")
        version_id = int(row[0])
        snapshot = dict(row[1] or {})
        snapshot.update({
            "record_origin": CURATED_ORIGIN,
            "is_synthetic": False,
            "excluded_from_derived_analytics": True,
            "source_cutoff": case.source_cutoff,
            "notices": list(case.notices),
            "official_references": case.official_references,
            "location": {
                "kind": "locality_reference",
                "latitude": case.latitude,
                "longitude": case.longitude,
                "attribution": "OpenStreetMap contributors / Nominatim",
                "note": case.location_note,
            },
            "reference_mapping": {
                "kind": "public_source_curated",
                "external_source_id": case.external_source_id,
                "manifest": "research/renukaswamy-case-evidence/evidence_manifest.csv",
            },
        })
        cur.execute(
            'UPDATE "CaseVersion" SET "SnapshotAttributes"=%s, "StatusCode"=%s, '
            '"ChangeReason"=%s WHERE "CaseVersionID"=%s',
            (Json(snapshot), STATUS_PENDING_TRIAL_CODE,
             "curated_public_source_load", version_id))
        # The operational status must agree with the court record: charges are
        # framed and the trial is under way.
        cur.execute(
            'UPDATE "CaseMaster" SET "CaseStatusID"=%s WHERE "CaseMasterID"=%s',
            (STATUS_PENDING_TRIAL_ID, case_id))


def _record_kind_for(row: dict[str, str]) -> str:
    """Map a manifest row to a RecordKind the case file will handle correctly."""
    category = (row.get("category") or "").lower()
    if category.startswith("e-") or "excluded" in category:
        return KIND_EXCLUDED
    if category.startswith("d-") or "nonpublic" in category:
        return KIND_NONPUBLIC
    if (row.get("graphic") or "").strip().lower() in ("yes", "true"):
        return KIND_EXCLUDED
    return KIND_PRESENTABLE


def _source_system_id(conn, code: str) -> int:
    with conn.cursor() as cur:
        cur.execute('SELECT "SourceSystemID" FROM "SourceSystem" WHERE "Code"=%s', (code,))
        row = cur.fetchone()
        if row:
            return int(row[0])
        # 'external_reference' is the only Kind in chk_sourcesystem_kind that fits a
        # curated inventory of third-party court and publisher records: nothing here
        # was imported from a feed or captured on a form.
        cur.execute(
            'INSERT INTO "SourceSystem" ("Code","Name","Kind","Description","IsSynthetic") '
            'VALUES (%s,%s,%s,%s,FALSE) RETURNING "SourceSystemID"',
            (code, "Curated public source", "external_reference",
             "Published court records and publisher material curated for reference."))
        return int(cur.fetchone()[0])


def load_manifest_sources(conn, case_id: int, manifest_path: Path,
                          case: CuratedCase) -> dict[str, int]:
    """Load the evidence manifest as SourceRecord rows linked to the case.

    Every row is stored, including the material that must never be displayed: the
    manifest is the honest inventory of what exists, and
    ``casedata.fetch_case_provenance`` filters excluded and nonpublic kinds out of
    the case-file response. Recording an exclusion is not the same as showing it.
    """
    if not manifest_path.exists():
        raise FileNotFoundError(f"evidence manifest not found: {manifest_path}")

    system_id = _source_system_id(conn, "PUBLIC_CURATED")
    counts = {"inserted": 0, "updated": 0, "linked": 0,
              KIND_PRESENTABLE: 0, KIND_EXCLUDED: 0, KIND_NONPUBLIC: 0}

    with manifest_path.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))

    with conn.cursor() as cur:
        for row in rows:
            manifest_id = (row.get("id") or "").strip()
            if not manifest_id:
                continue
            kind = _record_kind_for(row)
            counts[kind] += 1
            external_ref = f"{case.external_source_id}:{manifest_id}"

            payload = {k: (v or None) for k, v in row.items()}
            payload["record_origin"] = CURATED_ORIGIN
            payload["case_external_source_id"] = case.external_source_id
            # Read by fetch_case_provenance to drop unavailable material from the
            # case file even if the record kind were ever mislabelled.
            payload["availability_only"] = kind == KIND_NONPUBLIC
            payload["display_permitted"] = kind == KIND_PRESENTABLE

            content_hash = hashlib.sha256(
                json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
            ).hexdigest()

            cur.execute(
                'SELECT "SourceRecordID" FROM "SourceRecord" WHERE "ExternalRef"=%s',
                (external_ref,))
            found = cur.fetchone()
            if found:
                source_record_id = int(found[0])
                cur.execute(
                    'UPDATE "SourceRecord" SET "Payload"=%s, "RecordKind"=%s, '
                    '"ContentHash"=%s, "Status"=%s WHERE "SourceRecordID"=%s',
                    (Json(payload), kind, content_hash, RECORD_STATUS, source_record_id))
                counts["updated"] += 1
            else:
                cur.execute(
                    'INSERT INTO "SourceRecord" ("SourceSystemID","ExternalRef","RecordKind",'
                    '"Payload","ContentHash","Version","Status","IsSynthetic") '
                    'VALUES (%s,%s,%s,%s,%s,1,%s,FALSE) RETURNING "SourceRecordID"',
                    (system_id, external_ref, kind, Json(payload), content_hash,
                     RECORD_STATUS))
                source_record_id = int(cur.fetchone()[0])
                counts["inserted"] += 1

            cur.execute(
                'SELECT 1 FROM "CaseSource" WHERE "CaseMasterID"=%s AND "SourceRecordID"=%s',
                (case_id, source_record_id))
            if cur.fetchone() is None:
                cur.execute(
                    'INSERT INTO "CaseSource" ("CaseMasterID","SourceSystemID",'
                    '"SourceRecordID","ExternalRef","IngestionMethod") '
                    'VALUES (%s,%s,%s,%s,%s)',
                    (case_id, system_id, source_record_id,
                     case.external_source_id, "public_source_curation"))
                counts["linked"] += 1

    return counts


def load(conn, case: CuratedCase = RENUKASWAMY_CASE, *,
         actor: str = "curated.loader",
         manifest_path: Optional[Path] = None) -> dict[str, Any]:
    """Ingest the case through the real FIR path, then mark it curated.

    Idempotent: a reload refreshes the source inventory and the curated snapshot on
    the existing case rather than registering a second FIR for the same matter.
    """
    manifest_path = manifest_path or (
        Path(__file__).resolve().parents[4]
        / "research" / "renukaswamy-case-evidence" / "evidence_manifest.csv"
    )

    existing = _existing_case_id(conn, case.external_source_id)
    result: dict[str, Any] = {"external_source_id": case.external_source_id,
                              "reloaded": existing is not None}

    if existing is None:
        # --- the real intake workflow: draft -> validate -> submit -> approve ---
        draft = intake.create_draft(CreateDraftRequest(
            case_kind="fir_standard",
            case_category_code="FIR",
            idempotency_key=case.external_source_id,
            created_by_actor=actor,
            payload=_draft_payload(case),
            parties=_party_inputs(case),
        ))
        result["draft_key"] = draft.draft_key

        validation = intake.validate_draft(draft.draft_key)
        result["validation"] = {
            "ok": validation.ok,
            "can_submit": validation.can_submit,
            "errors": [f"{i.field}: {i.code}" for i in validation.errors],
            "warnings": [f"{i.field}: {i.code}" for i in validation.warnings],
        }
        if not validation.can_submit:
            result["status"] = "blocked_by_validation"
            return result

        intake.submit_draft(draft.draft_key, actor)
        approval = intake.review_draft(draft.draft_key, "approve", actor,
                                       "Curated public-source record load.")
        case_id = int(approval.case_master_id)
        result.update({
            "case_master_id": case_id,
            "case_version_id": int(approval.case_version_id),
            "crime_no": approval.crime_no,
            "party_roles": len(approval.case_party_role_ids),
            "canonical_persons": len(approval.canonical_person_ids),
        })
    else:
        case_id = existing
        result["case_master_id"] = case_id
        with conn.cursor() as cur:
            cur.execute('SELECT "CrimeNo" FROM "CaseMaster" WHERE "CaseMasterID"=%s',
                        (case_id,))
            row = cur.fetchone()
        result["crime_no"] = row[0] if row else None

    _stamp_curated_version(conn, case_id, case)
    result["sources"] = load_manifest_sources(conn, case_id, manifest_path, case)
    result["status"] = "loaded"
    result["read_only"] = True
    result["excluded_from_derived_analytics"] = True
    result["biometrics_recorded"] = False
    return result
