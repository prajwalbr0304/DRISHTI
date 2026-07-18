"""Digital-evidence generation: logical items + storage-manifest objects.

Hackathon scope = MANUAL structured metadata only (no OCR/extraction). For every
file-backed item we generate small, unmistakably synthetic bytes, compute the
REAL SHA-256 + byte size, and record an EvidenceObject/Version. In golden mode
the bytes are written to a gitignored fixture directory (with a manifest);
at scale only the manifest + real hashes are kept so we never write 100k files.
Storage status is 'fixture_pending_cloud_upload' — no S3 upload in Phase 1.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from dataclasses import dataclass
from typing import List, Optional

from .db import Arr, Json
from . import v2common as C

C.register("EvidenceItem", [
    "EvidenceItemID", "CaseMasterID", "SourceSystemID", "SourceRecordID",
    "EvidenceType", "Category", "Title", "Description", "SyntheticReference",
    "Language", "Tags", "UploaderActor", "Confidentiality", "State",
    "ManualMetadata", "CapturedAt", "ReceivedAt", "UploadedAt",
])
C.register("EvidenceObject", [
    "EvidenceObjectID", "EvidenceItemID", "StorageKey", "StorageStatus",
    "FileName", "MimeType", "SizeBytes", "Sha256", "VersionNo", "IsCurrent",
    "ManualProvenance",
])
C.register("EvidenceVersion", [
    "EvidenceItemID", "VersionNo", "EvidenceObjectID", "ChangeReason", "CreatedByActor",
])
C.register("EvidenceCaseLink",
           ["EvidenceItemID", "CaseMasterID", "LinkType", "CreatedByActor"])
C.register("EvidenceActivityEvent", ["EvidenceItemID", "EventType", "Actor", "Detail"])
C.register("EvidenceEntityLink", [
    "EvidenceItemID", "CanonicalEntityID", "LinkType", "Confidence",
    "ReviewStatus", "SourceRecordID",
])

# type -> (mime, extension, category)
EVIDENCE_TYPES = {
    "document":         ("application/pdf", "pdf", "complaint_document"),
    "image":            ("image/jpeg", "jpg", "scene_photo"),
    "video":            ("video/mp4", "mp4", "cctv_clip"),
    "audio":            ("audio/mpeg", "mp3", "voice_recording"),
    "court_document":   ("application/pdf", "pdf", "court_order"),
    "digital_export":   ("text/csv", "csv", "device_export"),
    "financial_dataset": ("application/json", "json", "bank_statement"),
    "external_reference": (None, None, "external_reference"),
}


@dataclass
class EvidenceWriter:
    out_dir: str
    write_files: bool
    manifest: list

    @classmethod
    def create(cls, out_dir: str, write_files: bool) -> "EvidenceWriter":
        if write_files:
            os.makedirs(out_dir, exist_ok=True)
        return cls(out_dir=out_dir, write_files=write_files, manifest=[])

    def make_object_bytes(self, etype: str, ref: str, seed_text: str) -> bytes:
        """Small, obviously-synthetic file bytes for a given evidence type."""
        header = f"SYNTHETIC-DRISHTI-EVIDENCE {etype} {ref}\n".encode()
        body = (seed_text + "\n" + json.dumps(
            {"synthetic": True, "not_real": True, "ref": ref}, separators=(",", ":"))
        ).encode()
        return header + body

    def store(self, etype: str, ref: str, filename: str, content: bytes):
        """Return (storage_key, sha256, size). Writes the file in golden mode."""
        sha = hashlib.sha256(content).hexdigest()
        size = len(content)
        storage_key = f"s3://drishti-synthetic-evidence/pending/{ref}/{filename}"
        if self.write_files:
            path = os.path.join(self.out_dir, filename)
            with open(path, "wb") as fh:
                fh.write(content)
            storage_key = f"file://fixtures/{filename}|{storage_key}"
        self.manifest.append({"ref": ref, "file": filename, "sha256": sha,
                              "size": size, "type": etype, "storage_key": storage_key})
        return storage_key, sha, size

    def flush_manifest(self) -> Optional[str]:
        if not self.write_files:
            return None
        path = os.path.join(self.out_dir, "evidence_manifest.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"synthetic": True, "objects": self.manifest}, fh, indent=1)
        return path


def _ts(d: dt.datetime) -> str:
    return d.strftime("%Y-%m-%d %H:%M:%S+00")


def build_case_evidence(world: C.World, writer: EvidenceWriter, *, case_id: int,
                        source_system_id: int, source_record_id: Optional[int],
                        uploader: str, entity_ids: List[int], reg_date: dt.date,
                        want_types: List[str], allow_version_replace: bool = False,
                        allow_conflicting_meta: bool = False,
                        second_case_id: Optional[int] = None) -> None:
    w = world
    rng = w.rng
    captured = dt.datetime(reg_date.year, reg_date.month, reg_date.day, 9, 30)

    for i, etype in enumerate(want_types):
        mime, ext, category = EVIDENCE_TYPES[etype]
        item_id = w.next_id("EvidenceItem")
        ref = C.synth_token("EV", item_id)
        title = f"{category.replace('_', ' ').title()} #{item_id}"
        tags = ["synthetic", etype, category]
        meta = {"manual": True, "entered_by": uploader, "file_backed": mime is not None}
        if allow_conflicting_meta and i == 0:
            # deliberate conflicting manual metadata (kept as metadata, never canonicalised)
            meta["conflict"] = {"date_field": "2020-01-01", "note": "conflicts with case date"}
            w.cover("quality_conflicting_evidence_metadata")

        w.add("EvidenceItem", (
            item_id, case_id, source_system_id, source_record_id, etype, category,
            title, f"Synthetic {category} for demo case.", ref, "en",
            Arr(tags), uploader, "demo_normal", "available", Json(meta),
            _ts(captured), _ts(captured), _ts(captured + dt.timedelta(hours=2)),
        ))
        w.add("EvidenceActivityEvent",
              (item_id, "created", uploader, Json({"synthetic": True})))
        w.add("EvidenceCaseLink", (item_id, case_id, "evidence", uploader))
        w.cover("evidence_item")

        # file-backed items get a real-hash object + version
        if mime is not None:
            fname = f"case{case_id}_{ref}.{ext}"
            content = writer.make_object_bytes(etype, ref, title)
            skey, sha, size = writer.store(etype, ref, fname, content)
            obj_id = w.next_id("EvidenceObject")
            w.add("EvidenceObject", (
                obj_id, item_id, skey, "fixture_pending_cloud_upload", fname, mime,
                size, sha, 1, not allow_version_replace,
                Json({"manual_provenance": True, "hash_algo": "sha256"}),
            ))
            w.add("EvidenceVersion", (item_id, 1, obj_id, "initial upload", uploader))

            # version replacement scenario
            if allow_version_replace:
                content2 = content + b"\nREVISED\n"
                skey2, sha2, size2 = writer.store(etype, ref, f"v2_{fname}", content2)
                obj2 = w.next_id("EvidenceObject")
                w.add("EvidenceObject", (
                    obj2, item_id, skey2, "fixture_pending_cloud_upload",
                    f"v2_{fname}", mime, size2, sha2, 2, True,
                    Json({"manual_provenance": True, "replaces_version": 1}),
                ))
                w.add("EvidenceVersion",
                      (item_id, 2, obj2, "revised document replaces v1", uploader))
                w.add("EvidenceActivityEvent",
                      (item_id, "version_added", uploader, Json({"version": 2})))
                w.cover("evidence_version_replacement")
        else:
            w.cover("evidence_external_reference")

        # link to a canonical entity (accused/victim) with review state
        if entity_ids:
            ent = int(rng.choice(entity_ids))
            w.add("EvidenceEntityLink",
                  (item_id, ent, "mentions", round(float(rng.g.uniform(0.6, 0.95)), 5),
                   "reviewed" if rng.bernoulli(0.6) else "candidate", source_record_id))

        # multi-case link scenario
        if second_case_id is not None and i == 0:
            w.add("EvidenceCaseLink", (item_id, second_case_id, "related", uploader))
            w.add("EvidenceActivityEvent",
                  (item_id, "linked", uploader, Json({"case": second_case_id})))
            w.cover("evidence_multi_case_link")
