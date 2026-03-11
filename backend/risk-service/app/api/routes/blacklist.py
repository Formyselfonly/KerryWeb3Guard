from fastapi import APIRouter, HTTPException

from app.schemas.blacklist import (
    BlacklistCase,
    BlacklistReportRequest,
    BlacklistReportResponse,
    BlacklistReviewRequest,
)
from app.services.blacklist import BlacklistService

router = APIRouter(prefix="/blacklist", tags=["blacklist"])
blacklist_service = BlacklistService()


@router.post("/report", response_model=BlacklistReportResponse)
async def report_blacklist_case(
    payload: BlacklistReportRequest,
) -> BlacklistReportResponse:
    return blacklist_service.submit_report(payload)


@router.get("", response_model=list[BlacklistCase])
async def list_blacklist_cases() -> list[BlacklistCase]:
    return blacklist_service.list_cases()


@router.patch("/{case_id}", response_model=BlacklistCase)
async def review_blacklist_case(
    case_id: str,
    payload: BlacklistReviewRequest,
) -> BlacklistCase:
    try:
        return blacklist_service.review_case(case_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
