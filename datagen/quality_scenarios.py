"""Deliberate data-quality / error scenarios kept in STAGING (never canonical).

The golden fixture must exercise the failure paths natural-frequency generation
rarely hits: missing/invalid required input, duplicate source/FIR, conflicting
dates, invalid jurisdiction, duplicate/corrupt file, same-name/different-person,
alias/same-person merges (reviewed + reversible), late/retracted source,
partial/retried idempotent import and audit actor/action fixtures.

Everything invalid lands in SourceRecord/IngestionRecord/DataQualityIssue or is
quarantined — it is NEVER written into a canonical table.
"""
from __future__ import annotations

import hashlib
from typing import List

from .db import Arr, Json
from .identity import IdentityBuilder
from . import v2common as C

# source + ingestion staging columns (also used by build.py for provenance)
C.register("SourceSystem", ["SourceSystemID", "Code", "Name", "Kind", "Description"])
C.register("SourceRecord", [
    "SourceRecordID", "SourceSystemID", "ExternalRef", "RecordKind", "Payload",
    "ContentHash", "Version", "SupersededBySourceRecordID", "Status",
])
C.register("IngestionJob", [
    "IngestionJobID", "SourceSystemID", "JobKind", "IdempotencyKey", "Status",
    "DryRun", "Totals", "StartedAt", "FinishedAt",
])
C.register("IngestionRecord", [
    "IngestionJobID", "SourceRecordID", "RowNumber", "StagingPayload", "Status",
    "RejectReason",
])
C.register("DataQualityIssue", [
    "IssueType", "Severity", "SourceRecordID", "IngestionJobID", "CaseMasterID",
    "EvidenceItemID", "Detail", "Status",
])
C.register("audit_logs", ["user_id", "action", "resource", "resource_id", "detail"])
# CanonicalPerson already registered in identity.py


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


_SAME_NAMES = [
    "Ravi Kumar Gowda", "Manjunath S", "Lakshmi Devi", "Imran Khan",
    "Suresh Patil", "Ananya Rao", "Venkatesh Naik", "Fatima Sheikh",
    "Prakash Reddy", "Geetha Kumari", "Basavaraj Hiremath", "Deepa Shetty",
]


