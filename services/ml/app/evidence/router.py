"""FastAPI router for the digital-evidence platform (Phase 5).

Endpoints (prefix /evidence):
  GET    /evidence/status                          — S3/hackathon flags (drives UI)
  GET    /evidence/lookups                          — types/categories/etc for the form
  GET    /evidence/items                            — evidence list (filter/paginate)
  POST   /evidence/items                            — create a draft item (manual metadata)
  GET    /evidence/items/{id}                        — full item + objects/versions/activity
  PUT    /evidence/items/{id}                        — metadata correction (append-only trail)
  GET    /evidence/items/{id}/activity                — activity timeline
  POST   /evidence/items/{id}/upload-url              — short-lived pre-signed PUT (S3)
  POST   /evidence/items/{id}/complete                — validate object + hash -> object/version
  POST   /evidence/items/{id}/download-url             — short-lived pre-signed GET (S3)
  POST   /evidence/items/{id}/links                    — link a case/entity
  DELETE /evidence/items/{id}/links                    — unlink a case/entity
  POST   /evidence/items/{id}/archive                   — archive (keeps history)
  POST   /evidence/items/{id}/restore                   — restore an archived item
  POST   /evidence/migrate-legacy                       — CaseEvidence -> EvidenceItem
  POST   /evidence/reset                                — synthetic-demo reset (admin)

Writes are localhost + synthetic-DB guarded; file upload/download additionally
require a configured private bucket. File bytes never pass through the API and
are never parsed; an upload never triggers a prediction.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from . import guards, service
from .schemas import (ArchiveRequest, CompleteUploadRequest, CompleteUploadResponse,
                      CreateResponse, DownloadUrlResponse, EvidenceActivityOut,
                      EvidenceCreateRequest, EvidenceItemOut, EvidenceListResponse,
                      EvidenceLookupsResponse, EvidenceMetadataUpdate, EvidenceStatusResponse,
                      LinkRequest, MigrateLegacyRequest, MigrateLegacyResponse, ResetRequest,
                      ResetResponse, UploadUrlRequest, UploadUrlResponse)
from .service import (EvidenceConflict, EvidenceNotFound, EvidenceValidationError)

router = APIRouter(prefix="/evidence", tags=["evidence"])


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except EvidenceNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except EvidenceValidationError as exc:
        detail = {"message": str(exc), **(exc.detail or {})} if exc.detail else str(exc)
        raise HTTPException(status_code=422, detail=detail)
    except EvidenceConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc))


# --- status + lookups -------------------------------------------------------
@router.get("/status", response_model=EvidenceStatusResponse)
def evidence_status(_role: str = Depends(guards.require_evidence_read)):
    return guards.hackathon_status()


@router.get("/lookups", response_model=EvidenceLookupsResponse)
def evidence_lookups(_role: str = Depends(guards.require_evidence_read)):
    return service_lookups()


# --- list + create ----------------------------------------------------------
@router.get("/items", response_model=EvidenceListResponse)
def list_items(case_id: Optional[int] = Query(None, ge=1),
               evidence_type: Optional[str] = Query(None),
               state: Optional[str] = Query(None),
               q: Optional[str] = Query(None),
               page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
               _role: str = Depends(guards.require_evidence_read)):
    return service.list_items(case_id=case_id, evidence_type=evidence_type, state=state,
                              q=q, page=page, page_size=page_size)


@router.post("/items", response_model=CreateResponse, status_code=201)
def create_item(body: EvidenceCreateRequest,
                role: str = Depends(guards.require_evidence_write),
                _w=Depends(guards.require_write_allowed)):
    if not body.uploader_actor:
        body.uploader_actor = f"demo.{role}"
    return _call(service.create_item, body)


@router.get("/items/{item_id}", response_model=EvidenceItemOut)
def get_item(item_id: int, _role: str = Depends(guards.require_evidence_read)):
    return _call(service.get_item, item_id)


@router.put("/items/{item_id}", response_model=EvidenceItemOut)
def update_item(item_id: int, body: EvidenceMetadataUpdate,
                role: str = Depends(guards.require_evidence_write),
                _w=Depends(guards.require_write_allowed)):
    if not body.actor:
        body.actor = f"demo.{role}"
    return _call(service.update_metadata, item_id, body)


@router.get("/items/{item_id}/activity", response_model=list[EvidenceActivityOut])
def item_activity(item_id: int, _role: str = Depends(guards.require_evidence_read)):
    item = _call(service.get_item, item_id)
    return item.activity


# --- upload / complete / download (need S3) ---------------------------------
@router.post("/items/{item_id}/upload-url", response_model=UploadUrlResponse)
def upload_url(item_id: int, body: UploadUrlRequest,
               role: str = Depends(guards.require_evidence_write),
               _w=Depends(guards.require_write_allowed),
               _s3=Depends(guards.require_s3_configured)):
    if not body.actor:
        body.actor = f"demo.{role}"
    return _call(service.issue_upload_url, item_id, body)


@router.post("/items/{item_id}/complete", response_model=CompleteUploadResponse)
def complete_upload(item_id: int, body: CompleteUploadRequest,
                    role: str = Depends(guards.require_evidence_write),
                    _w=Depends(guards.require_write_allowed),
                    _s3=Depends(guards.require_s3_configured)):
    if not body.actor:
        body.actor = f"demo.{role}"
    return _call(service.complete_upload, item_id, body)


@router.post("/items/{item_id}/download-url", response_model=DownloadUrlResponse)
def download_url(item_id: int, version_no: Optional[int] = Query(None, ge=1),
                 disposition: str = Query("attachment", pattern="^(attachment|inline)$"),
                 role: str = Depends(guards.require_evidence_read),
                 _s3=Depends(guards.require_s3_configured)):
    return _call(service.download_url, item_id, version_no, f"demo.{role}", None, disposition)


# --- links / archive / restore ----------------------------------------------
@router.post("/items/{item_id}/links", response_model=EvidenceItemOut)
def link_item(item_id: int, body: LinkRequest,
              role: str = Depends(guards.require_evidence_write),
              _w=Depends(guards.require_write_allowed)):
    if not body.actor:
        body.actor = f"demo.{role}"
    return _call(service.link, item_id, body)


@router.delete("/items/{item_id}/links", response_model=EvidenceItemOut)
def unlink_item(item_id: int, case_id: Optional[int] = Query(None, ge=1),
                canonical_entity_id: Optional[int] = Query(None, ge=1),
                role: str = Depends(guards.require_evidence_write),
                _w=Depends(guards.require_write_allowed)):
    return _call(service.unlink, item_id, case_id, canonical_entity_id, f"demo.{role}")


@router.post("/items/{item_id}/archive", response_model=EvidenceItemOut)
def archive_item(item_id: int, body: ArchiveRequest | None = None,
                 role: str = Depends(guards.require_evidence_write),
                 _w=Depends(guards.require_write_allowed)):
    req = body or ArchiveRequest()
    if not req.actor:
        req.actor = f"demo.{role}"
    return _call(service.archive, item_id, req)


@router.post("/items/{item_id}/restore", response_model=EvidenceItemOut)
def restore_item(item_id: int,
                 role: str = Depends(guards.require_evidence_write),
                 _w=Depends(guards.require_write_allowed)):
    return _call(service.restore, item_id, f"demo.{role}")


# --- legacy migration + reset -----------------------------------------------
@router.post("/migrate-legacy", response_model=MigrateLegacyResponse)
def migrate_legacy(body: MigrateLegacyRequest | None = None,
                   role: str = Depends(guards.require_evidence_write),
                   _w=Depends(guards.require_write_allowed)):
    req = body or MigrateLegacyRequest()
    return _call(service.migrate_legacy, req.case_id, req.actor or f"demo.{role}")


@router.post("/reset", response_model=ResetResponse)
def reset(body: ResetRequest,
          role: str = Depends(guards.require_evidence_reset),
          _w=Depends(guards.require_write_allowed)):
    if not body.confirm:
        raise HTTPException(status_code=400,
                            detail="Set confirm=true to reset synthetic evidence for this case.")
    return _call(service.reset_case, body.case_id, body.actor or f"demo.{role}")


# --- lookups payload --------------------------------------------------------
def service_lookups() -> dict:
    from .service import ALLOWED_EVIDENCE_TYPES, CONFIDENTIALITIES

    def lv(v: str) -> dict:
        return {"value": v, "label": v.replace("_", " ").title()}

    return {
        "evidence_types": [lv(t) for t in sorted(ALLOWED_EVIDENCE_TYPES)],
        "categories": [lv(c) for c in [
            "complaint_document", "scene_photo", "cctv_clip", "voice_recording",
            "court_order", "device_export", "bank_statement", "seizure_memo",
            "forensic_report", "external_reference", "legacy"]],
        "confidentialities": [lv(c) for c in sorted(CONFIDENTIALITIES)],
        "languages": [{"value": "en", "label": "English"},
                      {"value": "kn", "label": "Kannada"},
                      {"value": "mixed", "label": "Mixed (EN/KN)"}],
        "link_types": [lv(t) for t in ["evidence", "related", "mentions", "derived"]],
        "source_systems": [{"value": "FIR_FORM", "label": "FIR form"},
                           {"value": "CSV_IMPORT", "label": "CSV import"},
                           {"value": "JSON_IMPORT", "label": "JSON import"}],
    }
