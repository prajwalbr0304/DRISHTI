"""FastAPI router for Phase-8 digital + financial imports (prefix /imports).

Gating:
  * import pipeline (templates, batches, staging, commit, rollback, supersede,
    entity-link queue, CDR/device views) — intake guards (reads pass the role gate;
    writes need an investigating/registering role + localhost + synthetic DB;
    commit/rollback/link-review need a supervisory role).
  * financial views + money alerts (accounts, transactions, money scan/alerts/
    disposition) — the 'money_trail' permission (financial data is sensitive).

Every write is localhost + synthetic-DB guarded and audited. Files are uploaded
as evidence; only committed, provenanced canonical rows affect anything. Graph
links are created as candidates and must be reviewed.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ..intake import guards
from ..money.permissions import require_money_permission, require_money_write
from . import analytics, service
from . import schemas as S
from .analytics import MoneyAlertNotFound
from .service import ImportConflict, ImportNotFound, ImportValidationError

router = APIRouter(prefix="/imports", tags=["imports"])


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except ImportNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ImportValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except ImportConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except MoneyAlertNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ---------------------------------------------------------------------------
# Templates + batches (import pipeline)
# ---------------------------------------------------------------------------
@router.get("/templates", response_model=S.TemplateListResponse)
def list_templates(_role: str = Depends(guards.require_intake_read)):
    return service.list_templates()


@router.get("/batches", response_model=S.BatchListResponse)
def list_batches(status: Optional[str] = Query(None), domain: Optional[str] = Query(None),
                 case_id: Optional[int] = Query(None, ge=1),
                 page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
                 _role: str = Depends(guards.require_intake_read)):
    return service.list_batches(status, domain, case_id, page, page_size)


@router.post("/batches", response_model=S.BatchResponse, status_code=201)
def create_batch(body: S.CreateBatchRequest,
                 role: str = Depends(guards.require_intake_write),
                 _w=Depends(guards.require_write_allowed)):
    return _call(service.create_batch, body, body.created_by_actor or role)


@router.get("/batches/{batch_id}", response_model=S.BatchResponse)
def get_batch(batch_id: int, _role: str = Depends(guards.require_intake_read)):
    return _call(service.get_batch, batch_id)


@router.get("/batches/{batch_id}/rows", response_model=S.StagingRowListResponse)
def staging_rows(batch_id: int, status: Optional[str] = Query(None, description="staged|valid|rejected|duplicate|committed"),
                 page: int = Query(1, ge=1), page_size: int = Query(100, ge=1, le=500),
                 _role: str = Depends(guards.require_intake_read)):
    return _call(service.list_staging_rows, batch_id, status, page, page_size)


@router.post("/batches/{batch_id}/commit", response_model=S.CommitResult)
def commit_batch(batch_id: int, body: S.CommitRequest | None = None,
                 role: str = Depends(guards.require_intake_review),
                 _w=Depends(guards.require_write_allowed)):
    actor = body.actor if body else None
    return _call(service.commit_batch, batch_id, actor or role)


@router.post("/batches/{batch_id}/rollback", response_model=S.RollbackResult)
def rollback_batch(batch_id: int, body: S.RollbackRequest | None = None,
                   role: str = Depends(guards.require_intake_review),
                   _w=Depends(guards.require_write_allowed)):
    actor = body.actor if body else None
    reason = body.reason if body else None
    return _call(service.rollback_batch, batch_id, actor or role, reason)


@router.post("/batches/{batch_id}/supersede", response_model=S.BatchResponse, status_code=201)
def supersede_batch(batch_id: int, body: S.SupersedeRequest,
                    role: str = Depends(guards.require_intake_write),
                    _w=Depends(guards.require_write_allowed)):
    return _call(service.supersede_batch, batch_id, body, body.actor or role)


# ---------------------------------------------------------------------------
# Reviewed entity-link queue
# ---------------------------------------------------------------------------
@router.get("/entity-links", response_model=S.EntityLinkQueueResponse)
def entity_link_queue(review_status: Optional[str] = Query(None, description="candidate|reviewed|rejected"),
                      page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
                      _role: str = Depends(guards.require_intake_read)):
    return service.entity_link_queue(review_status, page, page_size)


@router.post("/entity-links/{link_id}/review")
def review_entity_link(link_id: int, body: S.EntityLinkReviewRequest,
                       role: str = Depends(guards.require_intake_review),
                       _w=Depends(guards.require_write_allowed)):
    return _call(service.review_entity_link, link_id, body.decision, body.actor or role, body.note)


# ---------------------------------------------------------------------------
# CDR / device views (digital)
# ---------------------------------------------------------------------------
@router.get("/cdr/timeline", response_model=S.CdrTimelineResponse)
def cdr_timeline(case_id: Optional[int] = Query(None, ge=1),
                 entity_id: Optional[int] = Query(None, ge=1),
                 limit: int = Query(500, ge=1, le=2000),
                 _role: str = Depends(guards.require_intake_read)):
    return _call(service.cdr_timeline, case_id, entity_id, limit)


@router.get("/devices", response_model=S.DeviceListResponse)
def devices(case_id: Optional[int] = Query(None, ge=1),
            entity_id: Optional[int] = Query(None, ge=1),
            _role: str = Depends(guards.require_intake_read)):
    return _call(service.list_devices, case_id, entity_id)


# ---------------------------------------------------------------------------
# Financial views + money alerts (money_trail permission)
# ---------------------------------------------------------------------------
@router.get("/accounts", response_model=S.AccountListResponse,
            dependencies=[Depends(require_money_permission)])
def list_accounts(flagged: Optional[bool] = Query(None), review_status: Optional[str] = Query(None),
                  page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100)):
    return service.list_accounts(flagged, review_status, page, page_size)


@router.get("/transactions", response_model=S.TransactionListResponse,
            dependencies=[Depends(require_money_permission)])
def list_transactions(account_id: Optional[int] = Query(None, ge=1), flagged: Optional[bool] = Query(None),
                      case_id: Optional[int] = Query(None, ge=1),
                      page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100)):
    return service.list_transactions(account_id, flagged, case_id, page, page_size)


@router.get("/money/alerts", response_model=S.MoneyAlertListResponse,
            dependencies=[Depends(require_money_permission)])
def money_alerts(status: Optional[str] = Query(None), alert_type: Optional[str] = Query(None),
                 case_id: Optional[int] = Query(None, ge=1),
                 page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100)):
    return analytics.list_alerts(status, alert_type, case_id, page, page_size)


@router.post("/money/scan", response_model=S.MoneyScanResponse,
             dependencies=[Depends(require_money_write), Depends(guards.require_write_allowed)])
def money_scan(structuring_min_count: int = Query(5, ge=2, le=50),
               structuring_window_days: int = Query(14, ge=1, le=90),
               cycle_min_amount: float = Query(10000, ge=0),
               cycle_max_len: int = Query(6, ge=2, le=10)):
    from ..contracts import AiResult
    rep = analytics.scan(structuring_min_count=structuring_min_count,
                         structuring_window_days=structuring_window_days,
                         cycle_min_amount=cycle_min_amount, cycle_max_len=cycle_max_len)
    result = AiResult(
        answer=(f"Wrote {rep['alerts_written']} money alert(s): "
                + ", ".join(f"{k} {v}" for k, v in rep["by_type"].items()) + "."),
        confidence=1.0,
        source_record_ids=["MoneyAlert", "FinancialTransaction",
                           f"ModelVersion:{rep['model_version_id']}"],
        reasoning_summary=("Rule-based structuring/layering/circular detectors over the "
                           "transaction graph; reason-coded, evidence-backed, reviewable alerts. "
                           "A pattern is investigation support only, never proof of guilt."),
        model_version=f"{analytics.MODEL_NAME}@{analytics.MODEL_VERSION} (id {rep['model_version_id']})")
    return S.MoneyScanResponse(result=result, transactions_scanned=rep["transactions_scanned"],
                               alerts_written=rep["alerts_written"], by_type=rep["by_type"],
                               by_reason_code=rep["by_reason_code"],
                               model_version_id=rep["model_version_id"])


@router.post("/money/alerts/{alert_id}/disposition",
             dependencies=[Depends(require_money_write), Depends(guards.require_write_allowed)])
def money_alert_disposition(alert_id: int, body: S.MoneyAlertDispositionRequest):
    return _call(analytics.disposition, alert_id, body.disposition, body.actor, body.reason)