def build_quality_scenarios(world: C.World, ib: IdentityBuilder,
                            sample_case_ids: List[int], *, n_each: int = 8) -> None:
    w = world
    src_sys = w.source_system.get("CSV_IMPORT")
    fir_sys = w.source_system.get("FIR_FORM")
    cases = sample_case_ids or [None]

    def pick_case(k):
        return cases[k % len(cases)]

    # --- partial / retried idempotent import job(s) -----------------------
    def new_job(idx):
        jid = w.next_id("IngestionJob")
        w.add("IngestionJob", (
            jid, src_sys, "csv_import", C.synth_token("IDEMP", idx), "partial", False,
            Json({"received": 10, "accepted": 7, "rejected": 2, "duplicate": 1,
                  "retried": True}),
            "2025-01-10 09:00:00+00", "2025-01-10 09:05:00+00"))
        w.cover("quality_partial_retry_import")
        return jid

    def src(ext, payload, chash, status):
        sid = w.next_id("SourceRecord")
        w.add("SourceRecord",
              (sid, src_sys, ext, "case", Json(payload), chash, 1, None, status))
        return sid

    for k in range(n_each):
        job_id = new_job(k)
        c0 = pick_case(k)
        ok_src = src(f"EXT-{k}-OK", {"crime_no": "demo", "ok": True}, _sha(f"OK{k}"), "committed")
        w.add("IngestionRecord", (job_id, ok_src, 1, Json({"ok": True}), "committed", None))

        # missing required
        m_src = src(f"EXT-{k}-MISS", {"crime_no": None}, _sha(f"MISS{k}"), "rejected")
        w.add("IngestionRecord", (job_id, m_src, 2, Json({"crime_no": None}), "rejected",
                                  "missing required field: crime_no"))
        w.add("DataQualityIssue", ("missing_required", "error", m_src, job_id, None, None,
                                   Json({"field": "crime_no"}), "quarantined"))
        w.cover("quality_missing_required")

        # duplicate source (same content hash as ok)
        d_src = src(f"EXT-{k}-OK", {"crime_no": "demo", "dup": True}, _sha(f"OK{k}"), "duplicate")
        w.add("IngestionRecord", (job_id, d_src, 3, Json({"dup": True}), "duplicate",
                                  "duplicate source key"))
        w.add("DataQualityIssue", ("duplicate_source", "warning", d_src, job_id, None, None,
                                   Json({"same_hash_as": ok_src}), "resolved"))
        w.cover("quality_duplicate_source")

        # conflicting dates
        cf_src = src(f"EXT-{k}-CONF", {"incident_date": "2025-05-01",
                                       "reported_date": "2024-01-01"}, _sha(f"CONF{k}"), "staged")
        w.add("DataQualityIssue", ("conflicting_dates", "error", cf_src, job_id, c0, None,
                                   Json({"incident_after_report": True}), "open"))
        w.cover("quality_conflicting_dates")

        # invalid jurisdiction (staging only, never canonicalised)
        ij_src = src(f"EXT-{k}-INVJ", {"lat": 19.9, "lon": 72.8, "note": "off Karnataka"},
                     _sha(f"INVJ{k}"), "staged")
        w.add("DataQualityIssue", ("invalid_jurisdiction", "blocker", ij_src, job_id, None, None,
                                   Json({"reason": "outside Karnataka", "canonicalised": False}),
                                   "quarantined"))
        w.cover("quality_invalid_jurisdiction_staged")

        # late-arriving / retracted source (supersedes earlier)
        late_src = src(f"EXT-{k}-LATE", {"revised": True}, _sha(f"LATE{k}"), "received")
        r_src = w.next_id("SourceRecord")
        w.add("SourceRecord", (r_src, src_sys, f"EXT-{k}-LATE", "case",
                               Json({"retracted": True}), _sha(f"LATE{k}-r"), 2, late_src,
                               "retracted"))
        w.add("DataQualityIssue", ("late_retracted_source", "warning", r_src, job_id, c0, None,
                                   Json({"supersedes": late_src}), "resolved"))
        w.cover("quality_late_retracted_source")

    # --- same-name / different-person pairs (reviewed: NOT merged) --------
    for name in _SAME_NAMES:
        p_a = ib.mint_person(name, 1, birth_year=1990,
                             attributes={"role_class": "quality_same_name", "note": "A"})
        p_b = ib.mint_person(name, 1, birth_year=1975,
                             attributes={"role_class": "quality_same_name", "note": "B"})
        ib.add_resolution_candidate(
            p_a, p_b, "fuzzy", 0.72, status="rejected",
            features={"name_exact": True, "dob_conflict": True},
            reviewer="analyst_demo", reviewed_at="2025-02-01 10:00:00+00")
        w.cover("same_name_different_person")

    # --- alias / same-person (reviewed accepted -> merge, then split) -----
    for j, name in enumerate(_SAME_NAMES[:10]):
        p_main = ib.mint_person(name, 1, birth_year=1988,
                                attributes={"role_class": "quality_alias"})
        ib.add_alias(p_main, name.split()[0] + " " + name.split()[-1][0] + ".", "aka")
        ib.add_alias(p_main, name.split()[0][:4], "nickname")
        loser_id = w.next_id("CanonicalPerson")
        w.add("CanonicalPerson", (
            loser_id, C.person_ref(loser_id), name, False, 1, 1988, False,
            "merged", p_main, Json({"role_class": "quality_alias_dup"})))
        ib.add_resolution_candidate(
            p_main, loser_id, "deterministic", 0.97, status="accepted",
            features={"phone_match": True, "alias_match": True},
            reviewer="analyst_demo", reviewed_at="2025-02-02 10:00:00+00")
        ib.add_merge(p_main, loser_id, "merge", "same phone + alias confirmed",
                     "analyst_demo", {"loser_status": "canonical"}, {"loser_status": "merged"})
        if j < 3:  # a few reversible split examples
            ib.add_merge(p_main, loser_id, "split", "reviewer reversed the merge",
                         "supervisor_demo", {"merged": True}, {"merged": False})
        w.cover("alias_same_person")

    # --- duplicate / corrupt file (evidence quality) ----------------------
    for k in range(n_each):
        c0 = pick_case(k)
        if c0 is None:
            break
        dq_item = w.next_id("EvidenceItem")
        w.add("EvidenceItem", (
            dq_item, c0, fir_sys, None, "document", "quality_probe",
            "Quality probe document", "duplicate + corrupt file scenario",
            C.synth_token("EV", dq_item), "en", Arr(["synthetic", "quality"]),
            "system", "demo_normal", "failed", Json({"quality": True}),
            None, None, None,
        ))
        corrupt_hash = _sha(f"corrupt-{dq_item}")
        obj_c = w.next_id("EvidenceObject")
        w.add("EvidenceObject", (
            obj_c, dq_item, "s3://drishti-synthetic-evidence/quarantine/corrupt",
            "quarantined", "corrupt.pdf", "application/pdf", 12, corrupt_hash, 1,
            False, Json({"corrupt": True, "manual_provenance": True})))
        w.add("DataQualityIssue", (
            "corrupt_file", "error", None, None, c0, dq_item,
            Json({"reason": "unreadable/corrupt upload"}), "quarantined"))
        w.cover("quality_corrupt_file")

        obj_d = w.next_id("EvidenceObject")
        w.add("EvidenceObject", (
            obj_d, dq_item, "s3://drishti-synthetic-evidence/pending/dup",
            "fixture_pending_cloud_upload", "dup.pdf", "application/pdf", 12,
            corrupt_hash, 2, False,
            Json({"duplicate_hash_of": obj_c, "manual_provenance": True})))
        w.add("DataQualityIssue", (
            "duplicate_file", "warning", None, None, c0, dq_item,
            Json({"same_hash_as": obj_c}), "resolved"))
        w.cover("quality_duplicate_file_hash")

    # --- audit actor/action fixtures --------------------------------------
    actions = [
        ("io.ramesh", "case.create", "cases"),
        ("analyst.divya", "entity.merge", "people_entities"),
        ("sho.suresh", "evidence.upload", "evidence"),
        ("admin", "model.request", "predictions"),
        ("sp.anand", "report.export", "analytics"),
        ("io.ramesh", "evidence.download", "evidence"),
        ("analyst.divya", "prediction.review", "predictions"),
        ("sho.suresh", "case.update", "cases"),
        ("admin", "import.commit", "imports"),
        ("sp.anand", "audit.search", "audit"),
        ("io.ramesh", "statement.record", "statements"),
        ("analyst.divya", "graph.rebuild", "network_analysis"),
    ]
    for j, (actor, action, resource) in enumerate(actions):
        w.add("audit_logs", (None, action, resource, str(pick_case(j) or j),
                             Json({"actor": actor, "synthetic": True})))
        w.cover("audit_actor_action")
